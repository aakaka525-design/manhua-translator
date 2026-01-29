"""
Tiling Manager - Dynamic image slicing for long manga pages.

Handles:
- Overlapping tile creation
- Coordinate remapping (local → global)
- NMS-based duplicate removal
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from ..models import Box2D, RegionData


@dataclass
class Tile:
    """Represents a single tile from a larger image."""
    index: int
    y_offset: int  # Offset in original image
    x_offset: int
    height: int
    width: int
    image: np.ndarray


class TilingManager:
    """
    Manages dynamic image tiling for OCR processing.
    
    Long images are split into overlapping tiles to improve OCR accuracy,
    then results are merged with coordinate remapping and NMS deduplication.
    """
    
    def __init__(
        self,
        tile_height: int = 1024,  # 保守值，1920 会导致漏检
        overlap_ratio: float = 0.5,
        min_tile_height: int = 256,
        edge_padding: int = 64,
        edge_band_ratio: float = 0.15,
        edge_band_min_height: int = 128,
    ):
        """
        Initialize tiling manager.
        
        Args:
            tile_height: Height of each tile in pixels
            overlap_ratio: Overlap between adjacent tiles (0.0-0.5)
            min_tile_height: Minimum height to trigger tiling
        """
        self.tile_height = tile_height
        self.overlap_ratio = min(0.5, max(0.15, overlap_ratio))  # 15-50%
        self.min_tile_height = min_tile_height
        self.overlap_pixels = int(tile_height * overlap_ratio)
        self.edge_padding = max(0, edge_padding)
        self.edge_band_ratio = max(0.05, min(0.5, edge_band_ratio))
        self.edge_band_min_height = max(32, edge_band_min_height)
    
    def should_tile(self, image_height: int) -> bool:
        """Check if image needs tiling."""
        return image_height > self.tile_height * 1.5
    
    def create_tiles(self, image: np.ndarray) -> list[Tile]:
        """
        Create overlapping tiles from image.
        
        Args:
            image: Source image (BGR format)
            
        Returns:
            List of Tile objects
        """
        height, width = image.shape[:2]
        
        if not self.should_tile(height):
            # Return single tile for small images
            return [Tile(
                index=0,
                y_offset=0,
                x_offset=0,
                height=height,
                width=width,
                image=image,
            )]
        
        tiles = []
        stride = self.tile_height - self.overlap_pixels
        y = 0
        index = 0
        
        while y < height:
            y_end = min(y + self.tile_height, height)
            
            # Ensure last tile has minimum height
            if height - y_end < self.min_tile_height and y_end < height:
                y_end = height

            y_start = max(0, y - self.edge_padding)
            y_end = min(height, y_end + self.edge_padding)

            tile_image = image[y_start:y_end, :].copy()
            
            tiles.append(Tile(
                index=index,
                y_offset=y_start,
                x_offset=0,
                height=y_end - y_start,
                width=width,
                image=tile_image,
            ))
            
            index += 1
            y += stride
            
            # Break if we've reached the end
            if y_end >= height:
                break
        
        return tiles

    def create_edge_tiles(self, image: np.ndarray) -> list[Tile]:
        """
        Create top/bottom edge tiles for boundary OCR.

        These tiles are used to catch text that gets cut by normal tiling.
        """
        height, width = image.shape[:2]
        band_height = max(int(height * self.edge_band_ratio), self.edge_band_min_height)
        band_height = min(band_height, height)

        top_end = min(height, band_height + self.edge_padding)
        bottom_start = max(0, height - band_height - self.edge_padding)

        tiles = [
            Tile(
                index=0,
                y_offset=0,
                x_offset=0,
                height=top_end,
                width=width,
                image=image[0:top_end, :].copy(),
            ),
            Tile(
                index=1,
                y_offset=bottom_start,
                x_offset=0,
                height=height - bottom_start,
                width=width,
                image=image[bottom_start:height, :].copy(),
            ),
        ]
        return tiles
    
    def remap_regions(
        self, 
        regions: list[RegionData], 
        tile: Tile
    ) -> list[RegionData]:
        """
        Remap region coordinates from tile-local to global.
        
        Args:
            regions: Regions with local coordinates
            tile: Source tile for offset information
            
        Returns:
            Regions with global coordinates
        """
        remapped = []
        
        for region in regions:
            if region.box_2d is None:
                remapped.append(region)
                continue
            
            # Apply offset
            global_box = Box2D(
                x1=region.box_2d.x1 + tile.x_offset,
                y1=region.box_2d.y1 + tile.y_offset,
                x2=region.box_2d.x2 + tile.x_offset,
                y2=region.box_2d.y2 + tile.y_offset,
            )
            
            # Create new region with global coordinates
            new_region = RegionData(
                region_id=region.region_id,
                box_2d=global_box,
                source_text=region.source_text,
                target_text=region.target_text,
                confidence=region.confidence,
                font_style_params=region.font_style_params,
                mask_path=region.mask_path,
            )
            remapped.append(new_region)
        
        return remapped
    
    def merge_regions(
        self,
        all_regions: list[RegionData],
        iou_threshold: float = 0.7,  # 高阈值，只合并高度重叠的区域
    ) -> list[RegionData]:
        """
        Merge overlapping regions using NMS-like algorithm.
        
        Args:
            all_regions: All regions from all tiles
            iou_threshold: IOU threshold for considering duplicates
            
        Returns:
            Deduplicated regions
        """
        if len(all_regions) <= 1:
            return all_regions
        
        # Filter regions with boxes
        regions_with_boxes = [r for r in all_regions if r.box_2d]
        regions_without_boxes = [r for r in all_regions if not r.box_2d]
        
        if not regions_with_boxes:
            return all_regions
        
        # Sort by confidence (descending) then by y position
        regions_with_boxes.sort(
            key=lambda r: (-r.confidence if r.confidence else 0, r.box_2d.y1)
        )
        
        keep = []
        suppressed = set()
        
        def text_similar(t1: str, t2: str) -> bool:
            """检查两个文本是否完全相同（忽略大小写和空白）"""
            if not t1 or not t2:
                return False
            t1 = t1.strip().upper()
            t2 = t2.strip().upper()
            return t1 == t2  # 只有完全相同才去重，不做子串匹配
        
        for i, region in enumerate(regions_with_boxes):
            if i in suppressed:
                continue
            
            keep.append(region)
            
            # Check remaining regions
            for j in range(i + 1, len(regions_with_boxes)):
                if j in suppressed:
                    continue
                
                other = regions_with_boxes[j]
                iou = self._calculate_iou(region.box_2d, other.box_2d)
                
                # 只根据位置重叠去重，不检查文本相似度
                # 避免误删多行文字中的不同行
                is_duplicate = iou > iou_threshold
                
                if is_duplicate:
                    # Same region detected in overlapping tiles
                    # Keep the one with higher confidence (already sorted)
                    suppressed.add(j)
                    
                    # Optionally keep longer text
                    if other.source_text and region.source_text:
                        if len(other.source_text) > len(region.source_text):
                            keep[-1] = other
        
        return keep + regions_without_boxes
    
    def _calculate_iou(self, box1: Box2D, box2: Box2D) -> float:
        """Calculate Intersection over Union of two boxes."""
        # Calculate intersection
        x1 = max(box1.x1, box2.x1)
        y1 = max(box1.y1, box2.y1)
        x2 = min(box1.x2, box2.x2)
        y2 = min(box1.y2, box2.y2)
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        
        # Calculate union
        area1 = box1.width * box1.height
        area2 = box2.width * box2.height
        union = area1 + area2 - intersection
        
        if union <= 0:
            return 0.0
        
        return intersection / union


# Singleton instance
_tiling_manager: Optional[TilingManager] = None


def get_tiling_manager() -> TilingManager:
    """Get or create the global tiling manager instance."""
    global _tiling_manager
    if _tiling_manager is None:
        _tiling_manager = TilingManager()
    return _tiling_manager

"""
Image Inpainting - Text removal and background restoration.

Provides two implementations:
1. LamaInpainter: High-quality using LaMa model (preferred)
2. OpenCVInpainter: Fallback using classical algorithms
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..models import RegionData


class Inpainter(ABC):
    """Abstract base class for image inpainting."""

    @abstractmethod
    async def inpaint(
        self,
        image_path: str,
        mask_path: str,
        output_path: str,
    ) -> str:
        """
        Inpaint image using provided mask.
        
        Args:
            image_path: Source image path
            mask_path: Binary mask (white = areas to inpaint)
            output_path: Path to save result
            
        Returns:
            Path to inpainted image
        """
        pass

    async def inpaint_regions(
        self,
        image_path: str,
        regions: list[RegionData],
        output_path: str,
        temp_dir: str = "./temp",
        dilation: int = 4,  # Reduced to avoid mask merging across bubbles
    ) -> tuple[str, str]:
        """
        Inpaint all regions in an image.
        
        Args:
            image_path: Source image path
            regions: Regions with box_2d to inpaint
            output_path: Path to save result
            temp_dir: Directory for temporary files
            dilation: Mask dilation in pixels
            
        Returns:
            Path to inpainted image
        """
        # Create combined mask
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        height, width = image.shape[:2]
        combined_mask = np.zeros((height, width), dtype=np.uint8)

        for region in regions:
            if region.box_2d is None:
                continue
            
            # 跳过 SFX 区域（不需要擦除）
            if region.target_text and region.target_text.startswith("[SFX:"):
                continue

            box = region.box_2d
            
            # Expand box to cover full text area with generous margin
            # Increased to 25 to handle edge cases where original text
            # extends beyond detected OCR box boundaries (especially for Korean)
            expand = 10  # Smaller margin to reduce mask merging across bubbles
            y1 = max(0, box.y1 - expand)
            y2 = min(height, box.y2 + expand)
            x1 = max(0, box.x1 - expand)
            x2 = min(width, box.x2 + expand)
            
            # Strategy: Fill entire detected region as mask
            # This is more reliable than pixel-level detection for complex backgrounds
            # The OCR has already identified these as text regions
            
            # Create full-box mask
            roi_mask = np.ones((y2 - y1, x2 - x1), dtype=np.uint8) * 255
            
            # Optionally refine with text detection for cleaner edges
            roi = image[y1:y2, x1:x2]
            if roi.size > 0:
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                mean_brightness = roi_gray.mean()
                
                # Try to detect text pixels for refinement
                if mean_brightness > 100:
                    _, text_mask = cv2.threshold(roi_gray, 140, 255, cv2.THRESH_BINARY_INV)
                else:
                    _, text_mask = cv2.threshold(roi_gray, 110, 255, cv2.THRESH_BINARY)
                
                # Dilate text mask to cover text edges
                if dilation > 0:
                    # 核大小 = dilation * 2 + 1，当 dilation=8 时为 17px
                    kernel_size = dilation * 2 + 1
                    kernel = cv2.getStructuringElement(
                        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
                    )
                    text_mask = cv2.dilate(text_mask, kernel)
                    text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, kernel)
                
                # Use union of full box and detected text
                roi_mask = cv2.bitwise_or(roi_mask, text_mask)

            # Add to combined mask
            combined_mask[y1:y2, x1:x2] = np.maximum(
                combined_mask[y1:y2, x1:x2],
                roi_mask
            )

        # Post-process: Fill vertical gaps between nearby text regions
        # This handles OCR miss of some text lines
        combined_mask = self._fill_vertical_gaps(combined_mask, regions, height, width)

        # Save combined mask
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        mask_path = Path(temp_dir) / f"combined_mask_{Path(image_path).stem}.png"
        cv2.imwrite(str(mask_path), combined_mask)

        # Inpaint
        result_path = await self.inpaint(image_path, str(mask_path), output_path)
        return result_path, str(mask_path)
    
    def _fill_vertical_gaps(
        self, 
        mask: np.ndarray, 
        regions: list[RegionData],
        height: int,
        width: int,
        max_gap: int = 0
    ) -> np.ndarray:
        """
        Fill vertical gaps between text regions that likely belong to same paragraph.
        
        This compensates for OCR missing some text lines.
        """
        if len(regions) < 2:
            return mask
        
        # Sort regions by Y position
        sorted_regions = sorted(
            [r for r in regions if r.box_2d], 
            key=lambda r: r.box_2d.y1
        )
        
        for i in range(len(sorted_regions) - 1):
            curr = sorted_regions[i].box_2d
            next_r = sorted_regions[i + 1].box_2d
            
            # Calculate gap
            y_gap = next_r.y1 - curr.y2
            
            # Check X overlap
            x_overlap = min(curr.x2, next_r.x2) - max(curr.x1, next_r.x1)
            min_width = min(curr.width, next_r.width)
            
            # If there's significant X overlap and reasonable Y gap, fill it
            if 0 < y_gap < max_gap and x_overlap > min_width * 0.5:
                # Fill the gap region
                fill_x1 = max(0, min(curr.x1, next_r.x1) - 10)
                fill_x2 = min(width, max(curr.x2, next_r.x2) + 10)
                fill_y1 = curr.y2
                fill_y2 = next_r.y1
                
                mask[fill_y1:fill_y2, fill_x1:fill_x2] = 255
        
        return mask


class LamaInpainter(Inpainter):
    """
    High-quality inpainting using LaMa (Large Mask Inpainting).
    
    Features:
    - Smart chunking: processes only regions containing text
    - Memory efficient: releases memory after each chunk
    """

    # Maximum chunk size to prevent OOM
    MAX_CHUNK_SIZE = 2048  # pixels

    def __init__(self, device: str = "cpu"):
        """
        Initialize LaMa inpainter.
        
        Args:
            device: Device to run on ('cpu' or 'mps' for Apple Silicon)
        """
        # Auto-detect MPS for Apple Silicon
        if device == "cpu":
            try:
                import torch
                if torch.backends.mps.is_available():
                    device = "mps"
            except Exception:
                pass
        self.device = device
        self._model = None

    def _init_model(self):
        """Lazy initialization of LaMa model."""
        if self._model is None:
            try:
                from simple_lama_inpainting import SimpleLama
                self._model = SimpleLama(device=self.device)
            except ImportError:
                raise ImportError(
                    "simple-lama-inpainting required. Install with:\n"
                    "pip install simple-lama-inpainting"
                )
        return self._model

    async def inpaint(
        self,
        image_path: str,
        mask_path: str,
        output_path: str,
    ) -> str:
        """Inpaint using LaMa model."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._inpaint_sync, image_path, mask_path, output_path
        )

    def _inpaint_sync(
        self,
        image_path: str,
        mask_path: str,
        output_path: str,
    ) -> str:
        """
        Synchronous LaMa inpainting with smart chunking.
        
        For large images, splits into chunks based on mask regions
        to reduce memory usage.
        """
        from PIL import Image
        import gc
        
        model = self._init_model()
        
        # Load images
        image = Image.open(image_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")
        
        width, height = image.size
        
        # If image is small enough, process directly
        if height <= self.MAX_CHUNK_SIZE and width <= self.MAX_CHUNK_SIZE:
            result = model(image, mask)
            result.save(output_path)
            return output_path
        
        # Find regions that need inpainting
        mask_np = np.array(mask)
        chunks = self._find_mask_chunks(mask_np)
        
        if not chunks:
            # No mask regions, save original
            image.save(output_path)
            return output_path
        
        # Process each chunk
        result_np = np.array(image)
        
        for chunk_y1, chunk_y2, chunk_x1, chunk_x2 in chunks:
            # Add padding for better inpainting
            pad = 50
            y1 = max(0, chunk_y1 - pad)
            y2 = min(height, chunk_y2 + pad)
            x1 = max(0, chunk_x1 - pad)
            x2 = min(width, chunk_x2 + pad)
            
            # Extract chunk
            chunk_img = image.crop((x1, y1, x2, y2))
            chunk_mask = mask.crop((x1, y1, x2, y2))
            
            # Process chunk
            try:
                chunk_result = model(chunk_img, chunk_mask)
                chunk_result_np = np.array(chunk_result)
                
                # Place result back (without padding overlap issues)
                inner_y1 = chunk_y1 - y1
                inner_y2 = inner_y1 + (chunk_y2 - chunk_y1)
                inner_x1 = chunk_x1 - x1
                inner_x2 = inner_x1 + (chunk_x2 - chunk_x1)
                
                result_np[chunk_y1:chunk_y2, chunk_x1:chunk_x2] = \
                    chunk_result_np[inner_y1:inner_y2, inner_x1:inner_x2]
                
            except Exception as e:
                print(f"Chunk inpaint failed: {e}")
                continue
            finally:
                # Release memory
                del chunk_img, chunk_mask
                gc.collect()
        
        # Save result
        result = Image.fromarray(result_np)
        result.save(output_path)
        
        # Cleanup
        del result_np
        gc.collect()
        
        return output_path

    def _find_mask_chunks(self, mask_np: np.ndarray) -> list[tuple[int, int, int, int]]:
        """
        Find bounding boxes of mask regions to create processing chunks.
        
        Groups nearby regions to minimize number of chunks.
        
        Returns:
            List of (y1, y2, x1, x2) tuples for each chunk
        """
        # Find contours of mask regions
        _, binary = cv2.threshold(mask_np, 127, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return []
        
        # Get bounding boxes
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 5 and h > 5:  # Filter tiny regions
                boxes.append((y, y + h, x, x + w))
        
        if not boxes:
            return []
        
        # Merge nearby boxes into chunks
        return self._merge_boxes_to_chunks(boxes, mask_np.shape[0], mask_np.shape[1])

    def _merge_boxes_to_chunks(
        self, 
        boxes: list[tuple], 
        height: int, 
        width: int,
        gap_threshold: int = 100
    ) -> list[tuple[int, int, int, int]]:
        """Merge nearby boxes into larger chunks."""
        if not boxes:
            return []
        
        # Sort by y position
        boxes = sorted(boxes, key=lambda b: b[0])
        
        chunks = []
        current_chunk = list(boxes[0])  # [y1, y2, x1, x2]
        
        for y1, y2, x1, x2 in boxes[1:]:
            # Check if this box should merge with current chunk
            # Merge if vertically close
            if y1 - current_chunk[1] < gap_threshold:
                # Expand current chunk
                current_chunk[0] = min(current_chunk[0], y1)
                current_chunk[1] = max(current_chunk[1], y2)
                current_chunk[2] = min(current_chunk[2], x1)
                current_chunk[3] = max(current_chunk[3], x2)
            else:
                # Start new chunk
                chunks.append(tuple(current_chunk))
                current_chunk = [y1, y2, x1, x2]
        
        # Add last chunk
        chunks.append(tuple(current_chunk))
        
        # Split chunks that are too large
        final_chunks = []
        for y1, y2, x1, x2 in chunks:
            chunk_height = y2 - y1
            if chunk_height > self.MAX_CHUNK_SIZE:
                # Split vertically
                for start in range(y1, y2, self.MAX_CHUNK_SIZE - 100):
                    end = min(start + self.MAX_CHUNK_SIZE, y2)
                    final_chunks.append((start, end, x1, x2))
            else:
                final_chunks.append((y1, y2, x1, x2))
        
        return final_chunks


class OpenCVInpainter(Inpainter):
    """
    Fallback inpainting using OpenCV classical algorithms.
    
    Uses Navier-Stokes or Telea algorithm.
    Less quality than LaMa but works without ML dependencies.
    """

    def __init__(self, method: str = "telea", radius: int = 3):
        """
        Initialize OpenCV inpainter.
        
        Args:
            method: 'telea' or 'ns' (Navier-Stokes)
            radius: Inpainting radius
        """
        self.method = method
        self.radius = radius
        
        if method == "telea":
            self.flags = cv2.INPAINT_TELEA
        elif method == "ns":
            self.flags = cv2.INPAINT_NS
        else:
            raise ValueError(f"Unknown method: {method}. Use 'telea' or 'ns'")

    async def inpaint(
        self,
        image_path: str,
        mask_path: str,
        output_path: str,
    ) -> str:
        """Inpaint using OpenCV."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._inpaint_sync, image_path, mask_path, output_path
        )

    def _inpaint_sync(
        self,
        image_path: str,
        mask_path: str,
        output_path: str,
    ) -> str:
        """Synchronous OpenCV inpainting."""
        # Read images
        image = cv2.imread(image_path)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        if mask is None:
            raise FileNotFoundError(f"Cannot read mask: {mask_path}")

        # Ensure mask is binary
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        # Inpaint
        result = cv2.inpaint(image, mask, self.radius, self.flags)

        # Save result
        cv2.imwrite(output_path, result)
        return output_path


def create_inpainter(prefer_lama: bool = True, device: str = "cpu") -> Inpainter:
    """
    Factory function to create appropriate inpainter.
    
    Args:
        prefer_lama: Try LaMa first, fallback to OpenCV
        device: Device for LaMa ('cpu' or 'cuda')
        
    Returns:
        Inpainter instance
    """
    if prefer_lama:
        try:
            inpainter = LamaInpainter(device=device)
            inpainter._init_model()  # Test if LaMa works
            return inpainter
        except (ImportError, Exception) as e:
            print(f"LaMa not available ({e}), falling back to OpenCV")
    
    return OpenCVInpainter()

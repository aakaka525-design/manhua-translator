"""
Text Region Detector - Detects speech bubbles and text areas in manga images.

Provides two implementations:
1. ContourDetector: MVP using morphological operations (no ML dependencies)
2. YOLODetector: Production-ready using YOLOv8 (optional)
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from uuid import uuid4

import cv2
import numpy as np

from ..models import Box2D, RegionData
from ..image_io import save_image


class TextDetector(ABC):
    """Abstract base class for text region detection."""

    @abstractmethod
    async def detect(self, image_path: str) -> list[RegionData]:
        """
        Detect text regions in an image.
        
        Args:
            image_path: Path to input image
            
        Returns:
            List of RegionData with box_2d filled
        """
        pass


class ContourDetector(TextDetector):
    """
    MVP text detector using contour analysis.
    
    Applicable for manga with clear speech bubble boundaries.
    Uses morphological operations to find text regions.
    """

    def __init__(
        self,
        min_area: int = 1000,
        max_area: int = 500000,
        padding: int = 5,
        binary_threshold: int = 240,
    ):
        """
        Initialize contour detector.
        
        Args:
            min_area: Minimum contour area to consider
            max_area: Maximum contour area to consider
            padding: Padding around detected regions
            binary_threshold: Threshold for binary conversion
        """
        self.min_area = min_area
        self.max_area = max_area
        self.padding = padding
        self.binary_threshold = binary_threshold

    async def detect(self, image_path: str) -> list[RegionData]:
        """Detect text regions using contour analysis."""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._detect_sync, image_path)

    def _detect_sync(self, image_path: str) -> list[RegionData]:
        """Synchronous detection implementation."""
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Binary threshold to find white regions (speech bubbles)
        _, binary = cv2.threshold(
            gray, self.binary_threshold, 255, cv2.THRESH_BINARY
        )

        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            
            # Filter by area
            if area < self.min_area or area > self.max_area:
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)

            # Apply padding
            x1 = max(0, x - self.padding)
            y1 = max(0, y - self.padding)
            x2 = min(width, x + w + self.padding)
            y2 = min(height, y + h + self.padding)

            # Calculate confidence based on contour properties
            # Higher aspect ratio or very small areas get lower confidence
            aspect_ratio = w / h if h > 0 else 0
            if 0.3 < aspect_ratio < 3.0:
                confidence = min(0.95, 0.5 + (area / self.max_area) * 0.5)
            else:
                confidence = 0.5

            region = RegionData(
                region_id=uuid4(),
                box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2),
                confidence=confidence,
            )
            regions.append(region)

        # Sort by position (top-to-bottom, left-to-right)
        regions.sort(key=lambda r: (r.box_2d.y1, r.box_2d.x1))

        return regions

    def generate_mask(
        self,
        image_path: str,
        region: RegionData,
        output_path: str,
        dilation: int = 3,
    ) -> str:
        """
        Generate binary mask for a text region.
        
        Args:
            image_path: Source image path
            region: Region data with box_2d
            output_path: Path to save mask
            dilation: Dilation pixels (3-5 recommended)
            
        Returns:
            Path to saved mask
        """
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        height, width = image.shape[:2]
        box = region.box_2d

        # Create mask
        mask = np.zeros((height, width), dtype=np.uint8)

        # Extract region and find text
        roi = image[box.y1:box.y2, box.x1:box.x2]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Detect dark pixels (text) in white bubble
        _, roi_binary = cv2.threshold(roi_gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Dilate to cover text edges
        if dilation > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation * 2 + 1, dilation * 2 + 1))
            roi_binary = cv2.dilate(roi_binary, kernel)

        # Place in full mask
        mask[box.y1:box.y2, box.x1:box.x2] = roi_binary

        return save_image(mask, output_path, purpose="intermediate")


class YOLODetector(TextDetector):
    """
    Production text detector using YOLOv8.
    
    Requires: ultralytics package and trained weights.
    """

    def __init__(self, model_path: Optional[str] = None, confidence: float = 0.5):
        """
        Initialize YOLO detector.
        
        Args:
            model_path: Path to YOLO weights file
            confidence: Minimum confidence threshold
        """
        self.model_path = model_path
        self.confidence = confidence
        self._model = None

    def _load_model(self):
        """Lazy load YOLO model."""
        if self._model is None:
            try:
                from ultralytics import YOLO
                self._model = YOLO(self.model_path)
            except ImportError:
                raise ImportError("ultralytics package required. Install with: pip install ultralytics")
        return self._model

    async def detect(self, image_path: str) -> list[RegionData]:
        """Detect text regions using YOLO."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._detect_sync, image_path)

    def _detect_sync(self, image_path: str) -> list[RegionData]:
        """Synchronous YOLO detection."""
        model = self._load_model()
        results = model(image_path, conf=self.confidence, verbose=False)

        regions = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for i, box in enumerate(boxes.xyxy):
                x1, y1, x2, y2 = map(int, box.tolist())
                conf = float(boxes.conf[i])

                region = RegionData(
                    region_id=uuid4(),
                    box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2),
                    confidence=conf,
                )
                regions.append(region)

        # Sort by position
        regions.sort(key=lambda r: (r.box_2d.y1, r.box_2d.x1))
        return regions

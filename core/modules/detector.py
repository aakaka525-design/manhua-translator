"""
Updated Detector Module - Uses real vision processing.

Replaces mock implementation with ContourDetector.
"""

import asyncio
from pathlib import Path
from typing import Optional

from ..models import TaskContext
from ..modules.base import BaseModule
from ..vision import ContourDetector, TextDetector


class DetectorModule(BaseModule):
    """
    Text region detector using vision processing.
    
    Uses ContourDetector by default, can be configured
    to use YOLODetector for production.
    """

    def __init__(
        self,
        detector: Optional[TextDetector] = None,
        min_area: int = 1000,
        max_area: int = 500000,
    ):
        """
        Initialize detector module.
        
        Args:
            detector: Custom detector instance
            min_area: Minimum region area (for ContourDetector)
            max_area: Maximum region area (for ContourDetector)
        """
        super().__init__(name="Detector")
        self.detector = detector or ContourDetector(
            min_area=min_area,
            max_area=max_area,
        )

    async def process(self, context: TaskContext) -> TaskContext:
        """
        Detect text regions in the image.
        
        Args:
            context: Task context with image_path
            
        Returns:
            Updated context with detected regions
        """
        if not await self.validate_input(context):
            raise ValueError("Invalid input: image_path is required")

        # Run detection
        regions = await self.detector.detect(context.image_path)
        context.regions = regions

        return context

    async def validate_input(self, context: TaskContext) -> bool:
        """Validate that image path exists."""
        if not context.image_path:
            return False
        return Path(context.image_path).exists()

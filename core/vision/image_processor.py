"""
ImageProcessor - Unified Vision Processing Interface.

Combines detection, OCR, and inpainting into a single class
that outputs:
1. Inpainted background image (text removed)
2. Text metadata JSON (regions with source_text)
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from uuid import UUID

from .text_detector import TextDetector, ContourDetector
from .ocr_engine import OCREngine, PaddleOCREngine, MockOCREngine
from .inpainter import Inpainter, create_inpainter
from ..models import RegionData, TaskContext


class ImageProcessor:
    """
    Unified image processor for manga translation.
    
    Orchestrates the vision pipeline:
    1. Detection: Find text regions
    2. OCR: Recognize text content
    3. Inpainting: Remove text from image
    """

    def __init__(
        self,
        detector: Optional[TextDetector] = None,
        ocr_engine: Optional[OCREngine] = None,
        inpainter: Optional[Inpainter] = None,
        output_dir: str = "./output",
        temp_dir: str = "./temp",
        use_mock_ocr: bool = False,
    ):
        """
        Initialize image processor.
        
        Args:
            detector: Text detector instance
            ocr_engine: OCR engine instance
            inpainter: Inpainter instance
            output_dir: Directory for output files
            temp_dir: Directory for temporary files
            use_mock_ocr: Use mock OCR (for testing without PaddleOCR)
        """
        self.detector = detector or ContourDetector()
        
        if use_mock_ocr:
            self.ocr_engine = MockOCREngine()
        else:
            self.ocr_engine = ocr_engine or self._create_ocr_engine()
        
        self.inpainter = inpainter or create_inpainter(prefer_lama=True)
        
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _create_ocr_engine(self) -> OCREngine:
        """Create OCR engine with fallback."""
        try:
            engine = PaddleOCREngine(lang="en")
            engine._init_ocr()  # Test initialization
            return engine
        except Exception as e:
            print(f"PaddleOCR not available ({e}), using mock OCR")
            return MockOCREngine()

    async def process(
        self,
        image_path: str,
        output_prefix: Optional[str] = None,
        use_integrated_ocr: bool = True,
    ) -> tuple[str, list[RegionData]]:
        """
        Process a single image through the full pipeline.
        
        Args:
            image_path: Path to input image
            output_prefix: Prefix for output files
            use_integrated_ocr: Deprecated, always uses detect_and_recognize
            
        Returns:
            Tuple of (inpainted_image_path, regions_with_text)
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        prefix = output_prefix or image_path.stem

        # 始终使用 detect_and_recognize 统一入口（支持长图切片）
        regions = await self.ocr_engine.detect_and_recognize(str(image_path))
        
        if not regions:
            return str(image_path), []

        # Step 3: Inpainting
        output_path = self.output_dir / f"{prefix}_inpainted.png"
        result = await self.inpainter.inpaint_regions(
            str(image_path),
            regions,
            str(output_path),
            str(self.temp_dir),
            # dilation uses default (8) for better edge coverage
        )
        if isinstance(result, tuple):
            output_path, _ = result
        else:
            output_path = result

        return str(output_path), regions

    async def process_batch(
        self,
        image_paths: list[str],
        max_concurrent: int = 5,
    ) -> list[tuple[str, list[RegionData]]]:
        """
        Process multiple images concurrently.
        
        Args:
            image_paths: List of image paths
            max_concurrent: Maximum concurrent tasks
            
        Returns:
            List of (output_path, regions) tuples
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(path: str):
            async with semaphore:
                return await self.process(path)

        tasks = [process_with_semaphore(p) for p in image_paths]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def export_metadata(
        self,
        regions: list[RegionData],
        output_path: str,
    ) -> str:
        """
        Export regions metadata to JSON.
        
        Args:
            regions: List of regions with text
            output_path: Path for JSON file
            
        Returns:
            Path to saved JSON
        """
        data = [
            {
                "region_id": str(r.region_id),
                "box_2d": {
                    "x1": r.box_2d.x1,
                    "y1": r.box_2d.y1,
                    "x2": r.box_2d.x2,
                    "y2": r.box_2d.y2,
                } if r.box_2d else None,
                "source_text": r.source_text,
                "confidence": r.confidence,
            }
            for r in regions
        ]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return output_path


# Convenience function
async def process_image(
    image_path: str,
    output_dir: str = "./output",
    use_mock: bool = False,
) -> tuple[str, list[RegionData]]:
    """
    Process a single image (convenience function).
    
    Args:
        image_path: Input image path
        output_dir: Output directory
        use_mock: Use mock OCR for testing
        
    Returns:
        Tuple of (output_path, regions)
    """
    processor = ImageProcessor(
        output_dir=output_dir,
        use_mock_ocr=use_mock,
    )
    return await processor.process(image_path)

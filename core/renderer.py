"""
Text Renderer - Stylized Chinese text rendering for manga.

Features:
- Style estimation from original image
- Dynamic font sizing to fit bubbles
- Chinese-aware text wrapping
- Stroke/outline support for readability
"""

import asyncio
import math
import re
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .models import Box2D, FontStyleParams, RegionData


# Chinese typography rules - punctuation handling
FORBIDDEN_LINE_START = ".,;:?!，。；：？！）】》、"
FORBIDDEN_LINE_END = "（【《"



class StyleEstimator:
    """
    Estimates text style from original image regions.
    
    Analyzes the original text area to extract:
    - Text color
    - Background color
    - Appropriate font size
    """

    def __init__(self, default_color: str = "#000000"):
        """
        Initialize style estimator.
        
        Args:
            default_color: Default text color if detection fails
        """
        self.default_color = default_color

    def estimate_text_color(
        self,
        image: np.ndarray,
        box: Box2D,
        invert: bool = True,
    ) -> str:
        """
        Estimate text color from image region using mode (most common color).
        
        For manga, text often has anti-aliasing, so we use the mode
        instead of mean for more accurate color detection.
        
        Args:
            image: Source image (BGR format)
            box: Bounding box
            invert: If True, detect dark pixels (text) on light background
            
        Returns:
            Hex color string
        """
        try:
            # Extract region
            roi = image[box.y1:box.y2, box.x1:box.x2]
            if roi.size == 0:
                return self.default_color

            # Convert to grayscale for analysis
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Determine background brightness
            mean_brightness = gray.mean()
            
            # For manga: detect text pixels based on background
            if mean_brightness > 127:
                # Light background -> dark text
                mask = gray < 100  # Stricter threshold for text
            else:
                # Dark background -> light text
                mask = gray > 180
            
            if not mask.any():
                return self.default_color

            # Get text pixels
            text_pixels = roi[mask]
            if len(text_pixels) == 0:
                return self.default_color

            # Use mode (most common color) instead of mean
            # Quantize to reduce color space for mode calculation
            quantized = (text_pixels // 16) * 16
            # Find the most common color
            from collections import Counter
            pixel_tuples = [tuple(p) for p in quantized]
            if not pixel_tuples:
                return self.default_color
            
            mode_color = Counter(pixel_tuples).most_common(1)[0][0]
            # BGR to RGB
            b, g, r = mode_color
            
            return f"#{r:02x}{g:02x}{b:02x}"

        except Exception:
            return self.default_color

    def estimate_font_size(
        self,
        box: Box2D,
        text_length: int,
        min_size: int = 12,
        max_size: int = 48,
        padding_ratio: float = 0.1,
    ) -> int:
        """
        Estimate appropriate font size based on box dimensions and text length.
        
        Args:
            box: Bounding box
            text_length: Number of characters
            min_size: Minimum font size
            max_size: Maximum font size
            padding_ratio: Padding ratio inside box
            
        Returns:
            Estimated font size
        """
        if text_length == 0:
            return min_size

        # Available area with padding
        available_width = box.width * (1 - 2 * padding_ratio)
        available_height = box.height * (1 - 2 * padding_ratio)

        # Estimate based on area
        # Assume square-ish characters for CJK
        char_area = (available_width * available_height) / text_length
        estimated_size = int(math.sqrt(char_area))

        # Also consider width constraint
        # Assume roughly 1.2 characters per line width
        lines_needed = math.ceil(text_length * estimated_size / available_width)
        size_by_height = int(available_height / max(lines_needed, 1))

        # Take the smaller of the two estimates
        size = min(estimated_size, size_by_height)

        return max(min_size, min(max_size, size))

    def needs_stroke(
        self,
        image: np.ndarray,
        box: Box2D,
        threshold: int = 180,
    ) -> bool:
        """
        Determine if text needs stroke/outline for readability.
        
        Args:
            image: Source image
            box: Bounding box
            threshold: Background brightness threshold
            
        Returns:
            True if stroke is recommended
        """
        try:
            roi = image[box.y1:box.y2, box.x1:box.x2]
            if roi.size == 0:
                return False

            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            mean_brightness = gray.mean()

            # If background is dark, we need stroke for dark text
            return mean_brightness < threshold

        except Exception:
            return False


class TextRenderer:
    """
    Renders translated text onto manga images.
    
    Features:
    - Chinese text wrapping with typography rules
    - Dynamic font sizing
    - Centered text placement
    - Optional stroke/outline
    """

    def __init__(
        self,
        font_path: Optional[str] = None,
        default_font_size: int = 20,
        line_spacing: float = 1.2,
    ):
        """
        Initialize text renderer.
        
        Args:
            font_path: Path to CJK font file
            default_font_size: Default font size
            line_spacing: Line height multiplier
        """
        self.font_path = font_path or self._find_system_font()
        self.default_font_size = default_font_size
        self.line_spacing = line_spacing
        self.style_estimator = StyleEstimator()

    def _find_system_font(self) -> str:
        """Find a suitable CJK font on the system."""
        # Common CJK font paths
        font_candidates = [
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            # Linux
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            # Windows
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
        ]

        for path in font_candidates:
            if Path(path).exists():
                return path

        # Fallback to default
        return None

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get font with specified size."""
        try:
            if self.font_path:
                return ImageFont.truetype(self.font_path, size)
        except Exception:
            pass
        return ImageFont.load_default()

    def wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        """
        Wrap text to fit within max_width, respecting Chinese typography rules.
        
        Args:
            text: Text to wrap
            font: Font for measuring
            max_width: Maximum line width in pixels
            
        Returns:
            List of wrapped lines
        """
        if not text:
            return []

        lines = []
        current_line = ""

        for char in text:
            test_line = current_line + char
            
            # Get text width
            try:
                bbox = font.getbbox(test_line)
                width = bbox[2] - bbox[0]
            except Exception:
                width = len(test_line) * 20  # Fallback estimate

            if width <= max_width:
                current_line = test_line
            else:
                # Need to wrap
                if current_line:
                    # Check if char should not start a line
                    if char in FORBIDDEN_LINE_START and len(current_line) > 1:
                        # Move last char of current line to next line
                        lines.append(current_line[:-1])
                        current_line = current_line[-1] + char
                    else:
                        lines.append(current_line)
                        current_line = char
                else:
                    current_line = char

        # Add remaining text
        if current_line:
            lines.append(current_line)

        return lines

    def fit_text_to_box(
        self,
        text: str,
        box: Box2D,
        min_size: int = 16,  # 提高最小字体，减少视觉差异
        max_size: int = 32,  # 降低最大字体，使大小更统一
        padding: int = 4,
    ) -> Tuple[int, list[str]]:
        """
        Find optimal font size and wrap text to fit box.
        
        Uses binary search to find the largest font size that fits.
        
        Args:
            text: Text to fit
            box: Target bounding box
            min_size: Minimum font size
            max_size: Maximum font size
            padding: Padding inside box
            
        Returns:
            Tuple of (font_size, wrapped_lines)
        """
        available_width = box.width - 2 * padding
        available_height = box.height - 2 * padding

        best_size = min_size
        best_lines = [text]

        # Binary search for optimal size
        low, high = min_size, max_size

        while low <= high:
            mid = (low + high) // 2
            font = self._get_font(mid)
            lines = self.wrap_text(text, font, available_width)

            # Calculate total height
            line_height = int(mid * self.line_spacing)
            total_height = len(lines) * line_height

            if total_height <= available_height:
                # This size fits, try larger
                best_size = mid
                best_lines = lines
                low = mid + 1
            else:
                # Too large, try smaller
                high = mid - 1

        return best_size, best_lines

    async def render(
        self,
        image_path: str,
        regions: list[RegionData],
        output_path: str,
        original_image_path: Optional[str] = None,
    ) -> str:
        """
        Render translated text onto image.
        
        Args:
            image_path: Path to inpainted background image
            regions: Regions with target_text
            output_path: Path to save result
            original_image_path: Original image for style estimation
            
        Returns:
            Path to rendered image
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._render_sync,
            image_path,
            regions,
            output_path,
            original_image_path,
        )

    def _render_sync(
        self,
        image_path: str,
        regions: list[RegionData],
        output_path: str,
        original_image_path: Optional[str] = None,
    ) -> str:
        """Synchronous rendering implementation."""
        # Load images
        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        # Load original for style estimation
        if original_image_path:
            original_cv = cv2.imread(original_image_path)
        else:
            original_cv = cv2.imread(image_path)

        for region in regions:
            if not region.target_text or not region.box_2d:
                continue

            box = region.box_2d
            text = region.target_text

            # Skip SFX markers
            if text.startswith("[SFX:"):
                continue

            # Estimate style from original
            text_color = self.style_estimator.estimate_text_color(
                original_cv, box
            )
            needs_stroke = self.style_estimator.needs_stroke(original_cv, box)

            # Fit text to box
            font_size, lines = self.fit_text_to_box(text, box)
            font = self._get_font(font_size)

            # Calculate positioning (center text in box)
            line_height = int(font_size * self.line_spacing)
            total_height = len(lines) * line_height
            
            y_start = box.y1 + (box.height - total_height) // 2

            for i, line in enumerate(lines):
                # Get line width for centering
                try:
                    bbox = font.getbbox(line)
                    line_width = bbox[2] - bbox[0]
                except Exception:
                    line_width = len(line) * font_size

                x = box.x1 + (box.width - line_width) // 2
                y = y_start + i * line_height

                # Draw stroke if needed
                if needs_stroke:
                    stroke_color = "#FFFFFF" if text_color != "#FFFFFF" else "#000000"
                    stroke_width = max(1, font_size // 12)  # Dynamic stroke width
                    draw.text(
                        (x, y),
                        line,
                        font=font,
                        fill=text_color,
                        stroke_width=stroke_width,
                        stroke_fill=stroke_color,
                    )
                else:
                    # Draw text without stroke
                    draw.text((x, y), line, font=font, fill=text_color)

        # Save result
        image.save(output_path)
        return output_path


# Convenience function
async def render_translated_image(
    inpainted_path: str,
    regions: list[RegionData],
    output_path: str,
    original_path: Optional[str] = None,
    font_path: Optional[str] = None,
) -> str:
    """
    Render translated text onto inpainted image.
    
    Args:
        inpainted_path: Path to inpainted background
        regions: Regions with target_text
        output_path: Output path
        original_path: Original image for style estimation
        font_path: Custom font path
        
    Returns:
        Path to final image
    """
    renderer = TextRenderer(font_path=font_path)
    return await renderer.render(
        inpainted_path,
        regions,
        output_path,
        original_path,
    )

"""
Core Data Models for Manhua Translation System.

Defines the standard data structures used across all modules:
- RegionData: Single text region with coordinates and text content
- TaskContext: Full task context passed through the pipeline
- PipelineResult: Final result of pipeline execution
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FontStyleParams(BaseModel):
    """Font styling parameters for text rendering."""
    font_family: str = Field(default="Arial", description="Font family name")
    font_size: int = Field(default=16, ge=8, le=72, description="Font size in pixels")
    color: str = Field(default="#000000", description="Text color in hex format")
    stroke_color: Optional[str] = Field(default=None, description="Stroke color for outline")
    stroke_width: int = Field(default=0, ge=0, description="Stroke width in pixels")
    bold: bool = Field(default=False, description="Bold text")
    italic: bool = Field(default=False, description="Italic text")


class Box2D(BaseModel):
    """2D bounding box coordinates."""
    x1: int = Field(..., description="Left coordinate")
    y1: int = Field(..., description="Top coordinate")
    x2: int = Field(..., description="Right coordinate")
    y2: int = Field(..., description="Bottom coordinate")

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)


class RegionData(BaseModel):
    """
    Single text region data structure.
    
    This is the core data unit that flows through the pipeline.
    Each module updates relevant fields.
    """
    region_id: UUID = Field(default_factory=uuid4, description="Unique region identifier")
    box_2d: Optional[Box2D] = Field(default=None, description="Bounding box coordinates")
    mask_path: Optional[str] = Field(default=None, description="Path to region mask image")
    source_text: Optional[str] = Field(default=None, description="Original text (OCR result)")
    normalized_text: Optional[str] = Field(default=None, description="Normalized OCR text")
    target_text: Optional[str] = Field(default=None, description="Translated text")
    glossary_cov: Optional[float] = Field(default=None, description="Glossary coverage ratio")
    is_sfx: bool = Field(default=False, description="Whether region is SFX")
    is_watermark: bool = Field(default=False, description="Whether region is watermark")
    inpaint_mode: str = Field(default="replace", description="Inpaint mode: erase or replace")
    font_style_params: FontStyleParams = Field(
        default_factory=FontStyleParams,
        description="Font styling for rendering"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection/OCR confidence")

    class Config:
        json_schema_extra = {
            "example": {
                "region_id": "550e8400-e29b-41d4-a716-446655440000",
                "box_2d": {"x1": 100, "y1": 50, "x2": 300, "y2": 150},
                "mask_path": "/tmp/masks/region_001.png",
                "source_text": "Hello World",
                "target_text": "你好世界",
                "font_style_params": {
                    "font_family": "Arial",
                    "font_size": 16,
                    "color": "#000000"
                },
                "confidence": 0.95
            }
        }


class TaskContext(BaseModel):
    """
    Task context that flows through the entire pipeline.
    
    Contains all information needed for processing a single image.
    """
    task_id: UUID = Field(default_factory=uuid4, description="Unique task identifier")
    image_path: str = Field(..., description="Path to source image")
    output_path: Optional[str] = Field(default=None, description="Path to output image")
    inpainted_path: Optional[str] = Field(default=None, description="Path to inpainted intermediate image")
    regions: list[RegionData] = Field(default_factory=list, description="Detected text regions")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.now, description="Task creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    
    # Processing metadata
    source_language: str = Field(default="en", description="Source language code")
    target_language: str = Field(default="zh", description="Target language code")

    def update_status(self, status: TaskStatus, error: Optional[str] = None) -> "TaskContext":
        """Update task status and timestamp."""
        self.status = status
        self.updated_at = datetime.now()
        if error:
            self.error_message = error
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "image_path": "/path/to/manga.jpg",
                "output_path": "/path/to/output.jpg",
                "regions": [],
                "status": "pending",
                "source_language": "en",
                "target_language": "zh"
            }
        }


class PipelineResult(BaseModel):
    """Result of pipeline execution."""
    success: bool = Field(..., description="Whether pipeline completed successfully")
    task: TaskContext = Field(..., description="Final task context")
    processing_time_ms: float = Field(default=0.0, description="Total processing time in ms")
    stages_completed: list[str] = Field(default_factory=list, description="List of completed stages")
    metrics: Optional[dict] = Field(default=None, description="Performance metrics per stage")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "task": {},
                "processing_time_ms": 1234.56,
                "stages_completed": ["ocr", "translator", "inpainter", "renderer"]
            }
        }


# Request/Response models for API
class TranslateImageRequest(BaseModel):
    """Request model for single image translation."""
    image_path: str = Field(..., description="Path to source image")
    source_language: str = Field(default="en", description="Source language")
    target_language: str = Field(default="zh", description="Target language")


class TranslateImageResponse(BaseModel):
    """Response model for image translation."""
    task_id: UUID = Field(..., description="Task ID for tracking")
    status: TaskStatus = Field(..., description="Current status")
    output_path: Optional[str] = Field(default=None, description="Output image path")
    regions_count: int = Field(default=0, description="Number of detected regions")


class BatchTranslateRequest(BaseModel):
    """Request model for batch translation."""
    directory: str = Field(..., description="Directory containing images")
    source_language: str = Field(default="en", description="Source language")
    target_language: str = Field(default="zh", description="Target language")
    recursive: bool = Field(default=False, description="Process subdirectories")


class TaskStatusResponse(BaseModel):
    """Response model for task status query."""
    task_id: UUID
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress 0-1")
    output_path: Optional[str] = None
    error_message: Optional[str] = None

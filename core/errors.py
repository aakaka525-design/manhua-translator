"""Core business exceptions for pipeline stages."""


class PipelineStageError(Exception):
    """Base exception with machine-readable code for stage failures."""

    def __init__(self, message: str, *, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class OCRNoTextError(PipelineStageError):
    """Raised when OCR detects no text regions."""

    def __init__(self, message: str = "OCR found no text regions"):
        super().__init__(message, error_code="ocr_no_text")

"""Base OCR engine interface."""

from abc import ABC, abstractmethod

from ...models import RegionData


class OCREngine(ABC):
    """Abstract OCR engine interface."""

    @abstractmethod
    async def recognize(
        self,
        image_path: str,
        regions: list[RegionData],
    ) -> list[RegionData]:
        """Recognize text in detected regions."""
        raise NotImplementedError

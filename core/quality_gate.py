import asyncio
import os
from typing import Any


class QualityGate:
    def __init__(self, retry_per_region: int = 1, retry_budget_per_image: int = 2, fallback_model: str | None = None):
        self.retry_per_region = retry_per_region
        self.retry_budget_per_image = retry_budget_per_image
        self.fallback_model = fallback_model

    def apply(self, ctx: Any, translator: Any):
        budget = self.retry_budget_per_image
        for region in ctx.regions:
            if budget <= 0:
                break
            if self.retry_per_region <= 0:
                continue
            if getattr(region, "is_sfx", False):
                continue
            low_quality = (not region.target_text) or (region.confidence is not None and region.confidence < 0.55)
            if low_quality:
                result = translator.translate_region(region)
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                region.target_text = result
                budget -= 1
                if self.fallback_model and os.getenv("GEMINI_API_KEY"):
                    fallback = translator.create_translator(self.fallback_model)
                    if asyncio.iscoroutine(fallback):
                        fallback = asyncio.run(fallback)
                    fallback_result = fallback.translate_region(region)
                    if asyncio.iscoroutine(fallback_result):
                        fallback_result = asyncio.run(fallback_result)
                    region.target_text = fallback_result
        return ctx


def build_retry_prompt(template: str, **kwargs) -> str:
    return template.format(**kwargs)

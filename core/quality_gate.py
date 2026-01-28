import asyncio
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
            if not region.target_text:
                result = translator.translate_region(region)
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                region.target_text = result
                budget -= 1
        return ctx

"""
Performance Metrics - Pipeline performance tracking.

Records timing information for each stage and sub-operation.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""
    name: str
    duration_ms: float = 0.0
    items_processed: int = 0
    sub_metrics: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "items_processed": self.items_processed,
            "sub_metrics": self.sub_metrics,
        }


@dataclass
class PipelineMetrics:
    """Complete metrics for a pipeline run."""
    total_duration_ms: float = 0.0
    stages: list[StageMetrics] = field(default_factory=list)
    
    def add_stage(self, metrics: StageMetrics):
        self.stages.append(metrics)
    
    def get_stage(self, name: str) -> Optional[StageMetrics]:
        for s in self.stages:
            if s.name == name:
                return s
        return None
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [f"=== Pipeline Metrics (Total: {self.total_duration_ms:.0f}ms) ==="]
        for s in self.stages:
            pct = (s.duration_ms / self.total_duration_ms * 100) if self.total_duration_ms > 0 else 0
            lines.append(f"  {s.name}: {s.duration_ms:.0f}ms ({pct:.1f}%)")
            if s.sub_metrics:
                for k, v in s.sub_metrics.items():
                    lines.append(f"    - {k}: {v}")
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        return {
            "total_duration_ms": round(self.total_duration_ms, 2),
            "stages": [s.to_dict() for s in self.stages],
        }


class Timer:
    """Context manager for timing code blocks."""
    
    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: float = 0
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000


# Global metrics storage for current pipeline run
_current_metrics: Optional[PipelineMetrics] = None


def start_metrics() -> PipelineMetrics:
    """Start a new metrics collection."""
    global _current_metrics
    _current_metrics = PipelineMetrics()
    return _current_metrics


def get_current_metrics() -> Optional[PipelineMetrics]:
    """Get current metrics collection."""
    return _current_metrics


def record_stage(name: str, duration_ms: float, items: int = 0, **sub_metrics):
    """Record metrics for a stage."""
    if _current_metrics:
        _current_metrics.add_stage(StageMetrics(
            name=name,
            duration_ms=duration_ms,
            items_processed=items,
            sub_metrics=sub_metrics,
        ))

"""Compatibility exports; implementation lives in features/monitoring/performance.py."""

from .features.monitoring.performance import Performance, split_response

__all__ = ["Performance", "split_response"]

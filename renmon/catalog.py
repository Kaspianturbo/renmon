"""Compatibility exports; implementation lives in features/ecu/catalog.py."""

from .features.ecu.catalog import Catalog, IdentificationError

__all__ = ["Catalog", "IdentificationError"]

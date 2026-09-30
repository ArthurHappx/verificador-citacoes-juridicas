"""Índice, recuperação e decisão de citações."""

from .decision import decide
from .repository import CanonicalRepository

__all__ = ["CanonicalRepository", "decide"]

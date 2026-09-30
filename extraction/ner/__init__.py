"""Extensões opcionais para candidatos produzidos por NER."""

from .protocol import Entity, EntityRecognizer
from .huggingface import HuggingFaceEntityRecognizer

__all__ = ["Entity", "EntityRecognizer", "HuggingFaceEntityRecognizer"]

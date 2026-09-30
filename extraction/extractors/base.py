"""Utilitários de reconciliação compartilhados pelos extratores."""

from __future__ import annotations

import re
from dataclasses import dataclass


OCR_DIGITS = str.maketrans({"O": "0", "I": "1", "L": "1"})


@dataclass(frozen=True)
class Candidate:
    value: str
    start: int
    end: int
    score: int = 0


def normalize_ocr_digits(value: str) -> str:
    """Corrige OCR somente em uma string previamente tipada como numérica."""

    return value.upper().translate(OCR_DIGITS)


def compact_number(value: str) -> str:
    value = normalize_ocr_digits(value)
    value = re.sub(r"\s*([.\-/])\s*", r"\1", value)
    return re.sub(r"\s+", "", value)


def compact_space(value: str) -> str:
    # Não usa regex sobre a superfície original. Os reconhecedores regex
    # operam exclusivamente sobre NormalizedText.text.
    return " ".join(value.split())


def overlaps(span: tuple[int, int], protected: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in protected)


def distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    if left[1] < right[0]:
        return right[0] - left[1]
    if right[1] < left[0]:
        return left[0] - right[1]
    return 0

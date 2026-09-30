"""Interface agnóstica a modelo para um reconhecedor auxiliar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Entity:
    label: str
    text: str
    start: int
    end: int
    score: float | None = None


class EntityRecognizer(Protocol):
    def recognize(self, text: str) -> Sequence[Entity]: ...


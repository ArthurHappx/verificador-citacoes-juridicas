"""Normalização compartilhada pelo índice e pelas consultas."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fold(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).strip().upper()


def digits(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def class_key(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", fold(value))).strip()


def name_tokens(value: Any) -> tuple[str, ...]:
    particles = {"DE", "DA", "DO", "DAS", "DOS", "E", "MIN", "MINISTRO", "MINISTRA"}
    return tuple(token for token in class_key(value).split() if token not in particles)


def name_matches(candidate: Any, expected: Any) -> bool:
    """Compara nome abreviado por subsequência ordenada de tokens."""

    available = iter(name_tokens(candidate))
    return bool(name_tokens(expected)) and all(token in available for token in name_tokens(expected))


def normalize_uf(value: Any) -> str | None:
    key = fold(value)
    return key if re.fullmatch(r"[A-Z]{2}", key) else None

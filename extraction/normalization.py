"""Normalização obrigatória anterior a qualquer reconhecimento por regex."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedText:
    """Texto normalizado e mapa de cada caractere para o texto original."""

    original: str
    text: str
    source_indices: tuple[int, ...]

    def original_slice(self, start: int, end: int) -> str:
        """Recupera a superfície original correspondente a um span normalizado."""

        if start >= end or not self.source_indices:
            return ""
        start = max(0, min(start, len(self.source_indices) - 1))
        end = max(start + 1, min(end, len(self.source_indices)))
        return self.original[
            self.source_indices[start] : self.source_indices[end - 1] + 1
        ]


def normalize_for_matching(value: str) -> NormalizedText:
    """Retorna texto NFD, sem marcas diacríticas e em caixa alta.

    O processamento é feito caractere a caractere para preservar a relação
    com a superfície original. Espaços Unicode e quebras de linha viram espaço
    ASCII, mas não são colapsados: os padrões decidem quanto espaço tolerar.
    """

    if not isinstance(value, str):
        raise TypeError("O trecho deve ser uma string")

    characters: list[str] = []
    source_indices: list[int] = []
    for index, character in enumerate(value):
        decomposed = unicodedata.normalize("NFD", character)
        for unit in decomposed:
            if unicodedata.category(unit) == "Mn":
                continue
            rendered = " " if unit.isspace() else unit.upper()
            for output_character in rendered:
                characters.append(output_character)
                source_indices.append(index)

    return NormalizedText(value, "".join(characters), tuple(source_indices))


def normalize_value(value: str) -> str:
    """Atalho para valores canônicos que não precisam do mapa de índices."""

    return normalize_for_matching(value).text


def stable_unique(values):
    """Remove duplicatas preservando ordem, inclusive para valores não-string."""

    return list(dict.fromkeys(values))


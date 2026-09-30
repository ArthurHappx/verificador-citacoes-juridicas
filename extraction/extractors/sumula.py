"""Extração de súmulas, inclusive plurais e vinculantes."""

from __future__ import annotations

import re

from ..normalization import normalize_for_matching, stable_unique
from ..patterns import sumula as patterns
from ..schemas import empty_data


def _tribunals(text: str) -> list[str]:
    found = []
    for tribunal, regexes in patterns.TRIBUNALS.items():
        if any(regex.search(text) for regex in regexes):
            found.append(tribunal)
    return found


def extract_sumula(trecho: str) -> dict:
    normalized = normalize_for_matching(trecho)
    text = normalized.text
    data = empty_data("sumula")

    vinc = bool(patterns.VINCULANTE.search(text))
    data["vinculante"] = vinc

    tribunals = _tribunals(text)
    if vinc:
        tribunals.append("STF")
    tribunals = stable_unique(tribunals)
    data["tribunal"] = tribunals[0] if len(tribunals) == 1 else None

    match = patterns.NUMBER_IN_ENUNCIADO.search(text) or patterns.NUMBER_AFTER.search(text)
    if match:
        numbers = [int(value) for value in re.findall(r"\d{1,4}", match.group("numbers"))]
        # Anos de publicação nunca são números de súmula.
        data["numero"] = stable_unique(value for value in numbers if value < 1800)
    else:
        # O tipo SUM já foi determinado pelo NER. Assim, superfícies compactas
        # como "150/STJ" ou "583" podem usar um único decimal inequívoco.
        candidates = [
            int(value) for value in re.findall(r"(?<!\d)\d{1,4}(?!\d)", text)
            if int(value) < 1800
        ]
        unique = stable_unique(candidates)
        if len(unique) == 1:
            data["numero"] = unique
    return data

"""Padrões tolerantes a OCR para súmulas, sem impor posição do tribunal."""

from __future__ import annotations

import re

from .common import FLAGS


# S/5, L/1 e M/RN são as confusões de OCR documentadas. Espaço interno cobre
# superfícies como "SÚ MULAS".
SUMULA_WORD = r"(?:S|5)U\s*(?:M|RN)U(?:L|1)AS?"
SUMULA_MARKER = re.compile(rf"\b(?:{SUMULA_WORD}|ENUNCIADOS?\s+SUMULARES?)\b", FLAGS)
VINCULANTE = re.compile(r"\bVINCULANTE\b", FLAGS)

NUMBER_AFTER = re.compile(
    rf"(?:{SUMULA_WORD}|ENUNCIADOS?\s+SUMULARES?)"
    r"(?:(?!\d).){0,45}?"
    r"(?P<numbers>\d{1,4}(?:\s*(?:,|\bE\b)\s*\d{1,4})*)",
    FLAGS,
)
NUMBER_IN_ENUNCIADO = re.compile(
    rf"\bENUNCIADO\s*(?:N(?:[O0º°.]|UMERO)?\s*)?"
    rf"(?P<numbers>\d{{1,4}}(?:\s*(?:,|\bE\b)\s*\d{{1,4}})*)"
    rf"(?:(?!\d).){{0,35}}?{SUMULA_WORD}\b",
    FLAGS,
)

TRIBUNALS: dict[str, tuple[re.Pattern[str], ...]] = {
    "STF": (
        re.compile(r"\bSTF\b", FLAGS),
        re.compile(r"\bSUPREMO\s+TRIBUNAL\s+FEDERAL\b", FLAGS),
    ),
    "STJ": (
        re.compile(r"\bSTJ\b", FLAGS),
        re.compile(r"\bSUPERIOR\s+TRIBUNAL\s+DE\s+JUSTICA\b", FLAGS),
    ),
    "TST": (
        re.compile(r"\bTST\b", FLAGS),
        re.compile(r"\bTRIBUNAL\s+SUPERIOR\s+DO\s+TRABALHO\b", FLAGS),
    ),
}


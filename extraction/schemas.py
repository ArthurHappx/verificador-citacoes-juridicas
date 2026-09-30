"""Contrato público e construção dos objetos ``dados``.

Campos naturalmente plurais são sempre listas. Isso evita que consumidores
tenham de tratar ora um escalar, ora uma lista para a mesma informação.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TYPE_MAP: dict[str, tuple[str, str]] = {
    "LEG": ("lei", "dispositivo"),
    "ACOR": ("jurisprudencia", "acordao"),
    "SUM": ("jurisprudencia", "sumula"),
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "dispositivo": {
        "diploma": None,
        "artigo": [],
        "inciso": [],
        "paragrafo": [],
        "alinea": [],
    },
    "sumula": {"tribunal": None, "numero": [], "vinculante": False},
    "acordao": {
        "tribunal": None,
        "classe_processual": None,
        "classe_processual_normalizada": None,
        "classe_normalizada_candidatos": [],
        "numero": None,
        "uf": None,
        "ano": None,
        "relator": None,
    },
}


def map_input_type(value: str) -> tuple[str, str]:
    """Converte o rótulo do NER em ``(tipo, natureza)``."""

    try:
        return TYPE_MAP[value.strip().upper()]
    except (AttributeError, KeyError):
        raise ValueError(f"Tipo de citação não suportado: {value!r}") from None


def empty_data(natureza: str) -> dict[str, Any]:
    try:
        return deepcopy(SCHEMAS[natureza])
    except KeyError:
        raise ValueError(f"Natureza não suportada: {natureza!r}") from None


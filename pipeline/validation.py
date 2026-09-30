"""Validação do contrato enriquecido antes do conversor oficial."""

from __future__ import annotations

from typing import Any


CLASSES = {"real", "inventada", "incompleta"}
TYPES = {"lei", "jurisprudencia"}
NATURES = {"dispositivo", "sumula", "acordao"}


def validate_document(document: dict[str, Any], text: str | None) -> None:
    if not document.get("documento_id"):
        raise ValueError("documento_id ausente")
    citations = document.get("citacoes")
    if not isinstance(citations, list):
        raise ValueError("citacoes deve ser uma lista")
    spans: list[tuple[int, int]] = []
    for position, citation in enumerate(citations, 1):
        prefix = f"citação {position}"
        start, end = citation.get("inicio"), citation.get("fim")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end:
            raise ValueError(f"{prefix}: span inválido")
        if text is not None:
            if end > len(text) or text[start:end] != citation.get("trecho"):
                raise ValueError(f"{prefix}: trecho não corresponde ao span")
        if citation.get("tipo") not in TYPES or citation.get("natureza") not in NATURES:
            raise ValueError(f"{prefix}: tipo ou natureza inválidos")
        classification = citation.get("classificacao")
        if classification not in CLASSES:
            raise ValueError(f"{prefix}: classificação inválida")
        resolution = citation.get("resolucao")
        if classification == "real":
            if not isinstance(resolution, dict) or not isinstance(resolution.get("id_canonico"), int):
                raise ValueError(f"{prefix}: real exige id_canonico inteiro")
        elif resolution is not None:
            raise ValueError(f"{prefix}: somente real admite resolução")
        confidence = citation.get("confianca")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise ValueError(f"{prefix}: confiança fora de [0,1]")
        spans.append((start, end))
    for index, left in enumerate(spans):
        for right in spans[index + 1:]:
            intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
            union = (left[1] - left[0]) + (right[1] - right[0]) - intersection
            if union and intersection / union >= 0.5:
                raise ValueError("citações duplicadas com IoU >= 0,5")


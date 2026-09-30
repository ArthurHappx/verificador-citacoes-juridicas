"""Reparos conservadores entre a extração determinística e a recuperação."""

from __future__ import annotations

import re
from typing import Any

from extraction.class_normalizer import resolve_procedural_class

from retrieval.normalization import digits, fold


OCR_NUMBER = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "L": "1", "S": "5", "s": "5", "G": "9", "g": "9"})
UF_PATTERN = re.compile(r"(?:[/\-()]|\s)(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b", re.IGNORECASE)


def _typed_number(text: str) -> str | None:
    """Recupera número somente no trecho já tipado como acórdão."""

    # CNJ, inclusive com pontos/hífens deslocados pelo OCR.
    cnj = re.search(
        r"(?<!\w)([0-9OIlLSGg](?:[0-9OIlLSGg.\-\s]*[0-9OIlLSGg]){13,})(?!\w)",
        text,
    )
    if cnj:
        normalized = cnj.group(1).translate(OCR_NUMBER)
        value = digits(normalized)
        if len(value) >= 14:
            return value

    # Tradicional agrupado por pontos ou espaços: 1.821.663 / 1 821 663.
    grouped = re.search(
        r"(?<![\w])([0-9OIlLSGg]{1,3}(?:\s*(?:[.]\s*|\s+)[0-9OIlLSGg]{3}){1,2})(?!\w)",
        text,
    )
    if grouped:
        return digits(grouped.group(1).translate(OCR_NUMBER))

    marker = re.search(r"\bN\s*[.º°O]*\s*([0-9OIlLSGg](?:[0-9OIlLSGg.\-\s]*[0-9OIlLSGg])?)", text, re.IGNORECASE)
    if marker:
        raw = marker.group(1)
        # Não absorver a primeira letra da UF em superfícies como "93967 - SC".
        raw = re.sub(r"\s*[-/(]\s*[A-Za-z]$", "", raw)
        return digits(raw.translate(OCR_NUMBER))

    # Classes compactas frequentemente omitem o marcador n.º.
    compact = re.search(
        r"\b(?:RCL|RECL(?:AMA[CÇ][AÃ]O)?|RESP|ARESP|AGRESP|R[.]?ESP[.]?|AR|RE|TEMA)\s*"
        r"(?:N\s*[.º°O]*\s*)?([0-9OIlLSGg][0-9OIlLSGg.\-\s]*[0-9OIlLSGg])",
        text,
        re.IGNORECASE,
    )
    if compact:
        return digits(compact.group(1).translate(OCR_NUMBER))
    return None


def _class_surface(text: str) -> str | None:
    match = re.search(
        r"^\s*((?:EDCL|ED|AGRG|AGINT|AGR|AG)\s+(?:NO|NA)\s+)*"
        r"(?:R[.]?ESP[.]?|RESP|ARESP|AGRESP|RCL|RECL(?:AMA[CÇ][AÃ]O)?|AR|RE|RESPE|RSE|APL|RR|AIRR)",
        text,
        re.IGNORECASE,
    )
    return match.group(0).strip() if match else None


def enrich_extraction(trecho: str, natureza: str, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Preenche lacunas OCR sem substituir campos já extraídos com qualidade."""

    enriched = dict(data)
    warnings: list[str] = []
    if natureza == "acordao":
        recovered = _typed_number(trecho)
        current = digits(enriched.get("numero"))
        if recovered and len(recovered) >= 2 and (not current or len(recovered) > len(current)):
            enriched["numero"] = recovered
            warnings.append("numero_recuperado_por_normalizacao_contextual")
        elif current and len(current) < 2:
            enriched["numero"] = None
            warnings.append("numero_curto_descartado")

        if not enriched.get("classe_processual"):
            surface = _class_surface(trecho)
            if surface:
                enriched["classe_processual"] = surface
                warnings.append("classe_recuperada_por_fallback")
        if enriched.get("classe_processual") and not enriched.get("classe_processual_normalizada"):
            resolution = resolve_procedural_class(
                enriched["classe_processual"], tribunal=enriched.get("tribunal")
            )
            if resolution.normalized:
                enriched["classe_processual_normalizada"] = resolution.normalized

        if not enriched.get("uf"):
            matches = UF_PATTERN.findall(trecho)
            if matches:
                enriched["uf"] = matches[-1].upper()

        number = digits(enriched.get("numero"))
        if len(number) == 20 and not enriched.get("tribunal"):
            segment = number[-9]
            enriched["tribunal"] = {"5": "TST", "6": "TSE", "7": "STM"}.get(segment)

        if re.search(r"\bTEMA\b", fold(trecho)) and not enriched.get("classe_processual"):
            enriched["classe_processual"] = "TEMA DE REPERCUSSAO GERAL"
            enriched["classe_processual_normalizada"] = "TEMA DE REPERCUSSAO GERAL"

    elif natureza == "sumula":
        if not enriched.get("numero"):
            match = re.search(r"(?:S[UÚ]M(?:ULA)?|5[UÚ]M(?:U1A|ULA)?)\s*[.]?\s*(?:N\s*[.º°O]*)?\s*(\d+)", trecho, re.IGNORECASE)
            if match:
                enriched["numero"] = [int(match.group(1))]
        if not enriched.get("tribunal"):
            court = re.search(r"\b(?:DO|DA)\s+(STF|STJ|TST|TSE|STM)\b", trecho, re.IGNORECASE)
            if court:
                enriched["tribunal"] = court.group(1).upper()

    elif natureza == "dispositivo" and not enriched.get("diploma"):
        law = re.search(
            r"\bLEI\s+(COMPLEMENTAR\s+)?(?:N\s*[.º°O]*\s*)?([\d.]+)\s*/\s*(\d{2,4})",
            trecho,
            re.IGNORECASE,
        )
        if law:
            enriched["diploma"] = f"{'LC' if law.group(1) else 'LEI'}:{digits(law.group(2))}/{law.group(3)}"
            warnings.append("diploma_fora_do_catalogo_conhecido")
    return enriched, warnings

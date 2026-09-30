"""Extração de artigos e subdispositivos com proteção contra anos."""

from __future__ import annotations

import re

from ..normalization import normalize_for_matching, stable_unique
from ..patterns import dispositivo as patterns
from ..schemas import empty_data
from .base import compact_number, normalize_ocr_digits, overlaps


def _four_digit_year(value: str) -> str:
    value = normalize_ocr_digits(value)
    if len(value) == 2:
        numeric = int(value)
        return str(2000 + numeric if numeric <= 30 else 1900 + numeric)
    return value


def _diploma_candidates(
    text: str,
) -> tuple[list[str], list[tuple[int, int]], list[tuple[int, int]]]:
    candidates: list[str] = []
    protected: list[tuple[int, int]] = []
    anchors: list[tuple[int, int]] = []

    for diploma, regexes in patterns.DIPLOMA_NAMES.items():
        for regex in regexes:
            for match in regex.finditer(text):
                candidates.append(diploma)
                protected.append(match.span())
                anchors.append(match.span())

    for match in patterns.LAW_IDENTITY.finditer(text):
        number = re.sub(r"\D", "", normalize_ocr_digits(match.group("number")))
        year = _four_digit_year(re.sub(r"\D", "", normalize_ocr_digits(match.group("year"))))
        diploma = patterns.LAW_NUMBER_YEAR_TO_DIPLOMA.get((number, year))
        if diploma:
            candidates.append(diploma)
            protected.append(match.span())
            anchors.append(match.span())

    for match in patterns.NAMED_LAW_NUMBER.finditer(text):
        number = re.sub(r"\D", "", normalize_ocr_digits(match.group("number")))
        diploma = patterns.LAW_NUMBER_TO_DIPLOMA.get(number)
        if diploma:
            candidates.append(diploma)
            protected.append(match.span())
            anchors.append(match.span())

    return stable_unique(candidates), protected, stable_unique(anchors)


def _clean_article(value: str) -> str:
    value = re.sub(r"\s*(?:º|°|O)\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*", "-", value)
    value = re.sub(r"\s*\.\s*", ".", value)
    return value.strip().upper()


def _article_region(text: str, marker_end: int) -> tuple[str, int]:
    tail = text[marker_end : marker_end + 180]
    boundary = patterns.DIPLOMA_BOUNDARY.search(tail)
    if boundary:
        tail = tail[: boundary.start()]
    return tail, marker_end


def _extract_articles(text: str, protected: list[tuple[int, int]]) -> tuple[list[str], list[tuple[int, int]]]:
    values: list[str] = []
    regions: list[tuple[int, int]] = []
    for marker in patterns.ARTICLE_MARKER.finditer(text):
        region, offset = _article_region(text, marker.end())
        first = patterns.FIRST_ARTICLE.search(region)
        if not first:
            continue
        first_span = (offset + first.start("value"), offset + first.end("value"))
        if not overlaps(first_span, protected):
            values.append(_clean_article(first.group("value")))

        # A região inteira continua disponível para subdispositivos. Artigos
        # adicionais exigem um separador/conector explícito.
        regions.append((marker.start(), offset + len(region)))
        paragraph_spans = [span for _, span in _paragraph_candidates(region)]
        for match in patterns.NEXT_ARTICLE.finditer(region, first.end()):
            span = (offset + match.start("value"), offset + match.end("value"))
            local_span = match.span("value")
            if not overlaps(local_span, paragraph_spans) and not overlaps(span, protected):
                values.append(_clean_article(match.group("value")))
    return stable_unique(values), regions


def _paragraph_candidates(region: str) -> list[tuple[str, tuple[int, int]]]:
    """Retorna parágrafos e seus spans sem engolir artigos subsequentes.

    Com ``§`` singular, somente o primeiro decimal pertence ao parágrafo. Com
    ``§§``/``PARÁGRAFOS``, a lista pode atravessar incisos romanos, mas termina
    antes de um decimal maior que 20. Nos diplomas deste escopo, esse limite é
    conservador e separa casos como ``§§ 1º e 2º, 513 e 522``.
    """

    candidates: list[tuple[str, tuple[int, int]]] = []
    for marker in patterns.PARAGRAPH_MARKER.finditer(region):
        plural = marker.group(0).startswith("§§") or marker.group(0).endswith("S")
        tail = region[marker.end() :]
        for number in re.finditer(r"\d{1,3}\s*(?:º|°|O)?", tail):
            between = tail[: number.start()]
            if patterns.ARTICLE_MARKER.search(between):
                break
            value = int(re.match(r"\d+", number.group(0)).group(0))
            if value > 20:
                break
            span = (marker.end() + number.start(), marker.end() + number.end())
            candidates.append((str(value), span))
            if not plural:
                break
    return candidates


def _extract_bare_articles(
    text: str,
    protected: list[tuple[int, int]],
    diploma_anchors: list[tuple[int, int]],
) -> tuple[list[str], list[tuple[int, int]]]:
    """Reconhece artigos sem ``art.`` somente junto a diploma conhecido.

    O NER já informou que o trecho é legal, mas a proximidade do diploma ainda
    é exigida. Números de parágrafo, datas e identidades legislativas ficam de
    fora. Esta é a exceção controlada à regra do marcador explícito.
    """

    values: list[str] = []
    regions: list[tuple[int, int]] = []
    for anchor_start, _ in diploma_anchors:
        region_start = max(0, anchor_start - 120)
        prefix = text[region_start:anchor_start]
        local_values: list[str] = []
        first_start: int | None = None
        for match in re.finditer(patterns.ARTICLE_VALUE, prefix, patterns.FLAGS):
            span = (region_start + match.start(), region_start + match.end())
            if overlaps(span, protected):
                continue
            before = text[max(0, span[0] - 18) : span[0]]
            if re.search(r"(?:§|PARAGRAFO|INCISO|ALINEA|LEI|DECRETO)\s*$", before):
                continue
            if any(start <= span[0] < end for start, end in protected):
                continue
            # Número dentro de uma data ou imediatamente depois de barra não
            # pode ser artigo neste fallback.
            if re.search(r"[/.-]\s*$", before) or re.match(r"\s*[/.-]\s*\d", text[span[1] :]):
                continue
            local_values.append(_clean_article(match.group(0)))
            first_start = span[0] if first_start is None else first_start
        if local_values:
            values.extend(local_values)
            regions.append((first_start or region_start, anchor_start))
    return stable_unique(values), regions


def _roman_values(value: str) -> list[str]:
    return re.findall(r"\b[IVXLCDM]+\b", value.upper())


def _extract_subdevices(text: str, regions: list[tuple[int, int]]) -> tuple[list[str], list[str], list[str]]:
    incisos: list[str] = []
    paragrafos: list[str] = []
    alineas: list[str] = []

    for start, end in regions:
        region = text[start:end]
        for match in patterns.INCISO_EXPLICIT.finditer(region):
            incisos.extend(_roman_values(match.group("values")))
        for match in patterns.INCISO_CONTEXTUAL.finditer(region):
            incisos.append(match.group("value").upper())

        paragrafos.extend(value for value, _ in _paragraph_candidates(region))
        for match in patterns.PARAGRAPH_UNIQUE.finditer(region):
            token = re.sub(r"[.\s]", "", match.group(0).upper())
            paragrafos.append("CAPUT" if token == "CAPUT" else "UNICO")

        for match in patterns.ALINEA_EXPLICIT.finditer(region):
            alineas.extend(re.findall(r"\b[A-Z]\b", match.group("values").upper()))
        for match in patterns.ALINEA_PAREN.finditer(region):
            alineas.append(match.group("value").lower())

    return stable_unique(incisos), stable_unique(paragrafos), stable_unique(alineas)


def extract_dispositivo(trecho: str) -> dict:
    normalized = normalize_for_matching(trecho)
    data = empty_data("dispositivo")

    diplomas, protected, anchors = _diploma_candidates(normalized.text)
    data["diploma"] = diplomas[0] if len(diplomas) == 1 else None

    articles, regions = _extract_articles(normalized.text, protected)
    if not articles and len(diplomas) == 1:
        articles, regions = _extract_bare_articles(normalized.text, protected, anchors)
    data["artigo"] = articles
    incisos, paragrafos, alineas = _extract_subdevices(normalized.text, regions)
    data["inciso"] = incisos
    data["paragrafo"] = paragrafos
    data["alinea"] = alineas
    return data

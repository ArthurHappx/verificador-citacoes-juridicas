"""Extração e reconciliação dos campos de acórdãos."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..class_normalizer import resolve_procedural_class
from ..normalization import NormalizedText, normalize_for_matching, stable_unique
from ..patterns import acordao as patterns
from ..schemas import empty_data
from .base import Candidate, compact_number, compact_space, distance

if TYPE_CHECKING:
    from ..ner.protocol import EntityRecognizer


CLASS_TO_TRIBUNAL = {
    "RESP": "STJ", "ARESP": "STJ", "ERESP": "STJ", "RHC": "STJ", "RMS": "STJ",
    "ADI": "STF", "ADC": "STF", "ADPF": "STF",
    "RR": "TST", "AIRR": "TST", "ARR": "TST", "RRAG": "TST",
    "RESPE": "TSE", "RESPEL": "TSE", "RCED": "TSE", "AIME": "TSE", "AIJE": "TSE",
    "RSE": "STM", "APL": "STM",
}


def _explicit_tribunals(text: str) -> list[str]:
    found = []
    for tribunal, regexes in patterns.TRIBUNALS.items():
        if any(regex.search(text) for regex in regexes):
            found.append(tribunal)
    return found


def _tribunal_from_class(class_text: str | None) -> str | None:
    if not class_text:
        return None
    normalized = re.sub(r"[^A-Z]", "", class_text.upper())
    phrase_tribunals = {
        "RECURSOESPECIAL": "STJ",
        "AGRAVOEMRECURSOESPECIAL": "STJ",
        "RECURSODEREVISTA": "TST",
        "RECURSOESPECIALELEITORAL": "TSE",
        "RECURSOELEITORAL": "TSE",
        "ACAODIRETADEINCONSTITUCIONALIDADE": "STF",
    }
    phrase_matches = {
        tribunal for phrase, tribunal in phrase_tribunals.items() if phrase in normalized
    }
    if len(phrase_matches) == 1:
        return next(iter(phrase_matches))
    tokens = set(re.findall(r"[A-Z]+", class_text.upper()))
    found = {tribunal for key, tribunal in CLASS_TO_TRIBUNAL.items() if key in tokens}
    return next(iter(found)) if len(found) == 1 else None


def _tribunal_from_cnj(number: str | None) -> str | None:
    if not number or number.count(".") < 4:
        return None
    compact = compact_number(number)
    if re.search(r"\.5\.\d{2}\.", compact):
        return "TST"
    if re.search(r"\.6\.\d{2}\.", compact):
        return "TSE"
    if re.search(r"\.7\.\d{2}\.", compact):
        return "STM"
    return None


def _protected_date_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for regex in (
        patterns.FULL_DATE,
        patterns.MONTH_YEAR,
        patterns.MONTH_NAME_YEAR,
        patterns.ADMINISTRATIVE_NUMBER,
    ):
        spans.extend(match.span() for match in regex.finditer(text))
    return spans


def _number_candidates(text: str, class_span: tuple[int, int] | None) -> list[Candidate]:
    candidates: list[Candidate] = []
    occupied: list[tuple[int, int]] = []
    date_spans = _protected_date_spans(text)

    sources = (
        (patterns.CNJ_NUMBER, 100),
        (patterns.FLEXIBLE_ELECTORAL_NUMBER, 90),
        (patterns.CNJ_WITHOUT_CHECK_DIGITS, 85),
        (patterns.PARTIAL_HYPHEN_NUMBER, 80),
        (patterns.DOTTED_NUMBER, 60),
        (patterns.PLAIN_NUMBER, 30),
        (patterns.SHORT_PREFIXED_NUMBER, 55),
    )
    for regex, base_score in sources:
        for match in regex.finditer(text):
            span = match.span("number")
            if any(span[0] < end and start < span[1] for start, end in date_spans + occupied):
                continue
            raw = match.group("number")
            compact = compact_number(raw)
            digits = re.sub(r"\D", "", compact)
            if not digits or (len(digits) == 4 and 1800 <= int(digits) <= 2099):
                continue
            score = base_score
            prefix = text[max(0, span[0] - 12) : span[0]]
            prefixed = bool(patterns.NUMBER_PREFIX.search(prefix))
            if prefixed:
                score += 30
            if class_span:
                proximity = distance(span, class_span)
                score += max(0, 50 - proximity)
                if len(digits) <= 4 and proximity > 25 and not prefixed:
                    continue
            elif base_score < 80:
                # Sem classe, apenas CNJ e números hifenizados são seguros.
                continue
            candidates.append(Candidate(compact, span[0], span[1], score))
            occupied.append(span)
    return candidates


def _select_number(text: str, class_span: tuple[int, int] | None) -> tuple[str | None, tuple[int, int] | None]:
    candidates = _number_candidates(text, class_span)
    if not candidates:
        return None, None
    ranked = sorted(candidates, key=lambda item: (-item.score, item.start))
    best = ranked[0]
    if len(ranked) > 1 and ranked[1].score == best.score and ranked[1].value != best.value:
        return None, None
    return best.value, (best.start, best.end)


def _select_uf(
    text: str,
    number_span: tuple[int, int] | None,
    class_span: tuple[int, int] | None,
) -> str | None:
    candidates: list[Candidate] = []
    for match in patterns.UF_ABBREVIATION.finditer(text):
        span = match.span("uf")
        if class_span and span[0] < class_span[1] and class_span[0] < span[1]:
            continue
        proximity = distance(span, number_span) if number_span else 999
        # Siglas de duas letras só são seguras perto do identificador.
        if number_span and proximity <= 30:
            prefix = text[max(0, span[0] - 3) : span[0]]
            bonus = 20 if re.search(r"[/\-\[(]\s*$", prefix) else 0
            candidates.append(Candidate(match.group("uf"), *span, 50 - proximity + bonus))
    for uf, regex in patterns.UF_NAME_PATTERNS.items():
        for match in regex.finditer(text):
            proximity = distance(match.span(), number_span) if number_span else 999
            if number_span and proximity <= 45:
                candidates.append(Candidate(uf, match.start(), match.end(), 40 - proximity))
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda item: (-item.score, item.start))
    return ranked[0].value


def _extract_year(text: str, number_span: tuple[int, int] | None) -> int | None:
    explicit = patterns.JUDGMENT_YEAR.search(text)
    if explicit:
        return int(explicit.group("year") or explicit.group("acordao_year"))

    date_spans = _protected_date_spans(text)
    candidates = []
    for match in patterns.ANY_YEAR.finditer(text):
        span = match.span("year")
        if number_span and span[0] < number_span[1] and number_span[0] < span[1]:
            continue
        if any(span[0] < end and start < span[1] for start, end in date_spans):
            continue
        prefix = text[max(0, span[0] - 12) : span[0]]
        if patterns.PUBLICATION.search(prefix):
            continue
        candidates.append(int(match.group("year")))
    unique = stable_unique(candidates)
    return unique[0] if len(unique) == 1 else None


def _extract_relator(normalized: NormalizedText) -> str | None:
    marker = patterns.RELATOR_MARKER.search(normalized.text)
    if not marker:
        return None
    tail = normalized.text[marker.end() :]
    stop = patterns.RELATOR_STOP.search(tail)
    end = marker.end() + (stop.start() if stop else min(len(tail), 90))
    surface = normalized.original_slice(marker.end(), end)
    surface = compact_space(surface).strip(" ,;.-–—")
    # Um nome plausível tem letras e não deve engolir uma frase inteira.
    if not any(character.isalpha() for character in surface) or len(surface.split()) > 8:
        return None
    return surface or None


def extract_acordao(
    trecho: str, *, entity_recognizer: "EntityRecognizer | None" = None
) -> dict:
    normalized = normalize_for_matching(trecho)
    text = normalized.text
    data = empty_data("acordao")

    class_match = patterns.CLASS_CHAIN.search(text)
    class_span = class_match.span("class") if class_match else None
    if class_match:
        surface = compact_space(normalized.original_slice(*class_span)).strip(" ,;.-–—")
        if surface.upper().startswith("TST-"):
            surface = surface[4:].strip()
        data["classe_processual"] = surface

    number, number_span = _select_number(text, class_span)
    data["numero"] = number

    explicit = _explicit_tribunals(text)
    inferred_cnj = _tribunal_from_cnj(number)
    inferred_class = _tribunal_from_class(class_match.group("class") if class_match else None)
    if len(explicit) == 1:
        data["tribunal"] = explicit[0]
    elif not explicit and inferred_cnj:
        data["tribunal"] = inferred_cnj
    elif not explicit and inferred_class:
        data["tribunal"] = inferred_class

    if data["classe_processual"]:
        resolution = resolve_procedural_class(
            data["classe_processual"], tribunal=data["tribunal"]
        )
        data["classe_processual_normalizada"] = resolution.normalized
        data["classe_normalizada_candidatos"] = resolution.candidates

    data["uf"] = _select_uf(text, number_span, class_span)
    data["ano"] = _extract_year(text, number_span)
    data["relator"] = _extract_relator(normalized)
    if data["relator"] is None and entity_recognizer is not None:
        people = [
            entity for entity in entity_recognizer.recognize(trecho)
            if entity.label.upper() in {"PERSON", "PER", "PESSOA"}
        ]
        # Um único nome é um fallback seguro dentro de um trecho já tipado
        # como acórdão. Múltiplas pessoas permanecem ambíguas.
        if len(people) == 1:
            data["relator"] = compact_space(people[0].text)
    return data

"""Fachada de inferência do identificador de citações."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from .inference import predict_text


TST_CITATION = re.compile(
    r"(?:\bPROCESSO\s+N\s*[.º°O]*\s*)?"
    r"(?:\bTST\s*[-–—]\s*)?(?:[A-Z]{1,8}\s*[-–—]\s*)+"
    r"\d{1,7}\s*[-–—]\s*\d{2}\s*[.]\s*\d{4}\s*[.]\s*5\s*[.]\s*\d{2}\s*[.]\s*\d{4}",
    re.IGNORECASE,
)
RCL_CITATION = re.compile(
    r"(?:(?:PRIMEIR[OA]|SEGUND[OA]|TERCEIR[OA]|QUART[OA])\s+AG[.]?REG[.]?\s+NA\s+)?"
    r"\b(?:RECLAMA[CÇ][AÃ]O|RCL|RECL[.])\s*(?:N\s*[.º°O]*\s*)?"
    r"[0-9OIlLSGg]{1,3}(?:(?:\s*[.\-]\s*)+|\s+)[0-9OIlLSGg]{3}"
    r"\s*(?:[/\-()]\s*[A-Z]{2}\s*\)?)?",
    re.IGNORECASE,
)
RCL_BY_YEAR = re.compile(
    r"\bRCL\s+DE\s+\d{4}\s*,\s*REL[.]\s*(?:\n\s*)?MIN[.]\s*[^,.\n]+",
    re.IGNORECASE,
)
LAW_CITATION = re.compile(
    r"\bART(?:IGO)?S?[.]?\s*(?:\n\s*)?\d[\d.]*[º°]?"
    r"(?:\s*,\s*(?:§\s*\d+[º°]?(?:-[A-Z])?|[IVXLCDM]+|['’\"]?[A-Z]['’\"]?))*"
    r"\s*,?\s+(?:DO|DA)\s+"
    r"(?:"
    r"CONSTITUI[CÇ][AÃ]O(?:\s+(?:DA\s+REP[UÚ]BLICA|FEDERAL))?"
    r"|C[OÓ]DIGO\s+(?:CIVIL|ELEITORAL|PENAL(?:\s+MILITAR)?|DE\s+PROCESSO\s+(?:CIVIL|PENAL)|DE\s+DEFESA\s+DO\s+CONSUMIDOR)"
    r"|CONSOLIDA[CÇ][AÃ]O\s+DAS\s+LEIS\s+DO\s+TRABALHO|CPC|CPP|CLT"
    r"|LEI(?:\s+COMPLEMENTAR)?\s+(?:N\s*[.º°O]*\s*)?[\d.]+\s*/\s*\d{2,4}"
    r")",
    re.IGNORECASE,
)


def _overlaps(left: dict[str, Any], start: int, end: int) -> bool:
    return left["inicio"] < end and left["fim"] > start


def _repair_entities(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recompõe processos fragmentados pelo BIO e corrige rótulos inequívocos."""

    repaired = [dict(entity) for entity in entities]

    # O modelo por vezes separa dois blocos numéricos contíguos do mesmo
    # processo (por exemplo, ``APL 7357`` + ``51-18...``).
    merged: list[dict[str, Any]] = []
    for entity in sorted(repaired, key=lambda item: (item["inicio"], item["fim"])):
        previous = merged[-1] if merged else None
        if (
            previous
            and previous["tipo"] == entity["tipo"] == "ACOR"
            and 0 <= entity["inicio"] - previous["fim"] <= 3
            and re.fullmatch(
                r"[A-Z\d.\-\s/]+",
                text[previous["fim"]:entity["inicio"]] + entity["trecho"],
                re.IGNORECASE,
            )
        ):
            previous["fim"] = entity["fim"]
            previous["trecho"] = text[previous["inicio"]:entity["fim"]]
            previous["span_ok"] = True
            previous["confianca"] = max(float(previous["confianca"]), float(entity["confianca"]))
        else:
            merged.append(entity)
    repaired = merged

    for pattern, label in (
        (TST_CITATION, "ACOR"),
        (RCL_CITATION, "ACOR"),
        (RCL_BY_YEAR, "ACOR"),
        (LAW_CITATION, "LEG"),
    ):
        for match in pattern.finditer(text):
            overlapping = [item for item in repaired if _overlaps(item, match.start(), match.end())]
            repaired = [item for item in repaired if not _overlaps(item, match.start(), match.end())]
            repaired.append({
                "tipo": label,
                "inicio": match.start(),
                "fim": match.end(),
                "trecho": text[match.start():match.end()],
                "span_ok": True,
                "confianca": (
                    max(float(item["confianca"]) for item in overlapping)
                    if overlapping else 0.995
                ),
            })

    for entity in repaired:
        surface = entity["trecho"].strip()
        if re.search(r"^ART(?:IGO)?S?[.]?\s*\d", surface, re.IGNORECASE | re.DOTALL):
            entity["tipo"] = "LEG"
        elif re.search(r"^(?:AR\b|RCL|RECL|RE\b|RESP|ARESP|AGRESP|R[.]?ESP|TST\s*[-–—]).*\d", surface, re.IGNORECASE | re.DOTALL):
            entity["tipo"] = "ACOR"
        elif re.search(r"^(?:S[UÚ]M|5[UÚ]M)", surface, re.IGNORECASE):
            entity["tipo"] = "SUM"

    selected = []
    for entity in repaired:
        surface = entity["trecho"].strip()
        if len(surface) < 4:
            continue
        selected.append(entity)
    return sorted(selected, key=lambda item: (item["inicio"], item["fim"]))


class CitationIdentifier:
    """Carrega um checkpoint local uma vez e identifica citações em documentos."""

    def __init__(
        self,
        model_path: Path,
        *,
        device: str = "auto",
        max_length: int = 512,
        stride: int = 96,
    ) -> None:
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA foi solicitada, mas não está disponível")
        self.device = torch.device(device)
        self.max_length = max_length
        self.stride = stride
        self.model_path = Path(model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, use_fast=True, local_files_only=True
        )
        self.model = AutoModelForTokenClassification.from_pretrained(
            self.model_path, local_files_only=True
        ).to(self.device)
        self.model.eval()

    def identify(self, text: str) -> tuple[list[dict[str, Any]], int]:
        """Retorna entidades ordenadas, com IDs estáveis, e reparos BIO."""

        entities, repairs = predict_text(
            text,
            self.model,
            self.tokenizer,
            self.device,
            max_length=self.max_length,
            stride=self.stride,
        )
        entities = _repair_entities(text, entities)
        for position, entity in enumerate(entities, 1):
            entity["id"] = f"c{position}"
        return entities, repairs

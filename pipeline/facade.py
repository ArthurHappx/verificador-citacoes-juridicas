"""Fachada que coordena identificação, extração, recuperação e saída."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extraction import extract_citation
from identifier import CitationIdentifier
from retrieval import CanonicalRepository, decide
from retrieval.normalization import sha256_file
from version import __version__

from .enrichment import enrich_extraction
from .validation import validate_document


TYPE_MAP = {
    "LEG": ("lei", "dispositivo"),
    "SUM": ("jurisprudencia", "sumula"),
    "ACOR": ("jurisprudencia", "acordao"),
}


def _supported(nature: str, data: dict[str, Any]) -> bool:
    """Rejeita fragmentos NER sem identidade ou descrição incompleta útil."""

    if nature == "acordao":
        return bool(
            data.get("numero")
            or (data.get("tribunal") and (data.get("ano") or data.get("relator")))
            or (data.get("ano") and data.get("relator"))
        )
    if nature == "sumula":
        return bool(data.get("numero"))
    if nature == "dispositivo":
        return bool(data.get("artigo"))
    return False


@dataclass(frozen=True)
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    model_path: Path
    database_path: Path
    index_path: Path
    converter_path: Path
    submission_path: Path
    device: str = "auto"
    verify_hash: bool = True
    seed: int = 42
    index_rebuilt: bool = False
    index_manifest: dict[str, Any] | None = None


def _error(stage: str, code: str, error: BaseException, *, recoverable: bool, citation_id: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "etapa": stage,
        "codigo": code,
        "mensagem": f"{type(error).__name__}: {error}",
        "recuperavel": recoverable,
    }
    if citation_id:
        value["citacao_id"] = citation_id
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _level(document_id: str) -> int | None:
    match = re.search(r"(?:^|_)n([12])(?:_|$)", document_id, re.IGNORECASE)
    return int(match.group(1)) if match else None


class PipelineFacade:
    """Mantém recursos carregados e isola falhas por documento/citação."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.identifier = CitationIdentifier(config.model_path, device=config.device)
        self.repository = CanonicalRepository(
            config.database_path, config.index_path, verify_hash=config.verify_hash
        )
        self.base_hash = self.repository.metadata["source_db_sha256"]
        self.index_hash = sha256_file(config.index_path)

    def close(self) -> None:
        self.repository.close()

    def _citation(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        citation_id = entity["id"]
        label = entity["tipo"]
        public_type, nature = TYPE_MAP[label]
        errors: list[dict[str, Any]] = []
        extraction_data: dict[str, Any] = {}
        extraction_warnings: list[str] = []
        retrieval: dict[str, Any]
        technical_error = False

        try:
            extracted = extract_citation(entity["trecho"], label, citation_id=citation_id)
            extraction_data, extraction_warnings = enrich_extraction(
                entity["trecho"], extracted["natureza"], extracted["dados"]
            )
            public_type, nature = extracted["tipo"], extracted["natureza"]
        except Exception as error:  # erro é persistido por citação
            errors.append(_error("extracao", "EXTRACTION_ERROR", error, recoverable=True, citation_id=citation_id))
            technical_error = True

        if not technical_error and not _supported(nature, extraction_data):
            return None

        try:
            retrieval = self.repository.retrieve(nature, extraction_data)
        except Exception as error:
            errors.append(_error("recuperacao", "RETRIEVAL_ERROR", error, recoverable=True, citation_id=citation_id))
            retrieval = {
                "executada": False,
                "status": "erro_tecnico",
                "identidade_minima_suficiente": False,
                "tentativas": [],
                "total_candidatos": 0,
                "candidatos": [],
            }
            technical_error = True

        decision = decide(retrieval, technical_error=technical_error)
        # A confiança NER participa com peso pequeno; decisão e vínculo canônico
        # dominam a probabilidade da resposta completa.
        final_confidence = round(0.85 * decision["confianca"] + 0.15 * float(entity["confianca"]), 4)
        return {
            "citacao_id": citation_id,
            "inicio": int(entity["inicio"]),
            "fim": int(entity["fim"]),
            "trecho": entity["trecho"],
            "tipo": public_type,
            "natureza": nature,
            "identificacao": {
                "rotulo_ner": label,
                "confianca": round(float(entity["confianca"]), 6),
                "span_ok": bool(entity.get("span_ok")),
            },
            "extracao": {
                "dados": extraction_data,
                "campos_ambiguos": extraction_data.get("classe_normalizada_candidatos", []),
                "alertas": extraction_warnings,
            },
            "recuperacao": retrieval,
            "decisao": decision["decisao"],
            "classificacao": decision["classificacao"],
            "resolucao": decision["resolucao"],
            "confianca": final_confidence,
            "erros": errors,
        }

    def process_path(self, path: Path) -> dict[str, Any]:
        document_id = path.stem
        errors: list[dict[str, Any]] = []
        document: dict[str, Any] = {
            "schema_version": "1.0",
            "documento_id": document_id,
            "nivel": _level(document_id),
            "fonte": {"arquivo": path.name},
            "pipeline": {
                "versao": __version__,
                "modelo_identificacao": self.config.model_path.name,
                "base_sha256": self.base_hash,
                "indice_sha256": self.index_hash,
            },
            "citacoes": [],
            "diagnostico": {},
            "erros": errors,
        }
        try:
            text = path.read_text(encoding="utf-8")
            document["fonte"].update(
                texto_len=len(text), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
            )
        except Exception as error:
            errors.append(_error("leitura", "DOCUMENT_READ_ERROR", error, recoverable=False))
            document["diagnostico"] = {"total_citacoes": 0, "reparos_bio": 0}
            return document

        try:
            entities, repairs = self.identifier.identify(text)
        except Exception as error:
            errors.append(_error("identificacao", "IDENTIFICATION_ERROR", error, recoverable=False))
            document["diagnostico"] = {"total_citacoes": 0, "reparos_bio": 0}
            return document

        citations = []
        discarded = 0
        for entity in entities:
            try:
                citation = self._citation(entity)
                if citation is None:
                    discarded += 1
                else:
                    citations.append(citation)
            except Exception as error:
                errors.append(_error("citacao", "CITATION_PIPELINE_ERROR", error, recoverable=True, citation_id=entity["id"]))
                public_type, nature = TYPE_MAP.get(entity.get("tipo"), ("jurisprudencia", "acordao"))
                citations.append({
                    "citacao_id": entity["id"], "inicio": entity["inicio"], "fim": entity["fim"],
                    "trecho": entity["trecho"], "tipo": public_type, "natureza": nature,
                    "identificacao": {"rotulo_ner": entity.get("tipo"), "confianca": entity.get("confianca"), "span_ok": entity.get("span_ok")},
                    "extracao": {"dados": {}, "campos_ambiguos": [], "alertas": []},
                    "recuperacao": {"executada": False, "status": "erro_tecnico", "identidade_minima_suficiente": False, "tentativas": [], "total_candidatos": 0, "candidatos": []},
                    "decisao": {"regra": "ERRO_TECNICO", "motivos": []},
                    "classificacao": "incompleta", "resolucao": None, "confianca": 0.2,
                    "erros": [_error("citacao", "CITATION_PIPELINE_ERROR", error, recoverable=True, citation_id=entity["id"])],
                })
        document["citacoes"] = citations
        document["diagnostico"] = {
            "total_citacoes": len(citations),
            "reparos_bio": repairs,
            "entidades_descartadas": discarded,
            "citacoes_com_erro": sum(bool(item["erros"]) for item in citations),
        }
        validate_document(document, text)
        return document

    def run(self) -> dict[str, Any]:
        paths = sorted(self.config.input_dir.glob("*.txt"))
        if not paths:
            raise ValueError(f"nenhum arquivo .txt encontrado em {self.config.input_dir}")
        json_dir = self.config.output_dir / "enriched_json"
        json_dir.mkdir(parents=True, exist_ok=True)
        expected = {path.stem for path in paths}
        stale = {path.stem for path in json_dir.glob("*.json")} - expected
        if stale:
            raise ValueError(f"diretório de saída contém JSONs obsoletos: {sorted(stale)[:3]}")

        summaries = []
        for path in paths:
            document = self.process_path(path)
            _atomic_json(json_dir / f"{path.stem}.json", document)
            summaries.append({
                "documento_id": path.stem,
                "citacoes": len(document["citacoes"]),
                "erros": len(document["erros"]) + sum(len(item["erros"]) for item in document["citacoes"]),
            })

        submission = self.config.submission_path
        submission.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [sys.executable, str(self.config.converter_path), str(json_dir), str(submission)],
            check=True,
            capture_output=True,
            text=True,
        )
        with submission.open(encoding="utf-8-sig", newline="") as stream:
            submission_ids = [row.get("documento_id", "") for row in csv.DictReader(stream)]
        if len(submission_ids) != len(expected) or set(submission_ids) != expected:
            raise RuntimeError(
                "o CSV produzido pelo conversor não contém exatamente um registro por documento"
            )
        summary = {
            "pipeline_version": __version__,
            "seed": self.config.seed,
            "documentos": len(paths),
            "citacoes": sum(item["citacoes"] for item in summaries),
            "erros": sum(item["erros"] for item in summaries),
            "saida_json": str(json_dir),
            "submission": str(submission),
            "conversor_stdout": completed.stdout.strip(),
            "indice_reconstruido": self.config.index_rebuilt,
            "indice_manifesto": self.config.index_manifest,
            "por_documento": summaries,
        }
        _atomic_json(self.config.output_dir / "run_summary.json", summary)
        return summary

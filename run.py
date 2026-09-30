"""Ponto de entrada único da solução BRACIS 2026."""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
from pathlib import Path

import torch

from pipeline.facade import PipelineConfig, PipelineFacade
from retrieval.build_canonical_index import SCHEMA_VERSION, build_index
from retrieval.normalization import sha256_file


ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recebe o SQLite canônico e a pasta de .txt, constrói o índice "
            "lateral e grava o CSV de submissão."
        )
    )
    parser.add_argument("database", type=Path, help="SQLite original fornecido pela organização")
    parser.add_argument("input_dir", type=Path, help="pasta contendo os documentos .txt")
    parser.add_argument("output_file", type=Path, help="caminho do CSV de submissão")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "models" / "bertimbau-citations",
        help="checkpoint NER local; nenhum download é feito durante a execução",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="diretório dos JSONs enriquecidos, índice e resumo (padrão: pasta do CSV)",
    )
    parser.add_argument("--index", type=Path, help="índice lateral reutilizável")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rebuild-index", action="store_true")
    return parser


def _validate_inputs(database: Path, input_dir: Path, model: Path) -> None:
    if not database.is_file():
        raise FileNotFoundError(f"banco SQLite não encontrado: {database}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"pasta de entrada não encontrada: {input_dir}")
    if not any(input_dir.glob("*.txt")):
        raise ValueError(f"nenhum arquivo .txt encontrado em {input_dir}")
    required_model_files = ("config.json", "model.safetensors", "tokenizer.json")
    missing = [name for name in required_model_files if not (model / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"checkpoint incompleto em {model}; ausentes: {', '.join(missing)}. "
            "Execute scripts/download_model.sh antes da execução offline."
        )
    expected_hash = None
    for line in (ROOT / "model-release.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("MODEL_WEIGHTS_SHA256="):
            expected_hash = line.split("=", 1)[1].strip().strip('"')
            break
    if not expected_hash or sha256_file(model / "model.safetensors") != expected_hash:
        raise ValueError("o SHA-256 de model.safetensors não corresponde à versão aprovada")


def _index_matches(index: Path, database: Path) -> bool:
    if not index.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{index.resolve()}?mode=ro", uri=True)
        try:
            metadata = dict(connection.execute("SELECT key,value FROM index_metadata"))
        finally:
            connection.close()
    except (sqlite3.Error, OSError, ValueError):
        return False
    return (
        metadata.get("schema_version") == SCHEMA_VERSION
        and metadata.get("source_db_sha256") == sha256_file(database)
    )


def _configure_determinism(seed: int) -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = args.database.resolve()
    input_dir = args.input_dir.resolve()
    output_file = args.output_file.resolve()
    model = args.model.resolve()
    artifacts_dir = (args.artifacts_dir or output_file.parent).resolve()
    index = (args.index or artifacts_dir / "canonical_index.sqlite").resolve()

    _validate_inputs(database, input_dir, model)
    if index == database:
        raise ValueError("o índice lateral não pode sobrescrever o banco de entrada")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _configure_determinism(args.seed)

    index_rebuilt = args.rebuild_index or not _index_matches(index, database)
    index_manifest = None
    if index_rebuilt:
        index_manifest = build_index(
            database,
            index,
            ROOT / "data" / "dicionario_classes.json",
        )

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=artifacts_dir,
        model_path=model,
        database_path=database,
        index_path=index,
        converter_path=ROOT / "json_to_submission.py",
        submission_path=output_file,
        device=args.device,
        verify_hash=True,
        seed=args.seed,
        index_rebuilt=index_rebuilt,
        index_manifest=index_manifest,
    )
    facade = PipelineFacade(config)
    try:
        summary = facade.run()
    finally:
        facade.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

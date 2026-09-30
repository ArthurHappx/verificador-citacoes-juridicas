"""Gera os dois artefatos de smoke test para inspeção humana.

Uso a partir da raiz do repositório::

    python -m extraction.testes.smoke_test
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..extractor import extract_citation, extract_document


TESTS_DIR = Path(__file__).resolve().parent
DEFAULT_TEST = TESTS_DIR / "test_annotations_combined.json"
DEFAULT_TRAIN = TESTS_DIR / "train_annotations_combined.json"
DEFAULT_CSV = TESTS_DIR / "synt_citacoes_bd.csv"
DEFAULT_ANNOTATIONS_OUTPUT = TESTS_DIR / "smoke_annotations.json"
DEFAULT_CSV_OUTPUT = TESTS_DIR / "smoke_synt_bd.json"

NATURE_TO_INPUT_TYPE = {
    "dispositivo": "LEG",
    "acordao": "ACOR",
    "sumula": "SUM",
}


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, list):
        raise ValueError(f"A raiz de {path} deve ser uma lista")
    return value


def _atomic_json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def process_annotations(test_path: Path, train_path: Path) -> list[dict[str, Any]]:
    documents = _read_json(test_path) + _read_json(train_path)
    return [extract_document(document) for document in documents]


def process_csv(path: Path) -> list[dict[str, Any]]:
    documents = []
    with path.open(encoding="utf-8", newline="") as stream:
        for number, row in enumerate(csv.DictReader(stream), start=1):
            natureza = row["natureza"].strip().lower()
            try:
                input_type = NATURE_TO_INPUT_TYPE[natureza]
            except KeyError:
                raise ValueError(
                    f"Natureza desconhecida na linha {number + 1}: {natureza!r}"
                ) from None
            trecho = row["text"]
            documents.append(
                {
                    "documento_id": f"synt_bd_{number}",
                    "text": trecho,
                    "citacoes": [
                        extract_citation(trecho, input_type, citation_id="c1")
                    ],
                }
            )
    return documents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST)
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--annotations-output", type=Path, default=DEFAULT_ANNOTATIONS_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    annotations = process_annotations(args.test, args.train)
    synthetic = process_csv(args.csv)
    _atomic_json_dump(args.annotations_output, annotations)
    _atomic_json_dump(args.csv_output, synthetic)
    annotation_citations = sum(len(document["citacoes"]) for document in annotations)
    print(
        f"annotations: {len(annotations)} documentos, "
        f"{annotation_citations} citacoes -> {args.annotations_output}"
    )
    print(
        f"synthetic: {len(synthetic)} documentos, {len(synthetic)} citacoes "
        f"-> {args.csv_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

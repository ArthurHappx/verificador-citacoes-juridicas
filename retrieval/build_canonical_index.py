"""Constrói um índice lateral determinístico sem alterar a base canônica."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from extraction.class_normalizer import resolve_procedural_class
from extraction.extractors.acordao import extract_acordao
from extraction.extractors.dispositivo import extract_dispositivo
from extraction.extractors.sumula import extract_sumula

from .normalization import class_key, digits, fold


SCHEMA_VERSION = "1"
BUILDER_VERSION = "1.0.0"

CNJ_RE = re.compile(
    r"(?<!\d)(\d{1,7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4})(?!\d)"
)
TST_CODE_RE = re.compile(
    r"\bTST\s*[-–—]\s*(?P<class>[A-ZÀ-Ý.\-\s]+?)\s*[-–—]\s*"
    r"(?P<number>\d{1,7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*5\s*\.\s*\d{2}\s*\.\s*\d{4})",
    re.IGNORECASE,
)
TST_TARGET_RE = re.compile(
    r"(?:RECURSO\s+(?:DE\s+REVISTA(?:\s+COM\s+AGRAVO)?|ORDIN[AÁ]RIO\s+TRABALHISTA))"
    r"\s+N\s*[.º°O]*\s*TST\s*[-–—]\s*(?P<class>[A-ZÀ-Ý.\-\s]+?)\s*[-–—]\s*"
    r"(?P<number>\d{1,7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*5\s*\.\s*\d{2}\s*\.\s*\d{4})",
    re.IGNORECASE,
)
LABELED_RE = re.compile(
    r"\bN\s*[.º°O]*\s*(?P<number>\d{1,3}(?:\s*\.\s*\d{3})+|\d{2,8})(?!\s*[-.]\s*\d{2}\s*\.\s*\d{4})",
    re.IGNORECASE,
)
STF_NUMBER_RE = re.compile(
    r"(?:RECLAMA[CÇ][AÃ]O|RECURSO\s+EXTRAORDIN[AÁ]RIO|HABEAS\s+CORPUS|"
    r"MANDADO\s+DE\s+SEGURAN[CÇ]A|A[CÇ][AÃ]O\s+PENAL|ARGUI[CÇ][AÃ]O|PETI[CÇ][AÃ]O)"
    r"\s+(?P<number>\d{1,3}(?:\s*\.\s*\d{3})+|\d{2,8})",
    re.IGNORECASE,
)
UF_RE = re.compile(r"(?:[-/()]|\b)(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b")
STATE_NUMBER_RE = re.compile(
    r"(?P<number>\d{1,3}(?:\s*\.\s*\d{3})+|\d{2,8})\s+"
    r"(?:ACRE|ALAGOAS|AMAPA|AMAZONAS|BAHIA|CEARA|DISTRITO\s+FEDERAL|ESPIRITO\s+SANTO|"
    r"GOIAS|MARANHAO|MATO\s+GROSSO(?:\s+DO\s+SUL)?|MINAS\s+GERAIS|PARA|PARAIBA|"
    r"PARANA|PERNAMBUCO|PIAUI|RIO\s+DE\s+JANEIRO|RIO\s+GRANDE\s+DO\s+(?:NORTE|SUL)|"
    r"RONDONIA|RORAIMA|SANTA\s+CATARINA|SAO\s+PAULO|SERGIPE|TOCANTINS)\b",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _header_slice(text: str, tribunal: str) -> tuple[int, int, str]:
    """Delimita a região que identifica o próprio acórdão."""

    if tribunal == "TST":
        match = TST_TARGET_RE.search(text)
        if match:
            return max(0, match.start() - 180), min(len(text), match.end() + 220), "tst_recurso_numero"
        match = TST_CODE_RE.search(text)
        if match:
            return max(0, match.start() - 260), min(len(text), match.end() + 220), "tst_codigo_processo"
        match = re.search(r"\bTST\s*[-–—].{0,220}", text, re.IGNORECASE | re.DOTALL)
        if match:
            return max(0, match.start() - 200), min(len(text), match.end() + 100), "tst_fallback"
        return 0, min(len(text), 2000), "tst_limite_fallback"

    markers = {
        "STF": r"\bRELATORA?\s*:",
        "STJ": r"\bRELATOR\s*:",
        "TSE": r"\bRELATOR(?:A|\s+ORIGIN[AÁ]RIO)?\s*:",
        "STM": r"\bRELATORA?\s*:",
    }
    marker = re.search(markers.get(tribunal, r"\bEMENTA\b"), text[:3000], re.IGNORECASE)
    if marker:
        tail = text[marker.end():marker.end() + 180]
        stop = re.search(r"\b(?:RECORRENTE|AGRAVANTE|APELANTE|REVISOR|REDATOR|EMENTA)\b", tail, re.IGNORECASE)
        end = marker.end() + (stop.start() if stop else min(len(tail), 120))
        return 0, end, f"{tribunal.lower()}_ate_relator"
    end_marker = re.search(r"\bEMENTA\b", text[:3000], re.IGNORECASE)
    return 0, end_marker.start() if end_marker else min(len(text), 1200), f"{tribunal.lower()}_fallback"


def _number_records(header: str, tribunal: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: str, kind: str, primary: int) -> None:
        value = digits(raw)
        if len(value) < 2 or value in seen:
            return
        seen.add(value)
        item: dict[str, Any] = {
            "number_digits": value,
            "number_type": kind,
            "is_primary": primary,
            "cnj_year": None,
            "cnj_segment": None,
            "cnj_region": None,
        }
        if kind == "cnj" and len(value) >= 20:
            item.update(cnj_year=int(value[-13:-9]), cnj_segment=int(value[-9]), cnj_region=value[-8:-6])
        records.append(item)

    tst = (TST_TARGET_RE.search(header) or TST_CODE_RE.search(header)) if tribunal == "TST" else None
    if tst:
        add(tst.group("number"), "cnj", 1)

    cnjs = list(CNJ_RE.finditer(header))
    for position, match in enumerate(cnjs):
        add(match.group(1), "cnj", 1 if tribunal in {"TST", "TSE", "STM"} and position == 0 else 0)

    # OCR eleitoral/militar frequentemente remove pontos ou insere espaços
    # dentro do ano. A região logo após o marcador de número permanece curta e
    # tipada, portanto a correção é restrita a ela.
    if tribunal in {"TSE", "STM", "TST"}:
        for marker in re.finditer(r"\bN\s*[.º°O]*\s*", header, re.IGNORECASE):
            tail = header[marker.end():marker.end() + 75]
            chunk = re.match(r"\d(?:[\d.\-\s]*\d)", tail)
            if chunk:
                compact = digits(chunk.group(0))
                if len(compact) >= 14:
                    add(chunk.group(0), "cnj", 1 if not records else 0)

    for position, match in enumerate(LABELED_RE.finditer(header)):
        add(match.group("number"), "traditional", 1 if not records and position == 0 else 0)

    if tribunal == "STF" and not records:
        match = STF_NUMBER_RE.search(header)
        if match:
            add(match.group("number"), "traditional", 1)
    if tribunal == "STF":
        match = STATE_NUMBER_RE.search(fold(header))
        if match:
            add(match.group("number"), "traditional", 1)
            for item in records:
                item["is_primary"] = int(item["number_digits"] == digits(match.group("number")))

    if records and not any(item["is_primary"] for item in records):
        records[0]["is_primary"] = 1
    return records


def _class_aliases(header: str, tribunal: str, dictionary: dict[str, Any]) -> list[str]:
    normalized_header = class_key(header)
    found: list[tuple[int, int, str]] = []
    for surface, entries in dictionary.items():
        surface_key = class_key(surface)
        if not surface_key:
            continue
        match = re.search(r"(?<![A-Z0-9])" + re.escape(surface_key) + r"(?![A-Z0-9])", normalized_header)
        if not match:
            continue
        for entry in entries:
            if entry.get("tribunal") not in {None, tribunal}:
                continue
            canonical = class_key(entry.get("classe_normalizada"))
            if canonical:
                found.append((match.start(), -len(surface_key), canonical))
    found.sort()
    return list(dict.fromkeys(value for _, _, value in found[:8]))


def _infer_uf(header: str, tribunal: str, number: dict[str, Any]) -> str | None:
    matches = list(UF_RE.finditer(fold(header)))
    if matches:
        return matches[0].group(1)
    if tribunal == "TST" and number.get("cnj_region"):
        unique = {
            "01": "RJ", "03": "MG", "04": "RS", "05": "BA", "06": "PE", "07": "CE",
            "09": "PR", "12": "SC", "13": "PB", "16": "MA", "17": "ES", "18": "GO",
            "19": "AL", "20": "SE", "21": "RN", "22": "PI", "23": "MT", "24": "MS",
        }
        return unique.get(number["cnj_region"])
    return None


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA foreign_keys=ON;
        CREATE TABLE index_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE canonical_document(
            id_canonico INTEGER PRIMARY KEY,
            documento_id TEXT NOT NULL UNIQUE,
            natureza TEXT NOT NULL,
            tribunal TEXT,
            ano INTEGER,
            relator_normalizado TEXT,
            header_start INTEGER NOT NULL,
            header_end INTEGER NOT NULL,
            header_strategy TEXT NOT NULL,
            header_raw TEXT NOT NULL,
            header_normalized TEXT NOT NULL,
            parse_status TEXT NOT NULL
        );
        CREATE TABLE acordao_key(
            id_canonico INTEGER NOT NULL REFERENCES canonical_document(id_canonico),
            numero_digitos TEXT NOT NULL,
            numero_tipo TEXT NOT NULL,
            principal INTEGER NOT NULL,
            classe_normalizada TEXT,
            uf TEXT,
            cnj_ano INTEGER,
            cnj_segmento INTEGER,
            cnj_regiao TEXT,
            UNIQUE(id_canonico, numero_digitos)
        );
        CREATE TABLE acordao_class(
            id_canonico INTEGER NOT NULL REFERENCES canonical_document(id_canonico),
            classe_normalizada TEXT NOT NULL,
            UNIQUE(id_canonico, classe_normalizada)
        );
        CREATE TABLE sumula_key(
            id_canonico INTEGER PRIMARY KEY REFERENCES canonical_document(id_canonico),
            tribunal TEXT NOT NULL,
            numero INTEGER NOT NULL,
            vinculante INTEGER NOT NULL
        );
        CREATE TABLE dispositivo_key(
            id_canonico INTEGER PRIMARY KEY REFERENCES canonical_document(id_canonico),
            diploma TEXT NOT NULL,
            artigo TEXT NOT NULL
        );
        CREATE TABLE index_warning(
            id_canonico INTEGER NOT NULL REFERENCES canonical_document(id_canonico),
            codigo TEXT NOT NULL,
            detalhes TEXT
        );
        CREATE VIRTUAL TABLE header_fts USING fts5(
            id_canonico UNINDEXED, classe, numero, tribunal, uf, relator,
            header_normalized, tokenize='unicode61 remove_diacritics 2'
        );
        CREATE INDEX idx_acordao_numero ON acordao_key(numero_digitos);
        CREATE INDEX idx_acordao_numero_uf ON acordao_key(numero_digitos, uf);
        CREATE INDEX idx_acordao_classe ON acordao_class(classe_normalizada);
        CREATE INDEX idx_sumula_identidade ON sumula_key(tribunal, numero, vinculante);
        CREATE INDEX idx_dispositivo_identidade ON dispositivo_key(diploma, artigo);
    """)


def build_index(database: Path, output: Path, class_dictionary: Path) -> dict[str, Any]:
    """Gera o índice por substituição atômica e retorna seu manifesto."""

    database = database.resolve()
    source_hash = sha256_file(database)
    dictionary = json.loads(class_dictionary.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    warnings = 0
    try:
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        target = sqlite3.connect(temporary)
        _create_schema(target)
        rows = source.execute("SELECT * FROM documentos ORDER BY id").fetchall()
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "source_db_sha256": source_hash,
            "source_row_count": str(len(rows)),
        }
        target.executemany("INSERT INTO index_metadata VALUES (?, ?)", sorted(metadata.items()))

        for row in rows:
            natureza, tribunal, text = row["natureza"], row["tribunal"], row["texto"]
            if natureza == "acordao":
                start, end, strategy = _header_slice(text, tribunal)
            else:
                start, end, strategy = 0, min(len(text), 500), f"{natureza}_inicio"
            header = text[start:end]
            status = "ok"
            target.execute(
                "INSERT INTO canonical_document VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"], row["documento_id"], natureza, tribunal, row["ano"], fold(row["relator"]),
                    start, end, strategy, header, fold(header), status,
                ),
            )

            if natureza == "acordao":
                numbers = _number_records(header, tribunal)
                parsed = extract_acordao(header)
                classes = _class_aliases(header, tribunal, dictionary)
                if parsed.get("classe_processual_normalizada"):
                    classes.insert(0, class_key(parsed["classe_processual_normalizada"]))
                classes = list(dict.fromkeys(filter(None, classes)))
                if not numbers:
                    warnings += 1
                    target.execute("INSERT INTO index_warning VALUES (?,?,?)", (row["id"], "NO_CASE_NUMBER", strategy))
                for number in numbers:
                    uf = _infer_uf(header, tribunal, number)
                    target.execute(
                        "INSERT INTO acordao_key VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            row["id"], number["number_digits"], number["number_type"], number["is_primary"],
                            classes[0] if classes else None, uf, number["cnj_year"],
                            number["cnj_segment"], number["cnj_region"],
                        ),
                    )
                for class_name in classes:
                    target.execute("INSERT OR IGNORE INTO acordao_class VALUES (?,?)", (row["id"], class_name))
                target.execute(
                    "INSERT INTO header_fts VALUES (?,?,?,?,?,?,?)",
                    (
                        row["id"], " ".join(classes), " ".join(item["number_digits"] for item in numbers),
                        tribunal or "", parsed.get("uf") or "", fold(row["relator"]), fold(header),
                    ),
                )
            elif natureza == "sumula":
                parsed = extract_sumula(header)
                numbers = parsed.get("numero") or []
                if len(numbers) == 1 and (parsed.get("tribunal") or tribunal):
                    target.execute(
                        "INSERT INTO sumula_key VALUES (?,?,?,?)",
                        (row["id"], parsed.get("tribunal") or tribunal, int(numbers[0]), int(parsed.get("vinculante", False))),
                    )
                else:
                    warnings += 1
                    target.execute("INSERT INTO index_warning VALUES (?,?,?)", (row["id"], "SUMULA_PARSE_FAILED", json.dumps(parsed)))
            else:
                first_line = text.splitlines()[0]
                parsed = extract_dispositivo(first_line)
                article_match = re.search(r"\bARTIGO\s+(\d+(?:[.\-]\w+)?)", fold(first_line))
                article = article_match.group(1) if article_match else None
                diploma = parsed.get("diploma")
                if not diploma:
                    normalized = fold(first_line)
                    if "LEI COMPLEMENTAR" in normalized and re.search(r"\b64\b", normalized) and "1990" in normalized:
                        diploma = "LC64/90"
                if diploma and article:
                    target.execute(
                        "INSERT INTO dispositivo_key VALUES (?,?,?)",
                        (row["id"], diploma, article),
                    )
                else:
                    warnings += 1
                    target.execute("INSERT INTO index_warning VALUES (?,?,?)", (row["id"], "DISPOSITIVO_PARSE_FAILED", json.dumps(parsed)))

        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integridade do índice falhou: {integrity}")
        target.commit()
        target.close()
        source.close()
        os.replace(temporary, output)
        output.chmod(0o644)
        return {**metadata, "warnings": warnings, "index_sha256": sha256_file(output)}
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=root / "data" / "desafio1_bracis.db")
    parser.add_argument("--output", type=Path, default=root / "data" / "canonical_index.sqlite")
    parser.add_argument("--class-dictionary", type=Path, default=root / "data" / "dicionario_classes.json")
    args = parser.parse_args()
    print(json.dumps(build_index(args.database, args.output, args.class_dictionary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

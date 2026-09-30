"""Recuperação auditável sobre o índice canônico imutável."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from extraction.class_normalizer import resolve_procedural_class

from .normalization import class_key, digits, fold, name_matches, sha256_file


def _scalars(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class CanonicalRepository:
    """Abre índice/base em modo somente leitura e executa planos de busca."""

    def __init__(self, database: Path, index: Path, *, verify_hash: bool = True) -> None:
        self.database_path = Path(database)
        self.index_path = Path(index)
        self.connection = sqlite3.connect(f"file:{self.index_path.resolve()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        metadata = dict(self.connection.execute("SELECT key,value FROM index_metadata"))
        if verify_hash and metadata.get("source_db_sha256") != sha256_file(self.database_path):
            raise ValueError("o índice canônico não corresponde ao banco fornecido")
        self.metadata = metadata

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CanonicalRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _attempt(plan: str, fields: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
        candidates = list(rows)
        return {
            "plano": plan,
            "campos": fields,
            "total_candidatos": len(candidates),
            "id_canonicos": [item["id_canonico"] for item in candidates],
        }

    def _document_candidate(self, identifier: int, matched: list[str], conflicts: list[str]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM canonical_document WHERE id_canonico=?", (identifier,)
        ).fetchone()
        return {
            "id_canonico": row["id_canonico"],
            "documento_id_base": row["documento_id"],
            "natureza": row["natureza"],
            "tribunal": row["tribunal"],
            "ano": row["ano"],
            "campos_confirmados": matched,
            "campos_conflitantes": conflicts,
            "evidencias": [{"origem": "cabecalho", "estrategia": row["header_strategy"]}],
        }

    def retrieve_sumula(self, data: dict[str, Any]) -> dict[str, Any]:
        tribunal = fold(data.get("tribunal")) or ("STF" if data.get("vinculante") else "")
        numbers = [digits(value) for value in _scalars(data.get("numero")) if digits(value)]
        attempts: list[dict[str, Any]] = []
        if not numbers:
            return self._result("dados_insuficientes", attempts, [], False)

        candidate_ids: set[int] = set()
        for number in numbers:
            if tribunal:
                rows = self.connection.execute(
                    "SELECT id_canonico FROM sumula_key WHERE tribunal=? AND numero=?",
                    (tribunal, int(number)),
                ).fetchall()
                ids = {int(row[0]) for row in rows}
                attempts.append(self._attempt("sumula_tribunal_numero", {"tribunal": tribunal, "numero": number}, [{"id_canonico": value} for value in sorted(ids)]))
            else:
                rows = self.connection.execute(
                    "SELECT id_canonico FROM sumula_key WHERE numero=?", (int(number),)
                ).fetchall()
                ids = {int(row[0]) for row in rows}
                attempts.append(self._attempt("sumula_numero", {"numero": number}, [{"id_canonico": value} for value in sorted(ids)]))
            candidate_ids.update(ids)

        candidates = [self._document_candidate(value, ["numero"] + (["tribunal"] if tribunal else []), []) for value in sorted(candidate_ids)]
        sufficient = bool(tribunal and len(numbers) == 1)
        return self._result("concluida", attempts, candidates, sufficient)

    def retrieve_dispositivo(self, data: dict[str, Any]) -> dict[str, Any]:
        diploma = str(data.get("diploma") or "").upper()
        articles = [str(value).upper() for value in _scalars(data.get("artigo")) if str(value).strip()]
        attempts: list[dict[str, Any]] = []
        if not articles:
            return self._result("dados_insuficientes", attempts, [], False)

        candidate_ids: set[int] = set()
        if diploma:
            for article in articles:
                rows = self.connection.execute(
                    "SELECT id_canonico FROM dispositivo_key WHERE diploma=? AND artigo=?",
                    (diploma, article),
                ).fetchall()
                ids = {int(row[0]) for row in rows}
                attempts.append(self._attempt("dispositivo_diploma_artigo", {"diploma": diploma, "artigo": article}, [{"id_canonico": value} for value in sorted(ids)]))
                candidate_ids.update(ids)
        else:
            for article in articles:
                rows = self.connection.execute(
                    "SELECT id_canonico FROM dispositivo_key WHERE artigo=?", (article,)
                ).fetchall()
                ids = {int(row[0]) for row in rows}
                attempts.append(self._attempt("dispositivo_artigo", {"artigo": article}, [{"id_canonico": value} for value in sorted(ids)]))
                candidate_ids.update(ids)

        candidates = [self._document_candidate(value, ["artigo"] + (["diploma"] if diploma else []), []) for value in sorted(candidate_ids)]
        sufficient = bool(diploma and len(articles) == 1)
        return self._result("concluida", attempts, candidates, sufficient)

    def _acordao_rows(self, number: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT DISTINCT d.*, k.numero_digitos, k.numero_tipo, k.uf AS key_uf,
                   k.cnj_ano, k.cnj_segmento, k.cnj_regiao
              FROM acordao_key k
              JOIN canonical_document d USING(id_canonico)
             WHERE k.numero_digitos=?
            """,
            (number,),
        ).fetchall()

    def _classes(self, identifier: int) -> set[str]:
        return {
            row[0]
            for row in self.connection.execute(
                "SELECT classe_normalizada FROM acordao_class WHERE id_canonico=?", (identifier,)
            )
        }

    @staticmethod
    def _class_matches(expected: str, available: set[str]) -> bool:
        expected_key = class_key(expected)
        return expected_key in available

    def _filter_acordaos(
        self, rows: list[sqlite3.Row], filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected: dict[int, dict[str, Any]] = {}
        for row in rows:
            matched = ["numero"]
            conflicts: list[str] = []
            tribunal = filters.get("tribunal")
            if tribunal:
                if fold(row["tribunal"]) != tribunal:
                    continue
                matched.append("tribunal")
            uf = filters.get("uf")
            if uf:
                header_has_uf = re_search_word(uf, row["header_normalized"])
                if row["key_uf"] != uf and not header_has_uf:
                    continue
                matched.append("uf")
            year = filters.get("ano")
            if year is not None:
                if row["ano"] != year and row["cnj_ano"] != year:
                    continue
                matched.append("ano")
            relator = filters.get("relator")
            if relator:
                if not name_matches(row["relator_normalizado"], relator):
                    continue
                matched.append("relator")
            procedural_class = filters.get("classe")
            if procedural_class:
                if not self._class_matches(procedural_class, self._classes(row["id_canonico"])):
                    continue
                matched.append("classe_processual")
            selected[row["id_canonico"]] = self._document_candidate(row["id_canonico"], matched, conflicts)
        return [selected[key] for key in sorted(selected)]

    def retrieve_acordao(self, data: dict[str, Any]) -> dict[str, Any]:
        number = digits(data.get("numero"))
        tribunal = fold(data.get("tribunal"))
        raw_class = data.get("classe_processual_normalizada") or data.get("classe_processual")
        if raw_class and not data.get("classe_processual_normalizada"):
            resolution = resolve_procedural_class(str(raw_class), tribunal=tribunal or None)
            raw_class = resolution.normalized or raw_class
        filters = {
            "tribunal": tribunal or None,
            "uf": fold(data.get("uf")) or None,
            "ano": int(data["ano"]) if data.get("ano") is not None else None,
            "relator": data.get("relator") or None,
            "classe": class_key(raw_class) if raw_class else None,
        }
        attempts: list[dict[str, Any]] = []
        if not number:
            return self._result("dados_insuficientes", attempts, [], False)

        rows = self._acordao_rows(number)
        # Tribunal e número são âncoras. Filtros auxiliares são removidos em
        # ordem conservadora apenas depois de uma tentativa sem resultados.
        active = {key: value for key, value in filters.items() if value is not None}
        plans: list[tuple[str, dict[str, Any]]] = [("acordao_completo", dict(active))]
        current = dict(active)
        for field in ("relator", "ano", "classe", "uf"):
            if field in current:
                current = {key: value for key, value in current.items() if key != field}
                plans.append((f"acordao_sem_{field}", dict(current)))

        candidates: list[dict[str, Any]] = []
        for plan, plan_filters in plans:
            candidates = self._filter_acordaos(rows, plan_filters)
            attempts.append(self._attempt(plan, {"numero": number, **plan_filters}, candidates))
            if candidates:
                break

        is_cnj = len(number) == 20
        sufficient = bool(is_cnj or (number and (tribunal or raw_class or filters.get("uf"))))
        return self._result("concluida", attempts, candidates, sufficient)

    @staticmethod
    def _result(
        status: str,
        attempts: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        sufficient: bool,
    ) -> dict[str, Any]:
        return {
            "executada": status != "dados_insuficientes",
            "status": status,
            "identidade_minima_suficiente": sufficient,
            "tentativas": attempts,
            "total_candidatos": len(candidates),
            "candidatos": candidates,
        }

    def retrieve(self, natureza: str, data: dict[str, Any]) -> dict[str, Any]:
        if natureza == "sumula":
            return self.retrieve_sumula(data)
        if natureza == "dispositivo":
            return self.retrieve_dispositivo(data)
        if natureza == "acordao":
            return self.retrieve_acordao(data)
        return self._result("natureza_desconhecida", [], [], False)


def re_search_word(value: str, text: str) -> bool:
    import re

    return bool(re.search(r"(?<![A-Z])" + re.escape(value) + r"(?![A-Z])", text))

"""Primitivas compartilhadas por treinamento, avaliação e inferência NER."""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
from torch.utils.data import Dataset

MODEL_NAME = "neuralmind/bert-base-portuguese-cased"
LABEL2ID = {"O": 0, "B-ACOR": 1, "I-ACOR": 2, "B-LEG": 3, "I-LEG": 4, "B-SUM": 5, "I-SUM": 6}
ID2LABEL = {value: key for key, value in LABEL2ID.items()}
ENTITY_TYPES = ("ACOR", "LEG", "SUM")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lê exemplos BIO JSONL e informa precisamente uma linha inválida."""
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON inválido em {path}:{line_number}") from error
            if not all(key in record for key in ("id", "text", "input_ids", "attention_mask", "labels", "offset_mapping", "spans")):
                raise ValueError(f"campos BIO ausentes em {path}:{line_number}")
            if not (len(record["input_ids"]) == len(record["attention_mask"]) == len(record["labels"]) == len(record["offset_mapping"])):
                raise ValueError(f"vetores de tamanhos diferentes em {path}:{line_number}")
            records.append(record)
    return records


def load_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    """Indexa o JSON silver por ``documento_id``; caminho nulo retorna mapa vazio."""
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("arquivo de metadados deve conter uma lista JSON")
    return {record["documento_id"]: record for record in value}


def validation_split(records: list[dict], metadata: dict[str, dict], fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Separa grupos documentais inteiros em treino/validação deterministicamente.

    O grupo vem de ``id_documento_original`` no silver. Sem metadados, cada ID
    BIO é tratado como grupo próprio. O algoritmo aproxima a fração por número
    de exemplos, sem dividir chunks de um mesmo documento.
    """
    if not 0 < fraction < 1:
        raise ValueError("validation_fraction deve estar entre 0 e 1")
    groups: dict[str, list[dict]] = {}
    for record in records:
        info = metadata.get(record["id"], {})
        group = str(info.get("id_documento_original", record["id"]))
        groups.setdefault(group, []).append(record)
    ordered = list(groups.items())
    ordered.sort(key=lambda item: hashlib.sha256(f"{seed}|{item[0]}".encode()).hexdigest())
    target, selected, count = round(len(records) * fraction), set(), 0
    for group, items in ordered:
        if count >= target:
            break
        selected.add(group); count += len(items)
    train, validation = [], []
    for group, items in groups.items():
        (validation if group in selected else train).extend(items)
    if not train or not validation:
        raise ValueError("split de validação produziu partição vazia")
    return train, validation


class TokenDataset(Dataset):
    """Dataset mínimo que entrega apenas tensores aceitos pelo modelo."""
    def __init__(self, records: list[dict]): self.records = records
    def __len__(self) -> int: return len(self.records)
    def __getitem__(self, index: int) -> dict[str, list[int]]:
        item = self.records[index]
        return {key: item[key] for key in ("input_ids", "attention_mask", "labels")}


@dataclass
class TokenCollator:
    """Padding dinâmico de IDs/máscara e labels, usando ``-100`` na loss."""
    pad_token_id: int
    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        length = max(len(item["input_ids"]) for item in features)
        def pad(values: list[int], fill: int) -> list[int]: return values + [fill] * (length-len(values))
        return {
            "input_ids": torch.tensor([pad(x["input_ids"], self.pad_token_id) for x in features]),
            "attention_mask": torch.tensor([pad(x["attention_mask"], 0) for x in features]),
            "labels": torch.tensor([pad(x["labels"], -100) for x in features]),
        }


def set_seed(seed: int) -> None:
    """Configura fontes aleatórias de Python/PyTorch para repetibilidade prática."""
    random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def bio_to_spans(label_ids: Iterable[int], offsets: Iterable[Iterable[int]], text: str) -> tuple[list[dict], int]:
    """Converte BIO de subtokens em spans Unicode, reparando ``I`` órfão.

    Returns:
        Par ``(entidades, reparos)``. Cada entidade contém tipo, início, fim e
        trecho literal. Tokens especiais e labels ``-100`` são ignorados.
    """
    entities, current, repairs = [], None, 0
    for label_id, offset in zip(label_ids, offsets):
        start, end = map(int, offset)
        if start == end or int(label_id) == -100:
            continue
        label = ID2LABEL.get(int(label_id), "O")
        if label == "O":
            if current: entities.append(current); current = None
            continue
        prefix, kind = label.split("-", 1)
        # Offsets de subtokens não incluem o espaço entre palavras; a sequência
        # BIO, e não a adjacência dos caracteres, define a continuação.
        continuation = prefix == "I" and current and current["tipo"] == kind
        if not continuation:
            if current: entities.append(current)
            if prefix == "I": repairs += 1
            current = {"tipo": kind, "inicio": start, "fim": end}
        else:
            current["fim"] = max(current["fim"], end)
    if current: entities.append(current)
    for entity in entities:
        entity["trecho"] = text[entity["inicio"]:entity["fim"]]
        entity["span_ok"] = 0 <= entity["inicio"] < entity["fim"] <= len(text) and entity["trecho"] == text[entity["inicio"]:entity["fim"]]
    return entities, repairs

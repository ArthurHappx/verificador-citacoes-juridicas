"""Inferência de spans NER em textos curtos ou longos com janelas sobrepostas."""
from __future__ import annotations

from typing import Any

import torch

from .core import bio_to_spans


def _merge_entities(candidates: list[dict]) -> list[dict]:
    """Remove duplicatas de janelas e resolve sobreposições pela confiança."""
    unique = {}
    for entity in candidates:
        key = (entity["inicio"], entity["fim"], entity["tipo"])
        if key not in unique or entity["confianca"] > unique[key]["confianca"]:
            unique[key] = entity
    selected = []
    for entity in sorted(unique.values(), key=lambda x: (-x["confianca"], x["inicio"], -x["fim"])):
        if not any(entity["inicio"] < other["fim"] and entity["fim"] > other["inicio"] for other in selected):
            selected.append(entity)
    return sorted(selected, key=lambda x: (x["inicio"], x["fim"]))


@torch.inference_mode()
def predict_text(text: str, model: Any, tokenizer: Any, device: torch.device,
                 max_length: int = 512, stride: int = 96) -> tuple[list[dict], int]:
    """Prediz entidades e spans Unicode, consolidando janelas de textos longos.

    Args:
        text: Texto original, que não sofre normalização.
        model: ``AutoModelForTokenClassification`` com labels BIO em ``config``.
        tokenizer: Tokenizer rápido correspondente ao checkpoint.
        device: Dispositivo em que o modelo está carregado.
        max_length: Tamanho total de cada janela, incluindo tokens especiais.
        stride: Quantidade de subtokens repetidos entre janelas consecutivas.

    Returns:
        Par com entidades ordenadas e número de sequências BIO inválidas
        reparadas. Cada entidade inclui tipo, trecho, offsets, confiança média e
        ``span_ok``, que verifica automaticamente o slice do texto original.
    """
    if not text: return [], 0
    if not tokenizer.is_fast: raise ValueError("inferência de spans exige tokenizer rápido")
    if stride < 0 or stride >= max_length-2: raise ValueError("stride incompatível com max_length")
    encoded = tokenizer(text, return_offsets_mapping=True, return_overflowing_tokens=True,
                        truncation=True, max_length=max_length, stride=stride, padding=False)
    candidates, repairs = [], 0
    model.eval()
    for input_ids, attention_mask, offsets in zip(encoded["input_ids"], encoded["attention_mask"], encoded["offset_mapping"]):
        ids = torch.tensor([input_ids], device=device)
        mask = torch.tensor([attention_mask], device=device)
        probabilities = model(input_ids=ids, attention_mask=mask).logits.softmax(-1)[0]
        labels = probabilities.argmax(-1).cpu().tolist()
        entities, fixed = bio_to_spans(labels, offsets, text); repairs += fixed
        for entity in entities:
            covered = [i for i,(start,end) in enumerate(offsets)
                       if start != end and start < entity["fim"] and end > entity["inicio"]]
            # Média da probabilidade da label escolhida em cada subtoken.
            entity["confianca"] = (float(torch.stack([probabilities[i, labels[i]] for i in covered]).mean().item())
                                     if covered else 0.0)
            candidates.append(entity)
    return _merge_entities(candidates), repairs

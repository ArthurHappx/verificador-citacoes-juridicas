"""Adaptador opcional para modelos token-classification do Hugging Face.

``transformers`` somente é importado quando o adaptador é instanciado. O
baseline determinístico, portanto, continua sem dependências ou downloads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .protocol import Entity


class HuggingFaceEntityRecognizer:
    def __init__(
        self,
        model: str,
        *,
        label_map: Mapping[str, str] | None = None,
        device: int | str | None = None,
        aggregation_strategy: str = "simple",
    ) -> None:
        try:
            from transformers import pipeline
        except ImportError as error:
            raise RuntimeError(
                "O adaptador opcional requer o pacote 'transformers'."
            ) from error

        kwargs = {
            "task": "token-classification",
            "model": model,
            "aggregation_strategy": aggregation_strategy,
        }
        if device is not None:
            kwargs["device"] = device
        self._pipeline = pipeline(**kwargs)
        self._label_map = dict(label_map or {})

    def recognize(self, text: str) -> Sequence[Entity]:
        entities = []
        for item in self._pipeline(text):
            source_label = str(item.get("entity_group") or item.get("entity"))
            label = self._label_map.get(source_label, source_label)
            entities.append(
                Entity(
                    label=label,
                    text=str(item["word"]),
                    start=int(item["start"]),
                    end=int(item["end"]),
                    score=float(item["score"]) if item.get("score") is not None else None,
                )
            )
        return entities


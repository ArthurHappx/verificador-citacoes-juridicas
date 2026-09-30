"""Fachada pública do extrator de informações."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from .extractors import extract_acordao, extract_dispositivo, extract_sumula
from .schemas import map_input_type

if TYPE_CHECKING:
    from .ner.protocol import EntityRecognizer


EXTRACTORS = {
    "dispositivo": extract_dispositivo,
    "acordao": extract_acordao,
    "sumula": extract_sumula,
}


def extract_citation(
    trecho: str,
    input_type: str,
    *,
    citation_id: str | None = None,
    entity_recognizer: "EntityRecognizer | None" = None,
) -> dict[str, Any]:
    """Extrai uma citação e aplica o remapeamento do rótulo do NER."""

    tipo, natureza = map_input_type(input_type)
    dados = (
        extract_acordao(trecho, entity_recognizer=entity_recognizer)
        if natureza == "acordao"
        else EXTRACTORS[natureza](trecho)
    )
    result: dict[str, Any] = {
        "id": citation_id,
        "trecho": trecho,
        "tipo": tipo,
        "natureza": natureza,
        "dados": dados,
    }
    return result


def extract_document(
    document: Mapping[str, Any], *, entity_recognizer: "EntityRecognizer | None" = None
) -> dict[str, Any]:
    """Processa o envelope produzido pelo identificador de citações."""

    try:
        documento_id = document["documento_id"]
        text = document["text"]
        citations = document["citacoes"]
    except KeyError as error:
        raise ValueError(f"Campo obrigatório ausente no documento: {error.args[0]}") from None

    extracted = []
    for index, citation in enumerate(citations, start=1):
        try:
            trecho = citation["trecho"]
            input_type = citation["tipo"]
        except KeyError as error:
            raise ValueError(
                f"Campo ausente na citação {index} de {documento_id}: {error.args[0]}"
            ) from None
        extracted.append(
            extract_citation(
                trecho,
                input_type,
                citation_id=str(citation.get("id", f"c{index}")),
                entity_recognizer=entity_recognizer,
            )
        )
    return {"documento_id": documento_id, "text": text, "citacoes": extracted}

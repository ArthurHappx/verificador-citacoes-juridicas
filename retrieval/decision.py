"""Decisão conservadora a partir do histórico de recuperação."""

from __future__ import annotations

from typing import Any


def decide(retrieval: dict[str, Any], *, technical_error: bool = False) -> dict[str, Any]:
    """Aplica cardinalidade, suficiência e consistência sem consultar a base."""

    candidates = retrieval.get("candidatos") or []
    candidate_ids = {candidate["id_canonico"] for candidate in candidates}
    attempts = retrieval.get("tentativas") or []
    used_partial = len(attempts) > 1
    candidate_id = next(iter(candidate_ids)) if len(candidate_ids) == 1 else None
    has_conflict = candidate_id is not None and any(
        candidate.get("campos_conflitantes")
        for candidate in candidates
        if candidate["id_canonico"] == candidate_id
    )

    if technical_error:
        classification, rule, resolution, confidence = "incompleta", "ERRO_TECNICO", None, 0.35
    elif len(candidate_ids) > 1:
        classification, rule, resolution, confidence = "incompleta", "MULTIPLOS_CANDIDATOS", None, 0.88
    elif has_conflict:
        classification, rule, resolution, confidence = "incompleta", "CANDIDATO_COM_CONFLITO", None, 0.75
    elif candidate_id is not None:
        classification = "real"
        rule = "UNICO_CONSISTENTE_EM_CONSULTA_PARCIAL" if len(attempts) > 1 else "UNICO_CONSISTENTE_EM_CONSULTA_COMPLETA"
        resolution = {"id_canonico": candidate_id}
        confidence = 0.90 if len(attempts) > 1 else 0.97
    elif retrieval.get("identidade_minima_suficiente"):
        classification, rule, resolution, confidence = "inventada", "IDENTIDADE_SUFICIENTE_SEM_CANDIDATO", None, 0.92
    else:
        classification, rule, resolution, confidence = "incompleta", "IDENTIDADE_INSUFICIENTE", None, 0.82

    return {
        "classificacao": classification,
        "resolucao": resolution,
        "confianca": confidence,
        "decisao": {"regra": rule, "motivos": [], "consulta_parcial": used_partial},
    }

"""Decisão conservadora a partir do histórico de recuperação."""

from __future__ import annotations

from typing import Any


def decide(retrieval: dict[str, Any], *, technical_error: bool = False) -> dict[str, Any]:
    """Aplica cardinalidade, suficiência e consistência sem consultar a base."""

    candidates = retrieval.get("candidatos") or []
    count = len({candidate["id_canonico"] for candidate in candidates})
    attempts = retrieval.get("tentativas") or []
    used_partial = len(attempts) > 1

    if technical_error:
        classification, rule, resolution, confidence = "incompleta", "ERRO_TECNICO", None, 0.35
    elif count == 1 and not candidates[0].get("campos_conflitantes"):
        classification = "real"
        rule = "UNICO_CONSISTENTE_EM_CONSULTA_PARCIAL" if len(attempts) > 1 else "UNICO_CONSISTENTE_EM_CONSULTA_COMPLETA"
        resolution = {"id_canonico": candidates[0]["id_canonico"]}
        confidence = 0.90 if len(attempts) > 1 else 0.97
    elif count > 1:
        classification, rule, resolution, confidence = "incompleta", "MULTIPLOS_CANDIDATOS", None, 0.88
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

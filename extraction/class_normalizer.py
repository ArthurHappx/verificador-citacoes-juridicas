"""Resolução contextual e normalização de classes processuais.

Adapta o normalizador da pesquisa exploratória. A diferença deliberada é que
a saída, além de NFD, remove efetivamente todos os caracteres combinantes.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from .normalization import normalize_value


CLASS_EXPANSIONS = {
    "AGR": "AGRAVO REGIMENTAL", "AGREG": "AGRAVO REGIMENTAL",
    "AGRREG": "AGRAVO REGIMENTAL", "AG": "AGRAVO",
    "AGINT": "AGRAVO INTERNO", "AGRG": "AGRAVO REGIMENTAL",
    "EDCL": "EMBARGOS DE DECLARACAO", "ED": "EMBARGOS DE DECLARACAO",
    "EDV": "EMBARGOS DE DIVERGENCIA", "ERESP": "EMBARGOS DE DIVERGENCIA EM RECURSO ESPECIAL",
    "ARESP": "AGRAVO EM RECURSO ESPECIAL", "RESP": "RECURSO ESPECIAL",
    "RHC": "RECURSO ORDINARIO EM HABEAS CORPUS",
    "RMS": "RECURSO ORDINARIO EM MANDADO DE SEGURANCA",
    "ADI": "ACAO DIRETA DE INCONSTITUCIONALIDADE",
    "ADC": "ACAO DECLARATORIA DE CONSTITUCIONALIDADE",
    "ADPF": "ARGUICAO DE DESCUMPRIMENTO DE PRECEITO FUNDAMENTAL",
    "AIRR": "AGRAVO DE INSTRUMENTO EM RECURSO DE REVISTA",
    "ARR": "RECURSO DE REVISTA COM AGRAVO",
    "RRAG": "RECURSO DE REVISTA COM AGRAVO", "RR": "RECURSO DE REVISTA",
    "RESPE": "RECURSO ESPECIAL ELEITORAL", "REspe".upper(): "RECURSO ESPECIAL ELEITORAL",
    "RP": "REPRESENTACAO", "RCL": "RECLAMACAO", "HC": "HABEAS CORPUS",
    "MS": "MANDADO DE SEGURANCA", "MI": "MANDADO DE INJUNCAO",
    "CC": "CONFLITO DE COMPETENCIA", "APL": "APELACAO",
    "RSE": "RECURSO EM SENTIDO ESTRITO", "AI": "AGRAVO DE INSTRUMENTO",
    "MC": "MEDIDA CAUTELAR", "QO": "QUESTAO DE ORDEM",
    "RG": "REPERCUSSAO GERAL", "RO": "RECURSO ORDINARIO",
    "PET": "PETICAO", "SLS": "SUSPENSAO DE LIMINAR E DE SENTENCA",
    "SS": "SUSPENSAO DE SEGURANCA", "AR": "ACAO RESCISORIA",
    "RCED": "RECURSO CONTRA EXPEDICAO DE DIPLOMA",
    "AIME": "ACAO DE IMPUGNACAO DE MANDATO ELETIVO",
    "AIJE": "ACAO DE INVESTIGACAO JUDICIAL ELEITORAL",
}

AMBIGUOUS_EXPANSIONS = {
    "RE": {"STF": "RECURSO EXTRAORDINARIO", "ELEITORAL": "RECURSO ELEITORAL"},
    "AC": {"STF": "ACAO CAUTELAR", "LOCAL": "APELACAO CIVEL"},
    "AP": {"PENAL": "ACAO PENAL", "LOCAL": "APELACAO"},
}


@dataclass(frozen=True)
class ClassNormalization:
    normalized: str | None
    candidates: list[str]
    ambiguous_keys: list[str]


def _output_form(value: str) -> str:
    value = re.sub(r"[-–—_/.,;:()'\"º°]", " ", normalize_value(value))
    return re.sub(r"\s+", " ", value).strip()


def _contextual_options(key: str, tribunal: str | None) -> list[str]:
    tribunal = (tribunal or "").upper()
    options = AMBIGUOUS_EXPANSIONS[key]
    if key == "RE":
        if tribunal == "STF":
            return [options["STF"]]
        if tribunal == "TSE" or tribunal.startswith("TRE"):
            return [options["ELEITORAL"]]
    elif key == "AC" and tribunal == "STF":
        return [options["STF"]]
    elif key == "AP" and tribunal in {"STF", "STJ"}:
        return [options["PENAL"]]
    return list(dict.fromkeys(options.values()))


def resolve_procedural_class(value: str, *, tribunal: str | None = None) -> ClassNormalization:
    recognition = normalize_value(value)
    substitutions = (
        (r"\bEMB\s*[.]?\s*DECL\s*[.]?", "EDCL"),
        (r"\bREC\s*[.]?\s*ESP\s*[.]?", "RESP"),
        (r"\bAG\s*[.]?\s*REG\b", "AGRG"),
        (r"\bAGR\s*[.]?\s*REG\b", "AGRG"),
        (r"\bEMB\s*[.]?\s*DECL\b", "EDCL"),
        (r"\bINST\s*[.]?", "INSTRUMENTO"),
        (r"\bORD[.]?(?=\s|$)", "ORDINARIO"),
        (r"^\s*TST\s*[-–—]\s*", ""),
        (r"\bAGRAVO\s+NO\s+RR\b", "AGRAVO EM RR"),
    )
    for pattern, replacement in substitutions:
        recognition = re.sub(pattern, replacement, recognition)
    recognition = re.sub(r"[-–—_/.,;:()'\"º°]", " ", recognition)
    tokens = re.sub(r"\s+", " ", recognition).strip().split()

    option_groups: list[list[str]] = []
    ambiguous_keys: list[str] = []
    for token in tokens:
        if token in AMBIGUOUS_EXPANSIONS:
            options = _contextual_options(token, tribunal)
            if len(options) > 1:
                ambiguous_keys.append(token)
            option_groups.append(options)
        else:
            option_groups.append([CLASS_EXPANSIONS.get(token, token)])

    rendered = (
        [_output_form(" ".join(parts)) for parts in itertools.product(*option_groups)]
        if option_groups else []
    )
    rendered = list(dict.fromkeys(rendered))
    if ambiguous_keys:
        return ClassNormalization(None, rendered, list(dict.fromkeys(ambiguous_keys)))
    return ClassNormalization(rendered[0] if rendered else None, [], [])


def normalize_procedural_class(value: str, *, tribunal: str | None = None) -> str | None:
    return resolve_procedural_class(value, tribunal=tribunal).normalized

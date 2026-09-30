"""Padrões independentes para os campos de citações de acórdãos."""

from __future__ import annotations

import re

from .common import FLAGS


TRIBUNALS: dict[str, tuple[re.Pattern[str], ...]] = {
    "STF": (re.compile(r"\bSTF\b", FLAGS), re.compile(r"\bSUPREMO\s+TRIBUNAL\s+FEDERAL\b", FLAGS)),
    "STJ": (re.compile(r"\bSTJ\b", FLAGS), re.compile(r"\bSUPERIOR\s+TRIBUNAL\s+DE\s+JUSTICA\b", FLAGS)),
    "TSE": (re.compile(r"\bTSE\b", FLAGS), re.compile(r"\bTRIBUNAL\s+SUPERIOR\s+ELEITORAL\b", FLAGS)),
    "TST": (re.compile(r"\bTST\b", FLAGS), re.compile(r"\bTRIBUNAL\s+SUPERIOR\s+DO\s+TRABALHO\b", FLAGS)),
    "STM": (re.compile(r"\bSTM\b", FLAGS), re.compile(r"\bSUPERIOR\s+TRIBUNAL\s+MILITAR\b", FLAGS)),
}

# Alternativas extensas aparecem antes de suas abreviações. O átomo não
# inclui conectores; CLASS_CHAIN é responsável por classes compostas.
CLASS_ATOM = r"""
(?:
    AGRAVO\s+DE\s+INSTRUMENTO\s+EM\s+RECURSO\s+DE\s+REVISTA
  | AGRAVO\s+EM\s+RECURSO\s+(?:ESPECIAL|EXTRAORDINARIO|DE\s+REVISTA)
  | AGRAVO\s+(?:INTERNO|REGIMENTAL)
  | EMBARGOS\s+DE\s+(?:DECLARACAO|DIVERGENCIA)
  | RECURSO\s+ESPECIAL\s+ELEITORAL
  | RECURSO\s+(?:ESPECIAL|EXTRAORDINARIO|ELEITORAL|ORDINARIO)
  | RECURSO\s+EM\s+(?:HABEAS\s+CORPUS|MANDADO\s+DE\s+SEGURANCA|SENTIDO\s+ESTRITO)
  | RECURSO\s+DE\s+REVISTA
  | MANDADO\s+DE\s+(?:SEGURANCA|INJUNCAO)
  | HABEAS\s+CORPUS
  | ACAO\s+(?:DIRETA\s+DE\s+INCONSTITUCIONALIDADE|DECLARATORIA\s+DE\s+CONSTITUCIONALIDADE|PENAL|RESCISORIA)
  | ARGUICAO\s+DE\s+DESCUMPRIMENTO\s+DE\s+PRECEITO\s+FUNDAMENTAL
  | CONFLITO\s+DE\s+COMPETENCIA
  | RECLAMACAO | REPRESENTACAO | APELACAO | PETICAO
  | SUSPENSAO\s+DE\s+(?:SEGURANCA|LIMINAR(?:\s+E\s+DE\s+SENTENCA)?)
  | EMB\.?\s*DECL\.?
  | REC\.?\s*ESP\.?
  | REC\.?\s+EM\s+(?:HC|HABEAS\s+CORPUS)
  | AG\.?\s*REG\.? | AGR\.?\s*REG\.?
  | AGINT | AGRG | AGREG | AGR | EDCL | EDV | ERESP | ARESP | RESP
  | RHC | RMS | ADI | ADC | ADPF | AIRR | RRAG | ARR | RR
  | RESPEL | RESPE | RCED | AIME | AIJE | RCL | HC | MS | MI | CC
  | APL | RSE | AI | MC | QO | RG | RO | PET | SLS | SS | RP
  | RE | AC | AP
)
"""

CLASS_TOKEN = rf"(?<![A-Z]){CLASS_ATOM}(?![A-Z])"

CLASS_CHAIN = re.compile(
    rf"(?P<class>(?:TST\s*[-–]\s*)?{CLASS_TOKEN}"
    rf"(?:(?:\s+(?:NO|NA|NOS|NAS|EM|AO|AOS|DO|DA|DOS|DAS)\s+|\s*[-–]\s*){CLASS_TOKEN})*)",
    FLAGS,
)

# O padrão CNJ aceita OCR apenas no segmento que deveria conter dígitos.
CNJ_NUMBER = re.compile(
    r"(?<![0-9OIL])(?P<number>[0-9OIL]{1,7}\s*-\s*[0-9OIL]\s*[0-9OIL]\s*\.\s*"
    r"[0-9OIL]{4}\s*\.\s*[0-9OIL]\s*\.\s*[0-9OIL]{2}\s*\.\s*[0-9OIL]{4})(?![0-9OIL])",
    FLAGS,
)
# Algumas superfícies eleitorais perdem pontos ou fundem os segmentos 6+UF.
# O formato continua ancorado em hífen, ano e cauda longa para não competir
# com datas ou números tradicionais.
FLEXIBLE_ELECTORAL_NUMBER = re.compile(
    r"(?<![0-9OIL])(?P<number>"
    r"[0-9OIL]{1,7}\s*-\s*(?:"
    r"[0-9OIL]{2}[0-9OIL]{4}[0-9OIL]{7,9}"
    r"|[0-9OIL]\s*[0-9OIL]\s*\.\s*[0-9OIL]{4}\s*\.\s*[0-9OIL]{1,3}\s*\.\s*[0-9OIL]{4}"
    r"|[0-9OIL]{1,4}(?:\s+[0-9OIL]{1,4}){3,}"
    r"))(?![0-9OIL])",
    FLAGS,
)
CNJ_WITHOUT_CHECK_DIGITS = re.compile(
    r"(?<![0-9OIL])(?P<number>[0-9OIL]{4,7}\s*\.\s*[0-9OIL]{4}\s*\.\s*"
    r"[0-9OIL]\s*\.\s*[0-9OIL]{2}\s*\.\s*[0-9OIL]{4})(?![0-9OIL])",
    FLAGS,
)
PARTIAL_HYPHEN_NUMBER = re.compile(r"(?<![0-9OIL])(?P<number>[0-9OIL]{5,7}\s*-\s*[0-9OIL]{2})(?![0-9OIL])", FLAGS)
DOTTED_NUMBER = re.compile(r"(?<![0-9OIL.])(?P<number>[0-9OIL]{1,3}(?:\s*\.\s*[0-9OIL]{3})+)(?![0-9OIL.])", FLAGS)
PLAIN_NUMBER = re.compile(r"(?<![0-9OIL])(?P<number>[0-9OIL]{3,9})(?![0-9OIL])", FLAGS)
SHORT_PREFIXED_NUMBER = re.compile(
    r"\bN(?:[O0º°.]|UMERO)(?![A-Z])\s*(?P<number>[0-9OIL]{1,2})(?![0-9OIL])",
    FLAGS,
)
NUMBER_PREFIX = re.compile(r"(?:\bN(?:[O0º°.]|UMERO)(?![A-Z])\s*)$", FLAGS)

VALID_UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
)
UF_ABBREVIATION = re.compile(rf"\b(?P<uf>{'|'.join(VALID_UFS)})\b", FLAGS)
UF_NAMES = {
    "AC": r"ACRE", "AL": r"ALAGOAS", "AP": r"AMAPA", "AM": r"AMAZONAS",
    "BA": r"BAHIA", "CE": r"CEARA", "DF": r"DISTRITO\s+FEDERAL",
    "ES": r"ESPIRITO\s+SANTO", "GO": r"GOIAS", "MA": r"MARANHAO",
    "MT": r"MATO\s+GROSSO", "MS": r"MATO\s+GROSSO\s+DO\s+SUL",
    "MG": r"MINAS(?:\s+GERAIS)?", "PA": r"PARA", "PB": r"PARAIBA",
    "PR": r"PARANA", "PE": r"PERNAMBUCO", "PI": r"PIAUI",
    "RJ": r"RIO\s+DE\s+JANEIRO", "RN": r"RIO\s+GRANDE\s+DO\s+NORTE",
    "RS": r"RIO\s+GRANDE\s+DO\s+SUL", "RO": r"RONDONIA",
    "RR": r"RORAIMA", "SC": r"SANTA\s+CATARINA", "SP": r"SAO\s+PAULO",
    "SE": r"SERGIPE", "TO": r"TOCANTINS",
}
UF_NAME_PATTERNS = {uf: re.compile(rf"\b{pattern}\b", FLAGS) for uf, pattern in UF_NAMES.items()}

JUDGMENT_YEAR = re.compile(
    r"\b(?:JULGAD[OA]|JULGAMENTO|PROFERID[OA])\s+EM\s+"
    r"(?:[0-3]?\d\s*[/.-]\s*[01]?\d\s*[/.-]\s*)?(?P<year>(?:19|20)\d{2})\b"
    r"|\bACORDAO\s+DE\s+(?P<acordao_year>(?:19|20)\d{2})\b",
    FLAGS,
)
ANY_YEAR = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b", FLAGS)
FULL_DATE = re.compile(r"\b[0-3]?\d\s*[/.-]\s*[01]?\d\s*[/.-]\s*(?:19|20)\d{2}\b", FLAGS)
MONTH_YEAR = re.compile(r"\b(?:0?[1-9]|1[0-2])\s*[-/]\s*(?:19|20)\d{2}\b", FLAGS)
MONTH_NAME_YEAR = re.compile(
    r"\b(?:JANEIRO|FEVEREIRO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|"
    r"OUTUBRO|NOVEMBRO|DEZEMBRO)\s+DE\s+(?:19|20)\d{2}\b",
    FLAGS,
)
ADMINISTRATIVE_NUMBER = re.compile(
    r"\b(?:19|20)\d{2}\s*[/⁄]\s*\d{6,8}\s*-\s*\d\b",
    FLAGS,
)
PUBLICATION = re.compile(r"\b(?:DJE|DJU|DJ|PJE)\b", FLAGS)

RELATOR_MARKER = re.compile(
    r"(?:\bREL(?:ATORA?|ATORIA)?\.?\s*(?:P\s*/\s*ACORDAO\s*)?(?:DO|DA|DE)?\s*"
    r"(?:MIN(?:ISTRO|ISTRA)?\.?\s*)?"
    r"|\b(?:SOB\s+A\s+|DE\s+|DA\s+)?RELATORIA\s+(?:DO|DA|DE)\s+"
    r"|\bDA\s+RESPONSABILIDADE\s+DE\s+"
    r"|\bDA\s+AUTORIA\s+DE\s+"
    r"|\bMIN(?:ISTRO|ISTRA)?\.?\s+)",
    FLAGS,
)
RELATOR_STOP = re.compile(
    r"(?=\s*(?:[,;()]|\b(?:PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|SEXTA|SETIMA|OITAVA|"
    r"TURMA|SECAO|PLENARIO|CORTE\s+ESPECIAL|ORGAO\s+JULGADOR|JULGAD[OA]|JULGAMENTO|"
    r"DJE|DJU|DJ|PJE|(?:19|20)\d{2})\b))",
    FLAGS,
)

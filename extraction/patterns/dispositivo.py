"""Padrões de dispositivos, separados por função sem impor ordem global."""

from __future__ import annotations

import re

from .common import FLAGS


# O marcador é propositalmente obrigatório: precisão de artigo é mais
# importante que tentar adivinhar o papel de todo número decimal no trecho.
ARTICLE_MARKER = re.compile(r"\bART(?:IGOS|IGO|S)?\.?\s*", FLAGS)
ARTICLE_VALUE = r"[0-9]{1,4}(?:\s*\.\s*[0-9]{3})?(?:\s*[-–]\s*[A-Z])?\s*(?:º|°|O)?"
FIRST_ARTICLE = re.compile(rf"^(?P<value>{ARTICLE_VALUE})(?![0-9])", FLAGS)
NEXT_ARTICLE = re.compile(
    rf"(?:[,;]|\bE\b|\bA\b|\bC\s*/\s*C\b)\s*(?:\bE\b\s*)?"
    rf"(?P<value>{ARTICLE_VALUE})(?![0-9])",
    FLAGS,
)

# Início de um diploma depois do artigo. Delimitar a região impede que o
# número/ano da lei seja consumido como mais um artigo.
DIPLOMA_BOUNDARY = re.compile(
    r"\b(?:(?:DA|DO|DE|NA|NO)\s+)?(?:LEI|LEI\s+COMPLEMENTAR|DECRETO(?:\s*-\s*LEI)?|"
    r"CODIGO|CONSTITUICAO|CONSOLIDACAO|CPC|CC|CLT|CF|CPP|CPM|CDC|LC)\b",
    FLAGS,
)

INCISO_EXPLICIT = re.compile(r"\bINC(?:ISO)?S?\.?\s+(?P<values>[IVXLCDM]+\b(?:\s*(?:,|E)\s*[IVXLCDM]+\b)*)", FLAGS)
INCISO_CONTEXTUAL = re.compile(r"(?:[,;]|\bE\b)\s*(?P<value>[IVXLCDM]+)\b(?=\s*(?:[,;]|E\b|DA\b|DO\b|DE\b|$))", FLAGS)
PARAGRAPH_NUMBER = re.compile(
    r"(?:§{1,2}|\bPARAGRAFOS?\b)\s*"
    r"(?P<values>[0-9]{1,3}\s*(?:º|°|O)?"
    r"(?:\s*(?:,|E|A)\s*[0-9]{1,3}\s*(?:º|°|O)?)*)",
    FLAGS,
)
PARAGRAPH_MARKER = re.compile(r"§{1,2}|\bPARAGRAFOS?\b", FLAGS)
PARAGRAPH_UNIQUE = re.compile(r"\b(?:PARAGRAFO\s+UNICO|P\.?\s*U\.?|CAPUT)\b", FLAGS)
ALINEA_EXPLICIT = re.compile(r"\bALINEAS?\s*[\"']?\s*(?P<values>[A-Z](?:\s*(?:,|E)\s*[A-Z])*)", FLAGS)
ALINEA_PAREN = re.compile(r"\(\s*(?P<value>[A-Z])\s*\)", FLAGS)


# Nomes/siglas. As fronteiras evitam que CC, CE ou CF casem em palavras.
DIPLOMA_NAMES: dict[str, tuple[re.Pattern[str], ...]] = {
    "CPC": (
        re.compile(r"\bCPC(?:\s*/\s*(?:19)?73|\s*/\s*20(?:15|16))?\b", FLAGS),
        re.compile(r"\bCODIGO\s+DE\s+PROCESSO\s+CIVIL\b", FLAGS),
    ),
    "CC": (
        re.compile(r"\bCC(?:\s*/\s*2002)?\b", FLAGS),
        re.compile(r"\bCODIGO\s+CIVIL(?:\s+DE\s+2002)?\b", FLAGS),
    ),
    "CLT": (
        re.compile(r"\bCLT\b", FLAGS),
        re.compile(r"\bCONSOLIDACAO\s+DAS\s+LEIS\s+DO\s+TRABALHO\b", FLAGS),
    ),
    "CF/88": (
        re.compile(r"\bCF(?:\s*/\s*(?:88|1988))?\b", FLAGS),
        re.compile(r"\bCONSTITUICAO(?:\s+DA\s+REPUBLICA(?:\s+FEDERATIVA\s+DO\s+BRASIL)?|\s+FEDERAL)?(?:\s+DE\s+1988)?\b", FLAGS),
        re.compile(r"\bCARTA\s+MAGNA\b", FLAGS),
    ),
    "CPP": (
        re.compile(r"\bCPP\b", FLAGS),
        re.compile(r"\bCODIGO\s+DE\s+PROCESSO\s+PENAL\b", FLAGS),
    ),
    "CPM": (
        re.compile(r"\bCPM\b", FLAGS),
        re.compile(r"\bCODIGO\s+PENAL\s+MILITAR\b", FLAGS),
    ),
    "CDC": (
        re.compile(r"\bCDC\b", FLAGS),
        re.compile(r"\bCODIGO\s+DE\s+DEFESA\s+DO\s+CONSUMIDOR\b", FLAGS),
    ),
    "CE": (
        re.compile(r"\bCODIGO\s+ELEITORAL\b", FLAGS),
    ),
    "LC64/90": (
        re.compile(r"\bLC\s*(?:N(?:[O0º°.]|UMERO)?\s*)?64\s*(?:[/\-]\s*(?:90|1990))?\b", FLAGS),
        re.compile(r"\bLEI\s+COMPLEMENTAR\s*(?:N(?:[O0º°.]|UMERO)?\s*)?64(?:\s*[/\-]\s*(?:90|1990))?\b", FLAGS),
    ),
}


# Identidades legislativas permitem resolver o diploma mesmo sem seu nome.
# Pontos e espaços dentro do número são tolerados; a validação final compara
# apenas os dígitos normalizados.
LAW_IDENTITY = re.compile(
    r"(?P<number>[0-9OIL]{1,3}(?:\s*\.\s*[0-9OIL]{3})+|[0-9OIL]{2,6})"
    r"\s*[/\-]\s*(?P<year>[0-9OIL]{2,4})",
    FLAGS,
)

# Forma oficial frequente no cadastro: "Lei 8.078, de 11 de setembro de
# 1990". O número da norma é suficiente para este vocabulário fechado; exigir
# que venha depois de LEI/DECRETO-LEI evita confundi-lo com artigo ou data.
NAMED_LAW_NUMBER = re.compile(
    r"\b(?:LEI(?:\s+COMPLEMENTAR)?|DECRETO\s*-?\s*LEI)\s*"
    r"(?:N(?:[O0º°.]|UMERO)?\s*)?"
    r"(?P<number>[0-9OIL]{1,3}(?:\s*\.\s*[0-9OIL]{3})+|[0-9OIL]{2,6})\b",
    FLAGS,
)

LAW_NUMBER_YEAR_TO_DIPLOMA = {
    ("13105", "2015"): "CPC",
    ("5869", "1973"): "CPC",
    ("10406", "2002"): "CC",
    ("5452", "1943"): "CLT",
    ("3689", "1941"): "CPP",
    ("1001", "1969"): "CPM",
    ("8078", "1990"): "CDC",
    ("4737", "1965"): "CE",
    ("64", "1990"): "LC64/90",
}

LAW_NUMBER_TO_DIPLOMA = {
    "13105": "CPC",
    "5869": "CPC",
    "10406": "CC",
    "5452": "CLT",
    "3689": "CPP",
    "1001": "CPM",
    "8078": "CDC",
    "4737": "CE",
    "64": "LC64/90",
}

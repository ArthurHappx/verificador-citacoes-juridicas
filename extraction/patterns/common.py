"""Fragmentos compartilhados pelos padrões jurídicos.

Os fragmentos ficam separados para tornar explícito quando um ponto aceita
separação vazia. ``SEP`` não deve ser usado como fronteira de siglas curtas.
"""

import re


WS = r"\s+"
OPT_WS = r"\s*"
SEP_CHARS = r"\s/\\|,.;\-_:()\[\]"
SEP = rf"[{SEP_CHARS}]*"
REQUIRED_SEP = rf"[{SEP_CHARS}]+"
CONNECTOR = r"(?:DE|DA|DO|DAS|DOS|EM|NA|NO|NAS|NOS|AO|AOS|E)"

# NÚMERO também pode chegar como NÚRNERO; Nº pode sofrer OCR O/0.
NUM_PREFIX = rf"(?:N(?:[O0º°.]|UM(?:E|(?:E|RN))RO)?{SEP})"

DIGITISH = r"[0-9OIL]"
YEAR = r"(?:18|19|20|21)[0-9]{2}"

FLAGS = re.IGNORECASE | re.VERBOSE


# Fonctions utilitaires pour fichiers (CSV, JSON)
import csv
import json
import re
from typing import Optional

def save_to_csv(data, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(data)

def save_to_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def str_to_hex(id_str: str) -> str:
    """
    Convertit une chaîne d'ID en format hexadécimal spécifique pour la génération d'URL.

    Args:
        id_str (str): L'identifiant à convertir.

    Returns:
        str: L'identifiant converti au format attendu.
    """
    hexreturn = ""
    for char in id_str:
        char_code = ord(char)
        hexreturn += str(99 - char_code)
        hexreturn += str(char_code)
    return hexreturn

# ---------------------------------------------------------------------------
# Conversion performances ----------------------------------------------------
# ---------------------------------------------------------------------------
# --- utils file_utils corrigé pour convert_time_to_seconds + tests ----------

# ---------------------------------------------------------------------------
# Conversion performances ----------------------------------------------------
# ---------------------------------------------------------------------------
# utils/file_utils.py – version corrigée
import re
from typing import Optional

_INVALID = {
    "DQ", "AB", "DNS", "DNF", "NP", "RET", "NC",
    "NCL", "NQ", "EL", "DSQ", "X"
}

# 14'09''95  – minutes' secondes'' centièmes
_TIME_RE   = re.compile(
    r"^(?:(?P<h>\d+)h)?(?P<min>\d+)'(?P<sec>\d{1,2})(?:'+(?P<cent>\d{1,2}))?$"
)
# 1:02:23.45 – heures:minutes:secondes.cent
_ROUTE_RE  = re.compile(
    r"^(?:(?P<h>\d+):)?(?P<min>\d{1,2}):(?P<sec>\d{1,2})(?:\.(?P<cent>\d{1,2}))?$"
)
# 9"58       – secondes"centièmes
_SECONDS_RE       = re.compile(r'^(?P<sec>\d+)"(?P<cent>\d{1,2})$')
# 9''58      – secondes''centièmes
_DOUBLE_PRIME_RE  = re.compile(r"^(?P<sec>\d+)''(?P<cent>\d{1,2})$")

def _to_seconds(h: Optional[str], min_: str, sec: str, cent: Optional[str]) -> float:
    total = int(min_) * 60 + int(sec)
    if h:
        total += int(h) * 3600
    if cent:
        total += int(cent) / 100
    return total

def convert_time_to_seconds(time_str: str) -> Optional[float]:
    if not isinstance(time_str, str):
        return None

    if any(bad in time_str for bad in _INVALID):
        return None

    # Nettoyage basique
    time_str = time_str.strip()

    # Si la valeur est entre parenthèses, on ne garde que l’intérieur
    m_par = re.search(r"\(([^)]+)\)", time_str)
    if m_par:
        time_str = m_par.group(1).strip()

    # ------------------------------------------------------------------
    # 1) Formats « secondes''centièmes » et « secondes"centièmes »
    # ------------------------------------------------------------------
    m_double_prime = _DOUBLE_PRIME_RE.fullmatch(time_str)
    if m_double_prime:
        return int(m_double_prime.group("sec")) + int(m_double_prime.group("cent")) / 100

    m_sec = _SECONDS_RE.fullmatch(time_str)
    if m_sec:
        return int(m_sec.group("sec")) + int(m_sec.group("cent")) / 100

    # ------------------------------------------------------------------
    # 2) Autres formats – on standardise puis on teste
    # ------------------------------------------------------------------
    time_str = time_str.replace("''", "'")   # ex : 14'09''95  → 14'09'95
    if time_str.endswith("'"):
        time_str = time_str[:-1]

    m_track = _TIME_RE.fullmatch(time_str)
    if m_track:
        return _to_seconds(
            m_track.group("h"),
            m_track.group("min"),
            m_track.group("sec"),
            m_track.group("cent")
        )

    m_route = _ROUTE_RE.fullmatch(time_str)
    if m_route:
        return _to_seconds(
            m_route.group("h"),
            m_route.group("min"),
            m_route.group("sec"),
            m_route.group("cent")
        )

    # ------------------------------------------------------------------
    # 3) Valeur numérique brute ?
    # ------------------------------------------------------------------
    try:
        return float(time_str)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Mini‑tests automatiques ----------------------------------------------------
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    TESTS = {
        "14'09''95": 849.95,
        "14'31''": 871.0,
        "13'12'' (13'05'')": 785.0,
        "13:13.66": 793.66,
        "13:28": 808.0,
        "1h02'23''": 3743.0,
        "1h02'27'' (1h02'27'')": 3747.0,
        "1:00:00": 3600.0,
        "59:59": 3599.0,
        "DNF": None,
        "9''58": 9.58,
        "65''58": 65.58,
        '9"58': 9.58,
        '65"58': 65.58,
    }

    for chrono, expected in TESTS.items():
        result = convert_time_to_seconds(chrono)
        assert (
            result == expected
            or (result is None and expected is None)
        ), f"Echec {chrono} → {result} au lieu de {expected}"
    print("✅ Tous les tests passent correctement.")

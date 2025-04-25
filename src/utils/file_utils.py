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
_INVALID = {"DQ", "AB", "DNS", "DNF", "NP", "RET", "NC", "NCL", "NQ", "EL", "DSQ", "X"}

_TIME_RE = re.compile(r"^(?P<min>\d+)'(?P<sec>\d{1,2})(?:'+(?P<cent>\d{1,2}))?$")
_ROUTE_RE = re.compile(r"^(?P<min>\d+):(?P<sec>\d{1,2})(?:\.(?P<cent>\d{1,2}))?$")


def _to_seconds(min_: str, sec: str, cent: Optional[str]) -> float:
    base = int(min_) * 60 + int(sec)
    if cent is not None and cent != "":
        base += int(cent) / 100
    return base


def convert_time_to_seconds(time_str):
    """Convertit un temps athlé en secondes (`float`).

    Gère les cas suivants :
    • "14'09''95"  piste (centièmes)
    • "14'31''"    piste (sans centièmes)
    • "13'12'' (13'05'')"  – on garde la valeur entre parenthèses
    • "13:13.66"    route WA (centièmes)
    • "13:28"       route WA (secondes uniquement)
    Si la chaîne contient l’un des mots `_INVALID`, renvoie None.
    """
    if not isinstance(time_str, str):
        return None

    # valeurs invalides
    if any(bad in time_str for bad in _INVALID):
        return None

    time_str = time_str.strip()

    # Prendre la valeur entre parenthèses si présente
    m_par = re.search(r"\(([^)]+)\)", time_str)
    if m_par:
        time_str = m_par.group(1).strip()

    time_str = time_str.replace("''", "'")  # normalise 2×'
    
    # si la chaîne se termine par un simple ', on le retire
    if time_str.endswith("'"):
        time_str = time_str[:-1]

    # Format piste  m'ss'cc  ou  m'ss'
    m_track = _TIME_RE.match(time_str)
    if m_track:
        return _to_seconds(m_track["min"], m_track["sec"], m_track["cent"])

    # Format route m:ss.cc  ou m:ss
    m_route = _ROUTE_RE.match(time_str)
    if m_route:
        cent = m_route["cent"] or "00"
        return _to_seconds(m_route["min"], m_route["sec"], cent)

    # Dernier recours : nombre brut
    try:
        return float(time_str)
    except ValueError:
        return None

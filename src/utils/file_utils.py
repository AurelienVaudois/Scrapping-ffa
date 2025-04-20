# Fonctions utilitaires pour fichiers (CSV, JSON)
import csv
import json

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

def convert_time_to_seconds(time_str):
    """
    Convertit une performance au format athlé (ex: 1'54''38) en secondes.
    Ignore les valeurs non numériques (DQ, AB, DNS, DNF, etc.).
    """
    if not isinstance(time_str, str):
        return None
    # Liste des valeurs à ignorer
    invalids = ['DQ', 'AB', 'DNS', 'DNF', 'NP', 'RET', 'NC', 'NCL', 'NQ', 'EL', 'DSQ', 'X']
    if any(invalid in time_str for invalid in invalids):
        return None
    import re
    time_str = time_str.strip()
    # Nettoyage : garde la valeur entre parenthèses si présente
    m = re.search(r"\(([^)]+)\)", time_str)
    if m:
        time_str = m.group(1)
    time_str = time_str.replace("''", "'")
    parts = re.split(r"'|\"", time_str)
    try:
        if len(parts) == 3:  # ex: 1'54'38
            min_, sec, cent = parts
            return int(min_) * 60 + int(sec) + int(cent) / 100
        elif len(parts) == 2:  # ex: 15'32
            min_, sec = parts
            return int(min_) * 60 + int(sec)
        elif len(parts) == 1 and ':' in parts[0]:  # ex: 1:54.38
            t = parts[0].split(':')
            if len(t) == 2:
                min_, sec = t
                return int(min_) * 60 + float(sec)
        elif len(parts) == 1:
            return float(parts[0])
    except Exception:
        return None
    return None

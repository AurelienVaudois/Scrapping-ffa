# Fonctions utilitaires HTTP
import requests
import json
from .file_utils import str_to_hex

def get_html(url, headers=None):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def search_athletes(search_term: str) -> list[dict]:
    """
    Recherche des athlètes et retourne leurs données, incluant hactseq et seq converti.

    Args:
        search_term (str): Terme de recherche pour trouver des athlètes.

    Returns:
        list[dict]: Liste de dictionnaires contenant les informations des athlètes.
    """
    cleaned_term = (search_term or "").strip()
    if len(cleaned_term) < 3:
        print("Search term must be at least 3 characters long.")
        return []

    search_candidates = [cleaned_term]
    parts = [part.strip() for part in cleaned_term.split() if part.strip()]
    if len(parts) > 1:
        search_candidates.extend([parts[0], parts[-1]])
        search_candidates.extend([p for p in sorted(parts, key=len, reverse=True) if len(p) >= 3])

    deduped_candidates = []
    seen_candidates = set()
    for candidate in search_candidates:
        key = candidate.lower()
        if len(candidate) >= 3 and key not in seen_candidates:
            deduped_candidates.append(candidate)
            seen_candidates.add(key)

    try:
        athletes = []
        seen_seq = set()

        for candidate in deduped_candidates:
            response = requests.get(
                "https://www.athle.fr/ajax/autocompletion.aspx",
                params={"mode": 1, "recherche": candidate},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            for item in data:
                seq = item.get('actseq', '')
                if seq in seen_seq:
                    continue

                athlete = {
                    'name': item.get('nom', ''),
                    'club': item.get('club', ''),
                    'sex': item.get('sexe', ''),
                    'seq': seq,
                }
                athletes.append(athlete)
                seen_seq.add(seq)

            if athletes:
                break

        return athletes

    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
        return []
    except json.JSONDecodeError:
        print("Error parsing JSON response")
        return []

def open_athlete_page(base: str = 'base', hactseq: str = 'hactseq', annee: int = 2025, espace: str = None, structure: str = None) -> str:
    """
    Génère l'URL de la page d'un athlète, similaire à bddThrowAthlete en JavaScript.

    Args:
        base (str): Paramètre base pour l'URL.
        hactseq (str): Code hactseq de l'athlète.
        annee (int): Année de la saison.
        espace (str, optional): Paramètre espace pour l'URL.
        structure (str, optional): Paramètre structure pour l'URL.

    Returns:
        str: URL complète de la page athlète.
    """
    url = f'https://bases.athle.fr/asp.net/athletes.aspx?base={base}&seq={str_to_hex(hactseq)}&saison={annee}'

    if espace:
        url += f'&espace={espace}'

    if structure:
        url += f'&structure={structure}'

    return url
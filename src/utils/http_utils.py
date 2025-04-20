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
    if len(search_term) < 3:
        print("Search term must be at least 3 characters long.")
        return []

    url = f"https://www.athle.fr/ajax/autocompletion.aspx?mode=1&recherche={search_term}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        athletes = []
        for item in data:
            hactseq = item.get('hactseq', '')
            athlete = {
                'hactseq': hactseq,
                'name': item.get('nom', ''),
                'club': item.get('club', ''),
                'sex': item.get('sexe', ''),
                'seq': str_to_hex(hactseq)
            }
            athletes.append(athlete)

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
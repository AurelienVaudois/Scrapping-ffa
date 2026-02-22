# Fonctions utilitaires HTTP
import requests
import json
import re
import unicodedata
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


def _normalize_text(value: str) -> str:
    value = str(value or "").strip().lower()
    value = "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", value)


def _extract_seq_from_ffa_profile(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/athletes/+([0-9]+)(?:/|$)", str(url))
    return match.group(1) if match else ""


def _score_athlete_candidate(query: str, athlete_name: str) -> int:
    q_norm = _normalize_text(query)
    n_norm = _normalize_text(athlete_name)
    if not q_norm or not n_norm:
        return 0

    tokens = [tok for tok in q_norm.split(" ") if tok]
    if not tokens:
        return 0

    score = 0
    if q_norm in n_norm:
        score += 100
    token_hits = sum(1 for tok in tokens if tok in n_norm)
    score += 20 * token_hits
    if token_hits == len(tokens):
        score += 60
    if len(tokens) >= 2 and tokens[-1] in n_norm:
        score += 15
    if len(tokens) >= 1 and tokens[0] in n_norm:
        score += 10
    return score


def search_athletes_lepistard(search_term: str, max_results: int = 50) -> list[dict]:
    """
    Recherche athlètes via l'endpoint Le Pistard et renvoie un format compatible app.
    """
    cleaned_term = (search_term or "").strip()
    if len(cleaned_term) < 3:
        return []

    tokens = [token for token in cleaned_term.split() if len(token) >= 3]
    if not tokens:
        return []

    candidates = []
    seen = set()

    search_keys = [tokens[-1]] + sorted(tokens, key=len, reverse=True)
    deduped_search_keys = []
    for key in search_keys:
        norm_key = _normalize_text(key)
        if norm_key not in seen:
            deduped_search_keys.append(key)
            seen.add(norm_key)

    endpoint = "https://lepistard.run/wp-admin/admin-ajax.php"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "origin": "https://lepistard.run",
        "referer": "https://lepistard.run/",
        "user-agent": "Mozilla/5.0",
    }

    for key in deduped_search_keys:
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data={
                    "action": "get_listing_names",
                    "name": key,
                    "table": "athlete",
                    "column": "nom",
                },
                timeout=4,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                continue

            for item in data:
                if not isinstance(item, dict):
                    continue

                seq = (
                    str(item.get("actseq") or "").strip()
                    or _extract_seq_from_ffa_profile(item.get("ffa_profile", ""))
                )
                first_name = str(item.get("prenom") or "").strip()
                last_name = str(item.get("nom") or "").strip()
                raw_name = str(item.get("name") or item.get("nom_complet") or "").strip()
                name = raw_name or " ".join(part for part in [first_name, last_name] if part).strip()
                if not name:
                    name = last_name or first_name

                key_id = seq or _normalize_text(name)
                if not key_id:
                    continue

                athlete = {
                    "name": name,
                    "club": str(item.get("club") or item.get("ligue") or "").strip(),
                    "sex": str(item.get("sexe") or "").strip(),
                    "seq": seq,
                    "source": "FFA_LEPISTARD",
                    "ffa_profile": item.get("ffa_profile"),
                }

                candidates.append(athlete)

            if candidates:
                break

        except (requests.exceptions.RequestException, json.JSONDecodeError):
            continue

    # déduplication finale
    deduped = []
    seen_keys = set()
    for athlete in candidates:
        unique_key = athlete.get("seq") or _normalize_text(athlete.get("name", ""))
        if not unique_key or unique_key in seen_keys:
            continue
        seen_keys.add(unique_key)
        deduped.append(athlete)

    scored = sorted(
        deduped,
        key=lambda athlete: _score_athlete_candidate(cleaned_term, athlete.get("name", "")),
        reverse=True,
    )
    return scored[:max_results]


def search_athletes_smart(search_term: str, max_results: int = 50) -> list[dict]:
    """
    Nouvelle stratégie de recherche:
    - FFA standard (fonction existante)
    - enrichissement Le Pistard pour les cas prénom + nom
    - tri/ranking par pertinence nom utilisateur
    """
    cleaned_term = (search_term or "").strip()
    if len(cleaned_term) < 3:
        return []

    base_results = search_athletes(cleaned_term)
    lp_results = search_athletes_lepistard(cleaned_term, max_results=max_results)

    merged = []
    seen = set()

    for athlete in base_results + lp_results:
        seq = str(athlete.get("seq") or "").strip()
        if not seq:
            seq = _extract_seq_from_ffa_profile(athlete.get("ffa_profile", ""))
            athlete["seq"] = seq

        unique_key = seq or _normalize_text(athlete.get("name", ""))
        if not unique_key or unique_key in seen:
            continue
        seen.add(unique_key)
        merged.append(athlete)

    ranked = sorted(
        merged,
        key=lambda athlete: _score_athlete_candidate(cleaned_term, athlete.get("name", "")),
        reverse=True,
    )

    return ranked[:max_results]

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
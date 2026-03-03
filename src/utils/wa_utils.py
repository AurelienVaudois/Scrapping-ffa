"""utils/wa_utils.py – Intégration World Athletics vers schéma Postgres
---------------------------------------------------------------------
Fonctions principales
• `search_wa_athletes()`  – suggestions fallback si FFA ≠ résultats
• `fetch_and_store_wa_results()` – scraping complet + insertion DB

Notes
-----
✓ Normalisation robuste des disciplines : on accepte de nombreuses
  variantes (casse, espaces, "Short Track", indoor flag) et on retombe
  sur les libellés utilisés par l’app Streamlit : « 800m »,
  « 800m Piste Courte », « 1 500m », « 3000m Steeple (91) », …
✓ Les performances au format WA « 1:21.67 » sont laissées telles quelles :
  la fonction `convert_time_to_seconds` du projet les gère déjà.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Callable
import pandas as pd
from sqlalchemy.engine import Engine
from datetime import datetime

from src.utils.scraping_wa import (
    search_athletes_by_name as _wa_search,
    get_athlete_results_by_name as _wa_results,
)


###############################################################################
# 1. Recherche d’athlètes (fallback) ##########################################
###############################################################################

def search_wa_athletes(search_term: str) -> List[Dict[str, Any]]:
    """Renvoie ≤5 suggestions World Athletics au même format que FFA."""
    if len(search_term) < 3:
        return []

    df = _wa_search(search_term)
    if (not isinstance(df, pd.DataFrame)) or (isinstance(df, pd.DataFrame) and df.empty):
        tokens = [t.strip() for t in search_term.split(" ") if len(t.strip()) >= 3]
        fallback_queries = []
        if tokens:
            fallback_queries.append(tokens[-1])
            fallback_queries.append(tokens[0])
        for fallback_query in fallback_queries:
            df = _wa_search(fallback_query)
            if isinstance(df, pd.DataFrame) and not df.empty:
                break

    if not isinstance(df, pd.DataFrame) or df.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, row in df.head(5).iterrows():
        aa_id = int(row["aaAthleteId"])
        out.append(
            {
                "hactseq": None,
                "name": f"{row['givenName']} {row['familyName']}",
                "club": row.get("country", "WA"),
                "sex": row.get("gender", ""),
                "seq": f"WA_{aa_id}",
                "source": "WA",
                "aa_id": aa_id,
            }
        )
    return out

###############################################################################
# 2. Normalisation des disciplines ###########################################
###############################################################################
# Dictionnaire case‑insensitive (clé stockée en minuscule) -------------------
_DISCIPLINE_MAP_CI = {
    
    "100 metres": "100m",
    '200 metres': '200m', 
    '200 metres short track': '200m Piste Courte',
    '400 metres': '400m', 
    '400 metres short track': '400m Piste Courte',
    
    "800 metres": "800m",
    "800 metres short track": "800m Piste Courte",
    "1500 metres": "1 500m",
    "1500 metres short track": "1 500m Piste Courte",
    "3000 metres steeplechase": "3000m Steeple (91)",

    "3000 metres": "3 000m",
    "3000 metres short track": "3 000m Piste Courte",
    
    "5000 metres": "5 000m",
    "5000 metres short track": "5 000m Piste Courte",
    "5 kilometres road": "5 Km Route",
    
    "10,000 metres": "10 000m",           
    "10 kilometres road": "10 Km Route",  
    
    "half marathon": "1/2 Marathon",
    
    
}


def _map_discipline(raw_name: str, indoor: bool) -> str:
    key = str(raw_name).strip().lower()
    base = _DISCIPLINE_MAP_CI.get(key, raw_name)
    return base

###############################################################################
# 3. Transformation WA → schéma `results` #####################################
###############################################################################
_EXPECTED_COLS = [
    "seq",
    "club",
    "date",
    "epreuve",
    "tour",
    "pl",
    "perf",
    "vt",
    "niv",
    "pts",
    "ville",
    "annee",
]

_COL_RENAME = {
    "date": "date",
    "mark": "perf",
    "wind": "vt",
    "place": "pl",
    "venue": "ville",
    "category": "niv",
    "resultScore": "pts",
}


def _prepare_results_df(raw: pd.DataFrame, seq: str) -> pd.DataFrame:
    if raw.empty:
        return raw

    df = raw.copy()

    # Discipline : si colonne absente / NaN → on tente disciplineCode
    def _disc(row):
        d = row.get("discipline")
        return _map_discipline(d, bool(row.get("indoor")))

    df["epreuve"] = df.apply(_disc, axis=1)

    # Renommage des autres colonnes utiles
    df = df.rename(columns=_COL_RENAME)

    # Colonnes absentes → None
    for col in ["club", "tour", "pl", "vt", "niv", "pts", "ville"]:
        if col not in df.columns:
            df[col] = None

    # Dates + année
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["annee"] = df["date"].dt.year

    df["seq"] = seq

    # Sélection finale & nettoyage strings
    df = df[_EXPECTED_COLS].copy()
    str_cols = [c for c in _EXPECTED_COLS if c not in ("date", "annee")]
    df[str_cols] = df[str_cols].applymap(
        lambda x: str(x).strip() if x is not None else None
    )

    return df.drop_duplicates(subset=_EXPECTED_COLS)

###############################################################################
# 4. Scraping + insertion DB ##################################################
###############################################################################

from src.utils.athlete_utils import save_athlete_info, save_results_to_postgres
from src.utils.scraping_wa import search_athletes_by_name, get_athlete_results_by_name


def _pick_best_wa_candidate(df_search: pd.DataFrame, name_query: str, athlete_hint: Optional[dict]) -> pd.Series:
    if df_search.empty:
        return pd.Series(dtype="object")

    given_series = df_search["givenName"] if "givenName" in df_search.columns else pd.Series([""] * len(df_search))
    family_series = df_search["familyName"] if "familyName" in df_search.columns else pd.Series([""] * len(df_search))
    country_series = df_search["country"] if "country" in df_search.columns else pd.Series([""] * len(df_search))
    full_names = (given_series.fillna("") + " " + family_series.fillna(""))

    if athlete_hint:
        hint_seq = str(athlete_hint.get("seq", "")).strip()
        hint_name = str(athlete_hint.get("name", "")).strip().lower()
        hint_country = str(athlete_hint.get("club", "")).strip().lower()

        if hint_seq.startswith("WA_"):
            try:
                hint_aa_id = int(hint_seq.replace("WA_", ""))
                exact_id = df_search[df_search["aaAthleteId"].astype(str) == str(hint_aa_id)]
                if not exact_id.empty:
                    return exact_id.iloc[0]
            except Exception:
                pass

        if hint_name:
            exact_name = df_search[full_names.str.strip().str.lower() == hint_name]
            if not exact_name.empty:
                if hint_country:
                    country_match = exact_name[country_series.loc[exact_name.index].fillna("").str.strip().str.lower() == hint_country]
                    if not country_match.empty:
                        return country_match.iloc[0]
                return exact_name.iloc[0]

    query_norm = name_query.strip().lower()
    exact_query = df_search[full_names.str.strip().str.lower() == query_norm]
    if not exact_query.empty:
        return exact_query.iloc[0]

    return df_search.iloc[0]


def fetch_and_store_wa_results(
    name_query: str,
    engine,
    athlete_hint: Optional[dict] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
):
    """
    Cherche un athlète sur WA, récupère ses résultats et sauvegarde tout en base.
    """
    if progress_callback:
        progress_callback("Recherche du profil World Athletics…")

    # 1. Recherche de l'athlète
    df_search = search_athletes_by_name(name_query)
    
    if df_search.empty:
        print(f"Aucun athlète trouvé sur WA pour : {name_query}")
        return pd.DataFrame() # Retourne un DF vide au lieu de None pour éviter le crash

    athlete = _pick_best_wa_candidate(df_search, name_query, athlete_hint)
    if athlete.empty:
        return pd.DataFrame()
    
    # 1. L'ID s'appelle 'aaAthleteId' et on ajoute le préfixe WA_
    wa_id = f"WA_{athlete['aaAthleteId']}"
    
    # 2. Le nom est séparé en 'givenName' et 'familyName'
    full_name = f"{athlete['givenName']} {athlete['familyName']}"
    
    # 3. Le pays et le sexe
    country = athlete.get('country', 'WA')
    
    # Correction du sexe (Men -> M)
    raw_sex = athlete.get('gender', '')
    if str(raw_sex).lower() == 'men':
        sex = 'M'
    elif str(raw_sex).lower() == 'women':
        sex = 'F'
    else:
        sex = str(raw_sex)[0].upper() if raw_sex else ''
    
    # Gestion de la date de naissance
    birth_date_raw = athlete.get('birthDate')
    birth_year = None

    if birth_date_raw:
        try:
            birth_date_raw = str(birth_date_raw).strip()
            parts = birth_date_raw.split()
            if parts:
                possible_year = parts[-1]
                if len(possible_year) == 4 and possible_year.isdigit():
                    birth_year = int(possible_year)
        except Exception:
            pass

    print(f"Sauvegarde infos athlète WA : {full_name} ({birth_date_raw})")

    # 2. Sauvegarde des infos athlète
    if progress_callback:
        progress_callback("Sauvegarde des informations athlète…")

    save_athlete_info(
        seq=wa_id,
        name=full_name,
        club=country,
        sex=sex,
        engine=engine,
        birth_date_raw=birth_date_raw,
        birth_year=birth_year
    )

    # 3. Récupération et sauvegarde des résultats
    current_year = datetime.now().year
    start_year = max(1990, current_year - 20)
    if birth_year is not None:
        start_year = max(1990, birth_year + 13)

    if progress_callback:
        progress_callback("Scraping des performances WA…")

    raw_df = get_athlete_results_by_name(
        full_name,
        start_year=start_year,
        end_year=current_year,
        use_threading=True,
        max_workers=6,
        max_total_seconds=18,
    )
    
    # Standardisation
    df_clean = _prepare_results_df(raw_df, wa_id)

    if not df_clean.empty:
        if progress_callback:
            progress_callback("Insertion des résultats en base…")
        save_results_to_postgres(df_clean, wa_id, engine)
    
    return df_clean # <--- C'est ce return qui manquait !

# ─── helper lecture-seule : DataFrame WA sans écriture DB ──────────────────
def fetch_wa_results_df(name: str) -> pd.DataFrame:
    """
    Scrape World Athletics → renvoie un DataFrame normalisé *sans* rien écrire
    dans la base.  Aucune ligne dupliquée n’est présente.

    Parameters
    ----------
    name : str
        Nom (ou slug) de l’athlète tel qu’affiché sur worldathletics.org.

    Returns
    -------
    pd.DataFrame
        Colonnes conformes au schéma `results` :
        seq, club, date, epreuve, tour, pl, perf, vt, niv, pts, ville, annee
        (DataFrame vide si rien trouvé ou si WA renvoie un message d’info/erreur).
    """
    # 1. Scraping brut via le helper existant : _wa_results(name, …)
    raw_df = _wa_results(name, use_threading=True)
    if raw_df.empty or "info" in raw_df.columns:
        return pd.DataFrame()

    # 2. Construction de l’identifiant unique « WA_<athlete_id> »"
    aa_id = int(raw_df["athlete_id"].iloc[0])
    seq   = f"WA_{aa_id}"

    # 3. Nettoyage / mapping vers le schéma Postgres déjà défini
    return _prepare_results_df(raw_df, seq)

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

from typing import List, Dict, Any
import pandas as pd
from sqlalchemy.engine import Engine

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

def fetch_and_store_wa_results(name: str, engine: Engine):
    """Scrape World Athletics, normalise les données puis insère dans Postgres."""
    raw_df = _wa_results(name, use_threading=True)
    if raw_df.empty or "info" in raw_df.columns:
        return pd.DataFrame()

    aa_id = int(raw_df["athlete_id"].iloc[0])
    seq = f"WA_{aa_id}"

    final_df = _prepare_results_df(raw_df, seq)
    if final_df.empty:
        return pd.DataFrame()

    from src.utils.athlete_utils import save_athlete_info, save_results_to_postgres

    save_athlete_info(seq, name, club="", sex="", engine=engine)
    save_results_to_postgres(final_df, seq, engine)

    return final_df

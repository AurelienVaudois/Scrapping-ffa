############################################################
# ffa_fast.py – Scraper FFA encore plus rapide ✔️          #
############################################################
from __future__ import annotations

import asyncio
from typing import List, Optional, Dict, Any

import httpx
import pandas as pd
import requests_cache
from selectolax.parser import HTMLParser

# ---------------------------------------------------------------------------
# Config réseau + cache ------------------------------------------------------
# ---------------------------------------------------------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (fast-ffa/2.1)"}
requests_cache.install_cache("ffa_http_cache", expire_after=86_400)

# ---------------------------------------------------------------------------
# Parsing utilitaires --------------------------------------------------------
# ---------------------------------------------------------------------------
_COLS = [
    "Club",
    "Date",
    "Epreuve",
    "Tour",
    "Pl.",
    "Perf.",
    "Vt.",
    "Niv.",
    "Pts",
    "Ville",
]


def _parse_years(html: str) -> List[str]:
    """Extrait la liste des saisons disponibles depuis le select HTML."""
    tree = HTMLParser(html)
    years: List[str] = []
    for opt in tree.css("select.selectMain option"):
        val = opt.attributes.get("value") or ""
        if "saison=" in val:
            years.append(val.split("saison=")[-1])
    return years


# --- table parsing sans pandas.read_html ------------------------------------

def _parse_results_table(html: str) -> Optional[List[Dict[str, Any]]]:
    tree = HTMLParser(html)
    tables = tree.css("table")
    if len(tables) <= 3:
        return None  # layout inattendu

    rows = tables[3].css("tr")
    if len(rows) <= 1:
        return None  # table vide

    data: List[Dict[str, Any]] = []
    for r in rows[1:]:  # skip header row
        cells = [c.text(strip=True) for c in r.css("td")]
        if len(cells) < len(_COLS):
            continue
        data.append(dict(zip(_COLS, cells)))
    return data

# ---------------------------------------------------------------------------
# Requêtes HTTP asynchrones ---------------------------------------------------
# ---------------------------------------------------------------------------
async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text


async def _fetch_year_results(client: httpx.AsyncClient, seq: str, year: str) -> Optional[pd.DataFrame]:
    url = f"https://bases.athle.fr/asp.net/athletes.aspx?base=resultats&seq={seq}&saison={year}"
    html = await _fetch(client, url)
    records = _parse_results_table(html)
    if records:
        df = pd.DataFrame.from_records(records)
        df["Annee"] = year
        return df
    return None


async def _gather_years(seq: str) -> List[str]:
    url = f"https://bases.athle.fr/asp.net/athletes.aspx?base=bilans&seq={seq}"
    async with httpx.AsyncClient() as client:
        html = await _fetch(client, url)
    return _parse_years(html)


async def _async_collect(seq: str) -> pd.DataFrame:
    years = await _gather_years(seq)
    if not years:
        return pd.DataFrame()

    async with httpx.AsyncClient(http2=True, headers=HEADERS) as client:
        dfs = await asyncio.gather(*[_fetch_year_results(client, seq, y) for y in years])

    combined = pd.concat([d for d in dfs if d is not None], ignore_index=True)
    if not combined.empty:
        combined["seq"] = seq
    return combined

# ---------------------------------------------------------------------------
# API publique synchronisée ---------------------------------------------------
# ---------------------------------------------------------------------------

def get_all_results_fast(seq: str) -> pd.DataFrame:
    """Collecte toutes les saisons pour l'athlète `seq` (async → sync)."""
    return asyncio.run(_async_collect(seq))

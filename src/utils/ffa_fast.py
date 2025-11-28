import asyncio
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from typing import List, Optional

# Configuration
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

async def fetch_url(client, url):
    try:
        # Important: follow_redirects=True pour gérer les redirections éventuelles
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

async def get_athlete_years_async(client, seq: str) -> List[str]:
    """Récupère les années disponibles (version async)"""
    # On utilise la même URL que la version synchrone qui fonctionne
    url = f"https://www.athle.fr/athletes/{seq}/resultats"
    html = await fetch_url(client, url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    header = soup.find(lambda t: t.name in ("h2", "h3") and "Résultats par année" in t.get_text())
    
    years = []
    if header:
        for sib in header.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            for txt in sib.stripped_strings:
                if txt.isdigit() and len(txt) == 4:
                    y = int(txt)
                    if 2000 <= y <= datetime.now().year:
                        s = str(y)
                        if s not in years:
                            years.append(s)
    return years

async def get_athlete_results_async(client, seq: str, year: str) -> Optional[pd.DataFrame]:
    """Récupère les résultats d'une année (version async)"""
    url = f"https://www.athle.fr/ajax/fiche-athlete-resultats.aspx?seq={seq}&annee={year}"
    html = await fetch_url(client, url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        # Nettoyage comme dans la version synchrone
        for t in soup.select(".detail-inner-table"):
            t.decompose()

        thead = soup.select_one("thead")
        tbody = soup.select_one("tbody")
        if not thead or not tbody:
            return None

        headers = [th.get_text(strip=True) for th in thead.select("tr > th")]
        if headers and not headers[-1]:
            headers = headers[:-1]

        rows = []
        for tr in tbody.find_all("tr", recursive=False):
            classes = tr.get("class", [])
            if any(c.startswith("detail-row") for c in classes):
                continue

            tds = tr.find_all("td", recursive=False)
            if tds and "desktop-tablet-d-none" in tds[-1].get("class", []):
                tds = tds[:-1]

            cells = []
            for i, td in enumerate(tds):
                if i == len(headers) - 1:
                    a = td.find("a")
                    cells.append(a.get_text(strip=True) if a else td.get_text(" ", strip=True))
                else:
                    cells.append(td.get_text(" ", strip=True))

            cells = cells[:len(headers)]
            rows.append(cells)

        df = pd.DataFrame(rows, columns=headers)
        df['Annee'] = year
        return df
    except Exception as e:
        print(f"Error parsing results for {year}: {e}")
        return None

async def get_all_results_async(seq: str) -> pd.DataFrame:
    """Orchestre les appels asynchrones"""
    # On désactive http2=True car certains serveurs/proxies le gèrent mal et cela peut causer des échecs silencieux
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        # 1. Récupérer les années
        years = await get_athlete_years_async(client, seq)
        if not years:
            # Fallback: si pas d'années trouvées, on renvoie vide
            return pd.DataFrame(columns=['seq', 'Club', 'Date', 'Epreuve', 'Tour', 'Pl.', 'Perf.', 'Vt.', 'Niv.', 'Pts', 'Ville', 'Annee'])
        
        # 2. Lancer toutes les requêtes d'années en PARALLÈLE
        tasks = [get_athlete_results_async(client, seq, year) for year in years]
        results = await asyncio.gather(*tasks)
        
        # 3. Assembler les résultats
        dfs = [df for df in results if df is not None]
        
        if dfs:
            final_df = pd.concat(dfs, ignore_index=True)
            final_df['seq'] = seq
            return final_df
        else:
            return pd.DataFrame(columns=['seq', 'Club', 'Date', 'Epreuve', 'Tour', 'Pl.', 'Perf.', 'Vt.', 'Niv.', 'Pts', 'Ville', 'Annee'])

def get_all_results_fast(seq: str) -> pd.DataFrame:
    """
    Fonction principale à appeler depuis votre code.
    Remplace get_all_athlete_results.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            raise RuntimeError(
                "Vous êtes dans un environnement asynchrone (Jupyter, etc.). "
                "Utilisez 'await get_all_results_async(seq)' ou installez 'nest_asyncio'."
            )
            
    return asyncio.run(get_all_results_async(seq))

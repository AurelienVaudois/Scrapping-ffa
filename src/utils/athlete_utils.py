import os
import re  # <--- Ajout de re
from datetime import datetime
from sqlalchemy import create_engine, text
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from typing import List, Optional, Tuple

from psycopg2.extras import execute_values
from sqlalchemy.engine import Engine
from contextlib import closing

load_dotenv()
db_url = os.getenv("DB_URL")
engine = create_engine(db_url)


def get_athlete_years(seq: str) -> List[str]:
    """
    Récupère la liste des années disponibles pour un athlète à partir de la page 'bilans'.
    Args:
        seq (str): Identifiant seq de l'athlète.
    Returns:
        List[str]: Liste des années (str).
    """
    url = f"https://www.athle.fr/athletes/{seq}/resultats"
    response = requests.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    # Trouver le titre "Résultats par année"
    header = soup.find(lambda t: t.name in ("h2", "h3") and "Résultats par année" in t.get_text())

    years = []
    if header:
        # On lit les éléments suivants jusqu'à la prochaine section
        for sib in header.find_next_siblings():
            # Si on tombe sur un autre titre, on arrête
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

def get_athlete_results(seq: str, year: str) -> Optional[pd.DataFrame]:
    """
    Récupère les résultats d'un athlète pour une année donnée.
    Args:
        seq (str): Identifiant seq de l'athlète.
        year (str): Année à récupérer.
    Returns:
        Optional[pd.DataFrame]: DataFrame des résultats ou None si erreur.
    """
    
    url = f"https://www.athle.fr/ajax/fiche-athlete-resultats.aspx?seq={seq}&annee={year}"
    r = requests.get(url)
    r.raise_for_status()
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        # Supprimer les sous-tableaux "detail-inner-table"
        for t in soup.select(".detail-inner-table"):
            t.decompose()

        thead = soup.select_one("thead")
        tbody = soup.select_one("tbody")
        if not thead or not tbody:
            raise ValueError("thead ou tbody introuvable")

        headers = [th.get_text(strip=True) for th in thead.select("tr > th")]
        if headers and not headers[-1]:
            headers = headers[:-1]

        rows = []
        # On parcourt uniquement les enfants directs de tbody
        for tr in tbody.find_all("tr", recursive=False):
            classes = tr.get("class", [])
            if any(c.startswith("detail-row") for c in classes):
                continue

            # <td> de premier niveau uniquement
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
        print(f"Erreur lors de la récupération des résultats pour {year}: {e}")
    return None

def get_all_athlete_results(seq: str) -> pd.DataFrame:
    """
    Récupère et concatène tous les résultats disponibles pour un athlète.
    Ajoute explicitement la colonne seq pour garantir l'unicité et éviter les erreurs lors du drop_duplicates.
    Args:
        seq (str): Identifiant seq de l'athlète.
    Returns:
        pd.DataFrame: DataFrame concaténé de tous les résultats.
    """
    years = get_athlete_years(seq)
    all_results = []
    for year in years:
        df = get_athlete_results(seq, year)
        if df is not None:
            all_results.append(df)
    if all_results:
        df = pd.concat(all_results, ignore_index=True)
        df['seq'] = seq  # Ajoute la colonne seq pour chaque ligne
        return df
    else:
        return pd.DataFrame(columns=['seq', 'Club', 'Date', 'Epreuve', 'Tour', 'Pl.', 'Perf.', 'Vt.', 'Niv.', 'Pts', 'Ville', 'Annee'])


def get_athlete_birth_info(seq: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Scrape la page de l'athlète pour récupérer sa date de naissance brute et son année.
    Gère les formats "Né(e) le : JJ/MM/AAAA" et "Né(e) en : AAAA".
    
    Returns:
        Tuple[str, int]: (date_brute, année) ou (None, None)
    """
    url = f"https://www.athle.fr/athletes/{seq}/resultats"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return None, None
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Recherche du label "Né(e)"
        label_span = soup.find('span', string=lambda t: t and "Né(e)" in t)
        
        if label_span:
            # Récupération du texte suivant (soit sibling direct, soit dans un <b>)
            raw_text = label_span.next_sibling
            if not raw_text or not raw_text.strip():
                next_tag = label_span.find_next_sibling('b')
                if next_tag:
                    raw_text = next_tag.text
            
            if raw_text:
                full_text = raw_text.strip()
                # On prend le premier "mot" qui est généralement la date (ex: "19/07/1993" ou "1998")
                # On ignore ce qui suit (ex: "à Paris")
                date_part = full_text.split(' ')[0]
                
                # Extraction de l'année via Regex (cherche 4 chiffres consécutifs)
                match_year = re.search(r'(\d{4})', date_part)
                year = int(match_year.group(1)) if match_year else None
                
                return date_part, year
                
    except Exception as e:
        print(f"Erreur scraping date naissance pour {seq}: {e}")
        
    return None, None


def save_athlete_info(seq: str, name: str, club: str, sex: str, engine, 
                     birth_date_raw: str = None, birth_year: int = None, 
                     table_name: str = 'athletes'):
    """
    Insère ou met à jour les informations d'un athlète, y compris la date de naissance.
    """
    now = datetime.utcnow()
    
    # Si les infos de naissance ne sont pas fournies, on essaie de les scraper à la volée
    if birth_date_raw is None or birth_year is None:
        scraped_raw, scraped_year = get_athlete_birth_info(seq)
        # On ne remplace que si on a trouvé quelque chose, sinon on garde None
        if scraped_raw: birth_date_raw = scraped_raw
        if scraped_year: birth_year = scraped_year

    with engine.begin() as conn:
        conn.execute(text(f'''
            INSERT INTO {table_name} (seq, name, club, sex, birth_date_raw, birth_year, last_update)
            VALUES (:seq, :name, :club, :sex, :birth_date_raw, :birth_year, :last_update)
            ON CONFLICT (seq) DO UPDATE SET
                name=EXCLUDED.name,
                club=EXCLUDED.club,
                sex=EXCLUDED.sex,
                birth_date_raw=COALESCE(EXCLUDED.birth_date_raw, athletes.birth_date_raw),
                birth_year=COALESCE(EXCLUDED.birth_year, athletes.birth_year),
                last_update=EXCLUDED.last_update
        '''), dict(
            seq=seq, 
            name=name, 
            club=club, 
            sex=sex, 
            birth_date_raw=birth_date_raw, 
            birth_year=birth_year, 
            last_update=now
        ))


def clean_and_prepare_results_df(df, seq):
    """
    Nettoie et prépare le DataFrame pour insertion PostgreSQL :
    - mapping des colonnes
    - reconstitution de la date complète
    - conversion des types
    - gestion des NaN/NaT
    """
    col_map = {
        'Club': 'club', 'Date': 'date', 'Epreuve': 'epreuve', 'Tour': 'tour', 'Place': 'pl',
        'Performance': 'perf', 'Vent': 'vt', 'Niveau': 'niv', 'Points': 'pts', 'Lieu': 'ville', 'Annee': 'annee', 'seq': 'seq'
    }
    
    mois_map = {
    "Janv": "Jan",
    "Fév": "Feb", "Fev": "Feb",
    "Mars": "Mar",
    "Avr": "Apr",
    "Mai": "May",
    "Juin": "Jun",
    "Juil": "Jul",
    "Août": "Aug", "Aout": "Aug",
    "Sept": "Sep",
    "Oct": "Oct",
    "Nov": "Nov",
    "Déc": "Dec", "Dec": "Dec"
}
    
    df = df.rename(columns=col_map)
    # df['seq'] = seq
    # Reconstitue la date complète avant conversion
    if 'date' in df.columns and 'annee' in df.columns:
        
        df["date_clean"] = (df["date"].str.replace(r"\.", "", regex=True).replace(mois_map, regex=True))
        df["date"] = pd.to_datetime(df["date_clean"] + " " + df["annee"].astype(str),dayfirst=True,errors='coerce')
        df = df.dropna(subset=['date'])
        # df = df[df['date'].notna()].copy()       # on ne garde que les dates valides
        # df['date'] = df['date'].astype(object)   # pour autoriser les None  
        df = df.drop(columns=['date_clean'])
    # Nettoyage des types et valeurs manquantes
    for col in ['club', 'epreuve', 'tour', 'pl', 'perf', 'vt', 'niv', 'pts', 'ville']:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    df = df.where(pd.notnull(df), None)
    return df


# def save_results_to_postgres(df: pd.DataFrame, seq: str, engine, table_name: str = 'results') -> int:
#     """
#     Insère les résultats dans une base PostgreSQL en évitant les doublons et en ajoutant la colonne seq.
#     Utilise une insertion batch rapide avec to_sql.
#     """
#     # On ne garde que les colonnes attendues par la table
#     expected_cols = ['seq', 'club', 'date', 'epreuve', 'tour', 'pl', 'perf', 'vt', 'niv', 'pts', 'ville', 'annee']
#     df = df[[col for col in expected_cols if col in df.columns]]
#     # Suppression des doublons
#     df = df.drop_duplicates(subset=expected_cols).reset_index(drop=True)

#     # Insertion batch
#     try:
#         df.to_sql(table_name, engine, if_exists='append', index=False, method='multi')
#         return len(df)
#     except Exception as e:
#         print(f"Erreur lors de l'insertion batch : {e}")
#         return 0

def save_results_to_postgres(
    df: pd.DataFrame,
    seq: str,
    engine: Engine,
    table: str = "results",
    batch_size: int = 1000,
) -> int:
    """
    Insère les résultats d'un athlète dans Postgres sans créer de doublons.

    Paramètres
    ----------
    df : DataFrame déjà nettoyé et conforme au schéma `results`
    seq : identifiant de l'athlète
    engine : SQLAlchemy Engine vers la base Postgres
    table : nom de la table cible (défaut « results »)
    batch_size : taille des paquets pour execute_values

    Retour
    ------
    int : nombre de nouvelles lignes réellement insérées
    """
    if df.empty:
        return 0

    # ------------------------------------------------------------------ build
    columns = list(df.columns)
    values  = [tuple(row) for row in df.to_numpy()]

    placeholders = ",".join(columns)
    insert_sql = f"""
        INSERT INTO {table} ({placeholders})
        VALUES %s
        ON CONFLICT (seq, date, epreuve, tour, perf) DO NOTHING
        RETURNING 1
    """

    # ─── NEW ─── remplacement du bloc connexion/curseur ──────────────────
    raw_conn = engine.raw_connection()          # ← plus de « with »
    try:
        with closing(raw_conn.cursor()) as cur:
            execute_values(cur, insert_sql, values, page_size=batch_size)
        raw_conn.commit()
    finally:
        raw_conn.close()
    return len(values)
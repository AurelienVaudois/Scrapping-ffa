import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
from typing import List, Optional


def get_athlete_years(seq: str) -> List[str]:
    """
    Récupère la liste des années disponibles pour un athlète à partir de la page 'bilans'.
    Args:
        seq (str): Identifiant seq de l'athlète.
    Returns:
        List[str]: Liste des années (str).
    """
    url = f"https://bases.athle.fr/asp.net/athletes.aspx?base=bilans&seq={seq}"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    select = soup.find('select', class_='selectMain')
    years = []
    if select:
        for option in select.find_all('option'):
            if 'saison=' in option.get('value', ''):
                # Extrait l'année de l'URL
                year = option.get('value').split('saison=')[-1]
                if year.isdigit():
                    years.append(year)
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
    url = f"https://bases.athle.fr/asp.net/athletes.aspx?base=resultats&seq={seq}&saison={year}"
    try:
        tables = pd.read_html(url, header=0)
        # La table des résultats est généralement la 4ème (index 3)
        if len(tables) > 3:
            df = tables[3]
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


def save_athlete_info(seq: str, name: str, club: str, sex: str, db_path: str, table_name: str = 'athletes'):
    """
    Insère ou met à jour les informations d'un athlète dans la table athletes.
    Args:
        seq (str): Identifiant unique de l'athlète.
        name (str): Nom de l'athlète.
        club (str): Club de l'athlète.
        sex (str): Sexe de l'athlète.
        db_path (str): Chemin vers la base SQLite.
        table_name (str): Nom de la table athletes.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            seq TEXT PRIMARY KEY,
            name TEXT,
            club TEXT,
            sex TEXT
        )
    ''')
    cursor.execute(f'''
        INSERT INTO {table_name} (seq, name, club, sex)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(seq) DO UPDATE SET name=excluded.name, club=excluded.club, sex=excluded.sex
    ''', (seq, name, club, sex))
    conn.commit()
    conn.close()


def preprocess_results_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie le DataFrame des résultats :
    - Supprime les doublons sur les colonnes clés
    """
    # Colonnes clés pour l'unicité
    key_cols = ['seq', 'Club', 'Date', 'Epreuve', 'Tour', 'Pl.', 'Perf.', 'Vt.', 'Niv.', 'Pts', 'Ville', 'Annee']
    for col in key_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    # Supprime les doublons
    df = df.drop_duplicates(subset=key_cols).reset_index(drop=True)
    return df


def save_results_to_sqlite(df: pd.DataFrame, seq: str, db_path: str, table_name: str = 'results') -> int:
    """
    Insère les résultats dans une base SQLite en évitant les doublons et en ajoutant la colonne seq.
    Retourne le nombre de nouveaux résultats insérés.
    """
    df = preprocess_results_df(df)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            seq TEXT,
            Club TEXT, Date TEXT, Epreuve TEXT, Tour TEXT, [Pl.] TEXT, [Perf.] TEXT, [Vt.] TEXT, [Niv.] TEXT, [Pts] TEXT, Ville TEXT, Annee TEXT,
            UNIQUE(seq, Club, Date, Epreuve, Tour, [Pl.], [Perf.], [Vt.], [Niv.], [Pts], Ville, Annee)
        )
    ''')
    new_rows = 0
    for _, row in df.iterrows():
        try:
            cursor.execute(f'''
                INSERT OR IGNORE INTO {table_name} (seq, Club, Date, Epreuve, Tour, [Pl.], [Perf.], [Vt.], [Niv.], [Pts], Ville, Annee)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (seq,) + tuple(row.get(col, "") for col in ['Club', 'Date', 'Epreuve', 'Tour', 'Pl.', 'Perf.', 'Vt.', 'Niv.', 'Pts', 'Ville', 'Annee']))
            if cursor.rowcount == 1:
                new_rows += 1
        except Exception as e:
            print(f"Erreur lors de l'insertion d'une ligne : {e}")
    conn.commit()
    conn.close()
    return new_rows

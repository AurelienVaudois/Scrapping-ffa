# Point d'entrée du projet de scraping
# Exemple d'utilisation :
# from scraper import Scraper
# from parser import Parser
# from exporter import Exporter

from src.utils.http_utils import search_athletes, str_to_hex
from src.utils.athlete_utils import get_all_athlete_results, save_results_to_sqlite, save_athlete_info


def main():
    """
    Exemple d'utilisation : recherche d'un athlète, récupération de ses résultats, insertion dans la base SQLite,
    et enregistrement des informations générales de l'athlète dans la table athletes.
    """
    search_term = input("Nom de l'athlète à rechercher : ")
    athletes = search_athletes(search_term)

    if not athletes:
        print("Aucun athlète trouvé.")
        return

    print("Athlètes trouvés :")
    for i, athlete in enumerate(athletes, 1):
        print(f"{i}. {athlete['name']} ({athlete['club']})")

    try:
        choice = int(input("\nNuméro de l'athlète à scraper (0 pour annuler) : "))
        if not (1 <= choice <= len(athletes)):
            print("Sélection annulée.")
            return
    except ValueError:
        print("Entrée invalide.")
        return

    selected = athletes[choice - 1]
    seq = selected['seq']
    name = selected['name']
    club = selected['club']
    sex = selected['sex']
    print(f"Récupération des résultats pour {name}...")
    df = get_all_athlete_results(seq)

    if df.empty:
        print("Aucun résultat trouvé pour cet athlète.")
        return

    db_path = "data/athle_results.sqlite"
    # Enregistre les infos générales de l'athlète
    save_athlete_info(seq, name, club, sex, db_path)
    # Insère les résultats avec la colonne seq
    new_results = save_results_to_sqlite(df, seq, db_path)
    print(f"{new_results} nouveaux résultats insérés dans la base {db_path}.")
    print(f"Nombre total de lignes récupérées : {len(df)}")


if __name__ == "__main__":
    main()
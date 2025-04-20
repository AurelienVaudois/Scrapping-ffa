import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from src.utils.http_utils import search_athletes, str_to_hex
from src.utils.athlete_utils import get_all_athlete_results, save_results_to_postgres, save_athlete_info


def main():
    """
    Exemple d'utilisation : recherche d'un athlète, récupération de ses résultats, insertion dans la base PostgreSQL,
    et enregistrement des informations générales de l'athlète dans la table athletes.
    """
    load_dotenv()
    db_url = os.getenv("DB_URL")
    engine = create_engine(db_url)

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

    # Enregistre les infos générales de l'athlète
    save_athlete_info(seq, name, club, sex, engine)
    # Insère les résultats avec la colonne seq
    new_results = save_results_to_postgres(df, seq, engine)
    print(f"{new_results} nouveaux résultats insérés dans la base PostgreSQL.")
    print(f"Nombre total de lignes récupérées : {len(df)}")


if __name__ == "__main__":
    main()
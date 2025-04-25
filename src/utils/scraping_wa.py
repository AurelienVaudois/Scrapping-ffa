import requests
import pandas as pd
from json.decoder import JSONDecodeError
import concurrent.futures
import time
from tqdm.auto import tqdm        # ↩ détecte console, Jupyter ou Streamlit

def get_athlete_results_by_name(athlete_name, start_year=1960, end_year=2025, use_threading=True, max_workers=10):
    """
    Récupère tous les résultats de compétition d'un athlète en le recherchant par son nom.
    Version optimisée avec multithreading pour accélérer le scraping.
    
    Args:
        athlete_name (str): Nom de l'athlète à rechercher
        start_year (int, optional): Année de début pour la recherche de résultats. Par défaut 1960.
        end_year (int, optional): Année de fin pour la recherche de résultats. Par défaut 2025.
        use_threading (bool, optional): Utiliser le multithreading pour accélérer les requêtes. Par défaut True.
        max_workers (int, optional): Nombre maximum de workers pour le multithreading. Par défaut 10.
        
    Returns:
        pd.DataFrame: DataFrame contenant tous les résultats de l'athlète
        ou un message d'erreur si l'athlète n'est pas trouvé
    """
    # Mesurer le temps d'exécution
    start_time = time.time()
    
    # Recherche de l'ID de l'athlète par son nom
    athlete_info = search_athletes_by_name(athlete_name)
    
    # Vérification si un DataFrame a été retourné
    if isinstance(athlete_info, pd.DataFrame):
        if not athlete_info.empty:
            athlete_id = int(athlete_info['aaAthleteId'].iloc[0])
            athlete_name_full = f"{athlete_info['givenName'].iloc[0]} {athlete_info['familyName'].iloc[0]}"
            print(f"Athlète trouvé: {athlete_name_full} (ID: {athlete_id})")
            
            # Récupération des résultats avec l'ID de l'athlète
            results_df = get_athlete_competition_results(
                athlete_id, 
                start_year, 
                end_year, 
                use_threading=use_threading,
                max_workers=max_workers
            )
            
            # Mesurer le temps total d'exécution
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"Temps d'exécution total: {execution_time:.2f} secondes")
            
            # Ajout des informations de l'athlète au DataFrame de résultats
            if not results_df.empty:
                for col in athlete_info.columns:
                    results_df[col] = athlete_info[col].iloc[0]
                
                return results_df
            else:
                return pd.DataFrame({'info': ['warning'], 'message': [f"Aucun résultat trouvé pour {athlete_name_full}"]})
        else:
            return pd.DataFrame({'info': ['error'], 'message': ["DataFrame d'athlète vide"]})
    else:
        # Si un message d'erreur est retourné
        return pd.DataFrame({'info': ['error'], 'message': [str(athlete_info)]})

def search_athletes_by_name(athlete_name):
    """
    Recherche un athlète par son nom via l'API World Athletics.
    
    Args:
        athlete_name (str): Nom de l'athlète à rechercher
        
    Returns:
        pd.DataFrame: DataFrame contenant les informations de l'athlète
        ou un message d'erreur si la recherche échoue
    """
    # Define the base URL and the API key
    url = "https://graphql-prod-4765.prod.aws.worldathletics.org/graphql"
    headers = {"x-api-key": "da2-ois4zbc7s5htnlsy2it7bfkr2q"}
    payload = {
        "operationName": "SearchCompetitors",
        "variables": {
            "query": athlete_name
        },
        "query": """
        query SearchCompetitors($query: String, $gender: GenderType, $disciplineCode: String, $environment: String, $countryCode: String) {
          searchCompetitors(query: $query, gender: $gender, disciplineCode: $disciplineCode, environment: $environment, countryCode: $countryCode) {
            aaAthleteId
            familyName
            givenName
            birthDate
            disciplines
            iaafId
            gender
            country
            urlSlug
            __typename
          }
        }
        """
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        json_data = response.json()
        athletes_data = json_data.get("data", {}).get("searchCompetitors", [])
        
        if athletes_data:
            first_athlete = athletes_data[0]
            df = pd.json_normalize(first_athlete)
            return df
        else:
            return f"Aucun résultat trouvé pour l'athlète: {athlete_name}"
            
    except requests.exceptions.RequestException as e:
        return f"Erreur de requête: {str(e)}"
    except JSONDecodeError as e:
        return f"Erreur de décodage JSON: {str(e)}"
    except Exception as e:
        return f"Erreur inattendue: {str(e)}"

def fetch_year_data(athlete_id, year):
    """
    Fonction auxiliaire pour récupérer les résultats d'une année spécifique.
    Utilisée par le multithreading.
    
    Args:
        athlete_id (int): ID de l'athlète
        year (int): Année à récupérer
        
    Returns:
        tuple: (année, données de l'année, années actives)
    """
    url = "https://graphql-prod-4765.prod.aws.worldathletics.org/graphql"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "x-amz-user-agent": "aws-amplify/3.0.2",
        "x-api-key": "da2-ois4zbc7s5htnlsy2it7bfkr2q"
    }
    
    payload = {
        "operationName": "GetSingleCompetitorResultsDate",
        "variables": {
            "resultsByYear": year,
            "resultsByYearOrderBy": "date",
            "id": athlete_id  
        },
        "query": """
        query GetSingleCompetitorResultsDate($id: Int, $resultsByYearOrderBy: String, $resultsByYear: Int) {
          getSingleCompetitorResultsDate(id: $id, resultsByYear: $resultsByYear, resultsByYearOrderBy: $resultsByYearOrderBy) {
            parameters {
              resultsByYear
              resultsByYearOrderBy
              __typename
            }
            activeYears
            resultsByDate {
              date
              competition
              venue
              indoor
              disciplineCode
              disciplineNameUrlSlug
              typeNameUrlSlug
              discipline
              country
              category
              race
              place
              mark
              wind
              notLegal
              resultScore
              remark
              __typename
            }
            __typename
          }
        }
        """
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Vérifier la présence des clés nécessaires
        if "data" not in data or data["data"] is None:
            return year, None, []
            
        competitor_data = data["data"]["getSingleCompetitorResultsDate"]
        
        # Vérifier si competitor_data est None
        if competitor_data is None:
            return year, None, []
        
        # Récupérer les années actives
        active_years = competitor_data.get("activeYears", [])
        
        # Récupérer les résultats
        results_data = competitor_data.get("resultsByDate", [])
        if not results_data:
            return year, None, active_years
            
        df = pd.json_normalize(results_data)
        df['year'] = year
        
        return year, df, active_years
        
    except Exception as e:
        return year, None, []

def get_athlete_competition_results(athlete_id, start_year=1990, end_year=2025, use_threading=True, max_workers=10):
    """
    Récupère tous les résultats de compétition d'un athlète par son ID.
    Version optimisée avec support du multithreading.
    
    Args:
        athlete_id (int): ID de l'athlète
        start_year (int, optional): Année de début pour la recherche de résultats. Par défaut 1990.
        end_year (int, optional): Année de fin pour la recherche de résultats. Par défaut 2025.
        use_threading (bool, optional): Utiliser le multithreading pour accélérer les requêtes
        max_workers (int, optional): Nombre maximum de workers pour le multithreading
        
    Returns:
        pd.DataFrame: DataFrame contenant tous les résultats de l'athlète
    """
    all_years = list(range(start_year, end_year + 1))
    df_list = []
    all_active_years = set()
    
    # ÉTAPE 1 : Récupérer seulement les années actives d'abord
    first_year = all_years[0]
    print(f"Recherche des années actives pour l'athlète ID: {athlete_id}...")
    _, _, active_years = fetch_year_data(athlete_id, first_year)
    
    # Si nous avons des années actives, ne récupérer que ces années
    if active_years:
        all_active_years.update(active_years)
        filtered_years = [y for y in all_years if y in active_years]
        print(f"Années actives trouvées: {sorted(active_years)}")
        print(f"Récupération des données pour {len(filtered_years)} années au lieu de {len(all_years)}")
    else:
        # Si pas d'années actives, continuer avec toutes les années
        filtered_years = all_years
        print("Aucune information sur les années actives. Récupération de toutes les années.")
    
    # ÉTAPE 2 : Récupérer les données pour les années filtrées
    if use_threading and len(filtered_years) > 1:
        print(f"Utilisation du multithreading avec {min(max_workers, len(filtered_years))} workers...")
        # Utiliser ThreadPoolExecutor pour le multithreading
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(filtered_years))) as executor:
            # Soumettre toutes les tâches et créer un dict pour suivre les résultats
            future_to_year = {
                executor.submit(fetch_year_data, athlete_id, year): year 
                for year in filtered_years
            }
            
            # Utiliser tqdm pour afficher une barre de progression
            for future in tqdm(concurrent.futures.as_completed(future_to_year), total=len(filtered_years), desc="Récupération des données"):
                year = future_to_year[future]
                try:
                    year, df, active_years = future.result()
                    if df is not None:
                        print(f"✓ Données récupérées pour l'année {year} ({len(df)} résultats)")
                        df_list.append(df)
                    
                    if active_years:
                        all_active_years.update(active_years)
                        
                except Exception as e:
                    print(f"✗ Erreur pour l'année {year}: {str(e)}")
    else:
        # Version séquentielle pour les cas simples
        for year in tqdm(filtered_years, desc="Récupération des données"):
            year, df, active_years = fetch_year_data(athlete_id, year)
            if df is not None:
                print(f"✓ Données récupérées pour l'année {year} ({len(df)} résultats)")
                df_list.append(df)
            
            if active_years:
                all_active_years.update(active_years)
                
    # ÉTAPE 3 : Consolidation des résultats    
    if df_list:
        final_df = pd.concat(df_list, ignore_index=True)
        final_df['athlete_id'] = athlete_id
        if all_active_years:
            final_df['all_active_years'] = ','.join(map(str, sorted(all_active_years)))
            
        # Ajouter des métriques sur les résultats
        print(f"\nRésumé:")
        print(f"• Nombre total de résultats: {len(final_df)}")
        print(f"• Années avec résultats: {sorted(final_df['year'].unique())}")
        print(f"• Épreuves: {sorted(final_df['discipline'].unique())}")
        
        return final_df
    else:
        print("Aucun résultat n'a été trouvé pour cet athlète.")
        return pd.DataFrame()

# Exemple d'utilisation
# results = get_athlete_results_by_name("Usain Bolt", use_threading=True, max_workers=15)
# results.head()

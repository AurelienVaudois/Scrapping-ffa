# Scrapping FFA

Projet Python modulaire pour le scraping, l'analyse et la visualisation de données d'athlétisme.

## Fonctionnalités principales
- Recherche d'athlètes par nom avec suggestions.
- Scraping automatisé des résultats depuis le site FFA.
- Stockage des résultats et des informations athlètes dans une base SQLite.
- Détection et ajout uniquement des nouveaux résultats (pas de doublons).
- Visualisation interactive de l'évolution des performances sur 800m (et autres épreuves à venir) via une webapp Streamlit.
- Notebook Jupyter pour l'exploration et l'analyse avancée.

## Structure du projet
- `main.py` : script principal de scraping et d'insertion en base
- `app.py` : webapp Streamlit pour la recherche, le scraping et la visualisation
- `src/utils/` : fonctions utilitaires (scraping, parsing, conversion, DB)
- `data/athle_results.sqlite` : base de données SQLite
- `test.ipynb` : notebook d'analyse et de visualisation
- `requirements.txt` : dépendances Python

## Installation
```bash
pip install -r requirements.txt
```

## Lancer la webapp
```bash
streamlit run app.py
```

## Lancer le script principal
```bash
python main.py
```

## Lancer le notebook
Ouvre `test.ipynb` dans Jupyter ou VS Code.

## Personnalisation
- Pour ajouter d'autres épreuves ou graphiques, modifie `app.py` ou `test.ipynb`.
- Pour adapter le scraping ou la base, modifie les fonctions dans `src/utils/`.

## Dépendances principales
- requests, beautifulsoup4, pandas, numpy, matplotlib, seaborn, streamlit, sqlite3

## Auteur
Projet développé par Aurélien Vaudois.

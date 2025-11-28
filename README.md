# 🏃‍♂️ Athlé Analyse (Scrapping-ffa)

Application d'analyse et de suivi des performances d'athlétisme, agrégeant les données de la **Fédération Française d'Athlétisme (FFA)** et de **World Athletics (WA)**.

Ce projet permet de visualiser l'évolution des performances d'un athlète sur différentes distances (Sprint, Demi-fond, Fond, Route) via une interface web interactive.

## ✨ Fonctionnalités principales

- **🔍 Recherche Intelligente** : Autocomplétion pour trouver les athlètes (bases FFA et World Athletics).
- **🚀 Scraping Haute Performance** : Moteur de scraping **asynchrone** (`httpx` + `asyncio`) capable de récupérer des carrières entières en quelques secondes.
- **🌍 Multi-Sources** :
  - Source primaire : **FFA** (bases.athle.fr)
  - Fallback : **World Athletics** (si l'athlète n'est pas trouvé en France).
- **📊 Visualisation Interactive** : Graphiques d'évolution des performances (Matplotlib/Seaborn intégrés dans Streamlit).
- **💾 Base de Données Robuste** : Stockage persistant sur **PostgreSQL** (via NeonDB ou local) pour éviter de re-scraper les données existantes.
- **⚡ Mise à jour intelligente** : Détection des doublons et mise à jour incrémentale.

## 🛠️ Stack Technique

- **Langage** : Python 3.9+
- **Interface** : [Streamlit](https://streamlit.io/)
- **Base de données** : PostgreSQL, SQLAlchemy, Psycopg2
- **Scraping** :
  - `httpx` (Asynchrone HTTP/2)
  - `BeautifulSoup4` & `Selectolax` (Parsing HTML)
- **Data Science** : Pandas, NumPy
- **Visualisation** : Matplotlib, Seaborn

## 📂 Structure du projet

```
Scrapping-ffa/
├── app.py                 # 🚀 Point d'entrée de l'application Streamlit
├── requirements.txt       # Dépendances Python
├── .env                   # Variables d'environnement (non versionné)
├── src/
│   ├── utils/
│   │   ├── ffa_fast.py    # Scraper asynchrone optimisé pour la FFA
│   │   ├── wa_utils.py    # Gestion de l'API et du scraping World Athletics
│   │   ├── athlete_utils.py # Gestion BDD et nettoyage des données
│   │   ├── http_utils.py  # Utilitaires requêtes HTTP
│   │   └── file_utils.py  # Conversion de temps et formats
│   └── data_storage/      # Gestionnaires de base de données
└── notebooks/             # Notebooks d'exploration (evol_scrap_ffa.ipynb, etc.)
```

## 🚀 Installation et Utilisation

### 1. Cloner le projet
```bash
git clone https://github.com/votre-username/Scrapping-ffa.git
cd Scrapping-ffa
```

### 2. Installer les dépendances
Il est recommandé d'utiliser un environnement virtuel.
```bash
pip install -r requirements.txt
```

### 3. Configuration (.env)
Créez un fichier `.env` à la racine du projet et ajoutez vos identifiants :
```properties
# Connexion PostgreSQL (ex: NeonDB, Supabase, ou Local)
DB_URL=postgresql://user:password@host:port/dbname?sslmode=require

# Configuration World Athletics (Optionnel)
WA_API_URL=https://api.worldathletics.org/v1
WA_API_KEY=votre_cle_api
```

### 4. Lancer l'application
```bash
streamlit run app.py
```
L'application sera accessible sur `http://localhost:8501`.

## 🧪 Notebooks
Des notebooks Jupyter sont disponibles pour tester les scrapers individuellement ou effectuer des analyses de données avancées (ex: `evol_scrap_ffa.ipynb`).

## 👤 Auteur
Projet développé par **Aurélien Vaudois**.
Contributions bienvenues !

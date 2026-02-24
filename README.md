# 🏃‍♂️ Athlé Analyse (Scrapping-ffa)

Application d'analyse et de suivi des performances d'athlétisme, agrégeant les données de la **Fédération Française d'Athlétisme (FFA)** et de **World Athletics (WA)**.

Ce projet permet de visualiser l'évolution des performances sur différentes distances (Sprint, Demi-fond, Fond, Route), puis de comparer un second athlète sur le même graphique.

## ✨ Fonctionnalités principales

- **🔍 Recherche Intelligente** : Autocomplétion pour trouver les athlètes (bases FFA et World Athletics).
- **🚀 Scraping Haute Performance** : Moteur de scraping **asynchrone** (`httpx` + `asyncio`) capable de récupérer des carrières entières en quelques secondes.
- **🌍 Multi-Sources** :
  - Source primaire : **FFA** (bases.athle.fr)
  - Fallback : **World Athletics** (si l'athlète n'est pas trouvé en France).
- **📊 Visualisation Interactive (Plotly)** :
  - Vue principale **mono-athlète** (parcours simple par défaut)
  - **Comparaison optionnelle** avec un 2e athlète
  - Choix du type de graphique : **Nuage de points** ou **Lignes + points**
  - Contrôles d'analyse : **Axe X (Date / Âge / Année)** et **Filtre performance (Toutes / Best année / Best âge)**
  - Infobulle enrichie : performance, date, lieu, âge, type indoor/outdoor, source (FFA/WA)
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
- **Visualisation** : Plotly (app), Matplotlib/Seaborn (notebooks d'exploration)

## 📂 Structure du projet

```
Scrapping-ffa/
├── app.py                 # 🚀 Point d'entrée de l'application Streamlit
├── requirements.txt       # Dépendances Python
├── .env                   # Variables d'environnement (non versionné)
├── exploration/           # Notebooks d'exploration (athle_live, graph_plotly, etc.)
├── src/
│   ├── utils/
│   │   ├── ffa_fast.py    # Scraper asynchrone optimisé pour la FFA
│   │   ├── wa_utils.py    # Gestion de l'API et du scraping World Athletics
│   │   ├── athlete_utils.py # Gestion BDD et nettoyage des données
│   │   ├── http_utils.py  # Utilitaires requêtes HTTP
│   │   └── file_utils.py  # Conversion de temps et formats
│   └── data_storage/      # Gestionnaires de base de données
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

## 🔄 Mise à jour incrémentale de la base

Le script [update_athletes.py](update_athletes.py) met à jour les performances en mode idempotent:
- il re-scrape les résultats des athlètes à rafraîchir,
- il n'insère que les nouvelles lignes (déduplication SQL via contrainte unique),
- il met à jour `last_update` uniquement si la récupération est techniquement réussie.

### Lancement manuel
```bash
python update_athletes.py --batch 10
```

### Lancement en boucle (période de compétition)
```bash
python update_athletes.py --loop --delay 600 --batch 10
```

Paramètres:
- `--batch`: nombre d'athlètes traités par batch
- `--delay`: pause entre deux batches en secondes (en mode `--loop`)

### Lancement Windows prêt scheduler
Le script [update_loop.bat](update_loop.bat) :
- active l'environnement virtuel,
- crée automatiquement le dossier `logs` si nécessaire,
- écrit les traces dans [logs/update.log](logs/update.log).

Tu peux le brancher dans le Planificateur de tâches Windows pour une exécution quotidienne.
Important: le PC doit être allumé (ou réveillable) au moment prévu.

### Exécution depuis téléphone
Possible de manière indirecte (bureau à distance vers ton PC), puis lecture du log dans [logs/update.log](logs/update.log).

### Presets Task Scheduler (Windows)

Commande utilisée dans les presets:

```powershell
cmd /c "C:\Users\Lucas\Documents\DATA_SCIENCE\Scrapping-ffa\update_loop.bat"
```

Preset `Normal` (1 fois / jour à 06:00):

```powershell
schtasks /Create /TN "ScrappingFFA-Update-Normal" /TR "cmd /c \"C:\Users\Lucas\Documents\DATA_SCIENCE\Scrapping-ffa\update_loop.bat\"" /SC DAILY /ST 06:00 /F
```

Preset `Intense` (2 fois / jour: 07:00 et 19:00):

```powershell
schtasks /Create /TN "ScrappingFFA-Update-Intense-AM" /TR "cmd /c \"C:\Users\Lucas\Documents\DATA_SCIENCE\Scrapping-ffa\update_loop.bat\"" /SC DAILY /ST 07:00 /F
schtasks /Create /TN "ScrappingFFA-Update-Intense-PM" /TR "cmd /c \"C:\Users\Lucas\Documents\DATA_SCIENCE\Scrapping-ffa\update_loop.bat\"" /SC DAILY /ST 19:00 /F
```

Commandes utiles:

```powershell
# Lister les tâches
schtasks /Query /TN "ScrappingFFA-Update-*"

# Lancer une tâche immédiatement
schtasks /Run /TN "ScrappingFFA-Update-Normal"

# Supprimer un preset
schtasks /Delete /TN "ScrappingFFA-Update-Normal" /F
schtasks /Delete /TN "ScrappingFFA-Update-Intense-AM" /F
schtasks /Delete /TN "ScrappingFFA-Update-Intense-PM" /F
```

Notes:
- Le PC doit être allumé (ou réveillable) au moment d'exécution.
- Les traces restent dans [logs/update.log](logs/update.log).

## 🧪 Notebooks
Les notebooks Jupyter d'exploration sont regroupés dans le dossier `exploration/` pour les tests de scraping, analyses et prototypage de visualisation.

## 🧭 Expérience utilisateur (résumé)
- **Sidebar structurée** : `Athlète` → `Comparaison` → `Analyse` → `Avancé`
- **Comparaison progressive** : l'utilisateur commence avec 1 athlète puis ajoute le 2e uniquement si besoin
- **Affichage avancé** : réglage de hauteur du graphique dans un panneau repliable

## 👤 Auteur
Projet développé par **Aurélien Vaudois**.
Contributions bienvenues !

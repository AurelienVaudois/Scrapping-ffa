import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from src.utils.http_utils import search_athletes
from src.utils.athlete_utils import get_all_athlete_results, save_results_to_postgres, save_athlete_info, clean_and_prepare_results_df
from src.utils.file_utils import convert_time_to_seconds
import os

try:
    db_url = st.secrets["DB_URL"]
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.getenv("DB_URL")
engine = create_engine(db_url)

st.set_page_config(page_title="Athlé Analyse", layout="wide")
st.title("Analyse des performances athlétisme")
st.markdown("""
Entrez le nom d'un athlète pour visualiser l'évolution de ses performances sur 800m. 
Si l'athlète n'est pas encore dans la base, le scraping sera lancé automatiquement.
""")

search_term = st.text_input("Nom de l'athlète à rechercher")

if search_term and len(search_term) >= 3:
    with st.spinner("Recherche des athlètes..."):
        athletes = search_athletes(search_term)
    if athletes:
        options = [f"{a['name']} ({a['club']})" for a in athletes]
        choice = st.selectbox("Sélectionnez l'athlète :", options)
        selected = athletes[options.index(choice)]
        seq = selected['seq']
        name = selected['name']
        club = selected['club']
        sex = selected['sex']

        @st.cache_data(show_spinner=False)
        def get_results_from_db(seq):
            query = "SELECT * FROM results WHERE seq = %(seq)s"
            df = pd.read_sql_query(query, engine, params={"seq": seq})
            return df

        df = get_results_from_db(seq)

        if df.empty:
            with st.spinner("Scraping en cours, cela peut prendre quelques secondes..."):
                try:
                    df = get_all_athlete_results(seq)
                    if not df.empty:
                        df = clean_and_prepare_results_df(df, seq)
                        save_athlete_info(seq, name, club, sex, engine)
                        save_results_to_postgres(df, seq, engine)
                        st.success("Scraping terminé et données ajoutées à la base.")
                    else:
                        st.warning("Aucune donnée trouvée pour cet athlète (scraping vide).")
                except Exception as e:
                    st.error(f"Erreur lors du scraping : {e}")
        else:
            st.success("Données chargées depuis la base.")
            

        # Filtrer sur 800m et 800m Piste Courte
        if not df.empty and 'epreuve' in df.columns:
            df_800 = df[df['epreuve'].isin(['800m', '800m Piste Courte'])].copy()
            if not df_800.empty:
                import numpy as np
                df_800['Lieu'] = np.where(df_800.epreuve == "800m Piste Courte", 'Indoor', 'Outdoor')
                df_800['date'] = pd.to_datetime(df_800['date'], errors='coerce')
                df_800['Annee'] = df_800['date'].dt.year
                df_800 = df_800[~df_800['perf'].str.contains('|'.join(['DNS','DNF', 'AB']), na=False)]
                df_800['time'] = df_800['perf'].apply(convert_time_to_seconds)
                df_800 = df_800.dropna(subset=['date', 'time'])
                df_800 = df_800.sort_values('date')
                best_performances = df_800[['perf','time','date','Annee']].sort_values('time', ascending=True).groupby('Annee').first().reset_index()
                import seaborn as sns
                import matplotlib.pyplot as plt
                import matplotlib
                matplotlib.use('Agg')
                sns.set_style("whitegrid")
                medium_colors = [
                    "#6A0572", "#9A1672", "#E8515A", "#FFA500", 
                    "#FFC947", "#00A878", "#008DD5", "#6E7BA8", 
                    "#9C82B8", "#F08CA5", "#4CBB17", "#FF6B6B"
                ]
                def format_time(x):
                    minutes = int(x) // 60
                    seconds = int(x) % 60
                    centiseconds = int((x * 100) %100)
                    return f"{minutes}'{seconds:02d}''{centiseconds:02d}"
                fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
                scatter_plot = sns.scatterplot(data=df_800, x='date', y='time', hue='Annee', style='Lieu',
                                 s=70, palette=medium_colors, ax=ax)
                for _, row in best_performances.iterrows():
                    time_format = format_time(row['time'])
                    ax.scatter(row['date'], row['time'], color='red', marker='s', s=100)
                    ax.text(row['date'], row['time'], f"{time_format}", ha='center', va='top', fontsize=10, fontweight='bold')
                ax.set_xlabel("Année", fontweight='bold')
                ax.set_ylabel("Performance", fontweight='bold')
                ax.set_title(f"Evolution des performances sur 800m pour {name}", fontweight='bold')
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: format_time(x)))
                handles, labels = scatter_plot.get_legend_handles_labels()
                best_handle = plt.Line2D([], [], marker='s', color='red', markersize=10, markerfacecolor='red', markeredgewidth=1.5)
                handles = [best_handle] + handles
                labels = ['Best'] + labels
                ax.legend(handles=handles, labels=labels, title="Best Per Year", loc='center left', bbox_to_anchor=(1, 0.5))
                ax.grid(True)
                plt.tight_layout()
                st.pyplot(fig)
                st.dataframe(df_800[['date', 'perf', 'time', 'ville', 'tour']].sort_values('date'), use_container_width=True)
            else:
                st.info("Aucune performance sur 800m trouvée pour cet athlète.")
        else:
            st.info("Aucune donnée trouvée pour cet athlète.")
    else:
        st.warning("Aucun athlète trouvé pour cette recherche.")
else:
    st.info("Veuillez entrer au moins 3 caractères pour lancer la recherche.")

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from src.utils.http_utils import search_athletes            # FFA autocomplete
from src.utils.wa_utils import (
    search_wa_athletes,                                     # WA autocomplete (fallback)
    fetch_and_store_wa_results                              # WA scraping (fallback)
)
from src.utils.athlete_utils import (
    save_results_to_postgres,
    save_athlete_info,
    clean_and_prepare_results_df,
)
from src.utils.file_utils import convert_time_to_seconds
import os
from src.utils.ffa_fast import get_all_results_fast as get_all_athlete_results

# -----------------------------------------------------------------------------
# DB connexion ----------------------------------------------------------------
# -----------------------------------------------------------------------------
try:
    db_url = st.secrets["DB_URL"]
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.getenv("DB_URL")
engine = create_engine(db_url)

# -----------------------------------------------------------------------------
# UI settings -----------------------------------------------------------------
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Athlé Analyse", layout="wide")
st.title("Analyse des performances athlétisme")
st.markdown(
    """Entrez le nom d'un athlète pour visualiser l'évolution de ses performances sur 
* 800m, 
* 1500m, 
* 3 000 m Steeple
* 5 000m & 5km route (graphique commun)
* 10000m & 10km route (graphique commun).

Si l'athlète n'est pas encore dans la base, le scraping sera lancé automatiquement.
"""
)

# --- State init ----------------------------------------------------------------
if "athletes" not in st.session_state:
    st.session_state["athletes"] = []
if "athlete_options" not in st.session_state:
    st.session_state["athlete_options"] = []
if "selected_athlete" not in st.session_state:
    st.session_state["selected_athlete"] = None

search_term = st.text_input("Nom de l'athlète à rechercher", key="search_term")

# -----------------------------------------------------------------------------
# 1. Recherche d'athlètes ------------------------------------------------------
# -----------------------------------------------------------------------------
if search_term and len(search_term) >= 3 and st.session_state.get("last_search_term") != search_term:
    with st.spinner("Recherche des athlètes…"):
        # ① Autocomplétion FFA
        athletes = search_athletes(search_term)
        # ② Fallback World Athletics si FFA vide
        if not athletes:
            athletes = search_wa_athletes(search_term)
        st.session_state["athletes"] = athletes
        st.session_state["athlete_options"] = [
            f"{a['name']} ({a.get('club','')})" for a in athletes
        ]
        st.session_state["selected_athlete"] = None
        st.session_state["last_search_term"] = search_term

athletes = st.session_state.get("athletes", [])
athlete_options = st.session_state.get("athlete_options", [])
selected_athlete = st.session_state.get("selected_athlete")

if athlete_options:
    idx = 0
    if selected_athlete and selected_athlete in athletes:
        idx = athletes.index(selected_athlete)
    choice = st.selectbox(
        "Sélectionnez l'athlète :", athlete_options, index=idx, key="athlete_select"
    )
    selected = athletes[athlete_options.index(choice)]
    st.session_state["selected_athlete"] = selected
else:
    selected = None

# -----------------------------------------------------------------------------
# 2. Chargement / scraping des résultats --------------------------------------
# -----------------------------------------------------------------------------
if selected:
    seq = selected["seq"]
    name = selected["name"]
    club = selected.get("club", "")
    sex = selected.get("sex", "")

    @st.cache_data(show_spinner=False)
    def get_results_from_db(seq_: str) -> pd.DataFrame:
        query = "SELECT * FROM results WHERE seq = %(seq)s"
        return pd.read_sql_query(query, engine, params={"seq": seq_})

    df = get_results_from_db(seq)

    if df.empty:
        # Détermine la source de l'athlète (WA ou FFA) pour savoir quel scraper lancer
        is_wa_athlete = selected.get("source") == "WA" or str(seq).startswith("WA_")

        if is_wa_athlete:
            # -----------------------------------------------------------------
            # Scraping World Athletics (fallback direct)
            # -----------------------------------------------------------------
            with st.spinner("Scraping World Athletics…"):
                df = fetch_and_store_wa_results(name, engine)
                if not df.empty:
                    st.cache_data.clear()
                    st.success("Données WA ajoutées à la base.")
                else:
                    st.warning("Aucune donnée trouvée sur World Athletics.")
        else:
            # -----------------------------------------------------------------
            # Scraping FFA (source par défaut)
            # -----------------------------------------------------------------
            with st.spinner("Scraping FFA…"):
                try:
                    df = get_all_athlete_results(seq)
                    if not df.empty:
                        df = clean_and_prepare_results_df(df, seq)
                        save_athlete_info(seq, name, club, sex, engine)
                        save_results_to_postgres(df, seq, engine)
                        st.cache_data.clear()
                        st.success("Données FFA ajoutées à la base.")
                    else:
                        # Rien côté FFA, on tente World Athletics en dernier recours
                        st.info("Aucune donnée FFA, tentative World Athletics…")
                        df = fetch_and_store_wa_results(name, engine)
                        if not df.empty:
                            st.cache_data.clear()
                            st.success("Données WA ajoutées à la base.")
                        else:
                            st.warning("Aucune donnée trouvée sur FFA ni WA.")
                except Exception as e:
                    st.error(f"Erreur scraping FFA : {e}")
    else:
        st.success("Données chargées depuis la base.")

    # -------------------------------------------------------------------------
    # 3. Affichage (identique à ton code d’origine) ----------------------------
    # -------------------------------------------------------------------------
    EPREUVES = {
        "800m": ["800m", "800m Piste Courte"],
        "1500m": ["1 500m", "1 500m Piste Courte"],
        "3000m Steeple (91)": ["3000m Steeple (91)"],
        # 🔽  ➜  nouveaux couples piste / route
    "5000 / 5K": [
        "5 000m",              # FFA piste
        "5000 Metres",         # WA piste
        "5 Km Route",          # FFA route
        "5 Kilometres Road",   # WA route
    ],
    "10000 / 10K": [
        "10 000m",             # FFA piste
        "10000 Metres",        # WA piste
        "10 Km Route",         # FFA route
        "10 Kilometres Road",  # WA route
    ],
    }
    epreuve_choisie = st.selectbox(
        "Choisissez l'épreuve à afficher :", list(EPREUVES.keys()), index=0, key="epreuve_select"
    )
    filtres_epreuve = EPREUVES[epreuve_choisie]

    if not df.empty and "epreuve" in df.columns:
        df_epreuve = df[df["epreuve"].isin(filtres_epreuve)].copy()
        if not df_epreuve.empty:
            import numpy as np
            import seaborn as sns
            import matplotlib.pyplot as plt
            import matplotlib

            df_epreuve["Lieu"] = np.where(
                df_epreuve.epreuve.str.contains("Piste Courte"), "Indoor", "Outdoor"
            )
            df_epreuve["date"] = pd.to_datetime(df_epreuve["date"], errors="coerce")
            df_epreuve["Annee"] = df_epreuve["date"].dt.year
            df_epreuve = df_epreuve[
                ~df_epreuve["perf"].str.contains("|".join(["DNS", "DNF", "AB", "DQ"]), na=False)
            ]
            df_epreuve["time"] = df_epreuve["perf"].apply(convert_time_to_seconds)
            df_epreuve = df_epreuve.dropna(subset=["date", "time"]).sort_values("date")

            best_performances = (
                df_epreuve[["perf", "time", "date", "Annee"]]
                .sort_values("time", ascending=True)
                .groupby("Annee")
                .first()
                .reset_index()
            )

            matplotlib.use("Agg")
            sns.set_style("whitegrid")
            medium_colors = [
                "#6A0572",
                "#9A1672",
                "#E8515A",
                "#FFA500",
                "#FFC947",
                "#00A878",
                "#008DD5",
                "#6E7BA8",
                "#9C82B8",
                "#F08CA5",
                "#4CBB17",
                "#FF6B6B",
            ]

            def format_time(x):
                minutes = int(x) // 60
                seconds = int(x) % 60
                centiseconds = int((x * 100) % 100)
                return f"{minutes}'{seconds:02d}''{centiseconds:02d}"

            fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
            scatter_plot = sns.scatterplot(
                data=df_epreuve,
                x="date",
                y="time",
                hue="Annee",
                style="Lieu",
                s=70,
                palette=medium_colors,
                ax=ax,
            )
            for _, row in best_performances.iterrows():
                time_format = format_time(row["time"])
                ax.scatter(row["date"], row["time"], color="red", marker="s", s=100)
                ax.text(
                    row["date"],
                    row["time"],
                    f"{time_format}",
                    ha="center",
                    va="top",
                    fontsize=10,
                    fontweight="bold",
                )
            ax.set_xlabel("Année", fontweight="bold")
            ax.set_ylabel("Performance", fontweight="bold")
            ax.set_title(f"Evolution des performances sur {epreuve_choisie} pour {name}", fontweight="bold")
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: format_time(x)))
            handles, labels = scatter_plot.get_legend_handles_labels()
            best_handle = plt.Line2D(
                [], [], marker="s", color="red", markersize=10, markerfacecolor="red", markeredgewidth=1.5
            )
            handles = [best_handle] + handles
            labels = ["Best"] + labels
            ax.legend(handles=handles, labels=labels, title="Best Per Year", loc="center left", bbox_to_anchor=(1, 0.5))
            ax.grid(True)
            plt.tight_layout()
            st.pyplot(fig)
            st.dataframe(
                df_epreuve[["date", "perf", "time", "ville", "tour"]].sort_values("date"),
                use_container_width=True,
            )
        else:
            st.info(f"Aucune performance sur {epreuve_choisie} trouvée pour cet athlète.")
    else:
        st.info("Aucune donnée trouvée pour cet athlète.")

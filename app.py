import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
import plotly.graph_objects as go
from src.utils.http_utils import search_athletes            # FFA autocomplete
from src.utils.wa_utils import (
    search_wa_athletes,                                     # WA autocomplete (fallback)
    fetch_and_store_wa_results                              # WA scraping (fallback)
)
from src.utils.athlete_utils import (
    save_results_to_postgres,
    save_athlete_info,
    clean_and_prepare_results_df,
    # get_all_athlete_results
)
from src.utils.file_utils import convert_time_to_seconds
from src.utils.ffa_fast import get_all_results_fast as get_all_athlete_results

# -----------------------------------------------------------------------------
# DB connexion ----------------------------------------------------------------
# -----------------------------------------------------------------------------
try:
    db_url = st.secrets["DB_URL"]
    WA_API_URL = st.secrets["WA_API_URL"]
    WA_API_KEY = st.secrets["WA_API_KEY"]
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.getenv("DB_URL")
    WA_API_URL = os.getenv("WA_API_URL")
    WA_API_KEY = os.getenv("WA_API_KEY")
engine = create_engine(db_url)
# ----------------------------------------------------------------------------- 
# UI settings -----------------------------------------------------------------
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Athlé Analyse", layout="wide")
st.title("Analyse des performances athlétisme")
st.markdown(
    """
    ### 📈 Suivi des performances athlétiques

    Entrez le **nom d'un athlète** pour visualiser l'évolution de ses performances :

    - **SPRINT** : **100m**, **200m**, **400m**
    - **MIDDLE DISTANCE** : **800m**, **1500m**, **3000m**, **3000m Steeple**
    - **LONG DISTANCE** : **5000m**, **10000m**, **Semi-Marathon**, **Marathon**
    - **ROUTE** : **5km**, **10km**

    Comparez ensuite avec un 2e athlète, choisissez le type de graphique et ajustez l'analyse
    (axe X, filtre de performance) depuis le panneau de contrôle.

    🔎 *Si l'athlète n'est pas encore dans la base, le scraping est lancé automatiquement.*
    """,
    unsafe_allow_html=True
)

control_panel = st.sidebar
control_panel.title("🎛️ Contrôles")
control_panel.subheader("Athlète")


# --- State init ----------------------------------------------------------------
if "athletes" not in st.session_state:
    st.session_state["athletes"] = []
if "athlete_options" not in st.session_state:
    st.session_state["athlete_options"] = []
if "selected_athlete" not in st.session_state:
    st.session_state["selected_athlete"] = None
if "athletes_compare" not in st.session_state:
    st.session_state["athletes_compare"] = []
if "athlete_options_compare" not in st.session_state:
    st.session_state["athlete_options_compare"] = []
if "selected_athlete_compare" not in st.session_state:
    st.session_state["selected_athlete_compare"] = None

search_term = control_panel.text_input("Nom de l'athlète à rechercher", key="search_term")

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
            print(f"Fallback WA: {athletes}")
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
    choice = control_panel.selectbox(
        "Sélectionnez l'athlète :", athlete_options, index=idx, key="athlete_select"
    )
    selected = athletes[athlete_options.index(choice)]
    print(selected)
    print(selected['seq'])
    st.session_state["selected_athlete"] = selected
else:
    selected = None

# -----------------------------------------------------------------------------
# 2. Chargement / scraping des résultats --------------------------------------
# -----------------------------------------------------------------------------
if selected:
    @st.cache_data(show_spinner=False)
    def get_results_from_db(seq_: str) -> pd.DataFrame:
        query = "SELECT * FROM results WHERE seq = %(seq)s"
        return pd.read_sql_query(query, engine, params={"seq": seq_})

    @st.cache_data(show_spinner=False)
    def get_birth_year_from_db(seq_: str):
        query = "SELECT birth_year FROM athletes WHERE seq = %(seq)s"
        df_birth = pd.read_sql_query(query, engine, params={"seq": seq_})
        if df_birth.empty:
            return None
        birth_year = pd.to_numeric(df_birth.iloc[0]["birth_year"], errors="coerce")
        if pd.isna(birth_year):
            return None
        return int(birth_year)

    def load_or_scrape_results(athlete: dict, show_loaded_message: bool = True) -> pd.DataFrame:
        seq_local = athlete["seq"]
        name_local = athlete["name"]
        club_local = athlete.get("club", "")
        sex_local = athlete.get("sex", "")

        df_local = get_results_from_db(seq_local)
        if df_local.empty:
            is_wa_athlete = athlete.get("source") == "WA" or str(seq_local).startswith("WA_")

            if is_wa_athlete:
                with st.spinner(f"Scraping World Athletics pour {name_local}…"):
                    df_local = fetch_and_store_wa_results(name_local, engine)
                    if not df_local.empty:
                        st.cache_data.clear()
                        st.success(f"Données WA ajoutées à la base pour {name_local}.")
                    else:
                        st.warning(f"Aucune donnée trouvée sur World Athletics pour {name_local}.")
            else:
                with st.spinner(f"Scraping FFA pour {name_local}…"):
                    try:
                        df_local = get_all_athlete_results(seq_local)
                        if not df_local.empty:
                            df_local = clean_and_prepare_results_df(df_local, seq_local)
                            save_athlete_info(seq_local, name_local, club_local, sex_local, engine)
                            save_results_to_postgres(df_local, seq_local, engine)
                            st.cache_data.clear()
                            st.success(f"Données FFA ajoutées à la base pour {name_local}.")
                        else:
                            st.info(f"Aucune donnée FFA pour {name_local}, tentative World Athletics…")
                            df_local = fetch_and_store_wa_results(name_local, engine)
                            if not df_local.empty:
                                st.cache_data.clear()
                                st.success(f"Données WA ajoutées à la base pour {name_local}.")
                            else:
                                st.warning(f"Aucune donnée trouvée sur FFA ni WA pour {name_local}.")
                    except Exception as e:
                        st.error(f"Erreur scraping FFA pour {name_local} : {e}")
        else:
            if show_loaded_message:
                st.success(f"Données chargées depuis la base pour {name_local}.")

        return df_local

    df = load_or_scrape_results(selected, show_loaded_message=True)

    # -------------------------------------------------------------------------
    # 3. Affichage (identique à ton code d’origine) ----------------------------
    # -------------------------------------------------------------------------
    control_panel.subheader("Comparaison")
    compare_enabled = control_panel.toggle("Comparer avec un autre athlète", value=False, key="compare_toggle")
    selected_compare = None
    if compare_enabled:
        search_term_compare = control_panel.text_input("Nom du 2e athlète", key="search_term_compare")
        if (
            search_term_compare
            and len(search_term_compare) >= 3
            and st.session_state.get("last_search_term_compare") != search_term_compare
        ):
            with st.spinner("Recherche du 2e athlète…"):
                athletes_compare = search_athletes(search_term_compare)
                if not athletes_compare:
                    athletes_compare = search_wa_athletes(search_term_compare)
                st.session_state["athletes_compare"] = athletes_compare
                st.session_state["athlete_options_compare"] = [
                    f"{a['name']} ({a.get('club', '')})" for a in athletes_compare
                ]
                st.session_state["selected_athlete_compare"] = None
                st.session_state["last_search_term_compare"] = search_term_compare

        athletes_compare = st.session_state.get("athletes_compare", [])
        athlete_options_compare = st.session_state.get("athlete_options_compare", [])
        selected_compare_state = st.session_state.get("selected_athlete_compare")

        if athlete_options_compare:
            idx_compare = 0
            if selected_compare_state and selected_compare_state in athletes_compare:
                idx_compare = athletes_compare.index(selected_compare_state)

            choice_compare = control_panel.selectbox(
                "Sélectionnez le 2e athlète :",
                athlete_options_compare,
                index=idx_compare,
                key="athlete_select_compare",
            )
            selected_compare = athletes_compare[athlete_options_compare.index(choice_compare)]
            st.session_state["selected_athlete_compare"] = selected_compare

    EPREUVES = {
        
        "100m": ["100m"],
        "200m": ["200m", "200m Piste Courte"],
        "400m": ["400m", "400m Piste Courte"],
        "800m": ["800m", "800m Piste Courte"],
        "1500m": ["1 500m", "1 500m Piste Courte"],
        
        "3000m": ["3 000m", "3 000m Piste Courte"],
        
        "3000m Steeple (91)": ["3000m Steeple (91)"],
        
        "5000 / 5K": ["5 000m", "5 000m Piste Courte", "5 Km Route"],
        
        "10000 / 10K": ["10 000m", "10 Km Route"],
        
        "1/2 Marathon": ["1/2 Marathon"],
        
        "Marathon": ["Marathon"],
        
        

    }

    control_panel.subheader("Analyse")
    epreuve_choisie = control_panel.selectbox(
        "Choisissez l'épreuve à afficher :", list(EPREUVES.keys()), index=0, key="epreuve_select"
    )
    filtres_epreuve = EPREUVES[epreuve_choisie]

    axis_mode_label = control_panel.radio(
        "Axe X",
        ["Date", "Âge", "Année"],
        horizontal=True,
        key="axis_mode",
    )
    perf_mode_label = control_panel.radio(
        "Filtre performance",
        ["Toutes", "Best année", "Best âge"],
        horizontal=True,
        key="perf_mode",
    )
    chart_type = control_panel.radio(
        "Type de graphique",
        ["Nuage de points", "Lignes + points"],
        horizontal=True,
        key="chart_type_mode",
    )

    control_panel.subheader("Avancé")
    with control_panel.expander("Affichage avancé", expanded=False):
        chart_height = st.slider(
            "Hauteur du graphique",
            min_value=600,
            max_value=1200,
            value=850,
            step=50,
            key="chart_height",
        )

    def prepare_plot_df(df_source: pd.DataFrame, seq_local: str) -> pd.DataFrame:
        if df_source.empty or "epreuve" not in df_source.columns:
            return pd.DataFrame()

        df_plot = df_source[df_source["epreuve"].isin(filtres_epreuve)].copy()
        if df_plot.empty:
            return pd.DataFrame()

        df_plot["date"] = pd.to_datetime(df_plot["date"], errors="coerce")
        df_plot["Annee"] = df_plot["date"].dt.year
        df_plot = df_plot[
            ~df_plot["perf"].str.contains("|".join(["DNS", "DNF", "AB", "DQ"]), na=False)
        ]
        df_plot["time"] = df_plot["perf"].apply(convert_time_to_seconds)
        df_plot["LieuType"] = df_plot["epreuve"].str.contains("Piste Courte", na=False).map(
            {True: "Indoor", False: "Outdoor"}
        )
        birth_year_local = get_birth_year_from_db(seq_local)
        if birth_year_local is not None:
            df_plot["age"] = df_plot["date"].dt.year - birth_year_local
        else:
            df_plot["age"] = pd.NA
        df_plot["Source"] = "World Athletics" if str(seq_local).startswith("WA_") else "FFA"
        df_plot = df_plot.dropna(subset=["date", "time"]).sort_values("date")

        return df_plot

    def apply_perf_mode(df_plot: pd.DataFrame, mode: str) -> pd.DataFrame:
        if df_plot.empty:
            return df_plot

        out = df_plot.copy()
        if mode == "all":
            return out.sort_values("date")
        if mode == "best_year":
            idx = out.groupby("Annee")["time"].idxmin()
            return out.loc[idx].sort_values("Annee")
        if mode == "best_age":
            out = out.dropna(subset=["age"]).copy()
            if out.empty:
                return out
            idx = out.groupby("age")["time"].idxmin()
            return out.loc[idx].sort_values("age")
        return out

    def add_perf_trace_variant(
        fig_obj: go.Figure,
        df_plot: pd.DataFrame,
        athlete_name: str,
        color: str,
        graph_mode: str,
        x_col: str,
        visible: bool,
    ):
        draw_mode = "markers" if graph_mode == "Nuage de points" else "lines+markers"
        df_variant = df_plot.dropna(subset=[x_col]).copy()

        fig_obj.add_trace(
            go.Scatter(
                x=df_variant[x_col],
                y=df_variant["time"],
                mode=draw_mode,
                name=athlete_name,
                marker={"size": 8, "color": color},
                line={"width": 2, "color": color},
                visible=visible,
                customdata=df_variant[["perf", "ville", "age", "LieuType", "date", "Source"]],
                hovertemplate=(
                    "Athlète: " + athlete_name + "<br>"
                    + "Perf: %{customdata[0]}<br>"
                    + "Date: %{customdata[4]|%Y-%m-%d}<br>"
                    + "Lieu: %{customdata[1]}<br>"
                    + "Âge: %{customdata[2]}<br>"
                    + "Type: %{customdata[3]}<br>"
                    + "Source: %{customdata[5]}<extra></extra>"
                ),
            )
        )

    df_primary_plot = prepare_plot_df(df, selected["seq"])

    if df_primary_plot.empty:
        st.info(f"Aucune performance sur {epreuve_choisie} trouvée pour cet athlète.")
    else:
        athlete_series = [(selected["name"], "#1f77b4", df_primary_plot)]
        table_frames = [df_primary_plot.assign(athlete=selected["name"]) ]

        if compare_enabled and selected_compare:
            if selected_compare["seq"] == selected["seq"]:
                st.warning("Le 2e athlète est identique au 1er. Sélectionnez un autre profil pour comparer.")
            else:
                df_compare = load_or_scrape_results(selected_compare, show_loaded_message=False)
                df_compare_plot = prepare_plot_df(df_compare, selected_compare["seq"])
                if df_compare_plot.empty:
                    st.warning(
                        f"Aucune performance sur {epreuve_choisie} pour {selected_compare['name']}."
                    )
                else:
                    athlete_series.append((selected_compare["name"], "#d62728", df_compare_plot))
                    table_frames.append(df_compare_plot.assign(athlete=selected_compare["name"]))

        axis_map = {"Date": ("date", "Date"), "Âge": ("age", "Âge"), "Année": ("Annee", "Année")}
        perf_map = {"Toutes": ("all", "Toutes"), "Best année": ("best_year", "Best année"), "Best âge": ("best_age", "Best âge")}

        selected_x_col, selected_x_label = axis_map[axis_mode_label]
        selected_perf_mode, selected_perf_label = perf_map[perf_mode_label]

        fig = go.Figure()
        for athlete_name, color, athlete_df in athlete_series:
            df_mode = apply_perf_mode(athlete_df, selected_perf_mode)
            add_perf_trace_variant(
                fig,
                df_mode,
                athlete_name,
                color,
                chart_type,
                selected_x_col,
                True,
            )

        fig.update_layout(
            title=f"Évolution des performances - {epreuve_choisie} ({selected_perf_label})",
            xaxis_title=selected_x_label,
            yaxis_title="Temps (secondes)",
            template="plotly_white",
            hovermode="closest",
            legend_title="Athlète",
            height=chart_height,
        )

        st.plotly_chart(fig, use_container_width=True)

        df_table = pd.concat(table_frames, ignore_index=True).sort_values("date")
        st.dataframe(
            df_table[["athlete", "date", "perf", "time", "ville", "tour", "epreuve"]],
            use_container_width=True,
        )

from __future__ import annotations

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
import math
import uuid
from time import perf_counter
import plotly.graph_objects as go
from src.utils.http_utils import (
    search_athletes,                                        # FFA autocomplete (legacy)
    search_athletes_smart,                                  # FFA+LePistard smart search
)
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
from src.utils.monitoring import ensure_monitoring_tables, init_sentry, track_event, track_timing

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


@st.cache_resource(show_spinner=False)
def init_monitoring() -> bool:
    ensure_monitoring_tables(engine)
    return init_sentry()


sentry_enabled = init_monitoring()
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
if "monitoring_session_id" not in st.session_state:
    st.session_state["monitoring_session_id"] = str(uuid.uuid4())
if "monitoring_session_tracked" not in st.session_state:
    st.session_state["monitoring_session_tracked"] = False

monitoring_session_id = st.session_state["monitoring_session_id"]
if not st.session_state["monitoring_session_tracked"]:
    track_event(
        engine,
        event_type="session_start",
        session_id=monitoring_session_id,
        metadata={"sentry_enabled": sentry_enabled},
    )
    st.session_state["monitoring_session_tracked"] = True


def detect_mobile_device() -> bool:
    mobile_markers = ["iphone", "android", "mobile", "ipad", "ipod"]
    user_agent = ""
    sec_ch_mobile = ""

    try:
        context_obj = getattr(st, "context", None)
        if context_obj is not None and hasattr(context_obj, "headers"):
            user_agent = str(context_obj.headers.get("user-agent", "")).lower()
            sec_ch_mobile = str(context_obj.headers.get("sec-ch-ua-mobile", "")).strip()
    except Exception:
        user_agent = ""
        sec_ch_mobile = ""

    if sec_ch_mobile == "?1":
        return True

    return any(marker in user_agent for marker in mobile_markers)


def merge_athlete_candidates(*groups: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for group in groups:
        for athlete in group or []:
            seq = str(athlete.get("seq", "")).strip()
            key = seq or f"{athlete.get('name', '')}|{athlete.get('club', '')}|{athlete.get('source', '')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(athlete)
    return merged

search_term = control_panel.text_input("Nom de l'athlète à rechercher", key="search_term")
include_wa_search = control_panel.toggle(
    "Athlète principal: mode WA uniquement",
    value=False,
    help="Activé: recherche World Athletics uniquement (FFA exclu). Désactivé: recherche FFA uniquement.",
    key="include_wa_search",
)

# -----------------------------------------------------------------------------
# 1. Recherche d'athlètes ------------------------------------------------------
# -----------------------------------------------------------------------------
if search_term and len(search_term) >= 3 and st.session_state.get("last_search_term") != search_term:
    with st.spinner("Recherche des athlètes…"):
        search_started = perf_counter()
        search_source = "WA" if include_wa_search else "FFA"
        search_status = "ok"
        try:
            if include_wa_search:
                athletes = search_wa_athletes(search_term)
                print(f"Mode WA direct activé: {len(athletes)} résultat(s)")
            else:
                # Recherche FFA
                athletes = search_athletes_smart(search_term)
                if not athletes:
                    athletes = search_athletes(search_term)
        except Exception:
            search_status = "error"
            raise
        finally:
            search_elapsed = int((perf_counter() - search_started) * 1000)
            track_event(
                engine,
                event_type="athlete_search",
                session_id=monitoring_session_id,
                status=search_status,
                duration_ms=search_elapsed,
                metadata={
                    "source_mode": search_source,
                    "query_len": len(search_term),
                },
            )

        st.session_state["athletes"] = athletes
        st.session_state["athlete_options"] = [
            f"{a['name']} ({a.get('club','')})" for a in athletes
        ]
        st.session_state["selected_athlete"] = None
        st.session_state["last_search_term"] = search_term

        if not athletes and not include_wa_search:
            st.info("Aucun profil trouvé sur FFA. Activez 'Inclure les profils World Athletics' pour élargir la recherche.")

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

        with track_timing(
            engine,
            event_type="db_results_lookup",
            session_id=monitoring_session_id,
            metadata={"seq": seq_local},
        ):
            df_local = get_results_from_db(seq_local)

        track_event(
            engine,
            event_type="db_results_lookup_count",
            session_id=monitoring_session_id,
            metadata={"seq": seq_local, "rows": int(len(df_local))},
        )

        if df_local.empty:
            is_wa_athlete = athlete.get("source") == "WA" or str(seq_local).startswith("WA_")

            if is_wa_athlete:
                with st.spinner(f"Scraping World Athletics pour {name_local}…"):
                    with track_timing(
                        engine,
                        event_type="wa_scrape",
                        session_id=monitoring_session_id,
                        metadata={"name": name_local},
                    ):
                        df_local = fetch_and_store_wa_results(name_local, engine)
                    if not df_local.empty:
                        st.cache_data.clear()
                        st.success(f"Données WA ajoutées à la base pour {name_local}.")
                        track_event(
                            engine,
                            event_type="wa_scrape_result",
                            session_id=monitoring_session_id,
                            metadata={"name": name_local, "rows": int(len(df_local))},
                        )
                    else:
                        st.warning(f"Aucune donnée trouvée sur World Athletics pour {name_local}.")
                        track_event(
                            engine,
                            event_type="wa_scrape_result",
                            session_id=monitoring_session_id,
                            status="empty",
                            metadata={"name": name_local},
                        )
            else:
                with st.spinner(f"Scraping FFA pour {name_local}…"):
                    try:
                        with track_timing(
                            engine,
                            event_type="ffa_scrape",
                            session_id=monitoring_session_id,
                            metadata={"seq": seq_local, "name": name_local},
                        ):
                            df_local = get_all_athlete_results(seq_local)
                        if not df_local.empty:
                            df_local = clean_and_prepare_results_df(df_local, seq_local)
                            save_athlete_info(seq_local, name_local, club_local, sex_local, engine)
                            save_results_to_postgres(df_local, seq_local, engine)
                            st.cache_data.clear()
                            st.success(f"Données FFA ajoutées à la base pour {name_local}.")
                            track_event(
                                engine,
                                event_type="ffa_scrape_result",
                                session_id=monitoring_session_id,
                                metadata={"seq": seq_local, "rows": int(len(df_local))},
                            )
                        else:
                            st.info(f"Aucune donnée FFA pour {name_local}, tentative World Athletics…")
                            with track_timing(
                                engine,
                                event_type="wa_scrape_fallback",
                                session_id=monitoring_session_id,
                                metadata={"seq": seq_local, "name": name_local},
                            ):
                                df_local = fetch_and_store_wa_results(name_local, engine)
                            if not df_local.empty:
                                st.cache_data.clear()
                                st.success(f"Données WA ajoutées à la base pour {name_local}.")
                                track_event(
                                    engine,
                                    event_type="wa_scrape_result",
                                    session_id=monitoring_session_id,
                                    metadata={"name": name_local, "rows": int(len(df_local)), "fallback": True},
                                )
                            else:
                                st.warning(f"Aucune donnée trouvée sur FFA ni WA pour {name_local}.")
                                track_event(
                                    engine,
                                    event_type="wa_scrape_result",
                                    session_id=monitoring_session_id,
                                    status="empty",
                                    metadata={"name": name_local, "fallback": True},
                                )
                    except Exception as e:
                        st.error(f"Erreur scraping FFA pour {name_local} : {e}")
                        track_event(
                            engine,
                            event_type="ffa_scrape_exception",
                            session_id=monitoring_session_id,
                            status="error",
                            metadata={"seq": seq_local, "name": name_local, "message": str(e)[:300]},
                        )
        else:
            if show_loaded_message:
                st.success(f"Données chargées depuis la base pour {name_local}.")
            track_event(
                engine,
                event_type="cache_hit_results",
                session_id=monitoring_session_id,
                metadata={"seq": seq_local, "rows": int(len(df_local))},
            )

        return df_local

    df = load_or_scrape_results(selected, show_loaded_message=True)

    # -------------------------------------------------------------------------
    # 3. Affichage (identique à ton code d’origine) ----------------------------
    # -------------------------------------------------------------------------
    control_panel.subheader("Comparaison")
    compare_enabled = control_panel.toggle("Comparer avec un autre athlète", value=False, key="compare_toggle")
    selected_compare = None
    if compare_enabled:
        include_wa_compare = control_panel.toggle(
            "2e athlète: mode WA uniquement",
            value=include_wa_search,
            help="Activé: recherche World Athletics uniquement. Désactivé: recherche FFA uniquement.",
            key="include_wa_search_compare",
        )
        search_term_compare = control_panel.text_input("Nom du 2e athlète", key="search_term_compare")
        if (
            search_term_compare
            and len(search_term_compare) >= 3
            and st.session_state.get("last_search_term_compare") != search_term_compare
        ):
            with st.spinner("Recherche du 2e athlète…"):
                if include_wa_compare:
                    athletes_compare = search_wa_athletes(search_term_compare)
                else:
                    athletes_compare = search_athletes_smart(search_term_compare)
                    if not athletes_compare:
                        athletes_compare = search_athletes(search_term_compare)

                st.session_state["athletes_compare"] = athletes_compare
                st.session_state["athlete_options_compare"] = [
                    f"{a['name']} ({a.get('club', '')})" for a in athletes_compare
                ]
                st.session_state["selected_athlete_compare"] = None
                st.session_state["last_search_term_compare"] = search_term_compare

                if not athletes_compare and not include_wa_compare:
                    st.info("Aucun profil FFA pour le 2e athlète. Activez la recherche World Athletics si besoin.")

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

    def get_available_epreuves(df_source: pd.DataFrame, epreuves_map: dict) -> dict:
        if df_source.empty or "epreuve" not in df_source.columns:
            return {}

        out = {}
        for label, aliases in epreuves_map.items():
            if df_source["epreuve"].isin(aliases).any():
                out[label] = aliases
        return out

    available_epreuves = get_available_epreuves(df, EPREUVES)
    if not available_epreuves:
        st.info("Aucune performance disponible sur les épreuves suivies pour cet athlète.")
        st.stop()

    available_labels = list(available_epreuves.keys())
    if (
        "epreuve_select" in st.session_state
        and st.session_state["epreuve_select"] not in available_labels
    ):
        st.session_state.pop("epreuve_select")

    control_panel.subheader("Analyse")
    epreuve_choisie = control_panel.selectbox(
        "Choisissez l'épreuve à afficher :", available_labels, index=0, key="epreuve_select"
    )
    filtres_epreuve = available_epreuves[epreuve_choisie]

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
    is_mobile_device = detect_mobile_device()
    default_chart_height = 500 if is_mobile_device else 850
    min_chart_height = 420 if is_mobile_device else 600
    max_chart_height = 900 if is_mobile_device else 1200

    with control_panel.expander("Affichage avancé", expanded=False):
        chart_height = st.slider(
            "Hauteur du graphique",
            min_value=min_chart_height,
            max_value=max_chart_height,
            value=default_chart_height,
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

    def get_time_display_mode(epreuve_label: str) -> str:
        if epreuve_label in {"100m", "200m", "400m"}:
            return "seconds"
        if epreuve_label in {"1/2 Marathon", "Marathon"}:
            return "hours"
        return "minutes"

    def format_axis_time(seconds_value: float, mode: str) -> str:
        total_seconds = float(seconds_value)
        if mode == "seconds":
            return f"{total_seconds:.1f}s"

        rounded = int(round(total_seconds))
        if mode == "hours":
            hours = rounded // 3600
            minutes = (rounded % 3600) // 60
            return f"{hours}h{minutes:02d}"

        minutes = rounded // 60
        seconds = rounded % 60
        return f"{minutes}:{seconds:02d}"

    def build_time_ticks(time_values: list[float], mode: str) -> tuple[list[float], list[str]]:
        if not time_values:
            return [], []

        min_time = float(min(time_values))
        max_time = float(max(time_values))
        if max_time <= min_time:
            return [min_time], [format_axis_time(min_time, mode)]

        base_step = {"seconds": 0.5, "minutes": 5.0, "hours": 300.0}[mode]
        step = base_step
        while ((max_time - min_time) / step) > 10:
            step *= 2

        start = math.floor(min_time / step) * step
        end = math.ceil(max_time / step) * step

        tickvals = []
        current = start
        guard = 0
        while current <= end + (step * 0.1) and guard < 200:
            tickvals.append(round(current, 6))
            current += step
            guard += 1

        ticktext = [format_axis_time(val, mode) for val in tickvals]
        return tickvals, ticktext

    with track_timing(
        engine,
        event_type="prepare_plot_df",
        session_id=monitoring_session_id,
        metadata={"seq": selected["seq"], "epreuve": epreuve_choisie},
    ):
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
        time_display_mode = get_time_display_mode(epreuve_choisie)

        fig = go.Figure()
        plotted_times = []
        for athlete_name, color, athlete_df in athlete_series:
            df_mode = apply_perf_mode(athlete_df, selected_perf_mode)
            plotted_times.extend(df_mode["time"].dropna().tolist())
            add_perf_trace_variant(
                fig,
                df_mode,
                athlete_name,
                color,
                chart_type,
                selected_x_col,
                True,
            )

        y_tick_vals, y_tick_text = build_time_ticks(plotted_times, time_display_mode)
        y_axis_title_map = {
            "seconds": "Temps (s)",
            "minutes": "Temps (mm:ss)",
            "hours": "Temps (hh:mm)",
        }

        legend_font_size = 9 if is_mobile_device else 12
        chart_margin = {"l": 8, "r": 8, "t": 42, "b": 18} if is_mobile_device else {"l": 40, "r": 30, "t": 70, "b": 40}
        chart_title = (
            f"{epreuve_choisie} · {selected_perf_label}"
            if is_mobile_device
            else f"Évolution des performances - {epreuve_choisie} ({selected_perf_label})"
        )

        fig.update_layout(
            title={"text": chart_title, "font": {"size": 13 if is_mobile_device else 18}},
            xaxis_title=selected_x_label,
            yaxis={
                "title": y_axis_title_map[time_display_mode],
                "tickmode": "array",
                "tickvals": y_tick_vals,
                "ticktext": y_tick_text,
            },
            template="plotly_white",
            hovermode="closest",
            legend={
                "title": {"text": "Athlète"},
                "x": 0.99,
                "y": 0.99,
                "xanchor": "right",
                "yanchor": "top",
                "bgcolor": "rgba(255,255,255,0.65)",
                "bordercolor": "rgba(0,0,0,0.2)",
                "borderwidth": 1,
                "font": {"size": legend_font_size},
            },
            margin=chart_margin,
            height=chart_height,
        )

        render_started = perf_counter()
        st.plotly_chart(fig, use_container_width=True)
        track_event(
            engine,
            event_type="plotly_chart_call",
            session_id=monitoring_session_id,
            duration_ms=int((perf_counter() - render_started) * 1000),
            metadata={"series_count": len(athlete_series), "epreuve": epreuve_choisie},
        )

        df_table = pd.concat(table_frames, ignore_index=True).sort_values("date")
        st.dataframe(
            df_table[["athlete", "date", "perf", "time", "ville", "tour", "epreuve"]],
            use_container_width=True,
        )

        with st.expander("🩺 Monitoring (7 derniers jours)", expanded=False):
            try:
                query_summary = """
                    SELECT
                        COUNT(*)::int AS total_events,
                        COUNT(DISTINCT session_id)::int AS active_sessions,
                        COUNT(*) FILTER (WHERE event_type = 'athlete_search')::int AS searches,
                        ROUND(AVG(duration_ms) FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS avg_search_ms,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
                            FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'error') / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
                    FROM app_monitoring_events
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                """
                monitoring_summary = pd.read_sql_query(query_summary, engine)
                if not monitoring_summary.empty:
                    summary_row = monitoring_summary.iloc[0]
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Sessions actives", int(summary_row.get("active_sessions") or 0))
                    col2.metric("Recherches", int(summary_row.get("searches") or 0))
                    col3.metric("Latence moyenne", f"{int(summary_row.get('avg_search_ms') or 0)} ms")
                    col4.metric("p95 recherche", f"{int(summary_row.get('p95_search_ms') or 0)} ms")
                    col5.metric("Taux erreur", f"{float(summary_row.get('error_rate_pct') or 0):.2f}%")

                query_capacity = """
                    SELECT
                        DATE_TRUNC('hour', created_at) AS hour_slot,
                        COUNT(*) FILTER (WHERE event_type = 'athlete_search')::int AS searches,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
                            FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
                        COUNT(*) FILTER (WHERE status = 'error')::int AS errors
                    FROM app_monitoring_events
                    WHERE created_at >= NOW() - INTERVAL '48 hours'
                    GROUP BY 1
                    ORDER BY 1 DESC
                    LIMIT 48
                """
                monitoring_capacity = pd.read_sql_query(query_capacity, engine)

                query_daily = """
                    SELECT
                        DATE_TRUNC('day', created_at)::date AS day_slot,
                        COUNT(*) FILTER (WHERE event_type = 'athlete_search')::int AS searches,
                        ROUND(AVG(duration_ms) FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS avg_search_ms,
                        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
                            FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
                        COUNT(*) FILTER (WHERE status = 'error')::int AS errors
                    FROM app_monitoring_events
                    WHERE created_at >= NOW() - INTERVAL '14 days'
                    GROUP BY 1
                    ORDER BY 1
                """
                monitoring_daily = pd.read_sql_query(query_daily, engine)

                query_errors = """
                    SELECT
                        event_type,
                        COUNT(*)::int AS errors
                    FROM app_monitoring_events
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                      AND status = 'error'
                    GROUP BY 1
                    ORDER BY 2 DESC
                    LIMIT 10
                """
                monitoring_errors = pd.read_sql_query(query_errors, engine)

                if not monitoring_daily.empty:
                    st.markdown("**Tendance journalière (14 jours)**")
                    daily_indexed = monitoring_daily.set_index("day_slot")
                    st.line_chart(
                        daily_indexed[["searches", "errors"]],
                        use_container_width=True,
                    )
                    st.line_chart(
                        daily_indexed[["avg_search_ms", "p95_search_ms"]],
                        use_container_width=True,
                    )

                if not monitoring_capacity.empty:
                    st.markdown("**Capacité horaire (48h)**")
                    monitoring_capacity = monitoring_capacity.sort_values("hour_slot")
                    st.line_chart(
                        monitoring_capacity.set_index("hour_slot")[["searches", "errors"]],
                        use_container_width=True,
                    )
                    st.line_chart(
                        monitoring_capacity.set_index("hour_slot")[["p95_search_ms"]],
                        use_container_width=True,
                    )

                with st.expander("Données brutes monitoring", expanded=False):
                    st.dataframe(monitoring_summary, use_container_width=True)
                    st.dataframe(monitoring_daily, use_container_width=True)
                    st.dataframe(monitoring_capacity, use_container_width=True)
                    st.dataframe(monitoring_errors, use_container_width=True)
            except Exception as monitor_exc:
                st.info(f"Monitoring indisponible: {monitor_exc}")

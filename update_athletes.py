###############################################
# update_athletes.py – mise à jour incrémentale
###############################################
"""Rafraîchit la base athlètes / résultats.

• Mode one‑shot (par défaut)        : traite ≤ BATCH_SIZE athlètes
• Mode boucle  --loop               : répète des mini‑batches jusqu’à
  ce que tous les athlètes soient à jour, avec une pause --delay.

Dépend d’un helper « lecture seule » dans *wa_utils.py* :

    def fetch_wa_results_df(name: str) -> pd.DataFrame

qui retourne un DataFrame déjà nettoyé sans rien écrire en DB.
"""
from __future__ import annotations

import os
import time
import logging
import argparse
from typing import Dict, List

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# ─── utils projet ────────────────────────────────────────────────────────────
from src.utils.ffa_fast import get_all_results_fast
from src.utils.athlete_utils import (
    clean_and_prepare_results_df,
    save_athlete_info,
    save_results_to_postgres,
)
from src.utils.wa_utils import fetch_wa_results_df   # ← nouveau helper

# ─── configuration ───────────────────────────────────────────────────────────
load_dotenv()
DB_URL        = os.getenv("DB_URL")
DEFAULT_BATCH = int(os.getenv("BATCH_SIZE", 10))
MAX_AGE_DAYS  = int(os.getenv("MAX_AGE_DAYS", 7))
DEFAULT_DELAY = int(os.getenv("DELAY_SECONDS", 600))  # 10 min

if not DB_URL:
    raise SystemExit("❌  DB_URL manquant dans l’environnement")

engine: Engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ─── sélection des athlètes à rafraîchir ─────────────────────────────────────

def select_stale_athletes(engine: Engine, batch_size: int) -> List[Dict]:
    q = text(
        """
        SELECT seq, name, club, sex, last_update
          FROM athletes
         WHERE last_update IS NULL
            OR last_update < (NOW() AT TIME ZONE 'utc') - INTERVAL :age
         ORDER BY last_update NULLS FIRST
         LIMIT :limit
        """
    )
    with engine.begin() as conn:
        rows = (
            conn.execute(q, {"age": f"{MAX_AGE_DAYS} days", "limit": batch_size})
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]

# ─── helpers ─────────────────────────────────────────────────────────────────

def _touch(seq: str, name: str, club: str, sex: str, engine: Engine):
    """Met à jour la colonne *last_update*."""
    save_athlete_info(seq, name, club, sex, engine)


def refresh_ffa(ath: Dict, engine: Engine):
    seq, name, club, sex = ath["seq"], ath["name"], ath["club"], ath["sex"]
    df = get_all_results_fast(seq)
    if df.empty:
        logging.info("   ↳ aucune donnée FFA trouvée pour %s", seq)
        _touch(seq, name, club, sex, engine)
        return

    df = clean_and_prepare_results_df(df, seq)
    with engine.begin() as conn:
        last_date = conn.scalar(text("SELECT MAX(date) FROM results WHERE seq = :s"), {"s": seq})
    if last_date is not None:
        df = df[df["date"] > pd.Timestamp(last_date)]

    if df.empty:
        logging.info("   ↳ rien de nouveau pour %s", seq)
        _touch(seq, name, club, sex, engine)
        return

    ins = save_results_to_postgres(df, seq, engine)
    logging.info("   ↳ %d nouvelles lignes insérées", ins)
    _touch(seq, name, club, sex, engine)


def refresh_wa(ath: Dict, engine: Engine):
    """Scrape WA puis insère seulement les nouvelles performances."""
    seq, name, club, sex = ath["seq"], ath["name"], ath["club"], ath["sex"]

    df = fetch_wa_results_df(name)  # DataFrame déjà nettoyé, pas d’insert
    if df.empty:
        logging.info("   ↳ aucune donnée WA pour %s", name)
        _touch(seq, name, club, sex, engine)
        return

    # filtre incrémental
    with engine.begin() as conn:
        last = conn.scalar(text("SELECT MAX(date) FROM results WHERE seq = :s"), {"s": seq})
    if last is not None:
        df = df[df["date"] > pd.Timestamp(last)]

    if df.empty:
        logging.info("   ↳ rien de nouveau pour %s", name)
    else:
        inserted = save_results_to_postgres(df, seq, engine)
        logging.info("   ↳ %d nouvelles lignes insérées", inserted)

    _touch(seq, name, club, sex, engine)


def process_batch(batch_size: int) -> int:
    """Traite un batch et renvoie le nombre d’athlètes rafraîchis."""
    stale = select_stale_athletes(engine, batch_size)
    if not stale:
        logging.info("✅ Base déjà à jour – aucune action nécessaire.")
        return 0

    logging.info("➡️  %d athlète(s) à mettre à jour (batch=%d, seuil=%dj)", len(stale), batch_size, MAX_AGE_DAYS)
    for ath in stale:
        logging.info("• Rafraîchissement %s (%s)", ath["name"], ath["seq"])
        try:
            if str(ath["seq"]).startswith("WA_"):
                refresh_wa(ath, engine)
            else:
                refresh_ffa(ath, engine)
        except Exception:
            logging.exception("   ↳ Erreur sur %s", ath["seq"])
    logging.info("🏁 Batch terminé.")
    return len(stale)

# ─── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mise à jour incrémentale athletes/results")
    parser.add_argument("--loop", action="store_true", help="boucle jusqu’à mise à jour complète")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY, help="délai entre batches en secondes")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="taille du batch (par ex. 10)")
    args = parser.parse_args()

    if args.loop:
        while True:
            count = process_batch(args.batch)
            if count == 0:
                break
            logging.info("⏳ Pause %d s avant batch suivant…", args.delay)
            time.sleep(args.delay)
    else:
        process_batch(args.batch)


if __name__ == "__main__":
    main()

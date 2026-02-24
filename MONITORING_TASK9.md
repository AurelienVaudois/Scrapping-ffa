# Task 9 — Monitoring Streamlit Cloud (usage, vitesse, capacité)

## Objectif
Déterminer si l'app Streamlit est suffisante pour une forte concurrence, ou s'il faut migrer vers un autre provider.

## Instrumentation implémentée
- Table PostgreSQL `app_monitoring_events` (création automatique au démarrage).
- Événements capturés:
  - `session_start`
  - `athlete_search`
  - `db_results_lookup`, `db_results_lookup_count`
  - `cache_hit_results`
  - `ffa_scrape`, `ffa_scrape_result`, `ffa_scrape_exception`
  - `wa_scrape`, `wa_scrape_fallback`, `wa_scrape_result`
  - `prepare_plot_df`, `plotly_chart_call`
- Dashboard de suivi dans l'app (expander **Monitoring (7 derniers jours)**):
  - sessions actives
  - volume de recherches
  - latence moyenne et p95 de recherche
  - taux d'erreur global
  - vue horaire 48h (recherches / p95 / erreurs)

## Sentry (optionnel)
Variables d'environnement:

```env
SENTRY_DSN=...
SENTRY_ENVIRONMENT=streamlit-cloud
SENTRY_TRACES_SAMPLE_RATE=0.2
```

Si `SENTRY_DSN` est absent, l'app continue sans Sentry.

## Test de charge (Locust)
Fichier: `load_tests/locustfile.py`
Runner paliers: `load_tests/run_stages.py`

### Lancer localement
```bash
pip install -r requirements.txt
locust -f load_tests/locustfile.py --host http://localhost:8501
```

### Lancer contre Streamlit Cloud
```bash
locust -f load_tests/locustfile.py --host https://<your-app>.streamlit.app
```

### Lancer un test par paliers automatique (CSV + HTML)
```bash
python load_tests/run_stages.py \
  --host https://<your-app>.streamlit.app \
  --users 5,20,50,75,100,150 \
  --duration 10m \
  --spawn-rate 5
```

Résultats générés dans `load_tests/results/` (un rapport par palier).

### Paliers recommandés
1. Baseline: 5 → 20 → 50 utilisateurs concurrents (10-15 min / palier)
2. Stress: 75 → 100 → 150 jusqu'au point de saturation

## Critères de décision provider (focus capacité)
Lancer l'étude de migration si, sur plusieurs runs cohérents:
- p95 `athlete_search` durablement élevé (ex: > 4-5s)
- hausse erreurs (`status=error`) en montée de charge
- instabilité/cold-start perceptible empêchant un service fluide

## Requêtes SQL utiles
### Vue rapide 7 jours
```sql
SELECT
  COUNT(*)::int AS total_events,
  COUNT(DISTINCT session_id)::int AS active_sessions,
  COUNT(*) FILTER (WHERE event_type = 'athlete_search')::int AS searches,
  ROUND(AVG(duration_ms) FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS avg_search_ms,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
    FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
  ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'error') / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
FROM app_monitoring_events
WHERE created_at >= NOW() - INTERVAL '7 days';
```

### Capacité par heure (48h)
```sql
SELECT
  DATE_TRUNC('hour', created_at) AS hour_slot,
  COUNT(*) FILTER (WHERE event_type = 'athlete_search')::int AS searches,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
    FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
  COUNT(*) FILTER (WHERE status = 'error')::int AS errors
FROM app_monitoring_events
WHERE created_at >= NOW() - INTERVAL '48 hours'
GROUP BY 1
ORDER BY 1 DESC;
```

## Limites actuelles
- Streamlit utilise WebSocket + reruns; Locust donne surtout un signal de capacité HTTP (pas une émulation parfaite de l'UX).
- Pour une décision finale, compléter par un test réel utilisateur simultané (session browser) et comparer aux métriques DB/Sentry.

## Grille de décision Go / No-Go (migration provider)

### Fenêtre d'évaluation
- Prendre les **3 derniers runs de charge** comparables (mêmes paliers, même durée).
- Décision uniquement si les signaux sont cohérents sur au moins **2 runs sur 3**.

### Seuils recommandés
- **p95 recherche (`athlete_search`)**:
  - Vert: ≤ 2500 ms
  - Orange: 2501 à 4000 ms
  - Rouge: > 4000 ms
- **Taux d'erreur global (`status=error`)**:
  - Vert: < 1%
  - Orange: 1% à 3%
  - Rouge: > 3%
- **Capacité palier cible** (ex: 100 users concurrents):
  - Vert: palier tenu 10 min sans dégradation continue
  - Orange: palier tenu avec dégradation ponctuelle
  - Rouge: palier non tenu (timeouts/erreurs/saturation)

### Règle de décision
- **Go Streamlit (rester)**: 0 critère rouge et au plus 1 orange.
- **Watch (surveillance renforcée)**: 2 oranges, 0 rouge.
- **No-Go Streamlit (préparer migration)**: au moins 1 rouge, ou incapacité à tenir le palier cible sur 2 runs.

## Score synthétique (optionnel)
- Score = `2 × nb_rouges + 1 × nb_oranges`
- Interprétation:
  - 0-1: OK
  - 2: attention
  - ≥3: migration à instruire immédiatement

## Template rapport hebdo (copier-coller)

```markdown
# Rapport capacité Streamlit - Semaine YYYY-WW

## Contexte
- Environnement: Streamlit Cloud
- Paliers: 5, 20, 50, 75, 100, 150
- Durée/palier: 10 min

## Résultats clés
- p95 recherche (palier cible): ... ms
- Taux erreur global: ... %
- Palier cible tenu: Oui / Non
- Signaux saturation observés: Oui / Non

## Statut grille
- Critères rouges: ...
- Critères oranges: ...
- Score synthétique: ...

## Décision
- Go / Watch / No-Go
- Action semaine suivante: ...
```

## SQL aide décision (7 jours)

```sql
WITH base AS (
  SELECT
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
      FILTER (WHERE event_type = 'athlete_search' AND status = 'ok'))::int AS p95_search_ms,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'error') / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
  FROM app_monitoring_events
  WHERE created_at >= NOW() - INTERVAL '7 days'
)
SELECT
  p95_search_ms,
  error_rate_pct,
  CASE
    WHEN p95_search_ms > 4000 OR error_rate_pct > 3 THEN 'NO_GO'
    WHEN p95_search_ms > 2500 OR error_rate_pct >= 1 THEN 'WATCH'
    ELSE 'GO'
  END AS decision_hint
FROM base;
```

# mlb_hit_pipeline

Daily MLB hit-probability platform: a $0 ELT pipeline (dlt → MotherDuck
→ dbt) scheduled on GitHub Actions, an ML plane tracked with MLflow,
and a Streamlit dashboard ranking every batter on today's slate by
calibrated P(records ≥1 hit).

Full build plan, research agenda, and modeling methodology: [PLAN.md](PLAN.md).

## Stack

| Concern | Tool |
|---|---|
| Extract + load | dlt (pybaseball/Statcast, MLB Stats API, Baseball-Reference WAR sources) |
| Warehouse | MotherDuck (local DuckDB file for dev/CI) |
| Transform + data quality | dbt Core + dbt tests |
| Scheduling / CI | GitHub Actions (daily 16:00 UTC cron) |
| ML | scikit-learn, LightGBM, MLflow |
| Dashboard | Streamlit Community Cloud |

## Layout

```
ingestion/    dlt pipelines + sources        (EL)
transform/    dbt project                    (T + tests)
ml/           train / calibrate / backtest / predict
research/     factor-study notebooks (disposable)
reports/eda/  exported research charts
app/          Streamlit dashboard
orchestration/  Dagster assets (Phase 8, optional)
```

## Running locally

Everything runs against a local DuckDB file (`data/local.duckdb`) when
`MOTHERDUCK_TOKEN` is unset — no cloud credentials needed to develop.

```bash
pip install -r requirements.txt
python ingestion/pipelines.py heartbeat   # EL: load a heartbeat row
cd transform
dbt build --profiles-dir . --target dev   # T: build + test all models
```

Scheduled runs (`.github/workflows/daily.yml`) set `MOTHERDUCK_TOKEN`
from repo secrets and hit the `prod` target instead.

## One-time backfill (Phase 1)

Run locally so history lands in the cloud warehouse (~5–6 h at the
polite rate limits; statcast ≈ 25–30 min/season, statsapi ≈ 25
min/season). Put `MOTHERDUCK_TOKEN=...` in a `.env` file at the repo
root (gitignored), then:

```bash
bash scripts/backfill.sh 2>&1 | tee backfill.log
```

The script loops seasons 2021–2026, then WAR (Baseball-Reference) +
coaches, then runs the Phase 1 gate (`ingestion/reconcile.py`, weekly pitch counts vs the
prototype within 0.5%). It is resumable — statcast picks up from
`max(game_date)` in the warehouse, so re-running after an interruption
skips completed seasons.

Off-days inside the ranges cost one cheap empty request each; game-type
filtering (regular season vs spring/postseason) happens downstream in
dbt, not at ingestion.

The daily `statcast` run resumes from `max(game_date)` already in the
warehouse, capped at 21 days per scheduled run — so a missed day heals
itself, but a cold warehouse won't accidentally attempt a five-year
backfill inside a GitHub Action.

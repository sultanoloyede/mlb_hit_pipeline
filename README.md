# mlb_hit_pipeline

Daily MLB hit-probability platform: a $0 ELT pipeline (dlt → MotherDuck
→ dbt) scheduled on GitHub Actions, an ML plane tracked with MLflow,
and a Streamlit dashboard ranking every batter on today's slate by
calibrated P(records ≥1 hit).

Full build plan, research agenda, and modeling methodology: [PLAN.md](PLAN.md).

## Stack

| Concern | Tool |
|---|---|
| Extract + load | dlt (pybaseball, MLB Stats API, FanGraphs sources) |
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

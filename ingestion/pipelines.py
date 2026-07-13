"""dlt pipeline entrypoints.

Destination resolution: MotherDuck when MOTHERDUCK_TOKEN is set
(scheduled prod runs), otherwise a local DuckDB file (dev and CI).

Phase 1 adds the real sources (statcast, mlb_statsapi, fangraphs) under
ingestion/sources/ and registers their entrypoints in PIPELINES. The
heartbeat pipeline exists to prove the EL path end to end.

Usage:
    python ingestion/pipelines.py heartbeat
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import dlt

MD_DATABASE = "mlb_hits"
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local.duckdb"


def destination():
    token = os.getenv("MOTHERDUCK_TOKEN")
    if token:
        return dlt.destinations.motherduck(
            credentials=f"md:{MD_DATABASE}?motherduck_token={token}"
        )
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return dlt.destinations.duckdb(str(LOCAL_DB_PATH))


@dlt.resource(table_name="heartbeat", write_disposition="append")
def heartbeat():
    yield {
        "run_at": datetime.now(timezone.utc),
        "runner": os.getenv("GITHUB_WORKFLOW", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "dev"),
    }


def run_heartbeat():
    pipeline = dlt.pipeline(
        pipeline_name="mlb_hits_heartbeat",
        destination=destination(),
        dataset_name="raw",
    )
    info = pipeline.run(heartbeat())
    print(info)


PIPELINES = {
    "heartbeat": run_heartbeat,
}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "heartbeat"
    if name not in PIPELINES:
        sys.exit(f"unknown pipeline '{name}' — options: {', '.join(PIPELINES)}")
    PIPELINES[name]()

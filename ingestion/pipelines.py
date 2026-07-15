"""dlt pipeline entrypoints — one pipeline per source, all loading to
the `raw` dataset. Destination: MotherDuck when MOTHERDUCK_TOKEN is
set (scheduled prod runs), otherwise a local DuckDB file (dev and CI).

Scheduled daily (.github/workflows/daily.yml):
    python ingestion/pipelines.py heartbeat
    python ingestion/pipelines.py statcast    # resumes from max(game_date) in warehouse
    python ingestion/pipelines.py statsapi    # sliding window + today's slate
    python ingestion/pipelines.py war         # season-to-date WAR snapshot

One-time backfill (run locally, season by season — see README):
    python ingestion/pipelines.py statcast --start 2021-03-15 --end 2021-11-05
    python ingestion/pipelines.py statsapi --start 2021-03-15 --end 2021-11-05
    python ingestion/pipelines.py war      --seasons 2021 2025
    python ingestion/pipelines.py coaches  --seasons 2021 2026
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import dlt

from sources import bref_war, mlb_statsapi, statcast

MD_DATABASE = "mlb_hits"
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local.duckdb"

# Cold-start guard: a scheduled statcast run with no explicit dates never
# attempts more than this many days (a multi-season backfill would blow
# past the Actions job limit — backfills pass --start/--end instead).
MAX_DAYS_PER_SCHEDULED_RUN = 21


def destination():
    token = os.getenv("MOTHERDUCK_TOKEN")
    if token:
        return dlt.destinations.motherduck(
            credentials=f"md:{MD_DATABASE}?motherduck_token={token}"
        )
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return dlt.destinations.duckdb(str(LOCAL_DB_PATH))


def _pipeline(source_name: str):
    return dlt.pipeline(
        pipeline_name=f"mlb_hits_{source_name}",
        destination=destination(),
        dataset_name="raw",
    )


@dlt.resource(table_name="heartbeat", write_disposition="append")
def heartbeat():
    yield {
        "run_at": datetime.now(timezone.utc),
        "runner": os.getenv("GITHUB_WORKFLOW", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "dev"),
    }


def run_heartbeat(args):
    print(_pipeline("heartbeat").run(heartbeat()))


def run_statcast(args):
    pipeline = _pipeline("statcast")
    yesterday = date.today() - timedelta(days=1)
    start = date.fromisoformat(args.start) if args.start else statcast.resume_date(pipeline)
    end = date.fromisoformat(args.end) if args.end else yesterday
    if not args.start and not args.end:
        end = min(end, start + timedelta(days=MAX_DAYS_PER_SCHEDULED_RUN))
    if start > end:
        print(f"statcast: warehouse current through {start}, nothing to fetch")
        return
    # load in ~4-week segments so each commits to the warehouse as it
    # completes — a crash costs at most one segment, and resume_date()
    # picks up right behind it
    seg_start = start
    while seg_start <= end:
        seg_end = min(seg_start + timedelta(days=27), end)
        print(f"statcast: fetching {seg_start} → {seg_end}")
        print(pipeline.run(statcast.pitches(seg_start, seg_end)))
        seg_start = seg_end + timedelta(days=1)


def run_statsapi(args):
    pipeline = _pipeline("statsapi")
    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
        resources = [
            mlb_statsapi.games(start, end),
            mlb_statsapi.batting_lines(start, end),
            mlb_statsapi.standings(start, end),
        ]
    else:
        today = date.today()
        resources = [
            # small overlapping window: catches reschedules and late
            # finals; staging keeps the latest-loaded row per key
            mlb_statsapi.games(today - timedelta(days=2), today + timedelta(days=1)),
            mlb_statsapi.batting_lines(today - timedelta(days=3), today),
            mlb_statsapi.standings(today - timedelta(days=3), today - timedelta(days=1)),
            mlb_statsapi.lineups(today),
        ]
    print(pipeline.run(resources))


def run_war(args):
    pipeline = _pipeline("bref_war")
    if args.seasons:
        start_season, end_season = args.seasons
        print(pipeline.run(bref_war.war_seasons(start_season, end_season)))
    else:
        print(pipeline.run(bref_war.war_snapshot()))


def run_coaches(args):
    if not args.seasons:
        sys.exit("coaches requires --seasons, e.g. --seasons 2021 2026")
    start_season, end_season = args.seasons
    seasons = list(range(start_season, end_season + 1))
    print(_pipeline("statsapi").run(mlb_statsapi.coaches(seasons)))


COMMANDS = {
    "heartbeat": run_heartbeat,
    "statcast": run_statcast,
    "statsapi": run_statsapi,
    "war": run_war,
    "coaches": run_coaches,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=COMMANDS)
    parser.add_argument("--start", help="backfill start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="backfill end date (YYYY-MM-DD)")
    parser.add_argument("--seasons", nargs=2, type=int,
                        metavar=("FIRST", "LAST"), help="season range")
    args = parser.parse_args()
    COMMANDS[args.source](args)


if __name__ == "__main__":
    main()

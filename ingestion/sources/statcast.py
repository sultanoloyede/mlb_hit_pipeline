"""Statcast pitch-level source (Baseball Savant via pybaseball).

Port of MLB_hits/scripts/1_fetch_statcast.py: weekly chunks with a
polite rate limit. Instead of file-per-week bookkeeping, the resume
point is the warehouse itself — max(game_date) already loaded. The raw
layer is append-only; overlapping fetches are deduped in dbt staging by
(game_pk, at_bat_number, pitch_number).
"""

import time
from datetime import date, timedelta

import dlt
import pandas as pd
from pybaseball import statcast

DEFAULT_START = "2021-03-01"
RATE_LIMIT_SEC = 8          # prototype-proven polite delay between chunks
CHUNK_DAYS = 7
MAX_RETRIES = 4             # Savant truncates responses under load
RETRY_BACKOFF_SEC = 15

# Curated subset of Savant's ~90 columns — covers every mart in
# PLAN.md §4 (batted-ball quality, plate discipline, expected stats,
# platoon, pitch type). Deprecated/duplicated columns are dropped to
# respect the 10 GB free tier.
#
# Dtypes are pinned explicitly: pybaseball infers types per fetch, so a
# chunk where a column is all-null (spring training, off-days) comes
# back int64 while the next is float64, and dlt's parquet writer
# refuses mixed schemas within a load.
INT_COLS = {
    "game_pk", "batter", "pitcher", "inning", "at_bat_number",
    "pitch_number", "outs_when_up", "balls", "strikes", "zone",
    "launch_speed_angle", "babip_value",
}
FLOAT_COLS = {
    "release_speed", "woba_value", "launch_speed", "launch_angle",
    "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
    "estimated_slg_using_speedangle",
}
STR_COLS = {
    "game_date", "game_type", "home_team", "away_team", "player_name",
    "stand", "p_throws", "inning_topbot", "pitch_type", "type",
    "description", "events", "bb_type",
}
KEEP_COLS = [
    "game_pk", "game_date", "game_type", "home_team", "away_team",
    "batter", "pitcher", "player_name", "stand", "p_throws",
    "inning", "inning_topbot", "at_bat_number", "pitch_number",
    "outs_when_up", "balls", "strikes",
    "pitch_type", "release_speed", "zone", "type", "description",
    "events", "bb_type", "woba_value", "babip_value",
    "launch_speed", "launch_angle", "launch_speed_angle",
    "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
    "estimated_slg_using_speedangle",
]


def _stable_types(df: pd.DataFrame) -> pd.DataFrame:
    """Reindex to the full column set (missing columns become null) and
    pin every dtype so all chunks share one arrow schema."""
    df = df.reindex(columns=KEEP_COLS)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    for col in INT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    for col in STR_COLS:
        df[col] = df[col].astype("string")
    return df


def resume_date(pipeline) -> date:
    """Max game_date already in the warehouse (refetched inclusively so a
    partially loaded day completes; staging dedupes). Falls back to
    DEFAULT_START on a cold warehouse."""
    try:
        with pipeline.sql_client() as client:
            rows = client.execute_sql("select max(game_date) from statcast_pitches")
        if rows and rows[0][0]:
            return date.fromisoformat(str(rows[0][0])[:10])
    except Exception:
        pass
    return date.fromisoformat(DEFAULT_START)


def _chunks(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur, min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        cur = cur + timedelta(days=CHUNK_DAYS)


def _fetch_chunk(chunk_start: date, chunk_end: date):
    """statcast() with retries: Savant intermittently truncates the CSV
    mid-stream (pandas 'EOF inside string') — refetching succeeds."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return statcast(start_dt=chunk_start.isoformat(),
                            end_dt=chunk_end.isoformat())
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF_SEC * attempt
            print(f"statcast {chunk_start} → {chunk_end}: attempt {attempt} "
                  f"failed ({type(exc).__name__}: {exc}); retrying in {wait}s")
            time.sleep(wait)


@dlt.resource(table_name="statcast_pitches", write_disposition="append")
def pitches(start: date, end: date):
    for chunk_start, chunk_end in _chunks(start, end):
        df = _fetch_chunk(chunk_start, chunk_end)
        if df is None or df.empty:
            time.sleep(RATE_LIMIT_SEC)
            continue
        df = _stable_types(df.copy())
        print(f"statcast {chunk_start} → {chunk_end}: {len(df)} pitches")
        yield df
        time.sleep(RATE_LIMIT_SEC)

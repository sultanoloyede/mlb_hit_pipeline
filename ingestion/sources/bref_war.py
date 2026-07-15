"""Batter WAR source — Baseball-Reference's published war_daily_bat.txt.

Replaces FanGraphs, whose site AND json api sit behind Cloudflare TLS
fingerprinting (403 for any non-browser client). Sports-Reference
publishes WAR as a plain CSV explicitly for download, updated daily
in-season, and it carries mlb_ID — a direct join to our Stats API /
Statcast batter ids, no name crosswalk needed.

Team pitching quality (research factors #22/#23) is computed as-of-date
from our own warehouse in dbt instead — season-level leaderboard
aggregates were the lookahead trap the plan warned about anyway.

Two shapes, same file:
  bref_war_bat_seasons    — player-seasons for a year range (backfill)
  bref_war_bat_snapshots  — current season-to-date stamped with
                            snapshot_date, appended daily (point-in-time
                            WAR for live features)
"""

import io
from datetime import date

import dlt
import pandas as pd
from dlt.sources.helpers import requests

URL = "https://www.baseball-reference.com/data/war_daily_bat.txt"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}
ID_COLS = {"mlb_ID", "year_ID", "stint_ID"}


def _fetch(min_season: int, max_season: int) -> pd.DataFrame:
    resp = requests.get(URL, headers=HEADERS)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
    df = df.replace("NULL", pd.NA)
    df["year_ID"] = pd.to_numeric(df["year_ID"], errors="coerce")
    df = df[df["year_ID"].between(min_season, max_season)].copy()
    # pin dtypes: the file ships numbers as strings with NULL sentinels
    for col in df.columns:
        if col in ID_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() >= df[col].notna().sum() * 0.99:
            df[col] = converted.astype("float64")
        else:
            df[col] = df[col].astype("string")
    return df


@dlt.resource(table_name="bref_war_bat_seasons", write_disposition="append")
def war_seasons(start_season: int, end_season: int):
    yield _fetch(start_season, end_season)


@dlt.resource(table_name="bref_war_bat_snapshots", write_disposition="append")
def war_snapshot():
    season = date.today().year
    df = _fetch(season, season)
    df["snapshot_date"] = date.today().isoformat()
    yield df

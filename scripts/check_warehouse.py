"""Quick warehouse sanity check: row counts and date coverage of the
raw tables in MotherDuck.

Usage (from the repo root):
    python scripts/check_warehouse.py
Reads MOTHERDUCK_TOKEN from the environment, falling back to .env.
"""

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent

CHECKS = {
    "statcast_pitches": "game_date",
    "games": "official_date",
    "batting_lines": "official_date",
    "standings": "standings_date",
    "bref_war_bat_seasons": "year_ID",
    "coaches": "season",
}


def token() -> str:
    if os.getenv("MOTHERDUCK_TOKEN"):
        return os.environ["MOTHERDUCK_TOKEN"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("MOTHERDUCK_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("MOTHERDUCK_TOKEN not set (export it or put it in .env)")


def main():
    con = duckdb.connect(f"md:mlb_hits?motherduck_token={token()}")
    for table, col in CHECKS.items():
        try:
            n, lo, hi = con.execute(
                f"select count(*), min({col}), max({col}) from raw.{table}"
            ).fetchone()
            print(f"{table:26} {n:>12,}   {lo} → {hi}")
        except Exception as exc:
            print(f"{table:26} MISSING ({type(exc).__name__})")


if __name__ == "__main__":
    main()

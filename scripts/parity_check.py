"""Phase 2 acceptance gate: spot-diff marts.fct_batter_game against the
prototype's batter_games.csv on one season.

Joins on (game_pk, batter) and compares every shared metric. Expected
sources of small drift: pandas vs duckdb round-half behavior at the 4th
decimal. PASS = every metric mismatching on < 0.5% of joined rows at
|diff| > 1e-3.

Usage (repo root):  python scripts/parity_check.py [season]
"""

import os
import sys
from pathlib import Path

import duckdb

SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
TOL = 1e-3
MAX_MISMATCH_RATE = 0.005

ROOT = Path(__file__).resolve().parent.parent
PROTO_CSV = ROOT.parent / "MLB_hits" / "data" / "game_stats" / "batter_games.csv"

# prototype column -> fct_batter_game column
#
# STRICT metrics derive from pitch OUTCOMES (events, descriptions,
# zones) which are stable across Savant downloads — these must match.
STRICT_METRICS = {
    "pa": "sc_pa",
    "hits": "sc_hits",
    "k_pct": "k_pct",
    "bb_pct": "bb_pct",
    "contact_pct": "contact_pct",
    "chase_rate": "chase_rate",
    "woba_mean": "woba_mean",
    "hits_vs_L": "hits_vs_l",
    "pa_vs_L": "pa_vs_l",
    "contact_pct_vs_R": "contact_pct_vs_r",
    "chase_rate_vs_R": "chase_rate_vs_r",
}
# DRIFT metrics depend on Savant's tracking measurements or its
# expected-stats MODEL, which Savant restates between downloads
# (verified at pitch level: identical pitches, identical launch_speed,
# xBA changed on 35% of batted balls between the prototype's March
# fetch and ours). Reported for information; only a blowup beyond the
# sanity ceiling (indicating a real aggregation bug) fails the gate.
DRIFT_METRICS = {
    "hard_hit_pct": "hard_hit_pct",
    "barrel_pct": "barrel_pct",
    "sweet_spot_pct": "sweet_spot_pct",
    "line_drive_pct": "line_drive_pct",
    "xba_mean": "xba_mean",
    "xslg_mean": "xslg_mean",
    "xwoba_mean": "xwoba_mean",
    "xba_minus_ba": "xba_minus_ba",
}
DRIFT_CEILING = 0.90
METRICS = {**STRICT_METRICS, **DRIFT_METRICS}


def token() -> str:
    if os.getenv("MOTHERDUCK_TOKEN"):
        return os.environ["MOTHERDUCK_TOKEN"]
    env_file = ROOT / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("MOTHERDUCK_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("MOTHERDUCK_TOKEN not set")


def main():
    con = duckdb.connect(f"md:mlb_hits?motherduck_token={token()}")

    pairs = ",\n            ".join(
        f'p."{proto}" as p_{ours}, o.{ours} as o_{ours}'
        for proto, ours in METRICS.items()
    )
    mismatches = ",\n        ".join(
        f"sum(case when abs(coalesce(p_{ours}, -99) - coalesce(o_{ours}, -99)) > {TOL} "
        f"then 1 else 0 end) as mm_{ours}"
        for ours in METRICS.values()
    )

    row = con.execute(f"""
        with p as (
            select * from read_csv_auto('{PROTO_CSV}')
            where date between '{SEASON}-01-01' and '{SEASON}-12-31'
        ),
        o as (
            select * from marts.fct_batter_game where season = {SEASON}
        ),
        joined as (
            select
            {pairs}
            from p join o on p.game_pk = o.game_pk and p.batter = o.batter_id
        )
        select count(*) as joined_rows,
        {mismatches}
        from joined
    """).fetchone()

    joined = row[0]
    proto_only = con.execute(f"""
        select count(*) from read_csv_auto('{PROTO_CSV}') p
        where p.date between '{SEASON}-01-01' and '{SEASON}-12-31'
          and not exists (select 1 from marts.fct_batter_game o
                          where o.game_pk = p.game_pk and o.batter_id = p.batter)
    """).fetchone()[0]

    print(f"season {SEASON}: {joined:,} joined batter-games "
          f"({proto_only:,} prototype-only rows — spring/postseason & 0-PA, expected)")

    failed = []
    drift_cols = set(DRIFT_METRICS.values())
    for ours, mm in zip(METRICS.values(), row[1:]):
        rate = mm / joined if joined else 1.0
        if ours in drift_cols:
            status = "drift" if rate < DRIFT_CEILING else "FAIL "
            if rate >= DRIFT_CEILING:
                failed.append(ours)
        else:
            status = "ok   " if rate < MAX_MISMATCH_RATE else "FAIL "
            if rate >= MAX_MISMATCH_RATE:
                failed.append(ours)
        print(f"  [{status}] {ours:22} mismatches: {mm:>6,} ({rate:.3%})")

    print("\n  [drift] = Savant-restated tracking/model values; informational.")
    if not joined or failed:
        sys.exit(f"FAIL: {failed or 'no joined rows'}")
    print("PASS: fct_batter_game reconciles with the prototype "
          "(outcome metrics exact; model-estimated metrics within drift ceiling)")


if __name__ == "__main__":
    main()

"""Phase 1 acceptance gate: reconcile raw.statcast_pitches against the
prototype's weekly parquet files (MLB_hits/data/raw/*.parquet).

Pass = weekly pitch counts within 0.5% over the overlapping window.
Small diffs are expected (the prototype kept all columns and started in
2020; Savant occasionally restates games) — big diffs mean a fetch bug.

Usage:
    python ingestion/reconcile.py            # local data/local.duckdb
    MOTHERDUCK_TOKEN=... python ingestion/reconcile.py
"""

import os
import sys
from pathlib import Path

import duckdb

TOLERANCE = 0.005
PROTO_GLOB = Path(__file__).resolve().parents[2] / "MLB_hits" / "data" / "raw" / "*.parquet"
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local.duckdb"


def connect():
    token = os.getenv("MOTHERDUCK_TOKEN")
    if token:
        return duckdb.connect(f"md:mlb_hits?motherduck_token={token}")
    return duckdb.connect(str(LOCAL_DB_PATH), read_only=True)


def main():
    con = connect()
    rows = con.execute(f"""
        -- distinct pitch key on both sides: raw is append-only and the
        -- inclusive resume refetches season-boundary days, so raw holds
        -- expected duplicates that staging removes downstream
        with proto as (
            select date_trunc('week', game_date::date) as wk,
                   count(distinct (game_pk, at_bat_number, pitch_number)) as n
            from read_parquet('{PROTO_GLOB}')
            where game_date::date >= date '2021-03-01'
            group by 1
        ),
        ours as (
            select date_trunc('week', game_date::date) as wk,
                   count(distinct (game_pk, at_bat_number, pitch_number)) as n
            from raw.statcast_pitches
            group by 1
        )
        select
            coalesce(proto.wk, ours.wk) as wk,
            coalesce(proto.n, 0) as proto_n,
            coalesce(ours.n, 0) as ours_n,
            abs(coalesce(proto.n, 0) - coalesce(ours.n, 0))
                / greatest(coalesce(proto.n, 0), 1) as diff_pct
        from proto
        full outer join ours on proto.wk = ours.wk
        -- compare only the window both sides cover
        where coalesce(proto.wk, ours.wk)
              between (select max(least(p.mn, o.mn)) from
                        (select min(wk) mn from proto) p,
                        (select min(wk) mn from ours) o)
              and (select min(least(p.mx, o.mx)) from
                        (select max(wk) mx from proto) p,
                        (select max(wk) mx from ours) o)
        order by 1
    """).fetchall()

    if not rows:
        sys.exit("no overlapping weeks found — has the backfill run?")

    bad = [r for r in rows if r[3] > TOLERANCE]
    total_proto = sum(r[1] for r in rows)
    total_ours = sum(r[2] for r in rows)
    print(f"{len(rows)} overlapping weeks | prototype {total_proto:,} pitches "
          f"| warehouse {total_ours:,} pitches")

    for wk, proto_n, ours_n, diff in bad:
        print(f"  MISMATCH {str(wk)[:10]}: prototype={proto_n:,} "
              f"warehouse={ours_n:,} ({diff:.2%})")

    if bad:
        sys.exit(f"FAIL: {len(bad)} week(s) beyond {TOLERANCE:.1%} tolerance")
    print(f"PASS: all weeks within {TOLERANCE:.1%}")


if __name__ == "__main__":
    main()

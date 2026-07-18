"""Phase 6 predict stage: score the slate and append to
output.predictions (append-only — every run keeps its run_ts, the
backtest grades exactly what was shown, revisions never overwrite).

Steps:
  1. dbt builds ml.feat_slate for the slate date (posted lineups where
     available, projected batting orders otherwise)
  2. load the deployment bundle (models/production/, exported from the
     MLflow registry by train.py)
  3. score, append to output.predictions with run_ts + model version +
     lineup_confirmed

Usage (repo root):
    python ml/predict.py                  # today's slate
    python ml/predict.py --date 2026-07-12  # backdated (point-in-time safe)
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

BUNDLE_DIR = common.ROOT / "models" / "production"
TRANSFORM_DIR = common.ROOT / "transform"


def build_feat_slate(slate_date: str):
    cmd = ["dbt", "build", "--profiles-dir", ".", "--target", "prod",
           "--select", "feat_slate",
           "--vars", json.dumps({"slate_date": slate_date})]
    subprocess.run(cmd, cwd=TRANSFORM_DIR, check=True,
                   stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    print(f"predict: building slate features for {args.date}")
    build_feat_slate(args.date)

    con = duckdb.connect(f"md:mlb_hits?motherduck_token={common.token()}")
    slate = con.execute("select * from ml.feat_slate").df()
    if slate.empty:
        print(f"no games on {args.date} — nothing to score")
        return

    params = common.load_params()
    frame = common.prepare(slate, params)
    if frame.empty:
        print("slate rows exist but none survived the universe filter")
        return

    bundle = joblib.load(BUNDLE_DIR / "hit_model.joblib")
    meta = json.loads((BUNDLE_DIR / "meta.json").read_text())
    frame["p_hit"] = bundle.predict(frame)

    out = frame[[
        "game_pk", "batter_id", "player_name", "team_id", "opponent_team_id",
        "batting_order_slot", "lineup_confirmed", "opp_starter_id", "p_hit",
    ]].copy()
    out.insert(0, "slate_date", args.date)
    out.insert(0, "run_ts", datetime.now(timezone.utc))
    out["model_version"] = f"{meta['model_name']}:v{meta['version']}"

    con.execute("create schema if not exists output")
    con.execute("""
        create table if not exists output.predictions (
            run_ts timestamp, slate_date date, game_pk bigint,
            batter_id bigint, player_name varchar, team_id bigint,
            opponent_team_id bigint, batting_order_slot integer,
            lineup_confirmed boolean, opp_starter_id bigint,
            p_hit double, model_version varchar
        )
    """)
    con.register("out_df", out)
    con.execute("insert into output.predictions select * from out_df")

    confirmed = out["lineup_confirmed"].mean()
    print(f"scored {len(out)} batters across {out['game_pk'].nunique()} games "
          f"({confirmed:.0%} from posted lineups) with {out['model_version'].iloc[0]}")
    top = out.nlargest(10, "p_hit")[["player_name", "batting_order_slot", "p_hit"]]
    print("\ntop 10:")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()

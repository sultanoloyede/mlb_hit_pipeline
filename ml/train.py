"""Phase 4 trainer: baselines -> structural per-PA model -> direct
LightGBM -> isotonic calibration, evaluated on the held-out second half
of the calibration season, tracked in MLflow, winner registered.

Gates (PLAN.md phase 4):
  - winner must beat the EB-shrunk baseline on BOTH log loss and Brier
  - isotonic calibration must not worsen Brier
Exit code is non-zero if a gate fails.

Usage (repo root):  python ml/train.py [--refresh]
"""

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from common import HitModel, HitModelPyfunc

REPORT = common.ROOT / "reports" / "model_report.md"


def X_of(d: pd.DataFrame, cols) -> pd.DataFrame:
    return d[cols].astype(float)


def fit_logistic(d, cols, y, w, C):
    pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(C=C, max_iter=2000)),
    ])
    pipe.fit(X_of(d, cols), y, lr__sample_weight=w)
    return pipe


def fit_ppa(train, cols, w, C):
    """Per-PA hit probability via the binomial expansion trick: each
    game contributes a success row weighted by hits and a failure row
    weighted by (pa - hits)."""
    X = pd.concat([X_of(train, cols)] * 2, ignore_index=True)
    y = np.r_[np.ones(len(train)), np.zeros(len(train))]
    sw = np.r_[train["hits"].to_numpy() * w,
               (train["pa"] - train["hits"]).clip(lower=0).to_numpy() * w]
    pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(C=C, max_iter=2000)),
    ])
    pipe.fit(X, y, lr__sample_weight=sw)
    return pipe


def md_table(df: pd.DataFrame, floatfmt="{:.4f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = [floatfmt.format(v) if isinstance(v, float) and not pd.isna(v)
                 else str(v) for v in r]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    params = common.load_params()
    feats = params["features"]
    df = common.prepare(common.load_frame("--refresh" in sys.argv), params)

    # ── temporal splits ──────────────────────────────────────────────
    sp = params["splits"]
    train = df[df["season"].isin(sp["train_seasons"])].copy()
    calib = df[df["season"] == sp["calib_season"]].copy()
    mid = calib["game_date"].quantile(0.5)
    calib_fit = calib[calib["game_date"] <= mid]
    calib_eval = calib[calib["game_date"] > mid].reset_index(drop=True)

    tail_start = train["game_date"].max() - pd.Timedelta(days=sp["early_stop_tail_days"])
    emb = tail_start - pd.Timedelta(days=sp["embargo_days"])
    train_fit = train[train["game_date"] <= emb]
    train_tail = train[train["game_date"] > tail_start]

    w_train = common.recency_weights(train["game_date"], params["recency_half_life_days"])
    w_fit = common.recency_weights(train_fit["game_date"], params["recency_half_life_days"])
    y_eval = calib_eval["has_hit"].to_numpy()
    print(f"train {len(train):,} | calib_fit {len(calib_fit):,} | "
          f"calib_eval {len(calib_eval):,}")

    preds, models = {}, {}

    # ── baselines ────────────────────────────────────────────────────
    preds["league"] = np.full(len(calib_eval), train["has_hit"].mean())

    pa_exp = calib_eval["pa_roll10"].fillna(train["pa_roll10"].median()).clip(1, 6)
    preds["eb_pa"] = 1 - (1 - calib_eval["eb_hit_per_pa_career"]) ** pa_exp

    logi = fit_logistic(train, feats["baseline_logistic"],
                        train["has_hit"], w_train, params["logistic"]["C"])
    preds["logistic"] = logi.predict_proba(X_of(calib_eval, feats["baseline_logistic"]))[:, 1]

    # ── structural per-PA model ──────────────────────────────────────
    ppa_pipe = fit_ppa(train, feats["ppa"], w_train, params["logistic"]["C"])
    epa = lgb.LGBMRegressor(**params["epa_lightgbm"], verbose=-1)
    epa.fit(X_of(train, feats["epa"]), train["pa"], sample_weight=w_train)
    structural = HitModel("structural", feats, ppa_pipe=ppa_pipe, epa_model=epa)
    preds["structural_raw"] = structural.predict_raw(calib_eval)

    # ── direct LightGBM ──────────────────────────────────────────────
    lgbm_params = {k: v for k, v in params["lightgbm"].items()
                   if k != "early_stopping_rounds"}
    gbm = lgb.LGBMClassifier(objective="binary", verbose=-1, **lgbm_params)
    gbm.fit(X_of(train_fit, feats["gbm"]), train_fit["has_hit"],
            sample_weight=w_fit,
            eval_set=[(X_of(train_tail, feats["gbm"]), train_tail["has_hit"])],
            callbacks=[lgb.early_stopping(params["lightgbm"]["early_stopping_rounds"],
                                          verbose=False)])
    gbm_model = HitModel("gbm", feats, model=gbm)
    preds["gbm_raw"] = gbm_model.predict_raw(calib_eval)

    # ── isotonic calibration (fit on calib_fit, applied to eval) ─────
    for name, hm in (("structural", structural), ("gbm", gbm_model)):
        raw_fit = hm.predict_raw(calib_fit)
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw_fit, calib_fit["has_hit"])
        hm.iso = iso
        preds[f"{name}_cal"] = hm.predict(calib_eval)
        models[f"{name}_cal"] = hm

    # ── scoreboard on calib_eval ─────────────────────────────────────
    rows = []
    for name, p in preds.items():
        r = {"model": name, **common.metric_row(y_eval, p)}
        r.update(common.top_k_rates(calib_eval, np.asarray(p), params["eval"]["top_k"]))
        rows.append(r)
    board = pd.DataFrame(rows).sort_values("log_loss")
    print("\n" + board.to_string(index=False))

    # ── gates ────────────────────────────────────────────────────────
    candidates = board[board["model"].isin(["structural_cal", "gbm_cal"])]
    winner_name = candidates.iloc[0]["model"]
    winner = models[winner_name]
    base = board.set_index("model").loc[params["gates"]["baseline_to_beat"]]
    win = board.set_index("model").loc[winner_name]
    raw = board.set_index("model").loc[winner_name.replace("_cal", "_raw")]

    failures = []
    if not (win["log_loss"] < base["log_loss"] and win["brier"] < base["brier"]):
        failures.append(f"{winner_name} does not beat {params['gates']['baseline_to_beat']}")
    if win["brier"] > raw["brier"] + params["gates"]["calibration_max_brier_increase"]:
        failures.append("isotonic worsened Brier")

    # ── tier report ──────────────────────────────────────────────────
    tiers = common.tier_table(
        calib_eval,
        {"winner": np.asarray(preds[winner_name]),
         "eb_pa": np.asarray(preds["eb_pa"], dtype=float)},
        params)

    # ── mlflow tracking + registry ───────────────────────────────────
    mlflow = common.mlflow_setup()
    for _, r in board.iterrows():
        with mlflow.start_run(run_name=r["model"]):
            mlflow.log_params({"universe": "starters", **params["splits"]})
            mlflow.log_metrics({k: float(r[k]) for k in r.index if k != "model"})

    version = None
    if not failures:
        # Selection and gates used the calib_fit/calib_eval half-split.
        # The SHIPPED artifact refits isotonic on ALL of CALIB: the low-
        # probability tail is sparse and a half-season leaves it badly
        # estimated (caught by the Phase 5 calibration gate).
        iso_full = IsotonicRegression(out_of_bounds="clip")
        iso_full.fit(winner.predict_raw(calib), calib["has_hit"])
        winner.iso = iso_full
        with mlflow.start_run(run_name=f"winner_{winner_name}") as run:
            mlflow.log_params({"winner": winner_name,
                               "n_features": len(feats["gbm" if winner.kind == "gbm" else "ppa"])})
            mlflow.log_metrics({k: float(win[k]) for k in win.index})
            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=HitModelPyfunc(winner),
                code_paths=[str(Path(__file__).resolve().parent / "common.py")])
            mv = mlflow.register_model(f"runs:/{run.info.run_id}/model", common.MODEL_NAME)
            version = mv.version
        from mlflow import MlflowClient
        MlflowClient().set_registered_model_alias(common.MODEL_NAME, "production", version)

    # ── report ───────────────────────────────────────────────────────
    lines = [
        "# Model report (Phase 4)", "",
        f"Universe: starters, {sp['train_seasons']} train / {sp['calib_season']} calibrate.",
        f"Evaluation: second half of {sp['calib_season']} ({len(calib_eval):,} batter-games, "
        f"base rate {y_eval.mean():.3f}).", "",
        "## Scoreboard", "", md_table(board), "",
        f"**Winner: `{winner_name}`**"
        + (f" — registered as `{common.MODEL_NAME}` v{version} (alias `production`)."
           if version else ""), "",
        "## Gates", "",
        "PASS — beats the EB baseline on log loss + Brier; calibration held."
        if not failures else "FAIL — " + "; ".join(failures), "",
        "## Per-tier log loss (winner vs EB baseline)", "", md_table(tiers), "",
    ]
    REPORT.write_text("\n".join(lines))
    print(f"\nreport -> {REPORT}")

    if failures:
        sys.exit("GATE FAIL: " + "; ".join(failures))
    print(f"PASS — {winner_name} registered as {common.MODEL_NAME} "
          f"v{version} (alias 'production')")


if __name__ == "__main__":
    main()

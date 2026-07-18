"""Shared plumbing for the ML plane: data loading, universe filter,
metrics, tier reports, MLflow setup, and the pyfunc model wrapper the
registry stores (predict.py loads it back in Phase 6).
"""

import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "model_frame.parquet"
PARAMS_PATH = Path(__file__).resolve().parent / "params.yaml"

MLFLOW_DB = ROOT / "ml" / "mlflow.db"
MODEL_NAME = "mlb_hits_hit_model"


def load_params() -> dict:
    return yaml.safe_load(PARAMS_PATH.read_text())


def token() -> str:
    if os.getenv("MOTHERDUCK_TOKEN"):
        return os.environ["MOTHERDUCK_TOKEN"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("MOTHERDUCK_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("MOTHERDUCK_TOKEN not set")


def load_frame(refresh: bool = False) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    con = duckdb.connect(f"md:mlb_hits?motherduck_token={token()}")
    df = con.execute("select * from ml.feat_batter_game").df()
    CACHE.parent.mkdir(exist_ok=True)
    df.to_parquet(CACHE)
    return df


def prepare(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Universe filter + derived encodings, sorted chronologically."""
    d = df.copy()
    if params["universe"]["starters_only"]:
        d = d[d["batting_order_slot"].notna() & ~d["is_substitute"].fillna(False)]
    d["is_vs_lhp"] = (d["opp_starter_throws"] == "L").astype(float)
    d["is_home"] = d["is_home"].astype(float)
    d["game_date"] = pd.to_datetime(d["game_date"])
    return d.sort_values(["game_date", "game_pk"]).reset_index(drop=True)


def recency_weights(dates: pd.Series, half_life_days: int) -> np.ndarray:
    age = (dates.max() - dates).dt.days.to_numpy()
    return 0.5 ** (age / half_life_days)


def metric_row(y, p) -> dict:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return {
        "log_loss": log_loss(y, p),
        "brier": brier_score_loss(y, p),
        "auc": roc_auc_score(y, p),
        "n": len(y),
    }


def top_k_rates(eval_df: pd.DataFrame, p: np.ndarray, ks) -> dict:
    """Daily top-K pick hit rate — the product surface."""
    d = eval_df[["game_date", "has_hit"]].copy()
    d["p"] = p
    out = {}
    for k in ks:
        picks = (d.sort_values("p", ascending=False)
                  .groupby(d["game_date"].dt.date, sort=False)
                  .head(k))
        out[f"top{k}_hit_rate"] = picks["has_hit"].mean()
    return out


def tier_table(eval_df: pd.DataFrame, preds: dict, params: dict) -> pd.DataFrame:
    """Log loss by player-quality quartile and expected-PA band, per
    model — the 'does it only work for stars?' report."""
    d = eval_df.copy()
    d["quality"] = pd.qcut(d[params["eval"]["tier_col"]], 4,
                           labels=["Q1 weakest", "Q2", "Q3", "Q4 strongest"])
    d["pa_band"] = pd.cut(d[params["eval"]["pa_band_col"]],
                          [0, 3.5, 4.2, 10], labels=["<3.5", "3.5-4.2", ">4.2"])
    rows = []
    for dim in ["quality", "pa_band"]:
        for level, g in d.groupby(dim, observed=True):
            row = {"dimension": dim, "level": str(level), "n": len(g),
                   "base_rate": g["has_hit"].mean()}
            for name, p in preds.items():
                pv = np.clip(p[g.index.to_numpy()], 1e-6, 1 - 1e-6)
                row[f"logloss_{name}"] = log_loss(g["has_hit"], pv)
            rows.append(row)
    return pd.DataFrame(rows)


def mlflow_setup():
    import mlflow
    mlflow.set_tracking_uri(f"sqlite:///{MLFLOW_DB}")
    mlflow.set_experiment("mlb_hits")
    return mlflow


class HitModel:
    """Registry artifact: calibrated model + feature contract, one
    predict() regardless of family. Wrapped for mlflow.pyfunc."""

    def __init__(self, kind: str, features: dict, model=None,
                 ppa_pipe=None, epa_model=None, iso=None):
        self.kind = kind                  # 'gbm' | 'structural'
        self.features = features          # {'gbm': [...]} or {'ppa': [...], 'epa': [...]}
        self.model = model
        self.ppa_pipe = ppa_pipe
        self.epa_model = epa_model
        self.iso = iso

    def predict_raw(self, X: pd.DataFrame) -> np.ndarray:
        if self.kind == "gbm":
            return self.model.predict_proba(X[self.features["gbm"]])[:, 1]
        p_pa = np.clip(self.ppa_pipe.predict_proba(X[self.features["ppa"]])[:, 1],
                       0.02, 0.55)
        e_pa = np.clip(self.epa_model.predict(X[self.features["epa"]]), 1.0, 6.5)
        return 1.0 - (1.0 - p_pa) ** e_pa

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        p = self.predict_raw(X)
        if self.iso is not None:
            p = self.iso.predict(p)
        return np.clip(p, 1e-6, 1 - 1e-6)


import mlflow.pyfunc


class HitModelPyfunc(mlflow.pyfunc.PythonModel):
    """mlflow.pyfunc adapter around HitModel."""

    def __init__(self, hit_model: HitModel):
        self.hit_model = hit_model

    def predict(self, context, model_input: pd.DataFrame, params=None):
        return self.hit_model.predict(model_input)

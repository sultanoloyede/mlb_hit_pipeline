"""Phase 5 backtest: replay the TEST season(s) with the frozen
production model and point-in-time features.

Because every feature row is strictly point-in-time (Phase 2 leakage
test) and the model is frozen (no refits inside TEST), scoring all rows
at once is exactly equivalent to an event-driven day-by-day replay.

Report sections (PLAN.md §8):
  1. calibration buckets  — gate: every bucket with n>=300 within ±3pts
  2. top-K daily picks    — gate: model top-5 beats the season-BA pick
  4. slices               — month, quality tier, home/away
(§8.3 ROI-at-odds arrives with odds data in Phase 8. The
confirmed-vs-projected-lineup slice needs live predictions — Phase 6+.)

Every run is logged to MLflow; the number of prior backtest runs is the
data-snooping ledger (one TEST season exists — every peek spends it).

Usage (repo root):  python ml/backtest.py [--refresh]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import common
import factor_lab as lab
import matplotlib.pyplot as plt

REPORT = common.ROOT / "reports" / "backtest_report.md"
EDA = common.ROOT / "reports" / "eda"
CAL_GATE_PTS = 0.03
CAL_GATE_MIN_N = 300
BA_BENCH_MIN_PA = 50


def md_table(df: pd.DataFrame, fmt="{:.4f}") -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(
            fmt.format(v) if isinstance(v, float) and not pd.isna(v) else str(v)
            for v in r) + " |")
    return "\n".join(out)


def calibration_buckets(y, p):
    d = pd.DataFrame({"y": y, "p": p})
    d["bucket"] = (d["p"] * 20).astype(int) / 20          # 5-point bins
    g = d.groupby("bucket").agg(n=("y", "size"), pred=("p", "mean"),
                                obs=("y", "mean")).reset_index()
    g["gap"] = g["obs"] - g["pred"]
    return g


def top_k_picks(df, score_col, k):
    ranked = (df.sort_values(score_col, ascending=False)
                .groupby(df["game_date"].dt.date, sort=True).head(k))
    return ranked.sort_values(["game_date", score_col], ascending=[True, False])


def longest_miss_streak(outcomes) -> int:
    worst = cur = 0
    for o in outcomes:
        cur = cur + 1 if o == 0 else 0
        worst = max(worst, cur)
    return worst


def main():
    params = common.load_params()
    df = common.prepare(common.load_frame("--refresh" in sys.argv), params)
    test = df[df["season"].isin(params["splits"]["test_seasons"])].reset_index(drop=True)
    if test.empty:
        sys.exit("no TEST rows in the frame — refresh with --refresh")

    mlflow = common.mlflow_setup()
    model = mlflow.pyfunc.load_model(f"models:/{common.MODEL_NAME}@production")
    p = np.asarray(model.predict(test), dtype=float)
    y = test["has_hit"].to_numpy()

    # snooping ledger
    prior = len(mlflow.search_runs(
        filter_string="tags.mlflow.runName LIKE 'backtest%'"))

    overall = common.metric_row(y, p)
    eb_pa = 1 - (1 - test["eb_hit_per_pa_career"]) ** \
        test["pa_roll10"].fillna(test["pa_roll10"].median()).clip(1, 6)
    eb_metrics = common.metric_row(y, eb_pa)

    # ── 1. calibration buckets ───────────────────────────────────────
    cal = calibration_buckets(y, p)
    gated = cal[cal["n"] >= CAL_GATE_MIN_N]
    cal_ok = (gated["gap"].abs() <= CAL_GATE_PTS).all()

    fig, axes = lab.new_fig(1, width=6.4, height=5.2)
    ax = axes[0]
    lims = (min(cal["pred"].min(), cal["obs"].min()) - 0.03,
            max(cal["pred"].max(), cal["obs"].max()) + 0.03)
    ax.plot(lims, lims, color=lab.BASELINE, linewidth=1.0, linestyle="--")
    ax.plot(gated["pred"], gated["obs"], color=lab.BLUE, linewidth=2.0, zorder=3)
    ax.scatter(gated["pred"], gated["obs"],
               s=np.sqrt(gated["n"]), color=lab.BLUE, zorder=4)
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_xlabel("predicted P(≥1 hit)", color=lab.SEC, fontsize=9)
    ax.set_ylabel("observed rate", color=lab.SEC, fontsize=9)
    fig.suptitle("Backtest calibration — 2026 to date", color=lab.INK,
                 fontsize=12, x=0.02, ha="left", fontweight="bold")
    fig.text(0.02, 0.005, f"marker size ∝ √n · gate ±{CAL_GATE_PTS:.0%} on "
             f"buckets with n≥{CAL_GATE_MIN_N}", color=lab.SEC, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(EDA / "backtest_calibration.png", dpi=150, facecolor=lab.SURFACE)
    plt.close(fig)

    # ── 2. top-K picks vs benchmarks ─────────────────────────────────
    test["p_model"] = p
    test["ba_bench"] = np.where(test["season_pa_prior"] >= BA_BENCH_MIN_PA,
                                test["season_hits_prior"] / test["season_pa_prior"].clip(lower=1),
                                -1.0)
    test["eb_bench"] = test["eb_hit_per_pa_career"]

    topk_rows, curves = [], {}
    for k in params["eval"]["top_k"]:
        for name, col in [("model", "p_model"), ("season_ba", "ba_bench"),
                          ("eb_shrunk", "eb_bench")]:
            picks = top_k_picks(test, col, k)
            row = {"k": k, "picker": name,
                   "picks": len(picks),
                   "hit_rate": picks["has_hit"].mean(),
                   "worst_miss_streak": longest_miss_streak(picks["has_hit"].to_numpy())}
            topk_rows.append(row)
            if k == 5:
                daily = picks.groupby(picks["game_date"].dt.date)["has_hit"].mean()
                curves[name] = daily.expanding().mean()
    topk = pd.DataFrame(topk_rows)

    fig, axes = lab.new_fig(1, width=9.0, height=4.6)
    ax = axes[0]
    colors = {"model": lab.BLUE, "season_ba": "#eda100", "eb_shrunk": "#1baf7a"}
    for name, curve in curves.items():
        x = pd.to_datetime(curve.index)
        ax.plot(x, curve.values, color=colors[name], linewidth=2.0, label=name)
        ax.text(x[-1], curve.values[-1], f" {name} {curve.values[-1]:.1%}",
                color=colors[name], fontsize=8.5, va="center")
    ax.axhline(0.71, color=lab.MUTED, linewidth=1.0, linestyle="--")
    ax.text(pd.to_datetime(list(curves["model"].index))[0], 0.71,
            "≈ break-even at −250 odds", color=lab.MUTED, fontsize=7.5, va="bottom")
    ax.legend(frameon=False, fontsize=8.5, labelcolor=lab.SEC, loc="lower right")
    ax.set_ylabel("running top-5 daily pick hit rate", color=lab.SEC, fontsize=9)
    fig.suptitle("Top-5 daily picks — model vs naive pickers (2026)",
                 color=lab.INK, fontsize=12, x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.02, 0.93, 0.94))
    fig.savefig(EDA / "backtest_topk.png", dpi=150, facecolor=lab.SURFACE)
    plt.close(fig)

    top5 = topk[topk["k"] == 5].set_index("picker")
    topk_ok = top5.loc["model", "hit_rate"] > top5.loc["season_ba", "hit_rate"]

    # ── 4. slices ────────────────────────────────────────────────────
    test["quality"] = pd.qcut(test[params["eval"]["tier_col"]], 4,
                              labels=["Q1 weakest", "Q2", "Q3", "Q4 strongest"])
    slices = []
    for dim in ["month", "quality", "is_home"]:
        for level, g in test.groupby(dim, observed=True):
            pv = np.clip(g["p_model"], 1e-6, 1 - 1e-6)
            slices.append({"dimension": dim, "level": str(level), "n": len(g),
                           "base_rate": g["has_hit"].mean(),
                           "mean_pred": pv.mean(),
                           "cal_gap": g["has_hit"].mean() - pv.mean(),
                           "log_loss": common.metric_row(g["has_hit"], pv)["log_loss"]})
    slices = pd.DataFrame(slices)

    # ── gates + report ───────────────────────────────────────────────
    failures = []
    if not cal_ok:
        bad = gated[gated["gap"].abs() > CAL_GATE_PTS]
        failures.append(f"calibration buckets out of band: "
                        f"{[f'{b:.2f}' for b in bad['bucket']]}")
    if not topk_ok:
        failures.append("model top-5 does not beat the season-BA picker")

    with mlflow.start_run(run_name=f"backtest_{test['season'].max()}"):
        mlflow.log_metrics({**{f"test_{k}": float(v) for k, v in overall.items()},
                            "top5_hit_rate": float(top5.loc['model', 'hit_rate']),
                            "test_evaluations_to_date": prior + 1})

    lines = [
        "# Backtest report — TEST 2026 to date (Phase 5)", "",
        f"{len(test):,} starter batter-games, {test['game_date'].min():%Y-%m-%d} → "
        f"{test['game_date'].max():%Y-%m-%d}. Base rate {y.mean():.3f}.",
        f"Model: `{common.MODEL_NAME}@production`. "
        f"**TEST evaluation #{prior + 1}** — every re-run spends the snooping budget.", "",
        f"Overall: log loss {overall['log_loss']:.4f} (EB baseline "
        f"{eb_metrics['log_loss']:.4f}), Brier {overall['brier']:.4f} "
        f"(EB {eb_metrics['brier']:.4f}).", "",
        "## 1. Calibration buckets", "",
        md_table(cal.assign(bucket=cal["bucket"].map("{:.2f}".format))), "",
        f"![calibration](eda/backtest_calibration.png)", "",
        "## 2. Top-K daily picks", "",
        md_table(topk), "",
        f"![topk](eda/backtest_topk.png)", "",
        f"(season-BA picker requires {BA_BENCH_MIN_PA}+ season PA before ranking a player)", "",
        "## 4. Slices", "",
        md_table(slices), "",
        "## Gates", "",
        ("**PASS** — calibration within ±3 pts on all gated buckets; "
         "model top-5 beats the season-BA picker."
         if not failures else "**FAIL** — " + "; ".join(failures)), "",
    ]
    REPORT.write_text("\n".join(lines))
    print(f"\nreport -> {REPORT}")
    print(f"TEST evaluation #{prior + 1}")
    print(topk.to_string(index=False))
    if failures:
        sys.exit("GATE FAIL: " + "; ".join(failures))
    print("PASS — both Phase 5 gates met")


if __name__ == "__main__":
    main()

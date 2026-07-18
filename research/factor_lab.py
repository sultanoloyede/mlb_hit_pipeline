"""Factor-study engine (Phase 3, PLAN.md §6).

Every candidate relationship is treated as an alpha factor (ML4T ch.4):
  - decile plot      — observed P(hit) per factor decile, Wilson 95% CIs
  - IC timeline      — monthly Spearman rank-IC vs has_hit; stability
                       matters more than magnitude
  - PA-controlled IC — IC re-computed inside expected-PA terciles, so a
                       factor can't fake skill by proxying playing time

Promotion rule: monthly IC keeps one sign in >= 70% of months, across
>= 3 seasons, with |median IC| >= 0.01 -> PROMOTE. Stable but tiny ->
WEAK. Otherwise REJECT.
"""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# ── chart chrome (dataviz reference palette, light mode) ─────────────
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SEC = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
RED = "#e34948"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ)

MIN_MONTH_N = 300      # skip months with fewer batter-games
IC_PROMOTE = 0.01
SIGN_STABILITY = 0.70
MIN_SEASONS = 3


def style_ax(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def new_fig(n_panels=2, width=12.0, height=4.2):
    fig, axes = plt.subplots(1, n_panels, figsize=(width, height))
    fig.patch.set_facecolor(SURFACE)
    if n_panels == 1:
        axes = [axes]
    for ax in np.ravel(axes):
        style_ax(ax)
    return fig, np.ravel(axes)


def wilson(k, n, z=1.96):
    """Wilson 95% interval for a binomial proportion."""
    if n == 0:
        return np.nan, np.nan
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def spearman(x: pd.Series, y: pd.Series) -> float:
    m = x.notna() & y.notna()
    if m.sum() < 30:
        return np.nan
    return x[m].rank().corr(y[m].rank())


def decile_table(df, col, target="has_hit", bins=10):
    d = df[[col, target]].dropna()
    d["bin"] = pd.qcut(d[col], bins, duplicates="drop")
    rows = []
    for i, (interval, g) in enumerate(d.groupby("bin", observed=True), 1):
        k, n = g[target].sum(), len(g)
        lo, hi = wilson(k, n)
        rows.append({"decile": i, "mid": interval.mid, "n": n,
                     "rate": k / n, "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def monthly_ic_table(df, col, target="has_hit"):
    rows = []
    for (season, month), g in df.groupby(["season", "month"]):
        if g[col].notna().sum() < MIN_MONTH_N:
            continue
        rows.append({"season": season, "month": month,
                     "label": f"{season}-{month:02d}",
                     "ic": spearman(g[col], g[target]), "n": len(g)})
    return pd.DataFrame(rows).dropna(subset=["ic"])


def pa_controlled_ic(df, col, target="has_hit", pa_col="pa_roll10"):
    d = df.dropna(subset=[col, pa_col])
    if len(d) < 1000:
        return np.nan
    d = d.assign(_band=pd.qcut(d[pa_col], 3, labels=False, duplicates="drop"))
    ics = [spearman(g[col], g[target]) for _, g in d.groupby("_band")]
    return float(np.nanmean(ics))


def verdict(ic_tbl: pd.DataFrame) -> tuple[str, dict]:
    if ic_tbl.empty:
        return "NO-DATA", {"median_ic": np.nan, "sign_stability": np.nan,
                           "n_months": 0, "n_seasons": 0}
    med = ic_tbl["ic"].median()
    sign = np.sign(med) if med != 0 else 1
    stability = (np.sign(ic_tbl["ic"]) == sign).mean()
    n_seasons = ic_tbl["season"].nunique()
    stats = {"median_ic": med, "sign_stability": stability,
             "n_months": len(ic_tbl), "n_seasons": n_seasons}
    if n_seasons >= MIN_SEASONS and stability >= SIGN_STABILITY:
        return ("PROMOTE" if abs(med) >= IC_PROMOTE else "WEAK"), stats
    return "REJECT", stats


def _decile_panel(ax, dec, base_rate, xlabel):
    ax.bar(dec["decile"], dec["rate"], width=0.62, color=BLUE, zorder=3)
    ax.vlines(dec["decile"], dec["lo"], dec["hi"], color=SEC, linewidth=1.2, zorder=4)
    ax.axhline(base_rate, color=MUTED, linewidth=1.0, linestyle="--", zorder=2)
    ax.text(ax.get_xlim()[1], base_rate, f" league {base_rate:.3f}",
            color=MUTED, fontsize=7.5, va="center")
    ax.set_xlabel(xlabel + " (deciles, low → high)", color=SEC, fontsize=9)
    ax.set_ylabel("P(≥1 hit)", color=SEC, fontsize=9)
    pad = (dec["rate"].max() - dec["rate"].min()) * 0.35 + 0.01
    ax.set_ylim(max(0, dec["lo"].min() - pad), min(1, dec["hi"].max() + pad))
    ax.set_xticks(dec["decile"])


def _ic_panel(ax, ic_tbl):
    x = np.arange(len(ic_tbl))
    ax.axhline(0, color=BASELINE, linewidth=1.0)
    ax.plot(x, ic_tbl["ic"], color=BLUE, linewidth=2.0, zorder=3)
    ax.scatter(x, ic_tbl["ic"], s=14, color=BLUE, zorder=4)
    season_starts = [i for i in range(len(ic_tbl))
                     if i == 0 or ic_tbl["season"].iloc[i] != ic_tbl["season"].iloc[i - 1]]
    ax.set_xticks(season_starts)
    ax.set_xticklabels(ic_tbl["season"].iloc[season_starts], fontsize=8.5)
    ax.set_ylabel("monthly Spearman IC", color=SEC, fontsize=9)
    ax.set_xlabel("month", color=SEC, fontsize=9)


def study_continuous(df, col, key, title, out_dir, note=""):
    """Decile plot + monthly IC timeline; returns scoreboard row."""
    base_rate = df["has_hit"].mean()
    dec = decile_table(df, col)
    ic_tbl = monthly_ic_table(df, col)
    verd, stats = verdict(ic_tbl)
    pa_ic = pa_controlled_ic(df, col)

    fig, (ax1, ax2) = new_fig(2)
    _decile_panel(ax1, dec, base_rate, col)
    _ic_panel(ax2, ic_tbl)
    fig.suptitle(title, color=INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    foot = (f"{verd} · median IC {stats['median_ic']:+.3f} · sign-stable "
            f"{stats['sign_stability']:.0%} of {stats['n_months']} months · "
            f"PA-controlled IC {pa_ic:+.3f}")
    fig.text(0.01, 0.005, foot + ("  ·  " + note if note else ""),
             color=SEC, fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(f"{out_dir}/{key}.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    return {"key": key, "factor": col, "title": title, "verdict": verd,
            "median_ic": stats["median_ic"], "sign_stability": stats["sign_stability"],
            "n_months": stats["n_months"], "pa_controlled_ic": pa_ic, "note": note}


def study_categorical(df, col, key, title, out_dir, note="", order=None,
                      top_bottom=None, horizontal=None):
    """Two panels: P(>=1 hit) and hits-per-PA by category (the PA-control
    view). Categoricals are context, not promotable factors -> verdict
    CONTEXT."""
    d = df.dropna(subset=[col])
    g = d.groupby(col).agg(n=("has_hit", "size"), k=("has_hit", "sum"),
                           hits=("hits", "sum"), pa=("pa", "sum"))
    g = g[g["n"] >= 200]
    g["rate"] = g["k"] / g["n"]
    g["hpp"] = g["hits"] / g["pa"]
    g[["lo", "hi"]] = [wilson(k, n) for k, n in zip(g["k"], g["n"])]
    if order is not None:
        g = g.reindex([o for o in order if o in g.index]).dropna(subset=["rate"])
    else:
        g = g.sort_values("rate")
    if top_bottom and len(g) > 2 * top_bottom:
        g = pd.concat([g.head(top_bottom), g.tail(top_bottom)])

    horizontal = horizontal if horizontal is not None else len(g) > 10
    base_rate, base_hpp = df["has_hit"].mean(), df["hits"].sum() / df["pa"].sum()
    height = max(4.2, 0.3 * len(g) + 1.6) if horizontal else 4.2
    fig, (ax1, ax2) = new_fig(2, height=height)
    labels = [str(i) for i in g.index]

    for ax, vals, base, lab in ((ax1, g["rate"], base_rate, "P(≥1 hit)"),
                                (ax2, g["hpp"], base_hpp, "hits per PA")):
        if horizontal:
            ax.barh(labels, vals, height=0.62, color=BLUE, zorder=3)
            if ax is ax1:
                ax.hlines(labels, g["lo"], g["hi"], color=SEC, linewidth=1.2, zorder=4)
            ax.axvline(base, color=MUTED, linewidth=1.0, linestyle="--")
            ax.set_xlabel(lab, color=SEC, fontsize=9)
            ax.xaxis.grid(True, color=GRID, linewidth=0.8)
            ax.yaxis.grid(False)
            lo = max(0, min(vals.min(), base) * 0.92)
            ax.set_xlim(lo, max(vals.max(), base) * 1.05)
        else:
            ax.bar(labels, vals, width=0.62, color=BLUE, zorder=3)
            if ax is ax1:
                ax.vlines(labels, g["lo"], g["hi"], color=SEC, linewidth=1.2, zorder=4)
            ax.axhline(base, color=MUTED, linewidth=1.0, linestyle="--")
            ax.set_ylabel(lab, color=SEC, fontsize=9)
            pad = (vals.max() - vals.min()) * 0.35 + 0.005
            ax.set_ylim(max(0, min(vals.min(), base) - pad),
                        min(1, max(vals.max(), base) + pad))

    fig.suptitle(title, color=INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    spread = g["rate"].max() - g["rate"].min()
    fig.text(0.01, 0.005,
             f"CONTEXT · P(hit) spread {spread:.3f} across {len(g)} groups"
             + ("  ·  " + note if note else ""), color=SEC, fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(f"{out_dir}/{key}.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    return {"key": key, "factor": col, "title": title, "verdict": "CONTEXT",
            "median_ic": np.nan, "sign_stability": np.nan, "n_months": 0,
            "pa_controlled_ic": np.nan,
            "note": f"spread {spread:.3f}" + (f" · {note}" if note else "")}

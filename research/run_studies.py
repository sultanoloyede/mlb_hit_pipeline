"""Phase 3 runner: executes every factor study from PLAN.md §6 against
the warehouse, writes charts to reports/eda/ and the scoreboard to
reports/research_findings.md.

Usage (repo root):  python research/run_studies.py [--refresh]
The analysis frame is cached at data/research_frame.parquet.
"""

import os
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_lab as lab
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "eda"
CACHE = ROOT / "data" / "research_frame.parquet"
FINDINGS = ROOT / "reports" / "research_findings.md"
OUT.mkdir(parents=True, exist_ok=True)


def token() -> str:
    if os.getenv("MOTHERDUCK_TOKEN"):
        return os.environ["MOTHERDUCK_TOKEN"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("MOTHERDUCK_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("MOTHERDUCK_TOKEN not set")


FRAME_SQL = """
select
    f.game_pk, f.game_date, f.season, f.month, f.batter_id, f.player_name,
    f.team_id, f.opponent_team_id, f.is_home, f.batting_order_slot,
    f.is_substitute, f.opp_starter_throws, f.league_rank_entering,
    f.day_night, f.has_hit, f.pa, f.hits, f.days_rest,
    f.career_pa_prior, f.eb_hit_per_pa_career, f.eb_hit_per_pa_season,
    f.hit_streak_entering, f.hitless_streak_entering,
    f.has_hit_roll10, f.hit_per_pa_roll20, f.hit_per_pa_roll40, f.pa_roll10,
    f.k_pct_roll20, f.bb_pct_roll20, f.contact_pct_roll20,
    f.chase_rate_roll20, f.hard_hit_pct_roll20, f.barrel_pct_roll20,
    f.sweet_spot_pct_roll20, f.line_drive_pct_roll20, f.xba_mean_roll20,
    f.xba_minus_ba_roll20, f.hit_per_pa_platoon_roll20,
    f.war_prev_season, f.team_hits_roll15,
    f.opp_xwoba_against_roll15, f.opp_hits_allowed_per_bf_roll15,
    f.p_hits_per_bf_roll10, f.p_xwoba_against_roll10,
    dp.bats,
    dt.team_code            as opponent_code,
    dg.venue_name,
    fb.manager_name,
    bvp.bvp_pa_career, bvp.bvp_hits_per_pa
from ml.feat_batter_game f
left join marts.dim_player dp on dp.player_id = f.batter_id
left join marts.dim_team dt   on dt.team_id = f.opponent_team_id
left join marts.dim_game dg   on dg.game_pk = f.game_pk
left join marts.fct_batter_game fb
       on fb.game_pk = f.game_pk and fb.batter_id = f.batter_id
left join marts.fct_batter_vs_pitcher bvp
       on bvp.game_pk = f.game_pk and bvp.batter_id = f.batter_id
      and bvp.pitcher_id = f.opp_starter_id
"""


def load_frame(refresh: bool) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    con = duckdb.connect(f"md:mlb_hits?motherduck_token={token()}")
    df = con.execute(FRAME_SQL).df()
    CACHE.parent.mkdir(exist_ok=True)
    df.to_parquet(CACHE)
    return df


# (key, column, title, note) — continuous factors, decile + IC engine
CONTINUOUS = [
    ("01_form_hitrate_r10", "has_hit_roll10", "Form — hit rate, last 10 games (#1)", ""),
    ("01_form_hpp_r20", "hit_per_pa_roll20", "Form — hits per PA, last 20 games (#1)", ""),
    ("03_war_prev", "war_prev_season", "Previous-season WAR (#3)", "bWAR; quality tier, partly tautological"),
    ("05_expected_pa", "pa_roll10", "Expected PA — avg PA last 10 (#5)", "the mechanical driver"),
    ("09_team_hits", "team_hits_roll15", "Team hits/game, last 15 (#9)", "lineup context"),
    ("10_barrel", "barrel_pct_roll20", "Barrel rate, last 20 (#10)", ""),
    ("11_walks", "bb_pct_roll20", "Walk rate, last 20 (#11)", "sign ambiguous by design"),
    ("12_chase", "chase_rate_roll20", "Chase rate, last 20 (#12)", ""),
    ("13_contact", "contact_pct_roll20", "Contact rate, last 20 (#13)", "prior: strongest family"),
    ("14_hard_hit", "hard_hit_pct_roll20", "Hard-hit rate, last 20 (#14)", ""),
    ("15_league_rank", "league_rank_entering", "League rank entering day (#15)", "1 = best"),
    ("17_k", "k_pct_roll20", "Strikeout rate, last 20 (#17)", "expect negative"),
    ("18_line_drive", "line_drive_pct_roll20", "Line-drive rate, last 20 (#18)", ""),
    ("19_sweet_spot", "sweet_spot_pct_roll20", "Sweet-spot rate, last 20 (#19)", ""),
    ("21_xba_gap", "xba_minus_ba_roll20", "xBA − BA, last 20 (#21)", "the luck meter; expect positive"),
    ("21b_xba_form", "xba_mean_roll20", "xBA, last 20 (#1/#21)", ""),
    ("07b_platoon_form", "hit_per_pa_platoon_roll20", "Platoon-matched form, last 20 (#7)", "vs today's starter hand"),
    ("22_opp_pitching", "opp_xwoba_against_roll15", "Opp team pitching xwOBA-against, last 15 (#22/#23)", "as-of date"),
    ("22b_opp_starter", "p_hits_per_bf_roll10", "Opp starter hits/BF, last 10 starts (#22)", ""),
    ("26_hit_streak", "hit_streak_entering", "Hit streak entering (#26)", ""),
    ("27_hitless_streak", "hitless_streak_entering", "Hitless streak entering (#27)", ""),
    ("00_eb_career", "eb_hit_per_pa_career", "EB-shrunk career hit/PA (baseline)", "the bar every factor must beat"),
]

# (key, column, title, kwargs) — categorical context studies
CATEGORICAL = [
    ("02_month", "month", "Hit rate by month (#2)", {"order": [3, 4, 5, 6, 7, 8, 9, 10]}),
    ("20_year", "season", "Hit rate by season (#20)", {"order": [2021, 2022, 2023, 2024, 2025, 2026]}),
    ("06_batting_order", "batting_order_slot", "Hit rate by lineup slot (#6)", {"order": list(range(1, 10))}),
    ("04_home_away", "is_home", "Home vs away (#4)", {"horizontal": False}),
    ("04b_venue", "venue_name", "Hit rate by venue — top/bottom 12 (#4)", {"top_bottom": 12}),
    ("08_opponent", "opponent_code", "Hit rate by opponent (#8)", {}),
    ("16_manager", "manager_name", "Hit rate by manager — top/bottom 10 (#16)", {"top_bottom": 10}),
]


def bespoke_platoon(df):
    d = df.dropna(subset=["bats", "opp_starter_throws"]).copy()
    d["matchup"] = np.where(d["bats"] == "S", "switch",
                   np.where(d["bats"] == d["opp_starter_throws"], "same hand", "opposite hand"))
    return lab.study_categorical(d, "matchup", "07_platoon_adv",
                                 "Platoon advantage vs opposing starter (#7)",
                                 OUT, horizontal=False,
                                 order=["same hand", "opposite hand", "switch"])


def bespoke_pa_actual(df):
    d = df.copy()
    d["pa_in_game"] = d["pa"].clip(upper=6)
    return lab.study_categorical(d, "pa_in_game", "05b_actual_pa",
                                 "Hit rate by actual PA in game (#5)", OUT,
                                 horizontal=False, order=[1, 2, 3, 4, 5, 6],
                                 note="mechanical: P ≈ 1-(1-p)^PA — motivates the structural model")


def bespoke_pitching_tiers(df):
    d = df.dropna(subset=["opp_xwoba_against_roll15"]).copy()
    ranks = d.groupby(["game_date", "opponent_team_id"])["opp_xwoba_against_roll15"].first().reset_index()
    ranks["rank"] = ranks.groupby("game_date")["opp_xwoba_against_roll15"].rank(method="first")
    ranks["n_teams"] = ranks.groupby("game_date")["opp_xwoba_against_roll15"].transform("size")
    ranks["tier"] = np.where(ranks["rank"] <= 5, "top-5 pitching",
                    np.where(ranks["rank"] > ranks["n_teams"] - 5, "bottom-5 pitching", "middle"))
    d = d.merge(ranks[["game_date", "opponent_team_id", "tier"]],
                on=["game_date", "opponent_team_id"], how="left")
    return lab.study_categorical(d, "tier", "23_pitching_tiers",
                                 "Opponent pitching tier, as-of date (#22/#23)", OUT,
                                 horizontal=False,
                                 order=["top-5 pitching", "middle", "bottom-5 pitching"],
                                 note="ranked daily by rolling xwOBA-against — no season-end lookahead")


def bespoke_bvp(df):
    d = df[df["bvp_pa_career"] >= 10].copy()
    return lab.study_continuous(d, "bvp_hits_per_pa", "24_bvp",
                                "Career BvP hits/PA entering game, ≥10 prior PA (#24)",
                                OUT, note=f"n={len(d):,}; literature expects ≈ nothing")


def bespoke_streak_buckets(df):
    """Hot-hand check: hit rate by streak bucket vs what each player's
    own EB rate predicts for exactly those games (selection-corrected)."""
    d = df.dropna(subset=["eb_hit_per_pa_career", "pa"]).copy()
    d["expected"] = 1 - (1 - d["eb_hit_per_pa_career"]) ** d["pa"]
    d["bucket"] = pd.cut(d["hit_streak_entering"], [-1, 0, 1, 2, 4, 9, 99],
                         labels=["0", "1", "2", "3-4", "5-9", "10+"])
    g = d.groupby("bucket", observed=True).agg(
        n=("has_hit", "size"), k=("has_hit", "sum"), exp=("expected", "mean"))
    g["rate"] = g["k"] / g["n"]
    g[["lo", "hi"]] = [lab.wilson(k, n) for k, n in zip(g["k"], g["n"])]

    fig, axes = lab.new_fig(1, width=7.2)
    ax = axes[0]
    x = np.arange(len(g))
    ax.bar(x, g["rate"], width=0.62, color=lab.BLUE, zorder=3, label="observed")
    ax.vlines(x, g["lo"], g["hi"], color=lab.SEC, linewidth=1.2, zorder=4)
    ax.scatter(x, g["exp"], marker="_", s=420, color=lab.RED, linewidth=2.2,
               zorder=5, label="expected from player quality + PA")
    ax.set_xticks(x)
    ax.set_xticklabels(g.index)
    ax.set_xlabel("hit streak entering game", color=lab.SEC, fontsize=9)
    ax.set_ylabel("P(≥1 hit)", color=lab.SEC, fontsize=9)
    ax.set_ylim(g["rate"].min() - 0.05, g["rate"].max() + 0.05)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=lab.SEC)
    fig.suptitle("Hot hand? Streaks vs selection-corrected expectation (#26/#27)",
                 color=lab.INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    resid = (g["rate"] - g["exp"]).round(4).to_dict()
    fig.text(0.01, 0.005, f"observed − expected by bucket: {resid}",
             color=lab.SEC, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT / "26_streak_buckets.png", dpi=150, facecolor=lab.SURFACE)
    plt.close(fig)
    worst = max(abs(v) for v in resid.values())
    return {"key": "26_streak_buckets", "factor": "hit_streak_entering",
            "title": "Hot-hand bucket test (#26/#27)", "verdict": "CONTEXT",
            "median_ic": np.nan, "sign_stability": np.nan, "n_months": 0,
            "pa_controlled_ic": np.nan,
            "note": f"max |obs−exp| {worst:.3f} — streak effect beyond quality+PA"}


def bespoke_pitchtype():
    con = duckdb.connect(f"md:mlb_hits?motherduck_token={token()}")
    league = con.execute("""
        select pitch_type, sum(hits) * 1.0 / sum(ab_ended) as ba, sum(pitches_seen) as n
        from marts.fct_batter_pitchtype
        where pitch_type in ('FF','SI','FC','SL','ST','CU','KC','CH','FS')
        group by 1 order by ba desc
    """).df()
    top = con.execute("""
        with top_batters as (
            select batter_id from marts.fct_batter_pitchtype
            group by 1 order by sum(pitches_seen) desc limit 25
        )
        select p.player_name, t.pitch_type, t.ba
        from marts.fct_batter_pitchtype t
        join top_batters using (batter_id)
        join marts.dim_player p on p.player_id = t.batter_id
        where t.pitch_type in ('FF','SI','FC','SL','ST','CU','KC','CH','FS')
          and t.ab_ended >= 30
    """).df()
    mat = top.pivot_table(index="player_name", columns="pitch_type", values="ba")
    mat = mat[[c for c in ["FF", "SI", "FC", "SL", "ST", "CU", "KC", "CH", "FS"]
               if c in mat.columns]]

    fig, axes = lab.new_fig(2, width=13, height=7.0)
    ax = axes[0]
    ax.barh(league["pitch_type"][::-1], league["ba"][::-1], height=0.62,
            color=lab.BLUE, zorder=3)
    ax.set_xlabel("league BA when AB ends on pitch type", color=lab.SEC, fontsize=9)
    ax.xaxis.grid(True, color=lab.GRID, linewidth=0.8)
    ax.yaxis.grid(False)
    ax.set_xlim(league["ba"].min() * 0.9, league["ba"].max() * 1.05)

    ax2 = axes[1]
    im = ax2.imshow(mat.values, cmap=lab.SEQ_CMAP, aspect="auto")
    ax2.set_xticks(range(len(mat.columns)), mat.columns, fontsize=8)
    ax2.set_yticks(range(len(mat.index)), mat.index, fontsize=7.5)
    ax2.yaxis.grid(False)
    cbar = fig.colorbar(im, ax=ax2, shrink=0.8)
    cbar.set_label("BA vs pitch type", color=lab.SEC, fontsize=8.5)
    cbar.ax.tick_params(colors=lab.MUTED, labelsize=7.5)
    fig.suptitle("Hits by pitch type — league + top-25 batters, full history (#25)",
                 color=lab.INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.005, "research view only (not point-in-time); model feature = "
             "starter pitch mix × batter per-type xBA", color=lab.SEC, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(OUT / "25_pitch_type.png", dpi=150, facecolor=lab.SURFACE)
    plt.close(fig)
    return {"key": "25_pitch_type", "factor": "pitch_type", "title": "Pitch type (#25)",
            "verdict": "CONTEXT", "median_ic": np.nan, "sign_stability": np.nan,
            "n_months": 0, "pa_controlled_ic": np.nan,
            "note": "full-history view; interaction feature deferred to Phase 4"}


def write_findings(rows):
    df = pd.DataFrame(rows)
    order = {"PROMOTE": 0, "WEAK": 1, "REJECT": 2, "CONTEXT": 3, "NO-DATA": 4}
    df = df.sort_values(["verdict", "median_ic"],
                        key=lambda s: s.map(order) if s.name == "verdict" else -s.abs())
    lines = [
        "# Factor research scoreboard (Phase 3)",
        "",
        "Promotion rule: monthly Spearman IC keeps one sign in >=70% of months",
        "across >=3 seasons AND |median IC| >= 0.01. WEAK = stable but tiny.",
        "CONTEXT = categorical/descriptive study, judged qualitatively.",
        "PA-controlled IC = IC inside expected-PA terciles (playing-time proxy check).",
        "",
        "| study | factor | verdict | median IC | sign-stable | months | PA-ctrl IC | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        med = "" if pd.isna(r.median_ic) else f"{r.median_ic:+.3f}"
        st = "" if pd.isna(r.sign_stability) else f"{r.sign_stability:.0%}"
        pa = "" if pd.isna(r.pa_controlled_ic) else f"{r.pa_controlled_ic:+.3f}"
        lines.append(f"| [{r.key}](eda/{r.key}.png) | `{r.factor}` | **{r.verdict}** "
                     f"| {med} | {st} | {r.n_months or ''} | {pa} | {r.note} |")
    FINDINGS.write_text("\n".join(lines) + "\n")


def main():
    refresh = "--refresh" in sys.argv
    df = load_frame(refresh)
    print(f"analysis frame: {len(df):,} rows")
    rows = []
    for key, col, title, note in CONTINUOUS:
        rows.append(lab.study_continuous(df, col, key, title, OUT, note))
        print(f"  {rows[-1]['verdict']:8} {key}")
    for key, col, title, kwargs in CATEGORICAL:
        rows.append(lab.study_categorical(df, col, key, title, OUT, **kwargs))
        print(f"  {rows[-1]['verdict']:8} {key}")
    for fn in (bespoke_platoon, bespoke_pa_actual, bespoke_pitching_tiers,
               bespoke_bvp, bespoke_streak_buckets):
        rows.append(fn(df) if fn is not bespoke_pitchtype else fn())
        print(f"  {rows[-1]['verdict']:8} {rows[-1]['key']}")
    rows.append(bespoke_pitchtype())
    print(f"  {rows[-1]['verdict']:8} {rows[-1]['key']}")
    write_findings(rows)
    print(f"\ncharts -> {OUT}\nscoreboard -> {FINDINGS}")


if __name__ == "__main__":
    main()

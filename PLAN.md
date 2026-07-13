# mlb_hits — Daily Hit-Probability Platform: Build Plan

Goal: every day, rank all MLB batters playing that day by a **calibrated
probability of recording ≥1 hit**, backed by a self-running $0 ELT
pipeline on industry-standard tools, a SQL warehouse, a research library
that justifies every model feature, a season-long backtest, and a web
dashboard.

Architecture philosophy: **no homegrown frameworks.** Every concern is
handled by the standard tool the industry uses for it — ingestion state
by dlt, transformation + data quality by dbt, scheduling by the
orchestrator, experiment tracking by MLflow. The modeling and
backtesting workflow follows *Machine Learning for Algorithmic Trading*
(Jansen, 2nd ed.) — the book's factor-research → ML process →
strategy-backtest loop, translated from equities to batter-games.

---

## 1. The stack ($0 audit)

Modern **ELT** (not ETL): load raw data into the warehouse first,
transform *inside* the warehouse with SQL. This is the pattern dbt
assumes and what you'd meet at any data-driven company today.

| Concern | Tool | Free tier / cost | Notes |
|---|---|---|---|
| Extraction + loading | **dlt** (data load tool) | OSS, $0 | Python-native EL. Sources are `@dlt.resource` generators wrapping pybaseball / MLB-StatsAPI. Handles incremental cursors (game date), schema inference/evolution, retries, and load state — no custom manifest code |
| Warehouse | **BigQuery** (recommended) | Free tier: 10 GB storage + 1 TB query/mo, forever | The industry-standard cloud warehouse. Sandbox mode needs no card but expires tables after 60 days → attach billing once (still $0 under free tier). No-card alternative: **MotherDuck** free plan (10 GB, DuckDB) |
| Transformation | **dbt Core** | OSS, $0 | staging → intermediate → marts; tests, source freshness, docs + lineage graph |
| Data quality | **dbt tests + dbt-expectations** | OSS, $0 | Schema, uniqueness, ranges, leakage assertions; failures fail the run |
| Orchestration (v1) | **GitHub Actions cron** | Public repo: unlimited minutes | Daily 16:00 UTC run: `dlt → dbt build → predict`. The standard "modern data stack in a box" scheduler at this scale |
| Orchestration (v2, optional) | **Dagster OSS** (or Airflow) on Oracle Cloud Always Free VM | OSS + always-free ARM VM (4 CPU/24 GB) | Asset lineage, retries, sensors, UI. Dagster has first-class dlt + dbt integrations. Oracle signup wants a card for identity only |
| Experiment tracking / model registry | **MLflow** | OSS, $0 | Every training run logged: params, metrics, calibration artifacts, model binary. Free hosted option: DagsHub. Replaces ad-hoc `*_meta.json` |
| ML | scikit-learn, **LightGBM** | OSS | Book Ch. 12: gradient boosting is the tabular workhorse |
| Dashboard | **Streamlit Community Cloud** | Free (public app) | Reads the warehouse with a read-only credential; renders `output` tables only |
| CI/CD | **GitHub Actions** | Free | PRs run: `pytest` (dlt sources), `sqlfluff` lint, `dbt build` against a dev schema. Merge to main = deploy (the daily job just pulls main) |
| dbt docs hosting | **GitHub Pages** | Free | Published lineage graph + column docs — the warehouse is self-documenting |
| Odds (Phase 8) | **The Odds API** | 500 req/mo free | 1 pull/day ≈ 30/mo |
| Alerting | GH Actions failure e-mail; optional Slack/Discord webhook | Free | Pipeline red = e-mail before you check the site |

Source data (all free): **Statcast via pybaseball** (pitch-level: xBA,
barrels, launch, sweet spot, chase/contact), **MLB Stats API**
(schedule, probable pitchers, lineups, boxscores, standings, coaching
staff), **FanGraphs via pybaseball** (batter WAR, plate discipline,
team pitching ranks), **Retrosheet** (historical managers).

Size check: pitch-level parquet ≈ 0.7 GB/season → 2021–2026 ≈ 4 GB;
marts are ~50 MB/season. Comfortably inside every free tier above.

---

## 2. Architecture

```
              GitHub Actions cron — daily 16:00 UTC (CI/CD on PRs)
                                 │
        ┌────────────────────────▼─────────────────────────┐
        │ EL — dlt pipelines (Python)                      │
        │   statcast source      → yesterday's pitches     │
        │   mlb_statsapi source  → schedule, probables,    │
        │                          lineups, boxscores,     │
        │                          standings               │
        │   fangraphs source     → WAR, plate discipline   │
        │   incremental state kept BY DLT in the warehouse │
        └────────────────────────┬─────────────────────────┘
                                 ▼   raw datasets (append-only)
        ┌──────────────────────────────────────────────────┐
        │ BigQuery  (or MotherDuck)                        │
        │   T — dbt build:                                 │
        │   staging → intermediate → marts (star schema)   │
        │           → ml feature views → output            │
        │   dbt tests gate every layer                     │
        └───────┬──────────────────────────────┬───────────┘
                ▼                              ▼
   ML jobs (Python + MLflow)          Streamlit dashboard
   train / calibrate / backtest       today's ranked slate,
   predict → appends to output.       research charts,
   predictions (point-in-time,        backtest report
   immutable)
```

Two planes, cleanly separated:
- **Data plane** (dlt + dbt): pure ELT, restartable, idempotent.
- **ML plane** (Python + MLflow): reads feature views, writes
  predictions back to `output` — the only writer besides dbt.

---

## 3. Book → project mapping

How Jansen's workflow translates to batter-games (the book thinks in
tickers × dates; we think in batters × games):

| Book concept | Chapter | Our implementation |
|---|---|---|
| Data sourcing & point-in-time discipline | 2–3 | dlt incremental loads keyed on game date; every feature built from data strictly *before* the game; "alternative data" = Statcast batted-ball physics |
| Alpha factor research (Alphalens: quantile returns, information coefficient) | 4 | Each of the 27 hypotheses becomes a **factor study**: decile plot of hit rate by factor value + monthly Spearman **IC timeline**. Promotion rule: IC keeps one sign in ≥70% of months across ≥3 seasons |
| The research phase vs the execution phase | 1 | `research/` notebooks are exploratory and disposable; only promoted factors get productionized as dbt feature columns |
| The ML process: bias-variance, CV design | 6 | Walk-forward **expanding-window CV with a 7-day embargo** (rolling features leak across adjacent days). Never shuffled, never k-fold |
| Purging / embargoing | 6 | Embargo gap between train and validation windows; leakage also asserted as a dbt test (`feature_source_date < game_date`) |
| Linear models first | 7 | Logistic-regression baseline must be beaten before any GBM ships |
| Gradient boosting | 12 | LightGBM classifier, log-loss objective |
| From model to strategy backtest; backtest pitfalls (lookahead, survivorship, snooping) | 5, 8 | Event-driven day-by-day replay of an untouched TEST season, reading only the immutable prediction snapshots; a counter tracks how many times TEST has been evaluated (data-snooping budget) |
| Kelly criterion / position sizing | 5 | Backtest Section 3: flat stake vs fractional Kelly on `p_cal − p_implied` edges |
| Sharpe / performance evaluation | 5 | Betting analog: cumulative units, max drawdown, hit rate of top-K picks vs benchmarks |

---

## 4. Warehouse design (dbt)

```
raw (dlt-owned, append-only)
  statcast_pitches · schedule · probables · lineups
  boxscore_batting · standings · fg_batting · coaches · odds

staging (stg_)          typed, deduped, renamed — 1:1 with raw
intermediate (int_)     game-level aggregations from pitches,
                        rolling windows, as-of joins

marts
  dim_player · dim_team · dim_venue (city, roof) · dim_manager
  dim_game (date, venue, day/night, doubleheader flag)
  fct_batter_game    ← core table, grain batter × game:
                       label has_hit, hits, pa, ab, batting_order,
                       is_home, month, opp team, opp starter +
                       handedness, per-game Statcast aggregates
                       (barrel%, hard-hit%, sweet-spot%, LD%,
                       contact%, chase, K%, BB%, xBA, xBA−BA)
  fct_pitcher_game · fct_team_game · fct_standings_daily
  fct_batter_vs_pitcher (career BvP — small-sample flagged)
  fct_batter_pitchtype  (batter × pitch type: BA/xBA)

ml
  feat_batter_game   ← point-in-time feature view: every column
                       windowed/lagged strictly before game_date
                       (5/10/20/40-game windows, platoon splits,
                       empirical-Bayes shrunk rates + raw PA counts)

output (ML plane writes, dashboard reads)
  predictions        append-only: batter × game × run_ts,
                       p_raw, p_cal, lineup_confirmed, model_version
  backtest_daily     predictions joined to outcomes
```

**dbt tests as the quality gates:** unique (batter, game_pk); label in
{0,1}; PA ≥ 1; **the leakage test** (no feature sourced on/after game
date) — the most important test in the repo; row-count anomaly checks;
freshness on every raw source. A red test fails the Action → e-mail;
the dashboard keeps serving yesterday's tables because predictions are
append-only.

**Label:** `has_hit = hits ≥ 1` from the official boxscore line, for
players with ≥1 PA. Zero-PA appearances (pinch-runner, defensive sub)
are excluded from training and voided in the backtest.

---

## 5. Daily run (once a day) and the lineup-timing problem

Cron 16:00 UTC (noon ET):

1. **dlt run** — yesterday's Statcast + boxscores (labels), today's
   schedule/probables/lineups, standings, FanGraphs snapshot.
2. **dbt build** — all layers + tests (the gate).
3. **predict** — load current model from MLflow registry, score today's
   slate, append to `output.predictions` with `run_ts`.
4. **label** — dbt model joins yesterday's predictions to outcomes →
   `backtest_daily`; dashboard refreshes automatically.

**Flagged concern:** at noon ET most lineups aren't posted, so night
games are scored with the *probable* starter and a *projected* batting
order (player's modal slot over the last 7 games vs that pitcher hand),
recorded via `lineup_confirmed`. That is exactly the information a
morning bettor has, so the backtest stays honest — but it costs
accuracy. v2 adds a second free cron at 22:00 UTC that re-scores only
games whose lineups posted since noon (new `run_ts`, nothing
overwritten). The backtest always evaluates the snapshot the site
actually showed.

---

## 6. Research phase — the 27 factor studies

Method: book Ch. 4. Every hypothesis is a factor; every factor gets
(a) a **decile plot** — hit rate per factor decile with Wilson CIs,
(b) a **monthly IC timeline** — stability beats magnitude, and
(c) a **PA-controlled view** where relevant, because plate appearances
mechanically drive P(hit) and will otherwise masquerade as every other
effect.

Deliverables: one notebook per theme in `research/`, charts exported to
`reports/eda/`, a `research_findings.md` scoreboard, and the best
charts on the dashboard's Research page. Only factors passing the
IC-stability rule become dbt feature columns.

| # | Relationship | Metric | Chart | Pitfalls & notes |
|---|---|---|---|---|
| 1 | Form | Rolling hit rate & xBA (5/10/20/40 g) | Decile + IC timeline | Regression to the mean; compare to season baseline |
| 2 | Month | Hit rate by month | Bar w/ CIs | Confounded by weather + call-ups |
| 3 | Batter WAR | Season-to-date WAR | Decile | WAR *contains* hitting — quality tier, not causal |
| 4 | Opponent city / away | Hit rate by venue/city | Heatmap | Park factor + travel; split home/away |
| 5 | Plate appearances | Hit rate by PA (1–6) | Bar | The dominant driver: P ≈ 1−(1−p)^PA — motivates the structural model |
| 6 | Batting order | Hit rate by slot 1–9 | Bar | Proxies both PA *and* quality; show raw + PA-adjusted |
| 7 | Pitcher handedness | Same-hand vs opposite | Grouped bar | Platoon effect; handle switch hitters |
| 8 | Opponent team | Hit rate vs each opponent | Sorted bar | Mostly proxies opp pitching → #22/23 |
| 9 | Team avg hits | Team rolling hits/g vs individual rate | Scatter | Lineup context: better offenses → more PA |
| 10 | Barrel % | Rolling barrel% | Decile + IC | Barrels → XBH more than singles; may matter less for P(any hit) |
| 11 | Walks | Rolling BB% | Decile | Ambiguous sign — walks steal hit chances but signal eye |
| 12 | Chase rate | Rolling O-Swing% | Decile | Interacts with #11 |
| 13 | Contact % | Rolling contact% | Decile + IC | Prior: strongest family for P(≥1 hit) |
| 14 | Hard-hit % | Rolling HH% | Decile | Collinear with barrel% — check before using both |
| 15 | League rank at time | Standings as-of date | Decile | April rank ≈ noise; as-of-date only |
| 16 | Manager / coach | Hit rate by manager | Bar w/ CIs | Near-pure confounding (managers ⇔ rosters); expect to reject |
| 17 | Strikeout % | Rolling K% | Decile + IC | Strong negative; near mirror of #13 |
| 18 | Line-drive % | Rolling LD% | Decile | Noisy in small windows — prefer 40-game |
| 19 | Sweet-spot % | Rolling SwSp% (8–32°) | Decile | Overlaps LD%; keep whichever survives |
| 20 | Year | Hit rate by season | Line | 2023 rules (shift ban, pitch clock) = regime shift; drop 2020 |
| 21 | xBA − BA | Rolling gap vs *future* hit rate | Decile | The luck meter — should mean-revert; most promising novel factor |
| 22 | Worst-5 pitching teams | Opp in bottom 5 by xwOBA-against, as-of date | Grouped bar | End-of-season ranks = lookahead trap |
| 23 | Best-5 pitching teams | Top 5, same discipline | Grouped bar | Same |
| 24 | Batter vs pitcher | Career BA vs that pitcher | Heatmap (pitchers × BA) | Tiny samples — show EB-shrunk values; literature says raw BvP ≈ no signal, test it |
| 25 | Pitch type | Batter BA/xBA by pitch type | Heatmap | Only useful crossed with opp starter's pitch mix → build `mix × per-type xBA` feature |
| 26 | Hit streak | Consecutive games with a hit | Rate by streak + permutation test | Hot-hand check vs shuffled baseline; expect ≈ nothing after skill |
| 27 | Hitless streak | Consecutive without | Same | Asymmetry vs #26 is the interesting question |

(Your list names WAR and opponent twice — merged/split as #3, #4, #8.)

---

## 7. Modeling plan

**Framing.** Binary classification, grain batter × game, target
`has_hit`, optimizing **log loss** — probability quality *is* the
product requirement, not accuracy or AUC.

**Two model families, compared honestly:**

1. **Structural per-PA model** — estimate per-PA hit probability with a
   regularized logistic model, predict expected PA from batting order +
   team offense + opp starter, compose `P = 1 − (1 − p_pa)^E[PA]`.
   Bakes in the mechanically-true PA effect and degrades gracefully for
   short-sample players.
2. **Direct LightGBM classifier** on the promoted feature set.

If within noise on validation, ship the structural model
(interpretable, robust); blending is a v2 experiment. Every run —
params, CV metrics, calibration curves, feature importances, model
binary — is an **MLflow run**; the daily job pulls whatever model is in
the registry's `production` alias, so promotion is an explicit,
auditable act.

**Player quality / sample size (your concern).** All rate features also
exist in **empirical-Bayes shrunk** form (Beta prior toward league/role
mean, prior strength ≈ 200 PA), raw PA counts are features themselves
(the model learns how much to trust a rate), and every evaluation is
reported **by quality tier** (season wOBA quartile) and PA band so we
can see if the model only works for stars.

**Baselines that must be beaten (in MLflow, side by side):**
league base rate (~65%) → EB-shrunk player hit rate → logistic
regression on {shrunk rate, order, opp starter quality, platoon}.

**Validation.** Walk-forward expanding-window by season with 7-day
embargo (book Ch. 6). Splits: **TRAIN 2021–2024** (2020 dropped),
**CALIB 2025** (isotonic calibration; must not worsen Brier),
**TEST 2026-to-date** (backtest only). Report Brier, log loss,
reliability curves — overall and per tier.

---

## 8. Backtest — season-long correctness proof

Event-driven replay (book Ch. 8): walk each TEST day in order, read
only the immutable prediction snapshot for that day, grade against
boxscores. Revisions forbidden by construction (append-only table).

1. **Calibration buckets** — the headline product number: the 60–65%
   bucket must hit 60–65%.
2. **Top-K view (the tradable surface)** — top 5 / top 10 daily picks:
   season hit rate, longest losing streak, cumulative record chart, vs
   two benchmarks (pick by raw season BA; pick by shrunk rate).
3. **ROI at real odds (Phase 8)** — hit props are juiced to −250/−300
   (break-even ≈ 71–75%); model-vs-reality ≠ model-vs-market. Flat
   stake and fractional Kelly (Ch. 5), betting only when
   `p_cal − p_implied ≥ 0.02`. Only this section claims profit.
4. **Slices** — month, quality tier, home/away, confirmed vs projected
   lineup (quantifies the §5 timing cost).

**Snooping budget (Ch. 6/8):** one TEST season exists; every peek
overfits it a little. The backtest job logs an evaluation counter to
MLflow, and improvements < 0.002 Brier are treated as noise.

---

## 9. Dashboard (Streamlit)

1. **Today** — ranked slate: P(hit) with uncertainty band, order
   (confirmed/projected badge), opp starter + hand, venue; top-5
   highlighted; filters by team/game.
2. **Research** — the factor library: each chart + a two-sentence
   verdict (promoted / rejected and why).
3. **Backtest** — calibration plot, top-K cumulative record, slice
   tables, and the honest accuracy-vs-market-edge disclaimer.
4. **Player detail** — rolling form, xBA−BA luck meter, our prediction
   history vs outcomes for that batter.

App renders `output`/marts tables only — no model code, read-only
credential in Streamlit secrets.

---

## 10. Repo layout

```
mlb_hits/
  PLAN.md
  ingestion/                    # dlt project
    sources/ statcast.py  mlb_statsapi.py  fangraphs.py  odds.py
    pipelines.py                # destinations: bigquery | motherduck | local duckdb (dev)
  transform/                    # dbt project
    models/ staging/ intermediate/ marts/ ml/ output/
    tests/                      # incl. the leakage test
    packages.yml                # dbt-expectations
  ml/
    features.py  train.py  calibrate.py  backtest.py  predict.py
    params.yaml                 # splits, feature list, hyperparams
  research/                     # factor-study notebooks (disposable)
  reports/eda/                  # exported charts
  app/streamlit_app.py
  orchestration/                # v2: Dagster asset defs (wraps dlt + dbt)
  .github/workflows/ ci.yml  daily.yml
```

Local dev runs the identical stack against a local DuckDB file — no
cloud credentials needed to iterate; only the destination config
changes.

---

## 11. Phased roadmap (each phase has an acceptance gate)

**Phase 0 — Scaffold (≈1 day).** Repo, warehouse account, dlt + dbt
skeletons, CI (pytest + sqlfluff + dbt build on PR), heartbeat cron.
*Gate: scheduled run green 2 days untouched.*

**Phase 1 — Ingestion (≈1 week).** dlt sources for all feeds; port the
`MLB_hits/scripts/1_fetch_statcast.py` logic into the statcast source;
backfill 2021 → today. *Gate: source freshness green; row counts
reconcile with prototype CSVs within 0.5%.*

**Phase 2 — dbt marts (≈1 week).** Port the prototype's aggregation
and rolling-window logic (`2_aggregate.py`, `3_build_features.py`) to
SQL; build §4 in full; publish dbt docs to Pages. *Gate:
`fct_batter_game` spot-diffs clean against the prototype's
`batter_games.csv` on a sampled season; leakage test passes.*

**Phase 3 — Factor research (1–2 weeks, parallel with 4).** All 27
studies; scoreboard; feature promotion. *Gate: every factor has decile
plot + IC timeline + verdict committed.*

**Phase 4 — Models (1–2 weeks).** Baselines → structural → GBM →
calibration, all tracked in MLflow. *Gate: beats the shrunk-rate
baseline on CALIB log loss + Brier; calibration gate holds; per-tier
report written; a model is promoted in the registry.*

**Phase 5 — Backtest (≈1 week).** §8 sections 1, 2, 4 over
TEST-to-date. *Gate: top-5 picks beat the season-BA benchmark;
calibration buckets within ±3 pts.*

**Phase 6 — Daily automation (≈3 days).** predict + label in the cron,
end to end. *Gate: 7 consecutive autonomous runs with next-morning
labels correct.*

**Phase 7 — Dashboard (≈1 week).** Four pages live on Community Cloud.
*Gate: slate visible before 1 pm ET; yesterday graded.*

**Phase 8 — Odds, ROI, hardening (ongoing).** The Odds API ingestion +
§8.3; 22:00 UTC re-score cron; weekly drift job (live Brier vs backtest
Brier); optional Dagster migration on the Oracle free VM for real
orchestrator lineage/retries.

---

## 12. My own considerations & concerns

1. **PA is the elephant** — most listed factors partially proxy playing
   time; every study controls for it, and the structural model exists
   because of it.
2. **Regime shift 2023** (shift ban, pitch clock) raised BABIP
   league-wide — season features + recency weighting; 2020 dropped.
3. **Projected vs confirmed lineups** is the biggest silent accuracy
   leak — measured explicitly (backtest slice 4), mitigated by the v2
   evening re-score.
4. **Postponements/doubleheaders** — postponed games void the
   prediction (not a loss); doubleheader game-2 lineups rotate heavily,
   flag them.
5. **The market bar is high** — a calibrated model that agrees with
   −270 pricing makes $0; until Phase 8 the site's claim is *calibrated
   ranking*, not profit.
6. **Streaks are probably astrology** — the permutation tests in
   #26/27 keep a "hot streak" badge honest before it ships.
7. **BvP tables are how casual bettors lose** — display shrunk
   estimates, never raw 3-for-5.
8. **Data etiquette** — Statcast pulls rate-limited (~8 s, as the
   prototype does), cached, incremental; dashboard stays
   non-commercial.
9. **Training–serving skew** — predict-time feature rows are
   snapshotted to the warehouse, so live-vs-backtest divergence is
   diagnosable from data, not guessed.
10. **Repo hygiene** — no parquet/pickles in git (warehouse + MLflow
    artifacts instead); the NBA project's CSVs-in-git pain is the
    cautionary tale.
11. **Free-tier drift** — quotas change; the stack is portable by
    design (dlt destinations and dbt adapters are config swaps).
12. **Late scratches** — a projected lineup can be wrong at 6 pm; v2
    idea: scratch detection in the evening re-score.

---

## 13. Open decisions (defaults chosen, cheap to flip)

| Decision | Default | Alternative | Flip cost |
|---|---|---|---|
| Warehouse | BigQuery (attach billing once; $0 under free tier) | MotherDuck free (no card at all) | dlt destination + dbt adapter swap, ~1 day |
| Repo visibility | Public (unlimited Action minutes, free Streamlit) | Private (2 000 min/mo still suffices) | None |
| Orchestrator | GH Actions now, Dagster in Phase 8 | Airflow on the same free VM | Assets vs DAGs, ~2 days |
| MLflow home | Local file store in repo runs | DagsHub free hosted MLflow | Config |
| Second daily run | Off in v1 | 22:00 UTC re-score | One cron line |
| Odds source | The Odds API free | Manual CSV | Schema shared |
```

# Factor research scoreboard (Phase 3)

Promotion rule: monthly Spearman IC keeps one sign in >=70% of months
across >=3 seasons AND |median IC| >= 0.01. WEAK = stable but tiny.
CONTEXT = categorical/descriptive study, judged qualitatively.
PA-controlled IC = IC inside expected-PA terciles (playing-time proxy check).

| study | factor | verdict | median IC | sign-stable | months | PA-ctrl IC | note |
|---|---|---|---|---|---|---|---|
| [05_expected_pa](eda/05_expected_pa.png) | `pa_roll10` | **PROMOTE** | +0.137 | 100% | 41 | +0.056 | the mechanical driver |
| [00_eb_career](eda/00_eb_career.png) | `eb_hit_per_pa_career` | **PROMOTE** | +0.106 | 100% | 41 | +0.066 | the bar every factor must beat |
| [01_form_hitrate_r10](eda/01_form_hitrate_r10.png) | `has_hit_roll10` | **PROMOTE** | +0.098 | 100% | 41 | +0.049 |  |
| [03_war_prev](eda/03_war_prev.png) | `war_prev_season` | **PROMOTE** | +0.094 | 100% | 33 | +0.039 | bWAR; quality tier, partly tautological |
| [01_form_hpp_r20](eda/01_form_hpp_r20.png) | `hit_per_pa_roll20` | **PROMOTE** | +0.076 | 100% | 41 | +0.049 |  |
| [17_k](eda/17_k.png) | `k_pct_roll20` | **PROMOTE** | -0.070 | 100% | 41 | -0.049 | expect negative |
| [07b_platoon_form](eda/07b_platoon_form.png) | `hit_per_pa_platoon_roll20` | **PROMOTE** | +0.067 | 100% | 41 | +0.045 | vs today's starter hand |
| [26_hit_streak](eda/26_hit_streak.png) | `hit_streak_entering` | **PROMOTE** | +0.055 | 100% | 41 | +0.029 |  |
| [13_contact](eda/13_contact.png) | `contact_pct_roll20` | **PROMOTE** | +0.051 | 100% | 41 | +0.036 | prior: strongest family |
| [27_hitless_streak](eda/27_hitless_streak.png) | `hitless_streak_entering` | **PROMOTE** | -0.050 | 100% | 41 | -0.030 |  |
| [21b_xba_form](eda/21b_xba_form.png) | `xba_mean_roll20` | **PROMOTE** | +0.048 | 100% | 41 | +0.023 |  |
| [14_hard_hit](eda/14_hard_hit.png) | `hard_hit_pct_roll20` | **PROMOTE** | +0.048 | 100% | 41 | +0.022 |  |
| [10_barrel](eda/10_barrel.png) | `barrel_pct_roll20` | **PROMOTE** | +0.041 | 95% | 41 | +0.012 |  |
| [18_line_drive](eda/18_line_drive.png) | `line_drive_pct_roll20` | **PROMOTE** | +0.030 | 100% | 41 | +0.017 |  |
| [22b_opp_starter](eda/22b_opp_starter.png) | `p_hits_per_bf_roll10` | **PROMOTE** | +0.028 | 100% | 40 | +0.031 |  |
| [22_opp_pitching](eda/22_opp_pitching.png) | `opp_xwoba_against_roll15` | **PROMOTE** | +0.027 | 90% | 41 | +0.022 | as-of date |
| [19_sweet_spot](eda/19_sweet_spot.png) | `sweet_spot_pct_roll20` | **PROMOTE** | +0.024 | 95% | 41 | +0.009 |  |
| [12_chase](eda/12_chase.png) | `chase_rate_roll20` | **PROMOTE** | +0.014 | 80% | 41 | +0.020 |  |
| [21_xba_gap](eda/21_xba_gap.png) | `xba_minus_ba_roll20` | **PROMOTE** | -0.014 | 83% | 41 | -0.015 | the luck meter; expect positive |
| [09_team_hits](eda/09_team_hits.png) | `team_hits_roll15` | **PROMOTE** | +0.011 | 71% | 41 | -0.001 | lineup context |
| [24_bvp](eda/24_bvp.png) | `bvp_hits_per_pa` | **REJECT** | +0.005 | 62% | 26 | +0.020 | n=16,307; literature expects ≈ nothing |
| [11_walks](eda/11_walks.png) | `bb_pct_roll20` | **REJECT** | +0.003 | 63% | 41 | -0.014 | sign ambiguous by design |
| [15_league_rank](eda/15_league_rank.png) | `league_rank_entering` | **REJECT** | -0.002 | 52% | 40 | +0.001 | 1 = best |
| [02_month](eda/02_month.png) | `month` | **CONTEXT** |  |  |  |  | spread 0.029 |
| [20_year](eda/20_year.png) | `season` | **CONTEXT** |  |  |  |  | spread 0.041 |
| [06_batting_order](eda/06_batting_order.png) | `batting_order_slot` | **CONTEXT** |  |  |  |  | spread 0.215 |
| [04_home_away](eda/04_home_away.png) | `is_home` | **CONTEXT** |  |  |  |  | spread 0.004 |
| [04b_venue](eda/04b_venue.png) | `venue_name` | **CONTEXT** |  |  |  |  | spread 0.103 |
| [08_opponent](eda/08_opponent.png) | `opponent_code` | **CONTEXT** |  |  |  |  | spread 0.104 |
| [16_manager](eda/16_manager.png) | `manager_name` | **CONTEXT** |  |  |  |  | spread 0.114 |
| [07_platoon_adv](eda/07_platoon_adv.png) | `matchup` | **CONTEXT** |  |  |  |  | spread 0.035 |
| [05b_actual_pa](eda/05b_actual_pa.png) | `pa_in_game` | **CONTEXT** |  |  |  |  | spread 0.692 · mechanical: P ≈ 1-(1-p)^PA — motivates the structural model |
| [23_pitching_tiers](eda/23_pitching_tiers.png) | `tier` | **CONTEXT** |  |  |  |  | spread 0.036 · ranked daily by rolling xwOBA-against — no season-end lookahead |
| [26_streak_buckets](eda/26_streak_buckets.png) | `hit_streak_entering` | **CONTEXT** |  |  |  |  | max |obs−exp| 0.019 — streak effect beyond quality+PA |
| [25_pitch_type](eda/25_pitch_type.png) | `pitch_type` | **CONTEXT** |  |  |  |  | full-history view; interaction feature deferred to Phase 4 |

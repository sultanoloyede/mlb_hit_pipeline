-- Point-in-time feature view: one row per batter-game, every feature
-- computed STRICTLY from before the game (window frames end at
-- 1 preceding; league prior joined as-of the previous date; WAR from
-- the previous season). Same-game stat columns from fct_batter_game
-- are deliberately absent — has_hit / pa / hits are targets, not
-- features. tests/assert_no_feature_leakage.sql guards the contract.

{% set windows = [5, 10, 20, 40] %}
{% set roll_metrics = ['has_hit', 'hit_per_pa', 'pa', 'k_pct', 'bb_pct',
                       'contact_pct', 'chase_rate', 'hard_hit_pct',
                       'barrel_pct', 'sweet_spot_pct', 'line_drive_pct',
                       'xba_mean', 'xba_minus_ba'] %}
{% set platoon_metrics = ['hit_per_pa', 'k_pct', 'contact_pct',
                          'chase_rate', 'hard_hit_pct', 'barrel_pct'] %}
{% set eb_prior_pa = var('eb_prior_pa', 200) %}

with base as (
    select
        *,
        hits * 1.0 / pa                                    as hit_per_pa,
        hits_vs_l * 1.0 / nullif(pa_vs_l, 0)               as hit_per_pa_vs_l,
        hits_vs_r * 1.0 / nullif(pa_vs_r, 0)               as hit_per_pa_vs_r,
        row_number() over (
            partition by batter_id order by game_date, game_pk
        )                                                  as game_idx
    from {{ ref('fct_batter_game') }}
),

lagged as (
    select
        base.*
        -- career / season expanding sums, strictly prior
        , sum(pa)    over prior_all    as career_pa_prior
        , sum(hits)  over prior_all    as career_hits_prior
        , count(*)   over prior_all    as career_games_prior
        , sum(pa)    over prior_season as season_pa_prior
        , sum(hits)  over prior_season as season_hits_prior
        , count(*)   over prior_season as season_games_prior
        , date_diff('day', lag(game_date) over batter_seq, game_date) as days_rest
        -- streak bookkeeping (resolved below)
        , max(case when has_hit = 0 then game_idx end) over prior_all as _last_miss_idx
        , max(case when has_hit = 1 then game_idx end) over prior_all as _last_hit_idx
        {%- for w in windows %}
        {%- for m in roll_metrics %}
        , avg({{ m }}) over w{{ w }} as {{ m }}_roll{{ w }}
        {%- endfor %}
        {%- for m in platoon_metrics %}
        {%- for hand in ['l', 'r'] %}
        , avg({{ m }}_vs_{{ hand }}) over w{{ w }} as _{{ m }}_vs_{{ hand }}_roll{{ w }}
        {%- endfor %}
        {%- endfor %}
        {%- endfor %}
    from base
    window
        batter_seq   as (partition by batter_id order by game_date, game_pk),
        prior_all    as (partition by batter_id order by game_date, game_pk
                         rows between unbounded preceding and 1 preceding),
        prior_season as (partition by batter_id, season order by game_date, game_pk
                         rows between unbounded preceding and 1 preceding),
        {%- for w in windows %}
        w{{ w }} as (partition by batter_id order by game_date, game_pk
                     rows between {{ w }} preceding and 1 preceding){{ "," if not loop.last }}
        {%- endfor %}
),

war_by_season as (
    select player_id, season, sum(war) as war, sum(pa) as pa
    from {{ ref('stg_war_seasons') }}
    group by 1, 2
)

select
    -- keys & prediction-time context
    l.game_pk
    , l.game_date
    , l.season
    , l.month
    , l.day_of_week
    , l.day_night
    , l.doubleheader
    , l.venue_id
    , l.batter_id
    , l.player_name
    , l.team_id
    , l.opponent_team_id
    , l.is_home
    , l.batting_order_slot
    , l.is_substitute
    , l.opp_starter_id
    , l.opp_starter_throws
    , l.league_rank_entering
    , l.division_rank_entering
    , l.win_pct_entering

    -- targets (never features)
    , l.has_hit
    , l.pa
    , l.hits

    -- sample sizes & schedule
    , coalesce(l.career_pa_prior, 0)     as career_pa_prior
    , coalesce(l.career_games_prior, 0)  as career_games_prior
    , coalesce(l.season_pa_prior, 0)     as season_pa_prior
    , coalesce(l.season_games_prior, 0)  as season_games_prior
    , l.days_rest

    -- empirical-Bayes shrunk hit rates (Beta prior toward the
    -- point-in-time league mean, prior strength {{ eb_prior_pa }} PA)
    , lg.league_hit_per_pa               as league_hit_per_pa_entering
    , (coalesce(l.career_hits_prior, 0)
       + {{ eb_prior_pa }} * coalesce(lg.league_hit_per_pa, 0.230))
      / (coalesce(l.career_pa_prior, 0) + {{ eb_prior_pa }})   as eb_hit_per_pa_career
    , (coalesce(l.season_hits_prior, 0)
       + {{ eb_prior_pa }} * coalesce(lg.league_hit_per_pa, 0.230))
      / (coalesce(l.season_pa_prior, 0) + {{ eb_prior_pa }})   as eb_hit_per_pa_season

    -- streaks entering the game (research #26/#27)
    , (l.game_idx - 1) - coalesce(l._last_miss_idx, 0) as hit_streak_entering
    , (l.game_idx - 1) - coalesce(l._last_hit_idx, 0)  as hitless_streak_entering

    -- rolling form
    {%- for w in windows %}
    {%- for m in roll_metrics %}
    , l.{{ m }}_roll{{ w }}
    {%- endfor %}
    {%- endfor %}

    -- platoon rolling form, matched to today's opposing starter hand
    {%- for w in windows %}
    {%- for m in platoon_metrics %}
    , case when l.opp_starter_throws = 'L'
           then l._{{ m }}_vs_l_roll{{ w }}
           else l._{{ m }}_vs_r_roll{{ w }} end as {{ m }}_platoon_roll{{ w }}
    {%- endfor %}
    {%- endfor %}

    -- opposing starter rolling form
    , pr.p_starts_prior
    , pr.p_hits_per_bf_roll5
    , pr.p_hits_per_bf_roll10
    , pr.p_k_pct_roll5
    , pr.p_k_pct_roll10
    , pr.p_bb_pct_roll10
    , pr.p_swstr_pct_roll10
    , pr.p_o_swing_pct_roll10
    , pr.p_xwoba_against_roll10
    , pr.p_bf_roll10

    -- own team offense context
    , tr_off.team_hits_roll15
    , tr_off.team_runs_roll15
    , tr_off.team_pa_roll15

    -- opponent team pitching context (as-of date, no season-end rank)
    , tr_def.team_hits_allowed_per_bf_roll15 as opp_hits_allowed_per_bf_roll15
    , tr_def.team_xwoba_against_roll15       as opp_xwoba_against_roll15
    , tr_def.team_k_pct_against_roll15       as opp_k_pct_against_roll15

    -- previous-season quality (complete season -> point-in-time safe)
    , war_prev.war as war_prev_season
    , war_prev.pa  as pa_prev_season

from lagged l
asof left join {{ ref('int_league_daily') }} lg
       on l.game_date > lg.game_date
left join {{ ref('int_pitcher_rolling') }} pr
       on pr.game_pk = l.game_pk and pr.pitcher_id = l.opp_starter_id
left join {{ ref('int_team_rolling') }} tr_off
       on tr_off.game_pk = l.game_pk and tr_off.team_id = l.team_id
left join {{ ref('int_team_rolling') }} tr_def
       on tr_def.game_pk = l.game_pk and tr_def.team_id = l.opponent_team_id
left join war_by_season war_prev
       on war_prev.player_id = l.batter_id and war_prev.season = l.season - 1

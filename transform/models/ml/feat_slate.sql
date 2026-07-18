-- Prediction-time feature rows for the slate of a given date: one row
-- per projected/posted lineup batter, with the SAME feature contract
-- as feat_batter_game — but windows end at each batter's latest game
-- (frames include the current row here, because "today" isn't played).
--
-- Everything reads strictly from BEFORE the slate date, so a backdated
-- run (--vars '{slate_date: 2026-07-12}') is a legitimate point-in-time
-- test. Default slate date is today.

{% set sd = var('slate_date', none) %}
{% set slate = ("date '" ~ sd ~ "'") if sd else "current_date" %}
{% set windows = [5, 10, 20, 40] %}
{% set roll_metrics = ['has_hit', 'hit_per_pa', 'pa', 'k_pct', 'bb_pct',
                       'contact_pct', 'chase_rate', 'hard_hit_pct',
                       'barrel_pct', 'sweet_spot_pct', 'line_drive_pct',
                       'xba_mean', 'xba_minus_ba'] %}
{% set platoon_metrics = ['hit_per_pa', 'k_pct', 'contact_pct',
                          'chase_rate', 'hard_hit_pct', 'barrel_pct'] %}
{% set eb_prior_pa = var('eb_prior_pa', 200) %}

with slate_games as (
    select * from {{ ref('dim_game') }}
    where official_date = {{ slate }} and game_type = 'R'
),

sides as (
    select game_pk, official_date, season, month, day_of_week, day_night,
           doubleheader, venue_id,
           home_team_id as team_id, away_team_id as opponent_team_id,
           true as is_home, away_probable_pitcher_id as opp_starter_id
    from slate_games
    union all
    select game_pk, official_date, season, month, day_of_week, day_night,
           doubleheader, venue_id,
           away_team_id, home_team_id, false, home_probable_pitcher_id
    from slate_games
),

hist as (
    select *,
           hits * 1.0 / pa                      as hit_per_pa,
           hits_vs_l * 1.0 / nullif(pa_vs_l, 0) as hit_per_pa_vs_l,
           hits_vs_r * 1.0 / nullif(pa_vs_r, 0) as hit_per_pa_vs_r
    from {{ ref('fct_batter_game') }}
    where game_date < {{ slate }}
),

seq as (
    select hist.*,
           row_number() over (partition by batter_id
                              order by game_date, game_pk) as game_idx
    from hist
),

windowed as (
    select
        seq.*
        , game_idx                   as career_games_cum
        , sum(pa)    over cum        as career_pa_cum
        , sum(hits)  over cum        as career_hits_cum
        , count(*)   over cum_season as season_games_cum
        , sum(pa)    over cum_season as season_pa_cum
        , sum(hits)  over cum_season as season_hits_cum
        , max(case when has_hit = 0 then game_idx end) over cum as _last_miss_idx
        , max(case when has_hit = 1 then game_idx end) over cum as _last_hit_idx
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
        , row_number() over (partition by batter_id
                             order by game_date desc, game_pk desc) as _rn_desc
    from seq
    window
        cum        as (partition by batter_id order by game_date, game_pk
                       rows between unbounded preceding and current row),
        cum_season as (partition by batter_id, season order by game_date, game_pk
                       rows between unbounded preceding and current row),
        {%- for w in windows %}
        w{{ w }} as (partition by batter_id order by game_date, game_pk
                     rows between {{ w - 1 }} preceding and current row){{ "," if not loop.last }}
        {%- endfor %}
),

batter_current as (
    select * from windowed where _rn_desc = 1
),

-- projected lineups: batters who started for the team recently; slot =
-- modal batting order over their last 7 starts
recent_starts as (
    select batter_id, team_id, batting_order_slot, game_date, game_pk,
           row_number() over (partition by batter_id
                              order by game_date desc, game_pk desc) as start_rn
    from hist
    where batting_order_slot between 1 and 9 and not is_substitute
      and game_date >= {{ slate }} - interval 15 day
),

projected as (
    select team_id, batter_id, batting_order_slot, n_recent_starts
    from (
        select
            team_id, batter_id,
            mode(batting_order_slot) filter (where start_rn <= 7) as batting_order_slot,
            count(*)                                              as n_recent_starts,
            max(game_date)                                        as last_start,
            row_number() over (partition by team_id
                               order by count(*) desc, max(game_date) desc) as team_rank
        from recent_starts
        group by team_id, batter_id
    )
    where team_rank <= 9
),

posted as (
    select game_pk, team_id, player_id as batter_id, batting_order_slot
    from {{ ref('stg_lineups') }}
    where official_date = {{ slate }} and batting_order_slot between 1 and 9
),

posted_teams as (
    select distinct game_pk, team_id from posted
),

roster as (
    select sides.game_pk, sides.team_id, posted.batter_id,
           posted.batting_order_slot, true as lineup_confirmed
    from sides
    join posted on posted.game_pk = sides.game_pk
               and posted.team_id = sides.team_id
    union all
    select sides.game_pk, sides.team_id, projected.batter_id,
           projected.batting_order_slot, false
    from sides
    join projected on projected.team_id = sides.team_id
    where not exists (select 1 from posted_teams pt
                      where pt.game_pk = sides.game_pk
                        and pt.team_id = sides.team_id)
),

-- opposing starter current form (frames include latest start)
pitcher_current as (
    select * from (
        select
            pitcher_id,
            count(*)  over cumP                                   as p_starts_prior,
            avg(hits_conceded * 1.0 / nullif(bf, 0)) over w5p     as p_hits_per_bf_roll5,
            avg(hits_conceded * 1.0 / nullif(bf, 0)) over w10p    as p_hits_per_bf_roll10,
            avg(k_pct)         over w5p                           as p_k_pct_roll5,
            avg(k_pct)         over w10p                          as p_k_pct_roll10,
            avg(bb_pct)        over w10p                          as p_bb_pct_roll10,
            avg(swstr_pct)     over w10p                          as p_swstr_pct_roll10,
            avg(o_swing_pct)   over w10p                          as p_o_swing_pct_roll10,
            avg(xwoba_against) over w10p                          as p_xwoba_against_roll10,
            avg(bf)            over w10p                          as p_bf_roll10,
            row_number() over (partition by pitcher_id
                               order by game_date desc, game_pk desc) as _rn
        from {{ ref('fct_pitcher_game') }}
        where is_starter and game_date < {{ slate }}
        window
            cumP as (partition by pitcher_id order by game_date, game_pk
                     rows between unbounded preceding and current row),
            w5p  as (partition by pitcher_id order by game_date, game_pk
                     rows between 4 preceding and current row),
            w10p as (partition by pitcher_id order by game_date, game_pk
                     rows between 9 preceding and current row)
    ) where _rn = 1
),

team_current as (
    select * from (
        select
            team_id,
            avg(hits) over w15t                                        as team_hits_roll15,
            avg(runs) over w15t                                        as team_runs_roll15,
            avg(pa)   over w15t                                        as team_pa_roll15,
            avg(hits_allowed * 1.0 / nullif(bf_against, 0)) over w15t  as team_hits_allowed_per_bf_roll15,
            avg(xwoba_against) over w15t                               as team_xwoba_against_roll15,
            avg(strikeouts_thrown * 1.0 / nullif(bf_against, 0)) over w15t as team_k_pct_against_roll15,
            row_number() over (partition by team_id
                               order by game_date desc, game_pk desc) as _rn
        from {{ ref('fct_team_game') }}
        where game_date < {{ slate }}
        window w15t as (partition by team_id order by game_date, game_pk
                        rows between 14 preceding and current row)
    ) where _rn = 1
),

standings_latest as (
    select * from (
        select team_id, league_rank, division_rank, win_pct,
               row_number() over (partition by team_id
                                  order by standings_date desc) as _rn
        from {{ ref('fct_standings_daily') }}
        where standings_date < {{ slate }}
    ) where _rn = 1
),

league as (
    select sum(hits) * 1.0 / nullif(sum(pa), 0) as league_hit_per_pa
    from hist
),

war_by_season as (
    select player_id, season, sum(war) as war, sum(pa) as pa
    from {{ ref('stg_war_seasons') }}
    group by 1, 2
)

select
    sides.game_pk
    , sides.official_date                as game_date
    , sides.season
    , sides.month
    , sides.day_of_week
    , sides.day_night
    , sides.doubleheader
    , sides.venue_id
    , roster.batter_id
    , bc.player_name
    , roster.team_id
    , sides.opponent_team_id
    , sides.is_home
    , roster.batting_order_slot
    , false                              as is_substitute
    , roster.lineup_confirmed
    , sides.opp_starter_id
    , opp_throws.throws                  as opp_starter_throws
    , standings_latest.league_rank       as league_rank_entering
    , standings_latest.division_rank     as division_rank_entering
    , standings_latest.win_pct           as win_pct_entering

    , bc.career_pa_cum                   as career_pa_prior
    , bc.career_hits_cum                 as career_hits_prior
    , bc.career_games_cum                as career_games_prior
    , case when bc.season = sides.season then bc.season_pa_cum    else 0 end as season_pa_prior
    , case when bc.season = sides.season then bc.season_hits_cum  else 0 end as season_hits_prior
    , case when bc.season = sides.season then bc.season_games_cum else 0 end as season_games_prior
    , date_diff('day', bc.game_date, sides.official_date) as days_rest

    , league.league_hit_per_pa           as league_hit_per_pa_entering
    , (bc.career_hits_cum + {{ eb_prior_pa }} * league.league_hit_per_pa)
      / (bc.career_pa_cum + {{ eb_prior_pa }})                    as eb_hit_per_pa_career
    , (case when bc.season = sides.season then bc.season_hits_cum else 0 end
       + {{ eb_prior_pa }} * league.league_hit_per_pa)
      / (case when bc.season = sides.season then bc.season_pa_cum else 0 end
         + {{ eb_prior_pa }})                                     as eb_hit_per_pa_season

    , bc.career_games_cum - coalesce(bc._last_miss_idx, 0) as hit_streak_entering
    , bc.career_games_cum - coalesce(bc._last_hit_idx, 0)  as hitless_streak_entering

    {%- for w in windows %}
    {%- for m in roll_metrics %}
    , bc.{{ m }}_roll{{ w }}
    {%- endfor %}
    {%- endfor %}

    {%- for w in windows %}
    {%- for m in platoon_metrics %}
    , case when opp_throws.throws = 'L'
           then bc._{{ m }}_vs_l_roll{{ w }}
           else bc._{{ m }}_vs_r_roll{{ w }} end as {{ m }}_platoon_roll{{ w }}
    {%- endfor %}
    {%- endfor %}

    , pc.p_starts_prior
    , pc.p_hits_per_bf_roll5
    , pc.p_hits_per_bf_roll10
    , pc.p_k_pct_roll5
    , pc.p_k_pct_roll10
    , pc.p_bb_pct_roll10
    , pc.p_swstr_pct_roll10
    , pc.p_o_swing_pct_roll10
    , pc.p_xwoba_against_roll10
    , pc.p_bf_roll10

    , t_off.team_hits_roll15
    , t_off.team_runs_roll15
    , t_off.team_pa_roll15
    , t_def.team_hits_allowed_per_bf_roll15 as opp_hits_allowed_per_bf_roll15
    , t_def.team_xwoba_against_roll15       as opp_xwoba_against_roll15
    , t_def.team_k_pct_against_roll15       as opp_k_pct_against_roll15

    , war_prev.war as war_prev_season
    , war_prev.pa  as pa_prev_season

from roster
join sides           on sides.game_pk = roster.game_pk
                    and sides.team_id = roster.team_id
join batter_current bc on bc.batter_id = roster.batter_id
cross join league
left join {{ ref('dim_player') }} opp_throws
       on opp_throws.player_id = sides.opp_starter_id
left join pitcher_current pc on pc.pitcher_id = sides.opp_starter_id
left join team_current t_off on t_off.team_id = roster.team_id
left join team_current t_def on t_def.team_id = sides.opponent_team_id
left join standings_latest   on standings_latest.team_id = roster.team_id
left join war_by_season war_prev
       on war_prev.player_id = roster.batter_id
      and war_prev.season = sides.season - 1

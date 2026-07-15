-- THE core table: one row per batter per regular-season game with >= 1
-- official plate appearance.
--
-- Label and playing time come from the official boxscore
-- (stg_batting_lines); contact quality and plate discipline come from
-- Statcast (int_batter_game*, sc_-prefixed where the statcast-derived
-- count could differ from the official one). All columns describe THIS
-- game — point-in-time lagged features are built on top of this table
-- in the ml layer, never here.
with base as (
    select * from {{ ref('stg_batting_lines') }}
    where plate_appearances >= 1
),

games as (
    select * from {{ ref('dim_game') }}
    where game_type = 'R'
)

select
    -- keys & context
    base.game_pk,
    games.official_date                       as game_date,
    games.season,
    games.month,
    games.day_of_week,
    games.day_night,
    games.doubleheader,
    games.venue_id,
    games.venue_name,
    base.player_id                            as batter_id,
    base.player_name,
    base.team_id,
    base.is_home,
    case when base.is_home then games.away_team_id
         else games.home_team_id end          as opponent_team_id,
    case when base.is_home then games.away_team_name
         else games.home_team_name end        as opponent_team_name,

    -- opposing starting pitcher (actual, from the game's first pitch)
    case when base.is_home then games.away_starter_id
         else games.home_starter_id end       as opp_starter_id,
    case when base.is_home then games.away_starter_throws
         else games.home_starter_throws end   as opp_starter_throws,
    sc.opp_p_throws,

    -- lineup
    base.batting_order_slot,
    base.is_substitute,

    -- label + official line
    base.plate_appearances                    as pa,
    base.at_bats                              as ab,
    base.hits,
    (base.hits >= 1)::int                     as has_hit,
    base.walks,
    base.strikeouts,
    base.home_runs,
    base.runs,
    base.rbi,

    -- statcast quality metrics (this game)
    sc.sc_pa,
    sc.sc_hits,
    sc.k_pct,
    sc.bb_pct,
    sc.hard_hit_pct,
    sc.barrel_pct,
    sc.sweet_spot_pct,
    sc.line_drive_pct,
    sc.contact_pct,
    sc.chase_rate,
    sc.xba_mean,
    sc.xslg_mean,
    sc.xwoba_mean,
    sc.woba_mean,
    sc.ba,
    sc.xba_minus_ba,

    -- platoon splits (this game)
    {%- for hand in ['l', 'r'] %}
    {%- for col in ['hits', 'pa', 'k_pct', 'bb_pct', 'hard_hit_pct',
                    'barrel_pct', 'sweet_spot_pct', 'line_drive_pct',
                    'contact_pct', 'chase_rate'] %}
    platoon.{{ col }}_vs_{{ hand }},
    {%- endfor %}
    {%- endfor %}

    -- team context entering the day (standings through yesterday)
    standings.league_rank                     as league_rank_entering,
    standings.division_rank                   as division_rank_entering,
    standings.win_pct                         as win_pct_entering,

    -- bench (research factor #16)
    manager.manager_id,
    manager.manager_name

from base
join games on games.game_pk = base.game_pk
left join {{ ref('int_batter_game') }} sc
       on sc.game_pk = base.game_pk and sc.batter_id = base.player_id
left join {{ ref('int_batter_game_platoon') }} platoon
       on platoon.game_pk = base.game_pk and platoon.batter_id = base.player_id
left join {{ ref('fct_standings_daily') }} standings
       on standings.team_id = base.team_id
      and standings.standings_date = games.official_date - interval 1 day
left join {{ ref('dim_manager') }} manager
       on manager.team_id = base.team_id and manager.season = games.season

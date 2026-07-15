-- Team crosswalk: Stats API numeric id <-> Statcast code, via games the
-- two sources share (game_pk). Latest name wins (franchise renames).
with sides as (
    select
        g.home_team_id  as team_id,
        g.home_team_name as team_name,
        p.home_team     as team_code,
        g.official_date
    from {{ ref('stg_games') }} g
    join (select distinct game_pk, home_team, away_team
          from {{ ref('stg_statcast_pitches') }}) p using (game_pk)

    union all

    select
        g.away_team_id,
        g.away_team_name,
        p.away_team,
        g.official_date
    from {{ ref('stg_games') }} g
    join (select distinct game_pk, home_team, away_team
          from {{ ref('stg_statcast_pitches') }}) p using (game_pk)
)

select
    team_id,
    arg_max(team_name, official_date) as team_name,
    mode(team_code)                   as team_code
from sides
group by 1

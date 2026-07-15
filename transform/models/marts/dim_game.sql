-- One row per scheduled game with everything context-shaped: date
-- parts, venue, teams, status, doubleheader, probables, actual starters.
select
    g.game_pk,
    g.official_date,
    g.season,
    g.game_type,
    g.status,
    g.day_night,
    g.doubleheader,
    g.game_number,
    date_part('month', g.official_date)  as month,
    dayname(g.official_date)             as day_of_week,
    g.venue_id,
    g.venue_name,
    g.home_team_id,
    g.home_team_name,
    g.away_team_id,
    g.away_team_name,
    g.home_probable_pitcher_id,
    g.away_probable_pitcher_id,
    hs.starter_id      as home_starter_id,
    hs.starter_throws  as home_starter_throws,
    aws.starter_id     as away_starter_id,
    aws.starter_throws as away_starter_throws
from {{ ref('stg_games') }} g
left join {{ ref('int_game_starters') }} hs
       on hs.game_pk = g.game_pk and hs.pitching_side = 'home'
left join {{ ref('int_game_starters') }} aws
       on aws.game_pk = g.game_pk and aws.pitching_side = 'away'

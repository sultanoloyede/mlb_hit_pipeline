-- One row per game, keeping the latest load (status and probables
-- change across loads: Scheduled -> Final, postponements, etc.)
with ranked as (
    select
        *,
        row_number() over (
            partition by game_pk
            order by _dlt_load_id desc
        ) as _rn
    from {{ source('raw', 'games') }}
)

select
    game_pk,
    cast(official_date as date)  as official_date,
    cast(season as integer)      as season,
    game_type,
    status,
    day_night,
    doubleheader,
    game_number,
    venue_id,
    venue_name,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    home_probable_pitcher_id,
    home_probable_pitcher_name,
    away_probable_pitcher_id,
    away_probable_pitcher_name
from ranked
where _rn = 1

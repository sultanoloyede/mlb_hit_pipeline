-- Baseball-Reference batter WAR per player-season-stint. mlb_id joins
-- directly to Stats API / Statcast batter ids.
-- DataFrame loads carry no _dlt_load_id; the row with the most PA is
-- the most recent download of an in-progress season (PA only grows).
with ranked as (
    select
        *,
        row_number() over (
            partition by mlb_id, year_id, stint_id
            order by pa desc nulls last, war desc nulls last
        ) as _rn
    from {{ source('raw', 'bref_war_bat_seasons') }}
)

select
    cast(mlb_id as bigint)    as player_id,
    name_common               as player_name,
    cast(year_id as integer)  as season,
    cast(stint_id as integer) as stint,
    team_id                   as bref_team_code,
    lg_id                     as league,
    cast(pa as integer)       as pa,
    cast(g as integer)        as games,
    cast(war as double)       as war
from ranked
where _rn = 1
  and mlb_id is not null

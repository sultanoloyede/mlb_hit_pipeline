-- Season-to-date WAR stamped per snapshot day — the point-in-time
-- quality view live features use.
-- DataFrame loads carry no _dlt_load_id; within one snapshot_date a
-- higher PA row is the later same-day re-download.
with ranked as (
    select
        *,
        row_number() over (
            partition by mlb_id, year_id, stint_id, snapshot_date
            order by pa desc nulls last, war desc nulls last
        ) as _rn
    from {{ source('raw', 'bref_war_bat_snapshots') }}
)

select
    cast(snapshot_date as date) as snapshot_date,
    cast(mlb_id as bigint)      as player_id,
    name_common                 as player_name,
    cast(year_id as integer)    as season,
    cast(stint_id as integer)   as stint,
    cast(pa as integer)         as pa,
    cast(g as integer)          as games,
    cast(war as double)         as war
from ranked
where _rn = 1
  and mlb_id is not null

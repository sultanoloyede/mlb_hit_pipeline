-- Posted lineups for upcoming games; latest load per (game, player)
-- wins so a lineup change before first pitch supersedes earlier posts.
--
-- raw.lineups doesn't exist until the first daily run catches a posted
-- lineup (dlt only creates tables it has rows for), so emit an empty,
-- correctly-typed relation until then to keep builds green.
{% set lineups_relation = load_relation(source('raw', 'lineups')) %}

{% if lineups_relation is none %}

select
    cast(null as bigint)  as game_pk,
    cast(null as date)    as official_date,
    cast(null as bigint)  as team_id,
    cast(null as boolean) as is_home,
    cast(null as bigint)  as player_id,
    cast(null as varchar) as player_name,
    cast(null as bigint)  as batting_order_raw,
    cast(null as integer) as batting_order_slot,
    cast(null as varchar) as game_status
where false

{% else %}

with ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, player_id
            order by _dlt_load_id desc
        ) as _rn
    from {{ source('raw', 'lineups') }}
)

select
    game_pk,
    cast(official_date as date)          as official_date,
    team_id,
    is_home,
    player_id,
    player_name,
    batting_order                        as batting_order_raw,
    cast(batting_order / 100 as integer) as batting_order_slot,
    game_status
from ranked
where _rn = 1

{% endif %}

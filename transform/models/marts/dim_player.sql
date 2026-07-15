-- One row per player: name (latest official boxscore spelling), batting
-- side observed at the plate ('S' when both sides carry real volume),
-- and throwing hand observed on the mound.
with batter_stand as (
    select batter_id as player_id, stand, count(*) as n
    from {{ ref('stg_statcast_pitches') }}
    group by 1, 2
),

bats as (
    select
        player_id,
        case when count(*) = 2 and min(n) * 1.0 / sum(n) > 0.10 then 'S'
             else arg_max(stand, n) end as bats
    from batter_stand
    group by 1
),

throws as (
    select pitcher_id as player_id, mode(p_throws) as throws
    from {{ ref('stg_statcast_pitches') }}
    group by 1
),

boxscore_names as (
    select player_id, arg_max(player_name, official_date) as player_name
    from {{ ref('stg_batting_lines') }}
    group by 1
),

pitcher_names as (
    select pitcher_id as player_id, arg_max(pitcher_name, game_date) as player_name
    from {{ ref('stg_statcast_pitches') }}
    group by 1
),

all_ids as (
    select player_id from bats
    union
    select player_id from throws
)

select
    all_ids.player_id,
    coalesce(boxscore_names.player_name, pitcher_names.player_name,
             cast(all_ids.player_id as varchar)) as player_name,
    bats.bats,
    throws.throws,
    throws.player_id is not null                 as has_pitched,
    bats.player_id is not null                   as has_batted
from all_ids
left join bats           using (player_id)
left join throws         using (player_id)
left join boxscore_names using (player_id)
left join pitcher_names  using (player_id)

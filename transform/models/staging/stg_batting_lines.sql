-- Official per-batter boxscore lines (the label source), deduped by
-- (game, player) keeping the latest load. battingOrder arrives in
-- boxscore form: 100 = leadoff starter, last digit > 0 = substitute.
with ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, player_id
            order by _dlt_load_id desc
        ) as _rn
    from {{ source('raw', 'batting_lines') }}
)

select
    game_pk,
    cast(official_date as date)          as official_date,
    game_type,
    team_id,
    is_home,
    player_id,
    player_name,
    position,
    batting_order                        as batting_order_raw,
    cast(batting_order / 100 as integer) as batting_order_slot,
    is_substitute,
    plate_appearances,
    at_bats,
    hits,
    doubles,
    triples,
    home_runs,
    walks,
    strikeouts,
    runs,
    rbi
from ranked
where _rn = 1

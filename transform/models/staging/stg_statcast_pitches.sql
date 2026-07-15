-- Pitch level, deduped by pitch key (raw is append-only;
-- season-boundary days are refetched by design). DataFrame loads don't
-- carry _dlt_load_id, and duplicate pitches are identical refetches of
-- the same event, so the tiebreak is arbitrary.
with ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, at_bat_number, pitch_number
            order by game_date
        ) as _rn
    from {{ source('raw', 'statcast_pitches') }}
)

select
    game_pk,
    cast(game_date as date)          as game_date,
    game_type,
    home_team,
    away_team,
    batter                           as batter_id,
    pitcher                          as pitcher_id,
    player_name                      as pitcher_name,
    stand,
    p_throws,
    inning,
    inning_topbot,
    at_bat_number,
    pitch_number,
    outs_when_up,
    balls,
    strikes,
    pitch_type,
    release_speed,
    zone,
    type                             as pitch_result_type,
    description,
    events,
    bb_type,
    woba_value,
    babip_value,
    launch_speed,
    launch_angle,
    launch_speed_angle,
    estimated_ba_using_speedangle    as xba,
    estimated_woba_using_speedangle  as xwoba,
    estimated_slg_using_speedangle   as xslg
from ranked
where _rn = 1

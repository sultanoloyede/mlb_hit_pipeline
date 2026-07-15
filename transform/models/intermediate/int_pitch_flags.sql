-- Pitch-level classification flags. Definitions ported verbatim from
-- the prototype (MLB_hits/scripts/2_aggregate.py) so fct_batter_game
-- reconciles against batter_games.csv:
--   swing / contact / whiff description sets, zones 1-9 in / 11-14 out,
--   chase = swing at an out-of-zone pitch, barrel = MLB definition
--   (EV >= 98 with the widening launch-angle window).
select
    *,

    description in (
        'swinging_strike', 'swinging_strike_blocked',
        'foul', 'foul_tip', 'foul_bunt',
        'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score'
    )                                                       as is_swing,

    description in (
        'foul', 'foul_tip', 'foul_bunt',
        'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score'
    )                                                       as is_contact,

    description in ('swinging_strike', 'swinging_strike_blocked')
                                                            as is_whiff,

    zone between 1 and 9                                    as is_in_zone,
    zone between 11 and 14                                  as is_out_zone,
    (zone between 11 and 14) and description in (
        'swinging_strike', 'swinging_strike_blocked',
        'foul', 'foul_tip', 'foul_bunt',
        'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score'
    )                                                       as is_chase,

    -- plate-appearance outcome flags (populated on the final pitch)
    events is not null                                      as is_pa_end,
    events in ('single', 'double', 'triple', 'home_run')    as is_hit,
    events = 'strikeout'                                    as is_k,
    events = 'walk'                                         as is_bb,
    events is not null and events not in (
        'walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt',
        'sac_fly_double_play', 'catcher_interf'
    )                                                       as is_ab,

    -- batted-ball flags
    pitch_result_type = 'X'                                 as is_bip,
    pitch_result_type = 'X' and launch_speed >= 95          as is_hard_hit,
    pitch_result_type = 'X'
        and launch_angle between 8 and 32                   as is_sweet_spot,
    pitch_result_type = 'X' and bb_type = 'line_drive'      as is_line_drive,
    pitch_result_type = 'X'
        and launch_speed >= 98
        and launch_angle between greatest(26 - 1.5 * (launch_speed - 98), 8)
                             and least(30 + 1.5 * (launch_speed - 98), 50)
                                                            as is_barrel
from {{ ref('stg_statcast_pitches') }}

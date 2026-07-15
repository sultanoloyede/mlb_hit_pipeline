-- One row per pitcher per game — feeds opponent-starter quality
-- features and the pitching-team studies. Mirrors the prototype's
-- aggregate_pitchers().
with pitches as (
    select * from {{ ref('int_pitch_flags') }}
),

pa_agg as (
    select
        game_pk, game_date, pitcher_id,
        count(*)                              as bf,
        count(*) filter (where is_k)          as strikeouts,
        count(*) filter (where is_bb)         as walks,
        count(*) filter (where is_hit)        as hits_conceded
    from pitches
    where is_pa_end
    group by 1, 2, 3
),

pitch_agg as (
    select
        game_pk, game_date, pitcher_id,
        max(p_throws)                                     as p_throws,
        max(pitcher_name)                                 as pitcher_name,
        case when max(inning_topbot) = 'Top'
             then max(home_team) else max(away_team) end  as team_code,
        count(*)                                          as total_pitches,
        count(*) filter (where is_swing)                  as swings,
        count(*) filter (where is_whiff)                  as whiffs,
        count(*) filter (where is_in_zone)                as pitches_in_zone,
        count(*) filter (where is_out_zone)               as pitches_out_zone,
        count(*) filter (where is_in_zone and is_swing)   as z_swings,
        count(*) filter (where is_out_zone and is_swing)  as o_swings,
        avg(xwoba) filter (where is_pa_end)               as xwoba_against
    from pitches
    group by 1, 2, 3
)

select
    pa_agg.game_pk,
    pa_agg.game_date,
    pa_agg.pitcher_id,
    pitch_agg.pitcher_name,
    pitch_agg.team_code,
    pitch_agg.p_throws,
    (starters.starter_id is not null)                                         as is_starter,

    pa_agg.bf,
    pa_agg.hits_conceded,
    pitch_agg.total_pitches,
    round(pa_agg.strikeouts * 1.0 / nullif(pa_agg.bf, 0), 4)                  as k_pct,
    round(pa_agg.walks * 1.0 / nullif(pa_agg.bf, 0), 4)                       as bb_pct,
    round(pitch_agg.o_swings * 1.0 / nullif(pitch_agg.pitches_out_zone, 0), 4) as o_swing_pct,
    round(pitch_agg.z_swings * 1.0 / nullif(pitch_agg.pitches_in_zone, 0), 4)  as z_swing_pct,
    round(pitch_agg.whiffs * 1.0 / nullif(pitch_agg.total_pitches, 0), 4)      as swstr_pct,
    round(pitch_agg.xwoba_against, 4)                                          as xwoba_against

from pa_agg
join pitch_agg using (game_pk, game_date, pitcher_id)
left join {{ ref('int_game_starters') }} starters
       on starters.game_pk = pa_agg.game_pk
      and starters.starter_id = pa_agg.pitcher_id

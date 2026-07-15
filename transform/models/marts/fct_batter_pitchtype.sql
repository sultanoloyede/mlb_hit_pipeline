-- Batter performance by pitch type faced, full history (research
-- factor #25: heatmap + the pitch-mix interaction feature). Not
-- point-in-time — research use only, never a direct model feature.
select
    batter_id,
    pitch_type,
    count(*)                                            as pitches_seen,
    count(*) filter (where is_swing)                    as swings,
    count(*) filter (where is_whiff)                    as whiffs,
    round(count(*) filter (where is_whiff) * 1.0
          / nullif(count(*) filter (where is_swing), 0), 4) as whiff_per_swing,
    count(*) filter (where is_pa_end)                   as pa_ended,
    count(*) filter (where is_ab)                       as ab_ended,
    count(*) filter (where is_pa_end and is_hit)        as hits,
    round(count(*) filter (where is_pa_end and is_hit) * 1.0
          / nullif(count(*) filter (where is_ab), 0), 4)    as ba,
    round(avg(xba) filter (where is_bip), 4)            as xba_mean
from {{ ref('int_pitch_flags') }}
where pitch_type is not null
group by 1, 2

-- Batter-game rate stats split by opposing pitcher hand, pivoted wide
-- (hits_vs_l, k_pct_vs_r, ...) exactly like the prototype's platoon
-- columns.
with pitches as (
    select * from {{ ref('int_pitch_flags') }}
),

by_hand as (
    select
        game_pk, game_date, batter_id, p_throws,

        count(*) filter (where is_pa_end)             as pa,
        count(*) filter (where is_pa_end and is_hit)  as hits,
        count(*) filter (where is_pa_end and is_k)    as strikeouts,
        count(*) filter (where is_pa_end and is_bb)   as walks,

        count(*) filter (where is_swing)              as swings,
        count(*) filter (where is_contact)            as contacts,
        count(*) filter (where is_out_zone)           as pitches_out_zone,
        count(*) filter (where is_chase)              as chases,

        count(*) filter (where is_bip)                as bip,
        count(*) filter (where is_hard_hit)           as hard_hits,
        count(*) filter (where is_barrel)             as barrels,
        count(*) filter (where is_sweet_spot)         as sweet_spots,
        count(*) filter (where is_line_drive)         as line_drives
    from pitches
    group by 1, 2, 3, 4
),

rates as (
    select
        game_pk, game_date, batter_id, p_throws,
        hits,
        pa,
        round(strikeouts * 1.0 / nullif(pa, 0), 4)           as k_pct,
        round(walks * 1.0 / nullif(pa, 0), 4)                as bb_pct,
        round(hard_hits * 1.0 / nullif(bip, 0), 4)           as hard_hit_pct,
        round(barrels * 1.0 / nullif(bip, 0), 4)             as barrel_pct,
        round(sweet_spots * 1.0 / nullif(bip, 0), 4)         as sweet_spot_pct,
        round(line_drives * 1.0 / nullif(bip, 0), 4)         as line_drive_pct,
        round(contacts * 1.0 / nullif(swings, 0), 4)         as contact_pct,
        round(chases * 1.0 / nullif(pitches_out_zone, 0), 4) as chase_rate
    from by_hand
)

select
    game_pk,
    game_date,
    batter_id
    {%- for hand in ['L', 'R'] %}
    {%- for col in ['hits', 'pa', 'k_pct', 'bb_pct', 'hard_hit_pct',
                    'barrel_pct', 'sweet_spot_pct', 'line_drive_pct',
                    'contact_pct', 'chase_rate'] %},
    max(case when p_throws = '{{ hand }}' then {{ col }} end) as {{ col }}_vs_{{ hand | lower }}
    {%- endfor %}
    {%- endfor %}
from rates
group by 1, 2, 3

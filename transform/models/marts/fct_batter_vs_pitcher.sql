-- Career batter-vs-pitcher stats ENTERING each meeting: expanding sums
-- over all prior games between the pair (the prototype's cumsum +
-- shift(1), as a window frame that excludes the current game). Rows
-- with bvp_pa_career null are first meetings.
with per_game as (
    select
        batter_id,
        pitcher_id,
        game_pk,
        game_date,
        count(*) filter (where is_pa_end)             as bvp_pa,
        count(*) filter (where is_pa_end and is_hit)  as bvp_hits,
        count(*) filter (where is_pa_end and is_k)    as bvp_k,
        count(*) filter (where is_pa_end and is_bb)   as bvp_bb,
        count(*) filter (where is_bip)                as bvp_bip,
        count(*) filter (where is_hard_hit)           as bvp_hard_hits,
        count(*) filter (where is_barrel)             as bvp_barrels
    from {{ ref('int_pitch_flags') }}
    group by 1, 2, 3, 4
),

career as (
    select
        *,
        sum(bvp_pa)        over prior as bvp_pa_career,
        sum(bvp_hits)      over prior as bvp_hits_career,
        sum(bvp_k)         over prior as bvp_k_career,
        sum(bvp_bb)        over prior as bvp_bb_career,
        sum(bvp_bip)       over prior as bvp_bip_career,
        sum(bvp_hard_hits) over prior as bvp_hard_hits_career,
        sum(bvp_barrels)   over prior as bvp_barrels_career
    from per_game
    window prior as (
        partition by batter_id, pitcher_id
        order by game_date, game_pk
        rows between unbounded preceding and 1 preceding
    )
)

select
    batter_id,
    pitcher_id,
    game_pk,
    game_date,
    bvp_pa_career,
    round(bvp_hits_career * 1.0 / nullif(bvp_pa_career, 0), 4)      as bvp_hits_per_pa,
    round(bvp_k_career * 1.0 / nullif(bvp_pa_career, 0), 4)         as bvp_k_pct,
    round(bvp_bb_career * 1.0 / nullif(bvp_pa_career, 0), 4)        as bvp_bb_pct,
    round(bvp_hard_hits_career * 1.0 / nullif(bvp_bip_career, 0), 4) as bvp_hard_hit_pct,
    round(bvp_barrels_career * 1.0 / nullif(bvp_bip_career, 0), 4)   as bvp_barrel_pct
from career

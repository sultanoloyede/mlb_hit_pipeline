-- Rolling form of each STARTER entering each start (frames end at
-- 1 preceding — the current start is never included). Joined into
-- feat_batter_game as the opposing-starter quality features.
with starts as (
    select * from {{ ref('fct_pitcher_game') }}
    where is_starter
)

select
    game_pk,
    game_date,
    pitcher_id,
    count(*)  over w10                                        as p_starts_prior,
    avg(hits_conceded * 1.0 / nullif(bf, 0)) over w5          as p_hits_per_bf_roll5,
    avg(hits_conceded * 1.0 / nullif(bf, 0)) over w10         as p_hits_per_bf_roll10,
    avg(k_pct)          over w5                               as p_k_pct_roll5,
    avg(k_pct)          over w10                              as p_k_pct_roll10,
    avg(bb_pct)         over w10                              as p_bb_pct_roll10,
    avg(swstr_pct)      over w10                              as p_swstr_pct_roll10,
    avg(o_swing_pct)    over w10                              as p_o_swing_pct_roll10,
    avg(xwoba_against)  over w10                              as p_xwoba_against_roll10,
    avg(bf)             over w10                              as p_bf_roll10
from starts
window
    w5  as (partition by pitcher_id order by game_date, game_pk
            rows between 5 preceding and 1 preceding),
    w10 as (partition by pitcher_id order by game_date, game_pk
            rows between 10 preceding and 1 preceding)

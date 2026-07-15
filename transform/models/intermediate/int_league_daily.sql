-- Cumulative league hit-per-PA through each game date — the
-- empirical-Bayes prior mean, joined as-of (strictly before) each game
-- so the prior itself can't leak.
with daily as (
    select
        game_date,
        sum(hits) as hits,
        sum(pa)   as pa
    from {{ ref('fct_batter_game') }}
    group by 1
)

select
    game_date,
    sum(hits) over cum * 1.0 / nullif(sum(pa) over cum, 0) as league_hit_per_pa
from daily
window cum as (order by game_date rows between unbounded preceding and current row)

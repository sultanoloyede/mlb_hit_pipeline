-- THE leakage test. A batter's first career game has no prior data, so
-- every rolling/career feature must be null (or zero for counts and
-- streaks). If any window accidentally includes the current game —
-- e.g. a frame ending at CURRENT ROW instead of 1 PRECEDING — these
-- rows light up and the build fails.
with ordered as (
    select
        *,
        row_number() over (
            partition by batter_id order by game_date, game_pk
        ) as _rn
    from {{ ref('feat_batter_game') }}
)

select batter_id, game_pk, game_date
from ordered
where _rn = 1
  and (
       career_pa_prior != 0
    or career_games_prior != 0
    or season_pa_prior != 0
    or hit_streak_entering != 0
    or hitless_streak_entering != 0
    or has_hit_roll5 is not null
    or hit_per_pa_roll40 is not null
    or k_pct_roll10 is not null
    or hit_per_pa_platoon_roll20 is not null
  )

union all

-- rest days can be zero (doubleheaders) but never negative — negative
-- would mean the ordering or lag is broken
select batter_id, game_pk, game_date
from ordered
where days_rest < 0

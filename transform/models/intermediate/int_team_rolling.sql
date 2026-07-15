-- Team rolling form entering each game (current game excluded):
-- offense for the batter's own lineup context (#9), defense for the
-- as-of-date opponent pitching quality (#22/#23).
select
    game_pk,
    game_date,
    team_id,
    count(*)                                          over w15 as team_games_prior,
    avg(hits)                                         over w15 as team_hits_roll15,
    avg(runs)                                         over w15 as team_runs_roll15,
    avg(pa)                                           over w15 as team_pa_roll15,
    avg(hits_allowed * 1.0 / nullif(bf_against, 0))   over w15 as team_hits_allowed_per_bf_roll15,
    avg(xwoba_against)                                over w15 as team_xwoba_against_roll15,
    avg(strikeouts_thrown * 1.0 / nullif(bf_against, 0)) over w15 as team_k_pct_against_roll15
from {{ ref('fct_team_game') }}
window
    w15 as (partition by team_id order by game_date, game_pk
            rows between 15 preceding and 1 preceding)

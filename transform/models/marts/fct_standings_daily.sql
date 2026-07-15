-- League/division rank as-of each date. Join with standings_date =
-- game_date - 1 to get the rank a bettor knew entering that day.
select
    standings_date,
    team_id,
    team_name,
    league_id,
    division_id,
    league_rank,
    division_rank,
    wins,
    losses,
    win_pct
from {{ ref('stg_standings') }}

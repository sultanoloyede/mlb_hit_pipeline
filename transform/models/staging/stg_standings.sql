with ranked as (
    select
        *,
        row_number() over (
            partition by standings_date, team_id
            order by _dlt_load_id desc
        ) as _rn
    from {{ source('raw', 'standings') }}
)

select
    cast(standings_date as date)    as standings_date,
    team_id,
    team_name,
    division_id,
    league_id,
    cast(division_rank as integer)  as division_rank,
    cast(league_rank as integer)    as league_rank,
    wins,
    losses,
    cast(win_pct as double)         as win_pct
from ranked
where _rn = 1

-- Manager per team-season (research factor #16).
--
-- The coaches endpoint can list several managers for one team-season
-- (mid-season firings, interims) with no date ranges to split on, so
-- this is deliberately one row per (season, team): the listed manager,
-- deterministic pick. Fine for the research factor's granularity; a
-- per-game manager would need Retrosheet game logs.
with managers as (
    select
        season,
        team_id,
        team_name,
        person_id,
        person_name,
        row_number() over (
            partition by season, team_id
            order by person_id
        ) as _rn
    from {{ ref('stg_coaches') }}
    where job_id = 'MNGR' or lower(job) = 'manager'
)

select
    season,
    team_id,
    team_name,
    person_id   as manager_id,
    person_name as manager_name
from managers
where _rn = 1

with ranked as (
    select
        *,
        row_number() over (
            partition by season, team_id, person_id, job_id
            order by _dlt_load_id desc
        ) as _rn
    from {{ source('raw', 'coaches') }}
)

select
    cast(season as integer) as season,
    team_id,
    team_name,
    person_id,
    person_name,
    job,
    job_id
from ranked
where _rn = 1

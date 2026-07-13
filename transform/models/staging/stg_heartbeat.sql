select
    run_at,
    runner,
    git_sha
from {{ source('raw', 'heartbeat') }}

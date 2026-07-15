-- Team-game grain: offense from official batting lines, defense
-- (pitching) from statcast. Basis for team-average-hits (#9) and the
-- as-of-date best/worst pitching-team studies (#22/#23).
with offense as (
    select
        game_pk,
        official_date          as game_date,
        team_id,
        max(is_home::int) = 1  as is_home,
        sum(plate_appearances) as pa,
        sum(at_bats)           as ab,
        sum(hits)              as hits,
        sum(walks)             as walks,
        sum(strikeouts)        as strikeouts,
        sum(runs)              as runs,
        sum(home_runs)         as home_runs
    from {{ ref('stg_batting_lines') }}
    group by 1, 2, 3
),

defense as (
    select
        pitches.game_pk,
        -- 'Top' half = home team pitching
        case when pitches.inning_topbot = 'Top'
             then pitches.home_team else pitches.away_team end as team_code,
        count(*) filter (where pitches.is_pa_end)              as bf_against,
        count(*) filter (where pitches.is_hit)                 as hits_allowed,
        count(*) filter (where pitches.is_k)                   as strikeouts_thrown,
        count(*) filter (where pitches.is_bb)                  as walks_allowed,
        avg(pitches.xwoba) filter (where pitches.is_pa_end)    as xwoba_against
    from {{ ref('int_pitch_flags') }} pitches
    group by 1, 2
)

select
    offense.game_pk,
    offense.game_date,
    offense.team_id,
    teams.team_code,
    teams.team_name,
    offense.is_home,
    offense.pa,
    offense.ab,
    offense.hits,
    offense.walks,
    offense.strikeouts,
    offense.runs,
    offense.home_runs,
    defense.bf_against,
    defense.hits_allowed,
    defense.strikeouts_thrown,
    defense.walks_allowed,
    round(defense.xwoba_against, 4) as xwoba_against
from offense
left join {{ ref('dim_team') }} teams using (team_id)
left join defense
       on defense.game_pk = offense.game_pk
      and defense.team_code = teams.team_code

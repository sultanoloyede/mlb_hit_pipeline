-- The actual starting pitcher for each side of each game: the pitcher
-- who threw the game's first pitch of that half-inning side.
-- inning_topbot = 'Top' means the HOME side is pitching.
with first_pitch as (
    select
        game_pk,
        game_date,
        case when inning_topbot = 'Top' then 'home' else 'away' end as pitching_side,
        pitcher_id,
        p_throws,
        row_number() over (
            partition by game_pk, inning_topbot
            order by at_bat_number, pitch_number
        ) as _rn
    from {{ ref('stg_statcast_pitches') }}
)

select
    game_pk,
    game_date,
    pitching_side,
    pitcher_id as starter_id,
    p_throws   as starter_throws
from first_pitch
where _rn = 1

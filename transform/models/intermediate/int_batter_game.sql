-- Statcast-derived batter-game aggregates (overall). Mirrors the
-- prototype's aggregate_batters(): pa here counts pitches carrying an
-- event (including baserunning-ended PAs — a known prototype quirk kept
-- for parity); official PA/AB/H live in stg_batting_lines.
with pitches as (
    select * from {{ ref('int_pitch_flags') }}
),

pa_agg as (
    select
        game_pk, game_date, batter_id,
        count(*)                                as sc_pa,
        count(*) filter (where is_hit)          as sc_hits,
        count(*) filter (where is_ab)           as sc_ab,
        count(*) filter (where is_k)            as strikeouts,
        count(*) filter (where is_bb)           as walks,
        avg(xwoba)                              as xwoba_mean,
        avg(woba_value)                         as woba_mean
    from pitches
    where is_pa_end
    group by 1, 2, 3
),

pitch_agg as (
    select
        game_pk, game_date, batter_id,
        count(*)                                as total_pitches,
        count(*) filter (where is_swing)        as swings,
        count(*) filter (where is_contact)      as contacts,
        count(*) filter (where is_whiff)        as whiffs,
        count(*) filter (where is_out_zone)     as pitches_out_zone,
        count(*) filter (where is_chase)        as chases
    from pitches
    group by 1, 2, 3
),

bip_agg as (
    select
        game_pk, game_date, batter_id,
        count(*)                                as bip,
        count(*) filter (where is_hard_hit)     as hard_hits,
        count(*) filter (where is_barrel)       as barrels,
        count(*) filter (where is_sweet_spot)   as sweet_spots,
        count(*) filter (where is_line_drive)   as line_drives,
        avg(xba)                                as xba_mean,
        avg(xslg)                               as xslg_mean
    from pitches
    where is_bip
    group by 1, 2, 3
),

-- batter's team/side from the half-inning he bats in (a batter only
-- ever bats in one half, so max() just picks that value)
side_info as (
    select
        game_pk, batter_id,
        max(home_team)      as home_team,
        max(away_team)      as away_team,
        max(inning_topbot)  as topbot
    from pitches
    group by 1, 2
),

-- the pitcher hand this batter faced most (prototype: opp_p_throws)
opp_hand as (
    select game_pk, batter_id, p_throws as opp_p_throws
    from (
        select
            game_pk, batter_id, p_throws,
            row_number() over (
                partition by game_pk, batter_id
                order by count(*) desc, p_throws
            ) as _rn
        from pitches
        group by game_pk, batter_id, p_throws
    )
    where _rn = 1
)

select
    pa_agg.game_pk,
    pa_agg.game_date,
    pa_agg.batter_id,

    case when side_info.topbot = 'Top'
         then side_info.away_team else side_info.home_team end as team_code,
    case when side_info.topbot = 'Top'
         then side_info.home_team else side_info.away_team end as opponent_code,
    (side_info.topbot = 'Bot')                                 as sc_is_home,
    opp_hand.opp_p_throws,

    pa_agg.sc_pa,
    pa_agg.sc_hits,
    pa_agg.sc_ab,
    pa_agg.strikeouts,
    pa_agg.walks,
    coalesce(bip_agg.bip, 0)          as bip,
    coalesce(bip_agg.hard_hits, 0)    as hard_hits,
    coalesce(bip_agg.barrels, 0)      as barrels,

    round(pa_agg.strikeouts * 1.0 / pa_agg.sc_pa, 4)                          as k_pct,
    round(pa_agg.walks * 1.0 / pa_agg.sc_pa, 4)                               as bb_pct,
    round(bip_agg.hard_hits * 1.0 / nullif(bip_agg.bip, 0), 4)                as hard_hit_pct,
    round(bip_agg.barrels * 1.0 / nullif(bip_agg.bip, 0), 4)                  as barrel_pct,
    round(bip_agg.sweet_spots * 1.0 / nullif(bip_agg.bip, 0), 4)              as sweet_spot_pct,
    round(bip_agg.line_drives * 1.0 / nullif(bip_agg.bip, 0), 4)              as line_drive_pct,
    round(pitch_agg.contacts * 1.0 / nullif(pitch_agg.swings, 0), 4)          as contact_pct,
    round(pitch_agg.chases * 1.0 / nullif(pitch_agg.pitches_out_zone, 0), 4)  as chase_rate,

    round(bip_agg.xba_mean, 4)        as xba_mean,
    round(bip_agg.xslg_mean, 4)       as xslg_mean,
    round(pa_agg.xwoba_mean, 4)       as xwoba_mean,
    round(pa_agg.woba_mean, 4)        as woba_mean,
    round(pa_agg.sc_hits * 1.0 / nullif(pa_agg.sc_ab, 0), 4)                  as ba,
    round(bip_agg.xba_mean
          - pa_agg.sc_hits * 1.0 / nullif(pa_agg.sc_ab, 0), 4)                as xba_minus_ba

from pa_agg
left join pitch_agg using (game_pk, game_date, batter_id)
left join bip_agg   using (game_pk, game_date, batter_id)
left join side_info on side_info.game_pk = pa_agg.game_pk
                   and side_info.batter_id = pa_agg.batter_id
left join opp_hand  on opp_hand.game_pk = pa_agg.game_pk
                   and opp_hand.batter_id = pa_agg.batter_id

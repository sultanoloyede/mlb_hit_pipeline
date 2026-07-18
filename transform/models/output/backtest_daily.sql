-- Live predictions graded against outcomes. output.predictions is
-- written append-only by ml/predict.py (not dbt); until the first
-- prediction lands the table doesn't exist, so emit an empty typed
-- relation to keep builds green.
-- depends_on: {{ ref('fct_batter_game') }}
{% set predictions_relation = load_relation(source('output', 'predictions')) %}

{% if predictions_relation is none %}

select
    cast(null as timestamp) as run_ts,
    cast(null as date)      as slate_date,
    cast(null as bigint)    as game_pk,
    cast(null as bigint)    as batter_id,
    cast(null as varchar)   as player_name,
    cast(null as bigint)    as team_id,
    cast(null as bigint)    as opponent_team_id,
    cast(null as integer)   as batting_order_slot,
    cast(null as boolean)   as lineup_confirmed,
    cast(null as bigint)    as opp_starter_id,
    cast(null as double)    as p_hit,
    cast(null as varchar)   as model_version,
    cast(null as boolean)   as is_latest,
    cast(null as integer)   as has_hit,
    cast(null as bigint)    as hits,
    cast(null as bigint)    as pa,
    cast(null as boolean)   as graded
where false

{% else %}

select
    p.run_ts,
    p.slate_date,
    p.game_pk,
    p.batter_id,
    p.player_name,
    p.team_id,
    p.opponent_team_id,
    p.batting_order_slot,
    p.lineup_confirmed,
    p.opp_starter_id,
    p.p_hit,
    p.model_version,
    row_number() over (
        partition by p.slate_date, p.game_pk, p.batter_id
        order by p.run_ts desc
    ) = 1                     as is_latest,
    f.has_hit,
    f.hits,
    f.pa,
    f.has_hit is not null     as graded
from {{ source('output', 'predictions') }} p
left join {{ ref('fct_batter_game') }} f
       on f.game_pk = p.game_pk and f.batter_id = p.batter_id

{% endif %}

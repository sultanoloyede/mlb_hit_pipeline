"""MLB Stats API source (statsapi.mlb.com — official, free JSON API).

Feeds: schedule + probable pitchers, boxscore batting lines (the label
source), daily standings, today's posted lineups, coaching staff.

No cursors here: the daily run re-pulls a small sliding window (catches
reschedules and late finals) and dbt staging dedupes by keeping the
latest-loaded row per key. Backfills pass explicit date ranges.
"""

import time
from datetime import date, timedelta

import dlt
from dlt.sources.helpers import requests

API = "https://statsapi.mlb.com/api/v1"
SLEEP_SEC = 0.4          # polite pause between requests
SCHEDULE_CHUNK_DAYS = 30


def _get(path: str, **params):
    resp = requests.get(f"{API}/{path}", params=params)
    resp.raise_for_status()
    time.sleep(SLEEP_SEC)
    return resp.json()


def _date_chunks(start: date, end: date, days: int):
    cur = start
    while cur <= end:
        yield cur, min(cur + timedelta(days=days - 1), end)
        cur = cur + timedelta(days=days)


def _schedule_games(start: date, end: date):
    for chunk_start, chunk_end in _date_chunks(start, end, SCHEDULE_CHUNK_DAYS):
        data = _get(
            "schedule", sportId=1,
            startDate=chunk_start.isoformat(), endDate=chunk_end.isoformat(),
            hydrate="probablePitcher",
        )
        for day in data.get("dates", []):
            for game in day.get("games", []):
                yield game


def _side(game: dict, side: str) -> dict:
    team = game["teams"][side]
    probable = team.get("probablePitcher") or {}
    return {
        f"{side}_team_id": team["team"]["id"],
        f"{side}_team_name": team["team"]["name"],
        f"{side}_probable_pitcher_id": probable.get("id"),
        f"{side}_probable_pitcher_name": probable.get("fullName"),
    }


@dlt.resource(table_name="games", write_disposition="append")
def games(start: date, end: date):
    for g in _schedule_games(start, end):
        yield {
            "game_pk": g["gamePk"],
            "official_date": g["officialDate"],
            "season": g.get("season"),
            "game_type": g.get("gameType"),
            "status": g["status"]["detailedState"],
            "day_night": g.get("dayNight"),
            "doubleheader": g.get("doubleHeader"),
            "game_number": g.get("gameNumber"),
            "venue_id": (g.get("venue") or {}).get("id"),
            "venue_name": (g.get("venue") or {}).get("name"),
            **_side(g, "home"),
            **_side(g, "away"),
        }


@dlt.resource(table_name="batting_lines", write_disposition="append")
def batting_lines(start: date, end: date):
    """Official per-batter lines for FINAL games — hits/PA/AB (the label)
    plus batting order straight from the book (\"100\" = leadoff starter;
    a non-zero last digit marks a substitute)."""
    for g in _schedule_games(start, end):
        if g["status"]["detailedState"] != "Final":
            continue
        box = _get(f"game/{g['gamePk']}/boxscore")
        for side in ("home", "away"):
            team = box["teams"][side]
            for player in team["players"].values():
                batting = (player.get("stats") or {}).get("batting") or {}
                if not batting:
                    continue
                order = player.get("battingOrder")
                yield {
                    "game_pk": g["gamePk"],
                    "official_date": g["officialDate"],
                    "game_type": g.get("gameType"),
                    "team_id": team["team"]["id"],
                    "is_home": side == "home",
                    "player_id": player["person"]["id"],
                    "player_name": player["person"]["fullName"],
                    "position": (player.get("position") or {}).get("abbreviation"),
                    "batting_order": int(order) if order else None,
                    "is_substitute": bool(order) and int(order) % 100 != 0,
                    "plate_appearances": batting.get("plateAppearances"),
                    "at_bats": batting.get("atBats"),
                    "hits": batting.get("hits"),
                    "doubles": batting.get("doubles"),
                    "triples": batting.get("triples"),
                    "home_runs": batting.get("homeRuns"),
                    "walks": batting.get("baseOnBalls"),
                    "strikeouts": batting.get("strikeOuts"),
                    "runs": batting.get("runs"),
                    "rbi": batting.get("rbi"),
                }


@dlt.resource(table_name="standings", write_disposition="append")
def standings(start: date, end: date):
    """League/division rank as-of each date (both leagues per request).
    Powers the 'league rank at time' factor without end-of-season
    lookahead."""
    cur = start
    while cur <= end:
        data = _get("standings", leagueId="103,104",
                    season=cur.year, date=cur.isoformat())
        for record in data.get("records", []):
            for team in record.get("teamRecords", []):
                yield {
                    "standings_date": cur.isoformat(),
                    "team_id": team["team"]["id"],
                    "team_name": team["team"]["name"],
                    "division_id": (record.get("division") or {}).get("id"),
                    "league_id": (record.get("league") or {}).get("id"),
                    "division_rank": team.get("divisionRank"),
                    "league_rank": team.get("leagueRank"),
                    "wins": team.get("wins"),
                    "losses": team.get("losses"),
                    "win_pct": team.get("winningPercentage"),
                }
        cur = cur + timedelta(days=1)


@dlt.resource(table_name="lineups", write_disposition="append")
def lineups(for_date: date):
    """Batting orders posted for today's not-yet-final games. At the noon
    run many are absent — predict falls back to projected order and the
    lineup_confirmed flag records which was used."""
    for g in _schedule_games(for_date, for_date):
        if g["status"]["detailedState"] == "Final":
            continue
        box = _get(f"game/{g['gamePk']}/boxscore")
        for side in ("home", "away"):
            team = box["teams"][side]
            for player in team["players"].values():
                order = player.get("battingOrder")
                if not order:
                    continue
                yield {
                    "game_pk": g["gamePk"],
                    "official_date": g["officialDate"],
                    "team_id": team["team"]["id"],
                    "is_home": side == "home",
                    "player_id": player["person"]["id"],
                    "player_name": player["person"]["fullName"],
                    "batting_order": int(order),
                    "game_status": g["status"]["detailedState"],
                }


@dlt.resource(table_name="coaches", write_disposition="append")
def coaches(seasons: list[int]):
    for season in seasons:
        teams = _get("teams", sportId=1, season=season).get("teams", [])
        for team in teams:
            roster = _get(f"teams/{team['id']}/coaches", season=season)
            for coach in roster.get("roster", []):
                yield {
                    "season": season,
                    "team_id": team["id"],
                    "team_name": team["name"],
                    "person_id": coach["person"]["id"],
                    "person_name": coach["person"]["fullName"],
                    "job": coach.get("job"),
                    "job_id": coach.get("jobId"),
                }

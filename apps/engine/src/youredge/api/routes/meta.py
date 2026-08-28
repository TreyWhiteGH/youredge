"""Coverage endpoint — what the engine actually holds, counted live.

The web app renders this verbatim on its Data page. Hard-coding these numbers into the
UI would let them drift the moment an ingest runs; counting them means the page can only
ever claim what is really in the database.
"""

from fastapi import APIRouter
from sqlalchemy import text

from youredge.db import get_engine

router = APIRouter(tags=["meta"])

_COUNTS = text("""
    SELECT
      (SELECT count(*) FROM teams WHERE league = 'nfl')                        AS nfl_teams,
      (SELECT count(*) FROM teams WHERE league = 'ncaaf'
         AND classification = 'fbs')                                           AS ncaaf_fbs_teams,
      (SELECT count(*) FROM players WHERE league = 'nfl')                      AS nfl_players,
      (SELECT count(*) FROM players WHERE league = 'ncaaf')                    AS ncaaf_players,
      (SELECT count(*) FROM games)                                             AS games,
      (SELECT count(*) FROM plays WHERE game_id LIKE 'nfl:%')                  AS nfl_plays,
      (SELECT count(*) FROM plays WHERE game_id LIKE 'ncaaf:%')                AS ncaaf_plays,
      (SELECT count(*) FROM drives WHERE game_id LIKE 'nfl:%')                 AS nfl_drives,
      (SELECT count(*) FROM drives WHERE game_id LIKE 'ncaaf:%')               AS ncaaf_drives,
      (SELECT count(*) FROM play_players)                                      AS ncaaf_play_players,
      (SELECT count(DISTINCT game_id) FROM play_players)                       AS ncaaf_player_games,
      (SELECT count(*) FROM games WHERE weather_condition IS NOT NULL)          AS games_with_weather,
      (SELECT count(*) FROM player_game_stats)                                 AS player_game_stats,
      (SELECT count(*) FROM pff_player_stats)                                  AS pff_rows,
      (SELECT count(DISTINCT facet) FROM pff_player_stats)                     AS pff_facets,
      (SELECT count(*) FROM odds_snapshots)                                    AS odds_snapshots,
      (SELECT count(DISTINCT bookmaker) FROM markets)                          AS bookmakers,
      (SELECT count(*) FROM player_career_links)                               AS career_links,
      (SELECT count(*) FROM coaches)                                           AS coaches,
      (SELECT count(*) FROM transfers)                                         AS transfers,
      (SELECT count(*) FROM venues)                                            AS venues,
      (SELECT max(captured_at) FROM odds_snapshots)                            AS odds_last_captured
""")

# Phase state is asserted here rather than in the UI so one edit moves every surface that
# gates on it. `available: false` is what makes the app say "not yet" instead of inventing.
#
# `label` and `detail` are rendered verbatim to end users, so they describe what a surface
# measures without naming the licensed vendor behind it. The provenance itself is not
# hidden — it lives in the schema, the ingest modules, and CAPABILITIES.md, where whoever
# maintains this needs it. Note that omitting the name does not reduce licensing exposure;
# redistributing proprietary grades is what carries risk, labelled or not.
CAPABILITIES = [
    {"id": "team_cards", "label": "Team unit cards", "available": True,
     "detail": "Pass/run EPA, success, explosive, red zone, late & close — with league ranks."},
    {"id": "pff_units", "label": "Unit grades & pass protection", "available": True,
     "detail": "Snap-weighted 0-100 unit grades and per-lineman pressure allowed. NFL only."},
    {"id": "tendencies", "label": "Pass-rate tendencies", "available": True,
     "detail": "Team vs league by quarter and score state."},
    {"id": "absence", "label": "Player-absence impact", "available": True,
     "detail": "On/off splits, depth slot, next man up, starter-to-backup grade dropoff."},
    {"id": "clutch", "label": "QB clutch profile", "available": True,
     "detail": "Late & close, two-minute, clutch-drive rate. NFL quarterbacks."},
    {"id": "ncaaf_context", "label": "NCAAF coaching & roster context", "available": True,
     "detail": "Portable career residual, returning production, portal churn, SP+."},
    {"id": "odds", "label": "Market prices, de-vigged", "available": True,
     "detail": "Spreads, totals, moneylines with fair probability and line movement."},
    {"id": "ncaaf_play_players", "label": "NCAAF play-level player attribution",
     "available": True,
     "detail": "Per-play player events from CFBD /plays/stats, resolved to canonical "
               "ids. Upstream coverage is SEC and ACC only — about 29% of FBS games — "
               "so absence of a player on a play is not evidence he was not involved."},
    {"id": "weather", "label": "Game weather", "available": True,
     "detail": "NCAAF temp/wind/precipitation/condition from CFBD. NFL is temp and "
               "wind only, outdoor games. NULL means unavailable, never calm."},
    {"id": "drives", "label": "Drive outcomes, pace and fatigue", "available": True,
     "detail": "Possession-level outcomes by starting field position, both leagues. "
               "The surfaces a drive-level simulator is fit from."},
    {"id": "sim", "label": "Drive-level Monte Carlo simulator", "available": False,
     "detail": "Phase 1. Until it calibrates against closing lines there is no model "
               "probability, so nothing here quotes an edge."},
    {"id": "sgp", "label": "SGP pricing & correlation", "available": False,
     "detail": "Phase 2. Needs the simulator's joint distribution to price legs together."},
    {"id": "narrator", "label": "Bet Lab modes (LLM tool-use)", "available": False,
     "detail": "Phase 3. The engine computes every number; the narrator only selects "
               "and explains."},
]


@router.get("/coverage")
async def coverage():
    async with get_engine().connect() as conn:
        row = (await conn.execute(_COUNTS)).mappings().first()
    return {"counts": dict(row), "capabilities": CAPABILITIES}

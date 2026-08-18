"""QB clutch surface — performance when the game is on the line.

Three lenses, all computed from enriched PBP, always shown against the QB's own
baseline (clutch skill = doing it when it matters, measured as the delta):

  late_close       Q4/OT, one-score game (|diff| <= 8): EPA/dropback, success
                   rate, completion rate, total WPA
  two_minute       final 2:00 of either half: EPA/play, success rate, completion
                   rate on dropbacks
  clutch_drives    drives the QB dropped back on, touching Q4/OT one-score with
                   under 5:00 left: share ending in TD or made FG

A dropback belongs to the QB when they passed/were sacked (passer_player_id) or
scrambled (rusher on a qb_scramble). Offensive-TD detection excludes pick-sixes;
rare fumble-return TDs slip through until a drive-outcome column exists.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MIN_DROPBACKS = 25  # below this, clutch splits are noise; caller shows sample size

_QB_PLAYS = """
    SELECT p.*,
           (p.quarter >= 4 AND abs(p.score_differential) <= 8)          AS is_late_close,
           ((p.quarter = 2 AND p.game_seconds_remaining BETWEEN 1800 AND 1920)
            OR (p.quarter >= 4 AND p.game_seconds_remaining <= 120))    AS is_two_minute
    FROM plays p
    JOIN games g ON g.game_id = p.game_id
    WHERE g.league = 'nfl' AND g.season = ANY(:seasons)
      AND p.qb_dropback
      AND (p.passer_player_id = :gsis OR (p.qb_scramble AND p.rusher_player_id = :gsis))
"""

_SPLITS = text(f"""
    WITH qb AS ({_QB_PLAYS})
    SELECT
      count(*)                                            AS dropbacks,
      avg(epa)                                            AS epa_per_db,
      avg(success::int)                                   AS success_rate,
      avg(complete_pass::int) FILTER (WHERE play_type = 'pass') AS comp_rate,
      count(*)                FILTER (WHERE is_late_close)            AS lc_dropbacks,
      avg(epa)                FILTER (WHERE is_late_close)            AS lc_epa_per_db,
      avg(success::int)       FILTER (WHERE is_late_close)            AS lc_success_rate,
      avg(complete_pass::int) FILTER (WHERE is_late_close AND play_type = 'pass') AS lc_comp_rate,
      sum(wpa)                FILTER (WHERE is_late_close)            AS lc_wpa_total,
      count(*)                FILTER (WHERE is_two_minute)            AS tm_plays,
      avg(epa)                FILTER (WHERE is_two_minute)            AS tm_epa_per_play,
      avg(success::int)       FILTER (WHERE is_two_minute)            AS tm_success_rate,
      avg(complete_pass::int) FILTER (WHERE is_two_minute AND play_type = 'pass') AS tm_comp_rate
    FROM qb
""")

# A clutch drive: any of its plays hit Q4/OT, one-score, <5:00; the QB dropped
# back on it; success = offensive TD (non-INT) or made FG anywhere on the drive.
_CLUTCH_DRIVES = text("""
    WITH drives AS (
        SELECT p.game_id, p.drive_num,
               bool_or(p.quarter >= 4 AND abs(p.score_differential) <= 8
                       AND p.game_seconds_remaining <= 300)             AS is_clutch,
               bool_or(p.qb_dropback AND (p.passer_player_id = :gsis
                       OR (p.qb_scramble AND p.rusher_player_id = :gsis))) AS qb_on_drive,
               bool_or((p.touchdown AND p.interception IS NOT TRUE)
                       OR p.field_goal_result = 'made')                 AS scored
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE g.league = 'nfl' AND g.season = ANY(:seasons) AND p.drive_num IS NOT NULL
        GROUP BY p.game_id, p.drive_num
    )
    SELECT count(*) AS clutch_drives,
           count(*) FILTER (WHERE scored) AS scoring_drives
    FROM drives WHERE is_clutch AND qb_on_drive
""")

# League baseline over the same seasons for context (QBs with enough volume).
_LEAGUE = text("""
    WITH db AS (
        SELECT p.passer_player_id AS gsis, p.epa,
               (p.quarter >= 4 AND abs(p.score_differential) <= 8) AS is_late_close
        FROM plays p JOIN games g ON g.game_id = p.game_id
        WHERE g.league = 'nfl' AND g.season = ANY(:seasons)
          AND p.qb_dropback AND p.passer_player_id IS NOT NULL
    )
    SELECT avg(epa) FILTER (WHERE is_late_close) AS lc_epa_per_db,
           avg(epa) AS epa_per_db
    FROM db
""")


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None


async def qb_clutch(conn: AsyncConnection, player_id: str, seasons: list[int]) -> dict[str, Any]:
    gsis = player_id.split(":", 1)[1]
    params = {"gsis": gsis, "seasons": seasons}

    s = (await conn.execute(_SPLITS, params)).mappings().one()
    d = (await conn.execute(_CLUTCH_DRIVES, params)).mappings().one()
    lg = (await conn.execute(_LEAGUE, {"seasons": seasons})).mappings().one()

    small_sample = (s["lc_dropbacks"] or 0) < MIN_DROPBACKS
    return {
        "seasons": seasons,
        "baseline": {
            "dropbacks": s["dropbacks"],
            "epa_per_dropback": _r(s["epa_per_db"]),
            "success_rate": _r(s["success_rate"]),
            "comp_rate": _r(s["comp_rate"]),
        },
        "late_close": {
            "dropbacks": s["lc_dropbacks"],
            "epa_per_dropback": _r(s["lc_epa_per_db"]),
            "success_rate": _r(s["lc_success_rate"]),
            "comp_rate": _r(s["lc_comp_rate"]),
            "wpa_total": _r(s["lc_wpa_total"]),
            "delta_vs_own_baseline": _r((s["lc_epa_per_db"] or 0) - (s["epa_per_db"] or 0))
                if s["lc_epa_per_db"] is not None else None,
            "league_epa_per_dropback": _r(lg["lc_epa_per_db"]),
            "small_sample": small_sample,
        },
        "two_minute": {
            "plays": s["tm_plays"],
            "epa_per_play": _r(s["tm_epa_per_play"]),
            "success_rate": _r(s["tm_success_rate"]),
            "comp_rate": _r(s["tm_comp_rate"]),
        },
        "clutch_drives": {
            "drives": d["clutch_drives"],
            "scoring_drives": d["scoring_drives"],
            "score_rate": _r(d["scoring_drives"] / d["clutch_drives"])
                if d["clutch_drives"] else None,
        },
    }

"""Pass rate by score state × quarter — the first tendency surface.

Answers: "when this team is down two scores in Q4, how pass-heavy do they get,
and is that more or less than the league?" Feeds script tags like
GARBAGE_TIME_PASS and CLOCK_KILL.

Scramble caveat: nflverse play_type marks scrambles as 'run', so pass rate here
is called-run vs called-pass-or-sack; dropback rate needs the qb_dropback
column (not yet extracted).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# Ordered pre-snap score states from the offense's perspective.
SCORE_STATES = ["trail_big", "trail_1sc", "tied", "lead_1sc", "lead_big"]

_QUERY = text("""
    WITH base AS (
        SELECT p.posteam_id,
               p.quarter,
               CASE
                   WHEN p.score_differential <= -9 THEN 'trail_big'
                   WHEN p.score_differential < 0   THEN 'trail_1sc'
                   WHEN p.score_differential = 0   THEN 'tied'
                   WHEN p.score_differential <= 8  THEN 'lead_1sc'
                   ELSE 'lead_big'
               END AS score_state,
               (p.play_type = 'pass')::int AS is_pass
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE p.play_type IN ('pass', 'run')
          AND p.down IS NOT NULL
          AND p.quarter BETWEEN 1 AND 4
          AND p.score_differential IS NOT NULL
          AND g.league = :league
          AND g.season = ANY(:seasons)
    )
    SELECT quarter,
           score_state,
           COUNT(*) FILTER (WHERE posteam_id = :team_id)      AS team_plays,
           SUM(is_pass) FILTER (WHERE posteam_id = :team_id)  AS team_passes,
           COUNT(*)                                           AS league_plays,
           SUM(is_pass)                                       AS league_passes
    FROM base
    GROUP BY quarter, score_state
""")


async def pass_rate_by_score_state(
    conn: AsyncConnection, team_id: str, seasons: list[int]
) -> list[dict[str, Any]]:
    """Team vs league pass rate for every (quarter, score_state) cell.

    team_id is canonical ('nfl:BAL'); league is derived from its prefix.
    delta_vs_league is None for cells where the team had no snaps.
    """
    league = team_id.split(":", 1)[0]
    result = await conn.execute(
        _QUERY, {"team_id": team_id, "league": league, "seasons": seasons}
    )
    cells = []
    for row in result.mappings():
        team_rate = (
            row["team_passes"] / row["team_plays"] if row["team_plays"] else None
        )
        league_rate = row["league_passes"] / row["league_plays"]
        cells.append({
            "quarter": row["quarter"],
            "score_state": row["score_state"],
            "team_plays": row["team_plays"],
            "team_pass_rate": round(team_rate, 4) if team_rate is not None else None,
            "league_pass_rate": round(league_rate, 4),
            "delta_vs_league": round(team_rate - league_rate, 4) if team_rate is not None else None,
        })
    cells.sort(key=lambda c: (c["quarter"], SCORE_STATES.index(c["score_state"])))
    return cells

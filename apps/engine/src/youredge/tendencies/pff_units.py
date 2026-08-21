"""Team unit quality from PFF player grades — the layer free data can't reach.

Rolls per-player PFF grades into snap-weighted unit grades with league ranks.
Pass protection is the headline: nflverse has no lineman data at all, so
"this OL grades 31st in pass blocking" is only sayable with PFF.

Units are (facet, positions) pairs because PFF facets mix positions: the
pass_blocking facet includes backs and tight ends who chip, so an OL unit
grade must filter to linemen or it measures the wrong thing.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

OL = ("T", "G", "C", "LT", "RT", "LG", "RG")
DL = ("DI", "ED", "DT", "DE")
COV = ("CB", "S", "LB", "SS", "FS")

UNITS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "blocking":       ("blocking", OL),
    "pass_blocking":  ("pass_blocking", OL),
    "run_blocking":   ("run_blocking", OL),
    "pass_rush":      ("pass_rush", DL),
    "run_defense":    ("run_defense", None),
    "coverage":       ("coverage", COV),
    "receiving":      ("receiving", ("WR", "TE")),
    "rushing":        ("rushing", ("HB", "RB", "FB")),
}

MIN_SNAPS = 100

# Snap-weighted so a backup's 40 bad snaps don't outweigh a starter's 900.
_UNIT = text("""
    WITH rows AS (
        SELECT team_id, grade, snaps
        FROM pff_player_stats
        WHERE facet = :facet AND season = :season AND week = 0
          AND grade IS NOT NULL AND snaps >= :min_snaps AND team_id IS NOT NULL
          AND (CAST(:positions AS text[]) IS NULL
               OR stats->>'position' = ANY(CAST(:positions AS text[])))
    ),
    per_team AS (
        SELECT team_id,
               sum(grade * snaps) / nullif(sum(snaps), 0) AS unit_grade,
               sum(snaps) AS snaps,
               count(*) AS players
        FROM rows GROUP BY team_id
    )
    SELECT *, rank() OVER (ORDER BY unit_grade DESC) AS rank,
           count(*) OVER () AS teams_ranked
    FROM per_team
""")


async def team_units(conn: AsyncConnection, team_id: str, season: int) -> dict[str, Any]:
    """Every available unit grade for one team, with league rank."""
    out: dict[str, Any] = {}
    for unit, (facet, positions) in UNITS.items():
        rows = (await conn.execute(_UNIT, {
            "facet": facet, "season": season, "min_snaps": MIN_SNAPS,
            "positions": list(positions) if positions else None,
        })).mappings().all()
        mine = next((r for r in rows if r["team_id"] == team_id), None)
        if mine is None:
            continue
        league_avg = sum(r["unit_grade"] for r in rows) / len(rows)
        out[unit] = {
            "grade": round(float(mine["unit_grade"]), 1),
            "league_avg": round(league_avg, 1),
            "rank": mine["rank"],
            "teams_ranked": mine["teams_ranked"],
            "players": mine["players"],
            "snaps": mine["snaps"],
        }
    return out

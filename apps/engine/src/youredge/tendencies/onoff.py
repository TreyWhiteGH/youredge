"""Player on/off splits, side-aware: what the unit does with vs without them.

side='defense': games gated on defense_pct, plays where their team defends.
side='offense': games gated on offense_pct, plays where their team has the ball.
Correlational either way — deltas ship with sample sizes.
"""

from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ON_SNAP_PCT = 0.20

_ONOFF_TMPL = """
    WITH played AS (
        SELECT game_id, team_id FROM snap_counts
        WHERE player_id = :pid AND {pct_col} >= :thresh
    ),
    team_games AS (
        SELECT g.game_id, tg.team_id
        FROM games g
        JOIN (SELECT DISTINCT team_id FROM played) tg
          ON g.home_team_id = tg.team_id OR g.away_team_id = tg.team_id
        WHERE g.league = 'nfl' AND g.season = ANY(:seasons) AND g.status = 'final'
    ),
    labeled AS (
        SELECT t.game_id, t.team_id, (p.game_id IS NOT NULL) AS is_on
        FROM team_games t LEFT JOIN played p ON p.game_id = t.game_id
    )
    SELECT l.is_on,
        count(DISTINCT l.game_id)                              AS games,
        avg(p.epa) FILTER (WHERE p.qb_dropback)                AS pass_epa,
        avg(p.success::int) FILTER (WHERE p.qb_dropback)       AS pass_success,
        avg(p.epa) FILTER (WHERE p.play_type = 'run')          AS rush_epa,
        avg(p.success::int) FILTER (WHERE p.play_type = 'run') AS rush_success,
        avg((p.yards_gained >= 15)::int)
            FILTER (WHERE p.play_type = 'pass' AND p.complete_pass) AS explosive_pass
    FROM labeled l
    JOIN plays p ON p.game_id = l.game_id AND p.{team_col} = l.team_id
    WHERE p.play_type IN ('pass', 'run') AND p.down IS NOT NULL
    GROUP BY l.is_on
"""

_QUERIES = {
    "defense": text(_ONOFF_TMPL.format(pct_col="defense_pct", team_col="defteam_id")),
    "offense": text(_ONOFF_TMPL.format(pct_col="offense_pct", team_col="posteam_id")),
}


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None


async def player_onoff(
    conn: AsyncConnection,
    player_id: str,
    seasons: list[int],
    side: Literal["offense", "defense"],
) -> dict[str, Any]:
    rows = {r["is_on"]: r for r in
            (await conn.execute(_QUERIES[side], {
                "pid": player_id, "seasons": seasons, "thresh": ON_SNAP_PCT,
            })).mappings().all()}
    on, off = rows.get(True), rows.get(False)
    suffix = "allowed" if side == "defense" else "generated"

    def block(r):
        if r is None:
            return None
        return {
            "games": r["games"],
            f"pass_epa_{suffix}": _r(r["pass_epa"]),
            f"pass_success_{suffix}": _r(r["pass_success"]),
            f"rush_epa_{suffix}": _r(r["rush_epa"]),
            f"rush_success_{suffix}": _r(r["rush_success"]),
            f"explosive_pass_{suffix}": _r(r["explosive_pass"]),
        }

    out = {"player_id": player_id, "seasons": seasons, "side": side,
           "on": block(on), "off": block(off), "delta_when_out": None}
    if on and off:
        pass_d = off["pass_epa"] - on["pass_epa"]
        rush_d = off["rush_epa"] - on["rush_epa"]
        worse = "positive = defense worse without them" if side == "defense" \
            else "negative = offense worse without them"
        out["delta_when_out"] = {
            f"pass_epa_{suffix}": _r(pass_d),
            f"rush_epa_{suffix}": _r(rush_d),
            "note": f"{worse}; correlational, mind the sample sizes",
        }
    return out

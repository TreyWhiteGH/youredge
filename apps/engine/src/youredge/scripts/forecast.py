"""What shape is this game likely to take, and what does each side tend to do.

The Game Tag Surface: for an upcoming game, the script probabilities and each
team's diagnostic tendencies, with the sample behind every number.

Computed on request rather than stored. `taggings` holds what *happened* — a
finished game's label carries weight 1.0 because it is a fact — and writing
forecasts into the same rows would make the table mean two different things
depending on a game's status. The realized labels are also what these forecasts
are counted from, so keeping them separate keeps the input clean.

No simulator. Script probabilities are empirical base rates conditioned on the
closing line, which is available today and is a genuine forecast: BLOWOUT_FAV
runs 12% of games at a pick-em and 40% at a two-touchdown spread. When the
simulator lands it replaces these numbers against the same vocabulary, and the
gap between the two is gate G4.

Backoff is explicit. A cell needs MIN_CELL games or the estimate falls back to a
coarser conditioning, and the level actually used is returned as `basis` so a
number conditioned on nothing is never mistaken for one that was.
"""

import logging
from typing import Any

from sqlalchemy import text

log = logging.getLogger(__name__)

MIN_CELL = 60
# How many of a team's most recent games a tendency is read from. Short enough to
# describe this team, long enough that one game does not define it.
FORM_GAMES = 20

_SPREAD_BUCKET = """
    CASE WHEN abs(gf.closing_spread) <= 3 THEN 'pickem'
         WHEN abs(gf.closing_spread) <= 7 THEN 'short'
         WHEN abs(gf.closing_spread) <= 14 THEN 'mid'
         ELSE 'big' END
"""
_TOTAL_BUCKET = """
    CASE WHEN gf.closing_total <= 41 THEN 'low'
         WHEN gf.closing_total <= 46 THEN 'mid'
         WHEN gf.closing_total <= 51 THEN 'high'
         ELSE 'vhigh' END
"""

# Three estimates per tag, coarsest last. The first with enough games wins.
_SCRIPT_RATES = text(f"""
    WITH labelled AS (
        SELECT g.game_id, g.league, {_SPREAD_BUCKET} AS sp, {_TOTAL_BUCKET} AS tot,
               t.slug
        FROM games g
        JOIN game_features gf ON gf.game_id = g.game_id
        JOIN game_state gs ON gs.game_id = g.game_id
        LEFT JOIN taggings tg ON tg.entity_type = 'game' AND tg.entity_id = g.game_id
        LEFT JOIN tags t ON t.tag_id = tg.tag_id AND t.dimension = 'script'
        WHERE g.league = :league AND gf.closing_spread IS NOT NULL
          AND gf.closing_total IS NOT NULL
    ),
    games_in AS (
        SELECT DISTINCT game_id, sp, tot FROM labelled
    ),
    tags_all AS (SELECT slug FROM tags WHERE dimension = 'script' AND status = 'active')
    SELECT ta.slug,
           -- both dimensions
           count(*) FILTER (WHERE gi.sp = :sp AND gi.tot = :tot) AS n_both,
           count(*) FILTER (WHERE gi.sp = :sp AND gi.tot = :tot
                              AND l.slug IS NOT NULL) AS hit_both,
           -- spread only
           count(*) FILTER (WHERE gi.sp = :sp) AS n_sp,
           count(*) FILTER (WHERE gi.sp = :sp AND l.slug IS NOT NULL) AS hit_sp,
           -- total only
           count(*) FILTER (WHERE gi.tot = :tot) AS n_tot,
           count(*) FILTER (WHERE gi.tot = :tot AND l.slug IS NOT NULL) AS hit_tot,
           -- league base rate
           count(*) AS n_all,
           count(*) FILTER (WHERE l.slug IS NOT NULL) AS hit_all
    FROM tags_all ta
    CROSS JOIN games_in gi
    LEFT JOIN labelled l ON l.game_id = gi.game_id AND l.slug = ta.slug
    GROUP BY ta.slug
""")

_TEAM_TENDENCIES = text(f"""
    WITH recent AS (
        SELECT d.game_id, d.team_id, g.kickoff,
               row_number() OVER (PARTITION BY d.team_id ORDER BY g.kickoff DESC) AS rn
        FROM team_game_diagnostics d
        JOIN games g ON g.game_id = d.game_id
        WHERE d.team_id = :team AND g.status = 'final'
    ),
    window_games AS (SELECT * FROM recent WHERE rn <= {FORM_GAMES})
    SELECT t.slug, count(*) FILTER (WHERE tg.tag_id IS NOT NULL) AS n_hit,
           (SELECT count(*) FROM window_games) AS n_games
    FROM (SELECT tag_id, slug FROM tags WHERE dimension = 'diagnostic') t
    CROSS JOIN window_games w
    LEFT JOIN taggings tg ON tg.entity_type = 'team_game'
                         AND tg.entity_id = w.game_id || '|' || w.team_id
                         AND tg.tag_id = t.tag_id
    GROUP BY t.slug
    ORDER BY 2 DESC
""")


def _pick(row) -> tuple[float, int, str]:
    """First conditioning level with enough games behind it."""
    for n, hit, basis in (
        (row["n_both"], row["hit_both"], "spread+total"),
        (row["n_sp"], row["hit_sp"], "spread"),
        (row["n_tot"], row["hit_tot"], "total"),
        (row["n_all"], row["hit_all"], "league"),
    ):
        if n >= MIN_CELL:
            return hit / n, n, basis
    return (row["hit_all"] / row["n_all"] if row["n_all"] else 0.0,
            row["n_all"], "league")


async def game_surface(conn, game_id: str) -> dict[str, Any]:
    g = (await conn.execute(text("""
        SELECT g.game_id, g.league, g.status, g.home_team_id, g.away_team_id,
               ht.name AS home_name, at.name AS away_name,
               gf.closing_spread, gf.closing_total
        FROM games g
        JOIN teams ht ON ht.team_id = g.home_team_id
        JOIN teams at ON at.team_id = g.away_team_id
        LEFT JOIN game_features gf ON gf.game_id = g.game_id
        WHERE g.game_id = :gid
    """), {"gid": game_id})).mappings().first()
    if not g:
        return {}

    spread, total = g["closing_spread"], g["closing_total"]
    line_source = "closing"
    if spread is None or total is None:
        # game_features carries closing lines for finished games only. An
        # upcoming game has no closing line yet — it has a market, which is the
        # right input anyway: the forecast should move as the line moves.
        live = (await conn.execute(text("""
            SELECT
              (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
                WHERE m.game_id = :gid AND m.market_key = 'spreads'
                  AND s.outcome = :home ORDER BY s.captured_at DESC LIMIT 1) AS spread,
              (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
                WHERE m.game_id = :gid AND m.market_key = 'totals'
                  AND s.outcome ILIKE 'over' ORDER BY s.captured_at DESC LIMIT 1) AS total
        """), {"gid": game_id, "home": g["home_name"]})).mappings().first()
        if live:
            spread = spread if spread is not None else live["spread"]
            total = total if total is not None else live["total"]
            line_source = "live market"
    scripts: list[dict] = []
    if spread is not None and total is not None:
        sp = ("pickem" if abs(spread) <= 3 else "short" if abs(spread) <= 7
              else "mid" if abs(spread) <= 14 else "big")
        tot = ("low" if total <= 41 else "mid" if total <= 46
               else "high" if total <= 51 else "vhigh")
        rows = (await conn.execute(_SCRIPT_RATES, {
            "league": g["league"], "sp": sp, "tot": tot})).mappings().all()
        for r in rows:
            p, n, basis = _pick(r)
            base = r["hit_all"] / r["n_all"] if r["n_all"] else 0.0
            scripts.append({
                "script": r["slug"], "probability": round(p, 3), "n": n,
                "basis": basis, "league_base_rate": round(base, 3),
                # Whether conditioning on the line actually told us anything, or
                # this is the league average wearing a game's name.
                "lift_vs_base": round(p / base, 2) if base else None,
            })
        scripts.sort(key=lambda s: -s["probability"])

    teams = []
    for side in ("home", "away"):
        rows = (await conn.execute(
            _TEAM_TENDENCIES, {"team": g[f"{side}_team_id"]})).mappings().all()
        n_games = rows[0]["n_games"] if rows else 0
        teams.append({
            "side": side, "team_id": g[f"{side}_team_id"], "name": g[f"{side}_name"],
            "games": n_games,
            "tendencies": [
                {"diagnostic": r["slug"], "rate": round(r["n_hit"] / n_games, 3),
                 "n": r["n_hit"], "of": n_games}
                for r in rows if n_games and r["n_hit"]
            ][:8],
        })

    return {
        "game_id": g["game_id"], "league": g["league"], "status": g["status"],
        "spread": spread, "total": total, "line_source": line_source,
        "scripts": scripts, "teams": teams,
        "basis_note": (
            "Script probabilities are empirical base rates for games with this "
            "closing line, not simulator output. `basis` says what each was "
            "conditioned on; 'league' means the line told us nothing and this is "
            "the league average. Team tendencies are that team's last "
            f"{FORM_GAMES} games."
        ),
    }

"""College player game logs from CFBD /games/players.

The production history props get priced against. CFBD nests this four levels deep -
game -> teams -> categories (passing/rushing/receiving/defensive/...) -> types
(YDS, TD, C/ATT, ...) -> athletes - so the work here is flattening that into the same
player_game_stats rows the NFL side already uses.

Only the shared typed columns are promoted; everything else (defensive box score,
kicking, returns, QBR, long gains) lands in stats JSONB keyed 'category.TYPE', so
nothing CFBD reports is lost even though it has no typed home.

Columns the NFL has and college does not: target_share, air_yards_share, wopr,
passing_epa/cpoe. CFBD does not report targets or air yards at all, so those stay
NULL rather than being derived from something that isn't the same measurement.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.cfbd_player_stats --seasons 2024
"""

import argparse
import asyncio
import json
import logging

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

# (category, CFBD type) -> typed column. C/ATT is split into two below.
TYPED = {
    ("passing", "YDS"): "passing_yards",
    ("passing", "TD"): "passing_tds",
    ("passing", "INT"): "passing_interceptions",
    ("rushing", "CAR"): "carries",
    ("rushing", "YDS"): "rushing_yards",
    ("rushing", "TD"): "rushing_tds",
    ("receiving", "REC"): "receptions",
    ("receiving", "YDS"): "receiving_yards",
    ("receiving", "TD"): "receiving_tds",
}
INT_COLS = {"passing_tds", "passing_interceptions", "carries", "rushing_tds",
            "receptions", "receiving_tds", "attempts", "completions"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


def _num(v):
    """CFBD stats arrive as strings and include '--' for absent."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "--", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def flatten(games: list[dict]) -> dict[tuple, dict]:
    """Nested payload -> {(espn_player_id, cfbd_game_id): row}."""
    out: dict[tuple, dict] = {}
    for g in games:
        gid = g.get("id")
        teams = g.get("teams") or []
        names = [t.get("team") for t in teams]
        for t in teams:
            opp = next((n for n in names if n != t.get("team")), None)
            for cat in t.get("categories") or []:
                cname = cat.get("name")
                for ty in cat.get("types") or []:
                    tname = ty.get("name")
                    for ath in ty.get("athletes") or []:
                        aid = ath.get("id")
                        if not aid:
                            continue
                        key = (str(aid), gid)
                        row = out.setdefault(key, {
                            "name": ath.get("name"), "team": t.get("team"),
                            "opponent": opp, "stats": {},
                        })
                        row["stats"][f"{cname}.{tname}"] = ath.get("stat")
    return out


async def ingest_week(season: int, week: int, season_type: str = "regular") -> dict:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=180) as client:
        games = await _get(client, "/games/players", {
            "year": season, "week": week, "seasonType": season_type,
            "classification": "fbs"})
    rows = flatten(games)
    if not rows:
        return {"games": 0, "rows": 0, "inserted": 0, "unresolved": 0}

    engine = get_engine()
    inserted = unresolved = 0
    async with engine.begin() as conn:
        known = {r[0] for r in await conn.execute(text(
            "SELECT player_id FROM players WHERE league='ncaaf'"))}
        teams = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT x.source_id, x.canonical_id FROM entity_xwalk x "
            "JOIN teams t ON t.team_id = x.canonical_id "
            "WHERE x.entity_type='team' AND x.source='cfbd_alias'"))}
        from youredge.ingest.resolve import normalize_name

        for (aid, gid), r in rows.items():
            pid = f"ncaaf:{aid}"
            if pid not in known:
                unresolved += 1
                continue
            s = r["stats"]
            vals: dict[str, float | None] = {}
            for (cat, ty), col in TYPED.items():
                v = _num(s.get(f"{cat}.{ty}"))
                if v is not None:
                    vals[col] = v
            # C/ATT is one CFBD field holding two numbers
            catt = s.get("passing.C/ATT")
            if catt and "/" in str(catt):
                c, a = str(catt).split("/", 1)
                vals["completions"], vals["attempts"] = _num(c), _num(a)

            await conn.execute(
                text("""
                    INSERT INTO player_game_stats
                        (player_id, season, week, season_type, game_id, team_id,
                         opponent_team_id, attempts, completions, passing_yards,
                         passing_tds, passing_interceptions, carries, rushing_yards,
                         rushing_tds, receptions, receiving_yards, receiving_tds, stats)
                    VALUES (:pid, :season, :week, :stype, :gid, :team, :opp,
                            :attempts, :completions, :passing_yards, :passing_tds,
                            :passing_interceptions, :carries, :rushing_yards,
                            :rushing_tds, :receptions, :receiving_yards,
                            :receiving_tds, CAST(:stats AS jsonb))
                    ON CONFLICT (player_id, season, week) DO UPDATE SET
                        season_type=EXCLUDED.season_type, game_id=EXCLUDED.game_id,
                        team_id=EXCLUDED.team_id, opponent_team_id=EXCLUDED.opponent_team_id,
                        attempts=EXCLUDED.attempts, completions=EXCLUDED.completions,
                        passing_yards=EXCLUDED.passing_yards, passing_tds=EXCLUDED.passing_tds,
                        passing_interceptions=EXCLUDED.passing_interceptions,
                        carries=EXCLUDED.carries, rushing_yards=EXCLUDED.rushing_yards,
                        rushing_tds=EXCLUDED.rushing_tds, receptions=EXCLUDED.receptions,
                        receiving_yards=EXCLUDED.receiving_yards,
                        receiving_tds=EXCLUDED.receiving_tds, stats=EXCLUDED.stats
                """),
                {
                    "pid": pid, "season": season, "week": week,
                    "stype": season_type, "gid": f"ncaaf:{gid}",
                    "team": teams.get(normalize_name(r["team"] or "")),
                    "opp": teams.get(normalize_name(r["opponent"] or "")),
                    **{c: (int(v) if c in INT_COLS and (v := vals.get(c)) is not None
                           else vals.get(c)) for c in
                       ("attempts", "completions", "passing_yards", "passing_tds",
                        "passing_interceptions", "carries", "rushing_yards",
                        "rushing_tds", "receptions", "receiving_yards", "receiving_tds")},
                    "stats": json.dumps(s),
                },
            )
            inserted += 1
    return {"games": len(games), "rows": len(rows), "inserted": inserted,
            "unresolved": unresolved}


async def main(seasons: list[int], weeks: list[int], season_types: list[str]):
    for season in seasons:
        for st in season_types:
            wk_list = [1] if st == "postseason" else weeks
            for w in wk_list:
                try:
                    stats = await ingest_week(season, w, st)
                    if stats["rows"]:
                        log.info("%s %s wk%s: %s", season, st, w, stats)
                except httpx.HTTPStatusError as e:
                    log.error("%s %s wk%s failed: %s", season, st, w, e)
                await asyncio.sleep(1.5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--weeks", nargs="+", type=int, default=list(range(1, 16)))
    parser.add_argument("--season-types", nargs="+", default=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.weeks, args.season_types))

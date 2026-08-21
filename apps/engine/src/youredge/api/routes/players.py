"""Player inspection endpoints — bio, game log, play log, QB traits & clutch.

GET /players?q=mahomes                 name search (alias-normalized)
GET /players/{player_id}               bio + season aggregates (+ NGS if QB)
GET /players/{player_id}/gamelog       weekly rows from player_game_stats
GET /players/{player_id}/plays         enriched PBP involving the player
GET /players/{player_id}/clutch        QB clutch surface (late&close, 2-min, drives)
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name
from youredge.pff_splits import compare
from youredge.tendencies.qb_clutch import qb_clutch

router = APIRouter(tags=["players"])

DEFAULT_SEASONS = [2023, 2024, 2025]


async def _player_or_404(conn, player_id: str) -> dict:
    row = (await conn.execute(
        text("""
            SELECT p.player_id, p.name, p.position, p.team_id, t.name AS team_name
            FROM players p LEFT JOIN teams t ON t.team_id = p.team_id
            WHERE p.player_id = :pid
        """),
        {"pid": player_id},
    )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown player_id {player_id}")
    return dict(row)


@router.get("/players")
async def search_players(q: str = Query(min_length=2), limit: int = 10):
    norm = normalize_name(q)
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT DISTINCT p.player_id, p.name, p.position, p.team_id
                FROM players p
                LEFT JOIN entity_xwalk x ON x.entity_type = 'player'
                     AND x.source = 'nflverse_alias' AND x.canonical_id = p.player_id
                WHERE p.name ILIKE '%' || :q || '%' OR x.source_id LIKE :norm || '%'
                ORDER BY p.name LIMIT :lim
            """),
            {"q": q, "norm": norm, "lim": limit},
        )).mappings().all()
    return {"query": q, "results": [dict(r) for r in rows]}


@router.get("/players/{player_id}")
async def player_detail(player_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        bio = await _player_or_404(conn, player_id)
        agg = (await conn.execute(
            text("""
                SELECT season, count(*) AS games,
                       sum(attempts) AS attempts, sum(completions) AS completions,
                       sum(passing_yards) AS passing_yards, sum(passing_tds) AS passing_tds,
                       sum(passing_interceptions) AS interceptions,
                       round(avg(passing_epa)::numeric, 3) AS passing_epa_per_game,
                       round(avg(passing_cpoe)::numeric, 3) AS cpoe,
                       sum(carries) AS carries, sum(rushing_yards) AS rushing_yards,
                       sum(rushing_tds) AS rushing_tds,
                       sum(targets) AS targets, sum(receptions) AS receptions,
                       sum(receiving_yards) AS receiving_yards, sum(receiving_tds) AS receiving_tds,
                       round(avg(target_share)::numeric, 3) AS avg_target_share
                FROM player_game_stats
                WHERE player_id = :pid AND season = ANY(:seasons)
                GROUP BY season ORDER BY season
            """),
            {"pid": player_id, "seasons": seasons},
        )).mappings().all()
        out = {**bio, "seasons": [dict(r) for r in agg]}

        pff = (await conn.execute(
            text("""
                SELECT facet, season, snaps, slot_rate, grade
                FROM pff_player_stats
                WHERE player_id = :pid AND week = 0 AND season = ANY(:seasons)
                ORDER BY season DESC, facet
            """),
            {"pid": player_id, "seasons": seasons},
        )).mappings().all()
        if pff:
            out["pff"] = [dict(r) for r in pff]

        if bio["position"] == "QB":
            ngs = (await conn.execute(
                text("""
                    SELECT season, avg_time_to_throw, avg_intended_air_yards,
                           aggressiveness, completion_percentage_above_expectation AS cpoe,
                           passer_rating
                    FROM qb_ngs_weekly
                    WHERE player_id = :pid AND week = 0 AND season = ANY(:seasons)
                    ORDER BY season
                """),
                {"pid": player_id, "seasons": seasons},
            )).mappings().all()
            out["ngs_passing"] = [dict(r) for r in ngs]
    return out


@router.get("/players/{player_id}/gamelog")
async def player_gamelog(player_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        await _player_or_404(conn, player_id)
        rows = (await conn.execute(
            text("""
                SELECT season, week, season_type, game_id, team_id, opponent_team_id,
                       attempts, completions, passing_yards, passing_tds,
                       passing_interceptions, sacks_suffered, passing_epa, passing_cpoe,
                       carries, rushing_yards, rushing_tds,
                       targets, receptions, receiving_yards, receiving_tds,
                       target_share, air_yards_share
                FROM player_game_stats
                WHERE player_id = :pid AND season = ANY(:seasons)
                ORDER BY season, week
            """),
            {"pid": player_id, "seasons": seasons},
        )).mappings().all()
    return {"player_id": player_id, "games": [dict(r) for r in rows]}


@router.get("/players/{player_id}/plays")
async def player_plays(
    player_id: str,
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
    limit: int = Query(default=100, le=1000),
):
    gsis = player_id.split(":", 1)[1]
    async with get_engine().connect() as conn:
        await _player_or_404(conn, player_id)
        rows = (await conn.execute(
            text("""
                SELECT p.game_id, g.season, g.week, p.quarter, p.game_seconds_remaining,
                       p.down, p.ydstogo, p.yardline_100, p.play_type, p.yards_gained,
                       p.epa, p.wpa, p.success, p.score_differential,
                       p.complete_pass, p.interception, p.touchdown, p.air_yards,
                       p.qb_dropback, p.qb_scramble, p.pass_location, p.run_location,
                       CASE WHEN p.passer_player_id = :gsis THEN 'passer'
                            WHEN p.rusher_player_id = :gsis THEN 'rusher'
                            ELSE 'receiver' END AS role
                FROM plays p JOIN games g ON g.game_id = p.game_id
                WHERE g.season = ANY(:seasons)
                  AND :gsis IN (p.passer_player_id, p.rusher_player_id, p.receiver_player_id)
                ORDER BY g.season DESC, g.week DESC, p.play_id DESC
                LIMIT :lim
            """),
            {"gsis": gsis, "seasons": seasons, "lim": limit},
        )).mappings().all()
    return {"player_id": player_id, "plays": [dict(r) for r in rows]}


@router.get("/players/{player_id}/pff")
async def player_pff(
    player_id: str,
    facet: str | None = Query(default=None, description="e.g. receiving, coverage, pass_blocking"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
    weekly: bool = Query(default=False, description="False = season rows (week 0) only"),
):
    """PFF rows for a player — typed headline numbers plus the complete export
    row (stats). Weekly rows carry game_id, so PFF context joins play-by-play."""
    async with get_engine().connect() as conn:
        await _player_or_404(conn, player_id)
        rows = (await conn.execute(
            text(f"""
                SELECT facet, season, week, game_id, team_id, snaps, slot_rate,
                       wide_rate, grade, stats
                FROM pff_player_stats
                WHERE player_id = :pid AND season = ANY(:seasons)
                  {"AND facet = :facet" if facet else ""}
                  {"" if weekly else "AND week = 0"}
                ORDER BY facet, season, week
            """),
            {"pid": player_id, "seasons": seasons, **({"facet": facet} if facet else {})},
        )).mappings().all()
    return {"player_id": player_id, "rows": [dict(r) for r in rows]}


@router.get("/players/{player_id}/pff/splits")
async def player_pff_splits(
    player_id: str,
    facet: str = Query(description="split facet, e.g. passing_pressure, passing_depth"),
    season: int = Query(default=2025),
    week: int = Query(default=0, description="0 = season aggregate"),
    metrics: list[str] | None = Query(default=None, description="narrow to these metrics"),
):
    """PFF split facets as {split: {metric: value}} — e.g. pressure vs clean
    pocket, or all 16 depth/direction zones — instead of 177-558 flat columns."""
    async with get_engine().connect() as conn:
        await _player_or_404(conn, player_id)
        row = (await conn.execute(
            text("""
                SELECT stats FROM pff_player_stats
                WHERE player_id = :pid AND facet = :facet
                  AND season = :season AND week = :week
            """),
            {"pid": player_id, "facet": facet, "season": season, "week": week},
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"no {facet} row for {player_id} season={season} week={week}",
        )
    return {"player_id": player_id, "facet": facet, "season": season, "week": week,
            **compare(row, metrics)}


@router.get("/players/{player_id}/clutch")
async def player_clutch(player_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        bio = await _player_or_404(conn, player_id)
        if bio["position"] != "QB":
            raise HTTPException(status_code=400, detail="clutch surface is QB-only")
        out = await qb_clutch(conn, player_id, seasons)
    return {**{k: bio[k] for k in ("player_id", "name", "team_id")}, **out}

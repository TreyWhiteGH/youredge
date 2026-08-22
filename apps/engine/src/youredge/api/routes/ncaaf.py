"""NCAAF-specific surfaces: coaching careers, roster experience, portal churn.

These have no NFL analog. College turnover means the predictive signal sits in who is
coaching and how much production returned, not in last season's player grades — and the
coaching signal belongs to the coach, not the school, so it travels when he moves.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine

router = APIRouter(tags=["ncaaf"])


@router.get("/coaches")
async def search_coaches(q: str = Query(min_length=2), limit: int = 10):
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT coach_id, name, first_season, history_seasons
                FROM coaches WHERE name ILIKE '%' || :q || '%'
                ORDER BY history_seasons DESC, name LIMIT :lim
            """),
            {"q": q, "lim": limit},
        )).mappings().all()
    return {"query": q, "results": [dict(r) for r in rows]}


@router.get("/coaches/{coach_id}")
async def coach_career(coach_id: str):
    """Full career across every school — the portable signal.

    career_sp_residual is SP+ minus what that roster's talent predicted, averaged over
    all prior seasons anywhere. A coach who beats his talent at one school and then
    takes over another is the pattern the market is slowest to price.
    """
    async with get_engine().connect() as conn:
        coach = (await conn.execute(
            text("SELECT coach_id, name, first_season, history_seasons FROM coaches WHERE coach_id = :cid"),
            {"cid": coach_id},
        )).mappings().first()
        if coach is None:
            raise HTTPException(status_code=404, detail=f"unknown coach_id {coach_id}")
        seasons = (await conn.execute(
            text("""
                SELECT cs.season, cs.team_id, t.name AS school, cs.wins, cs.losses,
                       cs.win_pct, cs.sp_overall, cs.sp_offense, cs.sp_defense, cs.srs,
                       cs.tenure_year, cs.is_first_year_at_school,
                       round(cf.career_sp_residual::numeric, 2) AS career_sp_residual,
                       round(cf.prior_school_trajectory::numeric, 2) AS trajectory,
                       cf.seasons_of_history
                FROM coach_seasons cs
                JOIN teams t ON t.team_id = cs.team_id
                LEFT JOIN coach_features cf ON cf.coach_id = cs.coach_id
                     AND cf.season = cs.season AND cf.team_id = cs.team_id
                WHERE cs.coach_id = :cid ORDER BY cs.season
            """),
            {"cid": coach_id},
        )).mappings().all()
    return {**dict(coach), "seasons": [dict(r) for r in seasons]}


@router.get("/teams/{team_id}/coaching")
async def team_coaching(team_id: str, season: int = Query(default=2026)):
    async with get_engine().connect() as conn:
        row = (await conn.execute(
            text("""
                SELECT c.coach_id, c.name, c.history_seasons,
                       cs.season, cs.tenure_year, cs.is_first_year_at_school,
                       cs.wins, cs.losses, cs.sp_overall,
                       round(cf.career_sp_residual::numeric, 2) AS career_sp_residual,
                       round(cf.prior_school_trajectory::numeric, 2) AS trajectory,
                       cf.seasons_of_history
                FROM coach_seasons cs
                JOIN coaches c USING (coach_id)
                LEFT JOIN coach_features cf ON cf.coach_id = cs.coach_id
                     AND cf.season = cs.season AND cf.team_id = cs.team_id
                WHERE cs.team_id = :tid AND cs.season = :season
                ORDER BY cs.games DESC NULLS LAST LIMIT 1
            """),
            {"tid": team_id, "season": season},
        )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no coach for {team_id} season={season}")
    return dict(row)


@router.get("/teams/{team_id}/context")
async def team_context(team_id: str, season: int = Query(default=2026)):
    """Returning production, talent, recruiting, SP+, portal churn — with league
    percentiles, because a raw 0.63 return rate means nothing without the field."""
    async with get_engine().connect() as conn:
        row = (await conn.execute(
            text("""
                WITH ranked AS (
                    SELECT *,
                        percent_rank() OVER (PARTITION BY season ORDER BY pct_ppa) AS pct_ppa_pctile,
                        percent_rank() OVER (PARTITION BY season ORDER BY talent) AS talent_pctile,
                        percent_rank() OVER (PARTITION BY season ORDER BY portal_in) AS portal_in_pctile
                    FROM team_season_context
                )
                SELECT r.*, t.name AS team_name
                FROM ranked r JOIN teams t USING (team_id)
                WHERE r.team_id = :tid AND r.season = :season
            """),
            {"tid": team_id, "season": season},
        )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no context for {team_id} season={season}")
    d = dict(row)
    for k in ("pct_ppa_pctile", "talent_pctile", "portal_in_pctile"):
        if d.get(k) is not None:
            d[k] = round(float(d[k]), 3)
    return d


@router.get("/teams/{team_id}/transfers")
async def team_transfers(team_id: str, season: int = Query(default=2026)):
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT player_name, position, stars, eligibility,
                       CASE WHEN destination_team_id = :tid THEN 'in' ELSE 'out' END AS direction,
                       CASE WHEN destination_team_id = :tid THEN origin_team_id
                            ELSE destination_team_id END AS other_team_id
                FROM transfers
                WHERE season = :season AND :tid IN (origin_team_id, destination_team_id)
                ORDER BY direction, stars DESC NULLS LAST
            """),
            {"tid": team_id, "season": season},
        )).mappings().all()
    out = [dict(r) for r in rows]
    return {
        "team_id": team_id, "season": season,
        "in_count": sum(1 for r in out if r["direction"] == "in"),
        "out_count": sum(1 for r in out if r["direction"] == "out"),
        "transfers": out,
    }

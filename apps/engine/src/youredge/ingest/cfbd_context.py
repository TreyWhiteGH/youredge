"""NCAAF context: coaching careers, returning production, talent, portal churn.

The thesis this serves: in college, coaching and roster experience carry more signal
than last year's player grades, because the portal churns rosters. The data backs it —
2025 returning production ranged from Navy at 97.3% to New Mexico at 2.8%.

Coach-keyed by design. A coach changing schools is a new coach_seasons row, not a new
coach, so Cignetti's JMU years and his Indiana years are one career. That is what makes
"proven overperformer arrives at a bad program" visible before the market prices it.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.cfbd_context --seasons 2016 2017 ... 2026
"""

import argparse
import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

# CFBD has no portal data before this; absent must stay NULL, never 0.
PORTAL_FIRST_SEASON = 2021


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _get(client: httpx.AsyncClient, path: str, params: dict):
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def _load_team_aliases(conn) -> dict[str, str]:
    """Normalized school name -> canonical team_id.

    FBS only. The alias table covers all 684 CFBD schools, but the context layer models
    FBS competition — coaching SP+ residuals and returning production aren't comparable
    across divisions. FCS programs appear in our data only as crossover opponents, so
    they resolve to NULL here (a transfer from an FCS school keeps its FBS side and
    NULLs the other). Enabling FCS later is just widening this filter.
    """
    rows = await conn.execute(text("""
        SELECT x.source_id, x.canonical_id FROM entity_xwalk x
        JOIN teams t ON t.team_id = x.canonical_id
        WHERE x.entity_type='team' AND x.source='cfbd_alias'
          AND t.classification = 'fbs'
    """))
    return {r[0]: r[1] for r in rows}


def _date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date() if s else None


async def ingest_season(client, conn, aliases: dict, season: int) -> dict:
    """Six fetches for one season; every write idempotent."""
    stats = {"coach_seasons": 0, "context": 0, "transfers": 0, "unresolved": 0}

    def tid(name):
        return aliases.get(normalize_name(name or ""))

    coaches = await _get(client, "/coaches", {"year": season})
    returning = await _get(client, "/player/returning", {"year": season})
    talent = {t["team"]: t["talent"] for t in await _get(client, "/talent", {"year": season})}
    sp = {s["team"]: s for s in await _get(client, "/ratings/sp", {"year": season})}
    recruiting = {r["team"]: r for r in await _get(client, "/recruiting/teams", {"year": season})}
    portal = await _get(client, "/player/portal", {"year": season}) if season >= PORTAL_FIRST_SEASON else []

    # ---- coaches ----
    for c in coaches:
        coach_id = f"cfbd_coach:{c['id']}"
        name = f"{c['firstName']} {c['lastName']}".strip()
        await conn.execute(
            text("""
                INSERT INTO coaches (coach_id, name, first_season)
                VALUES (:cid, :name, :fs)
                ON CONFLICT (coach_id) DO UPDATE SET name = EXCLUDED.name,
                    first_season = LEAST(coaches.first_season, EXCLUDED.first_season)
            """),
            {"cid": coach_id, "name": name,
             "fs": min((s["year"] for s in c["seasons"]), default=season)},
        )
        for s in c["seasons"]:
            team = tid(s["school"])
            if not team:
                stats["unresolved"] += 1
                continue
            await conn.execute(
                text("""
                    INSERT INTO coach_seasons (coach_id, team_id, season, games, wins, losses,
                        ties, win_pct, srs, sp_overall, sp_offense, sp_defense,
                        preseason_rank, postseason_rank, hire_date)
                    VALUES (:cid, :tid, :season, :g, :w, :l, :t, :wp, :srs, :spo, :spf, :spd,
                            :pre, :post, :hire)
                    ON CONFLICT (coach_id, team_id, season) DO UPDATE SET
                        games=EXCLUDED.games, wins=EXCLUDED.wins, losses=EXCLUDED.losses,
                        win_pct=EXCLUDED.win_pct, srs=EXCLUDED.srs,
                        sp_overall=EXCLUDED.sp_overall, sp_offense=EXCLUDED.sp_offense,
                        sp_defense=EXCLUDED.sp_defense, hire_date=EXCLUDED.hire_date
                """),
                {"cid": coach_id, "tid": team, "season": s["year"], "g": s.get("games"),
                 "w": s.get("wins"), "l": s.get("losses"), "t": s.get("ties"),
                 "wp": s.get("winPercentage"), "srs": s.get("srs"),
                 "spo": s.get("spOverall"), "spf": s.get("spOffense"),
                 "spd": s.get("spDefense"), "pre": s.get("preseasonRank"),
                 "post": s.get("postseasonRank"), "hire": _date(c.get("hireDate"))},
            )
            stats["coach_seasons"] += 1

    # ---- portal (aggregated onto context below) ----
    portal_in: dict[str, list] = {}
    portal_out: dict[str, list] = {}
    for p in portal:
        origin, dest = tid(p.get("origin")), tid(p.get("destination"))
        name = f"{p.get('firstName','')} {p.get('lastName','')}".strip()
        if dest:
            portal_in.setdefault(dest, []).append(p.get("stars"))
        if origin:
            portal_out.setdefault(origin, []).append(p.get("stars"))
        if origin or dest:
            await conn.execute(
                text("""
                    INSERT INTO transfers (season, player_name, position, origin_team_id,
                        destination_team_id, stars, rating, eligibility, transfer_date)
                    VALUES (:s, :n, :pos, :o, :d, :st, :r, :e, :dt)
                    ON CONFLICT (season, player_name, origin_team_id, destination_team_id)
                    DO NOTHING
                """),
                {"s": season, "n": name, "pos": p.get("position"), "o": origin, "d": dest,
                 "st": p.get("stars"), "r": p.get("rating"), "e": p.get("eligibility"),
                 "dt": _date(p.get("transferDate"))},
            )
            stats["transfers"] += 1

    def star_avg(lst):
        vals = [s for s in lst if s]
        return sum(vals) / len(vals) if vals else None

    # ---- team_season_context ----
    for r in returning:
        team = tid(r["team"])
        if not team:
            stats["unresolved"] += 1
            continue
        s = sp.get(r["team"], {})
        rec = recruiting.get(r["team"], {})
        has_portal = season >= PORTAL_FIRST_SEASON
        await conn.execute(
            text("""
                INSERT INTO team_season_context (team_id, season, pct_ppa, pct_passing_ppa,
                    pct_rushing_ppa, pct_receiving_ppa, usage, passing_usage, rushing_usage,
                    receiving_usage, total_ppa, talent, recruiting_rank, recruiting_points,
                    sp_overall, sp_offense, sp_defense, sp_ranking,
                    portal_in, portal_out, portal_in_stars, portal_out_stars)
                VALUES (:tid, :season, :ppa, :pass_ppa, :rush_ppa, :rec_ppa, :usage,
                    :pass_u, :rush_u, :rec_u, :total, :talent, :rrank, :rpts,
                    :spo, :spf, :spd, :sprank, :pin, :pout, :pins, :pouts)
                ON CONFLICT (team_id, season) DO UPDATE SET
                    pct_ppa=EXCLUDED.pct_ppa, pct_passing_ppa=EXCLUDED.pct_passing_ppa,
                    pct_rushing_ppa=EXCLUDED.pct_rushing_ppa,
                    pct_receiving_ppa=EXCLUDED.pct_receiving_ppa, usage=EXCLUDED.usage,
                    talent=EXCLUDED.talent, recruiting_rank=EXCLUDED.recruiting_rank,
                    recruiting_points=EXCLUDED.recruiting_points,
                    sp_overall=EXCLUDED.sp_overall, sp_offense=EXCLUDED.sp_offense,
                    sp_defense=EXCLUDED.sp_defense, sp_ranking=EXCLUDED.sp_ranking,
                    portal_in=EXCLUDED.portal_in, portal_out=EXCLUDED.portal_out,
                    portal_in_stars=EXCLUDED.portal_in_stars,
                    portal_out_stars=EXCLUDED.portal_out_stars
            """),
            {"tid": team, "season": season,
             "ppa": r.get("percentPPA"), "pass_ppa": r.get("percentPassingPPA"),
             "rush_ppa": r.get("percentRushingPPA"), "rec_ppa": r.get("percentReceivingPPA"),
             "usage": r.get("usage"), "pass_u": r.get("passingUsage"),
             "rush_u": r.get("rushingUsage"), "rec_u": r.get("receivingUsage"),
             "total": r.get("totalPPA"), "talent": talent.get(r["team"]),
             "rrank": rec.get("rank"), "rpts": rec.get("points"),
             "spo": s.get("rating"), "spf": (s.get("offense") or {}).get("rating"),
             "spd": (s.get("defense") or {}).get("rating"), "sprank": s.get("ranking"),
             "pin": len(portal_in.get(team, [])) if has_portal else None,
             "pout": len(portal_out.get(team, [])) if has_portal else None,
             "pins": star_avg(portal_in.get(team, [])) if has_portal else None,
             "pouts": star_avg(portal_out.get(team, [])) if has_portal else None},
        )
        stats["context"] += 1

    return stats


async def compute_coach_features(conn) -> int:
    """Portable coach signal: performance at ANY prior school, carried forward.

    career_sp_residual = mean SP+ minus what that season's roster talent predicted,
    via a league-wide linear fit of SP+ on talent per season. A coach who beats his
    talent everywhere he goes is the Cignetti pattern.
    """
    await conn.execute(text("DELETE FROM coach_features"))
    result = await conn.execute(text("""
        WITH talent_fit AS (
            -- per-season league mean SP+ and talent, for a simple residual baseline
            SELECT season, avg(sp_overall) AS mean_sp, avg(talent) AS mean_talent,
                   NULLIF(stddev_pop(talent), 0) AS sd_talent,
                   NULLIF(stddev_pop(sp_overall), 0) AS sd_sp
            FROM team_season_context WHERE sp_overall IS NOT NULL AND talent IS NOT NULL
            GROUP BY season
        ),
        expected AS (
            -- expected SP+ from talent z-score (correlation folded into the sd ratio)
            SELECT c.team_id, c.season,
                   f.mean_sp + 0.6 * f.sd_sp * ((c.talent - f.mean_talent) / f.sd_talent)
                       AS expected_sp
            FROM team_season_context c JOIN talent_fit f USING (season)
            WHERE c.talent IS NOT NULL
        ),
        resid AS (
            SELECT cs.coach_id, cs.season, cs.team_id, cs.sp_overall,
                   cs.sp_overall - e.expected_sp AS sp_residual
            FROM coach_seasons cs
            LEFT JOIN expected e ON e.team_id = cs.team_id AND e.season = cs.season
            WHERE cs.sp_overall IS NOT NULL
        ),
        target AS (SELECT DISTINCT coach_id, season, team_id FROM coach_seasons)
        INSERT INTO coach_features (coach_id, season, team_id, career_sp_residual,
                                    career_sp_mean, prior_school_trajectory,
                                    seasons_of_history, arrived_this_season)
        SELECT t.coach_id, t.season, t.team_id,
               avg(p.sp_residual),
               avg(p.sp_overall),
               -- trajectory: slope of SP+ across prior seasons
               regr_slope(p.sp_overall, p.season),
               count(p.season),
               NOT EXISTS (SELECT 1 FROM coach_seasons pr
                           WHERE pr.coach_id = t.coach_id AND pr.team_id = t.team_id
                             AND pr.season < t.season)
        FROM target t
        LEFT JOIN resid p ON p.coach_id = t.coach_id AND p.season < t.season
        GROUP BY t.coach_id, t.season, t.team_id
    """))

    # tenure + first-year flags, and history counts on the coach row
    await conn.execute(text("""
        UPDATE coach_seasons cs SET
            tenure_year = sub.tenure,
            is_first_year_at_school = (sub.tenure = 1)
        FROM (SELECT coach_id, team_id, season,
                     row_number() OVER (PARTITION BY coach_id, team_id ORDER BY season) AS tenure
              FROM coach_seasons) sub
        WHERE cs.coach_id = sub.coach_id AND cs.team_id = sub.team_id AND cs.season = sub.season
    """))
    await conn.execute(text("""
        UPDATE coaches c SET history_seasons = sub.n
        FROM (SELECT coach_id, count(*) AS n FROM coach_seasons GROUP BY coach_id) sub
        WHERE c.coach_id = sub.coach_id
    """))
    return result.rowcount


async def main(seasons: list[int]):
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    engine = get_engine()

    async with httpx.AsyncClient(headers=headers, timeout=90) as client:
        async with engine.begin() as conn:
            aliases = await _load_team_aliases(conn)
        log.info("FBS team aliases loaded: %d", len(aliases))

        for season in seasons:
            try:
                async with engine.begin() as conn:
                    s = await ingest_season(client, conn, aliases, season)
                log.info("%s: %d coach-seasons, %d context, %d transfers (%d unresolved)",
                         season, s["coach_seasons"], s["context"], s["transfers"],
                         s["unresolved"])
            except Exception as e:
                log.error("%s FAILED, continuing: %s", season, e)

    async with engine.begin() as conn:
        n = await compute_coach_features(conn)
    log.info("coach_features computed: %d rows", n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.seasons))

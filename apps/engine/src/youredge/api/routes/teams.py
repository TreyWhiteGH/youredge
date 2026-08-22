"""Team unit endpoints — rating cards and player-absence impact, both sides.

GET /teams/{team_id}/defense                        defense card vs league
GET /teams/{team_id}/offense                        offense card vs league
GET /teams/{team_id}/defense/absence?player_id=...  on/off + who plugs in
GET /teams/{team_id}/offense/absence?player_id=...  same for offensive players
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.tendencies.defense import team_defense
from youredge.tendencies.offense import team_offense
from youredge.tendencies.onoff import player_onoff
from youredge.tendencies.pff_units import team_units

router = APIRouter(tags=["teams"])

DEFAULT_SEASONS = [2023, 2024, 2025]

# Backup production profile differs by side: box-score keys for defenders live
# in the stats JSONB; offensive volume lives in typed columns.
_BACKUP_DEF = text("""
    SELECT count(*) AS games,
           round(avg(sc.defense_pct)::numeric, 3) AS avg_snap_pct,
           sum((s.stats->>'def_tackles_solo')::real) AS tackles_solo,
           sum((s.stats->>'def_sacks')::real) AS sacks,
           sum((s.stats->>'def_interceptions')::real) AS interceptions,
           sum((s.stats->>'def_pass_defended')::real) AS passes_defended
    FROM player_game_stats s
    LEFT JOIN snap_counts sc ON sc.player_id = s.player_id AND sc.game_id = s.game_id
    WHERE s.player_id = :pid AND s.season = ANY(:seasons)
""")
_BACKUP_OFF = text("""
    SELECT count(*) AS games,
           round(avg(sc.offense_pct)::numeric, 3) AS avg_snap_pct,
           sum(s.attempts) AS attempts, sum(s.passing_yards) AS passing_yards,
           sum(s.passing_tds) AS passing_tds,
           sum(s.carries) AS carries, sum(s.rushing_yards) AS rushing_yards,
           sum(s.targets) AS targets, sum(s.receptions) AS receptions,
           sum(s.receiving_yards) AS receiving_yards,
           round(avg(s.target_share)::numeric, 3) AS avg_target_share
    FROM player_game_stats s
    LEFT JOIN snap_counts sc ON sc.player_id = s.player_id AND sc.game_id = s.game_id
    WHERE s.player_id = :pid AND s.season = ANY(:seasons)
""")


@router.get("/teams/{team_id}/defense")
async def defense_card(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        card = await team_defense(conn, team_id, seasons)
    if not card:
        raise HTTPException(status_code=404, detail=f"no defensive plays for {team_id}")
    return card


@router.get("/teams/{team_id}/offense")
async def offense_card(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        card = await team_offense(conn, team_id, seasons)
    if not card:
        raise HTTPException(status_code=404, detail=f"no offensive plays for {team_id}")
    return card


async def _absence(team_id: str, player_id: str, seasons: list[int],
                   side: Literal["offense", "defense"]):
    async with get_engine().connect() as conn:
        player = (await conn.execute(
            text("SELECT player_id, name, position FROM players WHERE player_id = :pid"),
            {"pid": player_id},
        )).mappings().first()
        if player is None:
            raise HTTPException(status_code=404, detail=f"unknown player_id {player_id}")

        onoff = await player_onoff(conn, player_id, seasons, side)

        slot = (await conn.execute(
            text("""
                SELECT pos_grp, pos_name, pos_abb, pos_slot, pos_rank
                FROM depth_chart WHERE team_id = :tid AND player_id = :pid
                ORDER BY pos_rank LIMIT 1
            """),
            {"tid": team_id, "pid": player_id},
        )).mappings().first()

        backup = None
        if slot:
            # Exact-slot backup first; else same position family on the chart
            # (LCB/RCB/NB are one family — a nickel's next man can be a boundary
            # CB and vice versa; WR slots are interchangeable labels). Prefer a
            # candidate whose NGS alignment label matches the absent player's
            # (slot receiver replaced by the other slot receiver, not the X).
            # PFF slot_rate (a real percentage) outranks the binary NGS label
            # when available: replacing a 69%-slot receiver prefers the next
            # slot-heavy body, not the X who happens to sit one rank below.
            backup = (await conn.execute(
                text("""
                    WITH latest_align AS (
                        SELECT DISTINCT ON (player_id) player_id, slot_rate
                        FROM pff_player_stats
                        WHERE week = 0 AND slot_rate IS NOT NULL AND facet = :align_facet
                        ORDER BY player_id, season DESC
                    ),
                    me AS (
                        SELECT p.ngs_position, a.slot_rate
                        FROM players p LEFT JOIN latest_align a ON a.player_id = p.player_id
                        WHERE p.player_id = :pid
                    ),
                    family AS (
                        SELECT d.player_id, d.pos_abb, d.pos_slot, d.pos_rank
                        FROM depth_chart d
                        WHERE d.team_id = :tid AND d.pos_grp = :grp AND d.player_id != :pid
                          AND (d.pos_abb = :abb
                               OR (:abb IN ('LCB','RCB','NB') AND d.pos_abb IN ('LCB','RCB','NB')))
                          AND (d.pos_rank > :rank OR d.pos_slot != :slot)
                    )
                    SELECT f.player_id, p.name, p.position, p.ngs_position,
                           round(a.slot_rate::numeric, 3) AS slot_rate,
                           round(me.slot_rate::numeric, 3) AS absent_slot_rate
                    FROM family f
                    JOIN players p ON p.player_id = f.player_id
                    LEFT JOIN latest_align a ON a.player_id = f.player_id
                    LEFT JOIN me ON true
                    ORDER BY
                      (f.pos_slot = :slot AND f.pos_rank = :rank + 1) DESC,
                      (f.pos_rank > :rank) DESC,
                      CASE WHEN me.slot_rate IS NOT NULL AND a.slot_rate IS NOT NULL
                           THEN abs(a.slot_rate - me.slot_rate) END NULLS LAST,
                      (p.ngs_position IS NOT DISTINCT FROM me.ngs_position) DESC,
                      f.pos_rank,
                      abs(f.pos_slot - :slot)
                    LIMIT 1
                """),
                {"tid": team_id, "pid": player_id, "grp": slot["pos_grp"],
                 "abb": slot["pos_abb"], "slot": slot["pos_slot"], "rank": slot["pos_rank"],
                 "align_facet": "receiving" if side == "offense" else "coverage"},
            )).mappings().first()

        backup_profile = None
        if backup:
            q = _BACKUP_DEF if side == "defense" else _BACKUP_OFF
            prof = (await conn.execute(
                q, {"pid": backup["player_id"], "seasons": seasons},
            )).mappings().first()
            backup_profile = {**dict(backup), **{k: (float(v) if v is not None else None)
                                                 for k, v in dict(prof).items()}}
            # Dropoff signal: starter vs replacement on PFF's grade scale
            grades = {r["player_id"]: r for r in (await conn.execute(
                text("""
                    SELECT DISTINCT ON (player_id) player_id, season,
                           grade, yprr, snaps
                    FROM pff_player_stats
                    WHERE player_id = ANY(:pids) AND week = 0 AND grade IS NOT NULL
                      AND season = ANY(:seasons)
                    ORDER BY player_id, season DESC
                """),
                {"pids": [player_id, backup["player_id"]], "seasons": seasons},
            )).mappings()}
            if backup["player_id"] in grades or player_id in grades:
                b, s = grades.get(backup["player_id"]), grades.get(player_id)
                backup_profile["pff"] = {
                    "backup_grade": b["grade"] if b else None,
                    "backup_grade_season": b["season"] if b else None,
                    "starter_grade": s["grade"] if s else None,
                    "grade_dropoff": round(b["grade"] - s["grade"], 1) if b and s else None,
                }

    return {
        "team_id": team_id,
        "side": side,
        "player": dict(player),
        "depth_slot": dict(slot) if slot else None,
        "onoff": onoff,
        "backup": backup_profile,
    }


@router.get("/teams/{team_id}/units")
async def unit_grades(team_id: str, season: int = Query(default=2025)):
    """PFF unit quality (snap-weighted grades + league rank) for pass/run
    blocking, pass rush, run defense, coverage, receiving, rushing. Pass
    protection in particular has no free-data equivalent."""
    async with get_engine().connect() as conn:
        units = await team_units(conn, team_id, season)
    if not units:
        raise HTTPException(
            status_code=404,
            detail=f"no PFF unit data for {team_id} season={season}",
        )
    return {"team_id": team_id, "season": season, "units": units}


@router.get("/teams/{team_id}/protection")
async def pass_protection(team_id: str, season: int = Query(default=2025)):
    """Pass protection detail: unit pressure rate allowed plus per-lineman rows.

    pressure_rate_allowed is derived (pressures / pass-block snaps), not PFF's
    proprietary Pass Blocking Efficiency — the components are theirs, the ratio
    is ours and is stated plainly so nobody mistakes it for a PFF metric.
    true_pass_set_grade excludes screens/play-action/quick game, which is the
    cleaner read on a lineman actually protecting.
    """
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT p.name, s.stats->>'position' AS position,
                       (s.stats->>'snap_counts_pass_block')::real AS pb_snaps,
                       (s.stats->>'pressures_allowed')::real AS pressures,
                       (s.stats->>'sacks_allowed')::real AS sacks,
                       (s.stats->>'hurries_allowed')::real AS hurries,
                       (s.stats->>'hits_allowed')::real AS hits,
                       s.grade,
                       (s.stats->>'true_pass_set_grades_pass_block')::real AS true_pass_set_grade
                FROM pff_player_stats s JOIN players p USING (player_id)
                WHERE s.facet = 'pass_blocking' AND s.season = :season AND s.week = 0
                  AND s.team_id = :tid
                  AND (s.stats->>'snap_counts_pass_block')::real >= 100
                ORDER BY pb_snaps DESC
            """),
            {"tid": team_id, "season": season},
        )).mappings().all()
    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"no pass-blocking data for {team_id} season={season}")

    linemen = []
    tot_snaps = tot_press = 0.0
    for r in rows:
        d = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in dict(r).items()}
        if r["pb_snaps"]:
            d["pressure_rate_allowed"] = round((r["pressures"] or 0) / r["pb_snaps"], 4)
            tot_snaps += r["pb_snaps"]
            tot_press += r["pressures"] or 0
        linemen.append(d)

    return {
        "team_id": team_id, "season": season,
        "unit": {
            "pass_block_snaps": int(tot_snaps),
            "pressures_allowed": int(tot_press),
            "pressure_rate_allowed": round(tot_press / tot_snaps, 4) if tot_snaps else None,
            "linemen": len(linemen),
        },
        "by_lineman": linemen,
    }


@router.get("/teams/{team_id}/offense/receiver-alignment")
async def receiver_alignment(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    """Team pass production split by target's NGS alignment label (SLOT_WR vs
    WR vs TE...). Labels are the player's current primary alignment per NGS
    tracking — historical targets are attributed to today's label, and per-snap
    alignment percentages would need licensed (PFF) data."""
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT coalesce(p.ngs_position, p.position, 'UNKNOWN') AS alignment,
                       count(*) AS targets,
                       round(avg(pl.complete_pass::int)::numeric, 4) AS catch_rate,
                       round(avg(pl.epa)::numeric, 4) AS epa_per_target,
                       round(avg(pl.success::int)::numeric, 4) AS success_rate,
                       round(avg(pl.air_yards)::numeric, 2) AS adot,
                       round((count(*)::numeric / sum(count(*)) OVER ()), 4) AS target_share
                FROM plays pl
                JOIN games g ON g.game_id = pl.game_id
                LEFT JOIN players p ON p.player_id = 'nfl:' || pl.receiver_player_id
                WHERE g.league = :league AND g.season = ANY(:seasons)
                  AND pl.posteam_id = :tid AND pl.play_type = 'pass'
                  AND pl.receiver_player_id IS NOT NULL
                GROUP BY 1 HAVING count(*) >= 10
                ORDER BY targets DESC
            """),
            {"tid": team_id, "seasons": seasons,
             "league": team_id.split(":", 1)[0]},
        )).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no targets found for {team_id}")
    return {"team_id": team_id, "seasons": seasons,
            "by_alignment": [dict(r) for r in rows]}


@router.get("/teams/{team_id}/defense/absence")
async def defense_absence(
    team_id: str,
    player_id: str = Query(description="canonical id, e.g. nfl:00-0033886"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    return await _absence(team_id, player_id, seasons, "defense")


@router.get("/teams/{team_id}/offense/absence")
async def offense_absence(
    team_id: str,
    player_id: str = Query(description="canonical id, e.g. nfl:00-0036322"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    return await _absence(team_id, player_id, seasons, "offense")

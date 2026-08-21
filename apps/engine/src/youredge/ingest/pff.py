"""PFF Premium Stats CSV ingest — manual export drops, no consumer API.

Workflow (PFF+ subscription required, ToS forbids scraping):
  1. PFF.com -> Premium Stats -> pick facet (Receiving, Coverage, ...) ->
     export CSV, season-level or a single week.
  2. Name files data/pff/<facet>_<season>.csv or <facet>_<season>_wk<week>.csv
     (e.g. receiving_2025.csv, coverage_2025_wk3.csv).
  3. docker compose run --rm ingest python -m youredge.ingest.pff

Column handling: a few known headers are promoted to typed columns (slot rate,
snaps, grade); EVERY column is preserved in stats JSONB, so shape drift in PFF
exports never loses data — promote more columns as needed.

Player resolution: PFF rows carry PFF's own player_id, which is exactly
nflverse's pff_id — so resolution is an exact xwalk lookup (source='pff'),
not a name match. This matters for duplicate names: PFF 46601 is QB Josh
Allen, never the Jaguars linebacker. Rows without a usable id fall back to
normalized name + team; anything still unresolved is logged and skipped.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

DATA_DIR = Path("/app/data/pff")
FNAME = re.compile(r"^(?P<facet>[a-z_]+)_(?P<season>\d{4})(?:_wk(?P<week>\d+))?\.(?P<ext>csv|json)$")

# Candidate PFF header names per typed column (first match wins, case-insensitive).
PROMOTED = {
    "snaps": ["snap_counts_total", "snaps", "snap_counts_pass_play", "total_snaps"],
    "slot_rate": ["slot_rate", "slot_snaps_pct", "pct_slot"],
    "wide_rate": ["wide_rate", "wide_snaps_pct", "pct_wide"],
    "grade": ["grades_offense", "grades_defense", "grades_coverage_defense",
              "grades_pass_route", "grade"],
}
NAME_COLS = ["player", "player_name", "name"]
TEAM_COLS = ["team_name", "team", "franchise"]

# PFF's team abbreviation dialect -> nflverse canonical
TEAM_ALIASES = {"ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
                "SD": "LAC", "OAK": "LV", "SL": "LA"}


def _team_id(abbr) -> str | None:
    if abbr is None or pd.isna(abbr):
        return None
    a = str(abbr).upper()
    return f"nfl:{TEAM_ALIASES.get(a, a)}"


def _col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


async def ingest_file(conn, path: Path, alias_map: dict, team_by_player: dict,
                      pff_id_map: dict) -> tuple[int, int]:
    m = FNAME.match(path.name)
    if not m:
        log.warning("skipping %s (name must be <facet>_<season>[_wk<N>].csv)", path.name)
        return 0, 0
    facet, season = m["facet"], int(m["season"])
    week = int(m["week"]) if m["week"] else 0
    # PFF postseason weeks -> canonical (nflverse) playoff weeks
    week = {28: 19, 29: 20, 30: 21, 32: 22}.get(week, week)

    df = pd.read_json(path) if m["ext"] == "json" else pd.read_csv(path)
    name_col = _col(df, NAME_COLS)
    team_col = _col(df, TEAM_COLS)
    if name_col is None:
        log.warning("%s: no player-name column found in %s", path.name, list(df.columns)[:8])
        return 0, 0
    typed_cols = {k: _col(df, v) for k, v in PROMOTED.items()}

    id_col = _col(df, ["player_id", "pff_id"])

    upserted = skipped = 0
    for row in df.to_dict("records"):
        pid = None
        if id_col is not None and pd.notna(row.get(id_col)):
            pid = pff_id_map.get(str(int(row[id_col])))
        if pid is None:
            key = normalize_name(str(row[name_col]))
            pids = alias_map.get(key, [])
            if len(pids) > 1 and team_col:
                team = _team_id(row[team_col])
                pids = [p for p in pids if team_by_player.get(p) == team] or pids
            if len(pids) == 1:
                pid = pids[0]
        if pid is None:
            log.warning("%s: unresolved player %r (pff_id=%s)",
                        path.name, row[name_col], row.get(id_col))
            skipped += 1
            continue
        pids = [pid]

        def num(col):
            if col is None or pd.isna(row.get(col)):
                return None
            v = float(row[col])
            return v / 100.0 if col and "rate" in col.lower() and v > 1 else v

        await conn.execute(
            text("""
                INSERT INTO pff_player_stats
                    (player_id, season, week, facet, team_id, snaps, slot_rate,
                     wide_rate, grade, stats)
                VALUES (:pid, :season, :week, :facet, :team, :snaps, :slot, :wide,
                        :grade, CAST(:stats AS jsonb))
                ON CONFLICT (player_id, season, facet, week) DO UPDATE
                  SET team_id = EXCLUDED.team_id, snaps = EXCLUDED.snaps,
                      slot_rate = EXCLUDED.slot_rate, wide_rate = EXCLUDED.wide_rate,
                      grade = EXCLUDED.grade, stats = EXCLUDED.stats
            """),
            {
                "pid": pids[0], "season": season, "week": week, "facet": facet,
                "team": _team_id(row.get(team_col)) if team_col else None,
                "snaps": int(row[typed_cols["snaps"]]) if typed_cols["snaps"] and pd.notna(row.get(typed_cols["snaps"])) else None,
                "slot": num(typed_cols["slot_rate"]),
                "wide": num(typed_cols["wide_rate"]),
                "grade": num(typed_cols["grade"]),
                "stats": json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()},
                                    default=str),
            },
        )
        upserted += 1
    log.info("%s: %d upserted, %d unresolved", path.name, upserted, skipped)
    return upserted, skipped


async def main():
    if not DATA_DIR.exists() or not any([*DATA_DIR.glob("*.csv"), *DATA_DIR.glob("*.json")]):
        raise SystemExit(
            f"No PFF files in {DATA_DIR}. Drop exports named <facet>_<season>[_wk<N>].csv"
            " or let the harvester write .json there."
        )
    engine = get_engine()
    async with engine.begin() as conn:
        # Built from players directly (not the alias xwalk, which drops ambiguous
        # names): PFF rows carry a team, so duplicate names stay resolvable here.
        alias_map: dict[str, list[str]] = {}
        team_by_player: dict[str, str] = {}
        for pid, name, team in await conn.execute(text(
                "SELECT player_id, name, team_id FROM players WHERE league='nfl'")):
            alias_map.setdefault(normalize_name(name), []).append(pid)
            if team:
                team_by_player[pid] = team
        pff_id_map = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT source_id, canonical_id FROM entity_xwalk "
            "WHERE entity_type='player' AND source='pff'"))}
        log.info("pff id map: %d players", len(pff_id_map))

        for path in sorted([*DATA_DIR.glob("*.csv"), *DATA_DIR.glob("*.json")]):
            await ingest_file(conn, path, alias_map, team_by_player, pff_id_map)

        # Weekly rows -> canonical game via (season, week, team), either side
        await conn.execute(text("""
            UPDATE pff_player_stats s SET game_id = g.game_id
            FROM games g
            WHERE s.game_id IS NULL AND s.week > 0 AND g.league = 'nfl'
              AND g.season = s.season AND g.week = s.week
              AND s.team_id IN (g.home_team_id, g.away_team_id)
        """))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

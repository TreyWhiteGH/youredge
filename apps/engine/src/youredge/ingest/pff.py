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
from youredge.pff_splits import derive_splits

log = logging.getLogger(__name__)

DATA_DIR = Path("/app/data/pff")
# League is carried by directory, not filename, so the 1,500 existing NFL files keep
# working unchanged: data/pff/*.json is NFL, data/pff/ncaa/*.json is college.
NCAA_DIR = DATA_DIR / "ncaa"
FNAME = re.compile(r"^(?P<facet>[a-z_]+)_(?P<season>\d{4})(?:_wk(?P<week>\d+))?\.(?P<ext>csv|json)$")

# Candidate PFF header names per typed column (first match wins, case-insensitive).
PROMOTED = {
    # "snaps" is the facet's volume denominator, not always literal snaps:
    # every facet reports participation differently (routes for receivers,
    # dropbacks for QBs, attempts for backs). First match wins, so unit
    # rollups can weight by it uniformly.
    "snaps": ["snap_counts_offense", "snap_counts_defense", "snap_counts_total",
              "snap_counts_block", "snap_counts_pass_block", "snap_counts_run_block",
              "snap_counts_coverage", "snap_counts_pass_rush", "snap_counts_run_defense",
              "snap_counts_run", "coverage_snaps", "snaps", "total_snaps", "passing_snaps", "routes",
              "attempts", "dropbacks", "snap_counts_pass_play", "snap_counts_run_play"],
    "slot_rate": ["slot_rate", "slot_snaps_pct", "pct_slot"],
    "wide_rate": ["wide_rate", "wide_snaps_pct", "pct_wide"],
    "inline_rate": ["inline_rate"],
    "routes": ["routes"],
    "yprr": ["yprr", "yards_per_route_run"],
    "grade": ["grades_offense", "grades_defense", "grade"],
}
# Rates PFF reports as percentages; stored 0-1 like every other rate we keep.
PCT_COLS = {"slot_rate", "wide_rate", "inline_rate"}

# "grade" should mean *this facet's* grade. A global priority list can't do that:
# facets share column names (the rushing export also carries grades_run_block for
# blocking backs), so a shared list silently grades the wrong skill. Explicit
# per-facet choice, falling back to PROMOTED["grade"].
FACET_GRADE = {
    "pass_blocking": "grades_pass_block",
    "run_blocking": "grades_run_block",
    "coverage": "grades_coverage_defense",
    "coverage_scheme": "grades_coverage_defense",
    "slot_coverage": "grades_coverage_defense",
    "pass_rush": "grades_pass_rush_defense",
    "prp": "grades_pass_rush_defense",
    "run_defense": "grades_run_defense",
    "defense": "grades_defense",
}
NAME_COLS = ["player", "player_name", "name"]
TEAM_COLS = ["team_name", "team", "franchise"]

# PFF's team abbreviation dialect -> nflverse canonical
TEAM_ALIASES = {"ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
                "SD": "LAC", "OAK": "LV", "SL": "LA"}


def _team_id(abbr, league: str = "nfl") -> str | None:
    """PFF team abbreviation -> canonical team_id.

    NFL only. PFF's college team names are truncated ('S JOSE ST', 'N TEXAS') and do
    not normalize onto CFBD's, so college teams must resolve through a
    franchise_id-keyed crosswalk instead — see the guard in main().
    """
    if abbr is None or pd.isna(abbr) or league != "nfl":
        return None
    a = str(abbr).upper()
    return f"nfl:{TEAM_ALIASES.get(a, a)}"


def _col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def _snap_col(df: pd.DataFrame) -> str | None:
    """Volume column, falling back to any un-prefixed snap_counts_* column.

    PFF names participation differently in every export and keeps adding
    facets; the fallback means a new report weights correctly on arrival
    instead of silently landing NULL snaps.
    """
    if col := _col(df, PROMOTED["snaps"]):
        return col
    splits = derive_splits(list(df.columns))
    candidates = [c for c in df.columns
                  if c.lower().startswith("snap_counts_")
                  and not any(c.lower().startswith(p + "_") for p in splits)]
    return max(candidates, key=lambda c: df[c].fillna(0).sum(), default=None)


async def ingest_file(conn, path: Path, alias_map: dict, team_by_player: dict,
                      pff_id_map: dict, league: str = "nfl") -> tuple[int, int]:
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
    typed_cols["snaps"] = _snap_col(df)
    if (preferred := FACET_GRADE.get(facet)) and (col := _col(df, [preferred])):
        typed_cols["grade"] = col

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
                team = _team_id(row[team_col], league)
                pids = [p for p in pids if team_by_player.get(p) == team] or pids
            if len(pids) == 1:
                pid = pids[0]
        if pid is None:
            log.warning("%s: unresolved player %r (pff_id=%s)",
                        path.name, row[name_col], row.get(id_col))
            skipped += 1
            continue
        pids = [pid]

        def num(target):
            col = typed_cols.get(target)
            if col is None or pd.isna(row.get(col)):
                return None
            v = float(row[col])
            return v / 100.0 if target in PCT_COLS else v

        snaps = num("snaps")
        await conn.execute(
            text("""
                INSERT INTO pff_player_stats
                    (player_id, season, week, facet, team_id, snaps, slot_rate,
                     wide_rate, inline_rate, routes, yprr, grade, stats)
                VALUES (:pid, :season, :week, :facet, :team, :snaps, :slot, :wide,
                        :inline, :routes, :yprr, :grade, CAST(:stats AS jsonb))
                ON CONFLICT (player_id, season, facet, week) DO UPDATE
                  SET team_id = EXCLUDED.team_id, snaps = EXCLUDED.snaps,
                      slot_rate = EXCLUDED.slot_rate, wide_rate = EXCLUDED.wide_rate,
                      inline_rate = EXCLUDED.inline_rate, routes = EXCLUDED.routes,
                      yprr = EXCLUDED.yprr, grade = EXCLUDED.grade,
                      stats = EXCLUDED.stats
            """),
            {
                "pid": pids[0], "season": season, "week": week, "facet": facet,
                "team": _team_id(row.get(team_col), league) if team_col else None,
                "snaps": int(snaps) if snaps is not None else None,
                "slot": num("slot_rate"),
                "wide": num("wide_rate"),
                "inline": num("inline_rate"),
                "routes": int(r) if (r := num("routes")) is not None else None,
                "yprr": num("yprr"),
                "grade": num("grade"),
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
                "SELECT player_id, name, team_id FROM players WHERE league = :lg"),
                {"lg": "nfl"}):
            alias_map.setdefault(normalize_name(name), []).append(pid)
            if team:
                team_by_player[pid] = team
        pff_id_map = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT source_id, canonical_id FROM entity_xwalk "
            "WHERE entity_type='player' AND source='pff'"))}
        log.info("pff id map: %d players", len(pff_id_map))

        for path in sorted([*DATA_DIR.glob("*.csv"), *DATA_DIR.glob("*.json")]):
            await ingest_file(conn, path, alias_map, team_by_player, pff_id_map, "nfl")

        # College files are refused rather than name-matched. PFF college player ids
        # are a separate id space with no crosswalk to CFBD, and the name fallback
        # does not merely fail - it succeeds wrongly, writing college production into
        # same-named NFL players' rows. Observed: 22 of 50 college receivers matched
        # NFL players and overwrote them. Refusing is the only safe default until a
        # pff_ncaa_player crosswalk exists.
        ncaa_files = sorted([*NCAA_DIR.glob("*.csv"), *NCAA_DIR.glob("*.json")]) \
            if NCAA_DIR.exists() else []
        if ncaa_files:
            has_xwalk = (await conn.execute(text(
                "SELECT 1 FROM entity_xwalk WHERE entity_type='player' "
                "AND source='pff_ncaa' LIMIT 1"))).first()
            if not has_xwalk:
                log.error(
                    "%d college PFF file(s) in %s skipped: no 'pff_ncaa' player "
                    "crosswalk exists yet. Build the franchise_id team crosswalk and "
                    "the jersey-validated player crosswalk first - name matching "
                    "would corrupt NFL rows.", len(ncaa_files), NCAA_DIR)
            else:
                ncaa_ids = {r[0]: r[1] for r in await conn.execute(text(
                    "SELECT source_id, canonical_id FROM entity_xwalk "
                    "WHERE entity_type='player' AND source='pff_ncaa'"))}
                for path in ncaa_files:
                    await ingest_file(conn, path, {}, {}, ncaa_ids, "ncaaf")

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

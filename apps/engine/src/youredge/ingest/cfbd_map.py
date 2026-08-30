"""Pure transforms: CFBD v2 payloads → canonical schema rows.

Kept side-effect free so they can be tested against the JSON dumps in data/:
    python -m youredge.ingest.cfbd_pbp --seasons 2024 --week 1 --dump

Conventions:
- canonical team_id: 'ncaaf:<cfbd numeric id>'   (e.g. 'ncaaf:59')
- canonical game_id: 'ncaaf:<cfbd game id>'      (e.g. 'ncaaf:401635525')
- plays reference teams by NAME; resolve via the name→team_id map built from
  the same run's games payload. Unresolvable plays are skipped and counted.

Caveats:
- CFBD offenseScore/defenseScore is the score at the time of the play; we treat
  it as pre-snap. Spot-checks show scoring plays update on the NEXT play, which
  matches pre-snap semantics.
- ppa is CFBD's EPA analog. Comparable concept to nflverse epa, different scale;
  never mix leagues in one aggregate without normalizing.
- OT plays (period > 4) get game_seconds_remaining = NULL.
"""

from datetime import datetime
from typing import Any

RUN_TYPES = {"Rush", "Rushing Touchdown", "Two Point Rush"}
PASS_TYPES = {
    "Pass Reception", "Pass Incompletion", "Passing Touchdown", "Sack",
    "Pass Interception Return", "Interception Return Touchdown", "Interception",
    "Two Point Pass",
}
PUNT_TYPES = {"Punt", "Blocked Punt", "Punt Return Touchdown", "Blocked Punt Touchdown"}
FG_TYPES = {"Field Goal Good", "Field Goal Missed", "Blocked Field Goal"}
KICKOFF_TYPES = {"Kickoff", "Kickoff Return (Offense)", "Kickoff Return Touchdown"}
NO_PLAY_TYPES = {"Timeout", "End Period", "End of Half", "End of Game", "End of Regulation"}


def map_play_type(play_type: str, play_text: str | None) -> str:
    """Map CFBD playType text to nflverse-compatible vocabulary."""
    if play_type in RUN_TYPES:
        return "run"
    if play_type in PASS_TYPES:
        return "pass"
    if play_type in PUNT_TYPES:
        return "punt"
    if play_type in FG_TYPES:
        return "field_goal"
    if play_type in KICKOFF_TYPES:
        return "kickoff"
    if play_type == "Penalty":
        return "penalty"
    if play_type in NO_PLAY_TYPES:
        return "no_play"
    # Fumbles, safeties, uncategorized: recover the call from the text
    text = (play_text or "").lower()
    if " pass" in text or "sacked" in text:
        return "pass"
    if " run " in text or " rush" in text or "run for" in text:
        return "run"
    return "other"


def game_seconds_remaining(period: int, clock: dict | None) -> int | None:
    if period is None or period > 4 or not clock:
        return None
    return (4 - period) * 900 + (clock.get("minutes") or 0) * 60 + (clock.get("seconds") or 0)


def parse_kickoff(start_date: str) -> datetime:
    return datetime.fromisoformat(start_date.replace("Z", "+00:00"))


def transform_games(games: list[dict]) -> dict[str, Any]:
    """games payload → team rows, game rows, xwalk rows, and name→team_id map."""
    team_rows: dict[str, dict] = {}
    game_rows: list[dict] = []
    xwalk_rows: list[dict] = []
    name_to_tid: dict[str, str] = {}

    for g in games:
        pairs = (
            (g["homeId"], g["homeTeam"]),
            (g["awayId"], g["awayTeam"]),
        )
        for tid_num, name in pairs:
            tid = f"ncaaf:{tid_num}"
            if tid not in team_rows:
                team_rows[tid] = {"tid": tid, "abbr": name, "name": name}
                xwalk_rows.append(
                    {"etype": "team", "cid": tid, "source": "cfbd", "sid": str(tid_num)}
                )
            name_to_tid[name] = tid

        gid = f"ncaaf:{g['id']}"
        game_rows.append({
            "gid": gid,
            "season": int(g["season"]),
            "week": int(g["week"]),
            "season_type": "postseason" if g.get("seasonType") == "postseason" else "regular",
            "kickoff": parse_kickoff(g["startDate"]),
            "home": f"ncaaf:{g['homeId']}",
            "away": f"ncaaf:{g['awayId']}",
            "status": "final" if g.get("completed") else "scheduled",
            "home_score": g.get("homePoints"),
            "away_score": g.get("awayPoints"),
            "notes": g.get("notes"),
        })
        xwalk_rows.append({"etype": "game", "cid": gid, "source": "cfbd", "sid": str(g["id"])})

    return {
        "teams": list(team_rows.values()),
        "games": game_rows,
        "xwalk": xwalk_rows,
        "name_to_tid": name_to_tid,
    }


def transform_plays(
    plays: list[dict], name_to_tid: dict[str, str], known_gids: set[str]
) -> tuple[list[tuple], int]:
    """plays payload → tuples in PLAY_COLS order (see cfbd_pbp.PLAY_COLS).

    Returns (records, skipped) — skipped counts plays whose game or teams
    could not be resolved.
    """
    records: list[tuple] = []
    skipped = 0
    for p in plays:
        gid = f"ncaaf:{p['gameId']}"
        off = name_to_tid.get(p.get("offense"))
        deff = name_to_tid.get(p.get("defense"))
        if gid not in known_gids or off is None or deff is None:
            skipped += 1
            continue
        off_score = p.get("offenseScore")
        def_score = p.get("defenseScore")
        records.append((
            gid,
            str(p["id"]),
            p.get("period"),
            game_seconds_remaining(p.get("period"), p.get("clock")),
            p.get("driveNumber"),
            off,
            deff,
            p.get("down"),
            p.get("distance"),
            p.get("yardsToGoal"),
            map_play_type(p.get("playType", ""), p.get("playText")),
            float(p["yardsGained"]) if p.get("yardsGained") is not None else None,
            float(p["ppa"]) if p.get("ppa") is not None else None,
            None,  # wp: not provided per-play by CFBD REST
            (off_score - def_score) if off_score is not None and def_score is not None else None,
            None, None, None,  # player ids: CFBD plays don't carry athlete ids; playText parse later
            # Absolute scoreboard. The differential above cannot distinguish a
            # touchdown with a missed PAT from one with a two-point conversion,
            # and cannot see a return touchdown at all, because that play belongs
            # to no offensive drive. These two can.
            # Resolve both sides through the same name map rather than string
            # comparison: CFBD writes the home team's name in two fields that do
            # not always agree exactly, and a mismatch silently swaps the whole
            # game's scoreboard.
            *((off_score, def_score)
              if name_to_tid.get(p.get("home")) == off
              else (def_score, off_score)),
        ))
    return records, skipped


def transform_lines(
    lines: list[dict], known_gids: set[str]
) -> tuple[list[dict], int]:
    """lines payload → snapshot dicts. Skips games not already ingested (FCS leak-through).

    Each dict: {gid, bookmaker, market_key, outcome, line, price, captured_at}.
    Spread convention: CFBD 'spread' is the HOME line (negative = home favored).
    Outcomes are canonical team ids for spreads/h2h, 'over'/'under' for totals.
    """
    out: list[dict] = []
    skipped = 0
    for game in lines:
        gid = f"ncaaf:{game['id']}"
        if gid not in known_gids:
            skipped += 1
            continue
        captured = parse_kickoff(game["startDate"])
        home_tid = f"ncaaf:{game['homeTeamId']}"
        away_tid = f"ncaaf:{game['awayTeamId']}"
        for ln in game.get("lines") or []:
            bm = f"cfbd:{ln['provider'].lower().replace(' ', '_')}"

            def emit(market_key, outcome, line=None, price=None):
                out.append({
                    "gid": gid, "bookmaker": bm, "market_key": market_key,
                    "outcome": outcome, "line": line, "price": price,
                    "captured_at": captured,
                })

            if ln.get("spread") is not None:
                emit("spreads", home_tid, line=float(ln["spread"]))
                emit("spreads", away_tid, line=-float(ln["spread"]))
            if ln.get("overUnder") is not None:
                emit("totals", "over", line=float(ln["overUnder"]))
                emit("totals", "under", line=float(ln["overUnder"]))
            if ln.get("homeMoneyline") is not None:
                emit("h2h", home_tid, price=int(ln["homeMoneyline"]))
            if ln.get("awayMoneyline") is not None:
                emit("h2h", away_tid, price=int(ln["awayMoneyline"]))
    return out, skipped

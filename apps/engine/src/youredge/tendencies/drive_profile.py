"""Drive-level tendency surfaces — the simulator's parameters.

pass_rate.py answers "how does this team call plays in this state". These answer
the three questions a drive-level Monte Carlo actually asks each possession:

  * `drive_outcomes` — given a drive starting at this field position, how does it
    end? This is the kernel. Everything else in the sim is bookkeeping around it.
  * `pace` — seconds per play and plays per drive by score state, which is what
    turns a drive count into a clock and therefore into a total.
  * `fatigue` — yards allowed per play by drive number, first half against
    second. The proxy for defences wearing down, and the mechanism behind
    second-half script divergence.

All three are team-vs-league, matching pass_rate's shape, and all three carry
their sample size — a rate without an n is not a finding.

NFL only for now: the drive kernel reads `drives`, which is NFL-only because
CFBD play rows cannot express a scoring drive. See modeling/drives.py.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

SCORE_STATES = ["trail_big", "trail_1sc", "tied", "lead_1sc", "lead_big"]

# Field position buckets in yards to the opponent's end zone. Split where drive
# outcomes actually change rather than evenly: backed up inside your own 10 plays
# nothing like starting at midfield, and anything inside the opponent's 40 is
# already in field-goal range, which dominates the outcome mix.
FIELD_BUCKETS = [
    ("own_deep", 91, 100),      # own 1-9
    ("own_long", 76, 90),       # own 10-24
    ("own_mid", 61, 75),        # own 25-39
    ("midfield", 41, 60),       # own 40 - opp 40
    ("opp_territory", 21, 40),  # opp 39-21
    ("red_zone", 1, 20),        # opp 20 in
]

_SCORE_STATE_SQL = """
    CASE
        WHEN {col} <= -9 THEN 'trail_big'
        WHEN {col} < 0   THEN 'trail_1sc'
        WHEN {col} = 0   THEN 'tied'
        WHEN {col} <= 8  THEN 'lead_1sc'
        ELSE 'lead_big'
    END
"""

_BUCKET_SQL = """
    CASE
        WHEN d.start_yardline BETWEEN 91 AND 100 THEN 'own_deep'
        WHEN d.start_yardline BETWEEN 76 AND 90  THEN 'own_long'
        WHEN d.start_yardline BETWEEN 61 AND 75  THEN 'own_mid'
        WHEN d.start_yardline BETWEEN 41 AND 60  THEN 'midfield'
        WHEN d.start_yardline BETWEEN 21 AND 40  THEN 'opp_territory'
        WHEN d.start_yardline BETWEEN 1  AND 20  THEN 'red_zone'
    END
"""

_OUTCOMES = text(f"""
    WITH base AS (
        SELECT {_BUCKET_SQL} AS bucket, d.result, d.points, d.posteam_id
        FROM drives d
        JOIN games g ON g.game_id = d.game_id
        WHERE g.league = :league AND g.season = ANY(:seasons)
          AND d.start_yardline IS NOT NULL
          AND d.result <> 'UNKNOWN'
    )
    SELECT bucket, result,
           count(*) FILTER (WHERE posteam_id = :team_id) AS team_n,
           count(*)                                      AS league_n
    FROM base WHERE bucket IS NOT NULL
    GROUP BY bucket, result
""")

_PACE = text(f"""
    WITH base AS (
        SELECT {_SCORE_STATE_SQL.format(col="d.start_score_diff")} AS score_state,
               d.posteam_id, d.plays, d.seconds
        FROM drives d
        JOIN games g ON g.game_id = d.game_id
        WHERE g.league = :league AND g.season = ANY(:seasons)
          AND d.start_score_diff IS NOT NULL
          AND d.plays > 0
          -- A drive truncated by the half distorts both pace and length, and
          -- there is no way to know how long it would have run.
          AND d.result <> 'END_HALF' AND d.seconds IS NOT NULL AND d.seconds > 0
    )
    SELECT score_state,
           count(*)      FILTER (WHERE posteam_id = :team_id) AS team_drives,
           sum(plays)    FILTER (WHERE posteam_id = :team_id) AS team_plays,
           sum(seconds)  FILTER (WHERE posteam_id = :team_id) AS team_seconds,
           count(*)   AS league_drives,
           sum(plays) AS league_plays,
           sum(seconds) AS league_seconds
    FROM base GROUP BY score_state
""")

# Defensive fatigue: yards allowed per play by how deep into the game the drive
# is. Read against the same team's own first-half baseline, not the league's,
# because a defence that is simply bad is not a defence that tires.
_FATIGUE = text("""
    SELECT d.start_quarter <= 2 AS first_half,
           d.defteam_id = :team_id AS is_team,
           sum(d.yards) AS yards,
           sum(d.plays) AS plays
    FROM drives d
    JOIN games g ON g.game_id = d.game_id
    WHERE g.league = :league AND g.season = ANY(:seasons)
      AND d.plays > 0 AND d.yards IS NOT NULL AND d.start_quarter IS NOT NULL
    GROUP BY 1, 2
""")


async def drive_outcomes(
    conn: AsyncConnection, team_id: str, seasons: list[int]
) -> list[dict[str, Any]]:
    """Outcome mix per starting-field-position bucket, team vs league."""
    league = team_id.split(":", 1)[0]
    rows = (await conn.execute(
        _OUTCOMES, {"team_id": team_id, "league": league, "seasons": seasons}
    )).mappings().all()

    by_bucket: dict[str, dict[str, Any]] = {}
    for r in rows:
        b = by_bucket.setdefault(r["bucket"], {"results": {}, "team_n": 0, "league_n": 0})
        b["results"][r["result"]] = {"team_n": r["team_n"], "league_n": r["league_n"]}
        b["team_n"] += r["team_n"]
        b["league_n"] += r["league_n"]

    out = []
    for name, lo, hi in FIELD_BUCKETS:
        b = by_bucket.get(name)
        if not b:
            continue
        results = []
        for result, counts in sorted(b["results"].items(), key=lambda kv: -kv[1]["league_n"]):
            team_rate = counts["team_n"] / b["team_n"] if b["team_n"] else None
            league_rate = counts["league_n"] / b["league_n"]
            results.append({
                "result": result,
                "team_n": counts["team_n"],
                "team_rate": round(team_rate, 4) if team_rate is not None else None,
                "league_rate": round(league_rate, 4),
                "delta_vs_league": (
                    round(team_rate - league_rate, 4) if team_rate is not None else None
                ),
            })
        out.append({
            "bucket": name,
            "yards_to_goal": [lo, hi],
            "team_drives": b["team_n"],
            "league_drives": b["league_n"],
            "results": results,
        })
    return out


async def pace(
    conn: AsyncConnection, team_id: str, seasons: list[int]
) -> list[dict[str, Any]]:
    """Seconds per play and plays per drive by score state, team vs league."""
    league = team_id.split(":", 1)[0]
    rows = (await conn.execute(
        _PACE, {"team_id": team_id, "league": league, "seasons": seasons}
    )).mappings().all()

    cells = []
    for r in rows:
        has_team = bool(r["team_drives"])
        cells.append({
            "score_state": r["score_state"],
            "team_drives": r["team_drives"],
            "team_sec_per_play": (
                round(r["team_seconds"] / r["team_plays"], 2)
                if has_team and r["team_plays"] else None
            ),
            "team_plays_per_drive": (
                round(r["team_plays"] / r["team_drives"], 2) if has_team else None
            ),
            "league_sec_per_play": round(r["league_seconds"] / r["league_plays"], 2),
            "league_plays_per_drive": round(r["league_plays"] / r["league_drives"], 2),
        })
    cells.sort(key=lambda c: SCORE_STATES.index(c["score_state"]))
    return cells


async def fatigue(
    conn: AsyncConnection, team_id: str, seasons: list[int]
) -> dict[str, Any]:
    """Yards allowed per play, first half vs second, against the league's split.

    Positive `team_decay` means this defence gives up more per play late than it
    did early; `vs_league` puts that against how much every defence decays, since
    some second-half decay is just football.
    """
    league = team_id.split(":", 1)[0]
    rows = (await conn.execute(
        _FATIGUE, {"team_id": team_id, "league": league, "seasons": seasons}
    )).mappings().all()

    def rate(is_team: bool, first: bool) -> tuple[float | None, int]:
        yards = plays = 0
        for r in rows:
            if r["is_team"] is is_team and r["first_half"] is first:
                yards += r["yards"] or 0
                plays += r["plays"] or 0
        return (yards / plays if plays else None), plays

    t_first, t_first_n = rate(True, True)
    t_second, t_second_n = rate(True, False)
    # Baseline is every *other* defence: the query splits on defteam_id = team_id,
    # so this is a held-out field rather than one containing the team itself.
    l_first, _ = rate(False, True)
    l_second, _ = rate(False, False)
    l_first = l_first if l_first is not None else 0.0
    l_second = l_second if l_second is not None else 0.0

    team_decay = (
        round(t_second - t_first, 4) if t_first is not None and t_second is not None else None
    )
    league_decay = round(l_second - l_first, 4)
    return {
        "team_first_half_ypp": round(t_first, 4) if t_first is not None else None,
        "team_second_half_ypp": round(t_second, 4) if t_second is not None else None,
        "team_plays": {"first_half": t_first_n, "second_half": t_second_n},
        "team_decay": team_decay,
        "league_decay": league_decay,
        "vs_league": round(team_decay - league_decay, 4) if team_decay is not None else None,
    }

"""SGO's odd taxonomy -> the market vocabulary the rest of this engine speaks.

SGO names a market compositionally, and once that is seen the 123 distinct
combinations in a single college slate stop needing a 123-row table:

    oddID = {statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}

    points-home-game-sp-home                     the home spread
    points-all-1h-ou-over                        first-half total
    points-away-game-ou-over                     away team total
    passing_yards-JOHN_MATEER_1_NCAAF-game-ou-over    a passing yards prop

So the mapping is composed the same way: a base key from (statID, betType,
whether the subject is a team or a player), plus a period suffix. Anything
unrecognised returns None and is counted rather than guessed at -- a market
silently filed under the wrong key is worse than one that is missing, because
the second is visible and the first quietly corrupts a price surface.

Where SGO and The Odds API describe the same market, the Odds API spelling wins,
because every consumer in this repo -- pricing/fair_value.py, the game routes,
legs/ -- already reads those keys. Markets that only SGO carries get new keys in
the same style rather than being dropped.
"""

# statID -> our player-prop base, for betTypeID 'ou'. The first six already exist
# in odds_poller.PROP_MARKETS and keep their spelling exactly; the rest are boards
# The Odds API never offered us and are named to match its conventions.
_PLAYER_OU = {
    "passing_yards": "player_pass_yds",
    "rushing_yards": "player_rush_yds",
    "receiving_yards": "player_reception_yds",
    "receiving_receptions": "player_receptions",
    "passing_touchdowns": "player_pass_tds",
    "touchdowns": "player_tds",
    "rushing_touchdowns": "player_rush_tds",
    "receiving_touchdowns": "player_reception_tds",
    "passing_attempts": "player_pass_attempts",
    "passing_completions": "player_pass_completions",
    "passing_interceptions": "player_pass_interceptions",
    "rushing_attempts": "player_rush_attempts",
    "passing_longestCompletion": "player_pass_longest",
    "rushing_longestRush": "player_rush_longest",
    "receiving_longestReception": "player_reception_longest",
    "rushing+receiving_yards": "player_rush_reception_yds",
    "passing+rushing_yards": "player_pass_rush_yds",
    "fieldGoals_made": "player_field_goals",
    "extraPoints_kicksMade": "player_extra_points",
    "kicking_totalPoints": "player_kicking_points",
    # NFL-only boards. College books post none of these, which is why a mapping
    # validated at 100% against a college Saturday still came in at 88% against an
    # NFL week -- the missing 12% was not a bug in the composition rule, it was
    # markets the college slate never offers.
    #
    # The defensive props are worth having and worth distrusting in the same breath:
    # CAPABILITIES.md records that our own sack and interception counts run ~25%
    # light because play text often declines to name the defender. These are the
    # market's opinion, which is a useful check on a column we know undercounts, but
    # they cannot be settled against it.
    "fantasyScore": "player_fantasy_points",
    "defense_sacks": "player_sacks",
    "defense_interceptions": "player_def_interceptions",
    "defense_combinedTackles": "player_tackles",
    "defense_soloTackles": "player_solo_tackles",
    "defense_assistedTackles": "player_assisted_tackles",
}

# The yes/no boards. `touchdowns` here is the anytime-TD market The Odds API calls
# player_anytime_td, and it keeps that name; first and last scorer are their own
# markets. Everything else is "did this player record any X at all", which is a
# distinct question from the over/under and gets its own suffix.
_PLAYER_YN = {
    "touchdowns": "player_anytime_td",
    "firstTouchdown": "player_1st_td",
    "lastTouchdown": "player_last_td",
}

# Period -> key suffix. `game` is the whole game and takes no suffix, matching the
# Odds API. `reg` is regulation-only and appears solely on three-way moneylines,
# where excluding overtime is what makes a draw possible at all -- so it is the
# natural period for that market and likewise takes no suffix.
_PERIOD_SUFFIX = {
    "game": "", "reg": "", "1h": "_h1", "2h": "_h2",
    "1q": "_q1", "2q": "_q2", "3q": "_q3", "4q": "_q4",
}

TEAM_ENTITIES = ("home", "away", "all")


def is_player(stat_entity_id: str | None) -> bool:
    """Is this odd about a person rather than a side?

    SGO puts `home`, `away` or `all` here for team markets and a player id such as
    `JOHN_MATEER_1_NCAAF` for props, so anything outside the three reserved words
    is a player. Checking membership rather than pattern-matching the id means a
    change to their player-id format cannot silently reclassify team markets.
    """
    return stat_entity_id not in TEAM_ENTITIES


def market_key(odd: dict) -> str | None:
    """Our market_key for one SGO odd, or None if we do not model it.

    None is a real answer and callers must count it. The alternative -- falling
    back to some generic key -- files an unknown market alongside known ones and
    corrupts every surface that reads them.
    """
    stat = odd.get("statID")
    bet = odd.get("betTypeID")
    entity = odd.get("statEntityID")
    period = odd.get("periodID")
    if not stat or not bet or entity is None or period not in _PERIOD_SUFFIX:
        return None

    suffix = _PERIOD_SUFFIX[period]
    player = is_player(entity)

    if player:
        if bet == "ou":
            base = _PLAYER_OU.get(stat)
        elif bet == "yn":
            # An explicit first/last/anytime board, or the generic "any X at all"
            # form that SGO generates for most counting stats.
            base = _PLAYER_YN.get(stat) or (
                f"{_PLAYER_OU[stat]}_any" if stat in _PLAYER_OU else None
            )
        else:
            base = None
        return f"{base}{suffix}" if base else None

    # --- team and game markets ---------------------------------------------
    if stat == "points":
        if bet == "sp":
            base = "spreads"
        elif bet == "ml":
            base = "h2h"
        elif bet == "ml3way":
            base = "h2h_3way"
        elif bet == "eo":
            base = "totals_odd_even"
        elif bet == "ou":
            # `all` is the game total; a side is that side's team total.
            base = "totals" if entity == "all" else "team_totals"
        elif bet == "yn":
            base = "points_any" if entity == "all" else "team_points_any"
        else:
            return None
        return f"{base}{suffix}"

    if stat == "firstToScore" and bet == "ml":
        return f"first_to_score{suffix}"

    # "Did both sides score in this period" -- a game-level yes/no, quoted per
    # quarter. Not a total and not a team total: it asks about the minimum of the
    # two team scores, which neither of those can express.
    if stat == "bothTeamsScored" and bet == "yn":
        return f"both_teams_score{suffix}"

    return None


# Where the handicap lives, per bet type. A spread carries `bookSpread`, a total
# carries `bookOverUnder`, and a moneyline or yes/no carries neither -- reading the
# wrong field yields None and would store a priced rung as though it had no line,
# which collapses every rung of a ladder onto one row.
_LINE_FIELD = {"sp": "bookSpread", "ou": "bookOverUnder"}


def line_of(odd: dict) -> float | None:
    field = _LINE_FIELD.get(odd.get("betTypeID"))
    if not field:
        return None
    raw = odd.get(field)
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def book_line(odd: dict, book: dict) -> float | None:
    """A single bookmaker's handicap, falling back to the consensus.

    Books disagree about the number as well as the price -- one shop's -25.5 is
    another's -26 -- and the rung is part of what identifies the bet, so the book's
    own value is the one that matters. `spread`/`overUnder` are what byBookmaker
    calls the fields that the parent odd calls bookSpread/bookOverUnder.
    """
    bet = odd.get("betTypeID")
    key = {"sp": "spread", "ou": "overUnder"}.get(bet)
    if key:
        raw = book.get(key)
        try:
            if raw not in (None, ""):
                return float(raw)
        except (TypeError, ValueError):
            pass
    return line_of(odd)


def american(raw) -> int | None:
    """SGO prices are strings carrying an explicit sign: '-110', '+258'."""
    if raw in (None, ""):
        return None
    try:
        return int(str(raw).replace("+", ""))
    except ValueError:
        return None


def implied(price: int | None) -> float | None:
    if price is None:
        return None
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


# `outcome` in odds_snapshots is the selectable side. SGO's sideID is already that,
# with two exceptions worth normalising: home/away are stored as the team's own
# abbreviation by the Odds API path, and the three-way draw compounds have no
# equivalent there at all. Keeping sideID verbatim would make the same bet read two
# different ways depending on which poller wrote it.
def outcome_of(odd: dict, home_abbr: str | None, away_abbr: str | None) -> str | None:
    side = odd.get("sideID")
    if side == "home":
        return home_abbr
    if side == "away":
        return away_abbr
    return side

"""Parse player roles out of CFBD play text.

CFBD's /plays/stats endpoint gives play-level player attribution with real athlete
ids, but only for SEC and ACC — 790 of 2,761 games. Every other conference returns
nothing, and ESPN publishes no player participants on college plays either, so
there is no second feed to fall back on. What every play does carry is `playText`:

    Jordan McCloud pass complete to Jaden Williams for 15 yds to the TXST 47

This recovers the roles from that sentence. It is text parsing, which is exactly
the sort of thing that quietly attributes a touchdown to the wrong player, so it
is built to be *measured* rather than trusted: SEC and ACC games have both the
text and the ground truth, and `validate_playtext.py` scores this parser against
them before it is allowed anywhere near the other 71%.

Three name styles appear and all three have to work:
    'Jordan McCloud'   full name
    'W.Howard'         initial and surname
    'BAUER, Jase'      surname-first, upper case
"""

import collections
import re
from typing import NamedTuple

from sqlalchemy import text

from youredge.ingest.resolve import normalize_name

# Roles worth recovering: the ones props are written on, plus the two defensive
# events that end a drive. Blocking and tackling are not attempted — the text
# names them inconsistently and nothing downstream prices them.
PASSER, RECEIVER, RUSHER, SACKER, INTERCEPTOR = (
    "passer", "receiver", "rusher", "sacker", "interceptor",
)

# A name is anything up to the phrase that ends it. Kept deliberately loose,
# because surnames carry apostrophes, hyphens, periods and commas ("Jo'Laison
# Landry", "BAUER, Jase"), and tightening this drops real players.
_NAME = r"([A-Za-z][A-Za-z.'\-’, ]*?)"

# Conferences do not share a play-text format, and that mattered more than it
# looks. The first version of this parser was written from SEC and ACC text and
# scored against SEC and ACC ground truth, so it never saw the NFL-style rows
# other conferences use:
#
#   (07:48) No Huddle-Shotgun #24 C.Hawkins rush middle for 1 yard gain to TEM08
#   Trayvon Rudolph 60 Yd Run (Kanon Woodill Kick)
#   C.Skattebo rushed for 1 yards. TOUCHDOWN.
#
# The box-score form is used disproportionately for *scoring* plays, so missing
# it did not lose yards at random — it lost touchdowns, biasing exactly the
# events a prop is written on.
_PREFIXES = [
    re.compile(r"^\(\d+:\d+\)\s*"),                       # (07:48)
    re.compile(r"^\[[A-Z]+\]\s*"),                          # [SG]
    re.compile(r"^(?:No.?Huddle|Shotgun|Hurry.?Up)[\w\- ]*?(?=#|[A-Z][a-z])", re.I),
    re.compile(r"^#\d+\s*"),                                # #24
]

# 'Minnesota Penalty, illegal shift' arrives with play_type Rush and names no
# ball carrier. Not a parse failure — there is nobody in it.
_NO_PLAYER_EVENT = re.compile(
    r"^\w[\w .'\-]* Penalty,|kneel|takes a knee|spike|\bTEAM\b", re.I
)

_PATTERNS: list[tuple[re.Pattern, tuple[str, ...]]] = [
    # --- passing, prose form
    (re.compile(rf"^{_NAME} pass complete to {_NAME} for ", re.I), (PASSER, RECEIVER)),
    (re.compile(rf"^{_NAME} pass intercepted,", re.I), (PASSER,)),
    (re.compile(rf"^{_NAME} pass intercepted (?:for a TD )?{_NAME} return", re.I),
     (PASSER, INTERCEPTOR)),
    (re.compile(rf"^{_NAME} pass INTERCEPTED at .*?\. Intercepted by {_NAME} at ", re.I),
     (PASSER, INTERCEPTOR)),
    (re.compile(rf"^{_NAME} pass intercepted", re.I), (PASSER,)),
    (re.compile(rf"^{_NAME} pass incomplete to {_NAME}", re.I), (PASSER, RECEIVER)),
    (re.compile(rf"^{_NAME} pass incomplete", re.I), (PASSER,)),
    # --- passing, NFL-style and box-score forms
    (re.compile(rf"^{_NAME} pass (?:short|deep) (?:left|right|middle) "
                rf"(?:complete|intended) (?:to )?{_NAME}", re.I), (PASSER, RECEIVER)),
    # The trailing capture needs something to stop at: lazy and unanchored it
    # matches a single character, and the passer is silently lost.
    (re.compile(rf"^{_NAME} \d+ Yd pass from {_NAME}(?:\s*\(|\s*$)", re.I),
     (RECEIVER, PASSER)),
    (re.compile(rf"^{_NAME} pass,? (?:complete|caught) (?:by |to )?{_NAME}", re.I),
     (PASSER, RECEIVER)),
    # --- sacks
    (re.compile(rf"^{_NAME} sacked by {_NAME} for ", re.I), (PASSER, SACKER)),
    (re.compile(rf"^{_NAME} sacked for ", re.I), (PASSER,)),
    # --- rushing, every form seen
    (re.compile(rf"^{_NAME} \d+ Yd Run", re.I), (RUSHER,)),
    (re.compile(rf"^{_NAME} rush (?:up the middle|left|right|middle|end)?\s*for ", re.I),
     (RUSHER,)),
    (re.compile(rf"^{_NAME} rushed for ", re.I), (RUSHER,)),
    (re.compile(rf"^{_NAME} run for ", re.I), (RUSHER,)),
    (re.compile(rf"^{_NAME} rush for ", re.I), (RUSHER,)),
    (re.compile(rf"^{_NAME} run to the ", re.I), (RUSHER,)),
    (re.compile(rf"^{_NAME} (?:run|rush) ", re.I), (RUSHER,)),
]

# 'sacked by Kalil Alexander and Jo'Laison Landry' — a shared sack is two players.
_AND = re.compile(r"\s+and\s+", re.I)


class Role(NamedTuple):
    role: str
    name: str


def parse(play_text: str) -> list[Role]:
    """Roles named in one play's text. Empty when nothing is confidently readable."""
    if not play_text:
        return []
    text = play_text.strip()
    # Formation and jersey noise sits between the clock and the player's name,
    # so it is stripped repeatedly rather than once.
    for _ in range(4):
        before = text
        for rx in _PREFIXES:
            text = rx.sub("", text).lstrip()
        if text == before:
            break
    if _NO_PLAYER_EVENT.search(text):
        return []

    for pattern, roles in _PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        out: list[Role] = []
        for role, raw in zip(roles, m.groups()):
            for name in (_AND.split(raw) if role == SACKER else [raw]):
                cleaned = _clean(name)
                if cleaned:
                    out.append(Role(role, cleaned))
        return out
    return []


def _clean(name: str) -> str:
    """Trim a captured name to something resolvable.

    'BAUER, Jase' becomes 'Jase BAUER': the surname-first form is a display
    convention, and leaving it reversed would fail every roster lookup.
    """
    n = name.strip().strip(".,")
    if not n or len(n) < 2:
        return ""
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    n = " ".join(n.split())
    # Some rows lead with the suffix — 'Jr.  Bert Emanuel' for Bert Emanuel Jr.
    # Left alone it resolves to nobody, and it is one quarterback's whole season.
    lead = n.split(" ", 1)
    if len(lead) == 2 and lead[0].rstrip(".").lower() in ("jr", "sr", "ii", "iii", "iv"):
        n = f"{lead[1]} {lead[0].rstrip('.')}"
    return n


_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")


class Roster:
    """Team-scoped name lookup tolerating the feed's name styles and roster churn.

    Team scoping is what makes abbreviated forms resolvable at all — 'W.Howard' is
    hopeless across FBS and near-unique inside one roster. But it cannot be the
    only rule, for two reasons the data made obvious:

      * Transfers. `players.team_id` is a player's *current* team, so a 2023
        Arkansas receiver who is now at Oklahoma has no Arkansas alias, and every
        play he appears in fails a team-scoped lookup.
      * Suffixes. The roster says 'Isaiah Sategna III'; the play text says
        'Isaiah Sategna'.

    So the lookup widens in decreasing order of confidence, and every widened rule
    demands uniqueness. Two candidates resolve to neither — a coin flip here is a
    touchdown credited to the wrong player.
    """

    def __init__(self):
        self.exact: dict[tuple[str, str], str] = {}
        self.surname: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
        self.global_exact: dict[str, set[str]] = collections.defaultdict(set)

    def add(self, team_id: str, norm_name: str, player_id: str) -> None:
        self.exact[(team_id, norm_name)] = player_id
        self.global_exact[norm_name].add(player_id)
        bare = _SUFFIX.sub("", norm_name)
        if bare != norm_name:
            self.exact.setdefault((team_id, bare), player_id)
            self.global_exact[bare].add(player_id)
        parts = bare.split()
        if len(parts) >= 2:
            self.surname[(team_id, f"{parts[0][0]}|{parts[-1]}")].add(player_id)

    def resolve(self, team_id: str | None, name: str) -> str | None:
        norm = normalize_name(name)
        if not norm:
            return None
        bare = _SUFFIX.sub("", norm)

        if team_id:
            for key in ((team_id, norm), (team_id, bare)):
                hit = self.exact.get(key)
                if hit:
                    return hit

        # Transferred out of the team he played for: fall back to the whole of
        # FBS, but only when the name picks out exactly one player.
        for candidate in (norm, bare):
            pids = self.global_exact.get(candidate)
            if pids and len(pids) == 1:
                return next(iter(pids))

        if team_id:
            parts = bare.split()
            if len(parts) >= 2:
                cands = self.surname.get((team_id, f"{parts[0][0]}|{parts[-1]}"), set())
                if len(cands) == 1:
                    return next(iter(cands))
        return None


async def load_roster(conn) -> Roster:
    """Build the lookup from the team-scoped alias crosswalk."""
    r = Roster()
    rows = (await conn.execute(text("""
        SELECT source_id, canonical_id FROM entity_xwalk
        WHERE entity_type = 'player' AND source = 'ncaaf_alias_team'
    """))).all()
    for source_id, pid in rows:
        team_id, _, norm = source_id.partition("|")
        if norm:
            r.add(team_id, norm, pid)
    return r

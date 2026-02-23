import os

from .retrieve import SUPPORTED_SPORTS, fetch_scoreboard


class SportsProvider:
    """Base provider interface for scoreboard and picks."""

    id = "base"

    def supported_sports(self):
        raise NotImplementedError

    def fetch_scoreboard(self, sport_id, day_offset=0):
        raise NotImplementedError

    def fetch_picks(self, sport_id=None, day_offset=0):
        """Return a list of picks or recommendations."""
        return []


class ESPNProvider(SportsProvider):
    id = "espn"

    def supported_sports(self):
        return SUPPORTED_SPORTS

    def fetch_scoreboard(self, sport_id, date=None, day_offset=None):
        raw = fetch_scoreboard(sport_id=sport_id, date=date, day_offset=day_offset)
        return _simplify_scoreboard(sport_id, raw)

    def fetch_picks(self, sport_id=None, date=None, day_offset=None):
        """
        Lightweight placeholder picks: use the first few games of the day.
        """
        sport = sport_id or "nba"
        scoreboard = self.fetch_scoreboard(sport, date=date, day_offset=day_offset)
        picks = []
        for event in scoreboard.get("events", [])[:5]:
            matchup = event.get("shortName") or event.get("name")
            status = event.get("status", {}).get("shortDetail") or "Upcoming"
            picks.append(
                {
                    "matchup": matchup,
                    "status": status,
                    "home": event.get("home", {}).get("shortName"),
                    "away": event.get("away", {}).get("shortName"),
                }
            )
        return picks


def _is_top25_matchup(teams):
    """
    Returns True if either team is ranked in the top 25.
    Unranked teams often have rank None or 99+; those are excluded.
    """
    for side in ("home", "away"):
        rank = teams.get(side, {}).get("rank")
        if rank and rank <= 25:
            return True
    return False


def _simplify_scoreboard(sport_id, raw_json):
    league_info = raw_json.get("leagues", [{}])
    league = league_info[0] if league_info else {}
    events = []
    for event in raw_json.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        status = comp.get("status", {}) or {}
        status_type = status.get("type", {}) or {}
        competitors = comp.get("competitors", []) or []
        teams = {}
        for competitor in competitors:
            key = competitor.get("homeAway", "team")
            team_data = competitor.get("team", {}) or {}
            teams[key] = {
                "id": team_data.get("id"),
                "name": team_data.get("displayName") or team_data.get("name"),
                "shortName": team_data.get("shortDisplayName"),
                "abbrev": team_data.get("abbreviation"),
                "logo": team_data.get("logo"),
                "record": (competitor.get("records") or [{}])[0].get("summary")
                if competitor.get("records")
                else None,
                "score": competitor.get("score"),
                "rank": competitor.get("curatedRank", {}).get("current"),
            }

        # College football: only include matchups with a top-25 team
        if sport_id == "ncaaf" and not _is_top25_matchup(teams):
            continue

        events.append(
            {
                "id": event.get("id"),
                "name": event.get("name"),
                "shortName": event.get("shortName"),
                "start": event.get("date"),
                "venue": comp.get("venue", {}).get("fullName"),
                "status": {
                    "state": status_type.get("state"),
                    "detail": status_type.get("detail"),
                    "shortDetail": status_type.get("shortDetail"),
                    "completed": status_type.get("completed"),
                    "description": status.get("type", {}).get("description"),
                },
                "competitionId": comp.get("id"),
                "home": teams.get("home"),
                "away": teams.get("away"),
            }
        )

    return {
        "sport": sport_id,
        "league": {
            "name": league.get("name"),
            "abbreviation": league.get("abbreviation"),
        },
        "week": raw_json.get("week", {}).get("number"),
        "events": events,
    }


PROVIDERS = {
    "espn": ESPNProvider,
}


def get_provider():
    provider_key = os.environ.get("SPORTS_PROVIDER", "espn").lower()
    provider_cls = PROVIDERS.get(provider_key)
    if not provider_cls:
        raise ValueError(f"Unsupported provider '{provider_key}'")
    return provider_cls()

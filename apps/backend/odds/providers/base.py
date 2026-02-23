class OddsProvider:
    """Base provider interface for odds."""

    id = "base"

    def supported_sports(self):
        raise NotImplementedError

    def fetch_odds(self, sport_id, regions=None, markets=None, odds_format=None, date_format=None):
        raise NotImplementedError

"""NCAAF game weather from CFBD (Patreon Tier 1+).

Documented as paywalled in CAPABILITIES.md and NCAAF.md; the subscription makes it
reachable. One call per (season, week). Indoor games get gameIndoors=True and are
recorded as roof='dome' rather than as a temperature of nothing.
"""
import argparse, asyncio, logging
import httpx
from sqlalchemy import text
from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.cfbd_http import CFBDError, get_json

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def _get(client: httpx.AsyncClient, params: dict):
    return await get_json(client, f"{BASE}/games/weather", params)


_UPDATE = text("""
    UPDATE games g SET
        temp = COALESCE(s.temp, g.temp),
        wind = COALESCE(s.wind, g.wind),
        humidity = s.humidity, precipitation = s.precip, snowfall = s.snow,
        dew_point = s.dew, pressure = s.pressure, wind_direction = s.wind_dir,
        weather_condition = s.cond,
        roof = COALESCE(g.roof, CASE WHEN s.indoors THEN 'dome' END)
    FROM (
        SELECT unnest(CAST(:gids AS text[])) AS game_id,
               unnest(CAST(:temp AS real[])) AS temp,
               unnest(CAST(:wind AS real[])) AS wind,
               unnest(CAST(:hum  AS real[])) AS humidity,
               unnest(CAST(:pre  AS real[])) AS precip,
               unnest(CAST(:sno  AS real[])) AS snow,
               unnest(CAST(:dew  AS real[])) AS dew,
               unnest(CAST(:prs  AS real[])) AS pressure,
               unnest(CAST(:wdir AS real[])) AS wind_dir,
               unnest(CAST(:cond AS text[])) AS cond,
               unnest(CAST(:ind  AS boolean[])) AS indoors
    ) s
    WHERE g.game_id = s.game_id
""")


async def main(seasons, weeks, season_types):
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    total = 0
    async with httpx.AsyncClient(headers=headers, timeout=90) as client:
        for season in seasons:
            for st in season_types:
                for week in (weeks if st == "regular" else [1]):
                    try:
                        rows = await _get(client, {"year": season, "week": week, "seasonType": st})
                    except CFBDError as e:
                        log.warning("%s %s wk%s: %s", season, st, week, e); continue
                    if not rows:
                        continue
                    c = {k: [] for k in ("gids","temp","wind","hum","pre","sno","dew","prs","wdir","cond","ind")}
                    for r in rows:
                        c["gids"].append(f"ncaaf:{r.get('id')}")
                        c["temp"].append(_f(r.get("temperature")))
                        c["wind"].append(_f(r.get("windSpeed")))
                        c["hum"].append(_f(r.get("humidity")))
                        c["pre"].append(_f(r.get("precipitation")))
                        c["sno"].append(_f(r.get("snowfall")))
                        c["dew"].append(_f(r.get("dewPoint")))
                        c["prs"].append(_f(r.get("pressure")))
                        c["wdir"].append(_f(r.get("windDirection")))
                        c["cond"].append(r.get("weatherCondition"))
                        c["ind"].append(str(r.get("gameIndoors")).lower() == "true")
                    engine = get_engine()
                    async with engine.begin() as conn:
                        n = (await conn.execute(_UPDATE, c)).rowcount
                    total += n
                    if n:
                        log.info("%s %s wk%-2s  %4d games", season, st, week, n)
    log.info("weather written for %d games", total)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--seasons", nargs="+", type=int, required=True)
    p.add_argument("--max-week", type=int, default=17)
    p.add_argument("--season-type", nargs="+", default=["regular", "postseason"])
    a = p.parse_args()
    asyncio.run(main(a.seasons, range(1, a.max_week + 1), a.season_type))

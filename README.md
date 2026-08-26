# YourEdge

Football analytics engine and web client. Play-by-play, charting data, coaching and roster
context, and de-vigged market prices for the NFL and NCAAF.

The architecture has one rule that everything else follows from: **the engine computes
every number; nothing downstream invents one.** The web client is a view over the API, and
where a surface is not built yet the API says so with a `501` and the UI shows that rather
than a plausible-looking figure.

- [FRONTEND.md](FRONTEND.md) — web app architecture
- [CAPABILITIES.md](CAPABILITIES.md) — every table and endpoint, with the caveats each carries
- [NCAAF.md](NCAAF.md) — the college data model
- [ROADMAP.md](ROADMAP.md) — phases and what is deliberately unbuilt

---

## Prerequisites

| | Version | Notes |
|---|---|---|
| Docker Desktop | any current | runs Postgres 16, Redis 7, and the engine |
| Node | 18+ | 20+ recommended; Vite 5 will not run on 16 |
| Python | 3.12+ | only if you want to run the engine outside Docker |

You do **not** need Python locally for the normal path — the engine and every ingest job
run in containers.

---

## Quick start

Roughly five minutes to a running app with an empty database.

```bash
git clone <repo> && cd youredge
cp .env.example .env          # fill in keys — see Configuration below
make up                       # Postgres + Redis + engine on :8000
npm install                   # installs apps/web through the workspace
npm run dev                   # web client on :5173
```

Check the engine is alive:

```bash
make health
# {"status": "ok", "version": "0.1.0", "db": true}
```

Then open <http://localhost:5173>.

**It will be empty, and that is expected.** `make up` creates the schema but loads no data.
The slate will say "No games scheduled" and team pages will 404. Loading data is the next
section, and it is the slow part.

---

## Configuration

Everything lives in `.env` at the repo root. `.env` is gitignored; `.env.example` is the
template.

| Variable | Needed for | Cost |
|---|---|---|
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | always | — (defaults are fine locally) |
| `CFBD_API_KEY` | all NCAAF ingest, schedules, venues | free tier, [collegefootballdata.com/key](https://collegefootballdata.com/key) |
| `ODDS_API_KEY` | odds polling only | paid tiers; **each poll burns credits** |
| `ANTHROPIC_API_KEY` | Phase 3 Bet Lab modes | unused today — those endpoints return 501 |

NFL play-by-play comes from nflverse and needs no key at all, so you can get a useful NFL
dataset with an empty `.env`.

The web client reads `apps/web/.env.local` (optional) for `ENGINE_URL`, which defaults to
`http://localhost:8000`. See [apps/web/README.md](apps/web/README.md).

---

## Loading data

Order matters, because rows carry foreign keys to teams, games, and players. The sequence
below is dependency-correct. Times are rough on a laptop.

### 1. Games and plays — the foundation

```bash
make ingest-nfl        # nflverse PBP 2023-2025 (~5 min, no key)
make ingest-cfbd       # CFBD games/plays/lines 2023-2025 (~15 min, CFBD key)
make schedules         # current-season schedules, both leagues (~1 min)
```

`make schedules` also writes the CFBD team-name aliases, and **odds cannot resolve to games
without them** — run it before polling odds, not after.

### 2. Player identity — before anything keyed to a player

```bash
make ingest-players        # NFL player master + rosters + id crosswalks
make ingest-cfbd-roster    # NCAAF players via ESPN athlete ids
```

### 3. Player production

```bash
docker compose run --rm ingest python -m youredge.ingest.player_stats --seasons 2023 2024 2025
make ingest-cfbd-player-stats
make ingest-snaps          # snap counts + current depth charts
```

### 4. Link college careers to pro ones

`db/migrations/021_career_links.sql` creates the table *and* fills it — but migrations run
at first database init, when `players` is still empty, so on a fresh setup it inserts
nothing. Re-run just the `INSERT` after step 2, or `/players/{id}/college` returns 404 for
every player:

```bash
docker compose exec db psql -U youredge -d youredge -c "
INSERT INTO player_career_links (ncaaf_player_id, nfl_player_id, method, name_agrees)
SELECT col_p.player_id, nfl_p.player_id, 'espn_id', nfl_p.name = col_p.name
FROM entity_xwalk x
JOIN players nfl_p ON nfl_p.player_id = x.canonical_id AND nfl_p.league = 'nfl'
JOIN players col_p ON col_p.player_id = 'ncaaf:' || x.source_id
WHERE x.entity_type = 'player' AND x.source = 'espn'
ON CONFLICT DO NOTHING;"
```

It is idempotent, so running it again after a later roster ingest is safe and is how you
pick up new links.

### 5. NCAAF context — where college reasoning actually starts

```bash
make ingest-cfbd-context   # coaching, returning production, talent, SP+, portal (~10 min)
make ingest-fcs-coaches    # hand-seeded sub-FBS stints
make ingest-venues         # incl. elevation
```

### 6. Odds

```bash
make poll-odds             # one pass, 5 books, both leagues; de-vigs inline
make devig                 # backfill fair_prob on any snapshot group missing it
```

Each `poll-odds` costs API credits. It is a one-shot by design — schedule it externally
rather than looping it while developing.

### 7. Charting data (optional, licensed)

There is no API key for this one. The facet API is reachable from a logged-in
`premium.pff.com` browser tab; the harvester posts JSON to
`/api/football/pff-drop`, files land in `data/pff/`, then:

```bash
make ingest-pff
```

Without it, the Analysis and Protection tabs show "no data" and everything else works
normally. See [CAPABILITIES.md](CAPABILITIES.md) for the licensing constraints and why
college charting is deliberately refused.

### Verify what landed

```bash
curl -s localhost:8000/api/football/coverage | python3 -m json.tool
```

Or open <http://localhost:5173/data>, which renders the same counts. Both read live from
the database, so neither can drift from reality.

---

## Everyday commands

```bash
make up          # start db + redis + engine
make down        # stop (data survives)
make logs        # follow engine logs
make health      # engine + db health
make psql        # psql shell
make redis-cli   # redis shell
make reset-db    # DESTROYS the volume; migrations re-run on next `make up`
```

```bash
npm run dev      # web client with HMR on :5173
npm run build    # production bundle to apps/web/dist
```

The engine runs with `--reload`, so editing anything under `apps/engine/src` restarts it in
place. The web client hot-reloads. Neither needs a rebuild during normal work.

Interactive API docs: <http://localhost:8000/docs>

---

## Repo layout

```
apps/engine/     FastAPI service + all ingest jobs        <- the product
apps/web/        React + Vite client                      <- the UI
apps/backend/    legacy Flask service (basketball-era)    <- opt-in profile, not used
apps/mobile/     Expo shell                               <- not built out
db/migrations/   schema, applied at first db init
data/            ingest drops and dumps (gitignored)
```

`apps/backend` only starts under `docker compose --profile legacy up backend`. Nothing in
the current web client talks to it.

---

## Things that will bite you

**The engine container mounts the main checkout.** `docker-compose.yml` bind-mounts
`./apps/engine/src`, so if you are working in a git worktree the container on `:8000` cannot
see your engine changes. Run a second engine against the same database — the exact command
is in [apps/web/README.md](apps/web/README.md) — and point the client at it with
`ENGINE_URL`.

**`make migrate` is not a general migration runner.** It applies exactly two files
(`002_markets_null_unique`, `003_snapshot_nullable_price`) and exists for volumes created
before those were written. A fresh volume runs *all* of `db/migrations/` automatically
through Postgres's `docker-entrypoint-initdb.d`. If you have an old volume and are missing
later tables, apply the files you need by hand or `make reset-db` and re-ingest.

**A 404 from a team or player endpoint usually means "no rows", not "bad URL".** The engine
distinguishes them deliberately. If everything 404s, you have not ingested yet.

**A wrong-league id is a 400, not a 404.** `/api/nfl/teams/ncaaf:59` fails loudly, because
"wrong league" and "no data" mean very different things.

**`null` is not zero anywhere in this system.** A null `temp` means the weather was not
reported — CFBD's weather endpoint is paywalled — not that the game was calm or indoors.
Portal counts are null before 2021, which is not the same as zero.

**Never mix leagues in one aggregate.** NCAAF's `epa` column holds CFBD's PPA, which
averages 0.178 against the NFL's −0.004. They are different measurements wearing the same
column name.

---

## What is not built

No model has been trained. There is no simulator, no correlation engine, and no SGP
pricing, so **nothing in this app quotes an edge.** The Bet Lab modes call their real
endpoints and render the `501` those return, with the phase they are waiting on. That is
deliberate — see [ROADMAP.md](ROADMAP.md).

There is also no automated test suite. Changes are verified by running the stack.

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
make poll-odds             # one pass, both leagues; de-vigs inline
make devig                 # fill fair_prob where missing (--rebuild recomputes all)
```

Each `poll-odds` costs API credits. It is a one-shot by design — schedule it externally
rather than looping it while developing.

The meter charges one credit per market that actually **returns** a quote, not per market
requested: a 29-market request against a college game that returned nothing was charged
zero. So asking both leagues for the full board is free where the board does not exist,
and availability rations itself.

### 7. Staying current

Two services keep the running season from going stale:

```bash
docker compose --profile poller up -d poller results
```

`poller` snapshots odds on a tiered schedule. `results` runs the catch-up chain every 30
minutes — results and polls, then play-by-play, college play flags, `success`, drives, and
the derived layers when something new landed:

```bash
make catchup               # one pass of the same chain
make test                  # invariants: de-vig sums, ladder monotonicity,
                           # scoring timeline vs final scores, tag base rates
docker logs -f youredge-results
```

Without `results` running, a finished Saturday still reads as unplayed and every
current-season team card falls back to history.

### 8. Charting data (optional, licensed)

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

**A long-lived database drifts behind the repo.** Postgres runs
`docker-entrypoint-initdb.d` once, on an empty volume, so migrations added afterwards never
run on a database you already have. `db/migrate.sh` is the catch-up path — it tracks what
has been applied and baselines an existing database rather than replaying `001_init.sql`
over live tables:

```bash
./db/migrate.sh
```

`make migrate` is the older, narrower thing: it applies two specific files and predates the
tracker. Prefer the script.

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

## Where this stands (1 Sept 2026)

Written as a handover. If you are picking this up on a different machine, or
after a gap, start here and then read **Moving this off a laptop** below.

### What is solid

**The data spine.** Both leagues 2016–2026: 973k plays, 126k drives, 12.5k
games, all reconciling to final scores (NFL exactly; college 99.3%, the rest a
feed limit documented in `CAPABILITIES.md`). 358k odds snapshots across 39
market keys and 17 books, every one carrying `fair_prob`. This is the part that
cannot be rebuilt by running a script — line movement is only observable as it
happens — and it is why the backups below matter more than the code.

**De-vig.** Power method, per rung, with the sign-aware pairing that spreads
need. One-sided player ladders borrow their margin from the two-way parent;
touchdown boards scale to an expected-scorer target regressed on the closing
total. 15 tests in `make test` guard the invariants, and four of them failed on
their first run against real defects.

**The tag layer.** 13 script tags and 27 diagnostics, counted from play-by-play
only — no PFF, no box scores. Thresholds are league-relative because a flat cut
means different things in the two leagues. The vocabulary is expected to grow;
`pairs.py`, `forecast.py` and the Critique response all read it dynamically, so
a new tag needs a seed row and a predicate and nothing else.

**Staying current.** The `results` service runs the whole chain every 30
minutes and repairs what CFBD gets wrong along the way. Without it a finished
Saturday still reads as unplayed.

### The SGP estimator, and what it is honestly worth

`pricing/sgp.py` estimates what a book will quote, in three separable parts:
independence, the counted correlation, and the book's margin. Separable so a
miss can be attributed rather than guessed at.

Calibrated against **57 quotes hand-collected from DraftKings and FanDuel**
(`scripts/sgp_sheet.py` generates the slips, `scripts/sgp_record.py` reads the
answers back). Six of eight slip shapes land within ±6%:

| Design | Median miss |
|---|---|
| pair/correlated, pair/conflicting | −1 to −2% |
| triple/reinforcing | −2% |
| genuine/three-risk | +5% |
| pair/team-total | −6% |
| **triple/mixed** | **+13 to +33%** |
| **quad/reinforcing** | **+5 to +52%** |

Those last two are flagged `"reliable": false` in the response with the range
attached. Four hypotheses were tested and none explains them; the miss is
ordered in the spread, which is a real finding and not yet a model. Do not
apply a correction to them without more quotes — 12 per design is enough to see
a pattern and not enough to fit one.

**Entailment is the piece worth understanding.** Some legs cannot fail given
the others: Seattle -3.5 with over 44.5 means Seattle scores at least 25, so
"Seattle over 24.5" is free, and the books price it that way. That is
arithmetic, not correlation, and no amount of counting finds it — the empirical
surface called a certainty a 1.52 lift. `pricing/implications.py` checks it by
testing every leg against the grid of realistic scores rather than deriving it
in algebra, which caught a sign error in the first version.

### What is deliberately not shipping

Critique and Test-a-hypothesis work and are held back. Each is a
natural-language interface with a regex behind it, and a user who phrases a leg
the way people talk gets "not read" for input the engine could have answered.
They ship with the reasoning layer that makes them real. See `ROADMAP.md`.

### The open questions, in the order worth taking them

1. **Why `triple/mixed` misses.** Most valuable, least understood. Needs
   quotes across more games before it is worth modelling.
2. **Correlation conditioned on the line.** Measured and real: NCAAF spread ×
   over runs from φ 0.041 at a pick'em to 0.302 above 24 points, and the pair
   surface uses one number for both. Condition on the line rather than on unit
   ranks — the line is the market's own summary of the matchup.
3. **A touchdown-scorer template.** Anytime TD prices but cannot be correlated
   with anything, so those slips are quoted as independent. The `prop/atd-total`
   design measures the size of that gap directly.

## Moving this off a laptop

Three things exist only where you are running it, and they are not equally
replaceable.

**The code.** Push it. `git push origin main`. Everything else here assumes
this is done.

**The database.** 2.9 GB live, 126 MB as a compressed dump. Most of it
re-ingests from nflverse and CFBD on demand — but `odds_snapshots` does not,
because a line that has moved cannot be re-fetched, and `user_bets` does not,
because those 141 rows were collected by hand from two sportsbooks.

```bash
mkdir -p backups
docker exec youredge-db pg_dump -U youredge -d youredge --no-owner --no-acl -Fc \
  -f /tmp/youredge_full.dump
docker cp youredge-db:/tmp/youredge_full.dump backups/youredge_full_$(date +%Y%m%d).dump
```

Restoring onto a fresh machine:

```bash
docker compose up -d db
docker cp backups/youredge_full_YYYYMMDD.dump youredge-db:/tmp/restore.dump
docker exec youredge-db pg_restore -U youredge -d youredge --no-owner --clean --if-exists /tmp/restore.dump
bash db/migrate.sh          # applies anything newer than the dump
```

`backups/` is git-ignored. Put the dump somewhere that is not this machine —
cloud storage, an external drive, whatever you already trust. A 126 MB file is
small enough that there is no excuse for one copy of it.

**The secrets.** `.env` is not in git and must not be. Copy it across by hand.
It holds `ODDS_API_KEY` and `CFBD_API_KEY`; the Odds API key has a monthly
credit budget, so a second machine polling at the same time spends the same
quota twice. Run the poller in one place.

### Picking it back up

```bash
docker compose up -d db redis engine
docker compose --profile poller up -d poller results   # only on the machine that should poll
make test                                              # 15 invariants, should be green
```

Then `make catchup` to pull in whatever happened while you were away.

## What is not built

No model has been trained. There is no simulator, no correlation engine, and no SGP
pricing, so **nothing in this app quotes an edge.** The Bet Lab modes call their real
endpoints and render the `501` those return, with the phase they are waiting on. That is
deliberate — see [ROADMAP.md](ROADMAP.md).

There is also no automated test suite. Changes are verified by running the stack.

# YourEdge — Data & Capability Reference

*Updated 2026-08-23 (rev 3). Written for humans and for the Phase-3 LLM layer: every table
and endpoint below is a tool the Narrator/Planner can query, and the "AI context"
notes say when to reach for each. The core contract holds everywhere: **the Engine
computes every number; the LLM selects and explains.***

---

## 1. Database tables

### Reference & identity

| Table | Rows | What it is |
|---|---|---|
| `teams` | 285 | Canonical teams, both leagues. Carries `color`/`alt_color` and a `logo_url` **reference** — the artwork is never copied into this repo, so whether a mark is rendered stays a client decision.  `team_id` like `nfl:BAL`, `ncaaf:59`. `classification` marks FBS (138) vs FCS (105) for NCAAF. |
| `players` | 49,426 | NFL (4,619) `nfl:<gsis_id>` + NCAAF (44,807) `ncaaf:<espn_athlete_id>`, the id space CFBD's roster and stats endpoints share. `jersey`/`class_year` carried for college as match validators. Carries `position`, `team_id`, and `ngs_position` (NGS tracking-derived alignment: `SLOT_WR`, `SLOT_CB`, `HIGH_SAFETY`). |
| `entity_xwalk` | 128,444 | Translation between external ID systems and canonical IDs. Sources: `cfbd`, `odds_api`, `cfbd_alias`/`nflverse_alias`/`ncaaf_alias`/`ncaaf_alias_team` (normalized names), `espn`, `pfr`, `pff`. College aliases dominate the count: ~22k players/season need team-scoped keys. |

**AI context:** never invent an identifier. "Lamar" → `/players?q=` → canonical id → every other surface keys off it. Player IDs resolve *exactly* via `pff`/`espn` crosswalk rows, which is what keeps QB Josh Allen distinct from the Jaguars linebacker. If the crosswalk can't resolve something, the answer is "we can't link this," never a guess.

> **Row counts here are a snapshot, and they drift the moment the poller or the
> catch-up service writes.** `GET /football/coverage` reports them live and is the
> only figure to quote back to anyone. The numbers below are for orientation —
> which tables are large, which are thin — not for citation.

### Games & play-by-play

| Table | Rows | What it is |
|---|---|---|
| `games` | 12,553 | **NFL 2016–2026** (3,033) and **NCAAF 2016–2026** (9,520); labels backfilled for training. Complete incl. playoffs/CFP. `season_type` separates postseason; `notes` names bowls/CFP rounds (filter `ILIKE 'CFP%' OR ILIKE 'College Football Playoff%'`). |
| `plays` | 973,169 | The modeling foundation. NFL rows (484k, 2016–2026) enriched: `epa`, `wpa`, `success`, `complete_pass`, `interception`, `touchdown`, `air_yards`, `yards_after_catch`, `qb_dropback`, `qb_scramble`, `pass_location`, `run_location`, `field_goal_result`, score state, clock. NCAAF rows (489k) carry `ppa` in the `epa` column (CFBD's analog — different scale, **never mix leagues in one aggregate**) and `success` derived as `epa > 0` at ingest time. `complete_pass`, `qb_dropback`, `touchdown` and `interception` are **not** nflverse-only: `cfbd_map` folds CFBD's precise play vocabulary into the eight shared buckets and drops them, and `ingest/cfbd_play_flags.py` recovers them from `playType`. Roughly 26% of college plays carry no PPA from the feed and so get no `success` verdict either way — that is a feed limit, not a gap. |

**AI context:** every tendency, clutch metric, and script prior computes **from** this table — never quote a stat that doesn't trace here or to an official aggregate. Mode 3 hypothesis testing ("does NY's run defense fade in Q4?") is a query over `plays`, not an opinion.

### Odds

| Table | Rows | What it is |
|---|---|---|
| `markets` | 75,351 | A book's priced question per game: `(game_id, bookmaker, market_key, player_name)`. **39 market keys** across 17 bookmakers — the three featured markets, every quarter and half of spreads/totals/h2h, team totals for the halves and Q1, alternate spread and total ladders, six player props and six "X+" player ladders. DK/FD/MGM/Caesars/Pinnacle live; `cfbd:*` historical closing lines. |
| `odds_snapshots` | 249,637 | Price time series. `implied_prob` (with vig) **and** `fair_prob` (de-vigged). Unique on `(market_id, captured_at, outcome, line)` — the line is in the key because a ladder quotes one side at many numbers. |

**AI context:** the twin columns are the point. Edge = model probability − `fair_prob`, never − `implied_prob` (that overstates edge by the vig). Snapshot history = line movement, which is CLV's raw material and a narratable fact. All odds events resolve to canonical games (100% both leagues).

**What `fair_prob` means, and where it is absent.** De-vig groups a snapshot by `(market_id, captured_at, rung)` and divides each side by the pair's overround. The rung matters because a ladder keeps every step in one market row: summing across a whole alternate board gives an overround near 50, not 1.05. Spread rungs are keyed by *signed* line, since a ladder quotes both teams at every number and `|3.5|` alone gathers two complete pairs. A group must hold exactly two rows to be priced.

Books quote the player ladders one-sided, so there is no complement to normalise against; those rungs borrow the margin from their two-way parent market (`player_pass_yds_alternate` divides by the overround of `player_pass_yds` for the same player and book). The check that this holds: a ladder's rung at a player's main line reproduces that main line's own `fair_prob` to three decimals.

`player_anytime_td` and `player_tds_over` carry **no** `fair_prob`, deliberately. Their Yes prices legitimately sum well above 1 — two dozen candidate scorers, about five of whom score — so normalising to 1.0 would replace one wrong number with another. They need an expected-scorer target derived from the de-vigged game total, which is not built yet. Treat a missing `fair_prob` as "not priced", never as zero.

The multiplicative method is still biased on longshots; power/Shin and Pinnacle anchoring are open. The worst live overround is ~1.60 on a lopsided college moneyline, which is where that bias is largest.

### Player performance

| Table | Rows | What it is |
|---|---|---|
| `player_game_stats` | 234,430 | Weekly game logs 2023–2025, both leagues (NFL 56,982 + NCAAF 177,448). NCAAF rows come from CFBD `/games/players` flattened out of its four-level nesting; college has **no** `targets`, `air_yards`, or EPA (CFBD doesn't report them — NULL, not derived). Typed: attempts/completions/yards/TDs/INTs/sacks, `passing_epa`, `passing_cpoe`, carries, targets, `target_share`, `air_yards_share`, `wopr`. Full source row in `stats` JSONB (incl. all `def_*` box stats). Every row linked to canonical `game_id`, and carries `opponent_team_id`. |
| `qb_ngs_weekly` | 1,839 | Next Gen Stats passing: time-to-throw, intended air yards, aggressiveness, CPOE. Week 0 = season aggregate. |
| `ngs_receiving_weekly` | 4,310 | NGS receiving: cushion, separation, aDOT, air-yards share, YAC over expected. |
| `snap_counts` | 79,649 | Per player per game: offense/defense/ST snaps and %, plus `team_id`. The availability record behind on/off analysis. |
| `depth_chart` | 3,208 | Latest snapshot (`as_of` stamped). `pos_rank` 1 = starter. Defense has an explicit `NB` (nickel/slot) slot. |
| `pff_player_stats` | **359,513** | 22 PFF facets × 2023–2025 × season + every week (incl. playoffs). Typed: `snaps`, `slot_rate`, `wide_rate`, `inline_rate`, `routes`, `yprr`, `grade`. Complete export row in `stats` JSONB with a GIN index. Weekly rows carry `game_id` — **100% linked**. |

**AI context:** game logs answer "how has X performed" with official numbers — quote these, not sums over play-by-play. Target share + air-yards share are the prop layer's usage inputs. PFF is the layer free data can't reach: true alignment percentages, offensive-line measurement, coverage-allowed stats, and pressure splits. Snap counts + depth chart power "who plays, who's next"; injuries gate recommendations, they are never speculated about.

**PFF college is refused, not merely absent** — and the reason is subtler than it first
looked. PFF uses **one `player_id` per human across college and the pros**, so a 2024
college receiver who has since been drafted resolves to the *correct* person through our
NFL crosswalk — and then his college game lands as NFL production. On a 50-row test, 17
resolved that way. That is level conflation, not mistaken identity. `level` is now part
of the `pff_player_stats` key so both can coexist, but college rows belong under the
`ncaaf:` canonical id, which still needs a `franchise_id`-keyed team crosswalk (PFF
truncates college names to `S JOSE ST`) plus jersey-validated player matching. Until
then, `data/pff/ncaa/` files are skipped with an explicit error.

**PFF facets loaded (NFL):** `passing`, `passing_depth`, `passing_pressure`, `passing_concept`, `time_in_pocket`, `allowed_pressure`, `receiving`, `receiving_depth`, `receiving_concept`, `receiving_scheme`, `rushing`, `blocking`, `pass_blocking`, `run_blocking`, `defense`, `pass_rush`, `run_defense`, `coverage`, `coverage_scheme`, `slot_coverage`, `prp`, `field_goals`.
**Poll rank is not SP+ rank.** `team_rankings` holds the AP, Coaches and CFP committee
polls week by week; `team_season_context.sp_ranking` is a rating system's ordering. They
disagree often, and a "Top 25" built from SP+ would contain teams no voter has ranked —
so the ranked filter and every rank badge read from the poll. CFBD keys ranked teams by
the same numeric id our `ncaaf:` ids are built from, so the join is exact (1,951 rows
across 2024–2026, zero unresolved). FCS and Division II/III polls are skipped **by name
rather than by pattern**, so a new poll is reported as ignored instead of quietly
entering an FBS Top 25.

### NCAAF context (coaching & roster experience)

| Table | Rows | What it is |
|---|---|---|
| `coaches` | 374 | `cfbd_coach:<id>`, `history_seasons` = FBS seasons visible |
| `coach_seasons` | 1,583 | PK `(coach_id, team_id, season)` — **a coach changing schools is a new row, not a new coach**, so the signal travels with him. `source` marks CFBD facts vs hand-seeded FCS stints |
| `coach_features` | 1,581 | The portable signal: `career_sp_residual` (SP+ minus what his talent predicted, over all prior seasons **anywhere**), `prior_school_trajectory`, `seasons_of_history`, `arrived_this_season`, plus `fcs_*` sub-FBS record as a **separate** feature |
| `team_season_context` | 1,434 | 2016–2026 returning production (`pct_ppa` + splits, `usage`), `talent`, recruiting, SP+, `portal_in/out` (**NULL pre-2021, not zero**) |
| `transfers` | 23,358 | Portal detail 2021–2026, origin/destination/stars |

**AI context:** this is where college reasoning starts, not player stats. Roster churn
means last year's grades travel poorly, while returning production spans 2.8%–97.3% and
a proven coach arriving at a new school is a signal the market prices slowly (Cignetti:
+27.1 career residual carried from James Madison to Indiana). Always relay
`seasons_of_history` — short history means *uncertain*, not average. Full detail in
[NCAAF.md](NCAAF.md).

### Cross-league player identity

| Table | Rows | What it is |
|---|---|---|
| `player_career_links` | 1,663 | `ncaaf:<espn_id>` ↔ `nfl:<gsis_id>` for the same human, built from **ESPN athlete ids, which persist from college to the pros** — exact, no fuzzy matching |

**AI context:** the same person holds two canonical ids because college and pro data come
from different sources. This is what makes "what did this rookie do in college"
answerable (`GET /players/{id}/college`). 72 links have disagreeing names — `Cam`/`Cameron`,
`Nate`/`Nathan`, suffixes, `M.J.`/`MJ` — all the same people, and precisely the cases a
name matcher drops. `name_agrees` is surfaced, not hidden.

### Venues & conditions

| Table | Rows | What it is |
|---|---|---|
| `venues` | 899 | 852 NCAAF (with **elevation** — Laramie 2,200m) + 47 NFL. Statics only: location, capacity, dome, grass |
| `games.*` | — | Per-game `venue_id`, `roof`, `surface`, `temp`, `wind`, `neutral_site` |

**AI context:** roof and surface are game-level, not venue-level — retractable roofs open
and close, and neutral-site games (216 NCAAF, 29 NFL) aren't played on the home surface.
**Weather**: NCAAF now has temp, wind, precipitation, snowfall, humidity, dew point and
condition for 2,712 of 2,762 games (2023-25), from CFBD's weather endpoint — reachable
since the Patreon subscription. NFL remains temp/wind only (530 outdoor games, nflverse);
it has no precipitation. A NULL `temp` means *not available* — never "indoors" or "calm".

### Tagging & memory (Phase 3 surfaces, schema live)

| Table | Rows | What it is |
|---|---|---|
| `tags` | 33 | Controlled vocabulary: script tags (`SHOOTOUT`, `GARBAGE_TIME_PASS`…), leg roles (`ANCHOR`, `REDUNDANT`…), angles (`Q4`, `HOME_DOG`…), outcomes (`PROCESS_WIN`, `VARIANCE_LOSS`…). |
| `taggings` | 0 yet | Polymorphic: anything taggable with weights. `game_scripts` view = top script tags per game. |
| `user_bets` | 0 yet | Every BetLab bet: legs, price at rec time, fair prob, closing price (CLV), result. |

**AI context:** the shared language between LLM and Engine. The LLM **selects from** `tags` at runtime — never invents one mid-conversation. Parsed hypotheses become Script Specs in these tags; debriefs and coaching join on them.

---

## 2. API endpoints (`localhost:8000`, interactive docs at `/docs`)

**Paths split by league.** `/api/nfl/*` and `/api/ncaaf/*`; `/api/football/*` keeps only
genuinely cross-league surfaces (`health`, SGP stubs, `pff-drop`). Canonical IDs carry
their league, so `/api/nfl/teams/ncaaf:59` returns **400** rather than an empty result —
"wrong league" and "no data" mean different things.

### Players — `/api/nfl/*` (NFL only: props, NGS, PFF alignment, clutch)

| Endpoint | AI context — when to use it |
|---|---|
| `GET /players?q=` | Entity resolution for any player mention. Alias-normalized (`tj watt` → T.J. Watt). |
| `GET /players/{id}` | Bio, per-season aggregates, PFF grades, NGS traits (QBs). The "who is this" card. |
| `GET /players/{id}/gamelog` | Weekly rows, each tied to a canonical game. Recent form, consistency vs volatility for prop framing. |
| `GET /players/{id}/vs-opponent` | Splits by opponent (`?opponent=nfl:MIA`, `?include_games=true`). **Samples are tiny** — `games` ships with every rate; weight accordingly. |
| `GET /players/{id}/plays` | Enriched play log with role, EPA, WPA, air yards. Drill-down evidence behind a claim. |
| `GET /players/{id}/clutch` | QB-only: late&close EPA/dropback vs own baseline *and* league, two-minute drill, clutch-drive score rate, `small_sample` flag. |
| `GET /players/{id}/pff` | PFF rows by `facet`/`seasons`/`weekly`. Typed headliners + complete export row. |
| `GET /players/{id}/pff/splits` | **Split facets as `{split: {metric: value}}`** — pressure vs clean, 16 depth×direction zones, man vs zone, play-action vs not. Narrow with `metrics=`. This is how the LLM reaches 558-column tables without knowing column names. |

### Teams — `/api/nfl/*` and `/api/ncaaf/*`

| Endpoint | AI context |
|---|---|
| `GET /teams/{id}/offense` · `/defense` | Unit cards: pass/run EPA, success, explosive, INT rate, red-zone TD rate, late&close — with league ranks. Matchup table-setting and sim priors. |
| `GET /teams/{id}/units` | **PFF unit grades** (snap-weighted + rank): pass/run blocking, pass rush, run defense, coverage, receiving, rushing. Pass protection has no free-data equivalent. |
| `GET /teams/{id}/protection` | Unit pressure rate allowed + per-lineman rows (pressures/sacks/hurries/hits, true-pass-set grade). `pressure_rate_allowed` is **ours** (pressures ÷ pass-block snaps), not PFF's proprietary PBE. |
| `GET /teams/{id}/offense/receiver-alignment` | Pass production by target alignment (targets, catch rate, EPA/target, aDOT, share). |
| `GET /teams/{id}/{offense\|defense}/absence?player_id=` | On/off unit splits, depth slot, next-man-up chosen by PFF slot-rate proximity, plus starter-vs-backup grade dropoff. **Correlational** — relay sample sizes. |
| `GET /tendencies/pass-rate?team_id=` | Team vs league pass rate per (quarter × score state), with deltas and sample sizes. Script priors. |

### NCAAF-only — `/api/ncaaf/*`

| Endpoint | AI context |
|---|---|
| `GET /rankings?poll=&season=&week=` | One poll, one week, in order, with `movement` against the previous week (positive = climbing). Defaults to the newest week of the AP Top 25. |
| `GET /coaches?q=` · `/coaches/{id}` | Coach search and **full career across every school** — the portable-signal view |
| `GET /teams/{id}/coaching` | Current coach, tenure, `arrived_this_season`, career residual |
| `GET /teams/{id}/context` | Returning production **with league percentile**, talent, recruiting, SP+, portal counts |
| `GET /teams/{id}/transfers` | Portal detail in/out with stars |

Team cards under `/api/ncaaf/` rank **within FBS (138)** — FCS crossover opponents
would otherwise pad the field to 237 and flatter every rank.

### Slate, matchups & odds — `/api/nfl/*` and `/api/ncaaf/*`

| Endpoint | AI context |
|---|---|
| `GET /teams` | Every team in the league, carrying its current poll `rank`. NCAAF defaults to FBS — the 105 FCS teams have no odds and no context rows. `ranked=true` returns only the Top 25. |
| `GET /games` | The slate. Filter by `season`/`week`/`status`/`team_id`, `upcoming=true`, or a `kickoff_from`/`kickoff_to` instant window. Each game carries teams, per-game conditions, the best book's current price line, and each side's **poll rank as of that game's week** — not today's poll, so a past result keeps the matchup it actually was. |
| `GET /games/{game_id}` | One matchup with every book that quotes it. |
| `GET /games/{game_id}/odds` | Full board plus the snapshot time series. `sections` splits the non-featured game-level markets into alternates, period markets and team totals; `prop_market_keys` counts the props without expanding them. |
| `GET /games/{game_id}/props` | Player props grouped by **subject** rather than by market — a prop board keyed by market makes you hunt one player across six tables. Over/under markets carry a line and two sides; anytime-touchdown carries only a price on "Yes", so shape follows market. `player_id` is null for D/ST entries, which keep `side_team_id` and are labelled rather than dropped. Books disagree on the line, so the line is part of the key: over 249.5 and over 264.5 are different bets. |

Outcome strings are resolved to a side through the **`cfbd_alias` crosswalk**, not by
comparing names: The Odds API writes `North Carolina Tar Heels` where `teams.name` is
`North Carolina`, and string equality silently drops every college spread and moneyline
while leaving Over/Under intact. An outcome that resolves to neither team is omitted
rather than guessed at.

`kickoff_from`/`kickoff_to` take ISO instants rather than a date, deliberately. "Games
from today" is a question about the *caller's* day, and a Saturday-night college kickoff
is already Sunday in UTC — so the client sends its own local midnight boundaries and the
server never has to guess at a timezone.

Books are split into **live** (`draftkings`, `fanduel`, `betmgm`, `caesars`, `pinnacle`)
and **archive** (everything else — seventeen bookmakers appear in `markets` and only
those five are current, so the split is an allowlist rather than a list of archives to
keep in sync).

**Whether an archive is shown depends on whether the game has been played.** Before
kickoff it would be masquerading as a price still available, so it is suppressed —
91 upcoming games carry both kinds and their boards were mixing closing lines in with
live quotes. After kickoff the closing line *is* the record, and for 11,340 completed
games it is the only price there is, so it shows. `include_archive` overrides the
default in either direction, and `archive_books` reports how many were suppressed so a
caller can tell "never priced" from "hidden".

### Live scoreboard — `/api/nfl/live` · `/api/ncaaf/live`

| Endpoint | AI context |
|---|---|
| `GET /live?date=YYYY-MM-DD` | Scores, game clock, down & distance, possession, last play, per-quarter linescores, and ESPN's game leaders. |

**The only surface here that is not database-backed.** In-game state has no home in our
schema — `games` stores a final score and a status, not a play clock — so this reads the
public scoreboard on request with a 12-second TTL. `fetched_at` and `age_seconds` ship in
every response, and a failed upstream call is a 502 rather than a silently re-served
stale payload.

Two things the ingest layer should not relearn the hard way:

- **Do not set a browser User-Agent.** The upstream WAF allows recognised programmatic
  clients (httpx's and curl's defaults both pass) and returns 403 for anything claiming
  to be a browser, because the TLS fingerprint contradicts the claim. Verified across
  Chrome 58, Chrome 124 and Safari 17 strings, and for an unrecognised custom agent.
- **`down: 0` and `down: -1` are sentinels**, not downs — a timeout, kickoff, or extra
  point. They are normalised to null so nothing renders "0th & 7".

Live events map onto canonical ids: NCAAF for free (our `ncaaf:<id>` *is* the ESPN event
id, and `ncaaf:24` is its team id), NFL by kickoff date plus both team abbreviations,
with `WSH`→`WAS` and `LAR`→`LA` the only two that disagree.

### Season scope — `offense` / `defense`

`scope=current` returns this season and **falls back to 2023–2025 when the team has not
played**, reporting `basis`, `games_played`, `current_season` and `fell_back` so the
caller always knows which it got. Week one is the case that matters: an empty card is
useless, and a silent substitution is worse. `scope` defaults to `explicit`, so existing
callers are unaffected.

The current season is read from the newest season in `games`, not from the calendar — a
date rule would encode where each league's year turns over and be wrong whenever a
schedule loads early.

### Coverage — `/api/football/*`

| Endpoint | AI context |
|---|---|
| `GET /coverage` | Row counts per table, counted live, plus the capability roster with `available: true/false`. The web app renders this verbatim; hard-coding the numbers anywhere would let them drift the moment an ingest runs. |

### Stubs awaiting Phases 1–3 (501 with phase marker)

`GET /odds` · `POST /sgp/generate` · `/sgp/build-around-pick` · `/sgp/test-hypothesis` · `/sgp/critique` · `/sgp/save` · `GET /sgp/history`

---

## 2.5 Web app (`apps/web`)

React + Vite, three runtime dependencies, served at `localhost:5173` in dev with `/api`
proxied to the engine. It is a view over the endpoints above and holds no second source
of truth: **every number on screen came from an engine response.**

| Surface | What it reads |
|---|---|
| Slate | `/{league}/games` grouped by day, with the best book's line |
| Matchup | game detail, both unit cards ranked in one field, full odds board with movement |
| Team | offense/defense cards, PFF unit grades, per-lineman protection, pass-rate heatmap; NCAAF swaps in coaching, returning production and portal |
| Player | seasons, game log, PFF split facets, opponent splits, QB clutch, linked college career |
| Compare | up to four teams as columns over the same ranked rows |
| Bet Lab | the four SGP modes, calling the real endpoints and rendering their 501 |
| Data | `/football/coverage`, verbatim |

**Vendor naming and the `detail` parameter.** The grading surfaces are labelled
**Analysis** and **Unit grades** in the UI, and no user-visible string names PFF. That part
is cosmetic. The substantive part is `detail=summary`, accepted by
`/teams/{id}/units`, `/teams/{id}/protection`, `/players/{id}/pff` and `/players/{id}`:
it returns rank, percentile, counted events, snaps and alignment rates, and **omits the
licensed grade and the raw export row**. `full` remains the default so the Phase-3
reasoning layer still weighs the real evaluation; the web client sends `summary` on every
call. `/players/{id}/pff` drops from 126 KB to 4 KB under it, and `/pff/splits` — which
returns export rows verbatim — is called by no UI surface.

Recorded plainly because it will come up again: de-branding is **not** a licensing
control. The risk in redistributing proprietary grades is the redistribution, and doing it
unattributed is generally treated worse rather than better. Reducing granularity is the
part that lowers exposure.

**The contract the UI inherits.** A 501 is not an error — it is typed separately from
failure and rendered as a phase gate, so an unbuilt surface says "Phase 1" rather than
showing a spinner or a plausible number. A null renders as an em dash, never zero,
because "not reported" and "zero" are different facts. Rank colour comes from exactly one
function, so a hue means the same thing on every surface. Cross-league comparison warns
that NCAAF's `epa` column holds CFBD's PPA.

Architecture, the rules the UI holds to, and the fixes made along the way: [FRONTEND.md](FRONTEND.md). Quick start: [apps/web/README.md](apps/web/README.md).

---

## 3. Ingest & jobs (Makefile)

| Command | What it does |
|---|---|
| `make up` / `down` / `health` / `psql` | Stack lifecycle (Postgres 16 + Redis + FastAPI engine). |
| `make ingest-nfl` | nflverse PBP 2023–2025, enriched, idempotent (re-run refreshes in place). |
| `make ingest-cfbd` | CFBD NCAAF games/plays/lines (`--season-type postseason --week 1` for bowls/CFP). |
| `make schedules` | 2026 schedules both leagues + CFBD team aliases. Required for odds resolution. |
| `make ingest-players` | Player master + rosters + espn/pfr/pff/name-alias xwalk rows. |
| `make ingest-snaps` | Snap counts + latest depth charts. |
| `make ingest-pff` | Parse PFF drops from `data/pff/` (CSV or harvested JSON). |
| `make ingest-fcs-coaches` | Seeded sub-FBS coaching stints from `data/seeds/`; records computed from CFBD FCS games. |
| `make ingest-cfbd-context` | NCAAF coaching, returning production, talent, SP+, recruiting, portal (2016–2026). Six CFBD calls per season, **one transaction per season** so a late failure can't discard finished ones. |
| `make poll-odds` | One odds pass, both leagues; resolves events, de-vigs inline. |
| `make devig` | Fill `fair_prob` where missing. `--rebuild` clears every value and recomputes — needed after any change to how a rung is grouped. |
| `make catchup` | One pass of the in-season chain below. `--rebuild` forces the derived layers when only their inputs moved. |
| `python -m youredge.ingest.player_stats --seasons …` | Game logs + QB/receiving NGS. |

### Staying current

Two long-running services, both under the `poller` compose profile:

```bash
docker compose --profile poller up -d poller results
```

`poller` snapshots odds. `results` runs `ingest/catchup.py` every 30 minutes:
schedules and results, then the polls, then play-by-play for weeks holding a
finished game with no plays, then the college play flags, then `success`, then
drives, and finally — only when something new landed — the derived layers
(features, game state, script labels, the leg ledger, the pair surface,
diagnoses).

Each fetch stage carries **its own** staleness test rather than riding on the
one above it. A drive fetch or a flag backfill can be behind while plays are
perfectly current, and a trigger that only watched for missing plays would
report everything up to date forever. Derivations are the exception and run
unconditionally: their `WHERE` clause already limits them to rows that need
work, so gating them buys nothing and is how they get missed.

Without this running, a finished Saturday still reads as unplayed, `scope=current`
correctly falls back to history, and every team card says the season has not
started.

**PFF refresh (in-season):** the facet API is reachable from a logged-in `premium.pff.com` tab; the harvester posts JSON to `/api/football/pff-drop`, files land in `data/pff/` named `<facet>_<season>[_wk<N>].json`, then `make ingest-pff`. PFF postseason weeks (28/29/30/32) map to canonical 19–22 automatically.

## 4. External sources

| Source | Auth | Used for | Cost |
|---|---|---|---|
| nflverse (nflreadpy) | none | NFL PBP, schedules, players, rosters, weekly stats, NGS, snaps, depth charts | Free |
| CFBD | `CFBD_API_KEY` | NCAAF games/plays/lines, schedules, team metadata | Free → $10/mo |
| The Odds API | `ODDS_API_KEY` | Live odds, 17 books, 39 market keys, both leagues | 20k credits/mo |
| PFF Premium | browser session | Grades, alignment %, coverage, protection, pressure splits | ~$40/mo |
| Anthropic | `ANTHROPIC_API_KEY` | Phase-3 Narrator/Planner | usage |

## 5. Caveats the AI layer must inherit

- **On/off is correlational.** Sample sizes ship with every response. Small `off` samples (stars rarely sit) and confounds (Jefferson's split blames him for 2023 QB chaos) mean deltas are evidence, not verdicts.
- **Unit cards are raw, not opponent-adjusted.** Honest at the top-5/bottom-5 grain; adjacent ranks are noise.
- **vs-opponent samples are tiny** — 5–6 games for divisional foes, 1–2 for everyone else. "He torches Miami" is usually a sampling story.
- **`ngs_position` is a label; PFF `slot_rate` is the real percentage.** Prefer the latter. Historical targets inherit a player's *current* NGS label.
- **`pressure_rate_allowed` is ours**, not PFF's Pass Blocking Efficiency.
- **NCAAF play-level player attribution is partial, not absent.** `/plays` omits player
  ids, but `/plays/stats` carries them, and `play_players` now holds 124,080 player-events
  resolved 100% to canonical ids (athlete ids are ESPN ids, the same space `players` uses
  for college). **Upstream coverage is SEC and ACC only — 790 of 2,761 games, 28.6%.**
  Every other FBS conference returns zero rows, consistently across 2023-25, and ESPN's
  own APIs carry no player participants on college plays either, so this is an upstream
  reality rather than a CFBD limitation.

  The remaining games are filled by parsing `plays.play_text`, written with
  `source = 'playtext'` so inference is always separable from feed. Total coverage is
  **2,759 of 2,761 games (99.9%)**. The parser is scored against the games where both
  exist before it writes — a fixed 60,000 plays: rusher 100.0% precision / 98.7%
  recall, receiver 99.8% / 99.0%, passer 99.9% / 99.6%, sacker 99.8% / 96.4%,
  interceptor 100.0% / 56.7%. Re-run `make validate-playtext` after any change.

  **Recall, not precision, is the limit here.** Sacks run roughly a quarter under the
  real totals and interceptions further, because the text frequently declines to name
  the defender ("pass intercepted, touchback"). A defensive event attributed here is
  almost always right; there are simply fewer of them than actually happened, so these
  columns support "did this player do it" far better than "how often".

  A caution about measuring this. An earlier harness scored sacker at 32% and
  interceptor at 34%, which was the harness being wrong rather than the parser: the
  feed records a quarterback's `Sack Taken` on 3,033 of 3,160 sacks but names the
  defender on only 2,295, so a correctly parsed sacker on one of the other 738 plays
  counted as a false positive. Feed silence is not disagreement, and a validation set
  drawn only from where labels exist will keep producing that class of error.

  Play-text formats differ by conference, and that is a trap worth knowing about: the
  first version of this parser was written and validated entirely on SEC/ACC text, so
  it never saw the NFL-style rows other conferences use ("No Huddle-Shotgun #24
  C.Hawkins rush middle for 1 yard gain") or the box-score form ("Trayvon Rudolph 60 Yd
  Run"). The box-score form is used disproportionately for *scoring* plays, so the gap
  did not lose yards at random — it lost touchdowns.

  **Target share is fixed for 2025 and still broken before it.** CFBD's `/passing/plays`
  endpoint carries `targetId` on 96% of completions and 89% of incompletions, against
  the ~9% recoverable from play text — 49,202 target rows for 2025 against roughly 1,500
  for each of 2023 and 2024. Use 2025 for anything that depends on target share; do not
  pool it with the earlier seasons, which will read as though nobody was thrown at.

  Air yards and yards after catch arrive on the same endpoint and are **season-partial
  in a way that matters**: zero through week 8 of 2025, then 91–99% from week 9 onward
  (41.4% and 25.6% for the season as a whole, nothing at all for 2023–24). Any aDOT or
  air-yards split must be filtered to week ≥ 9, or it silently describes half a season.

  Absence of a player on a play is never evidence he was uninvolved.
- **Scrambles count as runs** in pass-rate tendencies (nflverse convention); `qb_dropback` metrics don't have this issue.
- **PFF weeks are PFF's** — postseason numbering is remapped on ingest; don't compare raw week integers across sources.
- **Split facets have no top-level grade** by design; their data lives in prefixed columns via `/pff/splits`.
- **FCS coaching stints are hand-seeded** (`source='manual_fcs'`, `verified=false`) —
  no free API carries them, and ESPN's coach endpoint would have fabricated them by
  returning today's coach for historical years. Records are computed from CFBD FCS games;
  only the coach→school→years mapping is asserted.
- **FCS success stays a separate feature** — FCS has no SP+, so it is never blended into
  `career_sp_residual`. `seasons_of_history` counts FBS seasons only.
- **`career_sp_residual` uses a simplified talent baseline**; sound for ranking, not a
  calibrated projection.
- **Portal is NULL before 2021**, which is not the same as zero.
- **NCAAF player identity is partial.** Play-level ids come from CFBD for the SEC and ACC
  and from play-text parsing elsewhere; no usage shares yet (Phase 2). College props are
  now requested for every game, but books post far fewer of them than for the NFL, and
  what they post appears close to kickoff.
- **Injuries gate, never narrate.**

## 6. What's next

Phase 1 remainder: more tendency surfaces (pace, plays-per-state, red zone, fatigue) → **drive-level Monte Carlo sim** → **calibration backtest** vs 2023–25 closing lines. Phase 2: correlation from the sim, SGP pricing vs book quotes, leg diagnostics. Phase 3: the four modes as LLM tool-use.

**NCAAF Phase 2 (planned):** college player identity from CFBD rosters (ESPN athlete ids + jersey), player props (confirmed live — 5–6 books on a mid-tier game, anytime TD densest), and PFF college (`league=ncaa`, needs a `franchise_id`-keyed team crosswalk because PFF's college team names are truncated). **Phase 3:** learned weighting of coaching vs continuity, fit from data rather than asserted.

**Available now but unbuilt:** template definitions as predicates over the unit/trait data, retro-labeling all 4,777 games into `taggings`, and per-template base rates + CLV records — which fills the two empty tables the architecture already anticipates and gives Mode 3 an honest, sim-free answer before Phase 1 lands.

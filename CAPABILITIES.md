# YourEdge — Data & Capability Reference

*As of 2026-08-18. The audience for this doc is both humans and the Phase-3 LLM layer:
every table and endpoint below is a tool the Narrator/Planner can query, and the "AI
context" notes say when it should reach for each one. The core contract holds
everywhere: **the Engine computes every number; the LLM selects and explains.***

---

## 1. Database tables

### Reference & identity

| Table | Rows | What it is |
|---|---|---|
| `teams` | 280 | Canonical teams, both leagues. `team_id` like `nfl:BAL`, `ncaaf:59`. Real names ("Baltimore Ravens"). |
| `players` | 4,618 | NFL players active 2023+ plus all current-season roster players. `player_id` = `nfl:<gsis_id>`. Carries `position`, current `team_id`, and `ngs_position` — NGS's tracking-derived primary alignment (`SLOT_WR`, `SLOT_CB`, `HIGH_SAFETY`). |
| `entity_xwalk` | 21,370 | The translation table between external ID systems and canonical IDs. Sources: `cfbd` (game/team ids), `odds_api` (event ids, cached resolutions), `cfbd_alias` + `nflverse_alias` (normalized name aliases), `espn` + `pfr` (player id dialects). |

**AI context:** the LLM never invents an identifier. User says "Lamar" → `/players?q=` (backed by the alias xwalk) → canonical id → every other surface keys off it. When a new odds feed or live-score source appears, it becomes a new `source` here and nothing downstream changes. If the crosswalk can't resolve something, the honest answer is "we can't link this," never a guess.

### Games & play-by-play

| Table | Rows | What it is |
|---|---|---|
| `games` | 4,777 | Both leagues, 2023–2025 complete (incl. playoffs/CFP) plus full 2026 schedules. `season_type` separates postseason (CFBD files its whole postseason under week 1); `notes` names bowls/CFP rounds (filter `ILIKE 'CFP%' OR ILIKE 'College Football Playoff%'`). |
| `plays` | 635,436 | The modeling foundation. NFL rows are enriched: `epa`, `wpa`, `success`, `complete_pass`, `interception`, `touchdown`, `air_yards`, `yards_after_catch`, `qb_dropback`, `qb_scramble`, `pass_location`, `run_location`, `field_goal_result`, score state, clock. NCAAF rows carry `ppa` (CFBD's EPA analog — different scale, never mix leagues in one aggregate) and no per-play player ids yet. |

**AI context:** every tendency, clutch metric, script prior, and (soon) sim input is computed **from** this table — the LLM should never quote a stat that doesn't trace here or to an official aggregate. For hypothesis testing (Mode 3), this is where claims get checked: "does NY's run defense actually fade in Q4?" is a query over `plays`, not an opinion.

### Odds

| Table | Rows | What it is |
|---|---|---|
| `markets` | 23,329 | A book's priced question per game: `(game_id, bookmaker, market_key, player_id)`. Books: DK/FD/MGM/Caesars/Pinnacle live via The Odds API; `cfbd:*` historical closing lines. |
| `odds_snapshots` | 53,726 | Time series of prices per market outcome. `implied_prob` (with vig) **and** `fair_prob` (de-vigged, filled automatically) — 2023–25 NCAAF closing lines + 2026 openers, growing every poll. Unique on `(market_id, captured_at, outcome)` so re-ingests can't duplicate. |

**AI context:** the twin columns are the point. Edge = model probability − `fair_prob`, never − `implied_prob` (that overstates edge by the vig). Snapshot history = line movement, which is CLV's raw material and a narratable fact ("this spread moved 6.5 → 4.5 since July"). All current odds events resolve to canonical games (100% both leagues), so odds join cleanly to everything else.

### Player performance

| Table | Rows | What it is |
|---|---|---|
| `player_game_stats` | 56,982 | Weekly game logs 2023–2025 from nflverse official stats. Typed: attempts/completions/yards/TDs/INTs/sacks, `passing_epa`, `passing_cpoe`, carries, targets/receptions, `target_share`, `air_yards_share`, `wopr`. **Full source row in `stats` JSONB** — including all `def_*` box stats — so nothing is lost. Every row linked to its canonical `game_id`. |
| `qb_ngs_weekly` | 1,839 | Next Gen Stats passing: `avg_time_to_throw`, `avg_intended_air_yards`, `aggressiveness`, CPOE, passer rating. Week 0 = season aggregate. |
| `ngs_receiving_weekly` | 4,310 | NGS receiving: `avg_cushion`, `avg_separation`, aDOT, share of intended air yards, catch %, YAC over expected. Cushion/separation are alignment-diagnostic. |
| `snap_counts` | 79,649 | Per player per game: offense/defense/ST snaps and %, plus `team_id` (players move). The availability record behind on/off analysis. |
| `depth_chart` | 3,208 | Latest snapshot (refreshed per ingest, `as_of` stamped). `pos_rank` 1 = starter. Defense has an explicit `NB` (nickel/slot) slot. |
| `pff_player_stats` | 0 (scaffold ready) | PFF Premium CSV drops: typed `slot_rate`/`snaps`/`grade` + full row JSONB. Unlocks OL/DL measurement, true alignment %, coverage-allowed stats, QB pressure splits. |

**AI context:** game logs answer "how has X actually performed" with official numbers — quote these, not sums over play-by-play (which drop official scoring nuances). Target share + air-yards share are the prop layer's usage inputs: sim team volume × player share = prop distribution. QB traits let the Narrator characterize *style* ("quick-release, low aDOT") with tracking data instead of vibes. Snap counts + depth chart power "who plays, who's next" — and injury gating is a suppress/flag rule, never speculation.

### Tagging & memory (Phase 3 surfaces, schema live now)

| Table | Rows | What it is |
|---|---|---|
| `tags` | 33 | The controlled vocabulary: script tags (`SHOOTOUT`, `GARBAGE_TIME_PASS`…), leg roles (`ANCHOR`, `REDUNDANT`…), angles (`Q4`, `HOME_DOG`…), outcomes (`PROCESS_WIN`, `VARIANCE_LOSS`…). |
| `taggings` | 0 yet | Polymorphic: anything (game, leg, bet, angle, debrief) can carry tags with weights. `game_scripts` view = top script tags per game ranked by sim probability. |
| `user_bets` | 0 yet | Every bet through BetLab: legs, price at rec time, engine's fair prob, closing price (CLV), result. Bettor Memory's substrate. |

**AI context:** this is the shared language between LLM and Engine. The LLM **selects from** `tags` at runtime — never invents one mid-conversation. A parsed hypothesis becomes a Script Spec in these tags; the engine answers in the same vocabulary; debriefs and coaching join on them ("you're 1–7 on SHOOTOUT scripts").

---

## 2. API endpoints (`http://localhost:8000`, interactive docs at `/docs`)

### Live now

| Endpoint | Returns | AI context — when to reach for it |
|---|---|---|
| `GET /api/football/health` | status + db check | Preflight. |
| `GET /api/football/tendencies/pass-rate?team_id=` | Team vs league pass rate per (quarter × score state) cell, with deltas and sample sizes | Script priors: "BAL goes run-heavy protecting leads (−10pp vs league)" grounds a `CLOCK_KILL` lean. Respect `team_plays` before trusting a cell. |
| `GET /api/football/players?q=` | Name search, alias-normalized (`tj watt` → T.J. Watt) | Entity resolution for any user mention of a player. |
| `GET /api/football/players/{id}` | Bio + per-season aggregates (+ NGS traits for QBs) | The "who is this player" card; official season numbers to quote. |
| `GET /api/football/players/{id}/gamelog` | Weekly rows, each tied to a canonical game | Recent form, consistency vs volatility for prop framing ("cleared 250.5 in 9 of 17"). |
| `GET /api/football/players/{id}/plays` | Enriched play log with role, EPA, WPA, air yards | Drill-down evidence: the actual plays behind a claim. |
| `GET /api/football/players/{id}/clutch` | QB-only: late&close EPA/dropback vs own baseline & league, two-minute drill, clutch-drive score rate, `small_sample` flag | Crunch-time framing with honest baselines: league QBs collapse to 0.018 EPA/dropback late-and-close; a QB holding 0.11 is a real signal — **if** the flag says the sample is real. |
| `GET /api/football/teams/{id}/offense` | Unit card: pass/run EPA, success, explosive, INT rate, red-zone TD rate, late&close — all with league ranks | Matchup table-setting ("4th pass offense vs 26th late-game defense") and sim priors. |
| `GET /api/football/teams/{id}/defense` | Mirror card, allowed side | Same, defensive side. Splits like "elite early, 26th in late&close EPA allowed" motivate `BACKDOOR` scripts. |
| `GET /api/football/teams/{id}/offense/receiver-alignment` | Pass production by target's alignment label (targets, catch rate, EPA/target, aDOT, target share) | Where a passing game lives (slot vs outside vs TE) — feeds matchup logic once coverage data lands. |
| `GET /api/football/teams/{id}/{offense\|defense}/absence?player_id=` | On/off splits (unit EPA with vs without the player), depth slot, next-man-up with production profile | The injury-impact story: "PIT allows +0.116 EPA/dropback without Watt; Herbig steps in (16 sacks, 44% snap share)." **Correlational** — always relay the sample sizes; distrust confounded cases (see Jefferson caveat below). |

### Stubs awaiting Phases 1–3 (return 501 with phase marker)

`GET /odds` · `POST /sgp/generate` · `/sgp/build-around-pick` · `/sgp/test-hypothesis` · `/sgp/critique` · `/sgp/save` · `GET /sgp/history` — the four BetLab modes; thin LLM layers over the sim + pricing engine once Phases 1–2 land.

---

## 3. Ingest & jobs (Makefile)

| Command | What it does |
|---|---|
| `make up` / `make down` / `make health` / `make psql` | Stack lifecycle (Postgres 16 + Redis + FastAPI engine). |
| `make ingest-nfl` | nflverse PBP 2023–2025, enriched columns, idempotent (re-run refreshes in place). |
| `make ingest-cfbd` | CFBD NCAAF games/plays/lines via canonical mapping (`--season-type postseason --week 1` for bowls/CFP). |
| `make schedules` | 2026 schedules both leagues + CFBD team alias table. Required for odds event resolution. |
| `make ingest-players` | Player master + current rosters + espn/pfr/name-alias xwalk rows. |
| `make ingest-snaps` | Snap counts 2023–2025 + latest depth charts. |
| `make poll-odds` | One odds snapshot pass, 5 books, both leagues; resolves events, de-vigs inline. Loop mode for the 30-min pregame cadence. |
| `make devig` | Backfill `fair_prob` on any snapshot group missing it. |
| `make ingest-pff` | Parse PFF CSV drops from `data/pff/` (see §4). |
| `python -m youredge.ingest.player_stats --seasons …` | Game logs + QB/receiving NGS. |

## 4. External sources & credentials

| Source | Auth | Used for | Cost |
|---|---|---|---|
| nflverse (nflreadpy) | none | NFL PBP, schedules, players, rosters, weekly stats, NGS, snap counts, depth charts | Free |
| CFBD | `CFBD_API_KEY` | NCAAF games/plays/lines, schedules, team metadata (1k calls/mo free; each week = 3 calls) | Free → $10/mo |
| The Odds API | `ODDS_API_KEY` | Live odds 5 books, both leagues (~20k credits/mo remaining) | Dev tier now |
| PFF (planned) | manual CSV export, PFF+ sub | OL/DL grades, true slot %, coverage-allowed, pressure splits | ~$40/mo |
| Anthropic | `ANTHROPIC_API_KEY` | Phase-3 Narrator/Planner | usage |

## 5. Honest caveats the AI layer must inherit

- **On/off is correlational.** Sample sizes ship with every response; small `off` samples (stars rarely sit) and confounds (Jefferson's split blames him for 2023 QB chaos) mean the Narrator should present deltas as evidence, not verdicts.
- **Unit cards are raw, not opponent-adjusted.** Rankings are honest at the "top-5 / bottom-5" grain; adjacent ranks are noise. Opponent adjustment is a Phase-2 refinement.
- **`ngs_position` is a primary-alignment label, not a % —** and historical targets inherit a player's *current* label. True per-snap alignment needs the PFF feed.
- **NCAAF plays have no player ids yet** (CFBD REST omits them) — NCAAF is game-markets-first, per roadmap.
- **Scrambles count as runs** in pass-rate tendencies (nflverse convention); dropback-based metrics use `qb_dropback` and don't have this issue.
- **Clutch-drive scoring** can miscount a rare fumble-return TD as drive success until a drive-outcome column exists.
- **Injuries gate, never narrate:** the engine suppresses/flags legs on injury status; the LLM must not speculate about injuries.

## 6. What's next (the gap between here and BetLab)

Phase 1 remainder: more tendency surfaces (pace, plays-per-state, red zone, fatigue) → **drive-level Monte Carlo sim** (team tendencies + market-implied strength → joint distributions) → **calibration backtest** vs 2023–25 closing lines. Phase 2: correlation from the sim, SGP pricing vs book quotes, leg diagnostics. Phase 3: the four modes as LLM tool-use over `get_game_data` / `run_simulation` / `price_legs` / `evaluate_parlay` / `find_legs_matching_script`.

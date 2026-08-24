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
| `teams` | 285 | Canonical teams, both leagues. `team_id` like `nfl:BAL`, `ncaaf:59`. `classification` marks FBS (138) vs FCS (105) for NCAAF. |
| `players` | 49,426 | NFL (4,619) `nfl:<gsis_id>` + NCAAF (44,807) `ncaaf:<espn_athlete_id>`, the id space CFBD's roster and stats endpoints share. `jersey`/`class_year` carried for college as match validators. Carries `position`, `team_id`, and `ngs_position` (NGS tracking-derived alignment: `SLOT_WR`, `SLOT_CB`, `HIGH_SAFETY`). |
| `entity_xwalk` | 128,444 | Translation between external ID systems and canonical IDs. Sources: `cfbd`, `odds_api`, `cfbd_alias`/`nflverse_alias`/`ncaaf_alias`/`ncaaf_alias_team` (normalized names), `espn`, `pfr`, `pff`. College aliases dominate the count: ~22k players/season need team-scoped keys. |

**AI context:** never invent an identifier. "Lamar" → `/players?q=` → canonical id → every other surface keys off it. Player IDs resolve *exactly* via `pff`/`espn` crosswalk rows, which is what keeps QB Josh Allen distinct from the Jaguars linebacker. If the crosswalk can't resolve something, the answer is "we can't link this," never a guess.

### Games & play-by-play

| Table | Rows | What it is |
|---|---|---|
| `games` | 10,647 | NFL 2023–2026; **NCAAF 2016–2026** (labels backfilled for training). Complete incl. playoffs/CFP. `season_type` separates postseason; `notes` names bowls/CFP rounds (filter `ILIKE 'CFP%' OR ILIKE 'College Football Playoff%'`). |
| `plays` | 635,436 | The modeling foundation. NFL rows (148k) enriched: `epa`, `wpa`, `success`, `complete_pass`, `interception`, `touchdown`, `air_yards`, `yards_after_catch`, `qb_dropback`, `qb_scramble`, `pass_location`, `run_location`, `field_goal_result`, score state, clock. NCAAF rows (488k) carry `ppa` in the `epa` column (CFBD's analog — different scale, **never mix leagues in one aggregate**) and `success` backfilled as `epa > 0`; `qb_dropback`/`touchdown` are nflverse-only and stay NULL. |

**AI context:** every tendency, clutch metric, and script prior computes **from** this table — never quote a stat that doesn't trace here or to an official aggregate. Mode 3 hypothesis testing ("does NY's run defense fade in Q4?") is a query over `plays`, not an opinion.

### Odds

| Table | Rows | What it is |
|---|---|---|
| `markets` | 23,329 | A book's priced question per game: `(game_id, bookmaker, market_key, player_id)`. DK/FD/MGM/Caesars/Pinnacle live; `cfbd:*` historical closing lines. |
| `odds_snapshots` | 53,726 | Price time series. `implied_prob` (with vig) **and** `fair_prob` (de-vigged automatically). Unique on `(market_id, captured_at, outcome)` so re-ingests can't duplicate. |

**AI context:** the twin columns are the point. Edge = model probability − `fair_prob`, never − `implied_prob` (that overstates edge by the vig). Snapshot history = line movement, which is CLV's raw material and a narratable fact. All odds events resolve to canonical games (100% both leagues).

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
**Weather is NFL-only**: nflverse reports temp/wind (530 outdoor games), CFBD's weather
endpoint is paywalled. A NULL `temp` means *not available* — never "indoors" or "calm".

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
| `GET /coaches?q=` · `/coaches/{id}` | Coach search and **full career across every school** — the portable-signal view |
| `GET /teams/{id}/coaching` | Current coach, tenure, `arrived_this_season`, career residual |
| `GET /teams/{id}/context` | Returning production **with league percentile**, talent, recruiting, SP+, portal counts |
| `GET /teams/{id}/transfers` | Portal detail in/out with stars |

Team cards under `/api/ncaaf/` rank **within FBS (138)** — FCS crossover opponents
would otherwise pad the field to 237 and flatter every rank.

### Stubs awaiting Phases 1–3 (501 with phase marker)

`GET /odds` · `POST /sgp/generate` · `/sgp/build-around-pick` · `/sgp/test-hypothesis` · `/sgp/critique` · `/sgp/save` · `GET /sgp/history`

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
| `make poll-odds` | One odds pass, 5 books, both leagues; resolves events, de-vigs inline. |
| `make devig` | Backfill `fair_prob` on any snapshot group missing it. |
| `python -m youredge.ingest.player_stats --seasons …` | Game logs + QB/receiving NGS. |

**PFF refresh (in-season):** the facet API is reachable from a logged-in `premium.pff.com` tab; the harvester posts JSON to `/api/football/pff-drop`, files land in `data/pff/` named `<facet>_<season>[_wk<N>].json`, then `make ingest-pff`. PFF postseason weeks (28/29/30/32) map to canonical 19–22 automatically.

## 4. External sources

| Source | Auth | Used for | Cost |
|---|---|---|---|
| nflverse (nflreadpy) | none | NFL PBP, schedules, players, rosters, weekly stats, NGS, snaps, depth charts | Free |
| CFBD | `CFBD_API_KEY` | NCAAF games/plays/lines, schedules, team metadata | Free → $10/mo |
| The Odds API | `ODDS_API_KEY` | Live odds, 5 books, both leagues | Dev tier |
| PFF Premium | browser session | Grades, alignment %, coverage, protection, pressure splits | ~$40/mo |
| Anthropic | `ANTHROPIC_API_KEY` | Phase-3 Narrator/Planner | usage |

## 5. Caveats the AI layer must inherit

- **On/off is correlational.** Sample sizes ship with every response. Small `off` samples (stars rarely sit) and confounds (Jefferson's split blames him for 2023 QB chaos) mean deltas are evidence, not verdicts.
- **Unit cards are raw, not opponent-adjusted.** Honest at the top-5/bottom-5 grain; adjacent ranks are noise.
- **vs-opponent samples are tiny** — 5–6 games for divisional foes, 1–2 for everyone else. "He torches Miami" is usually a sampling story.
- **`ngs_position` is a label; PFF `slot_rate` is the real percentage.** Prefer the latter. Historical targets inherit a player's *current* NGS label.
- **`pressure_rate_allowed` is ours**, not PFF's Pass Blocking Efficiency.
- **NCAAF plays have no player ids** (CFBD REST omits them) — NCAAF is game-markets-first.
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
- **NCAAF has no player identity yet** — no props, no player game logs, no usage shares
  (Phase 2). `rz_td_rate` is NULL for NCAAF because `touchdown` is nflverse-only.
- **Injuries gate, never narrate.**

## 6. What's next

Phase 1 remainder: more tendency surfaces (pace, plays-per-state, red zone, fatigue) → **drive-level Monte Carlo sim** → **calibration backtest** vs 2023–25 closing lines. Phase 2: correlation from the sim, SGP pricing vs book quotes, leg diagnostics. Phase 3: the four modes as LLM tool-use.

**NCAAF Phase 2 (planned):** college player identity from CFBD rosters (ESPN athlete ids + jersey), player props (confirmed live — 5–6 books on a mid-tier game, anytime TD densest), and PFF college (`league=ncaa`, needs a `franchise_id`-keyed team crosswalk because PFF's college team names are truncated). **Phase 3:** learned weighting of coaching vs continuity, fit from data rather than asserted.

**Available now but unbuilt:** template definitions as predicates over the unit/trait data, retro-labeling all 4,777 games into `taggings`, and per-template base rates + CLV records — which fills the two empty tables the architecture already anticipates and gives Mode 3 an honest, sim-free answer before Phase 1 lands.

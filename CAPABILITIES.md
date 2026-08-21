# YourEdge — Data & Capability Reference

*Updated 2026-08-21. Written for humans and for the Phase-3 LLM layer: every table
and endpoint below is a tool the Narrator/Planner can query, and the "AI context"
notes say when to reach for each. The core contract holds everywhere: **the Engine
computes every number; the LLM selects and explains.***

---

## 1. Database tables

### Reference & identity

| Table | Rows | What it is |
|---|---|---|
| `teams` | 280 | Canonical teams, both leagues. `team_id` like `nfl:BAL`, `ncaaf:59`. |
| `players` | 4,619 | NFL players active 2023+ plus current rosters. `player_id` = `nfl:<gsis_id>`. Carries `position`, `team_id`, and `ngs_position` (NGS tracking-derived alignment: `SLOT_WR`, `SLOT_CB`, `HIGH_SAFETY`). |
| `entity_xwalk` | 25,780 | Translation between external ID systems and canonical IDs. Sources: `cfbd`, `odds_api`, `cfbd_alias`/`nflverse_alias` (normalized names), `espn`, `pfr`, `pff`. |

**AI context:** never invent an identifier. "Lamar" → `/players?q=` → canonical id → every other surface keys off it. Player IDs resolve *exactly* via `pff`/`espn` crosswalk rows, which is what keeps QB Josh Allen distinct from the Jaguars linebacker. If the crosswalk can't resolve something, the answer is "we can't link this," never a guess.

### Games & play-by-play

| Table | Rows | What it is |
|---|---|---|
| `games` | 4,777 | Both leagues, 2023–2025 complete (incl. playoffs/CFP) plus 2026 schedules. `season_type` separates postseason; `notes` names bowls/CFP rounds (filter `ILIKE 'CFP%' OR ILIKE 'College Football Playoff%'`). |
| `plays` | 635,436 | The modeling foundation. NFL rows enriched: `epa`, `wpa`, `success`, `complete_pass`, `interception`, `touchdown`, `air_yards`, `yards_after_catch`, `qb_dropback`, `qb_scramble`, `pass_location`, `run_location`, `field_goal_result`, score state, clock. NCAAF rows carry `ppa` (CFBD's EPA analog — different scale, never mix leagues in one aggregate). |

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
| `player_game_stats` | 56,982 | Weekly game logs 2023–2025. Typed: attempts/completions/yards/TDs/INTs/sacks, `passing_epa`, `passing_cpoe`, carries, targets, `target_share`, `air_yards_share`, `wopr`. Full source row in `stats` JSONB (incl. all `def_*` box stats). Every row linked to canonical `game_id`, and carries `opponent_team_id`. |
| `qb_ngs_weekly` | 1,839 | Next Gen Stats passing: time-to-throw, intended air yards, aggressiveness, CPOE. Week 0 = season aggregate. |
| `ngs_receiving_weekly` | 4,310 | NGS receiving: cushion, separation, aDOT, air-yards share, YAC over expected. |
| `snap_counts` | 79,649 | Per player per game: offense/defense/ST snaps and %, plus `team_id`. The availability record behind on/off analysis. |
| `depth_chart` | 3,208 | Latest snapshot (`as_of` stamped). `pos_rank` 1 = starter. Defense has an explicit `NB` (nickel/slot) slot. |
| `pff_player_stats` | **359,513** | 22 PFF facets × 2023–2025 × season + every week (incl. playoffs). Typed: `snaps`, `slot_rate`, `wide_rate`, `inline_rate`, `routes`, `yprr`, `grade`. Complete export row in `stats` JSONB with a GIN index. Weekly rows carry `game_id` — **100% linked**. |

**AI context:** game logs answer "how has X performed" with official numbers — quote these, not sums over play-by-play. Target share + air-yards share are the prop layer's usage inputs. PFF is the layer free data can't reach: true alignment percentages, offensive-line measurement, coverage-allowed stats, and pressure splits. Snap counts + depth chart power "who plays, who's next"; injuries gate recommendations, they are never speculated about.

**PFF facets loaded:** `passing`, `passing_depth`, `passing_pressure`, `passing_concept`, `time_in_pocket`, `allowed_pressure`, `receiving`, `receiving_depth`, `receiving_concept`, `receiving_scheme`, `rushing`, `blocking`, `pass_blocking`, `run_blocking`, `defense`, `pass_rush`, `run_defense`, `coverage`, `coverage_scheme`, `slot_coverage`, `prp`, `field_goals`.

### Tagging & memory (Phase 3 surfaces, schema live)

| Table | Rows | What it is |
|---|---|---|
| `tags` | 33 | Controlled vocabulary: script tags (`SHOOTOUT`, `GARBAGE_TIME_PASS`…), leg roles (`ANCHOR`, `REDUNDANT`…), angles (`Q4`, `HOME_DOG`…), outcomes (`PROCESS_WIN`, `VARIANCE_LOSS`…). |
| `taggings` | 0 yet | Polymorphic: anything taggable with weights. `game_scripts` view = top script tags per game. |
| `user_bets` | 0 yet | Every BetLab bet: legs, price at rec time, fair prob, closing price (CLV), result. |

**AI context:** the shared language between LLM and Engine. The LLM **selects from** `tags` at runtime — never invents one mid-conversation. Parsed hypotheses become Script Specs in these tags; debriefs and coaching join on them.

---

## 2. API endpoints (`localhost:8000`, interactive docs at `/docs`)

All prefixed `/api/football`.

### Players

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

### Teams

| Endpoint | AI context |
|---|---|
| `GET /teams/{id}/offense` · `/defense` | Unit cards: pass/run EPA, success, explosive, INT rate, red-zone TD rate, late&close — with league ranks. Matchup table-setting and sim priors. |
| `GET /teams/{id}/units` | **PFF unit grades** (snap-weighted + rank): pass/run blocking, pass rush, run defense, coverage, receiving, rushing. Pass protection has no free-data equivalent. |
| `GET /teams/{id}/protection` | Unit pressure rate allowed + per-lineman rows (pressures/sacks/hurries/hits, true-pass-set grade). `pressure_rate_allowed` is **ours** (pressures ÷ pass-block snaps), not PFF's proprietary PBE. |
| `GET /teams/{id}/offense/receiver-alignment` | Pass production by target alignment (targets, catch rate, EPA/target, aDOT, share). |
| `GET /teams/{id}/{offense\|defense}/absence?player_id=` | On/off unit splits, depth slot, next-man-up chosen by PFF slot-rate proximity, plus starter-vs-backup grade dropoff. **Correlational** — relay sample sizes. |
| `GET /tendencies/pass-rate?team_id=` | Team vs league pass rate per (quarter × score state), with deltas and sample sizes. Script priors. |

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
- **Injuries gate, never narrate.**

## 6. What's next

Phase 1 remainder: more tendency surfaces (pace, plays-per-state, red zone, fatigue) → **drive-level Monte Carlo sim** → **calibration backtest** vs 2023–25 closing lines. Phase 2: correlation from the sim, SGP pricing vs book quotes, leg diagnostics. Phase 3: the four modes as LLM tool-use.

**Available now but unbuilt:** template definitions as predicates over the unit/trait data, retro-labeling all 4,777 games into `taggings`, and per-template base rates + CLV records — which fills the two empty tables the architecture already anticipates and gives Mode 3 an honest, sim-free answer before Phase 1 lands.

# YourEdge — NCAAF Data Reference

*Updated 2026-08-23. Companion to [CAPABILITIES.md](CAPABILITIES.md), which covers the
whole system. This file is the college-specific view: what's loaded, why it's shaped
this way, and what it can and cannot answer.*

---

## The thesis this data serves

College football is not a player-stats sport the way the NFL is. The transfer portal
churns rosters every year, so last season's player grades travel poorly. The predictive
signal sits in two places the NFL barely varies on:

**Roster experience.** Returning production in 2025 ranged from Navy at **97.3%** to
New Mexico at **2.8%** — a 35x spread. NFL roster continuity varies maybe 60–90%.

**Coaching, tracked by coach and not by school.** The signal moves with the person. A
team-keyed model looking at Indiana before 2024 says "they've been bad, bet them bad."
A coach-keyed model sees Curt Cignetti arriving with two years of beating his talent at
James Madison:

| Season | School | Record | SP+ | Tenure | Arrived | Career SP+ residual |
|---|---|---|---|---|---|---|
| 2019–21 | James Madison *(FCS)* | **33-5** | — | | | seeded |
| 2022 | James Madison | 8-3 | 6.5 | 1 | ✓ | — |
| 2023 | James Madison | 11-1 | 11.8 | 2 | | — |
| 2024 | **Indiana** | 11-2 | 20.1 | 1 | ✓ | **+27.1** |
| 2025 | Indiana | 16-0 | 32.4 | 2 | | +22.6 |
| 2026 | Indiana | — | 25.8 | 3 | | +25.8 |

The market had Indiana's 2024 win total near 3.5–4.5. They won 11. The signal was
visible beforehand in data we now store.

---

## What's loaded

| Table | Rows | Coverage | Notes |
|---|---|---|---|
| `teams` (ncaaf) | **138 FBS** | current | `classification` also marks 105 FCS + 1 D-III; context layer is FBS-only |
| `games` (ncaaf) | 9,400+ | **2016–2026** | incl. bowls/CFP; `notes` names the round; `venue_id`/`neutral_site` attached |
| `plays` (ncaaf) | 487,508 | 2023–2025 | `epa` holds CFBD's PPA; `success` backfilled as `epa > 0` |
| `coaches` | 374 | 2016–2026 | `history_seasons` = FBS seasons visible |
| `coach_seasons` | 1,583 | 2016–2026 | PK `(coach_id, team_id, season)` — **a coach changing schools is a new row, not a new coach** |
| `coach_features` | 1,581 | 2016–2026 | the portable signal, computed from all prior seasons anywhere |
| `team_season_context` | 1,434 | 2016–2026 | returning production, talent, recruiting, SP+, portal |
| `transfers` | 23,358 | **2021–2026** | portal detail; CFBD has nothing before 2021 |
| `odds_snapshots` (ncaaf) | ~120k | **2016–2026** | historical closing lines + live 2026 openers |
| `players` (ncaaf) | 40,602 | 2023–2026 | `ncaaf:<espn_athlete_id>`, with jersey + class year |
| `player_game_stats` (ncaaf) | 107k+ | 2023–2025 | from `/games/players`; no targets/air-yards/EPA (CFBD doesn't report them) |
| `venues` (ncaaf) | 852 | current | incl. **elevation** — Laramie 2,200m |

### `coach_features` — the portable signal

Computed per `(coach_id, season, team_id)` from **all prior seasons at any school**:

| Field | Meaning |
|---|---|
| `career_sp_residual` | Mean SP+ minus what that roster's talent predicted. "Does he beat his roster?" |
| `career_sp_mean` | Raw mean SP+, for context |
| `prior_school_trajectory` | Slope of SP+ across prior seasons — improving or fading |
| `seasons_of_history` | How much evidence exists. **Low means uncertain, not average.** |
| `arrived_this_season` | First year at this school — the Cignetti trigger |
| `fcs_seasons` / `fcs_wins` / `fcs_losses` / `fcs_win_pct` | Sub-FBS record, kept **separate** from the SP+ residual because FCS has no SP+ and the scales aren't comparable |

### `team_season_context` — roster experience and talent

Returning production (`pct_ppa` plus passing/rushing/receiving splits and `usage`
splits), `talent` composite, `recruiting_rank`/`points`, SP+ overall/offense/defense, and
`portal_in`/`portal_out` with star averages.

**`portal_*` is NULL before 2021, never 0** — CFBD has no portal data that far back, and
"we don't know" must not read as "nobody transferred."

---

## Endpoints (`/api/ncaaf/*`)

| Endpoint | Returns |
|---|---|
| `GET /coaches?q=` | Coach search by name |
| `GET /coaches/{coach_id}` | Full career across every school, with residual and trajectory per season |
| `GET /teams/{id}/coaching` | Current coach, tenure, whether they just arrived, career residual |
| `GET /teams/{id}/context` | Returning production + **league percentile**, talent, recruiting, SP+, portal counts |
| `GET /teams/{id}/transfers` | Portal detail in/out with positions and stars |
| `GET /teams/{id}/offense` · `/defense` | Unit cards ranked **within FBS** (138 teams) |
| `GET /tendencies/pass-rate?team_id=` | Pass rate by quarter × score state vs league |

Sample:

```bash
curl -s "http://localhost:8000/api/ncaaf/coaches?q=cignetti"
curl -s "http://localhost:8000/api/ncaaf/coaches/cfbd_coach:1741"
curl -s "http://localhost:8000/api/ncaaf/teams/ncaaf:84/context?season=2026"
curl -s "http://localhost:8000/api/ncaaf/teams/ncaaf:84/offense"
```

**Path discipline:** canonical IDs carry their league, so `/api/nfl/teams/ncaaf:59`
returns **400**, not an empty result. The two mean different things and the API says so.

---

## Ingest

```bash
make ingest-cfbd-context     # coaches, returning production, talent, SP+, recruiting, portal
make ingest-cfbd             # games, plays, historical lines
```

Six CFBD calls per season. **One transaction per season** — a long backfill must not
discard finished seasons because a later one fails. Re-runs are idempotent.

Rate limiting: firing 11 seasons back-to-back tripped CFBD's limiter mid-run. The
per-season transaction boundary means you simply re-run the failed seasons.

---

## What this data can answer today

- *"Which 2026 coaching hires have actually beaten their talent elsewhere?"* — Chesney to
  UCLA (+18.3 over two seasons), Whittingham to Michigan, Sumrall to Florida
- *"Who returns the most production, and where does that rank?"* — with league percentile
- *"How much did this roster churn?"* — portal in/out with star quality
- *"Is this offense actually good, or good against bad teams?"* — FBS-only unit ranks
- *"Does this team go conservative protecting a lead?"* — pass rate by score state

## What it cannot answer yet

- **No prop odds yet.** Identity and game logs now exist, so props are unblocked — but the
  market side costs Odds API credits and hasn't been pulled.
- **`rz_td_rate` is NULL for NCAAF** — the `touchdown` flag is an nflverse-only column
  and CFBD's equivalent is lost in our play-type mapping. Needs a plays re-ingest.
- **No PFF college data** — same API (`league=ncaa`), all 22 facets confirmed present,
  but it needs a logged-in session and a `franchise_id`-keyed team crosswalk because
  PFF's college team names are truncated (`S JOSE ST`, `N TEXAS`). Phase 2.
- **No learned weighting yet.** Whether coaching or continuity dominates is contextual;
  that gets fit from data rather than asserted. **No models exist yet — this is all data
  and pipeline.**
- **No weather.** CFBD's weather endpoint is paywalled ($10/mo tier). Venue elevation,
  dome and surface are loaded; live conditions are not.
- **No injury data, and none is obtainable.** College has no mandatory injury report and
  CFBD publishes no snap counts, so unlike the NFL there isn't even an after-the-fact
  availability proxy.

## Modeling readiness

**8,883 usable games** — closing spread, final score, and full context + coach features
on both sides, 2016–2025. For comparison the NFL side has 237 once prior-season features
are required, because its features are deep but its history is short. NCAAF is the
inverse: the context reaches back to 2016 and now the labels do too.

| Requirement | Status |
|---|---|
| Labels (score + closing line) | 8,578 FBS games, 2016–2025 |
| Team context features | 11 seasons, both teams |
| Coach features (portable, incl. FCS) | 11 seasons |
| Player identity + production | 2023–2025 |
| Venue / elevation / neutral site | loaded |
| Prop market history | **not loaded** (costs credits) |
| Weather | **paywalled** |
| Injuries | **unobtainable** |

## Caveats the AI layer must inherit

- **FCS coaching stints are hand-seeded, not API-sourced.** No free source carries them:
  CFBD's `/coaches` is FBS-only (its `classification` param is silently ignored), ESPN's
  coach endpoint is **not season-aware** and returns today's coach for every historical
  year, and Wikidata is sparse and undated. Seeded rows carry `source='manual_fcs'` and
  `verified=false` — the mapping is asserted, the **records are computed** from CFBD FCS
  game data. Extend via `data/seeds/fcs_coach_stints.csv` then `make ingest-fcs-coaches`.
- **FCS success is its own feature, not blended into `career_sp_residual`.** An FCS SRS
  of -13.5 does not mean what an FBS SP+ of -13.5 means. Phase 3 learns the weight.
- **`seasons_of_history` counts FBS seasons only** — short history means *uncertain*, not
  average.
- **`career_sp_residual` uses a simplified talent baseline** (SP+ regressed on talent
  z-score per season). Directionally sound for ranking; not a calibrated projection.
- **Portal NULL ≠ zero** before 2021.
- **Unit cards are raw, not opponent-adjusted** — honest at the top/bottom-10 grain,
  noise between adjacent ranks. College strength-of-schedule variance is far wider than
  the NFL's, so this caveat bites harder here.
- **NCAAF `epa` is CFBD's PPA** — comparable in concept to nflverse EPA, different scale.
  **Never mix leagues in one aggregate.**

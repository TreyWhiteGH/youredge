# YourEdge — Football SGP + Live Edge Roadmap

**Target: BetLab MVP (all 4 modes, NFL + NCAAF pregame) live by NFL Week 1, Sept 2026. Live alerts mid-season. Data budget: $50–300/mo.**

Timeline reality check: it's July 19. Week 1 is ~7 weeks out. NCAAF Week 0 is ~6 weeks out. The plan below is scoped so the pregame product ships on time and live alerts don't block it.

---

## Architecture Principle (the one rule everything follows)

**The LLM never invents numbers. The LLM never prices anything.**

YourEdge is two systems:

1. **The Engine (deterministic, Python):** ingests odds/stats/PBP, computes fair probabilities, correlations, EV, and script fits. Every number the user sees comes from here.
2. **The Narrator/Planner (LLM):** translates user intent ("Bama gets up early then bleeds garbage-time passing yards") into structured queries against the Engine, and translates Engine output back into human explanations. It selects, it explains, it never calculates odds.

Contract between them: the LLM emits a **structured Script Spec** (JSON: game state assumptions, phases, team tendencies invoked) → the Engine returns candidate legs with fair prices, book prices, edge, and correlation matrix → the LLM assembles/explains. If the Engine has no data for a claim, the answer is "we can't price this," not a guess. This contract is also your moat — the modes are just four different entry points into the same pipeline.

---

## Data Sources (the stack, with costs)

### Stats & Play-by-Play (free — this is the modeling foundation)

| Source | What | Cost |
|---|---|---|
| **nflverse / nflreadpy** (Python client) | NFL PBP back to 1999, EPA/WP models, player stats, rosters, injuries, snap counts, NGS data. Updated nightly in-season. | Free |
| **CollegeFootballData.com (CFBD)** | NCAAF PBP, drives, player stats, ratings (SP+, Elo), betting lines history. REST + GraphQL. | Free tier 1k calls/mo; **Patreon Tier 3 $10/mo** → 75k calls + GraphQL with realtime subscriptions |
| **ESPN unofficial APIs** | Live scoreboard, live win probability, drive data (both leagues). Undocumented but stable, widely used. | Free |
| **sportsdataverse** ecosystem | Python/R loaders wrapping the above | Free |

### Odds (the money spend)

| Source | What | Cost |
|---|---|---|
| **The Odds API** (the-odds-api.com) | Current odds across US books incl. player props (NFL props in season), alternate lines, plus **historical odds snapshots back to 2020** (props historical from May 2023). | Paid tiers roughly $30–$120/mo depending on request volume; historical requests burn ~10x credits |
| **SportsGameOdds** | 80+ books incl. Pinnacle, props, WebSocket streaming, object-based billing. | Free tier (9 books, 10-min delay) for dev; $99/mo starter when you need density/live |
| **CFBD betting endpoints** | Historical NCAAF closing lines by game | Included in CFBD |
| **Pinnacle odds** (via either API above) | Your "sharp anchor" for de-vigging and fair-value baselines | Included |

**Recommended spend by phase:** Phase 0–1: ~$10/mo (CFBD only, Odds API free/dev). Phase 2–3: ~$40–140/mo (Odds API paid + CFBD). Phase 5 (live): add SportsGameOdds $99 → ~$150–250/mo total. Fits your budget.

**What you deliberately don't buy yet:** OpticOdds/SportsDataIO-class feeds ($500+/mo). Revisit only if live alerts prove out and users pay.

### Injuries / News
nflverse injury reports + ESPN APIs for status. **Rule: injuries gate recommendations (suppress/flag legs), the LLM never speculates about them.** No paid news feed in v1.

---

---

## Status — 2026-08-23

**Phase 0 is complete and substantially exceeded.** The data layer went well past the
original scope; the simulator has not started. NFL Week 1 is ~2 weeks out, so the
Week-1 fallback in the risk section below is now the live plan: ship Modes 3 and 4 on
historical queries and de-vigged market math, hold Mode 1's edge claims until the sim
calibrates.

### Built

| Layer | State |
|---|---|
| Play-by-play | NFL 148k (2023–25, enriched: EPA/WPA/success/air yards/dropback/location); NCAAF 488k (2023–25, CFBD PPA) |
| Odds | 53k snapshots, both leagues, `implied_prob` + de-vigged `fair_prob`; NCAAF closing lines back to **2016** |
| PFF (NFL) | **359,513 rows**, 22 facets, weekly + season, 100% game-linked — pressure splits, true alignment %, OL protection, coverage-allowed |
| Player identity | NFL 4,619 (nflverse) + NCAAF 44,807 (CFBD/ESPN ids), exact-id crosswalks |
| Player production | 234,430 game logs both leagues |
| NCAAF context | Coaching **tracked by coach, not school** (portable career residual incl. hand-seeded FCS stints), returning production, portal, talent, SP+ — 2016–2026 |
| Venues | 899 venues incl. elevation; per-game roof/surface/temp/wind/neutral-site |
| Career links | 1,663 exact `ncaaf:` ↔ `nfl:` player links via ESPN athlete ids, which persist college→pro. Makes "what did this rookie do in college" answerable |
| Feature pipeline | As-of builder with verified no-lookahead; NFL 474 complete-case rows, NCAAF 7,361 |

### Two models, one base

The architecture is settled: shared scaffolding (as-of guarantee, one target definition
— margin residual vs the closing spread, one train/eval harness, weights stored as data
in `model_runs`/`model_weights`), but **each league declares its own feature list**.
They are not variations on a theme:

- **NFL** — deep features, thin sample (474 usable). Signal is accumulated in-season
  form plus the PFF layer.
- **NCAAF** — thinner features, deep sample (7,361 usable, 2016–2025). Signal is
  preseason context: who is coaching, how much production returned, recruited talent.

Pooling them would be actively wrong. NCAAF `epa` holds CFBD's PPA, which averages
0.178 against the NFL's −0.004 — different measurements wearing the same column name.

**No models have been trained.** This is data and pipeline only.

### Honest gaps

- **NCAAF props** — market confirmed live (5–6 books, anytime TD densest); costs Odds
  API credits. Unblocked now that player identity exists.
- **PFF college** — the API works (`league=ncaa`, all 22 facets), but ingestion is
  **deliberately refused** until a `pff_ncaa` player crosswalk exists. The hazard is
  level conflation, not mistaken identity: PFF uses **one player id per human across
  college and the pros**, so a 2024 college receiver since drafted resolves to the
  *correct* person and his college game lands as NFL production (17 of 22 on a test
  did exactly that). `pff_player_stats.level` now lets both coexist, but college rows
  belong under `ncaaf:` ids, which needs a `franchise_id` team crosswalk (PFF truncates
  college names to `S JOSE ST`) plus jersey-validated player matching.
- **Weather** — CFBD's endpoint is paywalled ($10/mo tier). Venue elevation/dome/surface
  are loaded; live conditions are not.
- **NCAAF injuries** — structurally unobtainable. No mandatory college injury report and
  no snap counts, so unlike the NFL there isn't even an after-the-fact proxy.
- **NFL sample depth** — 474 usable games is the binding constraint on that side.
  nflverse PBP goes back to 1999 and PFF NFL to 1994; backfilling is the highest-leverage
  fix if a game-level NFL model is ever wanted.

---

## Phase 0 — Foundation (now → Aug 1) ~2 weeks

Stack: Python/Flask or FastAPI, Postgres (add TimescaleDB later for odds snapshots), Redis (you know all of this — no new infra learning curve).

- Ingestion jobs (Dockerized, cron/ECS): nflverse nightly loads → Postgres; CFBD backfill (PBP + historical lines, 2015+); Odds API poller (start on dev tier, snapshot spreads/totals/props for tracked games every 30–60 min pregame).
- Canonical schema: `games`, `teams`, `players`, `plays`, `odds_snapshots`, `markets`, `legs`. The hard unglamorous work is **entity resolution** (player/team IDs across nflverse ↔ CFBD ↔ odds feeds). Build the crosswalk table now; everything downstream depends on it.
- **Tagging taxonomy (first-class, day one).** Tags are the controlled vocabulary shared by the LLM and the Engine — the Script Spec contract is only queryable because both sides speak in the same tags. `tags` + polymorphic `taggings` tables; everything is taggable: scripts, legs, bets, angles, debriefs. Core dimensions:
  - **Script tags:** `BLOWOUT_FAV`, `SHOOTOUT`, `GRIND`, `BACKDOOR`, `FAST_START_FADE`, `GARBAGE_TIME_PASS`, `COMEBACK`, etc. Assigned by the sim (each sim region maps to script tags), invoked by the LLM when parsing hypotheses.
  - **Leg role tags:** `ANCHOR`, `CORRELATE`, `LOTTO`, `REDUNDANT`, `SCRIPT_CONFLICT` — output of the Phase 2 diagnostics.
  - **Angle tags:** team, unit (`RUN_D`, `PASS_O`), situation (`Q4`, `2H`, `RED_ZONE`, `REST_ADVANTAGE`), source (`AI_MINED`, `USER_THEORY`).
  - **Outcome tags (debriefs):** `PROCESS_WIN`, `VARIANCE_LOSS`, `BAD_READ`, `SCRIPT_HIT`, `SCRIPT_MISS` — these are what Bettor Memory coaching joins on ("you're 1–7 on SHOOTOUT scripts").
  - Governance: enum-controlled and versioned, LLM selects from the list at runtime (never invents tags mid-conversation — same philosophy as odds). Start with ~30–40 seed tags. New tags enter through one door: the **Angle Miner promotion pipeline** (below), not free text.
  - **Miner-proposed tags.** The nightly Angle Miner can discover themes the seed taxonomy doesn't cover (e.g., `DOME_PACE_UP`, `SHORT_WEEK_RUN_HEAVY`). Lifecycle: miner proposes tag + definition + the statistical split that motivated it → status `candidate` (usable internally, not user-facing) → auto-promoted to `active` when its angles survive the backtest/holdout gate → `deprecated` when they decay. You approve promotions manually at first (a 2-minute weekly review), automate the gate later. This keeps the taxonomy alive without letting the LLM pollute it.
- **Game Tag Surface.** Every game exposes its tags at a glance — this is the primary read model for the whole product. A `game_scripts` view per game: top script tags ranked by sim probability (`BLOWOUT_FAV 34% · GRIND 27% · BACKDOOR 18%`), plus active angle tags touching either team (`DET: Q4_PASS_D_FADE`, `REST_ADVANTAGE`). Powers three surfaces: the BetLab game page header (users see the script landscape before picking a mode), slate-wide filtering ("show me every SHOOTOUT-leaning game this week"), and the reverse lookup (tag → all games where it's live this week, which is how Angle Library cards link to the slate). Recompute on each sim run; it's just a query over sim output + taggings.
- De-vig module: strip vig from book odds (power/multiplicative methods), Pinnacle-anchored fair probabilities where available.

**Exit criteria:** one command hydrates a game with clean PBP history + current de-vigged odds for every market the books offer on it.

## Phase 1 — Game Script Engine (Aug 1 → Aug 15)

The core IP. A **game script** = a distribution over how the game unfolds: pace, lead states by quarter, pass/run mix by state, garbage time.

- From historical PBP, compute per-team **state-conditional tendencies**: pass rate when leading/trailing by X in Q1–Q4, plays per game by state, pace, red-zone splits, defensive fatigue proxies (yards/play allowed by drive number, second-half vs first-half).
- **Game simulator v1:** drive-level Monte Carlo (not play-level — play-level is a v2 luxury). Inputs: team tendencies + market-implied strength (spread/total set the priors — the market does the power-rating work for you in v1). Output: 10k sims → joint distributions over final score, quarter scores, team totals, player-usage buckets.
- Player prop layer: map sim team-volume outputs → player shares (target share, carry share, aDOT from nflverse) → distributions for yards/receptions/TDs. NFL first; NCAAF props are thinner at the books anyway, so NCAAF v1 covers game markets (spread/total/team totals/quarters/halves) + a handful of star-player props.

**Exit criteria:** for any game, the sim produces a joint distribution you can query: `P(Ravens -6.5 AND under 44)`, `P(Lamar over 215 pass yds | Ravens lead at half)`.

**Validation gate (do not skip):** backtest sim-implied probabilities against 2023–2025 closing lines and outcomes. Calibration plots + Brier scores. You're not trying to beat the closer in v1 — you're trying to be *calibrated* so correlation math is trustworthy.

## Phase 2 — SGP Pricing & Correlation (Aug 15 → Aug 29)

- **Correlation from the sim, not from rules of thumb.** Because legs are evaluated jointly inside the same simulated games, `P(leg A ∩ leg B)` falls out directly. This is what lets you say "these legs are correlated at +0.42, and the book's SGP price only charges you for +0.15."
- SGP pricing model: compare book SGP price (books quote combined odds with a correlation haircut) vs sim joint probability → **parlay EV and edge per leg**.
- Leg quality scores: edge, correlation contribution, redundancy (two legs proxying the same event), script-consistency (do all legs live in the same region of the sim distribution?).
- Risk modes = selection policies over the same candidates: **Sharp** (high edge, high joint prob, 2–3 legs), **Balanced**, **Lotto** (long-tail script region, positive correlation stacking, capped stake guidance).

**Exit criteria:** given any set of legs + a book price, the Engine returns: joint fair prob, fair price, edge, per-leg diagnostics.

## Phase 3 — BetLab: the 4 Modes (Aug 29 → Sept 10, Week 1) 

All four modes are thin LLM layers over Phases 1–2. Use Claude with tool-use: tools = `get_game_data`, `run_simulation`, `price_legs`, `evaluate_parlay`, `find_legs_matching_script`.

1. **Auto Generate:** league/game/book/risk mode → Engine generates candidates → risk-mode policy selects → LLM writes the narrative ("this SGP expresses a Ravens-control script").
2. **Build Around My Pick:** anchor leg → Engine conditions the sim on the anchor (`P(X | Ravens -6.5 hits)`) → returns the legs most positively correlated with the anchor that still carry edge → LLM assembles. Tells the user if the anchor itself is -EV.
3. **Test My Hypothesis:** LLM parses the theory into a Script Spec → Engine checks it two ways: (a) *does history support it?* (e.g., NY's run defense by half, opponent rush EPA Q4 vs Q1), (b) *is it priced?* → returns supported/unsupported + the cheapest markets expressing it (2H team totals, quarter lines, alt props). "Your theory is real but fully priced" is a first-class answer.
4. **Critique My SGP:** user's legs → Engine flags mixed scripts (legs from conflicting sim regions), negative/overpriced correlation, redundancy, -EV legs → LLM presents cleaner + aggressive versions and a play/pass verdict at the quoted price.

Product surface for MVP: web app (Flask/FastAPI + a simple React front end — or even server-rendered to start). **Plays of the Day** = daily job running Mode 1 across the slate, publishing top-N by edge with narratives.

**Ship gate for Week 1:** Modes 1 and 4 polished; Modes 2 and 3 functional. Cut scope there if needed — Auto Generate + Critique are the demo-able core.

## Phase 3.5 — AI-Native Layer (built alongside Phases 3–4)

Three features that turn YourEdge from a pick engine into an analyst. All obey the core rule: the Engine finds and validates the numbers, the AI writes and reasons.

### Angle Library (AI-mined theories) — start Week 1, grow in-season

A nightly agent sweeps historical PBP + odds for angles, writes each as a human-readable theory ("Lions defenses since 2024 give up 38% more pass EPA in Q4"), and only publishes ones that survive backtesting (min sample size, holdout validation, edge vs closing line).

- Pipeline: candidate-generation job (templated statistical sweeps over team/situation splits) → significance + backtest filter → LLM writes the theory card → published to a browsable library, tagged by team/script type.
- Each angle card: the claim, sample size, backtest record, and a one-click "test this on this week's slate" that pipes it into Mode 3.
- This inverts Mode 3 — the AI brings theories to the user. Also your best content-marketing engine: angle cards are inherently shareable.
- Guardrail: multiple-comparison discipline. Sweeping thousands of splits will produce fake angles; require holdout performance and decay angles that stop hitting.

### Bettor Memory + Coaching — schema at Week 1, coaching from ~Week 4

Track every bet a user runs through BetLab (generated, critiqued, or logged) and let the AI reference the user's own history in every interaction.

- Data: `user_bets` (legs, price at rec time, closing price, result), derived profile (bet types, risk appetite, CLV by category, bias signatures).
- Coaching surfaces: in Critique ("you're 2–9 on road favorites this season and this slip has three"), in Auto Generate (risk mode defaults learned from behavior), and a weekly "your patterns" recap.
- Needs ~3–4 weeks of user data before coaching claims are honest — ship the logging Week 1, ship the coaching voice around Week 4.
- This is the long-term moat: memory compounds and can't be copied by anyone wrapping an odds API.

### Post-Game Debriefs — ship by Week 3

After each game a user had action on, the AI writes what actually happened vs. the script they bet, from the actual PBP.

- Engine side: replay the game against the pregame sim — which script region did reality land in, where did the bet's legs diverge, and a luck-vs-skill decomposition (e.g., leg lost on a fluke TD vs. the script never materializing).
- LLM side: 150-word debrief per bet — "your read was right, the script hit, you lost to a garbage-time TD; that's variance, the process was +EV."
- Feeds Bettor Memory directly (debrief verdicts become the coaching evidence base) and teaches users to trust CLV over results — which is also the product's honesty story.

## Phase 4 — In-Season Hardening (Sept → Oct)

- **CLV tracking is the product's report card:** log every recommendation at recommendation-time price, compare to closing line. Positive CLV = real edge; publish it (it's also your marketing).
- Weekly recalibration of team tendencies (shrinkage toward priors early season — Weeks 1–4 data is noisy, lean on 2025 tendencies + market priors).
- Injury gating, line-move staleness checks (recommendation invalidates if line moves > X), user feedback loop on Critique quality.
- Angle Library decay checks and Bettor Memory coaching launch (see Phase 3.5).

## Phase 5 — Live Edge Alerts (Oct → Dec)

Now the sim earns its keep twice:

- Live state ingestion: ESPN live APIs (score, clock, situation) + SportsGameOdds WebSocket for live odds ($99/mo tier).
- **Re-sim from current state:** the same drive-level simulator, initialized at the live game state, re-priced every score change/possession. Compare to live book prices.
- Alert types: (a) *script confirmation* — "the script you bet pregame is happening and 2H markets haven't caught up," (b) *entry timing* — "your watchlisted pick is now mispriced live," (c) generic live edge above threshold.
- Latency honesty: you will not out-speed the books' live pricing on main markets. The edge window is **derivative live markets** (2H lines, live team totals, live props) where books are slower and wider. Design alerts around those.
- Delivery: push/SMS/Discord webhook; alerts carry the number and the deadline ("edge exists at -110 or better").

### Live Script Narration (AI layer on live alerts)

Alerts become commentary, not just numbers. For games a user has action on, the AI narrates script evolution at natural checkpoints (score changes, quarter breaks, possession swings): "The Bama-runs-away script is on track — up 14 mid-Q2 — but they're passing more than sims expected, which threatens your rush-yards leg."

- Engine side: at each checkpoint, diff live game state vs. the pregame sim distribution — which script region is reality tracking, and which of the user's legs are ahead/behind their conditional expectation.
- LLM side: 1–2 sentence narration per checkpoint, always tied to the user's specific legs and, when relevant, the live-market opportunity ("2H under hasn't adjusted to this pace — edge at -108 or better").
- Ties directly into Bettor Memory (narrations become debrief inputs) and the entry-timing alerts above.
- Rate-limit the voice: max ~4–5 narrations per game per user. Constant pings kill trust; checkpoint-only keeps it feeling like a sharp friend texting, not a bot.

## Phase 6 — Basketball Port (Jan 2027+)

The whole point of the architecture: swap the ingestion layer (nba_api / hoopR, same odds providers) and the simulator internals (possession-based instead of drive-based). Script Spec contract, correlation engine, 4 modes, alert system all carry over. NBA is actually a *better* SGP sport (higher-volume props, cleaner usage data), so the port should be faster than the original build.

---

## Risks & Honest Caveats

- **Books limit winners.** If YourEdge works, users get limited. Position the product as intelligence, not a tout service; CLV is the honest metric.
- **Legal:** you're selling analytics, not taking bets — generally fine, but check NJ rules on paid picks/advice before charging money, and add responsible-gambling language day one.
- **Prop data thinness (NCAAF):** don't fight it; NCAAF v1 is game-markets-first.
- **ToS:** ESPN's APIs are unofficial; keep them for live state only, with The Odds API/SGO as the contractual backbone.
- **Biggest schedule risk is Phase 1 validation.** If the sim isn't calibrated by Aug 29, ship Modes 3/4 (which lean on historical queries + de-vigged market math) and hold Mode 1's "edge" claims until calibration passes.

## Cost Summary at Steady State (pregame MVP)

CFBD $10 + The Odds API ~$30–120 + hosting (small AWS: RDS + one container host) ~$40–70 → **~$80–200/mo**, inside budget. Live alerts add ~$99.

---

## Sources

- [The Odds API](https://the-odds-api.com/) · [Historical odds data](https://the-odds-api.com/historical-odds-data/)
- [SportsGameOdds pricing](https://sportsgameodds.com/pricing)
- [Odds API pricing comparison 2026](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/)
- [nflfastR / nflverse](https://nflfastr.com/) · [nflverse GitHub](https://github.com/nflverse)
- [CollegeFootballData.com](https://collegefootballdata.com/) · [CFBD API tiers](https://collegefootballdata.com/api-tiers) · [CFBD GraphQL](https://graphqldocs.collegefootballdata.com/)
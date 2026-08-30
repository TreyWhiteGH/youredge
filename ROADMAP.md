# YourEdge — Football SGP + Live Edge Roadmap

**Target: BetLab MVP (NFL + NCAAF pregame) live by NFL Week 1. Live alerts mid-season. Data budget: $50–300/mo.**

Timeline: **2026-08-29. NFL Week 1 is 11 days out (Sept 9).** NCAAF Week 0 has been
played. Two of the four modes are live and need no simulator; the plan below is what
remains, and it no longer pretends the sim gates the ship.

---

## Architecture Principle (the one rule everything follows)

**The LLM never invents numbers. The LLM never prices anything.**

YourEdge is two systems:

1. **The Engine (deterministic, Python):** ingests odds/stats/PBP, computes fair probabilities, correlations, EV, and script fits. Every number the user sees comes from here.
2. **The Narrator/Planner (LLM):** translates user intent ("Bama gets up early then bleeds garbage-time passing yards") into structured queries against the Engine, and translates Engine output back into human explanations. It selects, it explains, it never calculates odds.

**The sharpened form, learned by building it: the market supplies levels, the model
supplies conditionals.** Where a book prices something, its de-vigged number is the
better estimate and the engine's job is not to argue with it — it is to say how that
number *changes* conditional on something else. "Lamar over 215" is the book's
question; `P(over 215 | Ravens lead at half) ÷ P(over 215)` is ours. This is why the
simulator will be anchored to the market's spread and total by construction rather
than hoping to reproduce them, and why marginal calibration becomes a unit test
instead of a gate.

Contract between them: the LLM emits a **structured Script Spec** (JSON: game state assumptions, phases, team tendencies invoked) → the Engine returns candidate legs with fair prices, book prices, edge, and correlation matrix → the LLM assembles/explains. If the Engine has no data for a claim, the answer is "we can't price this," not a guess. This contract is also your moat — the modes are just four different entry points into the same pipeline.

---

## Data Sources (the stack, with costs)

### Stats & Play-by-Play (free — this is the modeling foundation)

| Source | What | Cost |
|---|---|---|
| **nflverse / nflreadpy** (Python client) | NFL PBP back to 1999, EPA/WP models, player stats, rosters, injuries, snap counts, NGS data. Updated nightly in-season. | Free |
| **CollegeFootballData.com (CFBD)** | NCAAF PBP, **drives**, **play-level player stats**, ratings, betting lines. | Free tier 1k calls/mo. **Subscribed.** Gates verified against the API: Tier 1 → `/games/weather`; Tier 2 → `/live/plays` (the college side of Phase 7); Tier 3 → GraphQL + 75k calls |
| **ESPN unofficial APIs** | Live scoreboard, live win probability, drive data (both leagues). Undocumented but stable, widely used. | Free |
| **sportsdataverse** ecosystem | Python/R loaders wrapping the above | Free |

### Odds (the money spend)

| Source | What | Cost |
|---|---|---|
| **The Odds API** (the-odds-api.com) | Featured markets bulk; props, alternates, halves, quarters and team totals **per event only**. Props are posted ~2 weeks ahead, earlier than assumed. | 20k credits/mo. Bulk call = 3 credits regardless of game count; a per-event sweep = 1 credit per market. **Books are free** — credits scale with markets × regions, not bookmakers, so ask widely and ration the market list |
| **SportsGameOdds** | 80+ books incl. Pinnacle, props, WebSocket streaming, object-based billing. | Free tier (9 books, 10-min delay) for dev; $99/mo starter when you need density/live |
| **CFBD betting endpoints** | Historical NCAAF closing lines by game | Included in CFBD |
| **Pinnacle odds** (via either API above) | Your "sharp anchor" for de-vigging and fair-value baselines | Included |

**The spend lesson:** the original plan deferred prop polling to a later phase. That was
the one deferrable item that is not actually deferrable — props and derivative markets
accrue only in real time and cannot be bought back at this granularity later. Everything
else on this list can wait; that cannot.

**What you deliberately don't buy yet:** OpticOdds/SportsDataIO-class feeds ($500+/mo). Revisit only if live alerts prove out and users pay.

### Injuries / News
nflverse injury reports + ESPN APIs for status. **Rule: injuries gate recommendations (suppress/flag legs), the LLM never speculates about them.** No paid news feed in v1.

---

---

## Status — 2026-08-29

**Two Bet Lab modes are live, and neither uses a simulator.** That is the headline,
and it is the opposite of what the original plan predicted: the sim was treated as
the gate on everything, when in fact the two modes that ship first are precisely the
two that never needed it.

### Live now

| Mode | State | Runs on |
|---|---|---|
| **Critique a slip** | live | counted leg outcomes + de-vigged prices |
| **Test a hypothesis** | live | same surface, queried by claim instead of by slip |
| Generate | 501 | needs the sim — it is the only mode that must be right unprompted |
| Build around a pick | 501 | needs conditional probabilities the sim produces |

Critique returns per-leg edge against the sharpest book, flags redundancy and script
conflict with the sample size on every claim, and **refuses to quote a combined
price** — the marginals behind it are base rates, not this game's fair probabilities.
Test-a-hypothesis answers whether a theory holds *and, separately, whether the price
already knows*, with "real but already priced" a first-class verdict.

### Built

| Layer | State |
|---|---|
| Play-by-play | NFL **484,254** (2016–25); NCAAF 487,508 (2023–25) |
| Drives | **126,435** possessions, both leagues — the simulator's kernel |
| Odds | **201k** snapshots across **17 market keys** — props, alternates, halves, quarters, team totals |
| Player attribution | 437,506 rows, **99.9% of NCAAF games**; feed and parsed rows separable by `source` |
| Weather | 2,712 of 2,762 college games — was documented as paywalled |
| Empirical joint | 52,387 leg outcomes · 1,609 pair correlations · 5,349 script labels |
| PFF (NFL) | 359,513 rows, 22 facets, 100% game-linked |
| Tendencies | pass rate, pace, drive outcomes by field position, defensive fatigue |

### Still true

**No simulator, and no trained model.** The RidgeCV margin trainer was deleted rather
than kept: the sim anchors to the market, so a learned margin residual is a later
refinement — the thing that eventually lets you *disagree* with the market rather than
ride it. `model_runs`/`model_weights` remain as the contract for its replacement.

### What the first pass got wrong

Worth recording, because the same shapes will recur.

- **The ship gate had its dependencies backwards.** It called for "Modes 1 and 4
  polished, Modes 2 and 3 functional". Mode 1 is the only one that needs a calibrated
  sim; 3 and 4 are the two that don't. Following it would have blocked the shippable
  work on the unshippable.
- **"Correlation from the sim, not from rules of thumb" was a false choice.** The third
  option — count it over finished games — is what both live modes now run on, and it
  has the added value of being a witness the sim can later be checked against.
- **Props were never budgeted.** The plan treated odds spend as spreads and totals.
  Props are the binding constraint on the whole SGP thesis, and they accrue only in
  real time — the one input that gets permanently more expensive to skip.
- **A validation set drawn only from where labels exist is not a random sample.** The
  play-text parser scored 99%+ on SEC/ACC and silently dropped touchdowns everywhere
  else, because other conferences use a play-text format SEC/ACC never produces.

### Honest gaps

- **NCAAF props** — now requested for every college game, but college books post a much
  thinner board than NFL books and post it close to kickoff, so coverage stays sparse
  until the week of a game.
- **Play-level player ids outside SEC/ACC** — CFBD's feed covers those two conferences
  only, and ESPN publishes no player participants on college plays either. The other
  ~71% is recovered by parsing play text at 99%+ precision, written under
  `source='playtext'` so inference is never confused with feed.
- **Defensive counts undercount.** Sacks run ~25% light and interceptions further,
  because the text often declines to name the defender. Precision is near-perfect;
  recall is not. These columns answer "did he" far better than "how often".
- **Target share is unreliable from either source** — the feed under-records `Target`,
  and CFBD names the intended receiver on ~9% of incompletions. This matters because
  target share is a core input to the prop layer.
- **`air_yards` / YAC for college** — in no free source; runs through PFF.
- **PFF college** — still refused pending a `franchise_id` crosswalk and jersey
  validation. Sequence it *after* play-level ids, which give it a second identity to
  validate against.
- **NCAAF injuries** — genuinely unobtainable. No mandatory report, no snap counts. Do
  not buy a scraped one; a wrong injury flag is worse than a stated absence.

---

## Phase 0 — Foundation ✅ complete

Ingestion, canonical schema, entity resolution, tagging taxonomy, de-vig. Went well
past its original scope. See Status above for what actually landed.

**One operational lesson worth keeping:** `make migrate` replayed two hard-coded files,
so every migration after them applied only to fresh volumes and a long-lived database
drifted silently behind the repo. It now tracks what has run and baselines an existing
DB. A migration that appears to succeed and changes nothing is the worst failure mode
in the stack.

## Phase 1 — The empirical joint ✅ complete

**Not in the original plan, and it is what let two modes ship early.** Count what
happened before modelling any of it.

- `game_state` — realized state per finished game: how big the lead got, where the
  margin sat at each break, how the play mix shifted once the game was decided.
  Deliberately no win probability, because nflverse has it and CFBD does not, and a
  script vocabulary meaning different things per league is worse than none.
- Script labels into `taggings` — predicates over what happened, so they are countable.
  The two mix-based tags use a percentile *within* league: a flat threshold fired on
  28% of NFL games and 9% of college ones purely from the scramble/dropback convention.
- `leg_outcomes` — what every leg template would have done. `line_source` separates
  real closing lines from synthetic ones, because a synthetic line supports a
  correlation and cannot price anything.
- `leg_pair_stats` — P(A), P(B), P(A∩B), φ and lift, unconditionally and per script,
  with `n` on every row.

**It reproduces football unprompted**, which is the check that matters: TOTAL
over/under φ = −0.98, spread × own team total +0.51, and both team totals shifting from
+0.05 to −0.52 inside a blowout.

## Phase 2 — Bet Lab, honest modes (Aug 29 → Sept 9) ← **here**

Critique and Test-a-hypothesis are live. What remains before Week 1:

- ~~**Poll NCAAF props.**~~ Done. Both leagues now request the full 39-key board — every
  quarter and half, alternate ladders, player props and the "X+" ladders. The per-league
  split was removed once the meter was measured: it charges for markets that return a
  quote, not markets requested, so asking college for a board it does not offer is free.
- **De-vig upgrade.** The structural half is done: rungs are grouped per line (signed, for
  spreads), which repaired 15,932 alternate rows that had been divided by a whole ladder's
  overround and stored at roughly a thirtieth of their true value. One-sided player ladders
  borrow their margin from the two-way parent. What remains is the *accuracy* half —
  power/Shin instead of multiplicative, which is worst exactly where the live data is worst
  (a 1.60 overround on a lopsided college moneyline), and Pinnacle anchoring throughout.
- **Price the touchdown boards.** `player_anytime_td` and `player_tds_over` still carry no
  `fair_prob`. They are one-sided and their Yes prices legitimately sum well above 1, so
  they need an expected-scorer target derived from the de-vigged game total rather than a
  normalisation. Anytime TD is the most-bet SGP leg there is, so this outranks power/Shin.
- **Freshness gating everywhere**, not just in Critique. A leg priced off a stale line
  is worse than no leg.
- **`user_bets` writes** — log every slip run through Critique at recommendation-time
  price. This is the CLV record and the Bettor Memory substrate, and it costs nothing
  to start now.
- **Tests.** There are none, in a system whose entire pitch is numerical honesty. The
  minimum: de-vig sums to 1 within every rung, a ladder's rung at a player's main line
  reproduces that main line's `fair_prob`, alternate ladders stay monotone, the play-text
  parser's golden file, ledger hit rates stay at 48–50% against closing lines, and a
  no-lookahead assertion. The first three are checks already run by hand on live data;
  writing them down is what stops the next grouping change from silently undoing them.

**Ship gate for Week 1:** Critique and Test-a-hypothesis polished, props flowing, CLV
logging live. Generate and Build-around stay 501. That is a real product — it tells
you what your slip is worth and whether your read is already priced — and it makes no
claim it cannot support.

## Phase 3 — Game script simulator (Sept, in-season)

The core IP, and now correctly downstream rather than blocking.

- Drive-level Monte Carlo over the `drives` kernel, using the tendency surfaces already
  built (pace, drive outcome by field position, red zone, fatigue).
- **Anchored by construction.** Solve two parameters per team so the simulated median
  margin equals the de-vigged market spread and the median total equals the market
  total. Marginal calibration then becomes a unit test rather than a hope, and the sim
  is only ever asked for what it uniquely provides: conditionals, script regions, and
  distributions for markets the book does not price.
- Player props by the same trick: anchor the mean to the posted line, let the sim supply
  only how the distribution shifts across script regions.

**Numeric gates, pass/fail — the original plan had none:**

| | Gate | Threshold |
|---|---|---|
| G1 | median sim margin vs de-vigged market spread | within 0.25 pt, 100% of games |
| G2 | H1 / team total / Q1 calibration, 10 buckets | max bucket deviation ≤ 4pp |
| G3 | Brier on ATS and total | ≤ market Brier + 0.005 |
| G4 | **sim φ vs the empirical φ from Phase 1** | Spearman ≥ 0.7; sign agreement where \|φ\| ≥ 0.15, n ≥ 200 |
| G5 | prop conditional lift vs empirical lift | sign agreement ≥ 80%, n ≥ 100 |
| G6 | no lookahead | assertion, hard fail |

**G4 is the one the first plan was missing and the one that matters.** Correlation is
the product; validating marginals and then selling the joint checks the wrong thing.
Phase 1 exists partly so this gate has something independent to check against.

## Phase 4 — Generate, Build-around, and SGP pricing (post-calibration)

Only once the sim clears its gates does a combined fair price mean anything.

**The SGP price problem, unaddressed in the first plan:** no API sells same-game parlay
quotes. Critique therefore takes the user's pasted price and stores it. A few hundred
real quotes make a book's correlation haircut modellable, which is what lets Generate
estimate a price without the user — the gap becomes a dataset rather than a blocker.

## Phase 5 — In-season hardening (Oct)

- CLV as the report card: recommendation-time price vs closing. Publish it.
- Weekly tendency recalibration, shrinkage toward priors while early-season data is thin.
- Injury gating, line-move staleness, Critique feedback loop.
- **CLV tracking is the product's report card:** log every recommendation at recommendation-time price, compare to closing line. Positive CLV = real edge; publish it (it's also your marketing).
- Weekly recalibration of team tendencies (shrinkage toward priors early season — Weeks 1–4 data is noisy, lean on 2025 tendencies + market priors).
- Injury gating, line-move staleness checks (recommendation invalidates if line moves > X), user feedback loop on Critique quality.
- Angle Library decay checks and Bettor Memory coaching launch (see Phase 6).


## Phase 6 — AI-Native Layer (in-season, after the sim)

Three features that turn YourEdge from a pick engine into an analyst. All obey the core rule: the Engine finds and validates the numbers, the AI writes and reasons.

### Angle Library (AI-mined theories) — **not Week 1**

Deferred deliberately. Sweeping thousands of splits before the holdout
discipline is enforced manufactures angles, and Test-a-hypothesis already
answers the same question on demand with the sample size attached.

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

## Phase 7 — Live Edge Alerts (Nov → Jan)

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

## Phase 8 — Basketball Port (Feb 2027+)

The whole point of the architecture: swap the ingestion layer (nba_api / hoopR, same odds providers) and the simulator internals (possession-based instead of drive-based). Script Spec contract, correlation engine, 4 modes, alert system all carry over. NBA is actually a *better* SGP sport (higher-volume props, cleaner usage data), so the port should be faster than the original build.

---

## Risks & Honest Caveats

- **Books limit winners.** If YourEdge works, users get limited. Position the product as intelligence, not a tout service; CLV is the honest metric.
- **Legal:** you're selling analytics, not taking bets — generally fine, but check NJ rules on paid picks/advice before charging money, and add responsible-gambling language day one.
- **Prop data thinness (NCAAF):** don't fight it; NCAAF v1 is game-markets-first.
- **ToS:** ESPN's APIs are unofficial; keep them for live state only, with The Odds API/SGO as the contractual backbone.
- **The schedule risk the first plan named has already resolved, in the good direction.**
  It said: if the sim isn't calibrated by Aug 29, fall back to Modes 3/4 on historical
  queries and de-vigged market math. That fallback became the plan, shipped, and is
  better than a fallback — those two modes make claims that stay true after the sim
  arrives, because counted history does not stop being counted.
- **The remaining schedule risk is prop coverage, not the sim.** Both leagues are polled
  now, but the depth only exists close to kickoff, so Week 1 is the first real sample.
  Every day unpolled is line-movement history that cannot be bought back, and the sim
  cannot fix it later.
- **Beware validating on the only segment that has labels.** The play-text parser scored
  99%+ against SEC/ACC ground truth and was systematically dropping touchdowns in every
  other conference, because those conferences use a format SEC/ACC never produces. The
  same trap is waiting for the simulator: NFL has richer labels than NCAAF, and a gate
  passed on NFL is not a gate passed.
- **Feed silence is not disagreement.** Scoring a parser against a feed that records the
  quarterback's sack but not the defender's put its precision at 32% when the real
  figure was 99.8%. Any future validation against a partial source needs the same
  distinction built in.

## Cost Summary at Steady State (pregame MVP)

CFBD Patreon (subscribed — unlocks weather, live plays, GraphQL, 75k calls) + The Odds
API 20k credits + hosting (small AWS: RDS + one container host) ~$40–70 →
**~$80–200/mo**, inside budget. Live alerts add ~$99 for SportsGameOdds.

Current burn: featured-market polling is 3 credits per league per poll and runs hourly;
the per-event tier costs 1 credit per market and is scheduled against time-to-kickoff,
tightening from daily to a single closing sweep inside the last hour. At 30-minute
polling the featured tier alone would consume most of the monthly allowance before props
got any — which is why the loop is hourly.

---

## Sources

- [The Odds API](https://the-odds-api.com/) · [Historical odds data](https://the-odds-api.com/historical-odds-data/)
- [SportsGameOdds pricing](https://sportsgameodds.com/pricing)
- [Odds API pricing comparison 2026](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/)
- [nflfastR / nflverse](https://nflfastr.com/) · [nflverse GitHub](https://github.com/nflverse)
- [CollegeFootballData.com](https://collegefootballdata.com/) · [CFBD API tiers](https://collegefootballdata.com/api-tiers) · [CFBD GraphQL](https://graphqldocs.collegefootballdata.com/)
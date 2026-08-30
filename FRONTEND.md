# YourEdge — Frontend

*Written 2026-08-25. Companion to [CAPABILITIES.md](CAPABILITIES.md), which describes the
data and the endpoints; this describes the app that renders them.*

The web client is a view over the engine and holds no second source of truth. **Every
number on screen came from an engine response.** There is no mock data in the bundle, no
client-side statistic, and no fallback that invents a plausible value when a request
fails.

---

## 1. What was replaced, and why

The previous app did not compile. `apps/web/src/sgp/lib/` — `types.js`,
`mockResponses.js`, `api.js` — was imported by nine modules and absent from the
repository. The cause was a `.gitignore` rule: a bare `lib/` intended for Python build
artifacts matches at *any* depth, so the directory was silently never committed. That
rule is now anchored (`/lib/`), which is the actual fix; restoring the files alone would
have let it happen again.

Two other things drove a rewrite rather than a repair:

- **It pointed at the wrong backend.** Every fetch went to the legacy Flask service
  (`/api/scoreboard`, `/api/picks`, `/api/generate-picks`) — basketball-era, multi-sport,
  and behind an opt-in `legacy` profile in `docker-compose.yml`. The football engine, which
  holds 973k plays, 360k charting rows and 250k odds snapshots, had no UI at all.
- **It presented invented numbers as real.** `MOCK_TOP_PICKS` carried fabricated
  confidence and edge values; `MOCK_GAMES` carried invented spreads. No model has been
  trained, so those numbers could not have been real — and nothing on screen said so.

---

## 2. Stack

React 18, Vite 5, React Router 6. Three runtime dependencies, no UI framework, no chart
library, no icon package.

```bash
npm install && npm run dev     # http://localhost:5173
```

Vite proxies `/api` to `http://localhost:8000`, so the browser stays on one origin: the
app is identical in dev and behind any static host in front of the engine. Override with
`ENGINE_URL` in `.env.local` — needed when working in a git worktree, because
`docker compose` bind-mounts the **main checkout's** `apps/engine/src` and cannot see
worktree changes.

Tailwind was previously loaded from a CDN `<script>`, which is a development-only build
and warns in production. It is gone; the design system is ~500 lines of CSS with tokens
for both themes.

```
src/
  lib/         api.js · hooks.js · format.js · store.jsx
  styles/      tokens.css · base.css · components.css
  icons/       index.jsx — the entire icon set
  components/  AppShell · CommandPalette · ShortcutSheet · GameCard · ui.jsx
  pages/       one file per route
public/icons/  mark.svg · mark-light.svg · wordmark.svg
```

---

## 3. Routes

| Route | Engine surfaces |
|---|---|
| `/slate` | `GET /{league}/games` — schedule grouped by day, each with the best book's line |
| `/games/:league/:id` | game detail, both unit cards ranked in one field, full board with line movement |
| `/teams` | `GET /{league}/teams` |
| `/teams/:league/:id` | offense/defense cards, unit analysis, protection, pass-rate heatmap; NCAAF swaps in coaching, returning production, portal |
| `/players` · `/players/:id` | search, bio, seasons, game log, usage & alignment, opponent splits, QB clutch, linked college career |
| `/coaches/:id` | full career across every school |
| `/compare` | up to four teams as columns over the same ranked rows |
| `/lab` | the four SGP modes, calling the real endpoints |
| `/data` | `GET /football/coverage`, rendered verbatim |

---

## 4. Endpoints added to the engine

The UI could not list a slate or a team, because no endpoint enumerated either. Five were
added as thin reads over existing tables — `routes/games.py` and `routes/meta.py`:

| Endpoint | Notes |
|---|---|
| `GET /{league}/teams` | NCAAF defaults to FBS; the 105 FCS teams have no odds and no context rows |
| `GET /{league}/games` | filter by season/week/status/team, or `upcoming=true`; carries teams, conditions, best-book price |
| `GET /{league}/games/{id}` | one matchup, every quoting book |
| `GET /{league}/games/{id}/odds` | full board plus the snapshot series |
| `GET /football/coverage` | row counts, counted live, plus the capability roster |

Two decisions inside them are worth knowing:

**Outcomes resolve through the alias crosswalk, not string equality.** The Odds API writes
`North Carolina Tar Heels` where `teams.name` is `North Carolina`. Comparing them directly
silently dropped every college spread and moneyline while leaving Over/Under intact — the
slate looked fine and was quietly wrong. Resolution now goes through the `cfbd_alias`
rows the ingest already built. An outcome matching neither team is omitted rather than
guessed at, because attributing a price to the wrong team is worse than showing none.

**Live books and archives are distinguished.** `cfbd:*` and `nflverse:closing` are
historical archives — correct for backtests, wrong as "the current line". They are
consulted only when no live book has the game, and `is_live_book` travels in the response
so the UI can badge them.

`league_guard` was extended to `game_id`, so `/api/nfl/games/ncaaf:401856766` returns 400
rather than a 404 that reads like "no data".

---

## 5. Four rules the code holds to

### Never fabricate

A `501` from the engine is not an error. It arrives with a `phase` marker on surfaces that
are deliberately unbuilt, and `lib/api.js` converts it to a typed `NotBuiltYet` so the UI
can render a phase gate instead of a spinner, a red error, or a plausible number.

This is why `/lab` looks the way it does. Selecting a game and running a mode calls the
real endpoint and shows its real answer: *"Generate is not implemented · 0-foundation ·
Engine is ingesting data; sim + pricing land in Phases 1–2."* Pricing a same-game parlay
needs a joint distribution, which needs the drive-level simulator, which has not been
calibrated. Rendering an edge before then would invent one.

### Null is not zero

A missing temperature means the reading was not reported — CFBD's weather endpoint is
paywalled — not that the game was calm or indoors. Absent values render as an em dash, and
`format.js` is the only place that decides. Conditions tiles are omitted entirely rather
than shown empty. `rz_td_rate` is null for NCAAF because `touchdown` is nflverse-only, and
the tile says so on hover instead of showing 0%.

### One colour scale, and it is not the accent

`scaleColor` maps a league percentile to a hue and is the only thing that colours a rank.
It reads from five dedicated tokens — `--rank-best` through `--rank-worst` — and
deliberately **not** from `--accent`.

That separation is load-bearing rather than tidy. The ramp used to borrow `--accent` for
its second band, which was fine while every theme's accent was blue. The moment the light
theme took a green accent, `--good` and `--accent` were the same hue and a five-step scale
rendered as four, silently. Ranks and chrome are different jobs and no longer share a
variable.

For the same reason `--good` is teal in the light theme: a positive delta sits next to a
link often enough — in the compare table they are adjacent columns — that they must not be
the same green.

The pass-rate heatmap is the single deliberate exception — there the two colours mean
*direction* (passes more / runs more), not quality — so it carries an explicit legend
rather than relying on a convention that means something else everywhere else.

### Sample size travels with the rate

Opponent splits show the game count beside every number and flag anything under three
games, because divisional foes reach five or six games over three seasons and everyone
else gets one or two. Heatmap cells under 25 plays are drawn washed out. The clutch tab
surfaces the engine's `small_sample` flag. Cross-league compare warns that NCAAF's `epa`
column holds CFBD's PPA, which averages 0.178 against the NFL's −0.004.

---

## 6. Licensed data: naming and reduction

The grading and charting layer is licensed from PFF. Two changes were made.

**Naming.** Those surfaces are labelled **Analysis** and **Unit grades**; no user-visible
string names the vendor. Provenance stays truthful everywhere else — the tables are still
`pff_player_stats`, the ingest is still `youredge.ingest.pff`, and `CAPABILITIES.md` still
says where the numbers come from.

**Reduction.** Renaming alone is cosmetic, so the amount of licensed data the browser can
reach was cut. Four endpoints accept `detail=summary`, and `lib/api.js` sends it on every
call the app makes:

| Endpoint | `full` (default — the reasoning layer) | `summary` (the browser) |
|---|---|---|
| `/teams/{id}/units` | grade, league average, rank | rank, percentile, above/below the field |
| `/teams/{id}/protection` | + per-lineman grade, true pass set | counted events, derived pressure rate |
| `/players/{id}/pff` | + grade + complete export row | snaps, routes, slot/wide rate |
| `/players/{id}` | + per-facet grade | usage and alignment only |

`/players/{id}/pff` drops from **126 KB to 4 KB**, because at full detail it was shipping
the vendor's export rows verbatim. `/pff/splits` returns those rows by design and **no UI
surface calls it**. What the client never requests, devtools cannot show.

The split is principled rather than arbitrary: *snaps taken, pressures given up, and how
often a receiver lined up inside* are observations about what happened on the field. *A
grade* is the vendor's evaluation of it. Summaries keep the first and drop the second.

Two caveats, recorded because they will come up again:

- **De-branding is not a licensing control.** The risk in redistributing proprietary
  grades is the redistribution; doing it unattributed is generally treated worse rather
  than better. Reducing granularity is the part that lowers exposure. The label is not.
- **The path and response key still read `pff`.** `/api/nfl/players/{id}/pff` and the
  `pff` key are visible to anyone opening devtools. Renaming them would obscure provenance
  for maintainers; if end-user inspection is a concern, that is a separate decision.

There is a happy accident here. `CAPABILITIES.md` already warns that unit cards are
"honest at the top-five and bottom-five grain; adjacent ranks are noise" — so showing a
rank and a tier rather than a grade to one decimal is *both* the lower-exposure choice and
the more honest one.

---

## 7. Making it worth returning to

Stickiness comes from speed and recall, not from decoration.

**Search is the primary interface.** `⌘K` or `/` opens a palette over players, teams,
coaches and pages. Teams for **both** leagues are fetched once and filtered locally, so
searching "Georgia" works without first flipping the league switch and returns instantly.
Players go to the engine's alias-normalized endpoint (`tj watt` finds T.J. Watt),
debounced at 200 ms, aborted on the next keystroke. Prefix matches sort first, then the
active league.

**Keyboard throughout.** `1`–`6` jump between sections, `L` flips league, `T` flips theme,
`?` lists the rest. Arrow keys and Enter drive the palette.

**State persists.** Watchlist, recently-viewed trail and the compare tray survive reloads
via `localStorage`. The slate surfaces a "on your watchlist" section above the day groups
when a followed team is playing.

**Compare is two clicks.** Stage teams from the list or from any team page; a floating
tray shows what is staged from anywhere in the app. Capped at four, because a fifth column
stops being readable on a laptop — the oldest drops out rather than the click doing
nothing.

**Motion is functional.** Staggered entrances (capped at 12 so a 200-row table does not
cascade for four seconds), animated rank bars, count-ups on headline figures, skeletons
shaped like the content they replace. All of it collapses under
`prefers-reduced-motion: reduce`.

**Live engine status.** The header polls `/football/health` every 30 s and shows a pulsing
dot, so "the engine is down" never presents as "the app is broken".

---

## 8. Bugs found and fixed while building

Recorded because each was invisible until something specific was tried:

- **A shared aborted promise deadlocked every first load.** The fetch cache de-duplicated
  concurrent requests by key, and React StrictMode's mount → unmount → remount cycle made
  the second mount adopt the promise the first had already aborted. It never settled, so
  the page loaded forever with no error. In-flight entries are now refcounted and dropped
  synchronously on abort, so a remount starts a fresh request.
- **The compare tray was never centred.** It positions with `translateX(-50%)`, and its
  shared fade-up animation ended on `transform: none` — animation fills beat base rules,
  so the offset was erased on the final frame. It has its own keyframe now. On a phone it
  ran clean off the right edge.
- **The navigation rail showed under the mobile tab bar.** The `max-width: 980px`
  override was written *above* the base `.rail` rule; equal specificity means source order
  decides, and the base rule won.
- **Every college spread and moneyline was missing.** Described in §4.
- **The rank bar mixed two scales.** Fill length was a percentile while the league-average
  marker was placed on the value's magnitude, so the two could not be compared. Length is
  now the value's share of a real maximum when one exists and the percentile only when it
  does not.
- **Defense cards read empty.** The offense card returns `epa`; the defense card returns
  `epa_allowed`. Components written against the offense shape rendered dashes.
- **Quarterbacks had a receiving table.** Mahomes has one target in 2024 and one in 2025.
  Stat groups now need a volume floor, not a non-zero value.

---

## 9. Known gaps

- **NCAAF player pages do not exist.** CFBD's REST endpoints omit player ids from
  play-by-play, so college is game-markets-first. College players appear in search results
  and are visibly not clickable, rather than 404-ing.
- **The legacy Flask surfaces are gone** — scoreboard, saved picks, live alerts, auth.
  They belonged to the basketball-era product and are not reachable from this app.
- **No tests.** The app was verified by driving it against the live engine; there is no
  automated suite.
- **`web/` at the repo root is dead** — a CRA skeleton with no `src/`. Untouched here.

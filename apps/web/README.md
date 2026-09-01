# TheBetLab — web

React + Vite front end for the football engine. It talks to one API and renders what
that API returns; there is no second source of truth and no mock data anywhere in the
bundle.

This is an npm workspace, so dependencies install from the **repo root** — there is one
lockfile there and none in this directory:

```bash
npm install          # at the repo root
npm run dev          # http://localhost:5173  (or `npm run dev` from the root)
npm run build        # -> dist/
```

The dev server proxies `/api` to `http://localhost:8000`, so start the engine first
(`make up` at the repo root). To point somewhere else, copy `.env.example` to `.env.local`
and set `ENGINE_URL`.

That override exists because `docker compose` bind-mounts the **main checkout's**
`apps/engine/src`. Engine changes made in a git worktree are invisible to the container on
:8000 until they are merged. To run a second engine against the same database while working
in a worktree:

```bash
docker run -d --name youredge-engine-wt --network youredge_default -p 8010:8000   -e DATABASE_URL='postgresql+asyncpg://youredge:youredge_dev@db:5432/youredge'   -e REDIS_URL='redis://redis:6379/0'   -v "$PWD/apps/engine/src:/app/src"   youredge-engine uvicorn youredge.api.main:app --host 0.0.0.0 --port 8000 --reload
```

then set `ENGINE_URL=http://localhost:8010`.

## What it shows

| Route | Reads |
|---|---|
| `/slate` | `GET /{league}/games` — schedule plus the best book's current price line |
| `/games/:league/:id` | game detail, both unit cards, and every book's board with line movement |
| `/teams` · `/teams/:league/:id` | unit cards, PFF grades and protection, pass-rate tendencies; NCAAF adds coaching, returning production and the portal |
| `/players` · `/players/:id` | bio, season aggregates, game log, PFF splits, opponent history, QB clutch, linked college career |
| `/coaches/:id` | a coach's full career across every school |
| `/compare` | up to four teams as columns over the same ranked rows |
| `/lab` | the four SGP modes, wired to the real endpoints |
| `/data` | coverage counted live by the engine, plus the caveats that travel with it |

## Naming: the "Analysis" tab

The grading and charting layer is licensed from PFF. In the UI those surfaces are labelled
**Analysis** and **Unit grades**, and no user-visible string names the vendor — a product
decision, deliberately made, not an oversight to be tidied up.

Renaming alone would have been cosmetic, so the amount of licensed data the browser can
reach was cut as well. Four endpoints take `detail=summary`, and `lib/api.js` sends it on
every call the app makes:

| Endpoint | `full` (default, for the reasoning layer) | `summary` (what the browser gets) |
|---|---|---|
| `/teams/{id}/units` | grade + league average + rank | rank, percentile, above/below the field |
| `/teams/{id}/protection` | + per-lineman grade, true pass set | counted events and our derived pressure rate |
| `/players/{id}/pff` | + grade + the complete export row | snaps, routes, slot/wide rate |
| `/players/{id}` | + per-facet grade | usage and alignment only |

The player endpoint drops from **126 KB to 4 KB** that way, because at full detail it was
shipping the vendor's export rows verbatim. `/pff/splits` returns those rows by design and
**no UI surface calls it**. What the client never requests, devtools cannot show.

Two things about all of this:

- **Provenance stays truthful everywhere else.** The tables are still `pff_player_stats`,
  the ingest is still `youredge.ingest.pff`, and `CAPABILITIES.md` still says where the
  numbers come from. Whoever maintains this has to know what the data is.
- **Omitting the name is not a legal control.** What carries licensing risk is
  redistributing proprietary grades to end users; doing it unattributed is generally
  treated worse than doing it attributed, not better. Reducing granularity — the table
  above — is the part that actually lowers exposure. The label is not.

There is a happy accident here. `CAPABILITIES.md` already warns that unit cards are
"honest at the top-five and bottom-five grain; adjacent ranks are noise" — so showing a
rank and a tier instead of a grade to one decimal is *both* the lower-exposure choice and
the more honest one.

## Three rules the code holds to

**Nothing is invented.** Every number on screen came from an engine response. Where a
surface is unbuilt the engine answers `501` with a phase marker, and the UI renders that
as a phase gate rather than a spinner, an error, or a plausible-looking number. This is
why `/lab` looks the way it does: no model has been trained, so no edge is quoted.

**Null is not zero.** A missing temperature means the reading was not reported — CFBD's
weather endpoint is paywalled — not that the game was calm or indoors. Absent values
render as an em dash everywhere, and `format.js` is the only place that decides so.

**One colour scale.** `scaleColor` maps a league percentile to a hue, and it is the only
thing that colours a rank. Green means the same on a team card, a PFF unit grade and a
protection row. The pass-rate heatmap is the one deliberate exception — there the two
colours mean direction, not quality — so it carries its own legend.

## Layout

```
src/
  lib/       api.js (every endpoint) · hooks.js (fetch cache) · format.js · store.jsx
  styles/    tokens.css (both themes) · base.css · components.css
  icons/     the whole icon set, as SVG paths in one module
  components/ AppShell · CommandPalette · GameCard · ui.jsx primitives
  pages/     one file per route
public/icons/ brand mark, favicon, wordmark — real .svg files
```

No icon font, no CDN, no emoji: every glyph is a path in `src/icons/index.jsx` or a file
in `public/icons/`.

## Naming

The product is **TheBetLab** (thebetlab.app) and the UI says so everywhere. The
repository, the Python package, the Docker containers and the database are still
`youredge` — renaming those touches volumes, container names and an installed package,
which is infrastructure work rather than a rebrand, and none of it is user-visible.

Persisted preferences moved from the `ye.` prefix to `tbl.`, with a one-time copy in
`store.jsx`. Renaming the prefix alone would not error; it would just read nothing and
hand every existing user an empty watchlist and the default theme.

## Keyboard

`⌘K` or `/` opens the palette (players, teams, coaches, pages). `1`–`6` jump between
sections, `L` flips league, `T` flips theme, `?` lists the rest.

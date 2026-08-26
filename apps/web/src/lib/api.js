/* ── Engine client ────────────────────────────────────────────────────────────
   One place that knows the shape of the API. Everything else in the app calls a
   named function here, so a route change is a one-file edit.

   Two behaviours worth knowing about:

   • 501 is not an error. The engine returns it with a `phase` marker for surfaces
     that are deliberately unbuilt (the simulator, SGP pricing). We convert those
     into a typed `NotBuiltYet` so the UI can say "Phase 1" instead of "Error".
   • 404 from a detail endpoint usually means "no rows for this team/season", not
     "bad URL" — the engine is explicit about that distinction, so we preserve it.
── */

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, { status, detail, url } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
  get isMissing() { return this.status === 404; }
}

export class NotBuiltYet extends Error {
  constructor({ phase, detail, url } = {}) {
    super(detail || 'Not built yet');
    this.name = 'NotBuiltYet';
    this.phase = phase;
    this.url = url;
  }
}

function qs(params = {}) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    // FastAPI reads repeated keys as a list — `seasons=2023&seasons=2024`.
    if (Array.isArray(v)) v.forEach((item) => sp.append(k, item));
    else sp.append(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export async function request(path, { params, signal, method = 'GET', body } = {}) {
  const url = `${BASE}${path}${qs(params)}`;
  let res;
  try {
    res = await fetch(url, {
      method,
      signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('Cannot reach the engine. Is it running on :8000?', { url });
  }

  const payload = await res.json().catch(() => null);

  if (res.status === 501) {
    throw new NotBuiltYet({
      phase: payload?.phase, detail: payload?.detail || payload?.error, url,
    });
  }
  if (!res.ok) {
    const detail = payload?.detail || payload?.error || `Request failed (${res.status})`;
    throw new ApiError(typeof detail === 'string' ? detail : 'Request failed',
      { status: res.status, detail, url });
  }
  return payload;
}

/* ── Cross-league ── */
export const getHealth   = (o) => request('/football/health', o);
export const getCoverage = (o) => request('/football/coverage', o);

/* ── Slate & matchups ── */
export const listTeams = (league, params, o) =>
  request(`/${league}/teams`, { params, ...o });
export const listGames = (league, params, o) =>
  request(`/${league}/games`, { params, ...o });
export const getGame = (league, gameId, o) =>
  request(`/${league}/games/${encodeURIComponent(gameId)}`, o);
export const getGameOdds = (league, gameId, params, o) =>
  request(`/${league}/games/${encodeURIComponent(gameId)}/odds`, { params, ...o });

/* ── Team surfaces ── */
const team = (league, id, suffix = '') =>
  `/${league}/teams/${encodeURIComponent(id)}${suffix}`;

export const getOffense    = (league, id, params, o) => request(team(league, id, '/offense'), { params, ...o });
export const getDefense    = (league, id, params, o) => request(team(league, id, '/defense'), { params, ...o });
// `detail: 'summary'` is the default here, not in the engine. These three endpoints
// carry licensed evaluation data at full detail, and the browser is an end-user surface —
// what it never requests, it never receives, and devtools cannot show. The reasoning
// layer calls the same endpoints without the flag and still gets everything.
const summary = (params) => ({ detail: 'summary', ...params });

export const getUnits      = (league, id, params, o) => request(team(league, id, '/units'), { params: summary(params), ...o });
export const getProtection = (league, id, params, o) => request(team(league, id, '/protection'), { params: summary(params), ...o });
export const getAlignment  = (league, id, params, o) =>
  request(team(league, id, '/offense/receiver-alignment'), { params, ...o });
export const getAbsence = (league, id, side, params, o) =>
  request(team(league, id, `/${side}/absence`), { params, ...o });
export const getPassRate = (league, params, o) =>
  request(`/${league}/tendencies/pass-rate`, { params, ...o });

/* ── NCAAF-only ── */
export const getCoaching  = (id, params, o) => request(team('ncaaf', id, '/coaching'), { params, ...o });
export const getContext   = (id, params, o) => request(team('ncaaf', id, '/context'), { params, ...o });
export const getTransfers = (id, params, o) => request(team('ncaaf', id, '/transfers'), { params, ...o });
export const searchCoaches = (params, o) => request('/ncaaf/coaches', { params, ...o });
export const getCoach = (id, o) => request(`/ncaaf/coaches/${encodeURIComponent(id)}`, o);

/* ── Players (NFL) ── */
const player = (id, suffix = '') => `/nfl/players/${encodeURIComponent(id)}${suffix}`;

export const searchPlayers = (params, o) => request('/nfl/players', { params, ...o });
export const getPlayer     = (id, params, o) => request(player(id), { params: summary(params), ...o });
export const getGamelog    = (id, params, o) => request(player(id, '/gamelog'), { params, ...o });
export const getPlays      = (id, params, o) => request(player(id, '/plays'), { params, ...o });
export const getClutch     = (id, params, o) => request(player(id, '/clutch'), { params, ...o });
export const getCollege    = (id, o) => request(player(id, '/college'), o);
export const getVsOpponent = (id, params, o) => request(player(id, '/vs-opponent'), { params, ...o });
export const getPlayerPff  = (id, params, o) => request(player(id, '/pff'), { params: summary(params), ...o });
// Deliberately not called by the app. This returns the vendor's export rows verbatim,
// which is republication rather than analysis. It stays in the client for the reasoning
// layer and for one-off inspection, and no UI surface reaches for it.
export const getPffSplits  = (id, params, o) => request(player(id, '/pff/splits'), { params, ...o });

/* ── Bet Lab (Phase 2–3; every one of these throws NotBuiltYet today) ── */
export const sgpGenerate  = (body, o) => request('/football/sgp/generate', { method: 'POST', body, ...o });
export const sgpAnchor    = (body, o) => request('/football/sgp/build-around-pick', { method: 'POST', body, ...o });
export const sgpHypothesis= (body, o) => request('/football/sgp/test-hypothesis', { method: 'POST', body, ...o });
export const sgpCritique  = (body, o) => request('/football/sgp/critique', { method: 'POST', body, ...o });
export const sgpHistory   = (o) => request('/football/sgp/history', o);

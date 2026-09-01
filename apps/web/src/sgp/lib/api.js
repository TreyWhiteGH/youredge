// SGP API service layer

const BASE = '';

async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function fetchFootballOdds({ league, gameId, sportsbook }) {
  const params = new URLSearchParams({ league, game_id: gameId, sportsbook });
  return apiFetch(`/api/football/odds?${params}`);
}

export async function generateSGP(payload) {
  return apiFetch('/api/football/sgp/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function buildAroundPick(payload) {
  return apiFetch('/api/football/sgp/build-around-pick', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function testHypothesis(payload) {
  return apiFetch('/api/football/sgp/test-hypothesis', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function critiqueSGP(payload) {
  return apiFetch('/api/football/sgp/critique', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function saveSGP(payload) {
  return apiFetch('/api/football/sgp/save', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchSGPHistory() {
  return apiFetch('/api/football/sgp/history');
}

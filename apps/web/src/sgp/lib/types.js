// Shared constants and mock data for SGP Lab

export const LEAGUES = [
  { id: 'NFL', label: 'NFL' },
  { id: 'NCAAF', label: 'NCAAF' },
];

export const SPORTSBOOKS = [
  { id: 'draftkings', label: 'DraftKings' },
  { id: 'fanduel', label: 'FanDuel' },
  { id: 'betmgm', label: 'BetMGM' },
  { id: 'caesars', label: 'Caesars' },
  { id: 'other', label: 'Other' },
];

export const RISK_MODES = [
  { id: 'sharp', label: 'Sharp', desc: '2 legs max · High conviction only', maxLegs: 2 },
  { id: 'balanced', label: 'Balanced', desc: '2–3 legs · Edge-first', maxLegs: 3 },
  { id: 'lotto', label: 'Lotto', desc: '3–5 legs · High upside', maxLegs: 5 },
];

export const SGP_MODES = [
  {
    id: 'generate',
    label: 'Generate Best SGP',
    subtitle: 'Pick a game and let YourEdge find the best same-game angle.',
    icon: '⚡',
  },
  {
    id: 'build',
    label: 'Build Around My Pick',
    subtitle: 'Already like a side, total, or player prop? Build the smartest SGP around it.',
    icon: '🎯',
  },
  {
    id: 'hypothesis',
    label: 'Test My Hypothesis',
    subtitle: 'Turn your football theory into a structured bet.',
    icon: '🧪',
  },
  {
    id: 'critique',
    label: 'Critique My SGP',
    subtitle: 'Paste your slip and YourEdge will find weak legs, conflicts, and better versions.',
    icon: '🔬',
  },
];

export const RECOMMENDATION_CONFIG = {
  'Playable small': { color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/30', dot: 'bg-blue-400' },
  'Strong edge': { color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/30', dot: 'bg-emerald-400' },
  'Lean': { color: 'text-yellow-400', bg: 'bg-yellow-400/10 border-yellow-400/30', dot: 'bg-yellow-400' },
  'No bet at this price': { color: 'text-slate-400', bg: 'bg-slate-400/10 border-slate-400/30', dot: 'bg-slate-400' },
  'Reject': { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30', dot: 'bg-red-500' },
};

export const CORRELATION_CONFIG = {
  'Negative but coherent': { color: 'text-blue-400', bg: 'bg-blue-400/10' },
  'Positive correlation': { color: 'text-emerald-400', bg: 'bg-emerald-400/10' },
  'Garbage-time volume': { color: 'text-purple-400', bg: 'bg-purple-400/10' },
  'Usage concentration': { color: 'text-orange-400', bg: 'bg-orange-400/10' },
  'Conflicting scripts': { color: 'text-red-400', bg: 'bg-red-400/10' },
  'Lotto only': { color: 'text-yellow-400', bg: 'bg-yellow-400/10' },
};

export const MOCK_GAMES = [
  {
    id: 'nfl_ravens_bengals',
    league: 'NFL',
    away: { abbrev: 'BAL', name: 'Ravens' },
    home: { abbrev: 'CIN', name: 'Bengals' },
    date: 'Sun · 8:20 PM ET',
    spread: { favorite: 'Ravens', line: -6.5 },
    total: 47.5,
    moneyline: { away: -260, home: 215 },
    sportsbook: 'DraftKings',
    oddsUpdated: '3 min ago',
    stale: false,
  },
  {
    id: 'nfl_chiefs_broncos',
    league: 'NFL',
    away: { abbrev: 'KC', name: 'Chiefs' },
    home: { abbrev: 'DEN', name: 'Broncos' },
    date: 'Sun · 4:25 PM ET',
    spread: { favorite: 'Chiefs', line: -7.0 },
    total: 44.5,
    moneyline: { away: -320, home: 255 },
    sportsbook: 'DraftKings',
    oddsUpdated: '47 min ago',
    stale: true,
  },
  {
    id: 'ncaaf_alabama_georgia',
    league: 'NCAAF',
    away: { abbrev: 'ALA', name: 'Alabama' },
    home: { abbrev: 'UGA', name: 'Georgia' },
    date: 'Sat · 3:30 PM ET',
    spread: { favorite: 'Alabama', line: -4.5 },
    total: 52.0,
    moneyline: { away: -185, home: 155 },
    sportsbook: 'FanDuel',
    oddsUpdated: '12 min ago',
    stale: false,
  },
  {
    id: 'ncaaf_ohio_michigan',
    league: 'NCAAF',
    away: { abbrev: 'OSU', name: 'Ohio State' },
    home: { abbrev: 'MICH', name: 'Michigan' },
    date: 'Sat · 12:00 PM ET',
    spread: { favorite: 'Ohio State', line: -3.5 },
    total: 49.0,
    moneyline: { away: -165, home: 140 },
    sportsbook: 'FanDuel',
    oddsUpdated: '8 min ago',
    stale: false,
  },
];

export const MOCK_LEGS = {
  nfl_ravens_bengals: [
    { id: 'bal_spread', label: 'Ravens -6.5', market: 'Spread', odds: -110 },
    { id: 'cin_spread', label: 'Bengals +6.5', market: 'Spread', odds: -110 },
    { id: 'game_over', label: 'Game Over 47.5', market: 'Total', odds: -110 },
    { id: 'game_under', label: 'Game Under 47.5', market: 'Total', odds: -110 },
    { id: 'bal_ml', label: 'Ravens ML -260', market: 'Moneyline', odds: -260 },
    { id: 'cin_ml', label: 'Bengals ML +215', market: 'Moneyline', odds: 215 },
    { id: 'cin_qb_over', label: 'Bengals QB Over 245.5 Pass Yds', market: 'QB Pass Yards', odds: -115 },
    { id: 'cin_qb_under', label: 'Bengals QB Under 245.5 Pass Yds', market: 'QB Pass Yards', odds: -105 },
    { id: 'bal_rb_over', label: 'Ravens RB Over 72.5 Rush Yds', market: 'RB Rush Yards', odds: -110 },
    { id: 'cin_wr_rec', label: 'Bengals WR Over 5.5 Receptions', market: 'WR Receptions', odds: -120 },
    { id: 'bal_1h', label: 'Ravens -3.5 1H', market: '1H Spread', odds: -115 },
  ],
  nfl_chiefs_broncos: [
    { id: 'kc_spread', label: 'Chiefs -7.0', market: 'Spread', odds: -110 },
    { id: 'den_spread', label: 'Broncos +7.0', market: 'Spread', odds: -110 },
    { id: 'kc_ml', label: 'Chiefs ML -320', market: 'Moneyline', odds: -320 },
    { id: 'mah_over', label: 'Mahomes Over 275.5 Pass Yds', market: 'QB Pass Yards', odds: -115 },
    { id: 'kc_rb_over', label: 'Chiefs RB Over 58.5 Rush Yds', market: 'RB Rush Yards', odds: -110 },
    { id: 'kelce_rec', label: 'Kelce Over 5.5 Receptions', market: 'TE Receptions', odds: -130 },
    { id: 'game_over_kc', label: 'Game Over 44.5', market: 'Total', odds: -110 },
  ],
  ncaaf_alabama_georgia: [
    { id: 'ala_spread', label: 'Alabama -4.5', market: 'Spread', odds: -110 },
    { id: 'uga_spread', label: 'Georgia +4.5', market: 'Spread', odds: -110 },
    { id: 'ala_1h', label: 'Alabama -3.5 1H', market: '1H Spread', odds: -115 },
    { id: 'game_over_al', label: 'Game Over 52.0', market: 'Total', odds: -110 },
    { id: 'uga_qb_over', label: 'Georgia QB Over 220.5 Pass Yds', market: 'QB Pass Yards', odds: -110 },
    { id: 'ala_rb_over', label: 'Alabama RB Over 95.5 Rush Yds', market: 'RB Rush Yards', odds: -115 },
  ],
  ncaaf_ohio_michigan: [
    { id: 'osu_spread', label: 'Ohio State -3.5', market: 'Spread', odds: -110 },
    { id: 'mich_spread', label: 'Michigan +3.5', market: 'Spread', odds: -110 },
    { id: 'game_over_om', label: 'Game Over 49.0', market: 'Total', odds: -110 },
    { id: 'osu_ml', label: 'Ohio State ML -165', market: 'Moneyline', odds: -165 },
  ],
};

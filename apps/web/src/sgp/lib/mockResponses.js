// Mock API responses for development/demo when backend endpoints aren't live

export const MOCK_GENERATE_RESPONSE = {
  league: 'NFL',
  game: 'Ravens @ Bengals',
  mode: 'auto_generate',
  odds_source: 'odds_api',
  odds_last_updated: new Date(Date.now() - 3 * 60000).toISOString(),
  single_leg_odds_fetched: true,
  sgp_price_source: 'manual_user_input',
  sgp_price_required: false,
  best_sgp: {
    sgp_type: 'garbage_time_volume',
    correlation_type: 'Negative but coherent',
    detected_script: 'Ravens lead and cover while Bengals throw heavily in catch-up mode.',
    legs: [
      {
        selection: 'Ravens -6.5',
        market: 'Spread',
        line: -6.5,
        odds_american: -110,
        model_probability: 0.56,
        reason: 'Ravens project to control early downs and finish drives better.',
      },
      {
        selection: 'Bengals QB Over 245.5 Passing Yards',
        market: 'QB Pass Yards',
        line: 245.5,
        odds_american: -110,
        model_probability: 0.57,
        reason: 'If Cincinnati trails, pass volume rises enough to support the yardage over.',
      },
    ],
    naive_probability: 0.319,
    correlation_adjustment: 0.82,
    model_probability: 0.262,
    sportsbook_price: '+390',
    sportsbook_implied_probability: 0.204,
    fair_price: '+282',
    minimum_playable_price: '+335',
    estimated_edge: 0.058,
    grade: 'A-',
    risk_level: 'Medium-High',
    script_confidence: 78,
    leg_fit_score: 84,
    price_score: 82,
    thesis: 'Ravens lead and cover while Cincinnati throws heavily in catch-up mode.',
    main_risk: 'If Baltimore dominates defensively and Cincinnati drives stall, the passing yardage leg may fail.',
    recommendation: 'Playable small',
  },
};

export const MOCK_BUILD_RESPONSE = {
  anchor: { selection: 'Ravens -6.5', market: 'Spread', type: 'Favorite spread' },
  implied_script: [
    'Ravens lead early',
    'Bengals trail and shift to pass-heavy offense',
    'Ravens lean run late to drain clock',
    'Backdoor cover risk if Bengals score garbage-time TDs',
  ],
  best_adds: [
    {
      selection: 'Bengals QB Over 245.5 Pass Yds',
      market: 'QB Pass Yards',
      fit: 'Strong',
      reason: 'Trailing script supports heavy pass volume for Bengals QB.',
    },
    {
      selection: 'Bengals WR Over 5.5 Receptions',
      market: 'WR Receptions',
      fit: 'Strong',
      reason: 'Short-area volume can rise while the Bengals chase the game.',
    },
    {
      selection: 'Ravens RB Over 72.5 Rush Yds',
      market: 'RB Rush Yards',
      fit: 'Medium',
      reason: 'Favorite leading creates clock-drain rushing attempts in the second half.',
    },
  ],
  avoid: [
    {
      selection: 'Bengals RB Over 52.5 Rush Yds',
      market: 'RB Rush Yards',
      reason: 'Trailing script severely limits Bengals rushing volume.',
    },
    {
      selection: 'Ravens QB Over 235.5 Pass Yds',
      market: 'QB Pass Yards',
      reason: 'Leading Ravens may abandon the pass entirely in the second half.',
    },
    {
      selection: 'Game Under 47.5',
      market: 'Total',
      reason: 'Conflicts if Bengals garbage-time passing converts into late scoring.',
    },
  ],
  best_build: {
    legs: ['Ravens -6.5', 'Bengals QB Over 245.5 Pass Yds'],
    minimum_playable_price: '+340',
    recommendation: 'Playable only if the book offers +340 or better.',
    grade: 'B+',
    correlation_type: 'Negative but coherent',
  },
};

export const MOCK_HYPOTHESIS_RESPONSE = {
  detected_hypothesis: 'Favorite blowout with underdog garbage-time volume',
  script_tags: [
    'favorite_cover',
    'favorite_fast_start',
    'underdog_trailing',
    'garbage_time_passing',
    'second_half_soft_coverage',
    'backdoor_risk',
  ],
  best_markets: [
    { rank: 1, market: 'Favorite spread', fit: 'Strong', reason: 'Core expression of the blowout thesis.' },
    { rank: 2, market: 'Favorite 1H spread', fit: 'Strong', reason: 'Fast start thesis should show in first half.' },
    { rank: 3, market: 'Underdog QB passing over', fit: 'Strong', reason: 'Trailing script forces pass volume.' },
    { rank: 4, market: 'Underdog WR receptions over', fit: 'Medium', reason: 'Short routes increase when chasing.' },
    { rank: 5, market: 'Favorite RB rushing over', fit: 'Medium', reason: 'Leader controlling clock encourages runs.' },
  ],
  avoid_markets: [
    { market: 'Underdog RB rushing over', reason: 'Trailing script kills rushing volume.' },
    { market: 'Favorite QB passing over (late)', reason: 'Leading favorite may pull QB late.' },
    { market: 'Full-game under', reason: 'High garbage-time scoring risk.' },
  ],
  best_sgp: {
    legs: ['Favorite 1H spread', 'Underdog QB passing over'],
    reason: 'Expresses the fast start + catch-up passing script cleanly with positive correlation.',
    grade: 'B+',
    recommendation: 'Playable small if priced +280 or better.',
  },
};

export const MOCK_CRITIQUE_RESPONSE = {
  overall_grade: 'C-',
  issue: 'This SGP mixes scripts.',
  conflicts: [
    {
      type: 'Script conflict',
      description: 'Chiefs -7.5 + Chiefs RB rushing over points to a lead/control script. Mahomes passing over needs sustained pass volume, which disappears when Kansas City leads comfortably.',
    },
  ],
  leg_verdicts: [
    { selection: 'Chiefs -7.5', verdict: 'keep', reason: 'Clean anchor. Fits control script.' },
    { selection: 'Mahomes Over 275.5 Pass Yds', verdict: 'maybe', reason: 'Only viable if opponent keeps pace. Conflicts with comfort-lead script.' },
    { selection: 'Chiefs RB Over 58.5 Rush Yds', verdict: 'remove', reason: 'Mixing rushing script with high pass volume is incoherent.' },
  ],
  cleaner_version: {
    legs: ['Chiefs -7.5', 'Chiefs RB Over 58.5 Rush Yds'],
    type: 'Favorite control script',
    grade: 'B',
    recommendation: 'Playable at +260 or better.',
  },
  aggressive_version: {
    legs: ['Chiefs -7.5', 'Mahomes Over 275.5 Pass Yds', 'Kelce Over 5.5 Receptions'],
    type: 'High-volume passing script',
    grade: 'C+',
    recommendation: 'Lotto only. Needs +420 or better.',
  },
  overall_recommendation: 'No bet as built.',
};

export const MOCK_HISTORY = [
  {
    id: 'h1',
    date: '2026-09-14',
    league: 'NFL',
    game: 'Ravens @ Bengals',
    legs: ['Ravens -6.5', 'Bengals QB Over 245.5'],
    recommendation: 'Playable small',
    grade: 'A-',
    book_price: '+390',
    fair_price: '+282',
    min_playable_price: '+335',
    result: null,
    script_type: 'Garbage-time volume',
    sportsbook: 'DraftKings',
  },
  {
    id: 'h2',
    date: '2026-09-07',
    league: 'NFL',
    game: 'Chiefs @ Broncos',
    legs: ['Chiefs -7.0', 'Chiefs RB Over 58.5'],
    recommendation: 'Lean',
    grade: 'B',
    book_price: '+280',
    fair_price: '+245',
    min_playable_price: '+265',
    result: 'win',
    script_type: 'Favorite control',
    sportsbook: 'FanDuel',
  },
  {
    id: 'h3',
    date: '2026-09-01',
    league: 'NCAAF',
    game: 'Alabama @ Georgia',
    legs: ['Alabama -4.5', 'Alabama 1H -3.5', 'Georgia QB Over 220.5'],
    recommendation: 'No bet at this price',
    grade: 'C+',
    book_price: '+520',
    fair_price: '+610',
    min_playable_price: '+580',
    result: 'loss',
    script_type: 'Blowout + garbage time',
    sportsbook: 'BetMGM',
  },
];

// Simulate API delay
export function mockDelay(ms = 1800) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

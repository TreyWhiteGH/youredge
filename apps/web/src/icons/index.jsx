/* ── TheBetLab icon set ───────────────────────────────────────────────────────
   Hand-drawn on a 24×24 grid, stroked in `currentColor` at 1.6 so weight matches
   Inter's at body sizes. No icon font, no CDN, no emoji — every glyph in the app
   is a path in this file, which means it themes, scales, and diffs like code.

   Usage: <Icon.Search size={16} />  ·  colour comes from the parent's `color`.
── */

import React from 'react';

function Svg({ size = 18, children, fill = 'none', ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/* ── Brand ── */
// A flask whose contents are a rising line: the lab is where the question gets tested,
// the line is what you are testing for. The flask takes `currentColor` so it follows
// the theme's accent, while the line inside stays on the "good" hue — the one place in
// the app where those two colours are deliberately shown together.
export const Logo = ({ size = 26 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M9.6 3.6v5.6l-4.9 9.0a1.6 1.6 0 0 0 1.4 2.4h11.8a1.6 1.6 0 0 0 1.4-2.4l-4.9-9.0V3.6"
      stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    <path d="M8.2 3.6h7.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    <path d="M7.3 16.6l3.1-2.9 2.2 1.8 3.6-4.2" stroke="var(--good)" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="10.4" cy="13.7" r="1.25" fill="var(--good)" />
  </svg>
);

/* ── Navigation ── */
export const Search = (p) => (
  <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-3.6-3.6" /></Svg>
);
export const Slate = (p) => (
  <Svg {...p}>
    <rect x="3" y="4.5" width="18" height="16" rx="2.5" /><path d="M3 9.5h18" />
    <path d="M8 3v3M16 3v3" /><path d="M7.5 13.5h3M13.5 13.5h3M7.5 17h3" />
  </Svg>
);
// A shield reads "team" faster than a jersey does at 16px.
export const Teams = (p) => (
  <Svg {...p}><path d="M12 3 4.5 6v6c0 4.4 3.1 7.9 7.5 9 4.4-1.1 7.5-4.6 7.5-9V6L12 3Z" />
    <path d="M9.2 11.8 11.3 14l3.6-3.9" /></Svg>
);
export const Players = (p) => (
  <Svg {...p}><circle cx="12" cy="8" r="3.6" />
    <path d="M4.8 20.2a7.2 7.2 0 0 1 14.4 0" /></Svg>
);
// Balance scale — a price weighed against a probability.
export const Odds = (p) => (
  <Svg {...p}><path d="M12 4v16M7 20h10" /><path d="M4 8h16" />
    <path d="M4 8 1.8 13.2a2.6 2.6 0 0 0 4.4 0L4 8Z" />
    <path d="M20 8l-2.2 5.2a2.6 2.6 0 0 0 4.4 0L20 8Z" /></Svg>
);
export const Lab = (p) => (
  <Svg {...p}><path d="M9.5 3v6.1L4.4 17.6A2 2 0 0 0 6.1 20.7h11.8a2 2 0 0 0 1.7-3.1L14.5 9.1V3" />
    <path d="M8.2 3h7.6" /><path d="M7 14.6h10" /></Svg>
);
export const Data = (p) => (
  <Svg {...p}><ellipse cx="12" cy="6" rx="7.5" ry="3" />
    <path d="M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" />
    <path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" /></Svg>
);
export const Compare = (p) => (
  <Svg {...p}><rect x="3" y="4" width="7" height="16" rx="1.6" />
    <rect x="14" y="4" width="7" height="16" rx="1.6" /><path d="M10.5 12h3" /></Svg>
);

/* ── Football domain ── */
export const Football = (p) => (
  <Svg {...p}><path d="M4.4 19.6C2.4 15 3 7.9 5.4 5.5 7.8 3.1 15 2.5 19.6 4.4c1.9 4.6 1.3 11.7-1.1 14.1-2.4 2.4-9.5 3-14.1 1.1Z" />
    <path d="m8.6 15.4 6.8-6.8" /><path d="M10.4 11.6 12 13.2M12.6 9.4l1.6 1.6" /></Svg>
);
export const Whistle = (p) => (
  <Svg {...p}><path d="M13.5 8.5H21l-1.8 5.2a6.2 6.2 0 1 1-5.7-8.3v3.1Z" />
    <circle cx="8.6" cy="13.4" r="2" /></Svg>
);
export const Field = (p) => (
  <Svg {...p}><rect x="2.5" y="5.5" width="19" height="13" rx="1.6" />
    <path d="M12 5.5v13" /><path d="M7.2 5.5v13M16.8 5.5v13" />
    <path d="M2.5 9.5h2.2v5H2.5M21.5 9.5h-2.2v5h2.2" /></Svg>
);
export const Shield = (p) => (
  <Svg {...p}><path d="M12 3 4.5 6v6c0 4.4 3.1 7.9 7.5 9 4.4-1.1 7.5-4.6 7.5-9V6L12 3Z" /></Svg>
);
export const Trophy = (p) => (
  <Svg {...p}><path d="M7.5 4h9v5.5a4.5 4.5 0 0 1-9 0V4Z" />
    <path d="M7.5 5.5H4.8V8a3.2 3.2 0 0 0 3.2 3.2M16.5 5.5h2.7V8a3.2 3.2 0 0 1-3.2 3.2" />
    <path d="M12 14v3.5M8.8 20.5h6.4l-.8-3H9.6l-.8 3Z" /></Svg>
);

/* ── Signals ── */
export const TrendUp = (p) => (
  <Svg {...p}><path d="M3 17.5 9.5 11l4 4 7.5-7.5" /><path d="M15.5 7.5H21v5.5" /></Svg>
);
export const TrendDown = (p) => (
  <Svg {...p}><path d="M3 6.5 9.5 13l4-4 7.5 7.5" /><path d="M15.5 16.5H21V11" /></Svg>
);
export const Activity = (p) => (
  <Svg {...p}><path d="M2.5 12h4l2.5-7 4.5 14 2.7-7h5.3" /></Svg>
);
// Broadcast signal — arcs radiating from a point. Reads as "on air" at 16px, and is
// distinct from Activity's waveform, which means something else in this app.
export const Live = (p) => (
  <Svg {...p}><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
    <path d="M8.1 15.9a5.5 5.5 0 0 1 0-7.8M15.9 8.1a5.5 5.5 0 0 1 0 7.8" />
    <path d="M5.3 18.7a9.5 9.5 0 0 1 0-13.4M18.7 5.3a9.5 9.5 0 0 1 0 13.4" /></Svg>
);
export const Bolt = (p) => (
  <Svg {...p}><path d="M13.3 2.5 4.5 13.6h6.2l-.9 7.9 8.8-11.1h-6.2l.9-7.9Z" /></Svg>
);
export const Layers = (p) => (
  <Svg {...p}><path d="m12 3 8.5 4.5L12 12 3.5 7.5 12 3Z" />
    <path d="m3.5 12 8.5 4.5L20.5 12" /><path d="m3.5 16.5 8.5 4.5 8.5-4.5" /></Svg>
);
export const Grid = (p) => (
  <Svg {...p}><rect x="3.5" y="3.5" width="7" height="7" rx="1.4" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.4" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.4" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.4" /></Svg>
);

/* ── Conditions ── */
export const Wind = (p) => (
  <Svg {...p}><path d="M3 8.5h10.2a2.8 2.8 0 1 0-2.8-2.8" />
    <path d="M3 15.5h13.4a2.8 2.8 0 1 1-2.8 2.8" /><path d="M3 12h7.5" /></Svg>
);
export const Thermometer = (p) => (
  <Svg {...p}><path d="M14 14.8V5.5a2 2 0 1 0-4 0v9.3a4.2 4.2 0 1 0 4 0Z" />
    <path d="M12 9.5v6.8" /></Svg>
);
export const Dome = (p) => (
  <Svg {...p}><path d="M3 13a9 9 0 0 1 18 0" /><path d="M2 13h20" />
    <path d="M3.5 13v6.5h17V13" /><path d="M9.5 19.5V15h5v4.5" /></Svg>
);
export const Mountain = (p) => (
  <Svg {...p}><path d="M2.5 19.5 9 7.5l4 6.6 2.4-3.6 6.1 9H2.5Z" />
    <path d="m6.6 12 2.4-1.4 1.8 1.4" /></Svg>
);

/* ── Interface ── */
export const Star = ({ size = 18, filled = false, ...rest }) => (
  <Svg size={size} fill={filled ? 'currentColor' : 'none'} {...rest}>
    <path d="m12 3.6 2.6 5.4 5.9.8-4.3 4.2 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.8l5.9-.8L12 3.6Z" />
  </Svg>
);
export const ChevronRight = (p) => <Svg {...p}><path d="m9.5 5 7 7-7 7" /></Svg>;
export const ChevronLeft  = (p) => <Svg {...p}><path d="m14.5 5-7 7 7 7" /></Svg>;
export const ChevronDown  = (p) => <Svg {...p}><path d="m5 9.5 7 7 7-7" /></Svg>;
export const ChevronUp    = (p) => <Svg {...p}><path d="m5 14.5 7-7 7 7" /></Svg>;
export const Close = (p) => <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>;
export const Check = (p) => <Svg {...p}><path d="m4.5 12.5 5 5 10-11" /></Svg>;
export const Plus  = (p) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>;
export const Minus = (p) => <Svg {...p}><path d="M5 12h14" /></Svg>;
export const Sun = (p) => (
  <Svg {...p}><circle cx="12" cy="12" r="4.2" />
    <path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" /></Svg>
);
export const Moon = (p) => (
  <Svg {...p}><path d="M20.5 14.3A8.6 8.6 0 0 1 9.7 3.5a8.7 8.7 0 1 0 10.8 10.8Z" /></Svg>
);
export const Info = (p) => (
  <Svg {...p}><circle cx="12" cy="12" r="8.8" /><path d="M12 11v5.2" />
    <path d="M12 7.9h.01" strokeWidth="2.1" /></Svg>
);
export const Alert = (p) => (
  <Svg {...p}><path d="M12 3.8 21.2 20H2.8L12 3.8Z" /><path d="M12 10v4.2" />
    <path d="M12 17.4h.01" strokeWidth="2.1" /></Svg>
);
export const Lock = (p) => (
  <Svg {...p}><rect x="4.5" y="10.5" width="15" height="10" rx="2.2" />
    <path d="M8 10.5V7.6a4 4 0 0 1 8 0v2.9" /></Svg>
);
export const Clock = (p) => (
  <Svg {...p}><circle cx="12" cy="12" r="8.8" /><path d="M12 7v5.3l3.4 2" /></Svg>
);
export const Refresh = (p) => (
  <Svg {...p}><path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1" /><path d="M20.5 4v5h-5" /></Svg>
);
export const SortArrows = (p) => (
  <Svg {...p}><path d="M8 4.5v15M8 4.5 4.8 8M8 4.5 11.2 8" />
    <path d="M16 19.5v-15M16 19.5 12.8 16M16 19.5l3.2-3.5" /></Svg>
);
export const External = (p) => (
  <Svg {...p}><path d="M14 4h6v6" /><path d="m20 4-8.5 8.5" />
    <path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H10" /></Svg>
);
export const CommandKey = (p) => (
  <Svg {...p}><path d="M8.5 6.5a2.5 2.5 0 1 0-2.5 2.5h12a2.5 2.5 0 1 0-2.5-2.5v11a2.5 2.5 0 1 0 2.5-2.5H6a2.5 2.5 0 1 0 2.5 2.5v-11Z" /></Svg>
);
export const Book = (p) => (
  <Svg {...p}><path d="M4 4.8A1.8 1.8 0 0 1 5.8 3H19v18H5.8A1.8 1.8 0 0 1 4 19.2V4.8Z" />
    <path d="M4 17.2h15" /></Svg>
);

export default {
  Logo, Search, Slate, Teams, Players, Odds, Lab, Data, Compare,
  Football, Whistle, Field, Shield, Trophy,
  TrendUp, TrendDown, Activity, Bolt, Layers, Grid, Live,
  Wind, Thermometer, Dome, Mountain,
  Star, ChevronRight, ChevronLeft, ChevronDown, ChevronUp,
  Close, Check, Plus, Minus, Sun, Moon, Info, Alert, Lock, Clock,
  Refresh, SortArrows, External, CommandKey, Book,
};

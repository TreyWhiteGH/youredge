/* ── Team mark ────────────────────────────────────────────────────────────────
   A team's visual identity: its own colour, and a monogram.

   No logo is rendered, deliberately. Logos are trademarks held by the clubs, the
   leagues, or a licensing arm, and this is a betting product — a context rights-holders
   treat far more carefully than a scores site. The `teams.logo_url` reference is still
   stored so the option survives a licensing decision, but nothing here reaches for it,
   and there is no setting that turns it on by accident.

   Colour carries the recognition anyway. A slate of twenty cards reads as twenty
   different teams on hue alone.
── */

import React from 'react';

/** Team colours are stored as bare hex. Anything malformed falls back rather than
 *  emitting `#undefined` into a style attribute. */
export function teamColor(team, fallback = 'var(--text-faint)') {
  const c = team?.color;
  if (!c || !/^[0-9a-f]{6}$/i.test(c)) return fallback;
  return `#${c}`;
}

/** Two or three letters that read as the team: a real abbreviation where one exists,
 *  otherwise initials from the name — "North Carolina State" becomes NCS, not "NOR". */
export function monogram(team) {
  const abbr = team?.abbr;
  if (abbr && abbr.length <= 4 && abbr === abbr.toUpperCase()) return abbr;
  const words = (team?.name || '').split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.slice(0, 3).map((w) => w[0]).join('').toUpperCase();
}

export default function TeamMark({ team, size = 24, className = '' }) {
  return (
    <span
      className={`team-mark ${className}`}
      style={{
        width: size, height: size,
        '--tm-color': teamColor(team, 'var(--border-loud)'),
        fontSize: Math.max(8, Math.round(size * 0.34)),
      }}
      title={team?.name}
    >
      <span className="tm-text">{monogram(team)}</span>
    </span>
  );
}

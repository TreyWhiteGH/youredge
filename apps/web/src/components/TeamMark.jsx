/* ── Team mark ────────────────────────────────────────────────────────────────
   A team's visual identity, in one component so the product decision behind it
   lives in one place.

   Logos are trademarks belonging to the clubs, the leagues, or a licensing arm, and
   this is a betting product — a context rights-holders treat more carefully than a
   scores site. So the mark is a setting, not an assumption. With logos off, a team
   still gets its own colour and monogram, which carries the recognition without
   reproducing anyone's artwork; the app never looks generic either way.

   The image is referenced from its origin and never copied into this repo.
── */

import React, { useState } from 'react';
import { useApp } from '../lib/store';

/** Team colours are stored as bare hex. Some come back near-white or near-black,
 *  which disappears against one theme or the other, so they are used as an accent
 *  rather than as text and get a floor on contrast. */
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
  const { showLogos } = useApp();
  const [failed, setFailed] = useState(false);
  const color = teamColor(team, 'var(--border-loud)');

  const useLogo = showLogos && team?.logo && !failed;

  return (
    <span
      className={`team-mark ${className}`}
      style={{
        width: size, height: size,
        // The colour shows through as a ring either way, so a team is identifiable
        // even while its logo is still loading — or permanently, if logos are off.
        '--tm-color': color,
        fontSize: Math.max(8, Math.round(size * 0.34)),
      }}
      title={team?.name}
    >
      {useLogo ? (
        <img
          src={team.logo}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="tm-text">{monogram(team)}</span>
      )}
    </span>
  );
}

"""Turn PFF's wide split tables into structured comparisons.

PFF split facets encode a matrix in flat column names: passing_depth carries
16 zones (behind_los/short/medium/deep x left/center/right + totals) as
`deep_grades_pass`, `left_short_attempts`, ...; passing_pressure carries
pressure/no_pressure/blitz/no_blitz; passing_concept carries pa/npa/screen/
no_screen. That's 177-558 columns per facet — unusable as typed columns and
unusable by an LLM that would have to memorize the names.

This module derives the split vocabulary from the data itself (no hardcoded
column lists, so new PFF facets work automatically) and regroups a flat row
into {split: {metric: value}}. Longest-prefix matching keeps 'no_pressure'
from being read as split 'no' + metric 'pressure_...'.
"""

from typing import Any

# Metrics that appear exactly once per split; used to discover prefixes.
ANCHORS = ("_grades_pass", "_attempts", "_completion_percent", "_snap_counts",
           "_sacks", "_targets", "_yards", "_snaps", "_dropbacks")


def derive_splits(keys: list[str]) -> list[str]:
    """Split prefixes present in a row, longest first."""
    for anchor in ANCHORS:
        prefixes = {k[: -len(anchor)] for k in keys if k.endswith(anchor) and len(k) > len(anchor)}
        if len(prefixes) >= 2:
            return sorted(prefixes, key=len, reverse=True)
    return []


def group_by_split(row: dict[str, Any]) -> dict[str, Any]:
    """Flat PFF row -> {"splits": {split: {metric: val}}, "base": {leftovers}}."""
    keys = list(row.keys())
    prefixes = derive_splits(keys)
    splits: dict[str, dict[str, Any]] = {p: {} for p in prefixes}
    base: dict[str, Any] = {}

    for key, val in row.items():
        match = next((p for p in prefixes if key.startswith(p + "_")), None)
        if match is None:
            base[key] = val
        else:
            splits[match][key[len(match) + 1:]] = val

    return {"splits": {k: v for k, v in splits.items() if v}, "base": base}


def compare(row: dict[str, Any], metrics: list[str] | None = None) -> dict[str, Any]:
    """Grouped view, optionally narrowed to the metrics that matter.

    Narrowing is what makes this LLM-friendly: ask for grades_pass + btt_rate
    and get a 4-row table instead of a 177-column dump.
    """
    grouped = group_by_split(row)
    if not metrics:
        return grouped
    narrowed = {
        split: {m: vals.get(m) for m in metrics if m in vals}
        for split, vals in grouped["splits"].items()
    }
    return {"splits": {k: v for k, v in narrowed.items() if v}, "base": grouped["base"]}

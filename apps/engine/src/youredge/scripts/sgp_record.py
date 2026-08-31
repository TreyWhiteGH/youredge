"""Load observed sportsbook prices back in, and report how the model did.

The sheet goes out with two empty columns; you fill them from the book and this
reads them back. Each observed price becomes a `user_bets` row, which is what
`pricing.sgp.book_margin` fits against once a book has enough of them at a given
leg count.

It also prints the comparison immediately, because a stack of stored rows is not
feedback. What is useful is knowing which half of the model missed: the estimate
splits into a joint and a margin, and the direction of the error says which one
to distrust. If every design misses by roughly the same proportion, the margin
prior is wrong and the correlation is fine — that is one number to change. If the
reinforcing slips miss one way and the conflicting ones the other, the
correlation is wrong and the margin is fine, which is a much larger job.

    docker compose run --rm ingest python -m youredge.scripts.sgp_sheet --csv > sheet.csv
    # fill actual_draftkings / actual_fanduel from the books
    docker compose run --rm ingest python -m youredge.scripts.sgp_record --file sheet.csv

A single slip, without the round trip:

    docker compose run --rm ingest python -m youredge.scripts.sgp_record \\
        --game nfl:2026_01_NE_SEA --book draftkings --price +265 \\
        --legs "SEA -3.5" "over 44.5"
"""

import argparse
import asyncio
import csv
import logging
import sys

from youredge.db import get_engine
from youredge.legs import ledger_bets
from youredge.legs.critique import parse_leg
from youredge.pricing import sgp as sgp_model
from youredge.pricing.fair_value import price_leg

log = logging.getLogger(__name__)

BOOKS = ("draftkings", "fanduel")


async def _price_legs(conn, game_id: str, book: str, raws: list[str]):
    priced, missing = [], []
    for raw in raws:
        leg = await parse_leg(conn, game_id, raw)
        if not leg:
            missing.append(raw)
            continue
        p = await price_leg(conn, game_id, leg["market_key"], leg["outcome"],
                            leg["line"], book, subject=leg.get("subject"))
        if p.fair_prob is None:
            missing.append(raw)
            continue
        priced.append({**leg, "raw": raw, "fair_prob": p.fair_prob,
                       "pricing": {"fair_prob": p.fair_prob,
                                   "book_price": p.book_price,
                                   "edge": p.edge,
                                   "quotable": not p.is_stale}})
    return priced, missing


async def record_one(conn, league: str, game_id: str, book: str,
                     raws: list[str], observed: int) -> dict | None:
    """Store one observed quote and return how the estimate compared."""
    priced, missing = await _price_legs(conn, game_id, book, raws)
    if missing or len(priced) < 2:
        log.warning("skipped %s (%s): could not price %s",
                    game_id, book, missing or "fewer than two legs")
        return None

    est = await sgp_model.estimate(conn, league, book, priced)
    await ledger_bets.record(
        conn,
        {"game_id": game_id,
         "legs": priced,
         "quoted_odds": str(observed)},
        league=league, sportsbook=book, mode="manual")

    obs_p = ledger_bets.american_to_prob(observed)
    est_p = ledger_bets.american_to_prob(est["estimated_book_price"])
    return {
        "game_id": game_id, "book": book, "legs": len(priced),
        "estimated": est["estimated_book_price"], "observed": observed,
        # Positive means the book is paying less than we expected, i.e. it holds
        # more than the model assumed or the legs are more correlated than the
        # counted surface says.
        "error_pct": round((obs_p / est_p - 1) * 100, 1),
        "implied_margin": round(obs_p / est["joint"] - 1, 4),
        "corr": est["correlation_multiplier"],
    }


async def from_csv(path: str) -> list[dict]:
    out = []
    async with get_engine().begin() as conn:
        with open(path) as fh:
            for row in csv.DictReader(fh):
                raws = [x.strip() for x in row["legs"].split("|") if x.strip()]
                for book in BOOKS:
                    cell = (row.get(f"actual_{book}") or "").strip()
                    if not cell:
                        continue
                    try:
                        observed = int(cell.lstrip("+"))
                    except ValueError:
                        log.warning("not a price: %r for %s", cell, book)
                        continue
                    r = await record_one(conn, row["league"], row["game_id"],
                                         book, raws, observed)
                    if r:
                        out.append({**r, "design": row.get("design", "")})
    return out


def report(rows: list[dict]) -> None:
    if not rows:
        print("Nothing loaded. Fill actual_draftkings / actual_fanduel and retry.")
        return
    print(f"\n{len(rows)} observed quotes recorded.\n")
    hdr = f"{'design':<18} {'book':<11} {'n':>2} {'est':>7} {'actual':>7} {'miss':>7} {'corr':>6}"
    print(hdr); print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: (x["design"], x["book"])):
        print(f"{r['design']:<18} {r['book']:<11} {r['legs']:>2} "
              f"{r['estimated']:>+7d} {r['observed']:>+7d} "
              f"{r['error_pct']:>+6.1f}% {r['corr']:>6.2f}")

    # The diagnosis this whole exercise exists for.
    by_book: dict[str, list[float]] = {}
    for r in rows:
        by_book.setdefault(r["book"], []).append(r["error_pct"])
    print()
    for book, errs in by_book.items():
        errs.sort()
        median = errs[len(errs) // 2]
        spread = errs[-1] - errs[0]
        print(f"{book}: median miss {median:+.1f}%, spread {spread:.1f} points "
              f"over {len(errs)} quotes")
    print(
        "\nA consistent miss in one direction is the margin prior, and it is one\n"
        "number to change. A miss that flips sign between reinforcing and\n"
        "conflicting designs is the correlation, which is a real problem. Twelve\n"
        "quotes per book per leg count replaces the prior with a fitted margin."
    )


async def main(args) -> None:
    if args.file:
        report(await from_csv(args.file))
        return
    if not (args.game and args.book and args.price and args.legs):
        sys.exit("need --file, or all of --game --book --price --legs")
    league = args.game.split(":", 1)[0]
    async with get_engine().begin() as conn:
        r = await record_one(conn, league, args.game, args.book, args.legs,
                             int(str(args.price).lstrip("+")))
    report([{**r, "design": "manual"}] if r else [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="a sheet CSV with actual_* columns filled in")
    ap.add_argument("--game")
    ap.add_argument("--book", choices=BOOKS)
    ap.add_argument("--price", help="the book's quote, e.g. +265")
    ap.add_argument("--legs", nargs="+")
    asyncio.run(main(ap.parse_args()))

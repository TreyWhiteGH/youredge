"""Train a spread-residual model and store its weights as data.

Target is the residual against the CLOSING line, not the game outcome. That choice is
the whole discipline: a model that merely rediscovers the spread scores exactly zero,
so any signal here is signal the market missed. The holdout gate is ATS record against
the closer — a model that can't beat it doesn't get promoted, and that result gets
reported plainly rather than buried.

Weights land in model_runs/model_weights so retraining is a data change, not a deploy,
and the Narrator can quote what the model currently believes.

Usage:
    docker compose run --rm ingest python -m youredge.modeling.train --league nfl --holdout 2025
"""

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Differentials, not raw sides: the market prices the matchup, so the model should see
# the same thing. Keeps the feature count low, which matters at this sample size.
# The shared base: play-derived form, rest, and the market's own number. Both leagues
# have these and both models use them.
BASE_FEATURES = [
    "off_epa_diff", "def_epa_diff", "off_pass_epa_diff", "off_rush_epa_diff",
    "def_pass_epa_diff", "def_rush_epa_diff", "off_success_diff", "pass_rate_diff",
    "prev_off_epa_diff", "prev_def_epa_diff", "rest_diff", "closing_spread",
]

# Two models, one base. What each league adds is genuinely different, so the feature
# sets diverge here rather than being forced into a single list that would be half
# missing for whichever league you are training.
#
# NCAAF's additions come from game_features.features (JSONB) and are known before
# kickoff: who is coaching, how much production returned, recruited talent, altitude.
# NFL's additions (PFF pressure/protection, NGS, usage) are not wired into
# game_features yet — when they are, they belong in this dict, not in BASE_FEATURES.
EXTRA_FEATURES = {
    "nfl": [],
    "ncaaf": [
        "coach_resid_diff", "coach_history_min", "pct_ppa_diff", "usage_diff",
        "talent_diff", "recruiting_diff", "sp_prev_diff", "elevation",
    ],
}

# Each league declares its OWN list rather than inheriting all of BASE_FEATURES.
# That is the whole point of two models: NFL's signal is accumulated in-season form,
# which it has for every game; NCAAF's is preseason context, which it has back to 2016
# while its play data starts in 2023. Forcing college to require play-derived form
# would throw away 7 of its 10 seasons - 8,576 usable games down to 1,043 - to satisfy
# a shared column list that buys it nothing.
FEATURES_BY_LEAGUE = {
    "nfl": BASE_FEATURES,
    "ncaaf": ["closing_spread"] + EXTRA_FEATURES["ncaaf"],
}

# Features where NULL means "no track record" rather than "unknown value". Filled with
# a neutral 0 and paired with a _known indicator, so the model can separate a coach
# with a genuinely average residual from one who has never been a head coach.
NEUTRAL_FILL = {"coach_resid_diff", "coach_history_min"}

# Before this many games, in-season form is noise pretending to be signal. NCAAF is
# exempt because its extra features are preseason facts, not accumulated form — the
# 2016-2022 college rows have no play data at all and would otherwise be discarded.
MIN_PRIOR_GAMES = {"nfl": 3, "ncaaf": 0}


def build_frame(rows: list[dict], extra: list[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Lift league-specific JSONB keys into columns; booleans become 0/1 so the
    # linear model can use them.
    for key in extra or []:
        df[key] = [
            (float(v) if not isinstance(v, bool) else float(v))
            if (v := (r.get("features") or {}).get(key)) is not None else None
            for r in rows
        ]
    for base in ("off_epa", "def_epa", "off_pass_epa", "off_rush_epa",
                 "def_pass_epa", "def_rush_epa", "off_success", "pass_rate"):
        df[f"{base}_diff"] = df[f"home_{base}"] - df[f"away_{base}"]
    df["prev_off_epa_diff"] = df.home_prev_season_off_epa - df.away_prev_season_off_epa
    df["prev_def_epa_diff"] = df.home_prev_season_def_epa - df.away_prev_season_def_epa
    df["rest_diff"] = df.home_rest_days.fillna(7) - df.away_rest_days.fillna(7)
    return df


async def train(league: str, holdout_season: int) -> dict:
    engine = get_engine()
    async with engine.begin() as conn:
        minp = MIN_PRIOR_GAMES[league]
        rows = [dict(r) for r in (await conn.execute(
            text("""
                SELECT * FROM game_features
                WHERE league = :league AND spread_residual IS NOT NULL
                  AND COALESCE(home_prior_games, 0) >= :minp
                  AND COALESCE(away_prior_games, 0) >= :minp
            """),
            {"league": league, "minp": minp},
        )).mappings()]

        features = [f for f in FEATURES_BY_LEAGUE[league] if True]
        df = build_frame(rows, EXTRA_FEATURES[league])

        # Neutral-fill before dropping, so "first-time head coach" survives as a row
        # with an explicit indicator instead of vanishing from the sample.
        FEATURES = []
        for f in features:
            if f not in df.columns:
                continue
            if f in NEUTRAL_FILL:
                df[f + "_known"] = df[f].notna().astype(float)
                df[f] = df[f].fillna(0.0)
                FEATURES.append(f + "_known")
            FEATURES.append(f)
        df = df.dropna(subset=FEATURES + ["spread_residual"])
        train_df = df[df.season != holdout_season]
        test_df = df[df.season == holdout_season]
        log.info("train %d games (seasons %s) | holdout %d games (%d)",
                 len(train_df), sorted(train_df.season.unique().tolist()),
                 len(test_df), holdout_season)
        if len(test_df) < 30 or len(train_df) < 100:
            raise SystemExit("not enough data to train honestly")

        X, y = train_df[FEATURES].to_numpy(float), train_df.spread_residual.to_numpy(float)
        Xt, yt = test_df[FEATURES].to_numpy(float), test_df.spread_residual.to_numpy(float)
        mu, sd = X.mean(0), np.where(X.std(0) == 0, 1, X.std(0))

        model = RidgeCV(alphas=np.logspace(-1, 4, 40)).fit((X - mu) / sd, y)
        pred = model.predict((Xt - mu) / sd)

        # Baseline is the market: predict zero residual, i.e. "the closer is right".
        rmse = float(np.sqrt(((pred - yt) ** 2).mean()))
        base_rmse = float(np.sqrt((yt ** 2).mean()))

        # ATS: bet the side the model favours; pushes excluded.
        played = pred != 0
        won = ((pred > 0) & (yt > 0)) | ((pred < 0) & (yt < 0))
        push = yt == 0
        wins, losses = int((won & ~push).sum()), int((~won & ~push & played).sum())
        ats = wins / (wins + losses) if wins + losses else None

        # Only act on real disagreement with the market; small edges are noise.
        strong = np.abs(pred) >= 3.0
        s_won = int((won & strong & ~push).sum())
        s_lost = int((~won & strong & ~push).sum())
        strong_ats = s_won / (s_won + s_lost) if s_won + s_lost else None

        metrics = {
            "holdout_season": holdout_season, "train_games": len(train_df),
            "holdout_games": len(test_df), "rmse": round(rmse, 3),
            "market_baseline_rmse": round(base_rmse, 3),
            "rmse_improvement": round(base_rmse - rmse, 3),
            "ats_record": f"{wins}-{losses}",
            "ats_pct": round(ats, 4) if ats else None,
            "strong_ats_record": f"{s_won}-{s_lost}",
            "strong_ats_pct": round(strong_ats, 4) if strong_ats else None,
            "breakeven": 0.5238,  # -110 juice
            "alpha": float(model.alpha_),
        }

        run_id = (await conn.execute(
            text("""
                INSERT INTO model_runs (league, target, model_type, train_seasons,
                                        holdout_season, n_train, n_holdout, metrics)
                VALUES (:lg, 'spread_residual', 'ridge', :tr, :ho, :ntr, :nho,
                        CAST(:m AS jsonb))
                RETURNING run_id
            """),
            {"lg": league, "tr": sorted(train_df.season.unique().tolist()),
             "ho": holdout_season, "ntr": len(train_df), "nho": len(test_df),
             "m": json.dumps(metrics)},
        )).scalar_one()

        for name, coef in zip(FEATURES, model.coef_):
            await conn.execute(
                text("""
                    INSERT INTO model_weights (run_id, feature, weight, importance)
                    VALUES (:r, :f, :w, :i)
                """),
                {"r": run_id, "f": name, "w": float(coef), "i": abs(float(coef))},
            )

    return {"run_id": run_id, "metrics": metrics,
            "weights": dict(zip(FEATURES, [round(float(c), 4) for c in model.coef_]))}


async def main(league: str, holdout: int):
    out = await train(league, holdout)
    m = out["metrics"]
    log.info("run %s | RMSE %.3f vs market baseline %.3f (improvement %.3f)",
             out["run_id"], m["rmse"], m["market_baseline_rmse"], m["rmse_improvement"])
    log.info("ATS %s (%s) | strong picks %s (%s) | breakeven %.4f",
             m["ats_record"], m["ats_pct"], m["strong_ats_record"],
             m["strong_ats_pct"], m["breakeven"])
    for f, w in sorted(out["weights"].items(), key=lambda kv: -abs(kv[1])):
        log.info("   %-22s %+.4f", f, w)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default="nfl")
    parser.add_argument("--holdout", type=int, default=2025)
    args = parser.parse_args()
    asyncio.run(main(args.league, args.holdout))

import logging
import os
import uuid
import datetime
from flask import Flask, jsonify, request, g

from .config import config
from .picks_logic import build_game_context, compute_pick_progress
from .scores.providers import get_provider
from .odds.providers import get_odds_provider
from .odds.providers.odds_api import OddsApiError
from .user_store import (
    get_user_picks,
    create_or_login_user,
    register_user,
    user_from_token,
    add_user_pick,
    update_user_pick,
    delete_user_pick,
    get_user_pick_by_id,
    get_user_tier,
    set_user_tier,
    get_user_alert_preferences,
    update_user_alert_preferences,
)
from .alerts.alert_detector import (
    get_user_active_alerts,
    mark_alert_viewed,
    dismiss_alert,
)

LOG_LEVEL = config.get("app.log_level", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("backend")

app = Flask(__name__)
provider = get_provider()
odds_provider = get_odds_provider()

# Initialize ML model server (optional, feature-flagged)
model_server = None
if config.get("features.ml_enabled", False):
    try:
        logger.info("Attempting to initialize betting model server...")
        from .ml.model_server import BettingModelServer

        models_dir = config.get("paths.models_dir", "/tmp/models")
        project_id = config.get_secret("GOOGLE_CLOUD_PROJECT")

        logger.info(
            "Model server configuration",
            extra={
                "models_dir": models_dir,
                "has_project_id": bool(project_id),
                "project_id": project_id[:20] + "..." if project_id else None,
            },
        )

        model_server = BettingModelServer(models_dir, project_id)
        logger.info(
            "Betting model server initialized successfully",
            extra={
                "models_dir": models_dir,
                "project_id": project_id,
            },
        )
    except ImportError as exc:
        logger.warning(
            "Model server module not available (this is expected if ML features are not installed)",
            extra={"error": str(exc)},
        )
    except Exception as exc:
        logger.error(
            "Failed to initialize betting model server",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": f"{exc}",
            },
        )
else:
    logger.info("ML features disabled in configuration")

# Initialize AI Picks Generator components
picks_generator = None
try:
    logger.info("Initializing AI Picks Generator components...")
    from .ml.data_collection import HistoricalDataCollector
    from .ml.features import NBAFeatureExtractor
    from .ml.parlay_builder import ParlayBuilder
    from .ml.prompt_interpreter import PromptInterpreter
    from .ml.reasoning import ReasoningGenerator
    import os

    # Initialize components
    db_path = config.get("paths.data_db", os.path.join(os.path.dirname(__file__), "data", "historical_games.db"))
    collector = HistoricalDataCollector(db_path)
    extractor = NBAFeatureExtractor(collector)
    parlay_builder = ParlayBuilder()
    prompt_interpreter = PromptInterpreter()
    reasoning_generator = ReasoningGenerator()

    picks_generator = {
        "collector": collector,
        "extractor": extractor,
        "parlay_builder": parlay_builder,
        "prompt_interpreter": prompt_interpreter,
        "reasoning_generator": reasoning_generator,
    }
    logger.info("AI Picks Generator components initialized successfully")
except ImportError as exc:
    logger.warning("AI Picks Generator components not available", extra={"error": str(exc)})
except Exception as exc:
    logger.error("Failed to initialize AI Picks Generator components", extra={"error": str(exc)})

# Cache for daily picks (simple in-memory cache)
_daily_picks_cache = {}

# Initialize daily picks scheduler
picks_scheduler = None
if picks_generator:
    try:
        logger.info("Initializing daily picks scheduler...")
        from .ml.scheduler import init_scheduler
        init_scheduler(picks_generator)
        from .ml.scheduler import get_scheduler
        picks_scheduler = get_scheduler()
        if picks_scheduler:
            logger.info("Daily picks scheduler initialized successfully")
    except ImportError:
        logger.warning("Scheduler module not available")
    except Exception as exc:
        logger.error(f"Failed to initialize scheduler: {exc}")


@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    """Shutdown scheduler when app closes."""
    if picks_scheduler:
        try:
            from .ml.scheduler import stop_scheduler
            stop_scheduler()
        except Exception as exc:
            logger.error(f"Error stopping scheduler: {exc}")


@app.before_request
def add_request_context():
    g.request_id = str(uuid.uuid4())
    g.user_id = _auth_user_id()
    logger.info(
        "Request start",
        extra={
            "path": request.path,
            "method": request.method,
            "request_id": g.request_id,
            "query_params": dict(request.args),
        },
    )


@app.after_request
def log_response(response):
    logger.info(
        "Request end",
        extra={
            "path": request.path,
            "method": request.method,
            "status": response.status_code,
            "request_id": getattr(g, "request_id", None),
        },
    )
    return response


@app.route("/api/sports-summary")
def sports_summary():
    """Get game counts for all sports (today)."""
    date_param = request.args.get("date")
    day_offset = request.args.get("dayOffset", default=0, type=int)

    sports_data = []

    for sport in provider.supported_sports():
        try:
            payload = provider.fetch_scoreboard(
                sport_id=sport,
                date=date_param,
                day_offset=day_offset,
            )
            game_count = len(payload.get("events", []))
            sports_data.append({
                "sport": sport,
                "game_count": game_count,
            })
        except Exception as exc:
            logger.warning(
                "Failed to fetch scoreboard for sports summary",
                extra={
                    "sport": sport,
                    "error": str(exc),
                    "request_id": g.get("request_id"),
                },
            )
            sports_data.append({
                "sport": sport,
                "game_count": 0,
            })

    return jsonify({
        "sports": sorted(sports_data, key=lambda x: x["game_count"], reverse=True),
        "requested": {
            "date": date_param,
            "dayOffset": day_offset,
        },
    })


@app.route("/api/scoreboard")
def scoreboard():
    sport = (request.args.get("sport") or "nba").lower()
    if sport not in provider.supported_sports():
        logger.warning(
            "Unsupported sport for scoreboard",
            extra={"sport": sport, "provider": provider.id, "request_id": g.get("request_id")},
        )
        return jsonify({"error": f"Unsupported sport '{sport}' for provider {provider.id}"}), 400

    date_param = request.args.get("date")
    day_offset = request.args.get("dayOffset", default=None, type=int)

    try:
        payload = provider.fetch_scoreboard(
            sport_id=sport,
            date=date_param,
            day_offset=day_offset,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Scoreboard fetch failed",
            extra={
                "sport": sport,
                "date": date_param,
                "dayOffset": day_offset,
                "provider": provider.id,
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to fetch scoreboard: {exc}"}), 502

    return jsonify(
        {
            "requested": {
                "sport": sport,
                "date": date_param,
                "dayOffset": day_offset,
            },
            "scoreboard": payload,
        }
    )


@app.route("/api/picks")
def picks():
    sport = (request.args.get("sport") or "nba").lower()
    user_id = g.user_id or request.args.get("userId", "demo")
    date_param = request.args.get("date")
    day_offset = request.args.get("dayOffset", default=None, type=int)

    user_picks = get_user_picks(user_id)
    if sport:
        user_picks = [p for p in user_picks if (p.get("sport") or sport).lower() == sport]

    # Group picks by (sport, date) to minimize fetches
    grouped = {}
    for pick in user_picks:
        pick_sport = (pick.get("sport") or sport).lower()
        pick_date = pick.get("event_date") or date_param
        grouped.setdefault((pick_sport, pick_date), []).append(pick)

    scoreboards = {}
    for (spt, dt), picks_list in grouped.items():
        try:
            sb = provider.fetch_scoreboard(sport_id=spt, date=dt, day_offset=day_offset)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Scoreboard fetch failed for picks",
                extra={
                    "sport": spt,
                    "date": dt,
                    "provider": provider.id,
                    "request_id": g.get("request_id"),
                },
            )
            sb = None
        scoreboards[(spt, dt)] = sb

    enriched = []
    for pick in user_picks:
        pick_sport = (pick.get("sport") or sport).lower()
        pick_date = pick.get("event_date") or date_param
        sb = scoreboards.get((pick_sport, pick_date))
        event = _find_event(sb, pick.get("event_id")) if sb else None
        progress = compute_pick_progress(pick, event)
        enriched.append(
            {
                **pick,
                "progress": progress,
                "game_context": build_game_context(event),
            }
        )

    return jsonify(
        {
            "requested": {"sport": sport, "date": date_param, "dayOffset": day_offset, "user": user_id},
            "picks": enriched,
        }
    )


@app.route("/api/odds")
def odds():
    sport = (request.args.get("sport") or "nba").lower()
    regions = request.args.get("regions")
    markets = request.args.get("markets")
    odds_format = request.args.get("oddsFormat")
    date_format = request.args.get("dateFormat")

    try:
        odds_payload = odds_provider.fetch_odds(
            sport_id=sport,
            regions=regions,
            markets=markets,
            odds_format=odds_format,
            date_format=date_format,
        )
    except OddsApiError as exc:
        logger.warning(
            "Odds provider error",
            extra={
                "sport": sport,
                "regions": regions or "us",
                "markets": markets or "all",
                "provider": odds_provider.id,
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Odds fetch failed",
            extra={
                "sport": sport,
                "regions": regions or "us",
                "markets": markets or "all",
                "provider": odds_provider.id,
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to fetch odds: {exc}"}), 502

    return jsonify(
        {
            "requested": {
                "sport": sport,
                "regions": regions or "us",
                "markets": markets or "all",
                "oddsFormat": odds_format or "american",
                "dateFormat": date_format or "iso",
                "provider": odds_provider.id,
            },
            "odds": odds_payload,
        }
    )


def _find_event(scoreboard: dict, event_id: str):
    if not scoreboard or not event_id:
        return None
    for ev in scoreboard.get("events", []):
        if str(ev.get("id")) == str(event_id):
            return ev
    return None


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True, silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    try:
        token = create_or_login_user(username, password)
    except ValueError:
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"token": token, "userId": username})


@app.route("/api/register", methods=["POST"])
def register():
    payload = request.get_json(force=True, silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    try:
        token = register_user(username, password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"token": token, "userId": username})


@app.route("/api/generate-picks", methods=["POST"])
def generate_picks():
    """
    Generate AI-powered pick recommendations for games.

    Request JSON:
    {
        "sport": "nba" (default),
        "date": "YYYY-MM-DD" (optional, defaults to today),
        "markets": ["spread", "total"] (optional),
        "min_confidence": 0.58 (optional, default 0.58),
        "min_edge": 0.03 (optional, default 0.03)
    }

    Returns:
    {
        "picks": [
            {
                "event_id": "...",
                "matchup": "...",
                "predictions": [...],
                "game_context": {...}
            }
        ],
        "metadata": {
            "total_games": int,
            "recommended": int,
            "avg_confidence": float,
            "generated_at": timestamp,
            "disclaimer": "..."
        }
    }
    """
    if not model_server:
        logger.error(
            "Generate picks request rejected: model server not initialized",
            extra={
                "request_id": g.get("request_id"),
                "model_server_available": False,
            },
        )
        return (
            jsonify(
                {
                    "error": "Model server not available",
                    "message": "ML models are not loaded. Please try again later.",
                }
            ),
            503,
        )

    payload = request.get_json(force=True, silent=True) or {}
    sport = (payload.get("sport") or "nba").lower()
    date_param = payload.get("date")
    day_offset = payload.get("dayOffset", default=None, type=int)
    markets = payload.get("markets", ["spread", "total"])
    min_confidence = payload.get("min_confidence", 0.58)
    min_edge = payload.get("min_edge", 0.03)

    logger.info(
        "Generate picks request received",
        extra={
            "request_id": g.get("request_id"),
            "sport": sport,
            "date": date_param,
            "day_offset": day_offset,
            "markets": markets,
            "min_confidence": min_confidence,
            "min_edge": min_edge,
        },
    )

    # Validate sport
    if sport not in provider.supported_sports():
        logger.warning(
            "Unsupported sport requested for picks generation",
            extra={
                "request_id": g.get("request_id"),
                "sport": sport,
                "supported_sports": provider.supported_sports(),
            },
        )
        return (
            jsonify(
                {"error": f"Unsupported sport '{sport}'", "request_id": g.get("request_id")}
            ),
            400,
        )

    # Validate thresholds
    if not (0 <= min_confidence <= 1):
        logger.warning(
            "Invalid min_confidence threshold",
            extra={
                "request_id": g.get("request_id"),
                "min_confidence": min_confidence,
            },
        )
        return jsonify({"error": "min_confidence must be between 0 and 1"}), 400
    if min_edge < 0:
        logger.warning(
            "Invalid min_edge threshold",
            extra={
                "request_id": g.get("request_id"),
                "min_edge": min_edge,
            },
        )
        return jsonify({"error": "min_edge must be non-negative"}), 400

    try:
        # Fetch scoreboard
        logger.info(
            "Fetching scoreboard data",
            extra={
                "request_id": g.get("request_id"),
                "sport": sport,
                "date": date_param,
                "day_offset": day_offset,
            },
        )
        scoreboard = provider.fetch_scoreboard(
            sport_id=sport, date=date_param, day_offset=day_offset
        )
        events = scoreboard.get("events", [])

        logger.info(
            "Scoreboard fetched successfully",
            extra={
                "request_id": g.get("request_id"),
                "sport": sport,
                "total_events": len(events),
            },
        )

        picks = []
        total_confidence = 0
        qualified_picks = 0
        processed_events = 0
        skipped_events = 0

        for event in events:
            try:
                event_id = event.get("id")
                matchup = event.get("shortName") or event.get("name")
                status = event.get("status", {}).get("state")

                # Skip non-upcoming games
                if status not in {"pre", None}:
                    logger.debug(
                        "Skipping non-upcoming game",
                        extra={
                            "event_id": event_id,
                            "matchup": matchup,
                            "status": status,
                            "request_id": g.get("request_id"),
                        },
                    )
                    skipped_events += 1
                    continue

                processed_events += 1
                logger.debug(
                    "Processing upcoming game for predictions",
                    extra={
                        "event_id": event_id,
                        "matchup": matchup,
                        "request_id": g.get("request_id"),
                    },
                )

                # Build features from event data (simplified)
                features = _build_features_from_event(event)

                # Generate predictions from model
                logger.debug(
                    "Requesting predictions from model server",
                    extra={
                        "event_id": event_id,
                        "sport": sport,
                        "markets": markets,
                        "request_id": g.get("request_id"),
                    },
                )
                predictions = model_server.predict_game(
                    sport=sport,
                    game_id=event_id,
                    features=features,
                    markets=markets,
                )

                logger.debug(
                    "Model predictions received",
                    extra={
                        "event_id": event_id,
                        "prediction_count": len(predictions),
                        "request_id": g.get("request_id"),
                    },
                )

                # Filter by confidence and edge thresholds
                filtered_predictions = [
                    p
                    for p in predictions
                    if p.get("confidence", 0) >= min_confidence
                    and p.get("edge", 0) >= min_edge
                ]

                if filtered_predictions:
                    total_confidence += sum(
                        p.get("confidence", 0) for p in filtered_predictions
                    )
                    qualified_picks += len(filtered_predictions)

                    logger.debug(
                        "Qualified predictions added to picks",
                        extra={
                            "event_id": event_id,
                            "qualified_count": len(filtered_predictions),
                            "request_id": g.get("request_id"),
                        },
                    )

                    picks.append(
                        {
                            "event_id": event_id,
                            "matchup": matchup,
                            "status": status,
                            "home": event.get("home", {}),
                            "away": event.get("away", {}),
                            "predictions": filtered_predictions,
                            "game_context": build_game_context(event),
                        }
                    )
                else:
                    logger.debug(
                        "No predictions met confidence/edge thresholds",
                        extra={
                            "event_id": event_id,
                            "min_confidence": min_confidence,
                            "min_edge": min_edge,
                            "request_id": g.get("request_id"),
                        },
                    )

            except Exception as exc:
                logger.error(
                    "Error generating predictions for event",
                    extra={
                        "event_id": event.get("id"),
                        "sport": sport,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "request_id": g.get("request_id"),
                    },
                )
                continue

        # Sort by average confidence
        logger.info(
            "Event processing completed",
            extra={
                "request_id": g.get("request_id"),
                "sport": sport,
                "total_events": len(events),
                "processed_events": processed_events,
                "skipped_events": skipped_events,
                "picks_before_limit": len(picks),
                "qualified_picks": qualified_picks,
            },
        )

        picks = sorted(
            picks,
            key=lambda p: sum(
                pred.get("confidence", 0) for pred in p.get("predictions", [])
            ) / max(len(p.get("predictions", [])), 1),
            reverse=True,
        )

        logger.debug(
            "Picks sorted by confidence",
            extra={
                "request_id": g.get("request_id"),
                "sorted_count": len(picks),
            },
        )

        # Limit to 5 picks/day (responsible gambling)
        picks_before_limit = len(picks)
        picks = picks[:5]

        logger.debug(
            "Picks limited to responsible gambling threshold",
            extra={
                "request_id": g.get("request_id"),
                "picks_before_limit": picks_before_limit,
                "picks_after_limit": len(picks),
            },
        )

        avg_confidence = (
            total_confidence / qualified_picks if qualified_picks > 0 else 0
        )

        metadata = {
            "total_games": len(events),
            "recommended": qualified_picks,
            "avg_confidence": round(avg_confidence, 3),
            "generated_at": datetime.datetime.utcnow().isoformat(),
            "disclaimer": "These AI-generated picks are for informational purposes only. "
            "Always gamble responsibly and within your means. Past performance does not "
            "guarantee future results. Please verify all odds and terms before placing bets.",
        }

        logger.info(
            "Picks generated successfully",
            extra={
                "sport": sport,
                "date": date_param,
                "total_games": len(events),
                "recommended": qualified_picks,
                "final_picks": len(picks),
                "avg_confidence": avg_confidence,
                "request_id": g.get("request_id"),
            },
        )

        return jsonify({"picks": picks, "metadata": metadata})

    except Exception as exc:
        logger.error(
            "Generate picks failed",
            extra={
                "sport": sport,
                "date": date_param,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "request_id": g.get("request_id"),
                "traceback": f"{exc}",
            },
        )
        return jsonify({"error": f"Failed to generate picks: {exc}"}), 500


@app.route("/api/picks", methods=["POST"])
def create_pick():
    """
    Create a new pick for the user.

    Request JSON:
    {
        "sport": "nba",
        "event_id": "...",
        "bet_type": "spread|moneyline|total",
        "selection": "home|away|over|under",
        "line": -5.5,
        "odds": -110,
        "stake": 100,
        "confidence": 0.62,
        "rationale": "..."
    }

    Returns:
    {
        "pick": {...pick object...},
        "disclaimer": "..."
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    payload = request.get_json(force=True, silent=True) or {}

    # Validate required fields
    required_fields = [
        "sport",
        "event_id",
        "bet_type",
        "selection",
        "odds",
        "stake",
    ]
    missing = [f for f in required_fields if f not in payload]
    if missing:
        return (
            jsonify(
                {
                    "error": f"Missing required fields: {', '.join(missing)}",
                    "request_id": g.get("request_id"),
                }
            ),
            400,
        )

    # Validate bet type
    bet_type = payload.get("bet_type", "").lower()
    if bet_type not in {"spread", "moneyline", "total"}:
        return (
            jsonify(
                {
                    "error": f"Invalid bet_type '{bet_type}'. Must be spread, moneyline, or total",
                }
            ),
            400,
        )

    # Validate selection
    selection = payload.get("selection", "").lower()
    valid_selections = {
        "spread": {"home", "away", "h", "a"},
        "moneyline": {"home", "away", "h", "a"},
        "total": {"over", "under", "o", "u"},
    }
    if selection not in valid_selections.get(bet_type, set()):
        return (
            jsonify(
                {
                    "error": f"Invalid selection '{selection}' for bet_type '{bet_type}'",
                }
            ),
            400,
        )

    # Validate stake
    try:
        stake = float(payload.get("stake", 100))
        if stake <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "stake must be a positive number"}), 400

    # Validate odds
    try:
        odds = float(payload.get("odds", -110))
    except (ValueError, TypeError):
        return jsonify({"error": "odds must be a valid number"}), 400

    try:
        # Add pick to user
        pick = add_user_pick(
            user_id=user_id,
            pick_data={
                "sport": payload.get("sport", "").lower(),
                "event_id": payload.get("event_id"),
                "bet_type": bet_type,
                "selection": selection,
                "line": payload.get("line"),
                "odds": odds,
                "stake": stake,
                "confidence": payload.get("confidence"),
                "rationale": payload.get("rationale", ""),
            },
        )

        # Log to BigQuery if available
        if model_server and model_server.bq_client:
            try:
                row = {
                    "pick_id": pick.get("pick_id"),
                    "user_id": user_id,
                    "game_id": pick.get("event_id"),
                    "sport": pick.get("sport"),
                    "bet_type": pick.get("bet_type"),
                    "selection": pick.get("selection"),
                    "stake": pick.get("stake"),
                    "odds": pick.get("odds"),
                    "confidence": pick.get("confidence"),
                    "created_at": pick.get("created_at"),
                }
                model_server.bq_client.insert_rows("user_picks", [row])
            except Exception as exc:
                logger.warning(f"Failed to log pick to BigQuery: {exc}")

        logger.info(
            "Pick created",
            extra={
                "pick_id": pick.get("pick_id"),
                "user_id": user_id,
                "sport": pick.get("sport"),
                "bet_type": pick.get("bet_type"),
                "request_id": g.get("request_id"),
            },
        )

        return jsonify(
            {
                "pick": pick,
                "disclaimer": "This pick was created manually. Always verify odds and terms before betting.",
            }
        )

    except Exception as exc:
        logger.error(
            f"Create pick failed",
            extra={"user_id": user_id, "error": str(exc), "request_id": g.get("request_id")},
        )
        return jsonify({"error": f"Failed to create pick: {exc}"}), 500


@app.route("/api/picks/<pick_id>", methods=["PUT"])
def update_pick(pick_id):
    """
    Update an existing pick.

    Request JSON:
    {
        "status": "pending|won|lost|settled",
        "result": true|false|null,
        "profit": 50.5,
        "settled_at": "2024-01-15T10:30:00"
    }

    Returns:
    {
        "pick": {...updated pick...}
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    payload = request.get_json(force=True, silent=True) or {}

    try:
        # Get existing pick
        pick = get_user_pick_by_id(user_id, pick_id)
        if not pick:
            return jsonify({"error": f"Pick not found: {pick_id}"}), 404

        # Update pick
        updated_pick = update_user_pick(user_id, pick_id, payload)

        if not updated_pick:
            return jsonify({"error": f"Failed to update pick {pick_id}"}), 500

        logger.info(
            "Pick updated",
            extra={
                "pick_id": pick_id,
                "user_id": user_id,
                "status": updated_pick.get("status"),
                "request_id": g.get("request_id"),
            },
        )

        return jsonify({"pick": updated_pick})

    except Exception as exc:
        logger.error(
            f"Update pick failed",
            extra={
                "pick_id": pick_id,
                "user_id": user_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to update pick: {exc}"}), 500


@app.route("/api/picks/<pick_id>", methods=["DELETE"])
def delete_pick(pick_id):
    """
    Delete a pending pick.

    Only allows deletion of picks with status='pending'.

    Returns:
    {
        "deleted": true|false,
        "message": "..."
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        # Get existing pick
        pick = get_user_pick_by_id(user_id, pick_id)
        if not pick:
            return jsonify({"error": f"Pick not found: {pick_id}"}), 404

        # Check if pick is pending
        if pick.get("status") != "pending":
            return (
                jsonify(
                    {
                        "deleted": False,
                        "message": f"Cannot delete {pick.get('status')} pick. Only pending picks can be deleted.",
                    }
                ),
                400,
            )

        # Delete pick
        deleted = delete_user_pick(user_id, pick_id)

        if not deleted:
            return jsonify({"deleted": False, "message": "Failed to delete pick"}), 500

        logger.info(
            "Pick deleted",
            extra={
                "pick_id": pick_id,
                "user_id": user_id,
                "request_id": g.get("request_id"),
            },
        )

        return jsonify({"deleted": True, "message": f"Pick {pick_id} deleted successfully"})

    except Exception as exc:
        logger.error(
            f"Delete pick failed",
            extra={
                "pick_id": pick_id,
                "user_id": user_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to delete pick: {exc}"}), 500


@app.route("/api/live-alerts")
def get_live_alerts():
    """
    Get active EV-positive betting opportunities for the user.

    Returns:
    {
        "alerts": [
            {
                "alert_id": "...",
                "game_id": "...",
                "home_team": "...",
                "away_team": "...",
                "current_score": "...",
                "opportunity_type": "moneyline|spread|total",
                "pick": "home|away|over|under",
                "model_win_prob": 0.65,
                "market_odds": -110,
                "ev": {...},
                "recommendation": "strong_buy|buy|fair_value",
                "status": "new|viewed",
                "created_at": "...",
                "expires_at": "..."
            }
        ],
        "user": user_id,
        "tier": "elite",
        "total": int
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        alerts = get_user_active_alerts(user_id)
        tier = get_user_tier(user_id)

        logger.info(
            "Live alerts retrieved",
            extra={
                "user_id": user_id,
                "alert_count": len(alerts),
                "tier": tier,
                "request_id": g.get("request_id"),
            },
        )

        return jsonify(
            {
                "alerts": alerts,
                "user": user_id,
                "tier": tier,
                "total": len(alerts),
            }
        )

    except Exception as exc:
        logger.error(
            "Get live alerts failed",
            extra={
                "user_id": user_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to fetch alerts: {exc}"}), 500


@app.route("/api/alert-preferences", methods=["GET"])
def get_alert_preferences():
    """
    Get user's alert preferences.

    Returns:
    {
        "preferences": {
            "alerts_enabled": true,
            "favorite_teams": [...],
            "favorite_sports": [...],
            "min_ev_threshold": 5,
            "favorite_markets": [...],
            "quiet_hours": {...},
            "subscribed_games": [...]
        },
        "tier": "elite"
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        prefs = get_user_alert_preferences(user_id)
        tier = get_user_tier(user_id)

        return jsonify({"preferences": prefs, "tier": tier})

    except Exception as exc:
        logger.error(
            "Get alert preferences failed",
            extra={
                "user_id": user_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to fetch preferences: {exc}"}), 500


@app.route("/api/alert-preferences", methods=["POST"])
def update_alert_preferences():
    """
    Update user's alert preferences.

    Request JSON:
    {
        "alerts_enabled": true,
        "favorite_teams": ["Lakers", "Warriors"],
        "favorite_sports": ["nba"],
        "min_ev_threshold": 5,
        "favorite_markets": ["spread", "moneyline"],
        "quiet_hours": {"start": "23:00", "end": "08:00"},
        "subscribed_games": [
            {"home": "Lakers", "away": "Celtics", "sport": "nba"}
        ]
    }

    Returns:
    {
        "preferences": {...updated preferences...},
        "tier": "elite"
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    payload = request.get_json(force=True, silent=True) or {}

    try:
        prefs = update_user_alert_preferences(user_id, payload)
        tier = get_user_tier(user_id)

        logger.info(
            "Alert preferences updated",
            extra={
                "user_id": user_id,
                "tier": tier,
                "request_id": g.get("request_id"),
            },
        )

        return jsonify({"preferences": prefs, "tier": tier})

    except Exception as exc:
        logger.error(
            "Update alert preferences failed",
            extra={
                "user_id": user_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to update preferences: {exc}"}), 500


@app.route("/api/alerts/<alert_id>/dismiss", methods=["POST"])
def dismiss_user_alert(alert_id):
    """
    Dismiss an alert (mark as dismissed).

    Returns:
    {
        "dismissed": true|false,
        "alert_id": "..."
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        success = dismiss_alert(user_id, alert_id)

        if success:
            logger.info(
                "Alert dismissed",
                extra={
                    "user_id": user_id,
                    "alert_id": alert_id,
                    "request_id": g.get("request_id"),
                },
            )
            return jsonify({"dismissed": True, "alert_id": alert_id})
        else:
            return jsonify({"dismissed": False, "alert_id": alert_id}), 404

    except Exception as exc:
        logger.error(
            "Dismiss alert failed",
            extra={
                "user_id": user_id,
                "alert_id": alert_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to dismiss alert: {exc}"}), 500


@app.route("/api/alerts/<alert_id>/view", methods=["POST"])
def view_alert(alert_id):
    """
    Mark an alert as viewed.

    Returns:
    {
        "viewed": true|false,
        "alert_id": "..."
    }
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        success = mark_alert_viewed(user_id, alert_id)

        if success:
            logger.debug(
                "Alert marked as viewed",
                extra={
                    "user_id": user_id,
                    "alert_id": alert_id,
                    "request_id": g.get("request_id"),
                },
            )
            return jsonify({"viewed": True, "alert_id": alert_id})
        else:
            return jsonify({"viewed": False, "alert_id": alert_id}), 404

    except Exception as exc:
        logger.error(
            "Mark alert viewed failed",
            extra={
                "user_id": user_id,
                "alert_id": alert_id,
                "error": str(exc),
                "request_id": g.get("request_id"),
            },
        )
        return jsonify({"error": f"Failed to mark alert viewed: {exc}"}), 500


# ==================== AI PICKS GENERATOR ENDPOINTS ====================


@app.route("/api/picks/daily", methods=["GET"])
def get_daily_picks():
    """
    Get auto-generated picks for today's NBA games.

    Query params:
        - min_confidence: Minimum confidence threshold (default 0.55)
        - min_edge: Minimum edge threshold (default 0.03)
        - max_picks: Maximum number of picks to return (default 20)

    Returns:
    {
        "date": "2026-02-02",
        "sport": "nba",
        "single_picks": [Pick],
        "parlays": [Parlay],
        "metadata": {
            "total_games": 10,
            "picks_generated": 15,
            "best_edge": 0.12,
            "generated_at": "ISO timestamp"
        }
    }
    """
    if not picks_generator:
        return jsonify({"error": "AI Picks Generator not initialized"}), 503

    try:
        from datetime import datetime as dt, date

        # Check cache
        today = str(date.today())
        cache_key = f"daily_picks_{today}"
        if cache_key in _daily_picks_cache:
            cached = _daily_picks_cache[cache_key]
            if (dt.now() - cached["timestamp"]).seconds < 14400:  # 4 hours
                logger.info("Returning cached daily picks", extra={"request_id": g.get("request_id")})
                return jsonify(cached["data"]), 200

        # Get today's games
        scoreboard = provider.fetch_scoreboard("nba", date=today)
        events = scoreboard.get("events", [])

        # Filter for pre-game events
        pre_game_events = [e for e in events if e.get("status", {}).get("type") != "final"]

        if not pre_game_events:
            return jsonify({
                "date": today,
                "sport": "nba",
                "single_picks": [],
                "parlays": [],
                "metadata": {"total_games": 0, "picks_generated": 0, "best_edge": 0, "generated_at": dt.now().isoformat()}
            }), 200

        # Generate picks for each game
        single_picks = []
        all_edges = []

        for event in pre_game_events[:5]:  # Limit to first 5 games for MVP
            try:
                event_id = event.get("id")
                home = event.get("home", {})
                away = event.get("away", {})

                # Extract features
                features = picks_generator["extractor"].extract_features(event)

                # Create mock picks (simplified - would use model predictions in production)
                pick_data = {
                    "pick_id": str(uuid.uuid4()),
                    "game_id": event_id,
                    "sport": "nba",
                    "bet_type": "spread",
                    "selection": "home",
                    "line": -3.5,
                    "odds": -110,
                    "confidence": 0.58,
                    "edge": 0.05,
                    "home_team": home.get("shortName", home.get("name")),
                    "away_team": away.get("shortName", away.get("name")),
                    "rationale": f"{home.get('shortName')} favorable matchup"
                }

                from ml.parlay_builder import Pick
                pick = Pick(**pick_data)
                single_picks.append(pick)
                all_edges.append(pick.edge)

            except Exception as e:
                logger.warning(f"Error generating pick for game {event_id}: {e}", extra={"request_id": g.get("request_id")})
                continue

        # Build sample parlay
        parlays = []
        if len(single_picks) >= 2:
            try:
                parlay = picks_generator["parlay_builder"].build_standard_parlay(single_picks[:3], max_legs=3)
                if parlay:
                    parlays.append(parlay)
            except Exception as e:
                logger.warning(f"Error building parlay: {e}", extra={"request_id": g.get("request_id")})

        result = {
            "date": today,
            "sport": "nba",
            "single_picks": [p.to_dict() for p in single_picks],
            "parlays": [p.to_dict() for p in parlays] if parlays else [],
            "metadata": {
                "total_games": len(pre_game_events),
                "picks_generated": len(single_picks),
                "best_edge": max(all_edges) if all_edges else 0,
                "generated_at": dt.now().isoformat()
            }
        }

        # Cache result
        _daily_picks_cache[cache_key] = {
            "data": result,
            "timestamp": dt.now()
        }

        return jsonify(result), 200

    except Exception as exc:
        logger.error("Daily picks generation failed", extra={"error": str(exc), "request_id": g.get("request_id")})
        return jsonify({"error": f"Failed to generate daily picks: {exc}"}), 500


@app.route("/api/picks/generate", methods=["POST"])
def generate_picks_from_prompt():
    """
    Generate picks based on user prompt describing game expectations.

    Request body:
    {
        "game_id": "401234567",  # Optional: specific game
        "prompt": "I think Lakers will dominate the paint and it'll be high scoring",
        "parlay": true,  # Build parlay from picks
        "min_confidence": 0.55,
        "min_edge": 0.03
    }

    Returns:
    {
        "picks": [Pick],
        "parlay": Parlay | null,
        "prompt_interpretation": {
            "scenario": "high_scoring",
            "keywords": [...],
            "constraints": {...}
        },
        "reasoning": [PickReasoning]
    }
    """
    if not picks_generator:
        return jsonify({"error": "AI Picks Generator not initialized"}), 503

    try:
        data = request.get_json()
        prompt = data.get("prompt", "")
        game_id = data.get("game_id")
        build_parlay = data.get("parlay", False)
        min_confidence = data.get("min_confidence", 0.55)
        min_edge = data.get("min_edge", 0.03)

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # Parse prompt
        interpretation = picks_generator["prompt_interpreter"].parse_prompt(prompt, game_id)

        # Get game data
        scoreboard = provider.fetch_scoreboard("nba")
        events = scoreboard.get("events", [])

        # Filter for pre-game events
        pre_game_events = [e for e in events if e.get("status", {}).get("type") != "final"]

        if not pre_game_events:
            return jsonify({"error": "No pre-game games available"}), 404

        # Generate picks
        from ml.parlay_builder import Pick
        picks = []

        for event in pre_game_events[:3]:  # Limit to first 3 games
            try:
                event_id = event.get("id")
                home = event.get("home", {})
                away = event.get("away", {})

                features = picks_generator["extractor"].extract_features(event)

                # Create pick based on interpretation
                scenario = interpretation.get("scenario", "balanced")
                selection = "home" if "home" in scenario or interpretation.get("constraints", {}).get("selection_bias") == "home" else "away"

                pick_data = {
                    "pick_id": str(uuid.uuid4()),
                    "game_id": event_id,
                    "sport": "nba",
                    "bet_type": "spread",
                    "selection": selection,
                    "line": -2.5 if selection == "home" else 2.5,
                    "odds": -110,
                    "confidence": min(0.58, interpretation.get("confidence_boost", 0) + 0.55),
                    "edge": 0.05,
                    "home_team": home.get("shortName", home.get("name")),
                    "away_team": away.get("shortName", away.get("name")),
                    "rationale": f"Aligned with: {prompt[:50]}"
                }

                pick = Pick(**pick_data)

                # Generate reasoning
                reasoning = picks_generator["reasoning_generator"].generate_reasoning(
                    pick=pick,
                    features=features.to_dict(),
                    user_prompt=prompt,
                    user_scenario=scenario
                )

                picks.append({
                    "pick": pick.to_dict(),
                    "reasoning": {
                        "summary": reasoning.summary,
                        "key_factors": reasoning.key_factors,
                        "stats_support": reasoning.stats_support,
                        "risks": reasoning.risks,
                        "user_alignment": reasoning.user_alignment
                    }
                })

            except Exception as e:
                logger.warning(f"Error generating pick for game: {e}", extra={"request_id": g.get("request_id")})
                continue

        # Build parlay if requested
        parlay_result = None
        if build_parlay and len(picks) >= 2:
            try:
                pick_objects = [p["pick"] for p in picks]
                parlay = picks_generator["parlay_builder"].build_standard_parlay(pick_objects, max_legs=3)
                if parlay:
                    parlay_result = parlay.to_dict()
            except Exception as e:
                logger.warning(f"Error building parlay: {e}", extra={"request_id": g.get("request_id")})

        return jsonify({
            "picks": picks,
            "parlay": parlay_result,
            "prompt_interpretation": {
                "scenario": interpretation.get("scenario"),
                "scenario_description": interpretation.get("scenario_description"),
                "keywords": list(interpretation.get("keywords", [])),
                "constraints": interpretation.get("constraints")
            }
        }), 200

    except Exception as exc:
        logger.error("Prompt-based generation failed", extra={"error": str(exc), "request_id": g.get("request_id")})
        return jsonify({"error": f"Failed to generate picks from prompt: {exc}"}), 500


@app.route("/api/picks/parlay", methods=["POST"])
def build_parlay_from_picks():
    """
    Build parlay from individual picks.

    Request body:
    {
        "pick_ids": ["uuid1", "uuid2", "uuid3"],
        "parlay_type": "standard" | "same_game",
        "min_confidence": 0.55
    }

    Returns:
    {
        "parlay": Parlay,
        "warning": "Optional warning about correlations"
    }
    """
    if not picks_generator:
        return jsonify({"error": "AI Picks Generator not initialized"}), 503

    try:
        data = request.get_json()
        pick_ids = data.get("pick_ids", [])
        parlay_type = data.get("parlay_type", "standard")
        min_confidence = data.get("min_confidence", 0.55)

        if not pick_ids or len(pick_ids) < 2:
            return jsonify({"error": "At least 2 picks required for parlay"}), 400

        # In production, would retrieve picks from database by ID
        # For MVP, creating mock picks for demonstration
        from ml.parlay_builder import Pick

        mock_picks = []
        for i, pick_id in enumerate(pick_ids):
            pick = Pick(
                pick_id=pick_id,
                game_id=f"game_{i}",
                sport="nba",
                bet_type="spread",
                selection="home" if i % 2 == 0 else "away",
                line=-2.5 if i % 2 == 0 else 2.5,
                odds=-110,
                confidence=0.58,
                edge=0.05,
                home_team=f"Team{i}",
                away_team=f"Team{i+1}",
                rationale=f"Pick {i+1}"
            )
            mock_picks.append(pick)

        # Build parlay
        if parlay_type == "same_game" and len(mock_picks) >= 1:
            parlay = picks_generator["parlay_builder"].build_same_game_parlay(
                game_id=mock_picks[0].game_id,
                picks=mock_picks,
                min_confidence=min_confidence
            )
        else:
            parlay = picks_generator["parlay_builder"].build_standard_parlay(
                picks=mock_picks,
                min_confidence=min_confidence
            )

        if not parlay:
            return jsonify({"error": "Could not build parlay with given picks"}), 400

        result = {
            "parlay": parlay.to_dict(),
            "warning": parlay.correlation_warning
        }

        return jsonify(result), 200

    except Exception as exc:
        logger.error("Parlay building failed", extra={"error": str(exc), "request_id": g.get("request_id")})
        return jsonify({"error": f"Failed to build parlay: {exc}"}), 500


def _build_features_from_event(event: dict) -> dict:
    """
    Build feature dictionary from event data.

    This is a simplified placeholder. Production would use
    comprehensive feature engineering from historical data.

    Args:
        event: Event dict from scoreboard

    Returns:
        Feature dictionary for model input
    """
    home = event.get("home", {}) or {}
    away = event.get("away", {}) or {}

    return {
        "home_id": home.get("id"),
        "away_id": away.get("id"),
        "home_rank": home.get("rank"),
        "away_rank": away.get("rank"),
        "spread_line": 0.0,  # Would come from odds provider
        "total_line": 45.0,  # Would come from odds provider
        "is_home_team": True,
    }


def _auth_user_id():
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
        return user_from_token(token)
    return None


def run():
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()

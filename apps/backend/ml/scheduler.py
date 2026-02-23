"""Daily pick generation scheduler using APScheduler."""

import logging
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class DailyPicksScheduler:
    """Scheduler for auto-generating NBA picks daily at 9 AM ET."""

    def __init__(self, picks_generator_components=None):
        """Initialize scheduler with ML components.

        Args:
            picks_generator_components: Dict with collector, extractor, etc.
        """
        self.scheduler = None
        self.components = picks_generator_components
        self.is_running = False

    def start(self):
        """Start the scheduler."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        try:
            self.scheduler = BackgroundScheduler()

            # Schedule daily pick generation at 9 AM ET
            trigger = CronTrigger(
                hour=9,
                minute=0,
                timezone="America/New_York"
            )

            self.scheduler.add_job(
                self.generate_daily_picks,
                trigger=trigger,
                id="daily_picks_generation",
                name="Daily NBA Picks Generation",
                replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True

            logger.info("Daily picks scheduler started - will generate picks daily at 9 AM ET")

        except Exception as exc:
            logger.error(f"Failed to start scheduler: {exc}")
            raise

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Daily picks scheduler stopped")

    def generate_daily_picks(self):
        """Generate picks for all today's NBA games.

        This is called automatically by the scheduler.
        """
        try:
            logger.info("Starting daily pick generation job...")

            if not self.components:
                logger.error("ML components not initialized, skipping daily pick generation")
                return

            from scores.providers import ESPNProvider
            from datetime import date

            provider = ESPNProvider()

            # Get today's games
            today = date.today()
            scoreboard = provider.fetch_scoreboard('nba', date=today)
            events = scoreboard.get('events', [])

            # Filter for pre-game events
            pre_game_events = [e for e in events if e.get('status', {}).get('type') != 'final']

            logger.info(f"Found {len(pre_game_events)} pre-game NBA games for {today}")

            if not pre_game_events:
                logger.info("No pre-game games available today")
                return

            # Generate picks for each game
            picks_generated = 0
            collector = self.components.get("collector")
            extractor = self.components.get("extractor")

            for event in pre_game_events:
                try:
                    event_id = event.get('id')
                    home = event.get('home', {})
                    away = event.get('away', {})

                    # Extract features
                    features = extractor.extract_features(event)

                    logger.debug(f"Generated features for game {event_id}: {len(features.to_feature_vector())} features")

                    picks_generated += 1

                except Exception as e:
                    logger.warning(f"Error generating pick for game {event_id}: {e}")
                    continue

            logger.info(f"Daily pick generation complete - generated picks for {picks_generated} games")

        except Exception as exc:
            logger.error(f"Daily pick generation job failed: {exc}", exc_info=True)

    def get_next_run_time(self):
        """Get the next scheduled run time.

        Returns:
            datetime of next scheduled execution, or None if not scheduled
        """
        if not self.scheduler:
            return None

        try:
            job = self.scheduler.get_job("daily_picks_generation")
            return job.next_run_time if job else None
        except Exception as exc:
            logger.error(f"Error getting next run time: {exc}")
            return None


# Global scheduler instance
_scheduler = None


def init_scheduler(components):
    """Initialize and start the global scheduler.

    Args:
        components: Dict with ML components
    """
    global _scheduler

    try:
        _scheduler = DailyPicksScheduler(components)
        _scheduler.start()
        logger.info("Global daily picks scheduler initialized")
    except Exception as exc:
        logger.error(f"Failed to initialize global scheduler: {exc}")
        _scheduler = None


def stop_scheduler():
    """Stop the global scheduler."""
    global _scheduler

    if _scheduler:
        _scheduler.stop()
        _scheduler = None
        logger.info("Global scheduler stopped")


def get_scheduler():
    """Get the global scheduler instance.

    Returns:
        DailyPicksScheduler or None if not initialized
    """
    return _scheduler

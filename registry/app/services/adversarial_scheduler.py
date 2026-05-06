"""Background scheduler for adversarial test suites.

Checks every 60 seconds for suites where schedule_enabled=True and
next_run_at <= now(). Triggers and executes runs, updates next_run_at.

Started as a daemon thread from the Flask app factory.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class AdversarialScheduler:
    """Background daemon that triggers scheduled adversarial test runs."""

    def __init__(self, app):
        self._app = app
        self._stop_event = threading.Event()
        self._thread = None
        self._check_interval = 60  # seconds

    def start(self):
        """Start the scheduler thread."""
        self._thread = threading.Thread(
            target=self._run_loop,
            name='adversarial-scheduler',
            daemon=True,
        )
        self._thread.start()
        logger.info("Adversarial scheduler started (interval=%ds)", self._check_interval)

    def stop(self):
        """Stop the scheduler thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Adversarial scheduler stopped")

    def _run_loop(self):
        """Main loop: check for due suites and execute."""
        while not self._stop_event.is_set():
            try:
                self._check_and_run()
            except Exception:
                logger.exception("adversarial_scheduler_error")

            self._stop_event.wait(timeout=self._check_interval)

    def _check_and_run(self):
        """Find due suites and trigger runs."""
        with self._app.app_context():
            from app import db
            from app.models.adversarial import AdversarialTestSuite
            from app.services.adversarial_service import AdversarialService

            now = datetime.now(timezone.utc)

            due_suites = AdversarialTestSuite.query.filter(
                AdversarialTestSuite.schedule_enabled.is_(True),
                AdversarialTestSuite.status == 'active',
                AdversarialTestSuite.deleted_at.is_(None),
                AdversarialTestSuite.next_run_at <= now,
            ).all()

            for suite in due_suites:
                try:
                    logger.info("scheduler_trigger suite_id=%s name=%s", suite.id, suite.name)

                    run = AdversarialService.trigger_run(
                        suite_id=str(suite.id),
                        triggered_by='scheduler',
                        tenant_id=suite.tenant_id,
                    )
                    AdversarialService.execute_run(
                        run_id=str(run.id),
                        tenant_id=suite.tenant_id,
                    )

                    # Update next_run_at
                    interval = suite.schedule_interval_minutes or 60
                    suite.next_run_at = now + timedelta(minutes=interval)
                    suite.last_run_at = now
                    db.session.commit()

                    logger.info("scheduler_completed suite_id=%s run_id=%s evasion_rate=%.2f",
                                suite.id, run.id, run.evasion_rate or 0)

                except Exception:
                    logger.exception("scheduler_run_failed suite_id=%s", suite.id)

import logging
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)


def enqueue_on_commit(task: Any, *args: Any) -> None:
    """Queue a Celery task once the current transaction commits.

    If the broker is unreachable (e.g. Redis not running in local dev) the task runs inline
    instead, so a send never fails half-way after the database has already committed.
    """

    def _send() -> None:
        try:
            task.delay(*args)
        except Exception:  # broker down
            logger.warning("Broker unavailable; running %s inline", task.name, exc_info=True)
            task.apply(args=args)

    transaction.on_commit(_send)

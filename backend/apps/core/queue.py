import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)

BROKER_ERRORS = (OperationalError, ConnectionError, OSError)


def enqueue_on_commit(task: Any, *args: Any) -> None:
    """Queue a Celery task once the current transaction commits.

    If the broker is unreachable (e.g. Redis not running in local dev) the task runs inline
    instead, so a send never fails half-way after the database has already committed.
    """

    def _send() -> None:
        if settings.CELERY_TASK_ALWAYS_EAGER:
            task.delay(*args)  # runs inline already; let task errors surface
            return
        try:
            task.delay(*args)
        except BROKER_ERRORS:
            logger.warning("Broker unavailable; running %s inline", task.name, exc_info=True)
            task.apply(args=args)

    transaction.on_commit(_send)

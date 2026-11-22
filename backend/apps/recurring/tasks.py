import logging

from celery import shared_task

from .services import generate_recurring

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def generate_recurring_invoices() -> int:
    count = generate_recurring()
    logger.info("Generated %s recurring invoices", count)
    return count

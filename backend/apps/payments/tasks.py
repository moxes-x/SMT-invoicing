import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def send_payment_notifications(payment_id: int) -> None:
    from .models import Payment
    from .online import notify

    payment = Payment.objects.select_related("business", "invoice__customer").get(pk=payment_id)
    notify(payment)


@shared_task(ignore_result=True)
def reconcile_payments() -> int:
    from .online import reconcile_open_attempts

    count = reconcile_open_attempts()
    if count:
        logger.info("Settled %s online payments by polling Lenco", count)
    return count

import datetime as dt

from django.utils import timezone


def today() -> dt.date:
    """Today's date in the business timezone (Africa/Lusaka, settings.TIME_ZONE)."""
    return timezone.localdate()

"""Tags for the ZRA block on tax invoices. Its labels stay in English: they are ZRA's terms."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

import segno
from django import template
from django.utils.safestring import SafeString, mark_safe

from apps.core.money import format_money

register = template.Library()


@register.filter
def major_money(amount: str | Decimal, currency: str = "ZMW") -> str:
    """A major-unit amount as reported to ZRA ("86.2069") in our money format (K86.21)."""
    minor = (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format_money(int(minor), currency)


@register.filter
def vsdc_time(value: str) -> str:
    """The VSDC's "20261101120000" or "2026-11-01 12:00:00" as "1 Nov 2026, 12:00"."""
    digits = "".join(c for c in value or "" if c.isdigit())
    try:
        when = dt.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return value
    return f"{when.day} {when:%b %Y, %H:%M}"


@register.simple_tag
def qr_svg(data: str) -> SafeString:
    """An inline SVG QR code. segno draws only paths from the encoded bits, so it's safe HTML."""
    if not data:
        return mark_safe("")  # noqa: S308
    svg = segno.make(data, error="m").svg_inline(scale=4, border=2, title="ZRA verification QR")
    return mark_safe(svg)  # noqa: S308

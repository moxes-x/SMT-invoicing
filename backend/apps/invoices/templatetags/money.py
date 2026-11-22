from decimal import Decimal

from django import template

from apps.core.money import format_money, format_rate

register = template.Library()


@register.filter
def money(amount: int, currency: str = "ZMW") -> str:
    return format_money(int(amount or 0), currency)


@register.filter
def qty(value: Decimal) -> str:
    """1.000 → 1, 2.500 → 2.5"""
    text = format(Decimal(value).normalize(), "f")
    return text


@register.filter
def rate(value: Decimal) -> str:
    return format_rate(Decimal(value))

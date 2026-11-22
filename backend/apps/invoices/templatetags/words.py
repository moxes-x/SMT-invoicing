"""{% t "key" name=value %}: a customer-facing word in the customer's language."""

from typing import Any

from django import template

from apps.core.i18n import status_label
from apps.core.i18n import t as translate

register = template.Library()


def _lang(context: Any) -> str:
    customer = context.get("customer")
    return getattr(customer, "language", "en") or "en"


@register.simple_tag(takes_context=True)
def t(context: Any, key: str, **kwargs: object) -> str:
    return translate(_lang(context), key, **kwargs)


@register.simple_tag(takes_context=True)
def status(context: Any, code: str, english: str) -> str:
    return status_label(_lang(context), code, english)


@register.simple_tag(takes_context=True)
def html_lang(context: Any) -> str:
    return _lang(context)

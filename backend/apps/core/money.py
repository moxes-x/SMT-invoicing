"""Money helpers. All amounts are integers in the minor unit (ngwee for ZMW, cents for USD)."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal) -> int:
    """Round once, at the end, half away from zero (K0.005 → K0.01)."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def line_amount(quantity: Decimal, unit_price: int, discount: int = 0) -> Decimal:
    """Exact (unrounded) value of one line in minor units."""
    return Decimal(quantity) * Decimal(unit_price) - Decimal(discount)


def invoice_totals(lines: Iterable[tuple[Decimal, int, int]]) -> dict[str, int]:
    """Totals for (quantity, unit_price, discount) lines.

    Lines are summed exactly and rounded once at the end, so many fractional quantities can't
    drift by a ngwee per line.
    """
    gross = Decimal(0)
    discount = Decimal(0)
    for quantity, unit_price, line_discount in lines:
        gross += Decimal(quantity) * Decimal(unit_price)
        discount += Decimal(line_discount)
    subtotal = round_half_up(gross)
    discount_total = round_half_up(discount)
    return {
        "subtotal": subtotal,
        "discount_total": discount_total,
        "total": subtotal - discount_total,
    }


def format_money(amount: int, currency: str = "ZMW") -> str:
    symbol = {"ZMW": "K", "USD": "$"}.get(currency, f"{currency} ")
    sign = "-" if amount < 0 else ""
    major, minor = divmod(abs(amount), 100)
    return f"{sign}{symbol}{major:,}.{minor:02d}"

from decimal import Decimal

import pytest

from apps.core.money import format_money, invoice_totals, round_half_up


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.5", 1), ("1.5", 2), ("2.4999", 2), ("-0.5", -1), ("1250", 1250)],
)
def test_round_half_up(value, expected):
    assert round_half_up(Decimal(value)) == expected


def test_totals_round_once_at_the_end():
    # Three lines of 0.333 x K0.05 = 1.665 ngwee each. Rounding per line would give 2+2+2 = 6;
    # rounding once gives 4.995 → 5.
    lines = [(Decimal("0.333"), 5, 0)] * 3
    assert invoice_totals(lines) == {"subtotal": 5, "discount_total": 0, "total": 5}


def test_totals_with_discounts():
    lines = [(Decimal("2"), 12_500, 1_000), (Decimal("1.5"), 10_000, 0)]
    assert invoice_totals(lines) == {"subtotal": 40_000, "discount_total": 1_000, "total": 39_000}


def test_format_money():
    assert format_money(123456) == "K1,234.56"
    assert format_money(5, "USD") == "$0.05"
    assert format_money(-150) == "-K1.50"

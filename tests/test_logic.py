"""line_amounts() on hand-made values. The golden test (test_golden.py) checks it against the real lines."""
from winedb.logic import LineAmounts, line_amounts


def test_price_includes_vat():
    # The example from the Access analysis: quantity 1, price 165 with VAT -> 132 without VAT.
    assert line_amounts(165, 1, 0, 0.25, 80) == LineAmounts(165.0, 132.0, 80.0)


def test_discount_is_taken_off_the_amount_with_vat():
    assert line_amounts(100, 3, 25, 0.25, 40) == LineAmounts(275.0, 220.0, 120.0)


def test_zero_vat():
    assert line_amounts(99.5, 2, 0, 0, 50) == LineAmounts(199.0, 199.0, 100.0)


def test_negative_quantity_gives_negative_amounts():
    assert line_amounts(120, -2, 0, 0.25, 70) == LineAmounts(-240.0, -192.0, -140.0)


def test_null_values_count_as_zero():
    assert line_amounts(None, None, None, None, None) == LineAmounts(0.0, 0.0, 0.0)
    assert line_amounts(120, 2, None, None, None) == LineAmounts(240.0, 240.0, 0.0)


def test_rounding_is_half_to_even_like_vba():
    # 0.125 is exact in binary, so this tests the rounding rule itself: VBA Round(0.125, 2) = 0.12.
    assert line_amounts(0.125, 1, 0, 0, 0.125).amount_incl_vat == 0.12
    assert line_amounts(0.125, 1, 0, 0, 0.125).amount_cost == 0.12


def test_amounts_have_two_decimals():
    result = line_amounts(120.7575, 3, 0, 0.25, 33.333)
    assert result == LineAmounts(362.27, 289.82, 100.0)

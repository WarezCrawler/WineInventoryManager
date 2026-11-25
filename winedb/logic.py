"""Business calculations as pure functions. They have no database access and no UI, so tests can
call them directly and the UI and the data functions use the same formulas."""
from typing import NamedTuple


class LineAmounts(NamedTuple):
    """The three calculated amounts of one invoice line, each rounded to 2 decimals."""
    amount_incl_vat: float
    amount_ex_vat: float
    amount_cost: float


def _number(value) -> float:
    """NULL counts as 0, as with the VBA function Nz."""
    return 0.0 if value is None else float(value)


def line_amounts(sales_price, quantity, discount, vat_rate, cost_price) -> LineAmounts:
    """Calculate the amounts of an invoice line (design doc §5.1, from fVinlager_Salg.CalcFullPrice).

    `sales_price` is the unit price with VAT, and `discount` is an amount off the whole line, also
    with VAT. Any argument can be None (NULL); it counts as 0.

    Rounding is half to even, as VBA `Round` does. Python's `round` does the same, and gives the
    stored values for all historical lines. Do not change to `Decimal` or another rounding rule
    without the golden test (tests/test_golden.py).
    """
    price, qty, disc = _number(sales_price), _number(quantity), _number(discount)
    amount_incl_vat = round(price * qty - disc, 2)
    amount_ex_vat = round(amount_incl_vat / (1 + _number(vat_rate)), 2)
    amount_cost = round(_number(cost_price) * qty, 2)
    return LineAmounts(amount_incl_vat, amount_ex_vat, amount_cost)


def default_cost(cost_rows: list[dict]) -> float:
    """The default cost price of a new invoice line (design doc §5.2, Access `GetCostPrisStandard`).

    `cost_rows` are the wine's rows of `prices_cost`. The default is the `cost_price` of the first row with
    `price_type = 'Standard'` (upper and lower case the same, as in Access), where "first" means the lowest
    `cost_price_id` (decision 4); 0 if there is none."""
    standard = sorted((r for r in cost_rows if (r.get("price_type") or "").casefold() == "standard"),
                      key=lambda r: r["cost_price_id"])
    return _number(standard[0]["cost_price"]) if standard else 0.0

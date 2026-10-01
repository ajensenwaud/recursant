from decimal import Decimal

CODES = {"SAVE10": ("percent", Decimal("10")), "FIVEOFF": ("fixed", Decimal("5.00"))}


def apply(code, amount):
    """Return the amount after applying a discount code (unknown codes: no change)."""
    if code not in CODES:
        return amount
    kind, value = CODES[code]
    if kind == "percent":
        return amount - amount * value / Decimal(100)
    return max(Decimal(0), amount - value)

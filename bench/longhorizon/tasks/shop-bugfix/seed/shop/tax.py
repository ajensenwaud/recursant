from decimal import Decimal

RATES = {"standard": Decimal("0.10"), "reduced": Decimal("0.05"), "zero": Decimal("0")}


def add_tax(amount, category="standard"):
    return amount * (1 + RATES[category])

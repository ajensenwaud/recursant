from decimal import Decimal

# Bulk pricing: quantities at or above the threshold get the bulk unit price.
BULK_THRESHOLD = 10
BULK_FACTOR = Decimal("0.9")


def unit_price(base, quantity):
    base = Decimal(str(base))
    if quantity >= BULK_THRESHOLD:
        return base * BULK_FACTOR
    return base


def line_total(base, quantity):
    return unit_price(base, quantity) * quantity

from decimal import Decimal, ROUND_HALF_UP
from . import pricing, discounts, tax


class Cart:
    def __init__(self, category="standard"):
        self.items = []
        self.category = category
        self.code = None

    def add(self, sku, price, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items.append((sku, price, quantity))

    def apply_code(self, code):
        self.code = code

    def subtotal(self):
        return sum((pricing.line_total(p, q) for _, p, q in self.items), Decimal(0))

    def total(self):
        amount = tax.add_tax(self.subtotal(), self.category)
        if self.code:
            amount = discounts.apply(self.code, amount)
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

import unittest
from decimal import Decimal
from shop import Cart


class HiddenShopTests(unittest.TestCase):
    def total(self, items, category="standard", code=None):
        c = Cart(category)
        for sku, price, qty in items:
            c.add(sku, price, qty)
        if code:
            c.apply_code(code)
        return c.total()

    def test_bulk_threshold_inclusive(self):
        self.assertEqual(self.total([("a", "2.00", 10)], "zero"), Decimal("18.00"))
        self.assertEqual(self.total([("a", "2.00", 9)], "zero"), Decimal("18.00"))
        self.assertEqual(self.total([("a", "2.00", 11)], "zero"), Decimal("19.80"))

    def test_percent_discount_before_tax(self):
        # 100 -> SAVE10 -> 90 -> +10% tax -> 99.00 (after-tax would give 99.00 too for percent;
        # use FIVEOFF to distinguish ordering)
        self.assertEqual(self.total([("a", "100.00", 1)], "standard", "SAVE10"), Decimal("99.00"))
        self.assertEqual(self.total([("a", "100.00", 1)], "standard", "FIVEOFF"), Decimal("104.50"))

    def test_single_final_rounding(self):
        # three lines of 0.335 each: rounding per line gives 1.02, once gives 1.01 (1.005 -> 1.01 half-up)
        self.assertEqual(self.total([("a", "0.335", 1), ("b", "0.335", 1), ("c", "0.335", 1)], "zero"), Decimal("1.01"))
        self.assertEqual(self.total([("a", "0.105", 3)], "standard"), Decimal("0.35"))

    def test_fixed_discount_floor_and_unknown_code(self):
        self.assertEqual(self.total([("a", "3.00", 1)], "zero", "FIVEOFF"), Decimal("0.00"))
        self.assertEqual(self.total([("a", "3.00", 1)], "zero", "NOPE"), Decimal("3.00"))

    def test_reduced_rate_bulk_and_discount(self):
        # 12 x 5.00 bulk -> 54.00 ; SAVE10 -> 48.60 ; +5% -> 51.03
        self.assertEqual(self.total([("a", "5.00", 12)], "reduced", "SAVE10"), Decimal("51.03"))

    def test_public_api_and_validation(self):
        with self.assertRaises(ValueError):
            Cart().add("a", "1.00", -1)
        self.assertIsInstance(self.total([("a", "1.00", 1)]), Decimal)

import unittest
from decimal import Decimal
from shop import Cart


class CartTests(unittest.TestCase):
    def test_single_item(self):
        c = Cart()
        c.add("a", "10.00", 1)
        self.assertEqual(c.total(), Decimal("11.00"))

    def test_zero_rate(self):
        c = Cart("zero")
        c.add("a", "3.50", 2)
        self.assertEqual(c.total(), Decimal("7.00"))

    def test_rejects_non_positive_quantity(self):
        with self.assertRaises(ValueError):
            Cart().add("a", "1", 0)


if __name__ == "__main__":
    unittest.main()

import unittest

from cart import total


class ShippingTests(unittest.TestCase):
    def test_boundary_free_shipping(self):
        self.assertEqual(total([1000]), 1000)

    def test_below_threshold(self):
        self.assertEqual(total([900]), 950)

    def test_above_threshold(self):
        self.assertEqual(total([1200]), 1200)

    def test_empty_cart(self):
        self.assertEqual(total([]), 0)

    def test_negative_price(self):
        with self.assertRaises(ValueError):
            total([-1])

    def test_multiple_items_boundary(self):
        self.assertEqual(total([400, 600]), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

import unittest
from calculator import add, divide


class CalculatorTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_negative(self):
        self.assertEqual(add(-2, -3), -5)

    def test_divide(self):
        self.assertEqual(divide(6, 3), 2)

    def test_zero_division(self):
        with self.assertRaises(ValueError):
            divide(5, 0)

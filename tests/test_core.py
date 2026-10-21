import unittest

from hourglass.calc import eta_seconds, fmt_duration, fmt_num
from hourglass.parsing import find_numbers, parse_number, parse_rate


class Parsing(unittest.TestCase):
    def test_sci(self):
        self.assertEqual(parse_number("1.14e11"), 1.14e11)

    def test_pair_with_ocr_O(self):
        self.assertEqual(find_numbers("1.64e94 / 1.OOe120"), [1.64e94, 1e120])

    def test_rate_hour(self):
        self.assertAlmostEqual(parse_rate("+7.34e11 / h"), 7.34e11 / 3600)

    def test_rate_min(self):
        self.assertAlmostEqual(parse_rate("+1.22e4 / min"), 1.22e4 / 60)

    def test_rate_default_unit(self):
        self.assertEqual(parse_rate("+3.03e90/s"), 3.03e90)
        self.assertAlmostEqual(parse_rate("5", "m"), 5 / 60)


class Calc(unittest.TestCase):
    def test_eta(self):
        self.assertEqual(eta_seconds(10, 110, 2), 50)
        self.assertEqual(eta_seconds(10, 5, 2), 0)
        self.assertIsNone(eta_seconds(10, 110, 0))

    def test_fmt(self):
        self.assertEqual(fmt_num(1.58e93), "1.58e93")
        self.assertEqual(fmt_duration(90061), "1d 1h 1m")


if __name__ == "__main__":
    unittest.main()

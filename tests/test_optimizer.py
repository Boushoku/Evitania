import unittest

from hourglass.optimizer import (Generator, Option, evaluate, levels_to_next_milestone,
                                 milestones_passed, rank, rate_after)


class MilestoneTests(unittest.TestCase):
    def test_passed(self):
        self.assertEqual([milestones_passed(n) for n in (0, 24, 25, 49, 50, 99, 100, 104, 200, 399)],
                         [0, 0, 1, 1, 2, 2, 3, 3, 4, 5])

    def test_to_next(self):
        self.assertEqual([levels_to_next_milestone(n) for n in (0, 25, 50, 99, 100, 104, 199)],
                         [25, 25, 50, 1, 100, 96, 1])


class RateTests(unittest.TestCase):
    def test_linear_without_milestone(self):
        g = Generator("g", 104, 8.0)
        self.assertAlmostEqual(rate_after(g, 10), 8.0 * 114 / 104)

    def test_doubles_on_milestone(self):
        g = Generator("g", 99, 99.0)
        self.assertAlmostEqual(rate_after(g, 1), 200.0)

    def test_max_level_caps(self):
        g = Generator("g", 90, 90.0, max_level=100)
        self.assertAlmostEqual(rate_after(g, 50), 100.0 * 2)


class RankTests(unittest.TestCase):
    def test_milestone_buy_beats_equal_cost_linear_buy(self):
        near = Generator("near", 99, 100.0)
        far = Generator("far", 60, 100.0)
        res = rank([Option(far, 1, 10.0), Option(near, 1, 10.0)],
                   gain=200.0, sand=100.0, progress=0.0, target=1e6)
        self.assertEqual(res[0].option.gen.name, "near")

    def test_waiting_for_cost_counts(self):
        g = Generator("g", 10, 10.0)
        cheap = evaluate(Option(g, 1, 0.0), 10.0, 0.0, 0.0, 1000.0)
        dear = evaluate(Option(g, 1, 500.0), 10.0, 0.0, 0.0, 1000.0)
        self.assertLess(cheap.total_seconds, dear.total_seconds)

    def test_useless_purchase_is_negative(self):
        g = Generator("g", 10, 1.0)
        r = evaluate(Option(g, 1, 1e9), 1000.0, 0.0, 0.0, 1e6)
        self.assertLess(r.saved_seconds, 0)


if __name__ == "__main__":
    unittest.main()

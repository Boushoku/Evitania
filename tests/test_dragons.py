import unittest

from hourglass.dragons import build_plan, parse_button, parse_level, parse_timer, wanted_dragon


class Dragons(unittest.TestCase):
    def test_level(self):
        self.assertEqual(parse_level("Power of the Red Dragon Lv 278 To lv 279: 5m 39s"), 278)
        self.assertIsNone(parse_level("Power of the Golden Dragon"))

    def test_button(self):
        self.assertEqual(parse_button("Train"), "train")
        self.assertEqual(parse_button("Training..."), "training")
        self.assertEqual(parse_button("Training…"), "training")
        self.assertIsNone(parse_button("Tr4in"))
        self.assertIsNone(parse_button(""))

    def test_timer(self):
        self.assertEqual(parse_timer("Power of the Red Dragon Lv 278 To lv 279: 5m 39s"), 339)
        self.assertEqual(parse_timer("Power of the Red Dragon Lv278 Tolv279: 2m 19s"), 139)
        self.assertEqual(parse_timer("Power of the Blue Dragon Lv 50 To lv 51: 5h 41m"), 5 * 3600 + 41 * 60)
        self.assertEqual(parse_timer("Lv 550 To lv 551: 1d 2h"), 86400 + 7200)
        self.assertIsNone(parse_timer("Power of the Golden Dragon"))
        self.assertIsNone(parse_timer("Lv 278"))

    def test_plan(self):
        goals = [{"name": "red", "goal": 300, "on": True}, {"name": "blue", "goal": 90, "on": False},
                 {"name": "green", "goal": 650, "on": True}, {"name": "x", "goal": 0, "on": True}]
        self.assertEqual(build_plan(goals), [("red", 300), ("green", 650)])

    def test_wanted(self):
        plan = [("red", 300), ("green", 650)]
        self.assertEqual(wanted_dragon(plan, {"red": 278, "green": 550}), "red")
        self.assertEqual(wanted_dragon(plan, {"red": 300, "green": 550}), "green")
        self.assertIsNone(wanted_dragon(plan, {"red": 300, "green": 650}))
        self.assertIsNone(wanted_dragon(plan, {"red": None, "green": 550}))  # unreadable: does not act


if __name__ == "__main__":
    unittest.main()

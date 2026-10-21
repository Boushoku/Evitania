import unittest

from hourglass.screens import classify, find_bar, find_menu_tile, guild_open, hourglass_open, monthly_open

SIZE = (1681, 770)


def W(text, x, y, w=60, h=14):
    return {"text": text, "x": x, "y": y, "w": w, "h": h}


BASE = [W(t, 700 + i * 100, 730) for i, t in enumerate(["Guild", "Journal", "Map", "Inventory", "Talents", "Auto", "Characters", "Menu"])]
MENU = [W("Offline", 1307, 42), W("Journal", 1121, 379), W("Hourglass", 1503, 470), W("of", 1568, 469, 15),
        W("Eternity", 1518, 487), W("Menu", 1400, 735), W("Talents", 1321, 379)]
HOURGLASS = [W("Hourglass", 208, 41), W("Timeline", 359, 41), W("Upgrades", 874, 45), W("Sand", 1150, 84)]


class ScreenTests(unittest.TestCase):
    def test_hourglass_open(self):
        self.assertEqual(classify(HOURGLASS, SIZE)[0], "hourglass")
        self.assertTrue(hourglass_open(HOURGLASS, SIZE))

    def test_base_screen_clicks_menu(self):
        state, pos = classify(BASE, SIZE)
        self.assertEqual(state, "base")
        self.assertAlmostEqual(pos[0], 1400 + 30)

    def test_side_menu_clicks_tile_not_title(self):
        state, pos = classify(MENU, SIZE)
        self.assertEqual(state, "menu")
        self.assertTrue(1500 < pos[0] < 1600 and 465 < pos[1] < 505)
        self.assertFalse(hourglass_open(MENU, SIZE))  # the tile label is mid-screen, not the title

    def test_unknown_does_not_act(self):
        self.assertEqual(classify([W("Smithing", 800, 300), W("Menu", 1400, 735)], SIZE), ("unknown", None))

    def test_bar_needs_enough_labels(self):
        self.assertFalse(find_bar(BASE[:2] + BASE[-1:], SIZE)[0])  # 3 labels: a panel covers the bar

    def test_menu_extrapolated_when_ocr_drops_it(self):
        # real OCR on a bright background: clipped labels, no 'Menu'
        words = [W("Guild", 703, 732, 38), W("Journal", 799, 732, 50), W("Map", 917, 732, 30), W("nventory", 1008, 733, 62),
                 W("Talents", 1116, 732, 52), W("haracter", 1324, 732, 58)]
        state, pos = classify(words, SIZE)
        self.assertEqual(state, "base")
        self.assertAlmostEqual(pos[0], 1458, delta=15)  # the Menu button center in the reference layout
        self.assertAlmostEqual(pos[1], 739, delta=8)
        self.assertIsNone(find_menu_tile(BASE))


GUILD = [W("Members", 73, 50), W("Week", 198, 50), W("Research", 283, 50), W("Shop", 407, 50), W("Management", 489, 50),
         W("Leaderboard", 657, 50), W("Roster", 593, 117), W("Level", 71, 156)]
SIDE_MENU = [W("Offline", 287, 15), W("Gains", 359, 15), W("Rate", 421, 15), W("Premium", 97, 233), W("Guild", 506, 251, 32),
             W("Journal", 101, 359), W("Hourglass", 483, 449, 60), W("Eternity", 497, 467)]


class GuildTests(unittest.TestCase):
    def test_guild_open_does_nothing(self):
        self.assertEqual(classify(GUILD, (1403, 676), "guild"), ("guild", None))

    def test_guild_from_base_clicks_bar_button(self):
        state, pos = classify(BASE, SIZE, "guild")
        self.assertEqual(state, "base")
        self.assertAlmostEqual(pos[0], 700 + 30)  # the 'Guild' label, not 'Menu'

    def test_guild_from_side_menu_clicks_tile(self):
        state, pos = classify(SIDE_MENU, (649, 650), "guild")
        self.assertEqual(state, "menu")
        self.assertAlmostEqual(pos[0], 522, delta=2)  # the tile, not the bar
        self.assertLess(pos[1], 650 * 0.5)

    def test_other_screen_open_is_not_the_target(self):
        self.assertEqual(classify(HOURGLASS, SIZE, "guild")[0], "hourglass")
        self.assertEqual(classify(GUILD, (1403, 676), "hourglass")[0], "guild")

    def test_hourglass_screen_is_not_guild(self):
        self.assertFalse(guild_open(HOURGLASS, SIZE))



class EnsureOpenFlowTests(unittest.TestCase):
    """ensure_open driven by a tiny fake game: clicks change which screen is showing."""

    FRAMES = {"hourglass": HOURGLASS, "base": BASE, "guild": GUILD}

    def play(self, start, **kw):
        from unittest import mock
        from PIL import Image
        from hourglass import screens
        world, clicks = {"screen": start}, []

        def click(title, fx, fy):
            clicks.append((round(fx, 2), round(fy, 2)))
            if (fx, fy) == screens.CLOSE_BUTTON:
                world["screen"] = "base"
            elif world["screen"] == "base" and fy > 0.9:  # a bar button: only 'Guild' is clicked in this test
                world["screen"] = "guild"
            return True

        top = lambda words: [w for w in words if w["y"] < 92]  # the title band of a 770 px frame
        with mock.patch.object(screens, "read_frame", lambda img: self.FRAMES[world["screen"]]), \
                mock.patch.object(screens, "read_words", lambda img, scale=2: top(self.FRAMES[world["screen"]])), \
                mock.patch.object(screens.time, "sleep", lambda s: None):
            from hourglass.screens import ensure_open
            res = ensure_open("game", lambda t: Image.new("RGB", (1681, 770)), click, "guild", log=lambda m: None, **kw)
        return res, clicks, world["screen"]

    def test_other_screen_open_is_not_touched_by_default(self):
        res, clicks, _ = self.play("hourglass")
        self.assertIsNone(res)
        self.assertEqual(clicks, [])

    def test_close_others_closes_then_opens(self):
        res, clicks, screen = self.play("hourglass", close_others=True)
        self.assertEqual((res, screen), ("opened", "guild"))
        self.assertEqual(clicks[0], (0.87, 0.06))  # the X first (rounded in the log)
        self.assertEqual(len(clicks), 2)             # then the bar's Guild button

    def test_already_open_clicks_nothing(self):
        res, clicks, _ = self.play("guild", close_others=True)
        self.assertEqual((res, clicks), ("already", []))


MONTHLY = [W("Monthly", 605, 37, 100), W("Rewards", 725, 37, 100), W("October", 886, 37), W("2026", 1007, 38),
           W("Reward", 728, 146), W("Received", 835, 146), W("HuntingKey", 766, 365)]


class MonthlyRewardsTests(unittest.TestCase):
    def test_recognized_by_its_title_only(self):
        self.assertTrue(monthly_open(MONTHLY, SIZE))
        self.assertEqual(classify(MONTHLY, SIZE, "guild")[0], "monthly")
        # the side-menu tile 'Monthly Reward' is mid-screen, not a title
        self.assertFalse(monthly_open([W("Monthly", 100, 578), W("Reward", 100, 595)], SIZE))

    def test_closed_with_its_own_x_then_guild_opens(self):
        from unittest import mock
        from PIL import Image
        from hourglass import screens
        frames = {"monthly": MONTHLY, "base": BASE, "guild": GUILD}
        world, clicks = {"screen": "monthly"}, []

        def click(title, fx, fy):
            clicks.append((fx, fy))
            world["screen"] = "base" if (fx, fy) == screens.MONTHLY_CLOSE else "guild"
            return True

        top = lambda words: [w for w in words if w["y"] < 92]
        with mock.patch.object(screens, "read_frame", lambda img: frames[world["screen"]]),                 mock.patch.object(screens, "read_words", lambda img, scale=2: top(frames[world["screen"]])),                 mock.patch.object(screens.time, "sleep", lambda s: None):
            res = screens.ensure_open("game", lambda t: Image.new("RGB", (1681, 770)), click, "guild",
                                      log=lambda m: None, close_others=True)
        self.assertEqual(res, "opened")
        self.assertEqual(clicks[0], screens.MONTHLY_CLOSE)  # not the usual panel X

    def test_cannot_be_opened(self):
        from hourglass import screens
        with self.assertRaises(ValueError):
            screens.classify([], SIZE, "monthly")


if __name__ == "__main__":
    unittest.main()

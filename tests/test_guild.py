import unittest
from datetime import datetime, timezone
from unittest import mock

from PIL import Image, ImageDraw

from hourglass import guild, guild_routine
from hourglass.guild_routine import Routine, routine_due


class ParseTests(unittest.TestCase):
    def test_level(self):
        self.assertEqual(guild.parse_level("Lv.4/10"), (4, 10))
        self.assertEqual(guild.parse_level("Lv.O/10"), (0, 10))
        self.assertEqual(guild.parse_level("LV. 3"), (3, None))
        self.assertIsNone(guild.parse_level("Expanded Stock"))

    def test_timer(self):
        self.assertEqual(guild.parse_timer("2d 02:13"), 2 * 86400 + 2 * 3600 + 13 * 60)
        self.assertEqual(guild.parse_timer("2d 23:59"), 259140)
        self.assertEqual(guild.parse_timer("05:12:30"), 5 * 3600 + 12 * 60 + 30)
        self.assertIsNone(guild.parse_timer("40K 120h"))

    def test_support_minutes(self):
        self.assertEqual(guild.parse_support_minutes("Support (—24 min)"), 24)
        self.assertEqual(guild.parse_support_minutes("Support (-36 min)"), 36)
        self.assertIsNone(guild.parse_support_minutes("Used up"))

    def test_button_state(self):
        self.assertEqual(guild.parse_button_state("Support (-24 min)", "yellow"), "support")
        self.assertEqual(guild.parse_button_state("Used up", "grey"), "used_up")
        self.assertEqual(guild.parse_button_state("Busy", "grey"), "busy")
        self.assertEqual(guild.parse_button_state("Start", "yellow"), "start")
        self.assertEqual(guild.parse_button_state("", "grey"), "disabled")
        # a yellow button whose text is unreadable is NOT assumed to be Support (it could be Start)
        self.assertEqual(guild.parse_button_state("", "yellow"), "unknown")

    def test_donation_counter(self):
        self.assertEqual(guild.parse_donation_counter("Donations • O / 2 today 5.88M"), (0, 2))
        self.assertEqual(guild.parse_donation_counter("Donations • 1 / 2 today"), (1, 2))
        self.assertIsNone(guild.parse_donation_counter("Make donations Lv. 4 / 4"))


class PixelTests(unittest.TestCase):
    @staticmethod
    def frame(color):
        img = Image.new("RGB", (800, 400), (40, 35, 55))
        ImageDraw.Draw(img).rectangle((500, 100, 690, 150), fill=color)
        return img

    def test_grey_and_yellow_buttons(self):
        rect, c = guild.find_button(self.frame((92, 89, 103)), (400, 60, 760, 200))
        self.assertEqual(c, "grey")
        self.assertAlmostEqual(rect[0], 500, delta=3)
        self.assertEqual(guild.find_button(self.frame((244, 180, 36)), (400, 60, 760, 200))[1], "yellow")

    def test_no_button(self):
        self.assertIsNone(guild.find_button(self.frame((40, 35, 55)), (400, 60, 760, 200)))

    def test_check_mark_only_in_green(self):
        img = self.frame((92, 89, 103))
        self.assertFalse(guild._has_check(img, (500, 100, 690, 150)))
        ImageDraw.Draw(img).rectangle((640, 110, 670, 140), fill=(40, 80, 40))
        self.assertTrue(guild._has_check(img, (500, 100, 690, 150)))


class DueTests(unittest.TestCase):
    def utc(self, h, m, day=20):
        return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)

    def test_due_from_0400_brt(self):
        self.assertFalse(routine_due(self.utc(6, 59), "04:00", ""))  # 03:59 BRT
        self.assertTrue(routine_due(self.utc(7, 0), "04:00", ""))    # 04:00 BRT
        self.assertTrue(routine_due(self.utc(20, 0), "04:00", ""))   # catches up later the same day

    def test_once_per_brt_day(self):
        self.assertFalse(routine_due(self.utc(8, 0), "04:00", "2026-10-20"))
        self.assertTrue(routine_due(self.utc(8, 0, day=21), "04:00", "2026-10-20"))

    def test_brt_date_changes_at_0300_utc(self):
        self.assertEqual(guild_routine.brt_date(self.utc(2, 59)), "2026-10-19")
        self.assertEqual(guild_routine.brt_date(self.utc(3, 0)), "2026-10-20")


def card(count, state, gold=5_880_000.0):
    return {"count": count, "limit": 2, "done": count >= 2, "gold": gold, "state": state, "button": (10, 10, 110, 40)}


class RoutineFlowTests(unittest.TestCase):
    """The donation/support flows with scripted OCR readings and recorded clicks (no game, no real waiting)."""

    def make(self, dry_run=False, wait_s=12):
        self.clicks = []
        r = Routine("game", lambda t: Image.new("RGB", (800, 400)), lambda t, x, y: self.clicks.append((x, y)) or True,
                    lambda *a: True, dry_run=dry_run, log=lambda m: None, sleep=lambda s: None, wait_s=wait_s, poll_s=3.0)
        r.open_tab = lambda name, tries=3: True
        r.to_top = lambda: None
        return r

    def run_donations(self, readings, **kw):
        r = self.make(**kw)
        with mock.patch.object(guild_routine, "read_donations", side_effect=readings):
            r.donations()
        return r

    def test_two_donations_each_confirmed(self):
        r = self.run_donations([card(0, "enabled"), card(0, "feedback"), card(1, "enabled"), card(1, "enabled"),
                                card(2, "done")])
        self.assertEqual(len(self.clicks), 2)
        self.assertTrue(r.ok)

    def test_second_donation_skipped_without_funds(self):
        r = self.run_donations([card(0, "enabled"), card(1, "disabled", 5_380_000.0), card(1, "disabled", 5_380_000.0)])
        self.assertEqual(len(self.clicks), 1)
        self.assertTrue(r.ok)  # not having gold is not a failure of the routine

    def test_no_reclick_when_backend_is_slow(self):
        r = self.run_donations([card(0, "enabled")] + [card(0, "feedback")] * 20)
        self.assertEqual(len(self.clicks), 1)  # clicked once, waited, never clicked again
        self.assertFalse(r.ok)

    def test_already_done_clicks_nothing(self):
        r = self.run_donations([card(2, "done")])
        self.assertEqual(self.clicks, [])
        self.assertTrue(r.ok)

    def test_unreadable_counter_does_not_click(self):
        r = self.run_donations([dict(card(0, "enabled"), count=None)])
        self.assertEqual(self.clicks, [])
        self.assertFalse(r.ok)

    def test_dry_run_never_clicks(self):
        r = self.run_donations([card(0, "enabled")], dry_run=True)
        self.assertEqual(self.clicks, [])
        self.assertIn("dry run", r.notes[-1])

    def run_research(self, rows_seq, found, **kw):
        r = self.make(**kw)
        r.find_active_research = lambda: (Image.new("RGB", (800, 400)), found)
        with mock.patch.object(guild_routine, "read_research", side_effect=rows_seq):
            r.research()
        return r

    @staticmethod
    def row(state, name="Research Efficiency"):
        return {"name": name, "level": 4, "max_level": 10, "timer_s": 1000,
                "button": {"rect": (10, 10, 110, 40), "color": "yellow", "text": "", "state": state, "support_min": 36}}

    def test_support_clicked_and_confirmed(self):
        r = self.run_research([[self.row("support")], [self.row("used_up")]], self.row("support"))
        self.assertEqual(len(self.clicks), 1)
        self.assertTrue(r.ok)

    def test_support_already_used(self):
        r = self.run_research([], self.row("used_up"))
        self.assertEqual(self.clicks, [])
        self.assertTrue(r.ok)

    def test_start_is_never_clicked(self):
        r = self.run_research([], self.row("start"))
        self.assertEqual(self.clicks, [])

    def test_support_not_confirmed_is_reported(self):
        r = self.run_research([[self.row("support")]] * 20, self.row("support"))
        self.assertEqual(len(self.clicks), 1)
        self.assertFalse(r.ok)

    def test_no_active_research(self):
        r = self.run_research([], None)
        self.assertEqual(self.clicks, [])
        self.assertTrue(r.ok)


class RetryTests(unittest.TestCase):
    def test_every_3_minutes_up_to_3_attempts(self):
        self.assertEqual(guild_routine.retry_delay(1), 180)
        self.assertEqual(guild_routine.retry_delay(2), 180)
        self.assertIsNone(guild_routine.retry_delay(3))  # the third failed attempt is the last one


if __name__ == "__main__":
    unittest.main()

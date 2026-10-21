"""Daily guild routine (reset at 04:00 BRT): Support the active research, make the daily donations, refresh the Week tab.

Order (docs/guild.md): Research tab -> Support the active research -> Week tab -> donate (up to 2, each one validated by
OCR until the counter goes up) -> click the Week tab twice (that is what makes the game sync the points to the server).

Safety: it never clicks Start; it clicks Support only when the button text reads 'Support'; it clicks Donate only when the
button is yellow and the counter was read; after a click it waits for the OCR to confirm and never re-clicks on a timeout.
Every step re-reads the screen first, so running it again the same day does not repeat what is already done.
"""
import time
from datetime import datetime, timedelta, timezone

from .guild import (active_research, find_tab, read_donations, read_research, tab_active)
from .ocr import read_words
from .screens import close_screen, ensure_open

BRT = timezone(timedelta(hours=-3))  # Brazil has had no daylight saving time since 2019
CONTENT_X = 0.55       # x of the scrolling list body (left of the buttons), where a scroll drag is made
TOP_NOTCHES = 15       # enough scroll notches to reach the top of any list
STEP_NOTCHES = -3      # one page down while searching the research list
MAX_PAGES = 8
RETRY_MINUTES = 3      # a failed scheduled run is retried after this long ...
MAX_ATTEMPTS = 3       # ... up to this many scheduled attempts per BRT day (the first one counts)
SETTLE_S = 1.2         # the list keeps animating after a drag; a capture taken sooner shows the old position


def brt_date(now: datetime) -> str:
    return now.astimezone(BRT).date().isoformat()


def routine_due(now: datetime, hhmm: str, last_done: str) -> bool:
    """True once per BRT day, from hhmm on (a late start still catches up the same day)."""
    local = now.astimezone(BRT)
    h, m = (int(x) for x in hhmm.split(":"))
    return last_done != local.date().isoformat() and (local.hour, local.minute) >= (h, m)


def retry_delay(attempt: int):
    """Seconds to wait before retrying after failed scheduled attempt number `attempt` (1-based), or None when the
    daily limit of attempts is used up."""
    return RETRY_MINUTES * 60 if attempt < MAX_ATTEMPTS else None


class Routine:
    def __init__(self, title, grab, click, scroll, dry_run=False, log=print, sleep=time.sleep, wait_s=120, poll_s=3.0):
        self.title, self.dry_run, self.log, self.sleep = title, dry_run, log, sleep
        self._grab, self._click, self._scroll = grab, click, scroll
        self.wait_s, self.poll_s = wait_s, poll_s
        self.notes, self.ok = [], True

    # ---- helpers ----
    def note(self, msg, fail=False):
        self.notes.append(msg)
        self.log(msg)
        if fail:
            self.ok = False

    def grab(self):
        return self._grab(self.title)

    def click_at(self, img, rect_or_pos):
        """Clicks the center of a pixel rect (x0,y0,x1,y1) or a pixel point of `img`."""
        if len(rect_or_pos) == 4:
            x, y = (rect_or_pos[0] + rect_or_pos[2]) / 2, (rect_or_pos[1] + rect_or_pos[3]) / 2
        else:
            x, y = rect_or_pos
        return self._click(self.title, x / img.width, y / img.height)

    def to_top(self):
        self._scroll(self.title, CONTENT_X, TOP_NOTCHES)
        self.sleep(SETTLE_S)

    def open_tab(self, name, tries=3) -> bool:
        for _ in range(tries):
            img = self.grab()
            words = read_words(img, scale=2)
            if tab_active(words, img.size, name):
                return True
            pos = find_tab(words, img.size, name)
            if pos is None or not self.click_at(img, pos):
                return False
            self.sleep(1.2)
        img = self.grab()
        return tab_active(read_words(img, scale=2), img.size, name)

    def click_tab(self, name) -> bool:
        img = self.grab()
        pos = find_tab(read_words(img, scale=2), img.size, name)
        return bool(pos) and self.click_at(img, pos)

    # ---- research ----
    def find_active_research(self):
        """(image, row) of the running research, scrolling the list from the top; (None, None) when there is none."""
        self.to_top()
        seen = None
        for _ in range(MAX_PAGES):
            img = self.grab()
            rows = read_research(img)
            row = active_research(rows)
            if row:
                return img, row
            names = [r["name"] for r in rows]
            if names == seen:  # same rows twice in a row (after letting the animation settle): the end of the list
                break
            seen = names
            self._scroll(self.title, CONTENT_X, STEP_NOTCHES)
            self.sleep(SETTLE_S)
        return None, None

    def research(self):
        if not self.open_tab("Research"):
            return self.note("Research: could not open the Research tab", fail=True)
        img, row = self.find_active_research()
        if row is None:
            return self.note("Research: no active research found, nothing to support")
        b = row["button"]
        state = b["state"] if b else "none"
        if state == "used_up":
            return self.note(f"Research: '{row['name']}' already supported today")
        if state != "support":
            return self.note(f"Research: '{row['name']}' button is '{state}', did not click", fail=state == "none")
        label = f"Support (-{b['support_min']} min)" if b["support_min"] else "Support"
        if self.dry_run:
            return self.note(f"Research: dry run, would click {label} on '{row['name']}'")
        if not self.click_at(img, b["rect"]):
            return self.note("Research: game not clickable, did not click Support", fail=True)
        waited = 0.0
        while waited <= self.wait_s:
            self.sleep(self.poll_s)
            waited += self.poll_s
            now = next((r for r in read_research(self.grab()) if r["name"] == row["name"]), None)
            if now and now["button"] and now["button"]["state"] == "used_up":
                return self.note(f"Research: supported '{row['name']}' ({label}), confirmed after ~{int(waited)} s")
        self.note(f"Research: clicked {label} on '{row['name']}' but 'Used up' did not appear in {int(self.wait_s)} s", fail=True)

    # ---- donations ----
    def read_card(self, attempts=4):
        for _ in range(attempts):
            d = read_donations(self.grab())
            if d is not None:
                return d
            self.to_top()
        return None

    def donations(self):
        if not self.open_tab("Week"):
            return self.note("Donations: could not open the Week tab", fail=True)
        self.to_top()
        made = 0
        card = self.read_card()
        if card is None:
            return self.note("Donations: card not visible on the Week tab", fail=True)
        for _ in range(6):  # bound: 2 donations plus feedback waits
            if card["state"] == "done" or (card["count"] is not None and card["limit"] and card["count"] >= card["limit"]):
                return self.note(f"Donations: {card['count']}/{card['limit']} done" + (f" ({made} made now)" if made else ""))
            if card["count"] is None:
                return self.note("Donations: counter unreadable, did not click", fail=True)
            if card["state"] == "disabled":
                return self.note(f"Donations: {card['count']}/{card['limit']}, button disabled (not enough gold? gold={card['gold']})")
            if card["state"] == "feedback":
                card = self.wait_card(lambda c: c["state"] != "feedback")
                if card is None:
                    return self.note("Donations: still showing feedback after the wait", fail=True)
                continue
            if card["state"] != "enabled":
                return self.note(f"Donations: no Donate button (state {card['state']}), did not click", fail=True)
            before = card["count"]
            if self.dry_run:
                return self.note(f"Donations: dry run, {before}/{card['limit']}, would click Donate (gold={card['gold']})")
            img = self.grab()
            if not self.click_at(img, card["button"]):
                return self.note("Donations: game not clickable, did not click Donate", fail=True)
            card = self.wait_card(lambda c: c["count"] is not None and c["count"] > before)
            if card is None:
                return self.note(f"Donations: clicked Donate at {before}/2 but the counter did not go up in "
                                 f"{int(self.wait_s)} s; not clicking again", fail=True)
            made += 1
            self.note(f"Donations: donation confirmed ({card['count']}/{card['limit']})")
        self.note("Donations: gave up after too many steps", fail=True)

    def wait_card(self, ok):
        """Polls the card until ok(card) (the backend can be slow); None on timeout."""
        waited = 0.0
        while waited <= self.wait_s:
            self.sleep(self.poll_s)
            waited += self.poll_s
            c = read_donations(self.grab())
            if c is not None and ok(c):
                return c
        return None

    # ---- whole routine ----
    def run(self):
        if ensure_open(self.title, self._grab, self._click, "guild", log=self.log, close_others=True) is None:
            self.note("Guild screen could not be opened", fail=True)
            return self.report()
        self.research()
        self.donations()
        if not self.dry_run:
            for _ in range(2):  # clicking the Week tab again makes the game sync the points to the server
                if not self.click_tab("Week"):
                    self.note("Week tab refresh click failed", fail=True)
                    break
                self.sleep(1.5)
        if not close_screen(self.title, self._grab, self._click, "guild", log=self.log):
            self.note("Guild screen was left open")
        return self.report()

    def report(self):
        return {"ok": self.ok, "dry_run": self.dry_run, "notes": self.notes}


def run_daily(title, grab, click, scroll, dry_run=False, log=print, **kw):
    return Routine(title, grab, click, scroll, dry_run, log, **kw).run()

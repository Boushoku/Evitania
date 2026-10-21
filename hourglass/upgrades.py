"""One-shot 'buy upgrade' action: open the Upgrades tab, find the row by its name (OCR), check that its
Buy button is enabled (bright green) and click it. Everything geometric is detected, nothing is hard-coded."""
import re
import time
from dataclasses import dataclass

from PIL import Image

from . import gameinput
from .ocr import read_words

_LEVEL = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass
class Row:
    x: float
    y: float          # vertical center of the name line
    level: int | None  # 'a' of 'Lv a/b' (None if unreadable)
    max_level: int | None


def find_row(img: Image.Image, name: str) -> Row | None:
    """Finds the row whose title is exactly `name` (e.g. 'Timeline Output'): the title words are adjacent,
    which tells it apart from descriptions such as 'x1.2 Timeline Engine output'."""
    words = read_words(img.crop((int(img.width * 0.42), 0, img.width, img.height)))
    for w in words:
        w["x"] += int(img.width * 0.42)
    target = name.lower().split()
    texts = [w["text"].lower() for w in words]
    for i in range(len(words) - len(target) + 1):
        if texts[i:i + len(target)] != target:
            continue
        first, last = words[i], words[i + len(target) - 1]
        if abs(first["y"] - last["y"]) > 8:
            continue
        level = max_level = None
        for w in words[i + len(target):i + len(target) + 4]:
            m = _LEVEL.fullmatch(w["text"])
            if m and abs(w["y"] - first["y"]) < 14:
                level, max_level = int(m.group(1)), int(m.group(2))
                break
        return Row(first["x"], first["y"] + first["h"] / 2, level, max_level)
    return None


def _is_green(p) -> bool:
    r, g, b = p[:3]
    return g > r + 35 and g > b + 60  # both the enabled and the dull disabled button are green-ish


def find_button(img: Image.Image, row: Row) -> tuple[tuple[int, int, int, int], bool] | None:
    """Buy button of a row: ((x0, y0, x1, y1), enabled). Located by color in the band around the row."""
    y0, y1 = max(0, int(row.y - 45)), min(img.height, int(row.y + 60))
    x0 = int(row.x + img.width * 0.12)
    px = img.convert("RGB").load()
    cols = [sum(_is_green(px[x, y]) for y in range(y0, y1)) for x in range(x0, img.width)]
    # button columns are tall (filled), description text columns are thin
    thresh = max(14, int(0.3 * (y1 - y0)))
    best, run = None, None
    for i, c in enumerate(cols + [0]):
        if c >= thresh:
            run = (run[0], i) if run else (i, i)
        elif run:
            if best is None or run[1] - run[0] > best[1] - best[0]:
                best = run
            run = None
    if not best or best[1] - best[0] < 30:
        return None
    bx0, bx1 = x0 + best[0], x0 + best[1]
    rows = [sum(_is_green(px[x, y]) for x in range(bx0, bx1 + 1)) for y in range(y0, y1)]
    ys = [y0 + i for i, c in enumerate(rows) if c >= 0.5 * (bx1 - bx0)]
    if not ys:
        return None
    by0, by1 = min(ys), max(ys)
    area = [px[x, y] for x in range(bx0, bx1 + 1, 2) for y in range(by0, by1 + 1, 2)]
    bright = sum(1 for r, g, b in (p[:3] for p in area) if g > 170 and g > r + 40 and g > b + 80) / max(1, len(area))
    return (bx0, by0, bx1, by1), bright >= 0.5


def run_buy(title, tabs, home_tab, upgrade, grab, click_client, click_rect, dry_run=False, log=print):
    """Returns (ok, message). With dry_run=True it navigates and inspects but never clicks Buy."""
    up = tabs["upgrades"]
    if not click_client(title, up["x"], up["y"]):
        return False, f"game is not clickable ({gameinput.LAST_BLOCK}; it must be visible on the active desktop)"
    try:
        time.sleep(1.5)
        img = grab(title)
        row = find_row(img, upgrade)
        if row is None:
            return False, f"row '{upgrade}' not found (already purchased/maxed, or the list scrolled)"
        btn = find_button(img, row)
        if btn is None:
            return False, f"Buy button of '{upgrade}' not found"
        rect, enabled = btn
        lvl = f"Lv {row.level}/{row.max_level}" if row.level is not None else "level unreadable"
        if not enabled:
            return False, f"Buy button of '{upgrade}' ({lvl}) is disabled (not enough sand?)"
        if dry_run:
            return True, f"dry run OK: '{upgrade}' ({lvl}), Buy button enabled at {rect}; nothing clicked"
        if not click_rect(title, img.size, rect):
            return False, "game not visible, did not click Buy"
        time.sleep(1.2)
        after = find_row(grab(title), upgrade)
        if after is None:
            return True, f"bought '{upgrade}' ({lvl} -> row gone: maxed/hidden)"
        if row.level is not None and after.level is not None and after.level > row.level:
            return True, f"bought '{upgrade}' (Lv {row.level} -> {after.level})"
        if row.level is None or after.level is None:
            return True, f"clicked Buy on '{upgrade}' (level not readable, could not verify the purchase)"
        return False, f"clicked Buy on '{upgrade}' but the level did not change ({lvl} -> Lv {after.level})"
    finally:
        home = tabs.get(home_tab)
        if home:
            click_client(title, home["x"], home["y"])

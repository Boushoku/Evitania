"""Reads the Guild screen (Research and Week tabs) from a captured frame. Read-only: nothing here clicks.

Layout facts (see docs/guild.md): research rows are located by their 'Lv. x / y' token, not by position (the list
order is not guaranteed and it scrolls); buttons are found by color because the OCR cannot read grey-on-grey text
at full-frame scale. Vertical offsets scale with the frame height (reference 770 px).
"""
import re

from PIL import Image

from .ocr import read_text, read_words
from .parsing import parse_number

REF_H = 770
TITLE_BOTTOM = 0.12  # tab headers live in the top band

_DIGITS = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})
_LV = re.compile(r"^l?v\.?(\d|[OIl])+(/(\d|[OIl])+)?$", re.I)  # merged token: 'Lv.4/10'
_LVWORD = re.compile(r"^(l?v|w)\.?$", re.I)  # the OCR splits it: 'Lv.', 'LV.', 'w.' ...
_NUMTOK = re.compile(r"^([0-9OIl]+)(/[0-9OIl]+)?$")  # ... followed by '2/10' or '3'
_MINUS = "−—–-"


# ---------- pure text parsing ----------
def _num(s: str) -> int:
    return int(s.translate(_DIGITS))


def parse_level(text: str):
    """'Lv. 4 / 10' -> (4, 10); 'Lv. 3' -> (3, None); None when there is no level."""
    m = re.search(r"L?v\.?\s*([0-9OIl]+)\s*(?:/\s*([0-9OIl]+))?", text, re.I)
    return (_num(m.group(1)), _num(m.group(2)) if m.group(2) else None) if m else None


def parse_timer(text: str):
    """Remaining time of a research ('2d 02:13' = 2 days 02h13m, '05:12:30' = h:m:s) in seconds, or None."""
    m = re.search(r"(?:(\d+)\s*d\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not m:
        return None
    d, a, b, c = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + a * 3600 + b * 60 + c if m.group(4) else d * 86400 + a * 3600 + b * 60


def parse_support_minutes(text: str):
    """'Support (-24 min)' -> 24; None when the text has no minutes."""
    m = re.search(rf"[{_MINUS}]\s*(\d+)\s*min", text)
    return int(m.group(1)) if m else None


def parse_button_state(text: str, color: str | None) -> str:
    """'support' | 'start' | 'busy' | 'used_up' | 'disabled' (grey, text unreadable) | 'unknown' from the button text (OCR) and its color."""
    t = text.lower()
    for key, state in (("support", "support"), ("used", "used_up"), ("busy", "busy"), ("start", "start")):
        if key in t:
            return state
    return "disabled" if color == "grey" else "unknown"


def parse_donation_counter(text: str):
    """'Donations · O / 2 today' -> (0, 2); None when not found."""
    m = re.search(r"([0-9OIl])\s*/\s*([0-9])\s*today", text)
    return (_num(m.group(1)), _num(m.group(2))) if m else None


# ---------- pixels ----------
def _color(p) -> str | None:
    r, g, b = p[:3]
    if r > 140 and r > b + 90 and g > 60:
        return "yellow"  # enabled button (Support / Donate): yellow to orange gradient
    if 70 <= r <= 125 and 70 <= g <= 125 and 85 <= b <= 135 and abs(r - g) <= 12 and b >= r:
        return "grey"  # disabled button
    return None


def find_button(img: Image.Image, box):
    """Biggest button-colored blob inside box=(x0,y0,x1,y1) px -> ((x0,y0,x1,y1), 'yellow'|'grey') or None."""
    s = max(1.0, img.height / REF_H)
    x0, y0, x1, y1 = (max(0, int(v)) for v in box)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    px = img.convert("RGB").load()
    step = 2
    gx, gy = range(x0, x1, step), range(y0, y1, step)
    cell = {(i, j): _color(px[x, y]) for i, x in enumerate(gx) for j, y in enumerate(gy)}
    seen, best = set(), None
    for start, c in cell.items():
        if c is None or start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            i, j = stack.pop()
            comp.append((i, j))
            for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if n not in seen and cell.get(n) == c:
                    seen.add(n)
                    stack.append(n)
        if best is None or len(comp) > len(best[1]):
            best = (c, comp)
    if not best:
        return None
    c, comp = best
    xs, ys = [x0 + i * step for i, _ in comp], [y0 + j * step for _, j in comp]
    rect = (min(xs), min(ys), max(xs), max(ys))
    if rect[2] - rect[0] < 60 * s or rect[3] - rect[1] < 25 * s:
        return None
    return rect, c


def _has_check(img: Image.Image, rect) -> bool:
    """Green check mark inside a (grey) button: the transient 'donation registered' feedback."""
    px = img.convert("RGB").load()
    n = sum(1 for x in range(rect[0], rect[2], 2) for y in range(rect[1], rect[3], 2)
            if px[x, y][1] > px[x, y][0] + 20 and px[x, y][1] > px[x, y][2] + 20)
    return n >= 8


def _read(img: Image.Image, rect, pad=0) -> str:
    return read_text(img.crop((max(0, rect[0] - pad), max(0, rect[1] - pad), min(img.width, rect[2] + pad), min(img.height, rect[3] + pad))))


def _is(w, text) -> bool:
    return w["text"].lower().strip(":.") == text


# ---------- tab headers ----------
def find_tab(words, size, name):
    """Pixel center of a tab header word (Members, Week, Research, ...) in the top band, or None."""
    for w in words:
        if _is(w, name.lower()) and w["y"] < size[1] * TITLE_BOTTOM:
            return w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    return None


def tab_active(words, size, name) -> bool:
    """The content title ('Research', 'Week') is shown under the tab bar, so the tab is the selected one."""
    H = size[1]
    return any(_is(w, name.lower()) and TITLE_BOTTOM * H < w["y"] < 0.3 * H and w["h"] > 12 * H / REF_H for w in words)


# ---------- Research ----------
def read_research(img: Image.Image, words=None):
    """Visible research rows: [{'name','level','max_level','timer_s','button': {'rect','color','state','text','support_min'}|None}].

    The active research is the one with a timer bar (or a Support / Used up button)."""
    W, H = img.size
    s = H / REF_H
    words = words if words is not None else read_words(img, scale=2)
    rows = []
    for i, lv in enumerate(words):
        if not (0.14 * H < lv["y"] < 0.9 * H and lv["x"] > 0.3 * W):
            continue
        nxt = min((w for w in words if abs(w["y"] - lv["y"]) < 8 * s and w["x"] > lv["x"]), key=lambda w: w["x"], default=None)
        if _LVWORD.match(lv["text"]) and nxt and _NUMTOK.match(nxt["text"]):
            tok = "Lv." + nxt["text"]
        elif _LV.match(lv["text"]):
            tok = lv["text"]
        else:
            continue
        # name = the words on the same text line, right-to-left from the level token, while they stay close together
        line = sorted((w for w in words if abs(w["y"] + w["h"] / 2 - (lv["y"] + lv["h"] / 2)) < 10 * s and w["x"] < lv["x"] and w["x"] > 0.3 * W),
                      key=lambda w: -w["x"])
        name, left = [], lv["x"]
        for w in line:
            if left - (w["x"] + w["w"]) > 40 * s:
                break
            name.append(w["text"])
            left = w["x"]
        if not name:
            continue
        lvl = parse_level(tok) or (None, None)
        by = lv["y"]
        box = (0.70 * W, by - 5 * s, 0.92 * W, by + 70 * s)
        found = find_button(img, box)
        button = None
        if found:
            rect, color = found
            text = _read(img, rect, pad=2)
            button = {"rect": rect, "color": color, "text": text, "state": parse_button_state(text, color),
                      "support_min": parse_support_minutes(text)}
        bar = (int(lv["x"] - 230 * s), int(by + 46 * s), int(0.74 * W), int(by + 76 * s))  # the text inside the progress bar
        timer_s = parse_timer(read_text(img.crop(bar))) if bar[2] > bar[0] and bar[3] <= H else None
        rows.append({"name": " ".join(reversed(name)), "level": lvl[0], "max_level": lvl[1], "timer_s": timer_s, "button": button})
    return rows


def active_research(rows):
    """The research that is running: it has a timer, or a Support / Used up button."""
    for r in rows:
        b = r["button"]
        if r["timer_s"] is not None or (b and b["state"] in ("support", "used_up")):
            return r
    return None


# ---------- Week: donations ----------
def read_donations(img: Image.Image, words=None):
    """State of the Donations card (Week tab, list scrolled to the top), or None when the card is not visible.

    {'count','limit','done','gold','state','button': rect|None}; state: 'enabled' (yellow Donate) | 'feedback'
    (grey with a check, transient) | 'disabled' (grey, e.g. not enough gold) | 'done' | 'none'."""
    W, H = img.size
    words = words if words is not None else read_words(img, scale=2)
    # the card header, not a task name such as 'Make donations' (those sit lower, in the scrolled list)
    anchor = next((w for w in words if _is(w, "donations") and w["y"] < 0.4 * H), None)
    if anchor is None:
        return None
    x0, y0 = int(anchor["x"] - 10), int(anchor["y"] - 10)
    card = img.crop((max(0, x0), max(0, y0), min(W, int(anchor["x"] + 0.30 * W)), min(H, int(anchor["y"] + 0.3 * H))))
    text = read_text(card)
    counter = parse_donation_counter(text)
    if counter is None and "every donation" not in text.lower():
        return None
    gold = next((parse_number(w["text"]) for w in words if anchor["y"] - 20 < w["y"] < anchor["y"] + 20
                 and w["x"] > anchor["x"] + 0.18 * W and re.search(r"\d", w["text"]) and parse_number(w["text"])), None)
    found = find_button(img, (anchor["x"] - 5, anchor["y"] + 0.07 * H, anchor["x"] + 0.30 * W, anchor["y"] + 0.20 * H))
    done = "every donation" in text.lower() or (counter is not None and counter[0] >= counter[1])
    if found is None:
        state, rect = ("done" if done else "none"), None
    else:
        rect, color = found
        state = "enabled" if color == "yellow" else ("feedback" if _has_check(img, rect) else "disabled")
    return {"count": counter[0] if counter else None, "limit": counter[1] if counter else None,
            "done": done, "gold": gold, "state": state, "button": rect}

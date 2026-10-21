"""Detects which game screen is showing and opens a target screen when it is closed.

Screens live in SCREENS (anchor words that say "this screen is open" + how to reach it):
  hourglass: base -> bottom-bar 'Menu' -> side menu tile 'Hourglass of Eternity'
  guild:     base -> bottom-bar 'Guild' button, or the side menu tile 'Guild'
Pure classification lives in `classify`; `ensure_open` does the clicking and does nothing when the screen is already
open. When the state is unclear (another screen open, labels unreadable, game covered) it does not click.
"""
import time

from .ocr import read_words

BAR_LABELS = ("guild", "journal", "map", "inventory", "talents", "auto", "characters", "menu")
BAR_X = dict(zip(BAR_LABELS, (722, 826, 932, 1037, 1142, 1248, 1353, 1458)))  # label centers in the 1680 px reference
BAR_X = {k: v / 1680 for k, v in BAR_X.items()}
BAR_MIN_LABELS = 4  # labels readable at once => no panel covers the bottom bar (base screen)
BAR_TOP = 0.88      # bottom bar band starts here (fraction of the height)
TITLE_BOTTOM = 0.12  # screen titles / tab headers sit in this top band
MONTHLY_CLOSE = (0.758, 0.062)  # the X of the full-screen Monthly Rewards panel (not at the usual panel spot)
GUILD_TABS = ("members", "week", "research", "shop", "management", "leaderboard")


def _norm(w):
    return w["text"].lower().strip(":.")


# ---------- "is this screen open?" anchors (OCR words of the top band) ----------
def hourglass_open(words, size) -> bool:
    """True when the 'Hourglass' title is shown at the top-left (the side-menu tile is in the middle of the screen)."""
    W, H = size
    return any(_norm(w) == "hourglass" and w["y"] < H * TITLE_BOTTOM and w["x"] < W * 0.5 for w in words)


def guild_open(words, size) -> bool:
    """True when at least 3 guild tab headers (Members, Week, Research, ...) are in the top band."""
    H = size[1]
    return len({_norm(w) for w in words if w["y"] < H * TITLE_BOTTOM} & set(GUILD_TABS)) >= 3


def monthly_open(words, size) -> bool:
    """True when the full-screen 'Monthly Rewards' panel is showing (the game opens it at the daily reset, behind the
    'Reward Received / Touch anywhere to close' popup). It is only ever closed, never opened, by this tool."""
    H = size[1]
    return {"monthly", "rewards"} <= {_norm(w) for w in words if w["y"] < H * TITLE_BOTTOM}


# ---------- side menu ----------
def menu_open(words, size) -> bool:
    """True when the side menu is showing: its 'Offline Gains Rate' header or the Hourglass tile."""
    H = size[1]
    header = {_norm(w) for w in words if w["y"] < H * TITLE_BOTTOM} >= {"offline", "gains"}
    return header or find_menu_tile(words) is not None


def find_menu_tile(words):
    """Pixel center of the 'Hourglass of Eternity' tile in the side menu, or None."""
    for a in words:
        if _norm(a) != "hourglass":
            continue
        for b in words:
            if _norm(b) == "eternity" and 0 < b["y"] - a["y"] < 40 and abs(b["x"] - a["x"]) < 120:
                return (min(a["x"], b["x"]) + max(a["x"] + a["w"], b["x"] + b["w"])) / 2, (a["y"] + b["y"] + b["h"]) / 2
    return None


def find_guild_tile(words, size):
    """Pixel center of the 'Guild' tile in the side menu (mid-screen; the bottom-bar 'Guild' is below BAR_TOP), or None."""
    H = size[1]
    for w in words:
        if _norm(w) == "guild" and H * 0.2 < w["y"] < H * BAR_TOP:
            return w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    return None


# 'bar' / 'tile' say how to open a screen; screens without them can only be recognized and closed. 'close' = X position.
SCREENS = {
    "hourglass": {"label": "Hourglass of Eternity", "is_open": hourglass_open, "bar": "menu",
                  "tile": lambda words, size: find_menu_tile(words)},
    "guild": {"label": "Guild", "is_open": guild_open, "bar": "guild", "tile": find_guild_tile},
    "monthly": {"label": "Monthly Rewards", "is_open": monthly_open, "close": MONTHLY_CLOSE},
}


# ---------- bottom bar ----------
def _bar_label(text):
    """Bar label an OCR word stands for, tolerating clipped reads ('nventory', 'haracter'), else None."""
    t = text.lower().strip(":.")
    for label in BAR_LABELS:
        if t == label or (len(t) >= 5 and t in label) or (len(label) >= 4 and label in t):
            return label
    return None


def find_bar(words, size, button="menu"):
    """(is_base_screen, pixel center of the bar `button` or None) from the bottom bar labels.

    OCR on a bright background often drops labels (even 'Menu'), so when the button's label is missing its position is
    extrapolated from the labels that were read, using the bar's fixed layout (BAR_X) and their median offset."""
    W, H = size
    seen = {}
    for w in words:
        label = _bar_label(w["text"]) if w["y"] > H * BAR_TOP else None
        if label:
            seen.setdefault(label, w)
    if len(seen) < BAR_MIN_LABELS:
        return False, None
    if button in seen:
        b = seen[button]
        return True, (b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
    cy = sorted(w["y"] + w["h"] / 2 for w in seen.values())[len(seen) // 2]
    deltas = sorted((w["x"] + w["w"] / 2) / W - BAR_X[k] for k, w in seen.items())
    return True, ((BAR_X[button] + deltas[len(deltas) // 2]) * W, cy)


def classify(words, size, target="hourglass"):
    """-> (state, pixel position to click or None).

    State: the name of the screen that is open ('hourglass' | 'guild'; equals `target` when already there),
    or 'menu' (side menu, click the target's tile) | 'base' (click the target's bar button) | 'unknown'."""
    for name, s in SCREENS.items():
        if s["is_open"](words, size):
            return name, None
    spec = SCREENS[target]
    if "bar" not in spec:
        raise ValueError(f"'{target}' can only be closed, not opened")
    if menu_open(words, size):
        tile = spec["tile"](words, size)
        return ("menu", tile) if tile else ("unknown", None)
    base, btn = find_bar(words, size, spec["bar"])
    if base and btn:
        return "base", btn
    return "unknown", None


def read_frame(img):
    """OCR words of the whole frame, reading the top band and the bottom bar as separate crops.

    The bar sits on a changing background (desert vs. dark cave): on the full frame the auto-contrast is decided by
    the whole image and every bar label can be lost, while the cropped band reads them all."""
    W, H = img.size
    top_h, bot_y = int(H * TITLE_BOTTOM), int(H * BAR_TOP)
    words = [w for w in read_words(img, scale=2) if top_h <= w["y"] < bot_y]
    words += read_words(img.crop((0, 0, W, top_h)), scale=2)
    for w in read_words(img.crop((0, bot_y, W, H)), scale=2):
        words.append({**w, "y": w["y"] + bot_y})
    return words


def locate(img, target="hourglass"):
    """OCRs the frame and returns which screen is showing plus the position vectors used to reach `target`.

    {'state': 'hourglass'|'guild'|'menu'|'base'|'unknown',
     'click': {'x','y'} fractions (0-1) of the next button to press, or None,
     'next': what that click presses (e.g. 'Menu', 'Guild', 'Hourglass of Eternity') or None,
     'bar': labels of the bottom bar that were read, 'words': every OCR word as fractions}.
    Read-only: never clicks."""
    words = read_frame(img)
    state, pos = classify(words, img.size, target)
    W, H = img.size
    spec = SCREENS[target]
    bar = sorted({_bar_label(w["text"]) for w in words if w["y"] > H * BAR_TOP} - {None})
    return {
        "state": state,
        "click": {"x": pos[0] / W, "y": pos[1] / H} if pos else None,
        "next": {"base": spec["bar"].capitalize(), "menu": spec["label"]}.get(state),
        "bar": bar,
        "words": [{"text": w["text"], "x": w["x"] / W, "y": w["y"] / H, "w": w["w"] / W, "h": w["h"] / H} for w in words],
    }


def ensure_open(title, grab, click_client, target="hourglass", log=print, steps=4, close_others=False):
    """Opens `target` if it is closed; if it is already open nothing is clicked.
    With close_others=True, a different known screen that is open (e.g. Hourglass, which the app keeps open) is closed
    with its X first; by default that case is reported and nothing is clicked.
    Returns 'already' | 'opened' | None (not opened / unclear: nothing was forced)."""
    spec = SCREENS[target]
    if "bar" not in spec:
        raise ValueError(f"'{target}' can only be closed, not opened")
    acted = False
    for _ in range(steps + (1 if close_others else 0)):
        img = grab(title)
        if not acted:  # cheap check first: OCR only the title band
            top = img.crop((0, 0, img.width, int(img.height * TITLE_BOTTOM)))
            if spec["is_open"](read_words(top, scale=2), img.size):
                return "already"
        state, pos = classify(read_frame(img), img.size, target)
        if state == target:
            return "opened" if acted else "already"
        if close_others and state in SCREENS and state != target:
            log(f"{state} screen is open: closing it to open {target}")
            if not close_screen(title, grab, click_client, state, log=log):
                return None
            acted = True
            continue
        if state not in ("menu", "base"):
            why = f"the {state} screen is open" if state in SCREENS else "the screen is not recognized"
            log(f"{target} screen closed, but {why}: did not click")
            return None
        if not click_client(title, pos[0] / img.width, pos[1] / img.height):
            log(f"{target} screen closed, but the game is not clickable")
            return None
        acted = True
        time.sleep(1.2)
    log(f"Could not open the {target} screen")
    return None


def ensure_hourglass_open(title, grab, click_client, log=print, steps=4):
    return ensure_open(title, grab, click_client, "hourglass", log, steps)


CLOSE_BUTTON = (0.873, 0.062)  # the X at the top right of every panel (fractions of the client area)


def close_screen(title, grab, click_client, name="guild", log=print, tries=2):
    """Closes the open `name` screen with its X button. Returns True when it is no longer open (or was not open).
    Only clicks while that screen is actually showing."""
    is_open = SCREENS[name]["is_open"]
    for _ in range(tries):
        img = grab(title)
        if not is_open(read_words(img.crop((0, 0, img.width, int(img.height * TITLE_BOTTOM))), scale=2), img.size):
            return True
        if not click_client(title, *SCREENS[name].get("close", CLOSE_BUTTON)):
            log(f"could not close the {name} screen: the game is not clickable")
            return False
        time.sleep(1.2)
    img = grab(title)
    return not is_open(read_words(img.crop((0, 0, img.width, int(img.height * TITLE_BOTTOM))), scale=2), img.size)

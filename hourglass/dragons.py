"""Dragon training rules: reads levels/buttons from OCR and decides who should train."""
import re

_LV = re.compile(r"L[vV]\.?\s*(\d+)")
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})


def parse_level(text: str) -> int | None:
    m = _LV.search(text or "")
    return int(m.group(1)) if m else None


def parse_button(text: str) -> str | None:
    """'train' (available), 'training' (in training) or None if it cannot be determined."""
    t = re.sub(r"[^a-z]", "", (text or "").lower())
    if t == "train":
        return "train"
    if t.startswith("training"):
        return "training"
    return None


def build_plan(goals: list[dict]) -> list[tuple[str, int]]:
    """UI goals (order = priority) -> [(dragon, goal level)] for enabled ones with goal > 0."""
    return [(g["name"], int(g["goal"])) for g in goals if g.get("on") and int(g.get("goal") or 0) > 0]


def wanted_dragon(plan: list[tuple[str, int]], levels: dict[str, int | None]) -> str | None:
    """First plan step whose dragon has not reached its goal level yet. None = nothing to do
    (plan finished or level unreadable: when in doubt it does not act)."""
    for name, until in plan:
        lvl = levels.get(name)
        if lvl is None:
            return None
        if lvl < until:
            return name
    return None


_NEXT = re.compile(r"lv\s*\d+\s*:\s*(.*)$")
_PART = re.compile(r"(\d+)\s*([dhms])")
_SECS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_timer(text: str) -> int | None:
    """Seconds left until the next level, from e.g. 'Lv278 To lv279: 5h 41m' (None if unreadable)."""
    matches = _NEXT.findall((text or "").lower().replace("\n", " "))
    if not matches:
        return None
    parts = _PART.findall(matches[-1])
    return sum(int(n) * _SECS[u] for n, u in parts) if parts else None

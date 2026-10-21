"""Extracts numbers from OCR text (e.g. '+3.03e90/s', '1.64e94 / 1.00e120')."""
import re
from decimal import Decimal

_NUM = re.compile(
    r"(?P<m>\d+(?:[.,]\d+)?)\s*[eE]\s*(?P<e>[+-]?\d+)"
    r"|(?P<p>\d+(?:[.,]\d+)?)\s*(?P<s>[KMBT])?(?![\w])"
)
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_UNIT = re.compile(r"/\s*(min|sec|hr|[smhd])\b", re.IGNORECASE)
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _f(txt: str) -> float:
    return float(txt.replace(",", "."))


_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})


def find_numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer((text or "").translate(_FIX)):
        if m.group("m"):
            out.append(float(Decimal(m.group("m").replace(",", ".")).scaleb(int(m.group("e")))))
        else:
            out.append(_f(m.group("p")) * _SUFFIX.get((m.group("s") or "").upper(), 1))
    return out


def parse_number(text: str) -> float | None:
    nums = find_numbers(text)
    return nums[0] if nums else None


def parse_rate(text: str, default_unit: str = "s") -> float | None:
    """Gain per SECOND from texts like '+7.34e11 / h'."""
    value = parse_number(text)
    if value is None:
        return None
    m = _UNIT.search(text)
    unit = (m.group(1) if m else default_unit).lower()
    unit = {"min": "m", "sec": "s", "hr": "h"}.get(unit, unit)
    return value / UNIT_SECONDS[unit]

import math


def eta_seconds(current: float, target: float, gain_per_sec: float | None) -> float | None:
    """ElapTime = (Target - Current) / Gain. None if there is no positive gain."""
    if current >= target:
        return 0.0
    if not gain_per_sec or gain_per_sec <= 0:
        return None
    return (target - current) / gain_per_sec


def fmt_num(x: float | None) -> str:
    if x is None:
        return "—"
    if x != 0 and (abs(x) >= 1e4 or abs(x) < 1e-2):
        m, e = f"{x:.2e}".split("e")
        return f"{m}e{int(e)}"
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    if math.isinf(sec) or sec > 100 * 365 * 86400:
        return "> 100 years"
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = [f"{d}d"] if d else []
    if d or h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    if not d and not h:
        parts.append(f"{s}s")
    return " ".join(parts)

import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "config.json"
_W, _H = 1353, 663  # reference screenshot size used for the default regions


def _r(x0, y0, x1, y1):
    return {"x": x0 / _W, "y": y0 / _H, "w": (x1 - x0) / _W, "h": (y1 - y0) / _H}


_W2, _H2 = 1681, 770  # real game window (reference for tabs/dragons)


def _r2(x0, y0, x1, y1):
    return {"x": x0 / _W2, "y": y0 / _H2, "w": (x1 - x0) / _W2, "h": (y1 - y0) / _H2}


DEFAULT = {
    "window_title": "",
    "interval": 15,
    "scan_tabs": False,
    "auto_close_popups": True,
    "auto_open_screen": True,
    "guild_routine": {"enabled": False, "time": "04:00", "last_done": ""},  # daily at 04:00 BRT; last_done = BRT date
    "scan_minutes": 5,
    "home_tab": "infinity",
    "tabs": {"infinity": {"x": 312 / _W2, "y": 335 / _H2}, "echo": {"x": 660 / _W2, "y": 228 / _H2},
             "dragons": {"x": 717 / _W2, "y": 335 / _H2}, "upgrades": {"x": 308 / _W2, "y": 462 / _H2}},
    "dragon_auto": False,
    "dragon_goals": [{"name": "red", "goal": 300, "on": True}, {"name": "green", "goal": 650, "on": True},
                     {"name": "blue", "goal": 0, "on": False}],
    "dragons": {n: {"info": _r2(995, y - 12, 1335, y + 12), "button": _r2(1332, y - 9, 1434, y + 29)}
                for n, y in {"red": 152, "blue": 223, "green": 294}.items()},
    "trackers": [
        {"name": "Sand", "enabled": True, "target": "", "gain_unit": "s", "alert_before_min": 0,
         "current": _r(638, 106, 738, 136), "gain": _r(535, 106, 645, 136)},
        {"name": "Infinity", "enabled": True, "target": "", "gain_unit": "h", "alert_before_min": 0,
         "current": _r(925, 445, 1120, 497), "gain": _r(960, 510, 1085, 540)},
        {"name": "Echo", "enabled": True, "target": "", "gain_unit": "m", "alert_before_min": 0,
         "current": None, "gain": None},
    ],
}


ON_TARGET = {"enabled": False, "upgrade": "Timeline Output", "fired": False, "fired_at": ""}


def load() -> dict:
    cfg = json.loads(PATH.read_text(encoding="utf8")) if PATH.exists() else {}
    for k, v in DEFAULT.items():  # fill in new keys on old configs (trackers are never merged)
        if k not in cfg:
            cfg[k] = json.loads(json.dumps(v))
    for name, pos in DEFAULT["tabs"].items():  # new tabs on old configs
        cfg.setdefault("tabs", {}).setdefault(name, pos)
    for t in cfg.get("trackers", []):  # one-shot action, only for Sand
        if t["name"] == "Sand" and "on_target" not in t:
            t["on_target"] = dict(ON_TARGET)
    return cfg


def save(cfg: dict) -> None:
    PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf8")

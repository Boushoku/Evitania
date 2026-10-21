"""Reads the current game values once (no GUI, no alerts) and prints them as JSON.

Usage: .venv\\Scripts\\python scripts/read_values.py [--no-scan] [--dragons]
  --no-scan  only read regions of the tab currently shown (no tab clicking)
  --dragons  also read dragon level / timer / button state
Needs the game window visible on the active desktop to switch tabs (Unity ignores background clicks).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hourglass import config, gameinput  # noqa: E402
from hourglass.capture import crop_region, grab  # noqa: E402
from hourglass.dragons import parse_button, parse_level, parse_timer  # noqa: E402
from hourglass.ocr import read_text  # noqa: E402
from hourglass.parsing import find_numbers, parse_number, parse_rate  # noqa: E402

REGION_KEYS = ("current", "gain", "add", "target_region")


def main(argv):
    scan, want_dragons = "--no-scan" not in argv, "--dragons" in argv
    cfg = config.load()
    title = cfg["window_title"]
    trackers = [t for t in cfg["trackers"] if t.get("enabled")]
    tabs = {r["tab"] for t in trackers for r in (t.get(k) for k in REGION_KEYS) if r and r.get("tab")}
    if want_dragons:
        tabs.add("dragons")
    home = cfg.get("home_tab")
    order = sorted(tabs, key=lambda n: n == home) if scan else []

    imgs = {None: grab(title)}
    try:
        for tab in order:
            pos = cfg["tabs"][tab]
            if not gameinput.click_client(title, pos["x"], pos["y"]):
                raise SystemExit(f"cannot click tab '{tab}': {gameinput.LAST_BLOCK}")
            time.sleep(1.5)
            imgs[tab] = grab(title)
    finally:
        if order and home in cfg["tabs"]:
            gameinput.click_client(title, cfg["tabs"][home]["x"], cfg["tabs"][home]["y"])

    def read(region):
        img = imgs.get(region.get("tab")) if scan else imgs[None]
        return read_text(crop_region(img, region)) if img is not None else None

    out = {"trackers": {}}
    for t in trackers:
        raw = {k: read(t[k]) for k in REGION_KEYS if t.get(k)}
        cur = find_numbers(raw.get("current") or "")
        value = cur[0] if cur else None
        if value is not None and "add" in raw:
            extra = parse_number(raw["add"] or "")
            value = value + extra if extra is not None else None
        out["trackers"][t["name"]] = {
            "raw": raw, "current": value,
            "gain_per_sec": parse_rate(raw["gain"], t["gain_unit"]) if raw.get("gain") else None,
            "target": parse_number(t["target"]) if t.get("target") else None,
        }
    if want_dragons and "dragons" in imgs:
        out["dragons"] = {}
        for name, d in cfg["dragons"].items():
            info = read_text(crop_region(imgs["dragons"], d["info"]))
            btn = read_text(crop_region(imgs["dragons"], d["button"]))
            out["dragons"][name] = {"raw": info, "level": parse_level(info),
                                    "seconds_to_next": parse_timer(info), "button": parse_button(btn)}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

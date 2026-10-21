"""Detects which game screen is showing (OCR + word positions) and opens a screen (hourglass | guild) if it is closed. Prints JSON.

Usage: .venv\\Scripts\\python scripts/open_screen.py [--screen hourglass|guild] [--check] [--words]
  --screen which screen to reach (default hourglass)
  --check  only report the screen and the button it would press (no clicks)
  --words  include every OCR word with its position (fractions 0-1 of the client area)
Opening is real mouse clicks (hourglass: Menu -> Hourglass of Eternity; guild: bottom-bar Guild or the side-menu tile), so the game must be visible on the active desktop.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hourglass import config, gameinput  # noqa: E402
from hourglass.capture import grab  # noqa: E402
from hourglass.screens import SCREENS, ensure_open, locate  # noqa: E402


def main(argv):
    title = config.load()["window_title"]
    target = argv[argv.index("--screen") + 1] if "--screen" in argv else "hourglass"
    if target not in SCREENS:
        raise SystemExit(f"unknown screen '{target}'; choose one of: {', '.join(SCREENS)}")
    before = locate(grab(title), target)
    out = {"screen": target, "before": before["state"], "next_click": before["next"], "click_at": before["click"], "bar": before["bar"]}
    if "--words" in argv:
        out["words"] = before["words"]
    if "--check" not in argv:
        notes = []
        out["result"] = ensure_open(title, grab, gameinput.click_client, target, log=notes.append)
        out["after"] = locate(grab(title), target)["state"]
        if notes:
            out["notes"] = notes
        if not out["result"] and gameinput.LAST_BLOCK:
            out["blocked"] = gameinput.LAST_BLOCK
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

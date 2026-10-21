"""Runs the daily guild routine once (Support the active research, 2 donations, Week refresh) and prints a JSON report.

Usage: .venv\\Scripts\\python scripts/guild_daily.py [--dry-run]
  --dry-run  navigates and reads everything but never clicks Support or Donate (and skips the Week refresh clicks)
Needs the game visible on the active desktop (real mouse clicks / wheel). Never presses Start.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hourglass import config, gameinput  # noqa: E402
from hourglass.capture import grab  # noqa: E402
from hourglass.guild_routine import run_daily  # noqa: E402


def main(argv):
    title = config.load()["window_title"]
    rep = run_daily(title, grab, gameinput.click_client, gameinput.scroll_client, dry_run="--dry-run" in argv,
                    log=lambda m: print(m, file=sys.stderr))
    if not rep["ok"] and gameinput.LAST_BLOCK:
        rep["blocked"] = gameinput.LAST_BLOCK
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

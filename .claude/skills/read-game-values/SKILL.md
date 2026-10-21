---
name: read-game-values
description: Read the live Evitania values (Sand, Infinity, Echo current/gain/target, dragon levels and timers) from the running game window via OCR and report them or the ETA. Use when the user asks for current values, how long until a target, or wants to check that OCR/regions still read correctly.
---

# Read game values

Runs the app's own OCR pipeline once, headless, and prints JSON.

1. From the project root run:
   `.venv\Scripts\python scripts/read_values.py` (add `--dragons` for dragon data, `--no-scan` to skip tab clicking and read only the visible tab).
2. Interpret the output per tracker: `raw` is the OCR text of each region, `current` the parsed value (Infinity = current + `add`), `gain_per_sec` the normalized rate, `target` from config.
3. For an ETA use `hourglass.calc.eta_seconds(current, target, gain_per_sec)`, and `fmt_duration` / `fmt_num` for display.

Notes:
- Tab switching is a real mouse click, so the game must be visible on the active desktop. The script returns to `home_tab` afterwards. If it fails with "cannot click", ask the user to bring the window forward or use `--no-scan`.
- A `null` current/gain with odd `raw` text means an OCR misread or a region/tab out of place. Do not guess the number; report the raw text and suggest re-picking the region in the app.
- This skill is read-only: never click Buy or dragon-train buttons from it.
- Regions are fractions (0-1) of the window client area in `config.json` (gitignored, user-specific); don't overwrite it.

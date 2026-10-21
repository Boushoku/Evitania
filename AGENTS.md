# Hourglass Timer — agent guide

Windows desktop tool (Python + tkinter) for the Unity game **Evitania Online**. It screenshots the game window, OCRs on-screen numbers, computes `ETA = (Target - Current) / Gain`, and alerts (toast + sound). It can also auto-train dragons and one-shot buy an upgrade.

## Commands
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py                                   # GUI (run.bat does the same)
.venv\Scripts\python -m unittest discover -s tests -t .        # tests (pure logic only, no game needed)
.venv\Scripts\python scripts/read_values.py [--dragons] [--no-scan]   # read live values once, JSON
```
Windows only (pywin32, winrt OCR). No linter is configured.

## Layout
| File | Role |
|---|---|
| `hourglass/app.py` | tkinter UI + worker thread, cycle scheduling, tab scanning, tracker logic |
| `hourglass/capture.py` | `grab(title)` via PrintWindow (works covered/background, not minimized); `crop_region` |
| `hourglass/ocr.py` | Windows.Media.Ocr; `read_text` (multi-scale vote), `read_words` (with positions) |
| `hourglass/parsing.py` | `find_numbers`, `parse_number`, `parse_rate` (OCR text -> numbers, per second) |
| `hourglass/calc.py` | `eta_seconds`, `fmt_num`, `fmt_duration` |
| `hourglass/dragons.py` | level/timer/button parsing, training plan rules |
| `hourglass/upgrades.py`, `popups.py` | find-by-text + color-based Buy click; close "Touch anywhere" popups |
| `hourglass/gameinput.py` | real mouse clicks (Unity ignores posted messages) |
| `hourglass/config.py` | defaults + load/save of `config.json` |
| `hourglass/screens.py` | which screen is open (OCR word positions) and opening it (Hourglass, Guild); see `docs/guild.md` |
| `hourglass/guild.py`, `guild_routine.py` | read the Guild tabs (Research rows, Donations card) and the daily routine (04:00 BRT); see `docs/guild.md` |

## How values are obtained (the data pipeline)
1. `capture.grab(window_title)` returns a PIL image of the **client area**.
2. Each tracker in `config.json` has regions (`current`, `gain`, optional `add`, `target_region`) stored as **fractions 0-1** of the client area, so resizing the window is safe. A region may name a `tab`.
3. Values on other tabs: `app._needed_tabs` clicks each tab (`tabs` positions, also fractions), waits ~1s, recaptures until regions parse, and ends on `home_tab`. Scans run every `scan_minutes`; in between, last value + gain x elapsed time is used (`cur_src: extrapolated`).
4. `ocr.read_text(crop_region(img, region))` returns text. OCR is scale-sensitive, so it reads at 2x/3x/4x and votes; it falls back to binarized variants.
5. `parsing` extracts numbers: scientific (`1.64e94`), K/M/B/T suffixes, OCR fixes (`O`->0, `l`->1). `parse_rate` divides by the unit (`/s /m /h /d`) to get per-second; `gain_unit` in config is the default when the unit text is missing.
6. Guards: `_gain_plausible` rejects >100x jumps unless seen twice; a missing `add` part makes the whole value unread (no partial sums).

To read values by hand or automatically, use `scripts/read_values.py` or the `read-game-values` skill (`.claude/skills/read-game-values/`).

## Conventions and gotchas
- UI text and code comments are in English.
- `config.json` is user-specific and **gitignored** (regions, targets, dragon goals). Never overwrite or commit it; new defaults go in `config.DEFAULT` (missing keys are back-filled on load).
- Clicks are real mouse events: the game must be visible on the active desktop. `click_client` refuses if covered and restores the cursor.
- When in doubt (unreadable level/value) the code does **not** act. Keep that bias for anything that clicks.
- Keep game/OCR calls out of unit tests; keep pure logic (parsing/calc/dragons) testable and add tests in `tests/`.
- Long work (OCR, clicks) runs in a worker thread; touch tkinter only from the main thread (`root.after`).

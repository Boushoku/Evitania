---
name: open-game-screen
description: Detect which Evitania screen is showing (base, side Menu, Hourglass, Guild) by OCR and word positions, and open the Hourglass or Guild screen when it is closed. Use when values read as null because the game shows no panel, when the user says a screen is closed, or to check which screen is open before reading values or clicking.
---

# Open game screen

Reads the frame with OCR, takes the word position vectors (fractions 0-1 of the client area), decides the state and, if asked, navigates to the target screen. Logic: `hourglass/screens.py` (`SCREENS`, `read_frame`, `locate`, `classify`, `ensure_open`).

1. Check only (no clicks): `.venv\Scripts\python scripts/open_screen.py --screen guild --check` (add `--words` to see every OCR word with its position).
2. Open it if closed: `.venv\Scripts\python scripts/open_screen.py --screen guild` (`--screen hourglass` is the default).
3. Read the JSON: `before`/`after` is the open screen (`hourglass` | `guild`), or `menu` | `base` | `unknown`; `next_click` is the button it presses; `click_at` is that button's position; `result` is `already` (nothing clicked), `opened` or `null`.

Rule: already open -> do nothing; closed -> open it; unclear -> do not click.

Screens and how each is recognized / reached:
- `hourglass`: the word "Hourglass" at the top-left (title band, y < 12%). Reached via bottom-bar **Menu** -> side-menu tile **Hourglass of Eternity**.
- `guild`: at least 3 of the tab headers Members / Week / Research / Shop / Management / Leaderboard in the top band. Reached via the bottom-bar **Guild** button directly, or the **Guild** tile if the side menu is already open. Tabs of interest: Members, Week, Research (Shop, Management, Leaderboard also visible; Boss and Map are locked).
- `menu` (side menu): the "Offline Gains Rate" header or the Hourglass tile.
- `base`: at least 4 bottom-bar labels (Guild, Journal, Map, Inventory, Talents, Auto, Characters, Menu) are readable, so no panel covers the bar.
- `unknown`, or a different screen than the target is open: it does NOT click. Report which screen is open, or the words read (`--words`), instead of guessing.

Notes:
- Clicks are real mouse events: the game must be visible on the active desktop. `result: null` with `blocked: "covered by ..."` means ask the user to bring the window forward.
- The bar is read as its own crop (`read_frame`): on the full frame the labels can all be lost on a dark background. If a label is still missing, the button is extrapolated from the bar's fixed layout.
- It navigates only; it never presses Buy or dragon-train buttons. After opening the Hourglass screen, run `read-game-values` for the numbers.
- The app calls the Hourglass opening automatically each cycle (config `auto_open_screen`, default true). Guild is not wired into the app yet. `config.json` is user-specific and gitignored; don't overwrite it.
- To support another screen, add an `is_open` anchor and an entry in `SCREENS`, plus tests in `tests/test_screens.py`.

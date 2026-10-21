# Hourglass Timer

Reads values from the game window (Windows OCR), computes `(Target - Current) / Gain` and alerts (toast + sound).

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
.venv\Scripts\python -m unittest discover -s tests -t .
```

## Using it with an AI assistant

The repo is set up so a coding assistant (Claude Code, Codex, Cursor, Copilot, ...) can read the live game and drive the same actions the app does.

1. **Prepare the project once:** create the venv and install the requirements (above), run the app once and fill in the window title (`config.json` is created next to `main.py`).
2. **Open the repo folder in the assistant.** It picks up its instructions from these files:

   | File | What it gives the assistant |
   |---|---|
   | `AGENTS.md` | The shared guide: layout, how values are read, conventions and gotchas. Assistants that follow the `AGENTS.md` convention read it automatically; otherwise tell it to read that file first. |
   | `CLAUDE.md` | Claude Code's entry point; it imports `AGENTS.md`. |
   | `.claude/skills/` | Claude Code skills: `read-game-values` (current values and ETA) and `open-game-screen` (detect and open the Hourglass / Guild screen). |
   | `docs/guild.md` | What the Guild screens and their buttons mean, and the rules for the daily routine. |

3. **Scripts work with any assistant** (plain commands that print JSON):

   ```
   .venv\Scripts\python scripts/read_values.py [--dragons] [--no-scan]
   .venv\Scripts\python scripts/open_screen.py [--screen hourglass|guild] [--check] [--words]
   .venv\Scripts\python scripts/guild_daily.py [--dry-run]
   ```

   Example prompts: "read the current Sand and Infinity and tell me when I reach the target", "which screen is open in the game?", "run the guild routine as a dry run and report what it would do".

Things to keep in mind:

- **The game must be visible** on the active desktop (not minimized, nothing on top). Reading works in the background, but clicks are real mouse events, so a covered game is never clicked.
- **Use `--check` / `--dry-run` first.** They read and report without pressing Support or Donate. `guild_daily.py` without `--dry-run` really spends gold and the daily Support.
- **`config.json` is yours and is gitignored.** Ask the assistant not to overwrite or commit it. The app rewrites it from memory on every cycle and when it closes, so close the app before editing the file by hand (by you or by the assistant), or the change is lost.
- **Never Start a research.** Starting researches is left to other players; no script presses it.
- Teach the assistant new game knowledge by adding it to `docs/guild.md` (or a new file in `docs/`) and a line in `AGENTS.md`, so the next session does not rediscover it.

# Guild screen — game knowledge

What the Guild screen looks like and what each state means. Facts come from the player; **(inferred)** marks an
interpretation that was not confirmed. Nothing here is automated yet except opening the screen.

## Opening it

Implemented in `hourglass/screens.py` (`SCREENS["guild"]`, `ensure_open`), CLI: `scripts/open_screen.py --screen guild`.
- Already open -> nothing is clicked. Otherwise: bottom-bar **Guild** button, or the **Guild** tile if the side menu is open.
- "Open" is recognized by >= 3 tab headers (Members, Week, Research, Shop, Management, Leaderboard) in the top 12% of the window.
- Another screen open (e.g. Hourglass) -> no click, reported instead.

## Layout

- Top: tabs **Members, Week, Research, Shop, Management, Leaderboard**, plus two locked tabs (Boss, Map). Close = X at the top right.
- Left panel (every tab): guild name/level/members, XP bar, **Guild funds**, **Seals**, **Activity**, guild notice.
- The right content of Week and Research scrolls vertically (scrollbar on the right edge). The mouse layer only clicks today; scrolling is not implemented.
- Accounts differ (guild level, which tasks/researches exist, values). Do not assume a fixed list: match rows **by name**.
- The window size varies between setups; positions are fractions of the client area.

## Week tab

Top cards (visible only with the list scrolled to the top):
- **My week**: `Task seals a / b`, `Activity`, `Daily login` (green check when done, shows +activity / +seals).
- **Donations · n / 2 today**, current **gold** (top right of the card), the cost of the next donation and what it gives.
- Header: weekly reset countdown (`1d 12:39`) and the guild-activity chest bar.

Task list (names vary per account, e.g. Mine ore, Make donations, Perfect week, Chop wood, Support research, Kill monsters, Kill bosses):
- In progress: orange/yellow bar with `n / m`, reward icons (seals, activity) on the right, `Lv. x / y`.
- Not started: dark bar with `0 / m`.
- Done: green bar "Done until the weekly reset" and the text "All rewards collected".
- "Make donations 12/14" = 2 donations a day x 7 days.
- Open: whether a task has a claim button before its rewards are collected (no screenshot yet).

### Donation card state machine

| State | Looks like | Action |
|---|---|---|
| Can donate | Yellow **Donate X** button, `n / 2 today` with n < 2 | the only state where a click makes sense |
| No funds | Grey button, no check, gold < X | do not click |
| Feedback | Grey button **with a check mark** | transient after a donation; wait and re-read (confirmed) |
| Done | `2 / 2 today`, "Every donation made today", no button | nothing |

After a click, re-read until the state settles; the second donation costs much more (500K -> 10M seen), so check gold again.
Donating spends gold: no automation rule has been defined yet.

## Research tab

Each row: name, `Lv. x / 10` (some have no cap, e.g. Guild Growth `Lv. 3`), effect (`Weekly chest tiers: 11 -> 12`),
cost in **guild funds**, duration (`144h`), button on the right.

- Only one research runs at a time; the active one shows a progress bar with the remaining time (`2d 02:26`).
- Button states: **Start** (can begin a research), **Busy** (grey; another research is running) **(inferred)**,
  **Support (−N min)** (yellow, on the active research), **Used up** (grey; this player's Support was already given — confirmed).
- **Never click Start**: starting researches is the other players' responsibility (confirmed by the player).
- The Support amount is **not fixed**: it depends on the Research Efficiency level (Lv. 1 = −24 min, Lv. 4 = −36 min). Read it from the button.
  On the Research Efficiency row, "Support speed-up: −36 min -> −40 min" is current -> next level, a second source for the same number.
- Row order is not guaranteed: find rows by name, never by position. The list scrolls.
- The remaining time of the active research is an ETA the app could alert on (same idea as `calc.eta_seconds`).

## Members tab

Not documented yet.

## Daily routine (implemented)

The daily reset is at **04:00 BRT** (UTC-3, no DST). Code: `hourglass/guild_routine.py`, readers in `hourglass/guild.py`,
CLI `scripts/guild_daily.py [--dry-run]`, scheduler + "Guild" tab in the app (`guild_routine` in `config.json`: `enabled`, `time`, `last_done`).

Order, as the player does it by hand:
1. Close the reset popup, make sure the Guild screen is open. Whatever other known screen is open is closed with its X first:
   the Hourglass screen (the app keeps it open) and the full-screen **Monthly Rewards** panel that shows behind the
   "Reward Received / Touch anywhere to close" popup (its X is at a different spot, x~0.76 instead of 0.87).
2. **Research** tab -> find the active research (scrolling the list) -> click **Support** -> wait until the button reads **Used up**.
3. **Week** tab -> list scrolled to the top -> **Donate** up to 2 times. Each click is validated by OCR: the counter `n / 2 today` must go up
   (the backend can take a while, default wait 120 s, polling every 3 s). On a timeout it does **not** click again and reports the failure.
4. Click the **Week tab itself** twice (not the body): that is what makes the game sync the points to the server.
5. Close the Guild screen (X) so the normal Hourglass cycle can reopen its screen.

Rules it follows:
- Never clicks Start. Clicks Support only when the button text reads "Support" (a yellow button alone is not enough: it could be Start).
- Clicks Donate only when the button is yellow and the counter was read. Grey = no gold (not an error), grey + check = feedback: wait and re-read.
- Every step re-reads the screen first, so running it twice the same day does not repeat finished work.
- Scheduling: once per BRT day, from the configured time on (a late start catches up the same day). A failed scheduled run is retried every 3 minutes, at most 3
  attempts per BRT day (the first counts; after that it gives up until the next day, "Run now" still works);
  `last_done` is only saved when the run had no failures. The app must be open and the game visible on the active desktop.

How the readers work (see the module docstring): research rows are found by their `Lv. x / y` token, buttons by color
(yellow = enabled, grey (92,89,103) = disabled) plus OCR of the button crop, the active research by its timer bar.
OCR quirks seen: `Lv.` comes back as `w.`/`lv.`/`LV.`, `10M` as `IOM`, and grey-on-grey text is only readable on a crop.

## Rules for any further automation

- Read-only first. Never click Start. When a state is unreadable, do not click (project-wide bias).
- Re-read after every click until the UI settles.

import queue
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime, timedelta, timezone
from tkinter import ttk

from . import config
from .alerts import alert
from .calc import eta_seconds, fmt_duration, fmt_num
from .capture import CaptureError, crop_region, grab
from .dragons import build_plan, parse_button, parse_level, parse_timer, wanted_dragon
from .gameinput import click_client, click_rect, scroll_client
from .guild_routine import MAX_ATTEMPTS, RETRY_MINUTES, brt_date, retry_delay, routine_due, run_daily
from .popups import dismiss as dismiss_popups
from .screens import ensure_hourglass_open
from .upgrades import run_buy
from .ocr import read_text
from .parsing import find_numbers, parse_number, parse_rate
from .picker import pick_region

REGION_KEYS = ("current", "gain", "target_region", "add")
DRAGON_LABEL = {"red": "Red", "blue": "Blue", "green": "Green", "golden": "Golden", "black": "Black"}
DRAGON_MARGIN = 3  # seconds added to the level-up timer before the early check
MAX_ETA = 100 * 365 * 86400
HIST_SECONDS = 600  # window used to estimate the gain when it is not read from the screen


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Hourglass Timer")
        self.cfg = config.load()
        self.history = {}   # name -> deque[(t, value)]
        self.alerted = {}   # name -> bool
        self.last = {}      # name -> {"gain":…, "target":…}
        self.last_scan = 0.0  # epoch of the last tab scan
        self._dragon_after = None  # Tk id of the scheduled early dragon check
        self.reach = {}  # name -> consecutive readings with current >= target
        self.pending_action = None  # currency whose one-shot action should run when idle
        self.action_retry_at = {}  # name -> epoch before which the action is not retried
        self.action_vars = {}
        self.guild_retry_at = 0.0  # epoch before which a failed scheduled guild routine is not retried
        self.guild_attempts = ("", 0)  # (BRT date, scheduled attempts made that day)
        self.q = queue.Queue()
        self.busy = False
        self.running = False
        self.rows = {}
        self._build()
        self.root.after(200, self._poll)
        self.root.after(5000, self._guild_tick)

    # ---------- UI ----------
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Window (part of the title):").pack(side="left")
        self.title_var = tk.StringVar(value=self.cfg["window_title"])
        ttk.Entry(top, textvariable=self.title_var, width=26).pack(side="left", padx=4)
        ttk.Label(top, text="Interval (s):").pack(side="left", padx=(8, 0))
        self.interval_var = tk.IntVar(value=self.cfg["interval"])
        ttk.Spinbox(top, from_=5, to=600, textvariable=self.interval_var, width=5).pack(side="left", padx=4)
        self.btn_run = ttk.Button(top, text="▶ Start", command=self.toggle)
        self.btn_run.pack(side="left", padx=4)
        ttk.Button(top, text="Read now", command=lambda: self.run_cycle(force_scan=True)).pack(side="left")
        self.scan_var = tk.BooleanVar(value=self.cfg.get("scan_tabs", False))
        ttk.Checkbutton(top, text="Scan tabs (clicks in the game) every", variable=self.scan_var).pack(side="left", padx=4)
        self.scan_min_var = tk.DoubleVar(value=self.cfg.get("scan_minutes", 5))
        ttk.Spinbox(top, from_=1, to=120, increment=1, textvariable=self.scan_min_var, width=4).pack(side="left")
        ttk.Label(top, text="min").pack(side="left", padx=(2, 4))
        self.popup_var = tk.BooleanVar(value=self.cfg.get("auto_close_popups", True))
        ttk.Checkbutton(top, text="Auto-close popups", variable=self.popup_var).pack(side="left", padx=4)
        ttk.Button(top, text="Test alert", command=lambda: alert("Hourglass Timer", "Alert test")).pack(side="left", padx=4)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="x", padx=8)
        grid = ttk.Frame(nb, padding=8)
        nb.add(grid, text="Currencies")
        dtab = ttk.Frame(nb, padding=8)
        nb.add(dtab, text="Dragons")
        self._build_dragons(dtab)
        gtab = ttk.Frame(nb, padding=8)
        nb.add(gtab, text="Guild")
        self._build_guild(gtab)
        heads = ["", "Currency", "Current", "Gain/s", "Target", "Remaining", "Finishes at", "Alert before (min)", "Regions"]
        for c, h in enumerate(heads):
            ttk.Label(grid, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=4, sticky="w")
        for r, t in enumerate(self.cfg["trackers"], start=1):
            self._row(grid, r, t)
        self._build_actions(grid, len(self.cfg["trackers"]) + 1)

        self.status = tk.StringVar(value="Ready. Set the regions and click Start.")
        ttk.Label(self.root, textvariable=self.status, padding=(8, 0)).pack(fill="x")
        self.log = tk.Text(self.root, height=7, width=100, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- Dragons tab ----------
    def _build_dragons(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x")
        self.dragon_var = tk.BooleanVar(value=self.cfg.get("dragon_auto", False))
        ttk.Checkbutton(bar, text="Switch dragon automatically (runs during the tab scan)",
                        variable=self.dragon_var).pack(side="left")
        ttk.Button(bar, text="Read levels now", command=self.read_dragons_now).pack(side="right")
        ttk.Label(parent, text="Order is priority: trains the first enabled dragon that has not reached its goal yet.").pack(anchor="w", pady=4)
        self.dtable = ttk.Frame(parent)
        self.dtable.pack(fill="x")
        self.dvars = {}
        for g in self.cfg["dragon_goals"]:
            self.dvars[g["name"]] = {"level": tk.StringVar(value="—"), "state": tk.StringVar(value="—"),
                                     "situ": tk.StringVar(value=""), "timer": tk.StringVar(value="—"), "on": tk.BooleanVar(value=g["on"]),
                                     "goal": tk.StringVar(value=str(g["goal"] or ""))}
        self.dragon_next = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.dragon_next, foreground="#0a6").pack(anchor="w", pady=(6, 0))
        self.dragon_info = None  # last (levels, buttons, timers) read
        self._render_dragons()

    def _render_dragons(self):
        for w in self.dtable.winfo_children():
            w.destroy()
        for c, h in enumerate(["Order", "Enabled", "Dragon", "Current level", "State", "Goal (level)", "Next level in", "Status"]):
            ttk.Label(self.dtable, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=4, sticky="w")
        for r, g in enumerate(self.cfg["dragon_goals"], start=1):
            v = self.dvars[g["name"]]
            mv = ttk.Frame(self.dtable)
            mv.grid(row=r, column=0, padx=4)
            ttk.Button(mv, text="▲", width=2, command=lambda i=r - 1: self._move_dragon(i, -1)).pack(side="left")
            ttk.Button(mv, text="▼", width=2, command=lambda i=r - 1: self._move_dragon(i, 1)).pack(side="left")
            ttk.Checkbutton(self.dtable, variable=v["on"]).grid(row=r, column=1)
            ttk.Label(self.dtable, text=DRAGON_LABEL.get(g["name"], g["name"]), width=10).grid(row=r, column=2, sticky="w")
            ttk.Label(self.dtable, textvariable=v["level"], width=11).grid(row=r, column=3, sticky="w")
            ttk.Label(self.dtable, textvariable=v["state"], width=12).grid(row=r, column=4, sticky="w")
            ttk.Entry(self.dtable, textvariable=v["goal"], width=8).grid(row=r, column=5, padx=4)
            ttk.Label(self.dtable, textvariable=v["timer"], width=12).grid(row=r, column=6, sticky="w")
            ttk.Label(self.dtable, textvariable=v["situ"], width=34).grid(row=r, column=7, sticky="w")
        if self.dragon_info:
            self._show_dragons(*self.dragon_info)

    def _move_dragon(self, i, d):
        goals = self.cfg["dragon_goals"]
        if 0 <= i + d < len(goals):
            self._sync_cfg()
            goals[i], goals[i + d] = goals[i + d], goals[i]
            config.save(self.cfg)
            self._render_dragons()

    def _show_dragons(self, levels, buttons, timers):
        self.dragon_info = (levels, buttons, timers)
        self._sync_cfg()
        want = wanted_dragon(build_plan(self.cfg["dragon_goals"]), levels)
        states = {"train": "available", "training": "training", None: "?"}
        for g in self.cfg["dragon_goals"]:
            n, v = g["name"], self.dvars[g["name"]]
            lvl = levels.get(n)
            v["level"].set("?" if lvl is None else str(lvl))
            v["state"].set(states[buttons.get(n)])
            v["timer"].set(fmt_duration(timers[n]) if timers.get(n) is not None else "—")
            if not g["on"] or not g["goal"]:
                v["situ"].set("disabled")
            elif lvl is not None and lvl >= g["goal"]:
                v["situ"].set("goal reached ✓")
            elif n == want:
                v["situ"].set("up next (training)" if buttons.get(n) == "training" else "up next → will switch")
            else:
                v["situ"].set("waiting")

    def read_dragons_now(self):
        """Read-only: clicks the Dragons tab, reads, and returns to the home tab; does not switch dragons."""
        if self.busy:
            return
        self._sync_cfg()
        self.busy = True
        threading.Thread(target=self._read_dragons_worker, daemon=True).start()

    def _read_dragons_worker(self):
        try:
            title, tabs = self.cfg["window_title"], self.cfg["tabs"]
            self._close_popups(title)
            self._ensure_screen(title)
            if not click_client(title, tabs["dragons"]["x"], tabs["dragons"]["y"]):
                self.q.put(("note", "Game is not visible on the active desktop; could not read the dragons"))
                return
            time.sleep(1.5)
            data = self._read_dragons(grab(title))
            self.q.put(("dragons", data))
            self.q.put(("dragon_due", self._early_due(*data)))
            home = tabs.get(self.cfg.get("home_tab"))
            if home:
                click_client(title, home["x"], home["y"])
        except Exception as e:
            self.q.put(("error", str(e)))
        finally:
            self.q.put(("done", None))

    # ---------- Guild daily routine ----------
    def _build_guild(self, parent):
        g = self.cfg["guild_routine"]
        row = ttk.Frame(parent)
        row.pack(fill="x")
        self.guild_on = tk.BooleanVar(value=g["enabled"])
        ttk.Checkbutton(row, text="Run the daily guild routine (clicks in the game) at", variable=self.guild_on).pack(side="left")
        self.guild_time = tk.StringVar(value=g["time"])
        ttk.Entry(row, textvariable=self.guild_time, width=6).pack(side="left", padx=4)
        ttk.Label(row, text="BRT").pack(side="left")
        ttk.Button(row, text="Dry run", command=lambda: self.start_guild(dry_run=True)).pack(side="left", padx=(12, 2))
        ttk.Button(row, text="Run now", command=lambda: self.start_guild(dry_run=False)).pack(side="left")
        ttk.Label(parent, foreground="#666", text="Supports the active research, makes the 2 donations (each confirmed by OCR) and "
                  "refreshes the Week tab. Never presses Start. Dry run reads and reports without clicking Support/Donate.").pack(anchor="w", pady=(6, 0))
        self.guild_status = tk.StringVar()
        ttk.Label(parent, textvariable=self.guild_status).pack(anchor="w", pady=(4, 0))
        self._refresh_guild_status()

    def _guild_hhmm(self):
        t = self.guild_time.get().strip()
        ok = len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit() and int(t[:2]) < 24 and int(t[3:]) < 60
        return t if ok else self.cfg["guild_routine"]["time"]

    def _refresh_guild_status(self, note=""):
        g = self.cfg["guild_routine"]
        state = "armed" if g["enabled"] else "disarmed"
        last = f"last done {g['last_done']}" if g["last_done"] else "never done"
        self.guild_status.set(f"{state} at {g['time']} BRT; {last}" + (f" — {note}" if note else ""))

    def start_guild(self, dry_run=False, scheduled=False):
        if self.busy:
            self.status.set("Busy; try again in a few seconds")
            return
        self._sync_cfg()
        self.busy = True
        threading.Thread(target=self._guild_worker, args=(dry_run, scheduled), daemon=True).start()

    def _guild_worker(self, dry_run, scheduled):
        try:
            title = self.cfg["window_title"]
            self._close_popups(title)  # the 4 AM reset shows a 'Touch anywhere' popup first
            rep = run_daily(title, grab, click_client, scroll_client, dry_run=dry_run,
                            log=lambda m: self.q.put(("note", m)))
        except Exception as e:
            rep = {"ok": False, "notes": [f"error: {e}"]}
        self.q.put(("guild", (rep, dry_run, scheduled)))
        self.q.put(("done", None))

    def _guild_result(self, rep, dry_run, scheduled):
        g = self.cfg["guild_routine"]
        if dry_run:
            note = "dry run finished"
        elif rep["ok"]:
            g["last_done"] = brt_date(datetime.now(timezone.utc))
            config.save(self.cfg)
            note = "done"
        else:
            note = "FAILED"
            if scheduled:
                n = self.guild_attempts[1]
                delay = retry_delay(n)
                if delay is None:
                    note += f", gave up after {n} attempts today (use Run now to try again)"
                else:
                    self.guild_retry_at = time.time() + delay
                    note += f", attempt {n}/{MAX_ATTEMPTS}, retrying in {RETRY_MINUTES} min"
        self._log(f"Guild routine: {note}")
        self._refresh_guild_status(note)

    def _guild_tick(self):
        g = self.cfg["guild_routine"]
        today = brt_date(datetime.now(timezone.utc))
        attempts = self.guild_attempts[1] if self.guild_attempts[0] == today else 0
        if (self.guild_on.get() and not self.busy and time.time() >= self.guild_retry_at and attempts < MAX_ATTEMPTS
                and routine_due(datetime.now(timezone.utc), self._guild_hhmm(), g["last_done"])):
            self.guild_attempts = (today, attempts + 1)
            self.start_guild(scheduled=True)
        self.root.after(30000, self._guild_tick)

    # ---------- one-shot actions ----------
    def _build_actions(self, grid, row):
        box = ttk.LabelFrame(grid, text="One-shot action when the target is reached", padding=6)
        box.grid(row=row, column=0, columnspan=9, sticky="we", pady=(10, 0))
        for t in self.cfg["trackers"]:
            ot = t.get("on_target")
            if not ot:
                continue
            v = {"on": tk.BooleanVar(value=ot["enabled"]), "upgrade": tk.StringVar(value=ot["upgrade"]),
                 "status": tk.StringVar()}
            self.action_vars[t["name"]] = v
            f = ttk.Frame(box)
            f.pack(fill="x")
            ttk.Checkbutton(f, text=f"Armed: when {t['name']} reaches its target, open Upgrades and buy", variable=v["on"]).pack(side="left")
            ttk.Entry(f, textvariable=v["upgrade"], width=18).pack(side="left", padx=4)
            ttk.Button(f, text="Dry run", command=lambda n=t["name"]: self.start_action(n, dry_run=True)).pack(side="left", padx=2)
            ttk.Button(f, text="Re-arm", command=lambda n=t["name"]: self.rearm_action(n)).pack(side="left")
            ttk.Label(box, textvariable=v["status"]).pack(anchor="w")
            self._refresh_action_status(t["name"])

    def _refresh_action_status(self, name, note=""):
        t = next(x for x in self.cfg["trackers"] if x["name"] == name)
        ot, v = t["on_target"], self.action_vars[name]
        if ot["fired"]:
            state = f"DONE at {ot['fired_at']} (runs only once; click Re-arm to run again)"
        else:
            state = "armed, waiting for the target" if ot["enabled"] else "disarmed"
        v["status"].set(state + (f" — {note}" if note else ""))

    def rearm_action(self, name):
        t = next(x for x in self.cfg["trackers"] if x["name"] == name)
        t["on_target"].update(fired=False, fired_at="", enabled=True)
        self.action_vars[name]["on"].set(True)
        self.reach[name] = 0
        config.save(self.cfg)
        self._refresh_action_status(name, "re-armed")

    def start_action(self, name, dry_run=False):
        if self.busy:
            self.status.set("Busy; try again in a few seconds")
            return
        self._sync_cfg()
        self.busy = True
        threading.Thread(target=self._action_worker, args=(name, dry_run), daemon=True).start()

    def _action_worker(self, name, dry_run):
        try:
            t = next(x for x in self.cfg["trackers"] if x["name"] == name)
            self._close_popups(self.cfg["window_title"])
            self._ensure_screen(self.cfg["window_title"])
            ok, msg = run_buy(self.cfg["window_title"], self.cfg["tabs"], self.cfg.get("home_tab"),
                              t["on_target"]["upgrade"], grab, click_client, click_rect, dry_run=dry_run)
            self.q.put(("action", (name, ok, msg, dry_run)))
        except Exception as e:
            self.q.put(("action", (name, False, f"error: {e}", dry_run)))
        finally:
            self.q.put(("done", None))

    def _action_result(self, name, ok, msg, dry_run):
        t = next(x for x in self.cfg["trackers"] if x["name"] == name)
        ot = t["on_target"]
        self._log(f"Action ({name}): {msg}")
        if dry_run:
            return self._refresh_action_status(name, f"dry run: {msg}")
        if ok:
            ot.update(fired=True, fired_at=f"{datetime.now():%Y-%m-%d %H:%M:%S}")
            config.save(self.cfg)
            alert(f"{name} reached its target", msg)
            return self._refresh_action_status(name, msg)
        self.action_retry_at[name] = time.time() + 120  # do not hammer the game; retry in 2 min
        if "not found" in msg and "Buy button" not in msg:  # row gone: retrying cannot help, disarm
            ot["enabled"] = False
            self.action_vars[name]["on"].set(False)
            config.save(self.cfg)
            alert(f"{name}: action disarmed", msg)
        self._refresh_action_status(name, f"last attempt failed: {msg}")

    def _row(self, grid, r, t):
        v = {k: tk.StringVar(value="—") for k in ("cur", "gain", "eta", "fin")}
        v["target"] = tk.StringVar(value=t["target"])
        v["before"] = tk.StringVar(value=str(t["alert_before_min"]))
        v["on"] = tk.BooleanVar(value=t["enabled"])
        ttk.Checkbutton(grid, variable=v["on"]).grid(row=r, column=0)
        ttk.Label(grid, text=t["name"], width=9).grid(row=r, column=1, sticky="w")
        ttk.Label(grid, textvariable=v["cur"], width=16).grid(row=r, column=2, sticky="w")
        ttk.Label(grid, textvariable=v["gain"], width=14).grid(row=r, column=3, sticky="w")
        ttk.Entry(grid, textvariable=v["target"], width=10).grid(row=r, column=4, padx=4)
        ttk.Label(grid, textvariable=v["eta"], width=16).grid(row=r, column=5, sticky="w")
        ttk.Label(grid, textvariable=v["fin"], width=16).grid(row=r, column=6, sticky="w")
        ttk.Entry(grid, textvariable=v["before"], width=6).grid(row=r, column=7)
        bf = ttk.Frame(grid)
        bf.grid(row=r, column=8, padx=4)
        ttk.Button(bf, text="Current…", width=7, command=lambda: self.pick(t, "current")).pack(side="left")
        ttk.Button(bf, text="Gain…", width=7, command=lambda: self.pick(t, "gain")).pack(side="left", padx=2)
        ttk.Button(bf, text="Target…", width=6, command=lambda: self.pick(t, "target_region")).pack(side="left")
        ttk.Button(bf, text="+Add…", width=7, command=lambda: self.pick(t, "add")).pack(side="left", padx=2)
        self.rows[t["name"]] = v

    def pick(self, t, key):
        self._sync_cfg()
        try:
            img = grab(self.cfg["window_title"])
        except CaptureError as e:
            self.status.set(str(e))
            return
        regions = [x[k] for x in self.cfg["trackers"] for k in ("current", "gain", "target_region", "add") if x.get(k) and x[k] is not t.get(key)]
        r = pick_region(self.root, img, f"{t['name']} — {key}", regions)
        if r:
            if (t.get(key) or {}).get("tab"):
                r["tab"] = t[key]["tab"]
            t[key] = r
            config.save(self.cfg)
            self.status.set(f"Region '{key}' of {t['name']} saved.")

    def _sync_cfg(self):
        self.cfg["window_title"] = self.title_var.get()
        self.cfg["scan_tabs"] = self.scan_var.get()
        self.cfg["dragon_auto"] = self.dragon_var.get()
        self.cfg["auto_close_popups"] = self.popup_var.get()
        self.cfg["guild_routine"]["enabled"] = self.guild_on.get()
        self.cfg["guild_routine"]["time"] = self._guild_hhmm()
        for g in self.cfg["dragon_goals"]:
            v = self.dvars[g["name"]]
            g["on"] = v["on"].get()
            try:
                g["goal"] = max(0, int(v["goal"].get()))
            except ValueError:
                g["goal"] = 0
        try:
            self.cfg["scan_minutes"] = max(1.0, float(self.scan_min_var.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            self.cfg["interval"] = max(5, int(self.interval_var.get()))
        except (tk.TclError, ValueError):
            pass
        for t in self.cfg["trackers"]:
            if t.get("on_target") and t["name"] in self.action_vars:
                av = self.action_vars[t["name"]]
                t["on_target"]["enabled"] = av["on"].get()
                t["on_target"]["upgrade"] = av["upgrade"].get().strip() or t["on_target"]["upgrade"]
            v = self.rows[t["name"]]
            t["target"] = v["target"].get().strip()
            t["enabled"] = v["on"].get()
            try:
                t["alert_before_min"] = float(v["before"].get().replace(",", "."))
            except ValueError:
                t["alert_before_min"] = 0
        config.save(self.cfg)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S} {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ---------- cycle ----------
    def toggle(self):
        self.running = not self.running
        self.btn_run.config(text="⏸ Stop" if self.running else "▶ Start")
        if self.running:
            self._tick()

    def _tick(self):
        if not self.running:
            return
        self.run_cycle()
        self.root.after(self.cfg["interval"] * 1000, self._tick)

    def run_cycle(self, force_scan=False, only=None):
        if self.busy:
            return
        self._sync_cfg()
        self.busy = True
        threading.Thread(target=self._worker, args=(force_scan, only), daemon=True).start()

    def _needed_tabs(self):
        """Tabs referenced by the regions of enabled currencies; the 'home' tab goes last (the scan ends there)."""
        tabs = {r["tab"] for t in self.cfg["trackers"] if t["enabled"]
                for r in (t.get(k) for k in REGION_KEYS) if r and r.get("tab")}
        if self.cfg.get("dragon_auto"):
            tabs.add("dragons")
        home = self.cfg.get("home_tab")
        return sorted(tabs, key=lambda n: n == home)

    def _capture_tab(self, title, tab, attempts=4):
        """Waits for the UI to switch tabs: recaptures until every region of the tab parses as a number (or attempts run out)."""
        regions = [r for t in self.cfg["trackers"] if t["enabled"] for r in (t.get(k) for k in REGION_KEYS)
                   if r and r.get("tab") == tab]
        img = None
        for _ in range(attempts):
            time.sleep(1.0)
            img = grab(title)
            if all(parse_number(read_text(crop_region(img, r))) is not None for r in regions):
                break
        return img

    def _read_dragons(self, img):
        levels, buttons, timers = {}, {}, {}
        for name, d in self.cfg["dragons"].items():
            info = read_text(crop_region(img, d["info"]))
            levels[name], timers[name] = parse_level(info), parse_timer(info)
            buttons[name] = parse_button(read_text(crop_region(img, d["button"])))
        return levels, buttons, timers

    def _early_due(self, levels, buttons, timers):
        """Seconds until the training dragon finishes the level that reaches its goal (None = no early check)."""
        plan = build_plan(self.cfg["dragon_goals"])
        want = wanted_dragon(plan, levels)
        if want is not None and buttons.get(want) == "training" and timers.get(want) is not None \
                and levels[want] == dict(plan)[want] - 1:
            return timers[want] + DRAGON_MARGIN
        return None

    def _dragons(self, title, img):
        """Switches the training dragon according to the plan. When in doubt (unreadable level/button) it does not click."""
        note = lambda m: self.q.put(("note", m))
        plan = build_plan(self.cfg["dragon_goals"])
        if not plan or any(n not in self.cfg["dragons"] for n, _ in plan):
            return note("Dragons: set goals (Dragons tab) for dragons that have a configured region")
        for _ in range(3):
            levels, buttons, timers = self._read_dragons(img)
            if all(levels.get(n) is not None for n, _ in plan):
                break
            time.sleep(1.0)
            img = grab(title)
        self.q.put(("dragons", (levels, buttons, timers)))
        self.q.put(("dragon_due", self._early_due(levels, buttons, timers)))
        summary = ", ".join(f"{n} Lv{levels[n]} {buttons[n]}" for n in self.cfg["dragons"])
        want = wanted_dragon(plan, levels)
        if want is None:
            return note(f"Dragons: {summary} — nothing to switch")
        if buttons.get(want) == "training":
            return note(f"Dragons: {summary} — {want} is already training")
        if buttons.get(want) != "train":
            return note(f"Dragons: {summary} — {want} button unreadable, did not click")
        b = self.cfg["dragons"][want]["button"]
        if not click_client(title, b["x"] + b["w"] / 2, b["y"] + b["h"] / 2):
            return note(f"Dragons: game not visible, did not switch to {want}")
        time.sleep(1.0)
        levels, after, timers = self._read_dragons(grab(title))
        self.q.put(("dragons", (levels, after, timers)))
        self.q.put(("dragon_due", self._early_due(levels, after, timers)))
        note(f"Dragons: switched to {want} (now: {after.get(want)}). {summary}")

    def _worker(self, force_scan=False, only=None):
        try:
            title = self.cfg["window_title"]
            self._close_popups(title)
            self._ensure_screen(title)
            imgs = {None: grab(title)}
            scan = self.cfg.get("scan_tabs", False)
            due = force_scan or time.time() - self.last_scan >= self.cfg.get("scan_minutes", 5) * 60
            if only and scan:  # early check of specific tabs; trackers are not updated
                for name in only:
                    pos = self.cfg["tabs"][name]
                    if not click_client(title, pos["x"], pos["y"]):
                        self.q.put(("note", f"Early check aborted at tab '{name}': game is not visible on the active desktop"))
                        break
                    imgs[name] = self._capture_tab(title, name)
                    if name == "dragons":
                        self._dragons(title, imgs[name])
                home = self.cfg["tabs"].get(self.cfg.get("home_tab"))
                if home:
                    click_client(title, home["x"], home["y"])
                self.q.put(("done", None))
                return
            if scan and due:
                self.last_scan = time.time()
                for name in self._needed_tabs():
                    pos = self.cfg["tabs"][name]
                    if not click_client(title, pos["x"], pos["y"]):
                        self.q.put(("note", f"Scan aborted at tab '{name}': game is not visible on the active desktop"))
                        break
                    imgs[name] = self._capture_tab(title, name)
                    if name == "dragons":
                        self._dragons(title, imgs[name])
            now = time.time()
            for t in self.cfg["trackers"]:
                if t["enabled"] and t["current"]:
                    self.q.put(("result", self._read_tracker(imgs, scan, t, now)))
            self.q.put(("done", None))
        except Exception as e:  # CaptureError, OCR, etc.
            self.q.put(("error", str(e)))

    def _ensure_screen(self, title):
        """Opens the Hourglass screen when it is closed (base screen -> Menu -> Hourglass of Eternity), then goes to the home tab."""
        if not self.cfg.get("auto_open_screen", True):
            return
        res = ensure_hourglass_open(title, grab, click_client, log=lambda m: self.q.put(("note", m)))
        if res == "opened":
            self.q.put(("note", "Hourglass screen was closed: opened it"))
            home = self.cfg["tabs"].get(self.cfg.get("home_tab"))
            if home:
                click_client(title, home["x"], home["y"])
                time.sleep(1.0)

    def _close_popups(self, title):
        """Closes 'Touch anywhere to close' popups (e.g. the 4 AM daily reward) that would block every click."""
        if not self.cfg.get("auto_close_popups", True):
            return
        log = lambda m: self.q.put(("note", m))
        n = dismiss_popups(title, grab, click_client, log=log)
        if n:
            log(f"Closed {n} popup(s) covering the game")

    @staticmethod
    def _gain_plausible(mem, gain):
        """Accepts a gain that is within 100x of the last one; a bigger jump (likely an OCR misread) is only
        accepted once it shows up twice in a row (a real change, e.g. after a timeline reset)."""
        last = mem.get("gain")
        if not last or 0.01 <= gain / last <= 100:
            mem.pop("gain_pending", None)
            return True
        pending = mem.get("gain_pending")
        if pending and 0.95 <= gain / pending <= 1.05:
            mem.pop("gain_pending", None)
            return True
        mem["gain_pending"] = gain
        return False

    def _read_tracker(self, imgs, scan, t, now):
        def read(region):
            """Text of the region in its own tab's image. With scanning on and the tab not captured, it does not read."""
            img = imgs.get(region.get("tab")) if scan else imgs[None]
            return read_text(crop_region(img, region)) if img is not None else ""

        res = {"name": t["name"], "raw_cur": "", "raw_gain": "", "cur": None, "gain": None, "target": None,
               "gain_src": ""}
        res["raw_cur"] = read(t["current"])
        nums = find_numbers(res["raw_cur"])
        res["cur"] = nums[0] if nums else None
        if t.get("add") and res["cur"] is not None:  # extra value added to the current one (e.g. Infinity stock)
            res["raw_add"] = read(t["add"])
            extra = parse_number(res["raw_add"])
            # a missing part would give a wrong partial sum: treat the whole value as unread
            res["cur"] = res["cur"] + extra if extra is not None else None
        mem = self.last.setdefault(t["name"], {})  # last valid value (the tab may not be visible right now)
        if t["target"]:
            res["target"] = parse_number(t["target"])
        else:
            if t.get("target_region"):
                res["raw_target"] = read(t["target_region"])
                res["target"] = parse_number(res["raw_target"])
            elif len(nums) > 1:
                res["target"] = nums[1]
            if res["target"] is not None:
                mem["target"] = res["target"]
            else:
                res["target"] = mem.get("target")
        if t["gain"]:
            res["raw_gain"] = read(t["gain"])
            res["gain"] = parse_rate(res["raw_gain"], t["gain_unit"])
            res["gain_src"] = "read"
            if res["gain"] and self._gain_plausible(mem, res["gain"]):
                mem["gain"] = res["gain"]
            elif mem.get("gain"):
                res["gain"], res["gain_src"] = mem["gain"], "memory"
        if res["cur"] is not None:
            mem["cur"] = (res["cur"], now)
        elif scan and mem.get("cur") and res["gain"]:  # outside a scan: last read + gain * elapsed time
            v0, t0 = mem["cur"]
            res["cur"], res["cur_src"] = v0 + res["gain"] * (now - t0), "extrapolated"
        hist = self.history.setdefault(t["name"], deque())
        if res["cur"] is not None and res.get("cur_src") != "extrapolated":
            hist.append((now, res["cur"]))
            while hist and now - hist[0][0] > HIST_SECONDS:
                hist.popleft()
        if res["gain"] is None and len(hist) >= 2 and hist[-1][0] > hist[0][0]:
            g = (hist[-1][1] - hist[0][1]) / (hist[-1][0] - hist[0][0])
            if g > 0:
                res["gain"], res["gain_src"] = g, "estimated"
        return res

    def _schedule_dragon_check(self, seconds):
        """Early dragon check right when the level-up timer ends (instead of waiting for the next scan)."""
        if self._dragon_after is not None:
            self.root.after_cancel(self._dragon_after)
            self._dragon_after = None
        if seconds is None:
            self.dragon_next.set("")
            return
        self.dragon_next.set(f"Early check scheduled for {datetime.now() + timedelta(seconds=seconds):%H:%M:%S}")
        self._dragon_after = self.root.after(int(seconds * 1000), self._dragon_check)
        self._log(f"Dragons: early check scheduled in {fmt_duration(seconds)} (goal level is next)")

    def _dragon_check(self):
        self._dragon_after = None
        self.dragon_next.set("")
        if not (self.cfg.get("scan_tabs") and self.cfg.get("dragon_auto")):
            return
        if self.busy:  # another cycle is in progress; try again shortly
            self._dragon_after = self.root.after(3000, self._dragon_check)
            return
        self.run_cycle(only=("dragons",))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "result":
                    self._apply(data)
                elif kind == "dragons":
                    self._show_dragons(*data)
                elif kind == "action":
                    self._action_result(*data)
                elif kind == "guild":
                    self._guild_result(*data)
                elif kind == "dragon_due":
                    self._schedule_dragon_check(data)
                elif kind == "note":
                    self.status.set(data)
                    self._log(data)
                elif kind == "error":
                    self.busy = False
                    self.status.set(f"Error: {data}")
                else:
                    self.busy = False
                    self.status.set(f"Last read: {datetime.now():%H:%M:%S}")
        except queue.Empty:
            pass
        if self.pending_action and not self.busy:  # run the one-shot action once the cycle is idle
            name, self.pending_action = self.pending_action, None
            self.start_action(name)
        self.root.after(200, self._poll)

    def _check_trigger(self, t, reached):
        """Queues the one-shot action after 2 consecutive readings at/above the target (guards against OCR glitches)."""
        ot, name = t.get("on_target"), t["name"]
        if not ot or not ot["enabled"] or ot["fired"] or not reached:
            self.reach[name] = 0
            return
        self.reach[name] = self.reach.get(name, 0) + 1
        if self.reach[name] >= 2 and time.time() >= self.action_retry_at.get(name, 0):
            self.pending_action = name

    def _apply(self, r):
        v = self.rows[r["name"]]
        t = next(x for x in self.cfg["trackers"] if x["name"] == r["name"])
        self._log(f"{r['name']}: current='{r['raw_cur']}' gain='{r['raw_gain']}'")
        v["cur"].set(fmt_num(r["cur"]) + (" (extrap.)" if r.get("cur_src") == "extrapolated" else ""))
        v["gain"].set(fmt_num(r["gain"]) + ({"estimated": " (est.)", "memory": " (mem.)"}.get(r["gain_src"], "")))
        if r["cur"] is None or r["target"] is None:
            v["eta"].set("no target/reading")
            v["fin"].set("—")
            return
        eta = eta_seconds(r["cur"], r["target"], r["gain"])
        self._check_trigger(t, eta == 0)
        v["eta"].set("done" if eta == 0 else fmt_duration(eta))
        v["fin"].set("—" if eta is None or eta > MAX_ETA else (datetime.now() + timedelta(seconds=eta)).strftime("%b %d %H:%M"))
        limit = t["alert_before_min"] * 60
        if eta is not None and eta <= limit:
            if not self.alerted.get(r["name"]):
                self.alerted[r["name"]] = True
                msg = "Done!" if eta == 0 else f"{fmt_duration(eta)} remaining"
                alert(f"{r['name']} — Hourglass Timer", msg)
        else:
            self.alerted[r["name"]] = False

    def _close(self):
        self._sync_cfg()
        self.root.destroy()

import time

import win32api
import win32con
import win32gui

from .capture import find_window

GA_ROOT = 2
LAST_BLOCK = ""  # why the last click_client refused to click (for messages)


def _screen_point(title: str, fx: float, fy: float):
    """Screen coordinates of a client-area point (fractions 0-1), or None (and LAST_BLOCK says why) when the game
    is not there to receive real input: minimized, covered or on another desktop."""
    global LAST_BLOCK
    LAST_BLOCK = ""
    if not title.strip():
        LAST_BLOCK = "no window title configured"
        return None
    h = find_window(title)
    if not h or win32gui.IsIconic(h):
        LAST_BLOCK = "window not found or minimized"
        return None
    _, _, w, ht = win32gui.GetClientRect(h)
    sx, sy = win32gui.ClientToScreen(h, (int(fx * w), int(fy * ht)))
    hit = win32gui.WindowFromPoint((sx, sy))
    if not hit or win32gui.GetAncestor(hit, GA_ROOT) != h:  # covered, minimized or on another desktop
        top = win32gui.GetAncestor(hit, GA_ROOT) if hit else 0
        LAST_BLOCK = f"covered by '{win32gui.GetWindowText(top) or win32gui.GetClassName(top)}'" if top else "no window at the point"
        return None
    return sx, sy


def click_client(title: str, fx: float, fy: float) -> bool:
    """Real mouse click at a point of the client area (fractions 0-1). Unity ignores clicks sent
    as messages, so this only works with the game visible on the active desktop; otherwise it does not click."""
    pt = _screen_point(title, fx, fy)
    if pt is None:
        return False
    old = win32api.GetCursorPos()
    try:
        win32api.SetCursorPos(pt)
        time.sleep(0.15)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)
    finally:
        win32api.SetCursorPos(old)
    return True


def _drag(pt_from, pt_to, steps=12):
    """Real mouse drag between two screen points (press, move in steps, release); restores the cursor."""
    old = win32api.GetCursorPos()
    try:
        win32api.SetCursorPos(pt_from)
        time.sleep(0.2)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.15)
        for i in range(1, steps + 1):
            win32api.SetCursorPos((pt_from[0] + (pt_to[0] - pt_from[0]) * i // steps,
                                   pt_from[1] + (pt_to[1] - pt_from[1]) * i // steps))
            time.sleep(0.03)
        time.sleep(0.25)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.3)
    finally:
        win32api.SetCursorPos(old)


NOTCH = 0.1  # fraction of the window height a list moves per scroll notch
DRAG_TOP, DRAG_BOTTOM = 0.28, 0.80  # vertical band (fractions) where a scroll drag starts and ends: inside the lists


def scroll_client(title: str, fx: float, notches: int) -> bool:
    """Scrolls a list of the game at fx by DRAGGING it, like touch scrolling: Unity ignores the mouse wheel here.
    notches > 0 scrolls towards the top of the list, < 0 towards the end; one notch ~ NOTCH of the window height.
    The drag starts on the list body (not on a button), so it is not taken as a click. Same visibility rules as click_client."""
    remaining = abs(notches) * NOTCH
    while remaining > 1e-6:
        d = min(remaining, 0.45)
        a, b = (DRAG_TOP, DRAG_TOP + d) if notches > 0 else (DRAG_BOTTOM, DRAG_BOTTOM - d)
        p_from, p_to = _screen_point(title, fx, a), _screen_point(title, fx, b)
        if p_from is None or p_to is None:
            return False
        _drag(p_from, p_to)
        remaining -= d
    return True


def click_rect(title: str, image_size: tuple[int, int], rect: tuple[int, int, int, int]) -> bool:
    """Clicks the center of a pixel rect (x0, y0, x1, y1) of a captured client-area image."""
    w, h = image_size
    return click_client(title, (rect[0] + rect[2]) / 2 / w, (rect[1] + rect[3]) / 2 / h)

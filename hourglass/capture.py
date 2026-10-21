import ctypes

import mss
import win32gui
import win32ui
from PIL import Image, ImageStat

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class CaptureError(Exception):
    pass


def find_window(substr: str):
    found = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and substr.lower() in win32gui.GetWindowText(h).lower():
            found.append(h)

    win32gui.EnumWindows(cb, None)
    # a Discord/browser window about the game can match the title too: prefer the Unity window
    unity = [h for h in found if win32gui.GetClassName(h) == "UnityWndClass"]
    return (unity or found or [None])[0]


def _print_window(h, w, ht) -> Image.Image:
    """Captures the window straight from the DWM: works when covered and on another virtual desktop."""
    hdc = win32gui.GetWindowDC(h)
    dc = win32ui.CreateDCFromHandle(hdc)
    mdc = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(dc, w, ht)
        mdc.SelectObject(bmp)
        ctypes.windll.user32.PrintWindow(h, mdc.GetSafeHdc(), 3)  # CLIENTONLY | RENDERFULLCONTENT
        info = bmp.GetInfo()
        return Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mdc.DeleteDC()
        dc.DeleteDC()
        win32gui.ReleaseDC(h, hdc)


def grab(title: str) -> Image.Image:
    """Captures the window by title (even in the background or on another desktop; not minimized).
    No title = primary monitor."""
    with mss.mss() as sct:
        if not title.strip():
            shot = sct.grab(sct.monitors[1])
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    h = find_window(title)
    if not h:
        raise CaptureError(f"Window '{title}' not found")
    if win32gui.IsIconic(h):
        raise CaptureError("Window is minimized (keep it open, in the background or on another desktop)")
    _, _, w, ht = win32gui.GetClientRect(h)
    img = _print_window(h, w, ht)
    if ImageStat.Stat(img).extrema[0][1] < 5:  # black frame: the game did not render
        raise CaptureError("Window capture came back black (the game is not rendering)")
    return img


def crop_region(img: Image.Image, r: dict) -> Image.Image:
    """Region as fractions (0-1) of the image — robust to window resizing."""
    W, H = img.size
    return img.crop((int(r["x"] * W), int(r["y"] * H), int((r["x"] + r["w"]) * W), int((r["y"] + r["h"]) * H)))

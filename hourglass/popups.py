"""Closes full-screen 'Touch anywhere to close' popups (e.g. the daily reward at 4 AM) that block every click."""
import time

from PIL import Image

from .ocr import read_words


def find_popup(img: Image.Image) -> tuple[float, float] | None:
    """Center (fractions of the image) of the 'Touch anywhere to close' text, or None if no popup is shown."""
    top = int(img.height * 0.50)
    band = img.crop((0, top, img.width, int(img.height * 0.92)))
    for w in read_words(band, scale=2):
        if "anywhere" in w["text"].lower():
            return (w["x"] + w["w"] / 2) / img.width, (top + w["y"] + w["h"] / 2) / img.height
    return None


def dismiss(title, grab, click_client, rounds=3, log=print) -> int:
    """Clicks on the popup until it is gone (several rewards can chain). Returns how many were closed."""
    closed = 0
    for _ in range(rounds):
        pos = find_popup(grab(title))
        if pos is None:
            break
        if not click_client(title, *pos):
            log("popup detected but the game is not clickable")
            break
        closed += 1
        time.sleep(1.2)
    return closed

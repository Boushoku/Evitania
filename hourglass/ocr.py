"""OCR via Windows.Media.Ocr (built into Windows 10/11, nothing to install)."""
import asyncio
import io
from collections import Counter

from PIL import Image, ImageOps
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream


def _prepare(img: Image.Image, scale: int) -> Image.Image:
    g = ImageOps.autocontrast(img.convert("L"))
    g = g.resize((g.width * scale, g.height * scale), Image.LANCZOS)
    if sum(g.getdata()) / (g.width * g.height) < 128:  # dark background -> dark text on a light background
        g = ImageOps.invert(g)
    return ImageOps.expand(g, border=12, fill=255)


async def _recognize(png: bytes) -> str:
    engine = OcrEngine.try_create_from_user_profile_languages()
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    return result.text


def _binarized(img: Image.Image, scale: int, threshold: int) -> Image.Image:
    """Hard black-on-white version; helps with low-contrast text (e.g. light purple on purple)."""
    g = ImageOps.autocontrast(img.convert("L"))
    light_text = sum(g.getdata()) / (g.width * g.height) < 128
    g = g.resize((g.width * scale, g.height * scale), Image.LANCZOS)
    g = g.point(lambda p: 0 if (p > threshold) == light_text else 255)
    return ImageOps.expand(g, border=14, fill=255)


def _ocr(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return asyncio.run(_recognize(buf.getvalue())).strip()


def read_text(img: Image.Image, scales=(2, 3, 4)) -> str:
    """OCR is scale-sensitive: reads at several scales and votes for the most frequent NON-empty result
    (tie: the longest). If every scale comes back empty, retries with binarized variants."""
    results = [t for t in (_ocr(_prepare(img, sc)) for sc in scales) if t]
    if not results:
        for sc, th in ((4, 110), (4, 150), (5, 110), (5, 150)):
            t = _ocr(_binarized(img, sc, th))
            if t:
                results.append(t)
                break
    if not results:
        return ""
    counts = Counter(results)
    return max(counts, key=lambda t: (counts[t], len(t)))


async def _recognize_words(png: bytes) -> list[tuple[str, float, float, float, float]]:
    engine = OcrEngine.try_create_from_user_profile_languages()
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    words = []
    for line in result.lines:
        for w in line.words:
            r = w.bounding_rect
            words.append((w.text, r.x, r.y, r.width, r.height))
    return words


def read_words(img: Image.Image, scale: int = 2) -> list[dict]:
    """OCR with positions: [{'text', 'x', 'y', 'w', 'h'}] in the ORIGINAL image's pixel coordinates."""
    prepared = _prepare(img, scale)
    buf = io.BytesIO()
    prepared.save(buf, "PNG")
    out = []
    for text, x, y, w, h in asyncio.run(_recognize_words(buf.getvalue())):
        out.append({"text": text, "x": (x - 12) / scale, "y": (y - 12) / scale, "w": w / scale, "h": h / scale})
    return out

import tkinter as tk

from PIL import ImageTk


def pick_region(parent, img, title, existing=()):
    """Shows the screenshot and lets you drag a rectangle. Returns a fraction {x,y,w,h} or None."""
    scale = min(1.0, (parent.winfo_screenwidth() - 100) / img.width, (parent.winfo_screenheight() - 160) / img.height)
    shown = img.resize((int(img.width * scale), int(img.height * scale)))
    top = tk.Toplevel(parent)
    top.title(title)
    top.transient(parent)
    tk.Label(top, text=title + " — drag a rectangle over the value (ESC cancels)").pack()
    cv = tk.Canvas(top, width=shown.width, height=shown.height, cursor="crosshair", highlightthickness=0)
    cv.pack()
    photo = ImageTk.PhotoImage(shown)
    cv.create_image(0, 0, image=photo, anchor="nw")
    for r in existing:
        if r:
            cv.create_rectangle(r["x"] * shown.width, r["y"] * shown.height, (r["x"] + r["w"]) * shown.width,
                                (r["y"] + r["h"]) * shown.height, outline="#888", dash=(3, 3))
    state = {"start": None, "rect": None, "result": None}

    def press(e):
        state["start"] = (e.x, e.y)
        state["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def drag(e):
        cv.coords(state["rect"], *state["start"], e.x, e.y)

    def release(e):
        x0, y0 = state["start"]
        x0, x1 = sorted((x0, e.x))
        y0, y1 = sorted((y0, e.y))
        if x1 - x0 > 3 and y1 - y0 > 3:
            W, H = shown.size
            state["result"] = {"x": x0 / W, "y": y0 / H, "w": (x1 - x0) / W, "h": (y1 - y0) / H}
            top.destroy()

    cv.bind("<ButtonPress-1>", press)
    cv.bind("<B1-Motion>", drag)
    cv.bind("<ButtonRelease-1>", release)
    top.bind("<Escape>", lambda e: top.destroy())
    top.grab_set()
    parent.wait_window(top)
    return state["result"]

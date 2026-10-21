import threading
import winsound

from winotify import Notification, audio


def alert(title: str, msg: str) -> None:
    try:
        Notification(app_id="HourglassTimer", title=title, msg=msg, duration="long").set_audio(audio.Reminder, loop=False).show()
    except Exception:
        pass

    def beep():
        for _ in range(3):
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)

    threading.Thread(target=beep, daemon=True).start()

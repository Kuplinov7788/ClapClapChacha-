import sys
import os
import random
import threading
import time
import ctypes
from pathlib import Path

import numpy as np

# Windows MCI API
winmm = ctypes.windll.winmm

def mci_send(command):
    buf = ctypes.create_unicode_buffer(256)
    err = winmm.mciSendStringW(command, buf, 256, 0)
    return buf.value, err
import sounddevice as sd
from PIL import Image, ImageDraw, ImageFont
import pystray

# --- Paths ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

SOUNDS_DIR = BASE_DIR / "sounds"


class SlapDetector:
    """Mikrofon orqali slap/chapak ovozini aniqlaydi."""

    def __init__(self, on_slap):
        self.on_slap = on_slap
        self.sensitivity = 0.5
        self.running = False
        self._stream = None
        self._last_slap = 0

    def start(self):
        if self.running:
            return
        self.running = True
        try:
            self._stream = sd.InputStream(
                samplerate=44100,
                channels=1,
                blocksize=1024,
                callback=self._audio_callback,
            )
            self._stream.start()
            print("SlapDetector ishga tushdi")
        except Exception as e:
            print(f"Mikrofon ochilmadi: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        print("SlapDetector to'xtadi")

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.running:
            return
        peak = np.max(np.abs(indata))
        threshold = 1.0 - (self.sensitivity * 0.9)
        now = time.time()
        if peak > threshold and (now - self._last_slap) > 0.5:
            self._last_slap = now
            print(f"Slap! peak={peak:.3f} > threshold={threshold:.3f}")
            self.on_slap()


class SoundPlayer:
    """Random ovoz faylini o'ynatadi (Windows MCI API orqali)."""

    def __init__(self):
        self._playing = False
        self._sounds = []
        self._load_sounds()

    def _load_sounds(self):
        if not SOUNDS_DIR.exists():
            return
        for ext in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
            self._sounds.extend(SOUNDS_DIR.glob(ext))

    def play_random(self):
        if self._playing or not self._sounds:
            return
        path = random.choice(self._sounds)
        self._playing = True
        threading.Thread(target=self._play_file, args=(path,), daemon=True).start()

    def _play_file(self, path):
        try:
            alias = "slapwin_sound"
            mci_send(f'close {alias}')
            mci_send(f'open "{path}" alias {alias}')
            # Ovoz uzunligini olish
            length_str, _ = mci_send(f'status {alias} length')
            mci_send(f'play {alias}')
            # Ovoz tugashini kutish
            if length_str:
                duration_ms = int(length_str)
                time.sleep(duration_ms / 1000.0 + 0.3)
            else:
                time.sleep(5)
            mci_send(f'close {alias}')
        except Exception as e:
            print(f"Ovoz xatosi: {e}")
        finally:
            self._playing = False


class SlapWinApp:
    """Asosiy dastur - system tray bilan ishlaydi."""

    def __init__(self):
        self.slap_count = 0
        self.active = True
        self.sound_player = SoundPlayer()
        self.detector = SlapDetector(on_slap=self._on_slap)
        self.icon = None
        self._sensitivity_window = None

    def _make_icon(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (76, 175, 80, 255) if self.active else (158, 158, 158, 255)
        draw.ellipse([2, 2, 62, 62], fill=color)
        text = str(self.slap_count)
        try:
            font = ImageFont.truetype("arial.ttf", 28 if len(text) < 3 else 20)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((64 - tw) / 2, (64 - th) / 2 - 4), text, fill="white", font=font)
        return img

    def _update_icon(self):
        if self.icon:
            self.icon.icon = self._make_icon()
            status = "ON" if self.active else "OFF"
            self.icon.title = f"SlapWin [{status}] - {self.slap_count} slaps"

    def _on_slap(self):
        if not self.active:
            return
        self.slap_count += 1
        self.sound_player.play_random()
        self._update_icon()

    def _toggle(self, icon, item):
        self.active = not self.active
        if self.active:
            self.detector.start()
        else:
            self.detector.stop()
        self._update_icon()

    def _reset_count(self, icon, item):
        self.slap_count = 0
        self._update_icon()

    def _open_sensitivity(self, icon, item):
        threading.Thread(target=self._show_sensitivity_window, daemon=True).start()

    def _show_sensitivity_window(self):
        import tkinter as tk

        if self._sensitivity_window is not None:
            return

        win = tk.Tk()
        self._sensitivity_window = win
        win.title("SlapWin - Sozlamalar")
        win.geometry("320x150")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        tk.Label(win, text="Sezgirlik (Sensitivity)", font=("Segoe UI", 11)).pack(pady=(15, 5))

        label_val = tk.Label(win, text=f"{self.detector.sensitivity:.2f}", font=("Segoe UI", 10))
        label_val.pack()

        def on_change(val):
            v = float(val)
            self.detector.sensitivity = v
            label_val.config(text=f"{v:.2f}")

        slider = tk.Scale(
            win, from_=0.1, to=1.0, resolution=0.05,
            orient=tk.HORIZONTAL, length=250,
            command=on_change, showvalue=False
        )
        slider.set(self.detector.sensitivity)
        slider.pack(pady=5)

        def on_close():
            self._sensitivity_window = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)
        win.mainloop()

    def _quit(self, icon, item):
        self.detector.stop()
        icon.stop()

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: "Yoqilgan (ON)" if self.active else "O'chirilgan (OFF)",
                self._toggle,
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sozlamalar...", self._open_sensitivity),
            pystray.MenuItem("Countni nollash", self._reset_count),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Chiqish", self._quit),
        )

        self.icon = pystray.Icon(
            "SlapWin",
            icon=self._make_icon(),
            title="SlapWin [ON] - 0 slaps",
            menu=menu,
        )

        self.detector.start()
        self.icon.run()


if __name__ == "__main__":
    app = SlapWinApp()
    app.run()

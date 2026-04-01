import sys
import os
import random
import shutil
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
    """Mikrofon orqali slap/chapak ovozini aniqlaydi va sonini sanaydi."""

    CLAP_WAIT = 1.2  # Keyingi chapakni kutish vaqti (soniya)
    CLAP_GAP = 0.3   # Chapaklar orasidagi minimal vaqt

    def __init__(self, on_slap):
        self.on_slap = on_slap  # on_slap(clap_count) — chapak sonini yuboradi
        self.sensitivity = 0.5
        self.running = False
        self._stream = None
        self._last_clap = 0
        self._clap_count = 0
        self._timer = None
        self._lock = threading.Lock()

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
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._clap_count = 0
        print("SlapDetector to'xtadi")

    def _fire_claps(self):
        """Kutish tugadi — yig'ilgan chapak sonini yuboradi."""
        with self._lock:
            count = self._clap_count
            self._clap_count = 0
            self._timer = None
        if count > 0:
            print(f"=== NATIJA: {count} chapak ===")
            self.on_slap(count)

    def set_muted(self, muted):
        """Ovoz o'ynayotganda mikni o'chirish."""
        self._muted = muted

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.running or getattr(self, '_muted', False):
            return
        peak = np.max(np.abs(indata))
        threshold = 1.0 - (self.sensitivity * 0.9)
        now = time.time()
        if peak > threshold and (now - self._last_clap) > self.CLAP_GAP:
            self._last_clap = now
            with self._lock:
                self._clap_count += 1
                count = self._clap_count
                # Oldingi timerni bekor qilish
                if self._timer:
                    self._timer.cancel()
                # Yangi timer — yana chapak kelishini kutish
                self._timer = threading.Timer(self.CLAP_WAIT, self._fire_claps)
                self._timer.daemon = True
                self._timer.start()
            print(f"Clap! #{count}  peak={peak:.3f}")


class SoundPlayer:
    """Random ovoz faylini o'ynatadi (Windows MCI API orqali)."""

    def __init__(self):
        self._playing = False
        self._sounds = []
        self._load_sounds()

    def _load_sounds(self):
        self._sounds.clear()
        if not SOUNDS_DIR.exists():
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            return
        for ext in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
            self._sounds.extend(SOUNDS_DIR.glob(ext))

    def reload(self):
        self._load_sounds()

    def _get_special(self, keyword):
        """Nomi ichida keyword bo'lgan faylni topadi."""
        for s in self._sounds:
            if keyword.lower() in s.stem.lower():
                return s
        return None

    def _get_random_normal(self):
        """myinstants va dyayda'dan boshqa random ovoz."""
        special = {"myinstants", "dyayda"}
        normal = [s for s in self._sounds if s.stem.lower() not in special]
        return random.choice(normal) if normal else None

    def _stop_current(self):
        """Hozir o'ynayotgan ovozni to'xtatadi."""
        try:
            mci_send('close slapwin_sound')
        except Exception:
            pass
        self._playing = False

    def play_by_clap_count(self, count):
        """Chapak soniga qarab tegishli ovozni o'ynatadi."""
        if not self._sounds:
            return
        # Oldingi ovoz o'ynayotgan bo'lsa to'xtatamiz
        if self._playing:
            self._stop_current()

        if count == 2:
            path = self._get_special("dyayda")
            print(f"  -> 2 chapak: dyayda -> {path}")
        elif count >= 3:
            path = self._get_special("myinstants")
            print(f"  -> 3+ chapak: myinstants -> {path}")
        else:
            path = self._get_random_normal()
            print(f"  -> 1 chapak: random -> {path}")

        if not path:
            path = random.choice(self._sounds)
            print(f"  -> fallback: {path}")

        self._playing = True
        threading.Thread(target=self._play_file, args=(path,), daemon=True).start()

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
            length_str, _ = mci_send(f'status {alias} length')
            mci_send(f'play {alias}')
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
            # Ovoz tugagandan keyin mic yana eshitmasligi uchun kichik pauza
            time.sleep(0.3)


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

    def _on_slap(self, clap_count=1):
        if not self.active:
            return
        self.slap_count += clap_count
        # Ovoz o'ynash vaqtida mikni o'chiramiz (feedback loop oldini olish)
        self.detector.set_muted(True)
        self.sound_player.play_by_clap_count(clap_count)
        self._update_icon()
        # Ovoz tugagandan keyin mikni yoqamiz
        threading.Thread(target=self._unmute_after_play, daemon=True).start()

    def _unmute_after_play(self):
        """Ovoz tugashini kutib, mikni qayta yoqadi."""
        while self.sound_player._playing:
            time.sleep(0.1)
        time.sleep(0.5)
        self.detector.set_muted(False)
        print("Mic yoqildi")

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

    def _open_sounds(self, icon, item):
        threading.Thread(target=self._show_sounds_window, daemon=True).start()

    def _add_sound_files(self, file_paths):
        """Ovoz fayllarini sounds/ papkasiga nusxalaydi."""
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        valid_ext = {'.mp3', '.wav', '.ogg', '.m4a'}
        added = 0
        for fp in file_paths:
            p = Path(fp.strip().strip('{}'))
            if p.is_file() and p.suffix.lower() in valid_ext:
                dest = SOUNDS_DIR / p.name
                if not dest.exists():
                    shutil.copy2(str(p), str(dest))
                    added += 1
        if added > 0:
            self.sound_player.reload()
        return added

    def _show_sounds_window(self):
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
            win = TkinterDnD.Tk()
            has_dnd = True
        except ImportError:
            import tkinter as tk
            win = tk.Tk()
            has_dnd = False

        import tkinter as tk
        from tkinter import filedialog

        win.title("SlapWin - Ovozlar")
        win.geometry("420x380")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#1e1e2e")

        # Status label
        status_var = tk.StringVar(value="")

        # Header
        tk.Label(
            win, text="Ovozlarni boshqarish",
            font=("Segoe UI", 14, "bold"), fg="#cdd6f4", bg="#1e1e2e"
        ).pack(pady=(15, 5))

        # Ovozlar ro'yxati
        list_frame = tk.Frame(win, bg="#1e1e2e")
        list_frame.pack(fill=tk.BOTH, padx=20, pady=(5, 5), expand=True)

        listbox = tk.Listbox(
            list_frame, font=("Segoe UI", 10),
            bg="#313244", fg="#cdd6f4", selectbackground="#585b70",
            borderwidth=0, highlightthickness=0, height=6
        )
        scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
        listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def refresh_list():
            listbox.delete(0, tk.END)
            self.sound_player.reload()
            for s in sorted(self.sound_player._sounds, key=lambda x: x.name):
                listbox.insert(tk.END, f"  {s.name}")

        refresh_list()

        # O'chirish tugmasi
        def delete_selected():
            sel = listbox.curselection()
            if not sel:
                return
            name = listbox.get(sel[0]).strip()
            path = SOUNDS_DIR / name
            if path.exists():
                path.unlink()
                self.sound_player.reload()
                refresh_list()
                status_var.set(f"O'chirildi: {name}")

        # Fayldan tanlash
        def pick_files():
            files = filedialog.askopenfilenames(
                title="Ovoz fayllarini tanlang",
                filetypes=[("Audio", "*.mp3 *.wav *.ogg *.m4a"), ("Barcha fayllar", "*.*")],
                parent=win,
            )
            if files:
                added = self._add_sound_files(files)
                refresh_list()
                status_var.set(f"{added} ta ovoz qo'shildi!")

        # Drop zone
        drop_frame = tk.Frame(win, bg="#45475a", bd=0, highlightthickness=2, highlightbackground="#585b70")
        drop_frame.pack(padx=20, pady=(5, 5), fill=tk.X, ipady=15)

        drop_label = tk.Label(
            drop_frame,
            text="Ovoz fayllarini shu yerga tashlang\n(drag & drop)",
            font=("Segoe UI", 10), fg="#a6adc8", bg="#45475a",
            justify=tk.CENTER,
        )
        drop_label.pack(expand=True)

        if has_dnd:
            def on_drop(event):
                files = win.tk.splitlist(event.data)
                added = self._add_sound_files(files)
                refresh_list()
                status_var.set(f"{added} ta ovoz qo'shildi!")
                drop_label.config(fg="#a6e3a1")
                win.after(1500, lambda: drop_label.config(fg="#a6adc8"))

            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind('<<Drop>>', on_drop)
            drop_label.drop_target_register(DND_FILES)
            drop_label.dnd_bind('<<Drop>>', on_drop)

        # Tugmalar
        btn_frame = tk.Frame(win, bg="#1e1e2e")
        btn_frame.pack(pady=(5, 5), fill=tk.X, padx=20)

        btn_style = dict(
            font=("Segoe UI", 10), bg="#585b70", fg="#cdd6f4",
            activebackground="#6c7086", activeforeground="#cdd6f4",
            borderwidth=0, padx=12, pady=4, cursor="hand2",
        )

        tk.Button(btn_frame, text="Fayldan tanlash", command=pick_files, **btn_style).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="O'chirish", command=delete_selected, **btn_style).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="Papkani ochish",
                  command=lambda: os.startfile(str(SOUNDS_DIR)), **btn_style).pack(side=tk.RIGHT)

        # Status
        tk.Label(win, textvariable=status_var, font=("Segoe UI", 9),
                 fg="#a6e3a1", bg="#1e1e2e").pack(pady=(0, 10))

        win.mainloop()

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
            pystray.MenuItem("Ovozlar...", self._open_sounds),
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

        def on_setup(icon):
            icon.visible = True
            self.detector.start()

        self.icon.run(setup=on_setup)


if __name__ == "__main__":
    app = SlapWinApp()
    app.run()

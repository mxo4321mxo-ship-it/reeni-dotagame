"""
Закрепляет картинку поверх всех окон в месте, которое укажешь мышкой,
и позволяет менять её яркость кнопками.

Запуск:
    python pin_image.py                 # откроется окно выбора файла
    python pin_image.py путь\\к\\картинке.png

Управление:
    1. После выбора картинки экран слегка затемнится — кликни ЛКМ туда,
       где должен быть ЛЕВЫЙ ВЕРХНИЙ угол картинки (Esc — отмена).
    2. Картинка закрепится поверх всех окон.

    Кнопки на панели управления:
        [ Ярче + ]  [ Темнее − ]  [ Сброс ]  [ Переместить ]  [ Выход ]

    Клавиши (когда активна картинка или панель):
        + / =  или  ↑   — ярче
        −      или  ↓   — темнее
        0               — сбросить яркость (100%)
        M               — выбрать новое место мышкой
        Esc             — выход

    Мышь по картинке:
        ЛКМ + тянуть    — двигать картинку
        колесико        — яркость
        ПКМ             — выход

    Глобальные горячие клавиши (работают даже в игре), если установлен
    модуль `keyboard` (pip install keyboard):
        Ctrl+Alt+↑ / Ctrl+Alt+↓ — ярче / темнее
        Ctrl+Alt+0              — сброс яркости
        Ctrl+Alt+M              — переместить
        Ctrl+Alt+Q              — выход

Нужно: Python 3 и Pillow (pip install pillow).
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    from PIL import Image, ImageEnhance, ImageTk
except ImportError:
    print("Нужен Pillow: pip install pillow")
    sys.exit(1)

try:
    import keyboard  # необязательно: глобальные горячие клавиши
except ImportError:
    keyboard = None

BRIGHTNESS_STEP = 0.1
BRIGHTNESS_MIN = 0.0
BRIGHTNESS_MAX = 3.0


def enable_dpi_awareness():
    """На Windows с масштабированием 125%/150% без этого координаты клика
    и окна не совпадают с реальными пикселями экрана."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class PinnedImage:
    def __init__(self, root, path):
        self.root = root
        self.original = Image.open(path).convert("RGBA")
        self.brightness = 1.0
        self.photo = None
        self._drag_offset = (0, 0)

        # Окно с картинкой: без рамки, поверх всех окон
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.withdraw()
        self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg="black")
        self.label.pack()

        self.label.bind("<ButtonPress-1>", self._drag_start)
        self.label.bind("<B1-Motion>", self._drag_move)
        self.label.bind("<Button-3>", lambda e: self.quit())
        self.label.bind("<MouseWheel>", self._on_wheel)        # Windows / macOS
        self.label.bind("<Button-4>", lambda e: self.change(+BRIGHTNESS_STEP))  # Linux
        self.label.bind("<Button-5>", lambda e: self.change(-BRIGHTNESS_STEP))

        self._build_panel()
        for w in (self.win, self.panel):
            self._bind_keys(w)
        self._bind_global_hotkeys()

        self.render()
        self.pick_position()

    # ---------- панель управления ----------
    def _build_panel(self):
        self.panel = tk.Toplevel(self.root)
        self.panel.title("Яркость картинки")
        self.panel.attributes("-topmost", True)
        self.panel.resizable(False, False)
        self.panel.protocol("WM_DELETE_WINDOW", self.quit)

        self.info = tk.Label(self.panel, font=("Segoe UI", 11, "bold"))
        self.info.pack(padx=10, pady=(8, 4))

        row = tk.Frame(self.panel)
        row.pack(padx=8, pady=(0, 8))
        buttons = [
            ("Ярче +", lambda: self.change(+BRIGHTNESS_STEP)),
            ("Темнее −", lambda: self.change(-BRIGHTNESS_STEP)),
            ("Сброс", self.reset),
            ("Переместить", self.pick_position),
            ("Выход", self.quit),
        ]
        for text, cmd in buttons:
            tk.Button(row, text=text, width=11, command=cmd).pack(side="left", padx=2)

        self.scale = tk.Scale(
            self.panel, from_=int(BRIGHTNESS_MIN * 100), to=int(BRIGHTNESS_MAX * 100),
            orient="horizontal", length=420, resolution=5, showvalue=False,
            command=lambda v: self.set_brightness(int(v) / 100),
        )
        self.scale.pack(padx=8, pady=(0, 8))

    def _bind_keys(self, w):
        for key in ("<plus>", "<equal>", "<KP_Add>", "<Up>"):
            w.bind(key, lambda e: self.change(+BRIGHTNESS_STEP))
        for key in ("<minus>", "<KP_Subtract>", "<Down>"):
            w.bind(key, lambda e: self.change(-BRIGHTNESS_STEP))
        w.bind("0", lambda e: self.reset())
        w.bind("<KeyPress-m>", lambda e: self.pick_position())
        w.bind("<KeyPress-M>", lambda e: self.pick_position())
        w.bind("<Escape>", lambda e: self.quit())

    def _bind_global_hotkeys(self):
        if keyboard is None:
            return
        # keyboard вызывает колбэки из своего потока — передаём в tk через after
        def safe(fn):
            return lambda: self.root.after(0, fn)
        try:
            keyboard.add_hotkey("ctrl+alt+up", safe(lambda: self.change(+BRIGHTNESS_STEP)))
            keyboard.add_hotkey("ctrl+alt+down", safe(lambda: self.change(-BRIGHTNESS_STEP)))
            keyboard.add_hotkey("ctrl+alt+0", safe(self.reset))
            keyboard.add_hotkey("ctrl+alt+m", safe(self.pick_position))
            keyboard.add_hotkey("ctrl+alt+q", safe(self.quit))
        except Exception as exc:  # например, на Linux без root
            print("Глобальные горячие клавиши недоступны:", exc)

    # ---------- яркость ----------
    def set_brightness(self, value):
        value = round(max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, value)), 2)
        if value == self.brightness:
            return
        self.brightness = value
        self.render()

    def change(self, delta):
        self.set_brightness(self.brightness + delta)

    def reset(self):
        self.set_brightness(1.0)

    def render(self):
        rgb = self.original.convert("RGB")
        alpha = self.original.getchannel("A")
        img = ImageEnhance.Brightness(rgb).enhance(self.brightness)
        img.putalpha(alpha)
        self.photo = ImageTk.PhotoImage(img)
        self.label.configure(image=self.photo)

        percent = int(round(self.brightness * 100))
        self.info.configure(text=f"Яркость: {percent}%")
        if int(self.scale.get()) != percent:
            self.scale.set(percent)

    # ---------- позиция ----------
    def pick_position(self):
        """Затемняет экран и ждёт клика — туда ставится картинка."""
        if getattr(self, "_overlay", None) is not None:
            return
        self.win.withdraw()

        ov = tk.Toplevel(self.root)
        self._overlay = ov
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.3)
        sw, sh = ov.winfo_screenwidth(), ov.winfo_screenheight()
        ov.geometry(f"{sw}x{sh}+0+0")
        ov.configure(bg="black", cursor="crosshair")
        tk.Label(
            ov, text="Кликни, где поставить картинку (левый верхний угол). Esc — отмена",
            bg="black", fg="white", font=("Segoe UI", 16, "bold"),
        ).pack(pady=40)

        def done(x=None, y=None):
            ov.destroy()
            self._overlay = None
            if x is not None:
                self.win.geometry(f"+{x}+{y}")
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.win.lift()

        ov.bind("<Button-1>", lambda e: done(e.x_root, e.y_root))
        ov.bind("<Escape>", lambda e: done())
        ov.focus_force()

    def _drag_start(self, e):
        self._drag_offset = (e.x, e.y)

    def _drag_move(self, e):
        dx, dy = self._drag_offset
        self.win.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _on_wheel(self, e):
        self.change(BRIGHTNESS_STEP if e.delta > 0 else -BRIGHTNESS_STEP)

    def quit(self):
        if keyboard is not None:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()

    path = sys.argv[1] if len(sys.argv) > 1 else filedialog.askopenfilename(
        title="Выбери картинку",
        filetypes=[("Картинки", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Все файлы", "*.*")],
    )
    if not path:
        return

    try:
        PinnedImage(root, path)
    except Exception as exc:
        messagebox.showerror("Ошибка", f"Не удалось открыть картинку:\n{exc}")
        return

    root.mainloop()


if __name__ == "__main__":
    main()

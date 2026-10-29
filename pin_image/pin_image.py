"""
Закрепляет картинку поверх всех окон в месте, которое укажешь мышкой.
Можно менять яркость и прозрачность (чтобы было видно, что под картинкой),
а также заблокировать её на месте.

Запуск:
    python pin_image.py                 # откроется окно выбора файла
    python pin_image.py путь\\к\\картинке.png

Управление:
    1. После выбора картинки экран слегка затемнится — кликни ЛКМ туда,
       где должен быть ЛЕВЫЙ ВЕРХНИЙ угол картинки (Esc — отмена).
    2. Картинка закрепится поверх всех окон.

    Панель управления:
        Яркость:      [ Темнее − ]  [ Ярче + ]  [ Сброс ]  + ползунок
        Видимость:    [ Прозрачнее ]  [ Плотнее ]          + ползунок
        [ Поставить в другое место ]  [ Другое фото ]  [ 🔓 Заблокировать ]
        [ Выход ]

    Блокировка: фото нельзя сдвинуть, а на Windows клики мышкой проходят
    сквозь фото в игру/окно под ним. Яркость и прозрачность при этом
    по-прежнему меняются с панели и горячими клавишами.

    Клавиши (когда активна картинка или панель):
        + / =  или  ↑   — ярче
        −      или  ↓   — темнее
        0               — сбросить яркость (100%)
        PgUp / PgDn     — плотнее / прозрачнее
        M               — выбрать новое место мышкой
        O               — выбрать другое фото
        L               — заблокировать / разблокировать
        Esc             — выход

    Мышь по картинке (когда не заблокирована):
        ЛКМ + тянуть    — двигать картинку
        колесико        — яркость
        ПКМ             — выход

    Глобальные горячие клавиши (работают даже в игре), если установлен
    модуль `keyboard` (pip install keyboard):
        Ctrl+Alt+↑ / Ctrl+Alt+↓       — ярче / темнее
        Ctrl+Alt+PgUp / Ctrl+Alt+PgDn — плотнее / прозрачнее
        Ctrl+Alt+0                    — сброс яркости
        Ctrl+Alt+M                    — поставить в другое место
        Ctrl+Alt+L                    — заблокировать / разблокировать
        Ctrl+Alt+Q                    — выход

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
OPACITY_STEP = 0.1
OPACITY_MIN = 0.1
OPACITY_MAX = 1.0
OPACITY_DEFAULT = 0.6
FILETYPES = [("Картинки", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Все файлы", "*.*")]


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


def set_click_through(win, enable):
    """Windows: клики мышью проходят сквозь окно в то, что под ним."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enable:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception as exc:
        print("Не удалось включить клики сквозь фото:", exc)


class PinnedImage:
    def __init__(self, root, path):
        self.root = root
        self.original = Image.open(path).convert("RGBA")
        self.brightness = 1.0
        self.opacity = OPACITY_DEFAULT
        self.locked = False  # True — фото нельзя сдвинуть, клики идут сквозь него
        self.photo = None
        self._overlay = None
        self._drag_offset = (0, 0)

        # Окно с картинкой: без рамки, поверх всех окон, полупрозрачное
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
        self.apply_opacity()
        self.pick_position()

    # ---------- панель управления ----------
    def _build_panel(self):
        self.panel = tk.Toplevel(self.root)
        self.panel.title("Закреплённое фото")
        self.panel.attributes("-topmost", True)
        self.panel.resizable(False, False)
        self.panel.protocol("WM_DELETE_WINDOW", self.quit)
        bold = ("Segoe UI", 10, "bold")

        # --- яркость ---
        self.bright_info = tk.Label(self.panel, font=("Segoe UI", 11, "bold"))
        self.bright_info.pack(padx=10, pady=(8, 2))
        row = tk.Frame(self.panel)
        row.pack(padx=8)
        for text, cmd in [
            ("Темнее −", lambda: self.change(-BRIGHTNESS_STEP)),
            ("Ярче +", lambda: self.change(+BRIGHTNESS_STEP)),
            ("Сброс", self.reset),
        ]:
            tk.Button(row, text=text, width=12, command=cmd).pack(side="left", padx=2)
        self.bright_scale = tk.Scale(
            self.panel, from_=int(BRIGHTNESS_MIN * 100), to=int(BRIGHTNESS_MAX * 100),
            orient="horizontal", length=420, resolution=5, showvalue=False,
            command=lambda v: self.set_brightness(int(v) / 100),
        )
        self.bright_scale.pack(padx=8, pady=(0, 6))

        # --- прозрачность ---
        self.opacity_info = tk.Label(self.panel, font=("Segoe UI", 11, "bold"))
        self.opacity_info.pack(padx=10, pady=(4, 2))
        row = tk.Frame(self.panel)
        row.pack(padx=8)
        for text, cmd in [
            ("Прозрачнее", lambda: self.change_opacity(-OPACITY_STEP)),
            ("Плотнее", lambda: self.change_opacity(+OPACITY_STEP)),
        ]:
            tk.Button(row, text=text, width=12, command=cmd).pack(side="left", padx=2)
        self.opacity_scale = tk.Scale(
            self.panel, from_=int(OPACITY_MIN * 100), to=int(OPACITY_MAX * 100),
            orient="horizontal", length=420, resolution=5, showvalue=False,
            command=lambda v: self.set_opacity(int(v) / 100),
        )
        self.opacity_scale.pack(padx=8, pady=(0, 6))

        # --- место / фото / блокировка ---
        row = tk.Frame(self.panel)
        row.pack(padx=8, pady=(4, 4), fill="x")
        self.place_btn = tk.Button(
            row, text="📍 Поставить в другое место", font=bold,
            bg="#2e7d32", fg="white", activebackground="#388e3c", activeforeground="white",
            command=self.pick_position,
        )
        self.place_btn.pack(side="left", padx=2, expand=True, fill="x")
        tk.Button(row, text="🖼 Другое фото", font=bold, command=self.change_image).pack(
            side="left", padx=2, expand=True, fill="x")
        self.lock_btn = tk.Button(row, font=bold, command=self.toggle_lock)
        self.lock_btn.pack(side="left", padx=2, expand=True, fill="x")
        self._update_lock_button()

        tk.Button(self.panel, text="Выход", width=12, command=self.quit).pack(pady=(4, 8))

    def _bind_keys(self, w):
        for key in ("<plus>", "<equal>", "<KP_Add>", "<Up>"):
            w.bind(key, lambda e: self.change(+BRIGHTNESS_STEP))
        for key in ("<minus>", "<KP_Subtract>", "<Down>"):
            w.bind(key, lambda e: self.change(-BRIGHTNESS_STEP))
        w.bind("0", lambda e: self.reset())
        w.bind("<Prior>", lambda e: self.change_opacity(+OPACITY_STEP))  # PgUp
        w.bind("<Next>", lambda e: self.change_opacity(-OPACITY_STEP))   # PgDn
        for key, fn in (("m", self.pick_position), ("o", self.change_image), ("l", self.toggle_lock)):
            w.bind(f"<KeyPress-{key}>", lambda e, fn=fn: fn())
            w.bind(f"<KeyPress-{key.upper()}>", lambda e, fn=fn: fn())
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
            keyboard.add_hotkey("ctrl+alt+page up", safe(lambda: self.change_opacity(+OPACITY_STEP)))
            keyboard.add_hotkey("ctrl+alt+page down", safe(lambda: self.change_opacity(-OPACITY_STEP)))
            keyboard.add_hotkey("ctrl+alt+0", safe(self.reset))
            keyboard.add_hotkey("ctrl+alt+m", safe(self.pick_position))
            keyboard.add_hotkey("ctrl+alt+l", safe(self.toggle_lock))
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
        img = ImageEnhance.Brightness(self.original.convert("RGB")).enhance(self.brightness)
        self.photo = ImageTk.PhotoImage(img)
        self.label.configure(image=self.photo)

        percent = int(round(self.brightness * 100))
        self.bright_info.configure(text=f"Яркость: {percent}%")
        if int(self.bright_scale.get()) != percent:
            self.bright_scale.set(percent)

    # ---------- прозрачность ----------
    def set_opacity(self, value):
        value = round(max(OPACITY_MIN, min(OPACITY_MAX, value)), 2)
        if value == self.opacity:
            return
        self.opacity = value
        self.apply_opacity()

    def change_opacity(self, delta):
        self.set_opacity(self.opacity + delta)

    def apply_opacity(self):
        self.win.attributes("-alpha", self.opacity)
        if self.locked:  # tk мог сбросить стиль окна — возвращаем клики сквозь фото
            set_click_through(self.win, True)

        percent = int(round(self.opacity * 100))
        self.opacity_info.configure(text=f"Видимость фото: {percent}%  (меньше — лучше видно, что под ним)")
        if int(self.opacity_scale.get()) != percent:
            self.opacity_scale.set(percent)

    # ---------- фото ----------
    def change_image(self):
        """Выбрать другой файл. Если фото заблокировано — новое встаёт на то же место."""
        path = filedialog.askopenfilename(parent=self.panel, title="Выбери картинку", filetypes=FILETYPES)
        if not path:
            return
        try:
            self.original = Image.open(path).convert("RGBA")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось открыть картинку:\n{exc}", parent=self.panel)
            return
        self.render()
        if not self.locked:
            self.pick_position()

    # ---------- блокировка ----------
    def toggle_lock(self):
        self.locked = not self.locked
        set_click_through(self.win, self.locked)
        self._update_lock_button()

    def _update_lock_button(self):
        if self.locked:
            self.lock_btn.configure(
                text="🔒 Разблокировать", bg="#c62828", fg="white",
                activebackground="#d32f2f", activeforeground="white",
            )
            self.place_btn.configure(state="disabled")
        else:
            self.lock_btn.configure(
                text="🔓 Заблокировать", bg="#455a64", fg="white",
                activebackground="#546e7a", activeforeground="white",
            )
            self.place_btn.configure(state="normal")

    # ---------- позиция ----------
    def pick_position(self):
        """Затемняет экран и ждёт клика — туда ставится картинка."""
        if self.locked or self._overlay is not None:
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
        if self.locked:
            return
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
        title="Выбери картинку", filetypes=FILETYPES,
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

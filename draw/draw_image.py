"""
Рисует картинку мышкой в выбранной области экрана:
Roblox (Starving Artists и другие рисовалки), Paint, Gartic Phone, skribbl.io и т.д.

Установка:
    pip install pyautogui pillow pynput

Примеры:
    python draw_image.py кот.png --roblox                      чёрно-белый
    python draw_image.py кот.png --roblox --colors 16          цветной, 16 цветов
    python draw_image.py кот.png --roblox --colors 16 --grid 32 32
                                         холст-сетка 32x32 клетки (Starving Artists)

Как пользоваться:
    1. Открой игру/программу, выбери кисть. Толщина кисти = --step + 1 px (в режиме
       сетки — размер кисти 1 клетка).
    2. Запусти скрипт.
    3. Наведи мышь на ЛЕВЫЙ ВЕРХНИЙ угол холста и нажми F8,
       затем на ПРАВЫЙ НИЖНИЙ угол — F8.
       В режиме сетки отмечай самые края холста, а не центры клеток.
    4. Для цветного рисунка: наведи мышь на поле ввода HEX-цвета и нажми F8
       (или Esc — тогда будешь выбирать цвета сам, скрипт подскажет какой).
    5. Посмотри preview.png, вернись в игру и нажми F8 — начнётся рисование.
    6. Остановить: Esc (или резко увести мышь в левый верхний угол экрана).
"""

import argparse
import os
import sys
import threading
import time

from PIL import Image, ImageDraw, ImageOps

# 8 соседей; сначала прямые, потом диагональные — так контуры получаются ровнее
NEIGHBORS = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)]


# ---------------------------------------------------------------- мышь

def enable_dpi_awareness():
    """Без этого при масштабе Windows 125%/150% координаты мыши съезжают."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class WinMouse:
    """Мышь через SendInput — такие события видит Roblox и другие игры
    (pyautogui двигает курсор через SetCursorPos, и Roblox этого не замечает)."""

    MOVE, LEFTDOWN, LEFTUP, VIRTUALDESK, ABSOLUTE = 0x1, 0x2, 0x4, 0x4000, 0x8000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

        self.ctypes, self.wintypes, self.INPUT = ctypes, wintypes, INPUT
        self.user32 = ctypes.windll.user32
        gsm = self.user32.GetSystemMetrics
        self.vx, self.vy, self.vw, self.vh = gsm(76), gsm(77), gsm(78), gsm(79)

    def _send(self, flags, dx=0, dy=0):
        inp = self.INPUT(type=0)
        inp.mi.dx, inp.mi.dy, inp.mi.dwFlags = dx, dy, flags
        self.user32.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(inp))

    def position(self):
        pt = self.wintypes.POINT()
        self.user32.GetCursorPos(self.ctypes.byref(pt))
        return pt.x, pt.y

    def move(self, x, y):
        # пиксель -> 0..65535 по всему виртуальному рабочему столу (с округлением вверх)
        dx = ((x - self.vx) * 65536 + self.vw - 1) // self.vw
        dy = ((y - self.vy) * 65536 + self.vh - 1) // self.vh
        self._send(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, dx, dy)
        if self.position() != (x, y):  # подстраховка: ровно в нужный пиксель
            self.user32.SetCursorPos(x, y)

    def down(self):
        self._send(self.LEFTDOWN)

    def up(self):
        self._send(self.LEFTUP)


class PyAutoGuiMouse:
    def __init__(self):
        import pyautogui
        pyautogui.PAUSE = 0
        pyautogui.MINIMUM_DURATION = 0
        self.p = pyautogui

    def position(self):
        pos = self.p.position()
        return pos.x, pos.y

    def move(self, x, y):
        self.p.moveTo(x, y, _pause=False)

    def down(self):
        self.p.mouseDown(_pause=False)

    def up(self):
        self.p.mouseUp(_pause=False)


def make_mouse():
    return WinMouse() if sys.platform == "win32" else PyAutoGuiMouse()


# ---------------------------------------------------------------- клавиатура

def wait_key(prompt):
    """Печатает подсказку и ждёт F8 (True) или Esc (False)."""
    from pynput import keyboard

    print(prompt)
    result = []

    def on_press(key):
        if key in (keyboard.Key.f8, keyboard.Key.esc):
            result.append(key == keyboard.Key.f8)
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
    return result[0]


def pick_point(mouse, prompt):
    if not wait_key(prompt):
        return None
    pos = mouse.position()
    print(f"  -> {pos[0]}, {pos[1]}")
    return pos


def select_region(mouse):
    p1 = pick_point(mouse, "Наведи мышь на ЛЕВЫЙ ВЕРХНИЙ угол холста и нажми F8 (Esc — выход)")
    if not p1:
        sys.exit("Отменено.")
    p2 = pick_point(mouse, "Теперь на ПРАВЫЙ НИЖНИЙ угол холста и нажми F8")
    if not p2:
        sys.exit("Отменено.")
    left, top = min(p1[0], p2[0]), min(p1[1], p2[1])
    width, height = abs(p2[0] - p1[0]), abs(p2[1] - p1[1])
    if width < 5 or height < 5:
        sys.exit("Область слишком маленькая.")
    return left, top, width, height


class Clipboard:
    def __init__(self):
        try:
            import tkinter
            self.tk = tkinter.Tk()
            self.tk.withdraw()
        except Exception:
            self.tk = None

    def set(self, text):
        if self.tk:
            self.tk.clipboard_clear()
            self.tk.clipboard_append(text)
            self.tk.update()


# ---------------------------------------------------------------- картинка

def load_image(path, invert):
    img = Image.open(path)
    img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")  # прозрачный фон -> белый
    if invert:
        img = ImageOps.invert(img)
    return img


def layout(img, region_w, region_h, step, grid):
    """Размер картинки в клетках и геометрия клеток на экране."""
    if grid:
        cols, rows = grid
        # сетка: картинка растягивается ровно на все клетки холста
        return cols, rows, region_w / cols, region_h / rows, 0.0, 0.0
    cols, rows = max(1, region_w // step), max(1, region_h // step)
    scale = min(cols / img.width, rows / img.height)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    return w, h, step, step, (region_w - w * step) / 2, (region_h - h * step) / 2


def color_layers(img, w, h, colors, threshold, dither, bg, smooth):
    """Возвращает [(цвет (r,g,b), маска)], маска[y][x] = True — закрасить этим цветом."""
    original = img
    # при увеличении цветной картинки сглаживание даёт каёмки чужих цветов,
    # поэтому пиксели переносим как есть
    if colors > 1 and w >= img.width:
        smooth = False
    img = img.resize((w, h), Image.LANCZOS if smooth else Image.NEAREST)

    if colors <= 1:
        gray = img.convert("L")
        px = (gray.convert("1") if dither else gray).load()
        if dither:
            mask = [[px[x, y] == 0 for x in range(w)] for y in range(h)]
        else:
            mask = [[px[x, y] < threshold for x in range(w)] for y in range(h)]
        return [((0, 0, 0), mask)]

    # палитру берём из оригинала: при масштабировании на краях появляются
    # смешанные цвета, которых в картинке нет, — они не должны занимать палитру
    palette = original.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                                dither=Image.Dither.NONE)
    q = img.quantize(palette=palette,
                     dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
    pal = q.getpalette()
    px = q.load()
    used = {}
    for y in range(h):
        for x in range(w):
            used.setdefault(px[x, y], 0)
            used[px[x, y]] += 1

    layers = []
    for idx, count in sorted(used.items(), key=lambda kv: -kv[1]):
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        if bg and sum((a - b) ** 2 for a, b in zip(rgb, bg)) < 20 ** 2:
            continue  # цвет фона холста — не рисуем
        mask = [[px[x, y] == idx for x in range(w)] for y in range(h)]
        layers.append((rgb, mask))
    # светлые цвета первыми, тёмные поверх — края получаются чище
    layers.sort(key=lambda l: -sum(l[0]))
    return layers


def fill_paths(mask, w, h):
    """Горизонтальные линии по закрашиваемым клеткам, змейкой."""
    paths = []
    for y in range(h):
        runs = []
        x = 0
        while x < w:
            if mask[y][x]:
                start = x
                while x + 1 < w and mask[y][x + 1]:
                    x += 1
                runs.append([(start, y), (x, y)])
            x += 1
        if y % 2:
            runs = [list(reversed(r)) for r in reversed(runs)]
        paths.extend(runs)
    return paths


def outline_paths(mask, w, h):
    """Граница закрашиваемых областей в виде непрерывных ломаных."""
    def on(x, y):
        return 0 <= x < w and 0 <= y < h and mask[y][x]

    edge = set()
    for y in range(h):
        for x in range(w):
            if mask[y][x] and not (on(x + 1, y) and on(x - 1, y) and on(x, y + 1) and on(x, y - 1)):
                edge.add((x, y))

    paths = []
    for y in range(h):
        for x in range(w):
            if (x, y) not in edge:
                continue
            path = [(x, y)]
            edge.discard((x, y))
            cx, cy = x, y
            while True:
                for dx, dy in NEIGHBORS:
                    nxt = (cx + dx, cy + dy)
                    if nxt in edge:
                        edge.discard(nxt)
                        path.append(nxt)
                        cx, cy = nxt
                        break
                else:
                    break
            paths.append(simplify(path))
    return paths


def simplify(path):
    """Убирает промежуточные точки на прямых участках (форма не меняется)."""
    if len(path) < 3:
        return path
    out = [path[0]]
    for i in range(1, len(path) - 1):
        ax, ay = out[-1]
        bx, by = path[i]
        cx, cy = path[i + 1]
        if (bx - ax) * (cy - ay) == (by - ay) * (cx - ax) and \
                (bx - ax) * (cx - bx) >= 0 and (by - ay) * (cy - by) >= 0:
            continue
        out.append(path[i])
    out.append(path[-1])
    return out


def build_plan(args, region_w, region_h):
    """Возвращает (план [(цвет, [ломаные в клетках])], геометрия)."""
    img = load_image(args.image, args.invert)
    w, h, cw, ch, ox, oy = layout(img, region_w, region_h, args.step, args.grid)
    bg = None if args.bg == "none" else hex_to_rgb(args.bg)
    layers = color_layers(img, w, h, args.colors, args.threshold, args.dither, bg,
                          smooth=not args.grid)
    plan = []
    for rgb, mask in layers:
        paths = []
        if args.mode in ("fill", "full"):
            paths += fill_paths(mask, w, h)
        if args.mode in ("outline", "full") and not args.dither and not args.grid:
            paths += outline_paths(mask, w, h)
        if paths:
            plan.append((rgb, paths))
    return plan, (w, h, cw, ch, ox, oy)


def to_screen(x, y, geom, left, top):
    """Клетка -> пиксель экрана (центр клетки)."""
    _, _, cw, ch, ox, oy = geom
    return int(left + ox + (x + 0.5) * cw), int(top + oy + (y + 0.5) * ch)


def hex_to_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "%02X%02X%02X" % rgb


def save_preview(plan, geom, region_w, region_h, path="preview.png"):
    """Как будет выглядеть результат (каждая клетка — своим цветом)."""
    w, h, cw, ch, ox, oy = geom
    img = Image.new("RGB", (region_w, region_h), "white")
    d = ImageDraw.Draw(img)
    for rgb, paths in plan:
        for p in paths:
            pts = [to_screen(x, y, geom, 0, 0) for x, y in p]
            if len(pts) == 1 or len(pts) == 2 and pts[0] == pts[1]:
                x, y = pts[0]
                d.rectangle((x - cw / 2, y - ch / 2, x + cw / 2, y + ch / 2), fill=rgb)
            else:
                d.line(pts, fill=rgb, width=max(1, round(min(cw, ch))), joint="curve")
    img.save(path)
    return os.path.abspath(path)


# ---------------------------------------------------------------- рисование

class Stopped(Exception):
    pass


def set_color(rgb, color_field, mouse, clipboard, args):
    hex_code = ("#" if args.hash else "") + rgb_to_hex(rgb)
    clipboard.set(hex_code)
    if not color_field:
        if not wait_key(f"\nВыбери цвет {hex_code} (уже скопирован — можно Ctrl+V), "
                        f"вернись к холсту и нажми F8 (Esc — стоп)"):
            raise Stopped
        return
    import pyautogui
    print(f"\nЦвет {hex_code}")
    mouse.move(*color_field)
    time.sleep(0.1)
    mouse.down()
    time.sleep(0.05)
    mouse.up()
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    for _ in range(10):
        pyautogui.press("backspace")
    pyautogui.write(hex_code, interval=0.03)
    time.sleep(0.05)
    pyautogui.press("enter")
    time.sleep(0.3)


def draw(plan, geom, left, top, mouse, args, color_field):
    from pynput import keyboard

    stop = threading.Event()

    def on_press(key):
        if key == keyboard.Key.esc:
            stop.set()

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    # шаг движения: не больше клетки, иначе игра, читающая мышь раз в кадр, оставит дыры
    cw, ch = geom[2], geom[3]
    seg = max(1.0, min(cw, ch) * args.seg)
    d, dpress = args.delay, max(args.delay, args.press_delay)
    clipboard = Clipboard()

    def check():
        if stop.is_set():
            raise Stopped
        if mouse.position() == (0, 0):
            stop.set()
            raise Stopped

    total = sum(len(p) for _, p in plan)
    done = 0
    try:
        for rgb, paths in plan:
            if args.colors > 1:
                set_color(rgb, color_field, mouse, clipboard, args)
            for path in paths:
                check()
                pts = [to_screen(x, y, geom, left, top) for x, y in path]
                mouse.move(*pts[0])
                time.sleep(dpress)
                mouse.down()
                time.sleep(dpress)
                if len(pts) == 1 or len(pts) == 2 and pts[0] == pts[1]:
                    x, y = pts[0]
                    mouse.move(x + 1, y)  # «подёргать», чтобы игра точно поставила точку
                    time.sleep(d)
                    mouse.move(x, y)
                    time.sleep(d)
                px, py = pts[0]
                for x, y in pts[1:]:
                    n = max(1, round(max(abs(x - px), abs(y - py)) / seg))
                    for k in range(1, n + 1):
                        mouse.move(round(px + (x - px) * k / n), round(py + (y - py) * k / n))
                        time.sleep(d)
                    px, py = x, y
                time.sleep(d)
                mouse.up()
                time.sleep(dpress)
                done += 1
                if done % 20 == 0 or done == total:
                    print(f"\r  {done}/{total} линий ({done * 100 // total}%)", end="", flush=True)
        print("\nГотово!")
    except Stopped:
        print("\nОстановлено.")
    finally:
        mouse.up()
        listener.stop()


def main():
    enable_dpi_awareness()

    p = argparse.ArgumentParser(description="Рисует картинку мышкой в выбранной области экрана")
    p.add_argument("image", help="путь к картинке (png/jpg/...)")
    p.add_argument("--roblox", action="store_true",
                   help="настройки для Roblox: медленнее, с учётом 60 FPS игры")
    p.add_argument("--colors", type=int, default=1,
                   help="сколько цветов: 1 — чёрно-белый (по умолчанию), 2..64 — цветной")
    p.add_argument("--grid", type=int, nargs=2, metavar=("COLS", "ROWS"),
                   help="холст — сетка из клеток (Starving Artists и т.п.): "
                        "картинка ложится ровно 1 пиксель = 1 клетка")
    p.add_argument("--mode", choices=["full", "fill", "outline"], default="full",
                   help="full — заливка + обводка (по умолчанию), fill — только заливка, "
                        "outline — только контуры")
    p.add_argument("--step", type=int, default=2,
                   help="размер «пикселя» рисунка = толщина кисти (по умолчанию 2; "
                        "без --grid)")
    p.add_argument("--threshold", type=int, default=128,
                   help="для ч/б: порог яркости 0-255 (по умолчанию 128)")
    p.add_argument("--dither", action="store_true", help="дизеринг (для фото)")
    p.add_argument("--invert", action="store_true", help="инвертировать картинку")
    p.add_argument("--bg", default="ffffff",
                   help="цвет фона холста — его не рисуем (по умолчанию ffffff, "
                        "none — рисовать всё)")
    p.add_argument("--hash", action="store_true", help="вводить цвет с # (#FF0000)")
    p.add_argument("--delay", type=float, default=None,
                   help="пауза между движениями мыши, сек (по умолчанию 0.004, с --roblox 0.02)")
    p.add_argument("--press-delay", type=float, default=None,
                   help="пауза при нажатии/отпускании, сек (по умолчанию 0.01, с --roblox 0.04)")
    p.add_argument("--seg", type=float, default=1.0,
                   help="длина одного движения в клетках (по умолчанию 1)")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                   help="задать область числами вместо выбора мышью")
    p.add_argument("--yes", action="store_true", help="не ждать F8 после превью")
    args = p.parse_args()

    if args.delay is None:
        args.delay = 0.02 if args.roblox else 0.004
    if args.press_delay is None:
        args.press_delay = 0.04 if args.roblox else 0.01
    if args.step < 1:
        sys.exit("--step должен быть >= 1")
    if args.grid and min(args.grid) < 1:
        sys.exit("--grid: размер сетки должен быть >= 1")
    if args.grid and args.mode == "outline":
        sys.exit("--mode outline не имеет смысла для сетки")

    mouse = make_mouse()
    if args.region:
        left, top, width, height = args.region
    else:
        left, top, width, height = select_region(mouse)
    print(f"Холст: x={left}, y={top}, {width}x{height}")
    if args.grid:
        print(f"Сетка {args.grid[0]}x{args.grid[1]}, клетка "
              f"{width / args.grid[0]:.1f}x{height / args.grid[1]:.1f} px")

    plan, geom = build_plan(args, width, height)
    if not plan:
        sys.exit("Нечего рисовать — попробуй изменить --threshold, --invert или --bg none.")

    color_field = None
    if args.colors > 1:
        color_field = pick_point(mouse, "Наведи мышь на ПОЛЕ ВВОДА HEX-цвета в игре и нажми F8 "
                                        "(Esc — буду выбирать цвета сам)")

    preview = save_preview(plan, geom, width, height)
    lines = sum(len(paths) for _, paths in plan)
    cells = sum(max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                for _, paths in plan for p in paths for a, b in zip(p, p[1:]))
    est = cells / args.seg * args.delay + lines * (3 * args.press_delay + 2 * args.delay)
    print(f"Цветов: {len(plan)}, линий: {lines}. Превью: {preview}")
    print(f"Примерное время: {est / 60:.0f} мин")
    if not args.yes and not wait_key("Вернись в игру и нажми F8 — начать (Esc — отмена)"):
        sys.exit("Отменено.")
    print("Начинаю через 1 секунду... (Esc — стоп)")
    time.sleep(1)
    draw(plan, geom, left, top, mouse, args, color_field)


if __name__ == "__main__":
    main()

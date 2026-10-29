"""
Рисует картинку мышкой в выбранной области экрана
(Paint, Gartic Phone, skribbl.io, любой холст в браузере и т.д.).

Установка:
    pip install pyautogui pillow pynput

Запуск:
    python draw_image.py картинка.png
    python draw_image.py картинка.png --mode outline --step 2

Как пользоваться:
    1. Открой программу/сайт, где можно рисовать, и выбери чёрную кисть.
       Толщину кисти поставь примерно равной --step (по умолчанию 2 px).
    2. Запусти скрипт.
    3. Наведи мышь на ЛЕВЫЙ ВЕРХНИЙ угол области и нажми F8.
    4. Наведи мышь на ПРАВЫЙ НИЖНИЙ угол области и нажми F8.
    5. Посмотри preview.png — так будет выглядеть рисунок.
       Вернись в окно рисования и нажми F8.
    6. Скрипт рисует. Остановить: Esc
       (или резко увести мышь в левый верхний угол экрана).
"""

import argparse
import os
import sys
import threading
import time

from PIL import Image, ImageDraw, ImageOps

SELECT_KEY_NAME = "F8"

# 8 соседей; сначала прямые, потом диагональные — так контуры получаются ровнее
NEIGHBORS = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)]


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


def load_mask(path, region_w, region_h, step, threshold, dither, invert):
    """Возвращает (mask, w, h, off_x, off_y): mask[y][x] = True, если пиксель надо закрасить."""
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        # прозрачный фон -> белый
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("L")
    if invert:
        img = ImageOps.invert(img)

    # вписываем картинку в область с сохранением пропорций
    cols = max(1, region_w // step)
    rows = max(1, region_h // step)
    scale = min(cols / img.width, rows / img.height)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((w, h), Image.LANCZOS)

    if dither:
        px = img.convert("1").load()  # дизеринг Флойда-Стейнберга
        mask = [[px[x, y] == 0 for x in range(w)] for y in range(h)]
    else:
        px = img.load()
        mask = [[px[x, y] < threshold for x in range(w)] for y in range(h)]

    # центрируем внутри области
    off_x = (region_w - w * step) // 2
    off_y = (region_h - h * step) // 2
    return mask, w, h, off_x, off_y


def fill_paths(mask, w, h):
    """Горизонтальные линии по тёмным участкам, змейкой (меньше холостых перемещений)."""
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
    """Граница тёмных областей в виде непрерывных ломаных."""
    def dark(x, y):
        return 0 <= x < w and 0 <= y < h and mask[y][x]

    edge = set()
    for y in range(h):
        for x in range(w):
            if mask[y][x] and not (dark(x + 1, y) and dark(x - 1, y) and dark(x, y + 1) and dark(x, y - 1)):
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
        # точки на одной прямой и b между a и c — b не нужна
        if (bx - ax) * (cy - ay) == (by - ay) * (cx - ax) and \
                (bx - ax) * (cx - bx) >= 0 and (by - ay) * (cy - by) >= 0:
            continue
        out.append(path[i])
    out.append(path[-1])
    return out


def build_paths(args, region_w, region_h):
    mask, w, h, off_x, off_y = load_mask(args.image, region_w, region_h, args.step,
                                         args.threshold, args.dither, args.invert)
    paths = []
    if args.mode in ("fill", "full"):
        paths += fill_paths(mask, w, h)
    if args.mode in ("outline", "full") and not args.dither:
        paths += outline_paths(mask, w, h)
    # из клеток в пиксели области (центр клетки)
    half = args.step // 2
    return [[(off_x + x * args.step + half, off_y + y * args.step + half) for x, y in p]
            for p in paths]


def save_preview(paths, region_w, region_h, brush, path="preview.png"):
    img = Image.new("RGB", (region_w, region_h), "white")
    d = ImageDraw.Draw(img)
    for p in paths:
        if len(p) == 1 or p[0] == p[-1] and len(p) == 2:
            x, y = p[0]
            r = brush / 2
            d.ellipse((x - r, y - r, x + r, y + r), fill="black")
        else:
            d.line(p, fill="black", width=max(1, brush), joint="curve")
    img.save(path)
    return os.path.abspath(path)


def select_region():
    """Ждёт два нажатия F8 и возвращает (left, top, width, height)."""
    import pyautogui
    from pynput import keyboard

    points = []
    done = threading.Event()

    def on_press(key):
        if key == keyboard.Key.f8:
            pos = pyautogui.position()
            points.append((pos.x, pos.y))
            print(f"  точка {len(points)}: {pos.x}, {pos.y}")
            if len(points) == 1:
                print("Теперь наведи на ПРАВЫЙ НИЖНИЙ угол и нажми F8")
            else:
                done.set()
                return False
        elif key == keyboard.Key.esc:
            done.set()
            return False

    print(f"Наведи мышь на ЛЕВЫЙ ВЕРХНИЙ угол области и нажми {SELECT_KEY_NAME} (Esc — выход)")
    with keyboard.Listener(on_press=on_press) as listener:
        done.wait()
        listener.stop()

    if len(points) < 2:
        sys.exit("Отменено.")

    (x1, y1), (x2, y2) = points
    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width < 5 or height < 5:
        sys.exit("Область слишком маленькая.")
    return left, top, width, height


def wait_f8():
    """True — нажали F8, False — Esc."""
    from pynput import keyboard

    result = []

    def on_press(key):
        if key in (keyboard.Key.f8, keyboard.Key.esc):
            result.append(key == keyboard.Key.f8)
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
    return result[0]


def draw(paths, left, top, delay, seg_len):
    import pyautogui
    from pynput import keyboard

    pyautogui.FAILSAFE = True  # мышь в угол экрана = аварийная остановка
    pyautogui.PAUSE = 0
    pyautogui.MINIMUM_DURATION = 0

    stop = threading.Event()

    def on_press(key):
        if key == keyboard.Key.esc:
            stop.set()
            return False

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    def move(x, y):
        pyautogui.moveTo(left + x, top + y, _pause=False)

    total = len(paths)
    try:
        for i, path in enumerate(paths, 1):
            if stop.is_set():
                print("\nОстановлено (Esc).")
                break
            x0, y0 = path[0]
            move(x0, y0)
            time.sleep(delay)
            pyautogui.mouseDown(_pause=False)
            time.sleep(delay)
            if len(path) == 1 or path[0] == path[-1] and len(path) == 2:
                move(x0 + 1, y0)  # точка: многим программам нужно движение
                time.sleep(delay)
            px, py = x0, y0
            for x, y in path[1:]:
                # длинные отрезки дробим, чтобы программа не пропустила движение
                n = max(1, int(max(abs(x - px), abs(y - py)) / seg_len))
                for k in range(1, n + 1):
                    move(round(px + (x - px) * k / n), round(py + (y - py) * k / n))
                    time.sleep(delay)
                px, py = x, y
            pyautogui.mouseUp(_pause=False)
            time.sleep(delay)
            if i % 20 == 0 or i == total:
                print(f"\r  {i}/{total} линий ({i * 100 // total}%)", end="", flush=True)
        else:
            print("\nГотово!")
    except pyautogui.FailSafeException:
        print("\nОстановлено (мышь в углу экрана).")
    finally:
        pyautogui.mouseUp()
        listener.stop()


def main():
    enable_dpi_awareness()

    p = argparse.ArgumentParser(description="Рисует картинку мышкой в выбранной области экрана")
    p.add_argument("image", help="путь к картинке (png/jpg/...)")
    p.add_argument("--mode", choices=["full", "fill", "outline"], default="full",
                   help="full — заливка + обводка краёв (по умолчанию, точнее всего), "
                        "fill — только заливка, outline — только контуры (быстрее)")
    p.add_argument("--step", type=int, default=2,
                   help="размер «пикселя» рисунка = толщина кисти; 1 — максимум деталей, "
                        "но очень долго (по умолчанию 2)")
    p.add_argument("--threshold", type=int, default=128,
                   help="порог яркости 0-255: что темнее — рисуется (по умолчанию 128)")
    p.add_argument("--dither", action="store_true",
                   help="дизеринг для передачи полутонов (для фото)")
    p.add_argument("--invert", action="store_true", help="инвертировать картинку")
    p.add_argument("--delay", type=float, default=0.004,
                   help="пауза между движениями мыши в секундах; увеличь (0.01-0.02), "
                        "если программа пропускает линии")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                   help="задать область числами вместо выбора мышью")
    p.add_argument("--yes", action="store_true", help="не ждать F8 после превью")
    args = p.parse_args()

    if args.step < 1:
        sys.exit("--step должен быть >= 1")

    if args.region:
        left, top, width, height = args.region
    else:
        left, top, width, height = select_region()
    print(f"Область: x={left}, y={top}, {width}x{height}")

    paths = build_paths(args, width, height)
    if not paths:
        sys.exit("Нечего рисовать — попробуй изменить --threshold или --invert.")

    preview = save_preview(paths, width, height, args.step)
    print(f"Линий: {len(paths)}. Превью: {preview}")
    if not args.yes:
        print("Вернись в окно рисования и нажми F8 — начать (Esc — отмена)")
        if not wait_f8():
            sys.exit("Отменено.")
    print("Начинаю через 1 секунду... (Esc — стоп)")
    time.sleep(1)
    draw(paths, left, top, args.delay, seg_len=max(4, args.step * 4))


if __name__ == "__main__":
    main()

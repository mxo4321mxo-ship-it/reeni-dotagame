"""
Рисует картинку мышкой в выбранной области экрана
(Paint, Gartic Phone, skribbl.io, любой холст в браузере и т.д.).

Установка:
    pip install pyautogui pillow pynput

Запуск:
    python draw_image.py картинка.png
    python draw_image.py картинка.png --mode outline --step 3

Как пользоваться:
    1. Открой программу/сайт, где можно рисовать, и выбери чёрную кисть.
    2. Запусти скрипт.
    3. Наведи мышь на ЛЕВЫЙ ВЕРХНИЙ угол области и нажми F8.
    4. Наведи мышь на ПРАВЫЙ НИЖНИЙ угол области и нажми F8.
    5. Скрипт начнёт рисовать. Остановить: Esc
       (или резко увести мышь в левый верхний угол экрана).
"""

import argparse
import sys
import threading

from PIL import Image, ImageFilter, ImageOps

SELECT_KEY_NAME = "F8"


def image_to_strokes(path, region_w, region_h, step, mode, threshold, dither, invert):
    """Превращает картинку в список горизонтальных штрихов (x1, x2, y) в пикселях области."""
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
    new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    img = img.resize(new_size, Image.LANCZOS)

    if mode == "outline":
        # рамка из соседних пикселей, чтобы фильтр не рисовал края самой картинки
        img = ImageOps.autocontrast(img)
        padded = img.resize((new_size[0] + 2, new_size[1] + 2))
        padded.paste(img, (1, 1))
        img = padded.filter(ImageFilter.FIND_EDGES).crop((1, 1, new_size[0] + 1, new_size[1] + 1))
        img = ImageOps.invert(img)  # контуры становятся тёмными

    if dither and mode == "fill":
        bw = img.convert("1")  # дизеринг Флойда-Стейнберга
        dark = lambda x, y: bw.getpixel((x, y)) == 0
    else:
        dark = lambda x, y: img.getpixel((x, y)) < threshold

    # центрируем внутри области
    off_x = (region_w - new_size[0] * step) // 2
    off_y = (region_h - new_size[1] * step) // 2

    strokes = []
    for y in range(new_size[1]):
        x = 0
        while x < new_size[0]:
            if dark(x, y):
                start = x
                while x + 1 < new_size[0] and dark(x + 1, y):
                    x += 1
                strokes.append((off_x + start * step, off_x + x * step, off_y + y * step))
            x += 1
    return strokes


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


def draw(strokes, left, top, stroke_duration):
    import pyautogui
    from pynput import keyboard

    pyautogui.FAILSAFE = True  # мышь в угол экрана = аварийная остановка
    pyautogui.PAUSE = 0

    stop = threading.Event()

    def on_press(key):
        if key == keyboard.Key.esc:
            stop.set()
            return False

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    total = len(strokes)
    try:
        for i, (x1, x2, y) in enumerate(strokes, 1):
            if stop.is_set():
                print("\nОстановлено (Esc).")
                break
            pyautogui.moveTo(left + x1, top + y)
            pyautogui.mouseDown()
            if x2 > x1:
                pyautogui.moveTo(left + x2, top + y, duration=stroke_duration)
            else:
                pyautogui.moveTo(left + x1 + 1, top + y)  # точка
            pyautogui.mouseUp()
            if i % 50 == 0 or i == total:
                print(f"\r  {i}/{total} штрихов ({i * 100 // total}%)", end="", flush=True)
        else:
            print("\nГотово!")
    except pyautogui.FailSafeException:
        print("\nОстановлено (мышь в углу экрана).")
    finally:
        pyautogui.mouseUp()
        listener.stop()


def main():
    p = argparse.ArgumentParser(description="Рисует картинку мышкой в выбранной области экрана")
    p.add_argument("image", help="путь к картинке (png/jpg/...)")
    p.add_argument("--mode", choices=["fill", "outline"], default="fill",
                   help="fill — заливка тёмных мест, outline — только контуры (быстрее)")
    p.add_argument("--step", type=int, default=4,
                   help="расстояние между линиями в пикселях; меньше = детальнее, но дольше (по умолчанию 4)")
    p.add_argument("--threshold", type=int, default=128,
                   help="порог яркости 0-255: что темнее — рисуется (по умолчанию 128)")
    p.add_argument("--dither", action="store_true",
                   help="дизеринг для передачи полутонов (только для fill)")
    p.add_argument("--invert", action="store_true", help="инвертировать картинку")
    p.add_argument("--speed", type=float, default=0.01,
                   help="время на один штрих в секундах; увеличь, если программа пропускает линии")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                   help="задать область числами вместо выбора мышью")
    args = p.parse_args()

    if args.step < 1:
        sys.exit("--step должен быть >= 1")

    if args.region:
        left, top, width, height = args.region
    else:
        left, top, width, height = select_region()
    print(f"Область: x={left}, y={top}, {width}x{height}")

    strokes = image_to_strokes(args.image, width, height, args.step, args.mode,
                               args.threshold, args.dither, args.invert)
    if not strokes:
        sys.exit("Нечего рисовать — попробуй изменить --threshold или --invert.")
    print(f"Штрихов: {len(strokes)}. Начинаю через 2 секунды... (Esc — стоп)")

    import time
    time.sleep(2)
    draw(strokes, left, top, args.speed)


if __name__ == "__main__":
    main()

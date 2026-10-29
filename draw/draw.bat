@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

rem --- ищем Python ---
set PY=
where py >nul 2>nul && set PY=py
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
    echo Python не найден. Установи его с https://www.python.org/downloads/
    echo При установке отметь галочку "Add Python to PATH".
    pause
    exit /b 1
)

rem --- ставим библиотеки (один раз) ---
%PY% -c "import pyautogui, PIL, pynput" >nul 2>nul
if errorlevel 1 (
    echo Устанавливаю библиотеки...
    %PY% -m pip install --upgrade pyautogui pillow pynput
    if errorlevel 1 (
        echo Не удалось установить библиотеки.
        pause
        exit /b 1
    )
)

rem --- картинка: перетащи её на этот файл или введи путь ---
set "IMG=%~1"
if not defined IMG (
    set /p "IMG=Перетащи картинку в это окно и нажми Enter: "
)
set "IMG=%IMG:"=%"
if not exist "%IMG%" (
    echo Файл не найден: %IMG%
    pause
    exit /b 1
)

set "ARGS="

echo.
echo Где рисуем?
echo   1 - Roblox
echo   2 - Paint / сайт / другое
set "WHERE=1"
set /p "WHERE=Выбери [1]: "
if "%WHERE%"=="1" set "ARGS=--roblox"

echo.
echo Рисунок:
echo   1 - цветной
echo   2 - чёрно-белый
echo   3 - только контуры (чёрные)
set "KIND=1"
set /p "KIND=Выбери [1]: "
if "%KIND%"=="1" (
    set "NCOL=16"
    set /p "NCOL=Сколько цветов? Больше = точнее, но дольше [16]: "
)
if "%KIND%"=="1" set "ARGS=%ARGS% --colors %NCOL%"
if "%KIND%"=="3" set "ARGS=%ARGS% --mode outline"

echo.
echo Холст в игре - сетка из клеток (как в Starving Artists)?
echo Если да - введи размер сетки, например: 32 32
set "GRID="
set /p "GRID=Размер сетки или просто Enter, если холст обычный: "
if defined GRID set "ARGS=%ARGS% --grid %GRID%"
if not defined GRID echo Поставь в игре толщину кисти на 1 больше шага: 3 px.

set "EXTRA="
set /p "EXTRA=Доп. опции (например --step 3 или --delay 0.03), или просто Enter: "

echo.
%PY% draw_image.py "%IMG%" %ARGS% %EXTRA%
echo.
pause

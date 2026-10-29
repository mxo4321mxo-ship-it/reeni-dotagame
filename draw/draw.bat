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

echo.
echo Режим:
echo   1 - заливка + обводка краёв (точнее всего)
echo   2 - только контуры (быстрее)
echo   3 - фото с полутонами
set "MODE=1"
set /p "MODE=Выбери режим [1]: "
set "ARGS="
if "%MODE%"=="2" set "ARGS=--mode outline"
if "%MODE%"=="3" set "ARGS=--dither"

echo.
echo Поставь в программе толщину кисти 2-3 px.
set "EXTRA="
set /p "EXTRA=Доп. опции (например --step 1 или --delay 0.02), или просто Enter: "

echo.
%PY% draw_image.py "%IMG%" %ARGS% %EXTRA%
echo.
pause

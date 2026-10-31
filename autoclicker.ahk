; Автокликер на боковую кнопку мыши (AutoHotkey v1)
; Зажал боковую кнопку - кликает. Отпустил - остановилось.
;
; Выход: Ctrl+Alt+Q  (или правый клик по иконке в трее -> Exit)

#NoEnv
#SingleInstance Force
#MaxHotkeysPerInterval 99000000
#HotkeyInterval 99000000
#KeyHistory 0
ListLines Off
SetBatchLines -1
SetWinDelay -1
SetControlDelay -1
SetMouseDelay -1
Process, Priority, , H

; ---------- НАСТРОЙКА ----------
CPS := 25          ; кликов в секунду (реально работает примерно до 60)
; -------------------------------

Delay := Round(1000 / CPS)
if (Delay < 1)
    Delay := 1

; XButton1 - "назад", обычно ближняя к себе боковая кнопка.
; Если нужна дальняя - замени оба XButton1 на XButton2.
XButton1::
    While GetKeyState("XButton1", "P")
    {
        Click
        DllCall("Sleep", "UInt", Delay)
    }
Return

^!q::ExitApp

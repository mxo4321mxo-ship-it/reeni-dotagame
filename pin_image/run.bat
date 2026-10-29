@echo off
cd /d "%~dp0"
py -m pip install --quiet pillow keyboard
py pin_image.py %*

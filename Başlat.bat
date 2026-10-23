@echo off
chcp 65001 >nul
title BIST Portfoy Danisman
cd /d "%~dp0"
echo Portfoy Danisman baslatiliyor...
python main.py
if errorlevel 1 (
  echo.
  echo Bir hata olustu. Bagimliliklar eksik olabilir; sunu calistir:
  echo    pip install -r requirements.txt
  pause
)

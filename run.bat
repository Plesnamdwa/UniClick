@echo off
title UniClick
cd /d "%~dp0"
echo Menjalankan UniClick...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Aplikasi berhenti dengan error code %ERRORLEVEL%.
    pause
)

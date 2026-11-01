@echo off
title Build Standalone EXE - UniClick
cd /d "%~dp0"
echo ============================================================
echo   Membangun Standalone EXE (PyInstaller)
echo ============================================================
echo.
python -m PyInstaller --noconsole --onefile --name "UniClick" --collect-all customtkinter main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   BERHASIL! File executable tersedia di:
    echo   "%~dp0dist\UniClick.exe"
    echo ============================================================
) else (
    echo.
    echo [ERROR] Terjadi kegagalan saat proses build EXE.
)
pause

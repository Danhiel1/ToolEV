@echo off
chcp 65001 >nul
setlocal
title ToolEV - Đóng gói File EXE Tự Bung

echo.
echo  ======================================================
echo         ĐÓNG GÓI TOOLEV THÀNH 1 FILE EXE TỰ BUNG
echo  ======================================================
echo.

set "PY=python"
if exist "scripts\.venv\Scripts\python.exe" (
    set "PY=scripts\.venv\Scripts\python.exe"
)

"%PY%" build_package.py

echo.
pause

@echo off
setlocal
chcp 65001 >nul
title ToolEV - AI English Learning Platform

echo ========================================================
echo               CHAO MUNG DEN VOI TOOLEV
echo    Tu dong bien Video thanh bai hoc va de thi IELTS
echo ========================================================
echo.

REM 1. Kiem tra Python
python --version >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong tim thay Python tren may tinh cua ban!
    echo Vui long cai dat Python 3.10 tro len tai: https://www.python.org/downloads/
    echo - Luu y: Tich vao muc "Add Python to PATH" khi cai dat
    echo.
    pause
    exit /b 1
)

REM 2. Kiem tra FFmpeg
ffmpeg -version >nul 2>nul
if errorlevel 1 (
    echo [THONG BAO] Chua phat hien FFmpeg tren he thong.
    echo Dang thu tu dong cai dat FFmpeg qua winget...
    winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements >nul 2>nul
    ffmpeg -version >nul 2>nul
    if errorlevel 1 (
        echo [CANH BAO] Khong the tu dong cai FFmpeg.
        echo Pipeline YouTube-only van chay binh thuong.
        echo De dung tinh nang Whisper cho moi loai video, ban hay cai FFmpeg:
        echo   Mo Terminal va go: winget install Gyan.FFmpeg
        echo.
    )
)

REM 3. Kiem tra va Khoi tao Virtual Environment
if not exist "scripts\.venv\Scripts\python.exe" (
    echo [1/3] Dang tao moi truong ao Python scripts\.venv...
    python -m venv scripts\.venv
    if errorlevel 1 (
        echo [LOI] Khong the tao Virtual Environment.
        pause
        exit /b 1
    )
    echo [2/3] Dang cai dat dependencies faster-whisper, yt-dlp, requests...
    scripts\.venv\Scripts\python.exe -m pip install -r scripts\requirements.txt
    if errorlevel 1 (
        echo [LOI] Khong the cai dat thu vien can thiet.
        pause
        exit /b 1
    )
)

REM 4. Tao thu muc output neu chua co
if not exist "output" (
    mkdir output
)

echo.
echo [3/3] Dang khoi dong may chu ToolEV...
echo ========================================================
echo  Server:    http://localhost:8000/all-video.html
echo  Dang mo trinh duyet... Nhan Ctrl + C de dung server
echo ========================================================
echo.

REM 5. Mo trinh duyet
start "" "http://localhost:8000/all-video.html"

REM 6. Chay Server
scripts\.venv\Scripts\python.exe server.py 8000
pause

@echo off
chcp 65001 >nul
setlocal
title ToolEV - AI English Learning Platform

echo.
echo  ======================================================
echo            CHAO MUNG DEN VOI TOOLEV
echo     Tu dong bien Video thanh bai hoc va de thi IELTS
echo  ======================================================
echo.

:: 0. Kiem tra Portable Runtime va Bin
if exist "bin" set "PATH=%~dp0bin;%PATH%"
if exist "runtime\python.exe" (
    set "VENV_PYTHON=%~dp0runtime\python.exe"
    set "SYS_PYTHON=%~dp0runtime\python.exe"
    echo  [OK] Su dung Python Portable san co trong thu muc runtime.
    goto :CHECK_OUTPUT
)

:: 1. Kiem tra Python
python --version >nul 2>nul
if errorlevel 1 (
    py --version >nul 2>nul
    if errorlevel 1 (
        echo  [LOI] Khong tim thay Python tren may tinh cua ban!
        echo  Vui long cai dat Python 3.10 tro len tai: https://www.python.org/downloads/
        echo  * Luu y: Tich vao muc "Add Python to PATH" khi cai dat.
        echo.
        pause
        exit /b 1
    ) else (
        set "SYS_PYTHON=py"
    )
) else (
    set "SYS_PYTHON=python"
)

for /f "tokens=*" %%v in ('%SYS_PYTHON% --version 2^>^&1') do echo  [OK] %%v

:: 2. Kiem tra FFmpeg
ffmpeg -version >nul 2>nul
if errorlevel 1 (
    echo  [THONG BAO] Chua phat hien FFmpeg. Pipeline van chay tot voi YouTube.
) else (
    echo  [OK] FFmpeg san sang.
)

:: 3. Kiem tra Virtual Environment
set "VENV_PYTHON=scripts\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo  [1/2] Dang tao moi truong ao scripts\.venv...
    %SYS_PYTHON% -m venv scripts\.venv
    if not exist "%VENV_PYTHON%" (
        set "VENV_PYTHON=%SYS_PYTHON%"
    ) else (
        echo  [2/2] Dang cai dat dependencies vao .venv...
        "%VENV_PYTHON%" -m pip install -r scripts\requirements.txt
    )
)

:CHECK_OUTPUT
:: 4. Tao thu muc output neu chua co
if not exist "output" mkdir output


:: 5. Kiem tra port 8000
set "PORT=8000"
netstat -aon 2>nul | findstr ":8000 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo  [THONG BAO] May chu ToolEV da dang chay san tren port 8000.
    echo  Dang mo trinh duyet: http://localhost:8000/all-video.html
    start "" "http://localhost:8000/all-video.html"
    echo.
    echo  Nhan phim bat ky de dong cua so nay.
    pause >nul
    exit /b 0
)

echo.
echo  ======================================================
echo  Server:  http://localhost:%PORT%/all-video.html
echo  Dang mo trinh duyet...
echo  Nhan Ctrl + C de dung server
echo  ======================================================
echo.

start "" "http://localhost:%PORT%/all-video.html"
"%VENV_PYTHON%" server.py %PORT%
if errorlevel 1 (
    %SYS_PYTHON% server.py %PORT%
)

pause

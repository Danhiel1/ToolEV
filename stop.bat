@echo off
chcp 65001 >nul
title Dừng ToolEV
echo.
echo  Đang dừng máy chủ ToolEV...
taskkill /F /IM ToolEV.exe >nul 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>nul
)
echo  [OK] Đã dừng toàn bộ dịch vụ ToolEV thành công.
timeout /t 2 >nul

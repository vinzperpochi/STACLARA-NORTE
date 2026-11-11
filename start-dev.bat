@echo off
setlocal
cd /d "%~dp0"
title Sta. Clara Norte - Development Server

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -u dev.py %*
) else (
    python -u dev.py %*
)

set "DEV_EXIT_CODE=%ERRORLEVEL%"
if not "%DEV_EXIT_CODE%"=="0" (
    echo.
    echo The development server stopped. Review the message above.
    echo If port 5000 is already in use, stop the other server first.
    pause
)
exit /b %DEV_EXIT_CODE%

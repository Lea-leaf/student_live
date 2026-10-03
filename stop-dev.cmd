@echo off
REM ===========================================================================
REM  Stop dev services (frees ports 5000 and 5173)
REM  This file is intentionally ASCII-only to avoid codepage problems.
REM ===========================================================================
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-dev.ps1" %*
echo.
echo Press any key to close this window...
pause >nul

@echo off
REM ===========================================================================
REM  Launch dev environment (Flask 5000 + Vite 5173)
REM  Double-click this file, or run it from cmd.
REM
REM  This file is intentionally ASCII-only to avoid codepage problems.
REM  All Chinese text lives in start-dev.ps1 (saved as UTF-8 with BOM).
REM
REM  Extra arguments are forwarded, e.g.:
REM      start-dev.cmd -SkipInit
REM      start-dev.cmd -BackendOnly
REM ===========================================================================
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" %*
echo.
echo Press any key to close this window...
pause >nul

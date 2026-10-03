@echo off
REM ===========================================================================
REM  Initialize database only (create tables + modules + configs + demo data),
REM  then exit without starting any server.
REM
REM  Useful on a fresh machine:  init-db.cmd
REM ===========================================================================
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" -InitOnly %*
echo.
echo Press any key to close this window...
pause >nul

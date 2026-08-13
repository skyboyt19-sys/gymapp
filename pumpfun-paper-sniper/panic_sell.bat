@echo off
REM ===========================================================================
REM  NOTVERKAUF - verkauft alle Token auf der Bot-Wallet.
REM
REM  Dafuer da, wenn der Bot abgestuerzt ist oder ein Verkauf nicht durchging
REM  und noch Token auf der Bot-Wallet liegen.
REM  Fragt vor dem Verkaufen nach.
REM ===========================================================================
setlocal
cd /d "%~dp0"
title NOTVERKAUF (pump.fun Bot-Wallet)

if not exist ".venv\Scripts\python.exe" (
    echo  [Hinweis] Die Umgebung fehlt noch. Bitte zuerst run.bat einmal starten.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" panic_sell.py
echo.
pause
endlocal

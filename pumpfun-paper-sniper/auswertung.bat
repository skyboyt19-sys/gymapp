@echo off
REM ===========================================================================
REM  AUSWERTUNG - liest die trades.csv und zeigt, woran es liegt.
REM  Handelt nichts, aendert nichts. Kann jederzeit laufen, auch waehrend
REM  der Bot in einem anderen Fenster arbeitet.
REM ===========================================================================
setlocal
cd /d "%~dp0"
title Auswertung (pump.fun Sniper)

if not exist ".venv\Scripts\python.exe" (
    echo  [Hinweis] Die Umgebung fehlt noch. Bitte zuerst run.bat einmal starten.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" auswertung.py %*
echo.
pause
endlocal

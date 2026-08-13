@echo off
REM ===========================================================================
REM  Feed-Test: zeigt nur die neuen pump.fun-Launches an. Handelt nichts.
REM  Nutze das, um zu pruefen, ob die Verbindung auf deinem PC funktioniert.
REM ===========================================================================
setlocal
cd /d "%~dp0"
title Feed-Test (pump.fun)

if not exist ".venv\Scripts\python.exe" (
    echo  [Hinweis] Die Umgebung fehlt noch. Bitte zuerst run.bat einmal starten.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" check_feed.py
echo.
pause
endlocal

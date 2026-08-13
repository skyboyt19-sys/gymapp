@echo off
REM ===========================================================================
REM  pump.fun Paper-Sniper - Doppelklick-Starter fuer Windows
REM ---------------------------------------------------------------------------
REM  Dieses Skript macht beim ersten Start alles automatisch:
REM    1. legt eine virtuelle Python-Umgebung (venv) an
REM    2. installiert die noetigen Pakete aus requirements.txt
REM    3. legt eine .env aus .env.example an, falls sie fehlt
REM    4. startet den Bot
REM  Ab dem zweiten Start wird nur noch gestartet (geht dann sofort).
REM ===========================================================================

setlocal
cd /d "%~dp0"

title pump.fun Paper-Sniper (SIMULATION)

echo.
echo  ================================================================
echo   pump.fun PAPER-SNIPER  --  reine Simulation, kein echtes Geld
echo  ================================================================
echo.

REM --- 1) Python vorhanden? -------------------------------------------------
REM  Bewusst mit Sprungmarken statt verschachtelter IF-Bloecke: in Batch wird
REM  %errorlevel% innerhalb eines Klammerblocks schon beim Einlesen ersetzt,
REM  nicht erst beim Ausfuehren - verschachtelte Pruefungen liefern dort
REM  falsche Ergebnisse.
where py >nul 2>nul
if %errorlevel%==0 goto :python_launcher
where python >nul 2>nul
if %errorlevel%==0 goto :python_direkt

echo  [FEHLER] Python wurde nicht gefunden.
echo.
echo  Bitte Python 3.11 oder neuer installieren:
echo    https://www.python.org/downloads/windows/
echo  WICHTIG: beim Installieren den Haken bei
echo    "Add python.exe to PATH"  setzen!
echo.
pause
exit /b 1

:python_launcher
set "PYLAUNCH=py -3"
goto :python_ok

:python_direkt
set "PYLAUNCH=python"

:python_ok

REM --- 2) venv anlegen, falls nicht vorhanden -------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [1/3] Lege virtuelle Umgebung an ^(.venv^) ...
    %PYLAUNCH% -m venv .venv
    if errorlevel 1 (
        echo  [FEHLER] venv konnte nicht angelegt werden.
        pause
        exit /b 1
    )
    echo  [2/3] Installiere Pakete ^(dauert beim ersten Mal 1-2 Minuten^) ...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo  [FEHLER] Installation der Pakete fehlgeschlagen.
        pause
        exit /b 1
    )
) else (
    echo  [1/3] Virtuelle Umgebung gefunden.
    echo  [2/3] Pakete bereits installiert.
)

REM --- 3) .env anlegen, falls nicht vorhanden -------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo  [Info] .env wurde aus .env.example erstellt ^(oeffentliche RPC^).
    )
)

REM --- 4) Bot starten -------------------------------------------------------
echo  [3/3] Starte Bot ... ^(Beenden mit STRG+C^)
echo.
".venv\Scripts\python.exe" -m sniper.main
set "EXITCODE=%errorlevel%"

echo.
echo  ================================================================
echo   Bot beendet ^(Exit-Code %EXITCODE%^).
echo  ================================================================
echo.
pause
endlocal

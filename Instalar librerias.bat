@echo off
rem Revisa e instala las librerias que usa el autopiloto, mostrando el avance.
cd /d "%~dp0programa"
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
    echo  No se encontro Python. Instala Python 3.12 desde https://www.python.org/downloads/
    echo  y marca "Add python.exe to PATH".
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)
%PY% arranque.py --instalar
pause

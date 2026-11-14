@echo off
rem Abre el autopiloto. Antes revisa que esten instaladas las librerias (programa\arranque.py).
cd /d "%~dp0programa"
set "PYW="
where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PYW where pyw >nul 2>nul && set "PYW=pyw"
if not defined PYW where python >nul 2>nul && set "PYW=python"
if not defined PYW where py >nul 2>nul && set "PYW=py"
if not defined PYW (
    echo.
    echo  No se encontro Python en este PC.
    echo  Instala Python 3.12 desde https://www.python.org/downloads/
    echo  y en el instalador marca "Add python.exe to PATH".
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)
start "" %PYW% arranque.py

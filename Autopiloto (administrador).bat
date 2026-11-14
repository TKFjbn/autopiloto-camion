@echo off
rem Igual que Autopiloto.bat pero como administrador (necesario si el juego corre como administrador).
net session >nul 2>&1
if %errorlevel%==0 (
    call "%~dp0Autopiloto.bat"
    exit /b
)
rem Pide permisos y se vuelve a abrir a si mismo. La ruta va en una variable para que no se rompa
rem con espacios, tildes, parentesis o apostrofos.
set "AP_BAT=%~f0"
powershell -NoProfile -Command "Start-Process -FilePath $env:AP_BAT -Verb RunAs"

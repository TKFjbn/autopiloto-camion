@echo off
rem Crea Autopiloto.exe: un lanzador chico que abre el autopiloto sin ventana negra (hace lo mismo que
rem Autopiloto.bat). Usa el compilador de C# que ya trae Windows; no instala nada. Se hace una sola vez:
rem las actualizaciones del programa no lo cambian. No toca el juego ni su carpeta.
cd /d "%~dp0"
set "CSC="
if exist "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not defined CSC if exist "%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not defined CSC goto sin_csc
echo.
echo  Crear Autopiloto.exe
echo  -------------------
echo  Si el juego corre como administrador, el autopiloto tambien tiene que hacerlo
echo  para poder manejar. Si respondes S, Windows pedira permiso cada vez que lo abras.
echo.
choice /c SN /m " Abrir siempre como administrador"
set "MAN=admin"
if errorlevel 2 set "MAN=normal"
if exist "Autopiloto.exe" del /q "Autopiloto.exe" >nul 2>nul
"%CSC%" /nologo /target:winexe /optimize+ /out:"%~dp0Autopiloto.exe" /win32icon:"%~dp0programa\lanzador\autopiloto.ico" /win32manifest:"%~dp0programa\lanzador\%MAN%.manifest" /reference:System.Windows.Forms.dll "%~dp0programa\lanzador\Autopiloto.cs"
if not exist "Autopiloto.exe" goto fallo
echo.
echo  Listo: Autopiloto.exe quedo en esta carpeta.
echo.
choice /c SN /m " Crear un acceso directo en el escritorio"
if errorlevel 2 goto fin
set "AP_EXE=%~dp0Autopiloto.exe"
set "AP_DIR=%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Autopiloto.lnk'); $s.TargetPath=$env:AP_EXE; $s.WorkingDirectory=$env:AP_DIR; $s.IconLocation=$env:AP_EXE+',0'; $s.Save()"
echo  Acceso directo creado en el escritorio.
goto fin

:sin_csc
echo.
echo  No encontre el compilador de C# de Windows (.NET Framework 4).
echo  Sigue usando Autopiloto.bat, funciona igual.
echo.
pause
exit /b 1

:fallo
echo.
echo  No se pudo crear Autopiloto.exe (mira el mensaje de arriba).
echo  Sigue usando Autopiloto.bat, funciona igual.
echo.
pause
exit /b 1

:fin
echo.
echo  Para anclarlo a la barra de tareas: clic derecho en Autopiloto.exe, "Anclar a la barra de tareas".
echo.
pause

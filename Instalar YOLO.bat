@echo off
rem Instala YOLO (opcional, 3.6.0): deteccion de vehiculos y personas delante del camion.
rem Descarga unos 2,5 GB (PyTorch). No toca el juego ni su carpeta.
cd /d "%~dp0programa"
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
    echo  No se encontro Python. Instala Python 3.12 desde https://www.python.org/downloads/
    pause
    exit /b 1
)
echo.
echo  Instalar YOLO (opcional)
echo  ------------------------
echo  Si tienes tarjeta de video NVIDIA (por ejemplo GTX 1660), responde S para instalar PyTorch
echo  con soporte para la tarjeta (mas rapido). Si no, responde N: funciona con el procesador.
echo.
choice /c SN /m " Tienes tarjeta NVIDIA"
if errorlevel 2 goto cpu
echo.
echo  Instalando PyTorch con CUDA (puede tardar varios minutos)...
%PY% -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu121
goto ultra
:cpu
echo.
echo  Instalando PyTorch (procesador)...
%PY% -m pip install --upgrade torch torchvision
:ultra
echo.
echo  Instalando ultralytics (YOLO)...
%PY% -m pip install --upgrade ultralytics
echo.
echo  Probando (la primera vez descarga el modelo yolo11n.pt, unos 6 MB)...
%PY% -c "import vision_yolo as v; print(v.disponible()[1]); v.cargar_modelo('yolo11n.pt'); print('Modelo listo en mi_equipo/yolo.')"
echo.
echo  Listo. En el programa: Experimental, deja prendida la deteccion YOLO y marca la vista YOLO en Conducir.
pause

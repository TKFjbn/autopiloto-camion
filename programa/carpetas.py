"""
Carpetas del autopiloto (2.0.0) y migración desde el orden antiguo.

    Autopiloto/
      Autopiloto.bat
      programa/     el código. Se reemplaza entero al actualizar.
      datos/        lo que se comparte entre jugadores (rutas, grabaciones, trazados).
      mi_equipo/    lo de tu PC: config.json (calibración de pantalla y ajustes),
                    interfaz.json (tema, vista, notificaciones), registro.txt, zonas/.
      viajes/       CSV de cada viaje, incidentes.csv y observaciones.

Todos los módulos trabajan con el directorio actual = carpeta Autopiloto/ (RAIZ).
"""
import json
import os
import shutil
import time

PROGRAMA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PROGRAMA)

DATOS = os.path.join(RAIZ, "datos")
RUTAS = os.path.join(DATOS, "rutas")
GRABACIONES = os.path.join(DATOS, "grabaciones")
TRAZADOS = os.path.join(DATOS, "trazados")
DATOS_INFO = os.path.join(DATOS, "datos.json")

EQUIPO = os.path.join(RAIZ, "mi_equipo")
CONFIG = os.path.join(EQUIPO, "config.json")
INTERFAZ = os.path.join(EQUIPO, "interfaz.json")
REGISTRO = os.path.join(EQUIPO, "registro.txt")
RESPALDOS = os.path.join(EQUIPO, "respaldos")
CAPTURAS_TEMP = os.path.join(EQUIPO, "capturas_temp")   # 2.2.0: capturas de incidentes (se borran al cerrar)
PARA_LLM = os.path.join(EQUIPO, "para_llm")             # 2.2.0: archivos listos para adjuntar a otro LLM

VIAJES = os.path.join(RAIZ, "viajes")

# 3.9.0: trabajo/modo elegido en el menú de inicio (lo pasa arranque.py en AUTOPILOTO_MODO).
# Cada modo distinto del camionero tiene su configuración (calibración del carril, máscara de YOLO, color de la
# ruta…) y su carpeta de viajes; los datos compartibles (rutas, grabaciones) son del camionero.
MODO = (os.environ.get("AUTOPILOTO_MODO") or "camionero").strip().lower() or "camionero"
CONFIG_CAMIONERO = CONFIG
MODOS = os.path.join(DATOS, "modos")              # reglas de cada modo (p. ej. datos/modos/libre.json)
if MODO != "camionero":
    CONFIG = os.path.join(EQUIPO, f"config_{MODO}.json")
    VIAJES = os.path.join(VIAJES, MODO)


def preparar():
    """Crea las carpetas, entra en RAIZ y mueve los archivos del orden antiguo (una sola vez)."""
    for c in (DATOS, RUTAS, GRABACIONES, TRAZADOS, EQUIPO, VIAJES, MODOS):
        os.makedirs(c, exist_ok=True)
    os.chdir(RAIZ)
    preparar_modo()
    movidos = migrar()
    movidos += retirar_obsoletos()
    return movidos


COLOR_RUTA_LIBRE = [[128, 90, 110, 146, 255, 255]]   # 3.9.0: la ruta morada de un punto libre (H ~136)


def preparar_modo():
    """3.9.0: la primera vez en un modo nuevo, su configuración parte de la del camionero (minimapa, ventana,
    teclas, mando) sin lo que depende del vehículo o del modo: calibración del carril y máscara de YOLO."""
    if MODO == "camionero" or os.path.exists(CONFIG):
        return
    base = leer_json(CONFIG_CAMIONERO, None) if os.path.exists(CONFIG_CAMIONERO) else None
    if base is None:
        return                                    # configuracion.cargar crea una por defecto
    base = dict(base)
    if MODO == "libre":
        base["color_ruta_hsv"] = COLOR_RUTA_LIBRE
    cal = dict(base.get("calibracion") or {})
    cal.pop("carril", None)
    base["calibracion"] = cal
    car = dict(base.get("carril") or {})
    car["trapecio"] = None
    base["carril"] = car
    yo = dict(base.get("yolo") or {})
    yo["mascara"] = []
    base["yolo"] = yo
    guardar_json(CONFIG, base)


def retirar_obsoletos():
    """2.3.2: datos/obsoletos.json lista archivos de datos que ya no sirven (grabaciones repetidas o que
    fallaban). Si existen con EXACTAMENTE ese contenido (sha1) se mueven a mi_equipo/respaldos/datos_obsoletos/.
    Nada se borra, y un archivo nuevo con el mismo nombre no se toca."""
    import hashlib
    lista = leer_json(os.path.join(DATOS, "obsoletos.json"), {}).get("archivos") or []
    avisos = []
    for item in lista:
        rel = str(item.get("ruta", "")).replace("\\", "/")
        if not rel or ".." in rel.split("/"):
            continue
        origen = os.path.join(DATOS, *rel.split("/"))
        if not os.path.isfile(origen):
            continue
        try:
            with open(origen, "rb") as fh:
                if hashlib.sha1(fh.read()).hexdigest() != item.get("sha1"):
                    continue
            destino = os.path.join(RESPALDOS, "datos_obsoletos", *rel.split("/"))
            _mover(origen, destino, avisos)
            if item.get("motivo"):
                avisos[-1] += f"  ({item['motivo']})"
        except Exception:  # noqa
            pass
    return avisos


def limpiar_capturas():
    """Borra las capturas temporales de incidentes (al abrir y al cerrar el programa)."""
    try:
        shutil.rmtree(CAPTURAS_TEMP, ignore_errors=True)
    except Exception:  # noqa
        pass


def _mover(origen, destino, avisos):
    if not os.path.exists(origen):
        return
    if os.path.exists(destino):
        base, ext = os.path.splitext(destino)
        destino = f"{base}_antiguo_{time.strftime('%Y%m%d%H%M%S')}{ext}"
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.move(origen, destino)
    avisos.append(f"{os.path.relpath(origen, RAIZ)} -> {os.path.relpath(destino, RAIZ)}")


def migrar():
    """Antes (hasta la v39) todo estaba suelto en la carpeta principal. Lo ordena sin borrar nada.
    Devuelve la lista de movimientos hechos (vacía si no había nada que mover)."""
    avisos = []
    r = lambda *p: os.path.join(RAIZ, *p)          # noqa: E731
    # lo tuyo -> mi_equipo/
    _mover(r("config.json"), CONFIG, avisos) if not os.path.exists(CONFIG) else \
        _mover(r("config.json"), os.path.join(RESPALDOS, "config.json"), avisos)
    for f in os.listdir(RAIZ):
        if f.startswith("config_v") and f.endswith(".json"):
            _mover(r(f), os.path.join(RESPALDOS, f), avisos)
    _mover(r("registro.txt"), REGISTRO, avisos) if not os.path.exists(REGISTRO) else None
    _mover(r("zonas"), os.path.join(EQUIPO, "zonas"), avisos) if not os.path.exists(
        os.path.join(EQUIPO, "zonas")) else None
    _mover(r("captura_calibracion.png"), os.path.join(EQUIPO, "captura_calibracion.png"), avisos)
    _mover(r("rutas.json"), os.path.join(RESPALDOS, "rutas_propias_antiguas.json"), avisos)
    # grabaciones -> datos/grabaciones
    vieja = r("grabaciones")
    if os.path.isdir(vieja):
        for f in os.listdir(vieja):
            _mover(os.path.join(vieja, f), os.path.join(GRABACIONES, f), avisos)
        try:
            os.rmdir(vieja)
        except OSError:
            pass
    # programa viejo suelto -> _version_anterior/ (no se borra, por si acaso)
    anteriores = [f for f in os.listdir(RAIZ)
                  if (f.endswith(".py") or f in ("plantillas_hud.npz", "rutas_base.json", "config_ejemplo.json",
                                                 "requirements.txt")) and os.path.isfile(r(f))]
    for f in anteriores:
        _mover(r(f), r("_version_anterior", f), avisos)
    if os.path.isdir(r("__pycache__")):
        shutil.rmtree(r("__pycache__"), ignore_errors=True)
    return avisos


def leer_json(ruta, defecto=None):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {} if defecto is None else defecto


def guardar_json(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def abrir(ruta):
    """Abre un archivo o carpeta con el programa de Windows que corresponda."""
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        os.startfile(os.path.abspath(ruta))            # noqa
    else:
        subprocess.Popen(["xdg-open", ruta])

"""
Actualizaciones del programa desde GitHub (3.1.0).

  - `consultar()`      pregunta a GitHub cuál es la última versión publicada (release) y trae su texto.
  - `descargar()`      baja el .zip de esa versión.
  - `aplicar()`        instala un .zip (el bajado de GitHub o uno que te pasen): guarda una copia de lo que
                       reemplaza en mi_equipo/respaldos/ y cambia solo programa/ y, si quieres, datos/.

Nunca toca mi_equipo/ (tu calibración, tus preferencias, tus plantillas) ni viajes/, ni los .bat, ni el
launcher o la carpeta del juego. Si algo falla a mitad de camino, deja todo como estaba.

Cómo publicar una versión (para quien mantiene el repositorio): ver LEEME.md → «Publicar una versión».
"""
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

import carpetas
import version

REPO = "TKFjbn/autopiloto-camion"
API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT = 8

RAIZ_ARCHIVOS = ("CAMBIOS.md", "LEEME.md", "PROMPT_CALIBRACION.md", "PUBLICAR.md", "Crear Autopiloto.exe.bat")      # se actualizan junto al programa
NO_TOCAR_EN_PROGRAMA = {"config.json"}                                   # restos de versiones viejas del usuario


class ErrorActualizar(Exception):
    """Error que se le puede mostrar tal cual al usuario."""


# ------------------------------------------------------------------ GitHub
def _abrir(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": f"autopiloto-camion/{version.VERSION}",
                                               "Accept": accept})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _limpiar_version(tag):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(tag or ""))
    return ".".join(m.groups()) if m else None


def consultar(repo=REPO):
    """Última versión publicada: {"version", "titulo", "notas", "zip", "url"}. Lanza ErrorActualizar."""
    try:
        with _abrir(API.format(repo=repo)) as r:
            j = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ErrorActualizar("En GitHub todavía no hay ninguna versión publicada.")
        if e.code in (403, 429):
            raise ErrorActualizar("GitHub no deja consultar ahora (demasiadas consultas). Prueba en un rato.")
        raise ErrorActualizar(f"GitHub respondió {e.code}.")
    except Exception as e:  # noqa
        raise ErrorActualizar(f"No se pudo conectar con GitHub ({e}). ¿Hay internet?")
    v = _limpiar_version(j.get("tag_name")) or _limpiar_version(j.get("name"))
    if not v:
        raise ErrorActualizar("La última versión de GitHub no tiene un número como 3.1.0 en su etiqueta.")
    return {"version": v, "titulo": j.get("name") or j.get("tag_name") or v, "notas": j.get("body") or "",
            "zip": elegir_zip(j), "url": j.get("html_url") or f"https://github.com/{repo}/releases"}


def elegir_zip(release):
    """El .zip adjunto a la versión (autopiloto_camion_X.zip) o, si no hay, el zip automático de GitHub."""
    for a in release.get("assets") or []:
        n = str(a.get("name", "")).lower()
        if n.endswith(".zip") and a.get("browser_download_url"):
            return a["browser_download_url"]
    return release.get("zipball_url")


def hay_nueva(nueva, actual=None):
    return version.tupla(nueva) > version.tupla(actual or version.VERSION)


def descargar(url, destino, progreso=None):
    """Baja `url` a `destino`. `progreso(bytes_bajados, total)` si se da."""
    if not url:
        raise ErrorActualizar("Esa versión no tiene un .zip para bajar.")
    try:
        with _abrir(url, accept="application/octet-stream") as r, open(destino, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            hecho = 0
            while True:
                bloque = r.read(64 * 1024)
                if not bloque:
                    break
                f.write(bloque)
                hecho += len(bloque)
                if progreso:
                    progreso(hecho, total)
    except Exception as e:  # noqa
        raise ErrorActualizar(f"No se pudo bajar la actualización ({e}).")
    return destino


# ------------------------------------------------------------------ zip
def _miembros_seguros(z):
    for n in z.namelist():
        p = n.replace("\\", "/")
        if p.startswith("/") or ".." in p.split("/") or re.match(r"^[A-Za-z]:", p):
            raise ErrorActualizar(f"El .zip trae una ruta insegura ({n}); no lo uso.")
    return z.namelist()


def inspeccionar(ruta_zip):
    """Mira un .zip sin instalarlo: {"prefijo", "programa", "datos", "datos_minimo"} (versiones en texto)."""
    try:
        z = zipfile.ZipFile(ruta_zip)
    except Exception as e:  # noqa
        raise ErrorActualizar(f"No se pudo abrir el .zip ({e}).")
    with z:
        nombres = _miembros_seguros(z)
        cand = [n for n in nombres if n.replace("\\", "/").endswith("programa/version.py")]
        if not cand:
            raise ErrorActualizar("Ese .zip no parece del autopiloto (no tiene programa/version.py).")
        cand.sort(key=lambda n: n.count("/"))
        vp = cand[0].replace("\\", "/")
        prefijo = vp[: -len("programa/version.py")]
        m = re.search(r'VERSION\s*=\s*"([\d.]+)"', z.read(cand[0]).decode("utf-8", "replace"))
        if not m:
            raise ErrorActualizar("No se pudo leer la versión del programa dentro del .zip.")
        datos = datos_min = None
        try:
            dj = json.loads(z.read(prefijo + "datos/datos.json").decode("utf-8"))
            datos, datos_min = dj.get("version"), dj.get("programa_minimo")
        except Exception:  # noqa
            pass
        return {"prefijo": prefijo, "programa": m.group(1), "datos": datos, "datos_minimo": datos_min}


def version_datos_local():
    return carpetas.leer_json(carpetas.DATOS_INFO, {}).get("version")


# ------------------------------------------------------------------ instalar
def _copiar_arbol(origen, destino, omitir=()):
    """Copia los archivos de `origen` sobre `destino` (sin borrar nada de lo que ya hay). Devuelve la lista."""
    copiados = []
    for base, dirs, archivos in os.walk(origen):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(base, origen)
        for a in archivos:
            if a in omitir and rel == ".":
                continue
            d = os.path.normpath(os.path.join(destino, rel, a))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            tmp = d + ".nuevo"
            shutil.copy2(os.path.join(base, a), tmp)
            os.replace(tmp, d)
            copiados.append(os.path.normpath(os.path.join(rel, a)))
    return copiados


def _compilar(carpeta):
    """Comprueba que cada .py tenga sintaxis válida (sin escribir nada)."""
    for base, dirs, archivos in os.walk(carpeta):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for a in archivos:
            if a.endswith(".py"):
                ruta = os.path.join(base, a)
                with open(ruta, "rb") as f:
                    try:
                        compile(f.read(), ruta, "exec")
                    except SyntaxError as e:
                        raise ErrorActualizar(f"El .zip trae un archivo con errores ({a}, línea {e.lineno}); "
                                              "no lo instalo.")


def aplicar(ruta_zip, con_datos=True, permitir_igual=False, log=print, raiz=None):
    """Instala el .zip. Devuelve {"antes", "despues", "respaldo", "archivos", "datos"}.
    `raiz` es la carpeta Autopiloto/ (por defecto la real; las pruebas pasan otra)."""
    raiz = raiz or carpetas.RAIZ
    prog_dir = os.path.join(raiz, "programa")
    datos_dir = os.path.join(raiz, "datos")
    respaldos = os.path.join(raiz, "mi_equipo", "respaldos")
    info = inspeccionar(ruta_zip)
    antes = version.VERSION
    if version.tupla(info["programa"]) < version.tupla(antes):
        raise ErrorActualizar(f"Ese .zip es más viejo ({info['programa']}) que el programa que tienes ({antes}).")
    if version.tupla(info["programa"]) == version.tupla(antes) and not permitir_igual:
        raise ErrorActualizar(f"Ya tienes la versión {antes}.")
    if not version.cumple_minimo_de(info["programa"], info.get("datos_minimo") or "0"):
        raise ErrorActualizar("Los datos de ese .zip necesitan un programa más nuevo que el que trae.")
    usar_datos = bool(con_datos and info.get("datos"))
    sello = time.strftime("%Y%m%d_%H%M%S")
    respaldo = os.path.join(respaldos, f"actualizacion_{sello}_{antes}_a_{info['programa']}")
    n = 1
    while os.path.exists(respaldo):
        n += 1
        respaldo = os.path.join(respaldos, f"actualizacion_{sello}_{antes}_a_{info['programa']}_{n}")
    tmp = tempfile.mkdtemp(prefix="autopiloto_upd_")
    try:
        # 1) extraer lo necesario (programa/, datos/ y los textos)
        with zipfile.ZipFile(ruta_zip) as z:
            _miembros_seguros(z)
            pref = info["prefijo"]
            for n in z.namelist():
                p = n.replace("\\", "/")
                if not p.startswith(pref) or p.endswith("/"):
                    continue
                rel = p[len(pref):]
                if rel.startswith(("programa/", "datos/")) or rel in RAIZ_ARCHIVOS:
                    if "__pycache__" in rel:
                        continue
                    destino = os.path.join(tmp, *rel.split("/"))
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    with z.open(n) as fo, open(destino, "wb") as fd:
                        shutil.copyfileobj(fo, fd)
        if not os.path.isfile(os.path.join(tmp, "programa", "version.py")):
            raise ErrorActualizar("El .zip no trae el programa completo.")
        _compilar(os.path.join(tmp, "programa"))                 # que no traiga errores de sintaxis
        # 2) copia de lo que se va a reemplazar
        os.makedirs(respaldo, exist_ok=True)
        shutil.copytree(prog_dir, os.path.join(respaldo, "programa"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.nuevo"))
        if usar_datos and os.path.isdir(datos_dir):
            shutil.copytree(datos_dir, os.path.join(respaldo, "datos"))
        for a in RAIZ_ARCHIVOS:
            if os.path.isfile(os.path.join(raiz, a)):
                shutil.copy2(os.path.join(raiz, a), os.path.join(respaldo, a))
        log(f"[i] Copia de lo que se reemplaza: {os.path.relpath(respaldo, raiz)}")
        # 3) instalar
        try:
            archivos = _copiar_arbol(os.path.join(tmp, "programa"), prog_dir, omitir=NO_TOCAR_EN_PROGRAMA)
            if usar_datos and os.path.isdir(os.path.join(tmp, "datos")):
                _copiar_arbol(os.path.join(tmp, "datos"), datos_dir)
            for a in RAIZ_ARCHIVOS:
                if os.path.isfile(os.path.join(tmp, a)):
                    shutil.copy2(os.path.join(tmp, a), os.path.join(raiz, a))
        except Exception as e:  # noqa
            log(f"[!] Falló la instalación ({e}): vuelvo a lo anterior.")
            _copiar_arbol(os.path.join(respaldo, "programa"), prog_dir)
            if usar_datos and os.path.isdir(os.path.join(respaldo, "datos")):
                _copiar_arbol(os.path.join(respaldo, "datos"), datos_dir)
            raise ErrorActualizar(f"No se pudo instalar ({e}). Dejé todo como estaba.")
        return {"antes": antes, "despues": info["programa"], "respaldo": respaldo, "archivos": len(archivos),
                "datos": info.get("datos") if usar_datos else None}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def notas_cortas(texto, maximo=1800):
    """Recorta el texto de la versión para mostrarlo en una ventana."""
    t = (texto or "").strip().replace("\r", "")
    return t if len(t) <= maximo else t[:maximo].rsplit("\n", 1)[0] + "\n…"

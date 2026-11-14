"""
Comprobar instalación (2.2.0): revisa que estén las librerías y herramientas que usa el programa.
Solo revisa: no instala nada. Cada resultado trae qué hacer si falta algo.

    resultado = {"nombre": ..., "estado": "ok" | "aviso" | "error", "detalle": ..., "solucion": ...}
"""
import importlib
import os
import platform
import sys
import tempfile
import time

import carpetas


def _r(nombre, estado, detalle="", solucion=""):
    return {"nombre": nombre, "estado": estado, "detalle": detalle, "solucion": solucion}


def _libreria(nombre, modulo, paquete, obligatoria=True, uso=""):
    try:
        m = importlib.import_module(modulo)
        v = getattr(m, "__version__", None) or getattr(m, "VERSION", None) or ""
        return _r(nombre, "ok", f"versión {v}" if v else "instalada")
    except Exception as e:  # noqa
        return _r(nombre, "error" if obligatoria else "aviso",
                  f"no se pudo cargar ({type(e).__name__}: {e})" + (f". {uso}" if uso else ""),
                  f"pip install {paquete}")


def _backend():
    """Lee mi_equipo/config.json tal cual (sin crearlo ni actualizarlo)."""
    cfg = carpetas.leer_json(carpetas.CONFIG, None) if os.path.exists(carpetas.CONFIG) else None
    return cfg, ((cfg or {}).get("control") or {}).get("backend", "teclado")


def _ventanas_visibles():
    """Títulos de las ventanas visibles (solo Windows)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    titulos = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _l):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                titulos.append(b.value)
        return True
    user32.EnumWindows(proto(cb), 0)
    return titulos


def comprobar():
    res = []
    windows = sys.platform == "win32"

    # --- sistema y Python
    res.append(_r("Sistema", "ok" if windows else "error", f"{platform.system()} {platform.release()}",
                  "" if windows else "El programa funciona solo en Windows (lee la pantalla y simula teclas)."))
    v = sys.version_info
    bits = "64 bits" if sys.maxsize > 2 ** 32 else "32 bits"
    ok_py = v >= (3, 9)
    res.append(_r("Python", "ok" if ok_py else "error", f"{v.major}.{v.minor}.{v.micro} ({bits})",
                  "" if ok_py else "Instala Python 3.10 o más nuevo desde python.org (marca \"Add to PATH\")."))

    # --- librerías obligatorias
    res.append(_libreria("numpy", "numpy", "numpy"))
    res.append(_libreria("OpenCV", "cv2", "opencv-python"))
    res.append(_libreria("mss (captura de pantalla)", "mss", "mss"))
    res.append(_libreria("Pillow (imágenes de la interfaz)", "PIL", "pillow"))

    # --- captura de pantalla real
    try:
        import mss
        import numpy as np
        with mss.mss() as sct:
            mon = sct.monitors[1]
            img = np.asarray(sct.grab(mon))
        negra = float(img[..., :3].mean()) < 2
        res.append(_r("Captura de pantalla", "aviso" if negra else "ok",
                      f"{mon['width']}x{mon['height']}" + (" · la captura salió negra" if negra else ""),
                      "Pon el juego en «Ventana sin bordes»: en pantalla completa exclusiva la captura sale negra."
                      if negra else ""))
    except Exception as e:  # noqa
        res.append(_r("Captura de pantalla", "error", f"falló: {e}", "pip install --upgrade mss"))

    # --- módulos del programa
    faltan = []
    for m in ("vision", "entrada", "hud_texto", "pantalla_estado", "grabaciones", "rutas", "velocimetro",
              "calibrar", "notificador"):
        try:
            importlib.import_module(m)
        except Exception as e:  # noqa
            faltan.append(f"{m} ({type(e).__name__}: {e})")
    externo = any("No module named" in f and not any(f"'{m}'" in f for m in ("vision", "entrada", "hud_texto",
                  "pantalla_estado", "grabaciones", "rutas", "velocimetro", "calibrar", "notificador",
                  "configuracion", "carpetas", "version", "zona_muerta", "carril", "condicion")) for f in faltan)
    res.append(_r("Archivos del programa", "error" if faltan else "ok",
                  "faltan o fallan: " + "; ".join(faltan) if faltan else "todos cargan",
                  ("Falta una librería: pip install -r requirements.txt (en la carpeta programa/)." if externo
                   else "Vuelve a copiar la carpeta programa/ completa desde el zip.") if faltan else ""))
    npz = os.path.join(carpetas.PROGRAMA, "plantillas_hud.npz")
    res.append(_r("Plantillas del HUD", "ok" if os.path.exists(npz) else "error",
                  "plantillas_hud.npz encontrado" if os.path.exists(npz) else "falta programa/plantillas_hud.npz",
                  "" if os.path.exists(npz) else "Vuelve a copiar la carpeta programa/ completa desde el zip."))

    # --- mando virtual
    cfg, backend = _backend()
    try:
        import vgamepad as vg
        try:
            pad = vg.VX360Gamepad()
            del pad
            res.append(_r("Mando virtual (vgamepad + ViGEmBus)", "ok", "funciona"
                          + ("" if backend == "mando" else " · ahora usas teclado; el mando es más suave")))
        except Exception as e:  # noqa
            res.append(_r("Mando virtual (vgamepad + ViGEmBus)", "error" if backend == "mando" else "aviso",
                          f"vgamepad está, pero el driver no responde ({e})",
                          "Instala el driver ViGEmBus (github.com/nefarius/ViGEmBus/releases) y reinicia el PC."))
    except Exception:  # noqa
        res.append(_r("Mando virtual (vgamepad + ViGEmBus)", "error" if backend == "mando" else "aviso",
                      "no instalado" + ("" if backend == "mando" else " (opcional: ahora usas teclado)"),
                      "pip install vgamepad   (instala también el driver ViGEmBus)"))

    # --- OCR (zona, calle y "Cargando drogas…")
    try:
        import hud_texto
        lector = hud_texto.LectorTexto()
        if not lector.disponible():
            raise RuntimeError("sin OCR")
        idiomas = []
        try:
            try:
                from winsdk.windows.media.ocr import OcrEngine
            except ImportError:
                from winrt.windows.media.ocr import OcrEngine
            idiomas = [lg.language_tag for lg in OcrEngine.available_recognizer_languages]
        except Exception:  # noqa
            pass
        con_es = any(str(x).lower().startswith("es") for x in idiomas) or lector.nombre == "Tesseract"
        res.append(_r("OCR (zona, calle y cargamento)", "ok" if con_es else "aviso",
                      f"{lector.nombre}" + (f" · idiomas: {', '.join(idiomas)}" if idiomas else ""),
                      "" if con_es else "Agrega el idioma Español en Windows: Configuración → Hora e idioma → "
                                        "Idioma → Agregar un idioma → Español (con «reconocimiento de texto»)."))
    except Exception:  # noqa
        res.append(_r("OCR (zona, calle y cargamento)", "aviso",
                      "no disponible: el programa funciona, pero no lee la zona, la calle ni el cargamento",
                      "pip install winsdk"))

    # --- tu equipo
    if not os.path.exists(carpetas.CONFIG):
        res.append(_r("Calibración", "aviso", "todavía no hay mi_equipo/config.json",
                      "Calibración → Calibrar todo (una vez por resolución)."))
    else:
        try:
            import configuracion
            if cfg is None:
                raise ValueError("archivo vacío o con un error de formato")
            por_defecto = cfg.get("minimapa", configuracion.DEFAULTS["minimapa"]) == configuracion.DEFAULTS["minimapa"] \
                and not cfg.get("calibracion")
            cal = cfg.get("calibracion")
            res.append(_r("Calibración", "aviso" if por_defecto else "ok",
                          "sin calibrar (posición por defecto)" if por_defecto else
                          (f"relativa a la ventana del juego ({cal['ventana'][0]}x{cal['ventana'][1]})" if cal
                           else "calibrada (formato antiguo: se convierte sola con el juego abierto)"),
                          "Calibración → Calibrar todo (automático)." if por_defecto else ""))
            try:
                import ventana
                r = ventana.buscar(cfg.get("ventana_juego") or "Grand Theft Auto")
                res.append(_r("Ventana del juego", "ok" if r else "aviso",
                              f"{r[2]}x{r[3]} en ({r[0]}, {r[1]})" if r else "no está abierta (o no la encuentro)",
                              "" if r else "Abre GTA antes de calibrar o de activar el autopiloto."))
            except Exception:  # noqa
                pass
        except Exception as e:  # noqa
            res.append(_r("Calibración", "error", f"config.json no se puede leer: {e}",
                          "Revisa mi_equipo/config.json o bórralo para empezar de cero (se pierde la calibración)."))

    try:
        import rutas
        import version
        d = rutas.cargar()
        info = carpetas.leer_json(carpetas.DATOS_INFO, {})
        minimo = info.get("programa_minimo")
        ok_d = bool(d["rutas"]) and version.cumple(minimo)
        res.append(_r("Datos (rutas)", "ok" if ok_d else "aviso",
                      f"versión {info.get('version', '?')} · {len(d['rutas'])} recorridos",
                      "" if ok_d else ("Los datos necesitan el programa " + str(minimo) + " o más nuevo."
                                       if not version.cumple(minimo) else "Copia la carpeta datos/ del zip.")))
    except Exception as e:  # noqa
        res.append(_r("Datos (rutas)", "error", f"no se pudieron leer: {e}", "Copia la carpeta datos/ del zip."))

    malas = []
    for c in (carpetas.EQUIPO, carpetas.VIAJES, carpetas.DATOS):
        try:
            os.makedirs(c, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=c, delete=True):
                pass
        except Exception:  # noqa
            malas.append(os.path.relpath(c, carpetas.RAIZ))
    res.append(_r("Carpetas con permiso de escritura", "error" if malas else "ok",
                  "sin permiso: " + ", ".join(malas) if malas else "mi_equipo, viajes y datos",
                  "Saca la carpeta del programa de «Archivos de programa» (por ejemplo, al Escritorio o a "
                  "Documentos)." if malas else ""))

    if windows:
        titulo = (cfg or {}).get("ventana_juego", "Grand Theft Auto")
        try:
            hay = any(titulo.lower() in t.lower() for t in _ventanas_visibles())
            res.append(_r("Ventana del juego", "ok" if hay else "aviso",
                          f"«{titulo}» " + ("encontrada" if hay else "no está abierta"),
                          "" if hay else "Abre el juego y vuelve a comprobar. Si el título es otro, cámbialo "
                                         "en config.json → ventana_juego."))
        except Exception as e:  # noqa
            res.append(_r("Ventana del juego", "aviso", f"no se pudo revisar: {e}"))
        try:
            import ctypes
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            res.append(_r("Permisos de administrador", "ok" if admin else "aviso",
                          "el programa corre como administrador" if admin else "el programa corre sin administrador",
                          "" if admin else "Si el juego corre como administrador, abre «Autopiloto (administrador).bat»: "
                                           "si no, Windows bloquea las teclas simuladas."))
        except Exception:  # noqa
            pass
    return res


def probar_mando(segundos=1.0):
    """Mueve el volante del mando virtual a la derecha y a la izquierda. Devuelve (ok, mensaje)."""
    try:
        import vgamepad as vg
    except Exception:  # noqa
        return False, "vgamepad no está instalado: pip install vgamepad"
    try:
        pad = vg.VX360Gamepad()
        mitad = max(0.2, segundos / 2)
        for x in (0.6, -0.6):
            pad.left_joystick_float(x_value_float=x, y_value_float=0.0)
            pad.update()
            time.sleep(mitad)
        pad.reset()
        pad.update()
        del pad
        return True, "El mando virtual respondió (volante a la derecha y a la izquierda)."
    except Exception as e:  # noqa
        return False, f"El driver ViGEmBus no responde: {e}. Instálalo y reinicia el PC."


def informe(res):
    marca = {"ok": "OK", "aviso": "AVISO", "error": "ERROR"}
    lineas = [f"Comprobación de instalación · {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    for r in res:
        lineas.append(f"[{marca[r['estado']]}] {r['nombre']}: {r['detalle']}"
                      + (f"  -> {r['solucion']}" if r["solucion"] and r["estado"] != "ok" else ""))
    return "\n".join(lineas)


if __name__ == "__main__":
    carpetas.preparar()
    print(informe(comprobar()))

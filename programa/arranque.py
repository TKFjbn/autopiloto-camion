"""
2.7.1: arranque del autopiloto. Lo abren Autopiloto.bat y Autopiloto (administrador).bat.

Antes de abrir la interfaz revisa que estén instaladas las librerías. Si falta alguna, pregunta si
instalarla y la instala con pip. Si el programa no puede arrancar, muestra el error en una ventana y lo
guarda en mi_equipo/error_inicio.txt (antes, con pythonw, simplemente no se abría nada).

Solo usa la biblioteca estándar de Python, para poder funcionar aunque falte todo lo demás.

    python arranque.py              revisa, instala lo que falte (preguntando) y abre la interfaz
    python arranque.py --instalar   solo revisa e instala, sin preguntar, y no abre la interfaz
    python arranque.py --menu       (3.9.0) muestra el menú de trabajos aunque esté «abrir siempre»
    python arranque.py --modo libre (3.9.0) abre directo en ese trabajo
"""
import importlib
import importlib.util
import os
import subprocess
import sys
import traceback

PROGRAMA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PROGRAMA)
ERROR = os.path.join(RAIZ, "mi_equipo", "error_inicio.txt")

# (módulo que se importa, paquete de pip, para qué sirve)
NECESARIAS = [
    ("cv2", "opencv-python", "leer la pantalla"),
    ("numpy", "numpy", "cálculos de imagen"),
    ("mss", "mss", "capturar la pantalla"),
    ("PIL", "pillow", "mostrar imágenes en la interfaz"),
]
RECOMENDADAS = [
    ("vgamepad", "vgamepad", "mando virtual (dirección suave)"),
    ("winsdk", "winsdk", "leer el nombre de la zona y la calle"),
]
# si winsdk no se instala (pasa con Python muy nuevo), el OCR de Windows funciona igual con estos
WINRT = ["winrt-runtime", "winrt-Windows.Media.Ocr", "winrt-Windows.Graphics.Imaging",
         "winrt-Windows.Storage.Streams", "winrt-Windows.Foundation"]

PY_MIN, PY_MAX_PROBADO = (3, 9), (3, 13)
DESCARGA = "https://www.python.org/downloads/"


def hay(modulo):
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def hay_ocr():
    return hay("winsdk") or hay("winrt.windows.media.ocr") or hay("pytesseract")


def faltan():
    nec = [x for x in NECESARIAS if not hay(x[0])]
    rec = [x for x in RECOMENDADAS if not (hay_ocr() if x[0] == "winsdk" else hay(x[0]))]
    return nec, rec


def guardar_error(texto):
    try:
        os.makedirs(os.path.dirname(ERROR), exist_ok=True)
        with open(ERROR, "w", encoding="utf-8") as fh:
            fh.write(f"Python {sys.version}\nEjecutable: {sys.executable}\nCarpeta: {PROGRAMA}\n\n{texto}\n")
    except OSError:
        pass


def _python_consola():
    """pip se corre con python.exe (no pythonw) en una consola visible, para que se vea el avance."""
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            exe = cand
    return exe


def pip_instalar(paquetes, ventana=True):
    """Instala los paquetes. Devuelve True si pip terminó bien."""
    cmd = [_python_consola(), "-m", "pip", "install", "--upgrade", *paquetes]
    kw = {}
    if ventana and os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    try:
        return subprocess.call(cmd, **kw) == 0
    except OSError:
        return False


def instalar(nec, rec, ventana=True):
    """Instala lo que falta. Devuelve la lista de lo que sigue faltando después."""
    if nec:
        pip_instalar([p for _, p, _ in nec], ventana)
    for mod, paq, _ in rec:
        ok = pip_instalar([paq], ventana)
        if mod == "winsdk" and not ok:
            pip_instalar(WINRT, ventana)
    importlib.invalidate_caches()
    n2, r2 = faltan()
    return n2, r2


def aviso_version():
    v = sys.version_info[:2]
    if v < PY_MIN:
        return (f"Tienes Python {v[0]}.{v[1]}, y el autopiloto necesita Python {PY_MIN[0]}.{PY_MIN[1]} o más nuevo.\n"
                f"Instala Python 3.12 desde {DESCARGA} (marca «Add python.exe to PATH»).")
    if v > PY_MAX_PROBADO:
        return (f"Tienes Python {v[0]}.{v[1]}, más nuevo que el probado ({PY_MAX_PROBADO[0]}.{PY_MAX_PROBADO[1]}). "
                f"Si alguna librería no se instala, instala Python 3.12 desde {DESCARGA}.")
    return None


def lista(items):
    return "\n".join(f"  • {p}  ({para})" for _, p, para in items)


def modo_consola():
    """python arranque.py --instalar"""
    av = aviso_version()
    if av:
        print("[!]", av)
    nec, rec = faltan()
    if not nec and not rec:
        print("[i] Está todo instalado.")
        return 0
    print("[i] Instalando:\n" + lista(nec + rec))
    n2, r2 = instalar(nec, rec, ventana=False)
    if n2:
        print("[!] No se pudo instalar:\n" + lista(n2))
        return 1
    if r2:
        print("[!] Opcionales que no se instalaron (el programa abre igual):\n" + lista(r2))
    print("[i] Listo.")
    return 0


def main():
    if "--instalar" in sys.argv:
        sys.exit(modo_consola())

    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:  # noqa  (tkinter viene con Python; si falta, Python se instaló sin él)
        guardar_error("Falta tkinter. Reinstala Python marcando «tcl/tk and IDLE».\n\n" + traceback.format_exc())
        print("Falta tkinter. Reinstala Python marcando «tcl/tk and IDLE».")
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()
    titulo = "Autopiloto"

    av = aviso_version()
    if av and sys.version_info[:2] < PY_MIN:
        messagebox.showerror(titulo, av)
        sys.exit(1)

    nec, rec = faltan()
    if nec or rec:
        texto = ""
        if nec:
            texto += "Faltan librerías que el autopiloto necesita:\n" + lista(nec) + "\n\n"
        if rec:
            texto += "Faltan librerías recomendadas:\n" + lista(rec) + "\n\n"
        if av:
            texto += av + "\n\n"
        texto += "¿Instalarlas ahora? (se abre una ventana con el avance; necesita internet)"
        if messagebox.askyesno(titulo, texto):
            n2, r2 = instalar(nec, rec)
            if n2:
                msg = ("No se pudieron instalar:\n" + lista(n2) +
                       "\n\nAbre cmd en la carpeta «programa» y ejecuta:\n"
                       "  python -m pip install -r requirements.txt\n"
                       "para ver el error." + (f"\n\n{av}" if av else ""))
                guardar_error(msg)
                messagebox.showerror(titulo, msg)
                sys.exit(1)
            if r2:
                messagebox.showwarning(titulo, "No se pudieron instalar (el programa abre igual):\n" + lista(r2))
        elif nec:
            sys.exit(1)

    root.destroy()

    # 3.9.0: menú de trabajos (camionero, libre…); --menu lo muestra siempre, --modo X lo salta
    sys.path.insert(0, PROGRAMA)
    modo = None
    if "--modo" in sys.argv:
        i = sys.argv.index("--modo")
        modo = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    if not modo:
        try:
            import menu_trabajos
            modo = menu_trabajos.elegir(forzar_menu="--menu" in sys.argv)
        except Exception:  # noqa
            guardar_error("Menú de trabajos:\n" + traceback.format_exc())
            modo = "camionero"
        if modo is None:                                 # cerró el menú sin elegir
            sys.exit(0)
    os.environ["AUTOPILOTO_MODO"] = modo

    # abrir la interfaz; cualquier error al arrancar se muestra y se guarda
    try:
        import runpy
        runpy.run_path(os.path.join(PROGRAMA, "interfaz.py"), run_name="__main__")
    except SystemExit:
        raise
    except BaseException:  # noqa
        tb = traceback.format_exc()
        guardar_error(tb)
        try:
            r = tk.Tk()
            r.withdraw()
            ultimas = "\n".join(tb.strip().splitlines()[-6:])
            messagebox.showerror(titulo, "El autopiloto no pudo arrancar:\n\n" + ultimas +
                                 f"\n\nEl error completo quedó en:\n{ERROR}")
            r.destroy()
        except Exception:  # noqa
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

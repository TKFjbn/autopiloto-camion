"""
Notificaciones en pantalla (tipo Discord) encima del juego.

Cada aviso es una ventanita propia del programa: sin bordes, siempre encima, semitransparente.
En Windows se marca como "no activable" y "transparente al ratón": no le quita el foco al juego
ni recibe clics (el juego sigue recibiendo el teclado y el ratón). No toca el juego.

Se ven con el juego en modo ventana o pantalla completa SIN BORDES. En pantalla completa
exclusiva Windows no deja dibujar nada encima.
"""
import sys
import tkinter as tk

ES_WINDOWS = sys.platform.startswith("win")

# tipo -> (color de la franja, icono de texto, nombre para Ajustes)
TIPOS = {
    "autopiloto": ("#2f7fd1", "●", "Autopiloto activado / desactivado"),
    "control": ("#e08a1e", "✋", "Tomaste el control"),
    "etapa": ("#2e9e44", "✔", "Etapas (cargado, descargado, completado, recorrido)"),
    "grabacion": ("#c0392b", "⏺", "Grabaciones (grabar, repetir, guardar)"),
    "problema": ("#e24b4a", "⚠", "Problemas (choque, atasco, condición)"),
    "aviso": ("#d4a017", "ℹ", "Avisos (falso choque, foco, descargado no detectado)"),
    "reporte": ("#8e5cc4", "✎", "Reportes y observaciones"),
    "hito": ("#1f9bb8", "⚑", "Hitos que marcas tú"),
    "calibracion": ("#16a085", "⚙", "Calibración"),
}

DEFECTO = {
    "activas": True,
    "tipos": {k: True for k in TIPOS},
    "esquina": "arriba_derecha",        # arriba_derecha, arriba_izquierda, abajo_derecha, abajo_izquierda
    "pantalla": "juego",                 # juego (la del juego), principal, 1, 2, 3...
    "duracion_seg": 4.0,
    "sonido": "problemas",               # ninguno, problemas, todos
    "tamano": "normal",                  # chico, normal, grande
    "opacidad": 0.92,
    "maximo": 4,                          # avisos a la vez
}

TAMANOS = {"chico": (280, 9, 10), "normal": (340, 10, 12), "grande": (420, 12, 14)}   # ancho, letra, título

if ES_WINDOWS:
    import ctypes
    from ctypes import wintypes
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    GWL_EXSTYLE = -20
    WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
    WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x08000000, 0x8
    try:
        _get_ex = _u32.GetWindowLongPtrW
        _set_ex = _u32.SetWindowLongPtrW
    except AttributeError:  # 32 bits
        _get_ex = _u32.GetWindowLongW
        _set_ex = _u32.SetWindowLongW
    _get_ex.restype = ctypes.c_ssize_t
    _get_ex.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_ex.restype = ctypes.c_ssize_t
    _set_ex.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]


def _no_activable(win):
    """Ventana que no roba el foco ni recibe clics (Windows)."""
    if not ES_WINDOWS:
        return
    try:
        win.update_idletasks()
        hwnd = _u32.GetParent(win.winfo_id()) or win.winfo_id()
        ex = _get_ex(hwnd, GWL_EXSTYLE)
        _set_ex(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
    except Exception:  # noqa
        pass


def monitores():
    """Lista de áreas de trabajo (x0, y0, x1, y1) de cada pantalla. La principal primero."""
    if not ES_WINDOWS:
        return []
    res = []
    try:
        CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                wintypes.LPARAM)

        def cb(hmon, _hdc, _rc, _lp):
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if _u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                w = mi.rcWork
                res.append(((w.left, w.top, w.right, w.bottom), bool(mi.dwFlags & 1)))
            return 1
        _u32.EnumDisplayMonitors(None, None, CB(cb), 0)
    except Exception:  # noqa
        return []
    res.sort(key=lambda x: not x[1])                    # principal primero
    return [r for r, _ in res]


def monitor_del_juego(titulo):
    """Área de trabajo de la pantalla donde está la ventana del juego (por su título)."""
    if not ES_WINDOWS or not titulo:
        return None
    try:
        hallada = []
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _lp):
            if not _u32.IsWindowVisible(hwnd):
                return True
            n = _u32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            _u32.GetWindowTextW(hwnd, buf, n + 1)
            if titulo.lower() in buf.value.lower():
                hallada.append(hwnd)
                return False
            return True
        _u32.EnumWindows(CB(cb), 0)
        if not hallada:
            return None
        hmon = _u32.MonitorFromWindow(hallada[0], 2)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            return (w.left, w.top, w.right, w.bottom)
    except Exception:  # noqa
        return None
    return None


def _sonar(tipo):
    if not ES_WINDOWS:
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONHAND if tipo == "problema" else winsound.MB_ICONASTERISK)
    except Exception:  # noqa
        pass


class Notificador:
    """Muestra avisos apilados en una esquina de la pantalla elegida."""

    def __init__(self, root, ajustes=None, titulo_juego="Grand Theft Auto"):
        self.root = root
        self.titulo_juego = titulo_juego
        self.ajustes = dict(DEFECTO)
        self.configurar(ajustes or {})
        self.visibles = []          # [Toplevel]

    def configurar(self, ajustes):
        a = dict(DEFECTO)
        a.update({k: v for k, v in (ajustes or {}).items() if k != "tipos"})
        a["tipos"] = dict(DEFECTO["tipos"])
        a["tipos"].update((ajustes or {}).get("tipos", {}))
        self.ajustes = a

    def _area(self):
        p = str(self.ajustes.get("pantalla", "juego"))
        mons = monitores()
        if p == "juego":
            r = monitor_del_juego(self.titulo_juego)
            if r:
                return r
            p = "principal"
        if p.isdigit() and mons and 1 <= int(p) <= len(mons):
            return mons[int(p) - 1]
        if mons:
            return mons[0]
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def mostrar(self, tipo, titulo, texto="", forzar=False):
        a = self.ajustes
        if not forzar and (not a.get("activas", True) or not a["tipos"].get(tipo, True)):
            return
        color, icono, _ = TIPOS.get(tipo, TIPOS["aviso"])
        ancho, letra, letra_t = TAMANOS.get(a.get("tamano", "normal"), TAMANOS["normal"])
        try:
            win = tk.Toplevel(self.root)
        except Exception:  # noqa
            return
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", float(a.get("opacidad", 0.92)))
        except Exception:  # noqa
            pass
        cuerpo = tk.Frame(win, bg="#1e1f22", highlightthickness=1, highlightbackground="#3a3c42")
        cuerpo.pack(fill="both", expand=True)
        tk.Frame(cuerpo, bg=color, width=5).pack(side="left", fill="y")
        dentro = tk.Frame(cuerpo, bg="#1e1f22", padx=10, pady=7)
        dentro.pack(side="left", fill="both", expand=True)
        tk.Label(dentro, text=f"{icono}  {titulo}", bg="#1e1f22", fg="#f2f3f5", anchor="w",
                 font=("Segoe UI", letra_t, "bold")).pack(fill="x")
        if texto:
            tk.Label(dentro, text=texto, bg="#1e1f22", fg="#b5bac1", anchor="w", justify="left",
                     wraplength=ancho - 30, font=("Segoe UI", letra)).pack(fill="x")
        _no_activable(win)
        win.update_idletasks()
        self.visibles.append(win)
        while len(self.visibles) > int(a.get("maximo", 4)):
            self._cerrar(self.visibles[0])
        self._ancho = ancho
        self._acomodar(ancho)
        son = a.get("sonido", "problemas")
        if son == "todos" or (son == "problemas" and tipo == "problema"):
            _sonar(tipo)
        ms = int(float(a.get("duracion_seg", 4.0)) * 1000)
        win.after(ms, lambda: self._desvanecer(win, float(a.get("opacidad", 0.92))))

    def _acomodar(self, ancho):
        x0, y0, x1, y1 = self._area()
        esquina = self.ajustes.get("esquina", "arriba_derecha")
        margen, sep = 16, 8
        arriba = esquina.startswith("arriba")
        derecha = esquina.endswith("derecha")
        y = y0 + margen if arriba else y1 - margen
        for win in reversed(self.visibles):              # el más nuevo junto al borde
            try:
                win.update_idletasks()
                h = win.winfo_reqheight()
                x = x1 - margen - ancho if derecha else x0 + margen
                yy = y if arriba else y - h
                win.geometry(f"{ancho}x{h}+{x}+{yy}")
                y = y + h + sep if arriba else y - h - sep
            except Exception:  # noqa
                pass

    def _desvanecer(self, win, alfa):
        if win not in self.visibles:
            return
        alfa -= 0.12
        if alfa <= 0.05:
            self._cerrar(win)
            return
        try:
            win.attributes("-alpha", alfa)
            win.after(40, lambda: self._desvanecer(win, alfa))
        except Exception:  # noqa
            self._cerrar(win)

    def _cerrar(self, win):
        if win in self.visibles:
            self.visibles.remove(win)
        try:
            win.destroy()
        except Exception:  # noqa
            pass
        if self.visibles:
            self._acomodar(getattr(self, "_ancho", 340))

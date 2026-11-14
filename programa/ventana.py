"""
3.0.0: dónde está la ventana del juego en la pantalla.

Solo PREGUNTA a Windows por la posición y el tamaño de la zona de dibujo de la ventana de GTA
(sin la barra de título ni los bordes). No toca el juego ni su memoria.

    rect = buscar("Grand Theft Auto")   ->  (x, y, ancho, alto) en píxeles de pantalla, o None
"""
import os
import time

ES_WINDOWS = os.name == "nt"
CLASE_GTA = "grcWindow"          # clase de la ventana de GTA V (la busca primero)

_dpi_listo = False


def _dpi():
    """Coordenadas en píxeles reales (igual que la captura de pantalla), también con escalado de Windows."""
    global _dpi_listo
    if _dpi_listo or not ES_WINDOWS:
        return
    _dpi_listo = True
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa
            pass


def _ventanas():
    """[(hwnd, clase, titulo)] de las ventanas visibles y no minimizadas."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    out = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            t = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, t, n + 1)
            c = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, c, 256)
            out.append((hwnd, c.value, t.value))
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def _rect_cliente(hwnd):
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 320 or h < 240:
        return None
    return (int(p.x), int(p.y), int(w), int(h))


def buscar(titulo="Grand Theft Auto"):
    """(x, y, ancho, alto) de la zona de dibujo de la ventana del juego, o None si no está abierta."""
    if not ES_WINDOWS:
        return None
    try:
        _dpi()
        vs = _ventanas()
        cand = [v for v in vs if v[1] == CLASE_GTA]
        if not cand and titulo:
            t = titulo.lower()
            # por título, descartando ventanas que suelen llevar el nombre del juego (navegador, este programa)
            cand = [v for v in vs if t in v[2].lower()
                    and not any(x in v[2].lower() for x in ("autopiloto", "chrome", "firefox", "edge", "opera",
                                                             "explorador", "explorer", "discord"))]
        for hwnd, _c, _t in cand:
            r = _rect_cliente(hwnd)
            if r:
                return r
    except Exception:  # noqa
        return None
    return None


class Vigia:
    """Revisa cada `cada_seg` si la ventana se movió o cambió de tamaño."""

    def __init__(self, titulo, cada_seg=2.0):
        self.titulo = titulo
        self.cada = cada_seg
        self.t = 0.0
        self.rect = None

    def revisar(self):
        """Devuelve el rect nuevo si cambió desde la última vez, si no None."""
        ahora = time.monotonic()
        if ahora - self.t < self.cada:
            return None
        self.t = ahora
        r = buscar(self.titulo)
        if r is not None and r != self.rect:
            antes, self.rect = self.rect, r
            return r if antes is not None else None
        return None

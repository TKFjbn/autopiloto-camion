"""
Panel flotante (3.1.0), para jugar con una sola pantalla.

Una tira chica y semitransparente arriba al centro de la pantalla del juego con lo esencial: estado,
velocidad, distancia al punto, condición y, abajo, el aviso más importante (problema o regla activa).

  - No roba el foco ni recibe clics (el juego sigue funcionando igual).
  - Va arriba al centro: el programa lee el minimapa (abajo a la izquierda), el velocímetro y la condición
    (abajo a la derecha) y los carteles del trabajo (al centro), así que ahí no tapa nada que se lea.
  - Se muestra solo cuando el programa está corriendo, si hay UNA sola pantalla (modo «auto»), siempre
    (modo «siempre»), o con la tecla del panel (por defecto F6), que lo prende o apaga a mano.
"""
import tkinter as tk

import notificador

BG, FG, TENUE = "#16181c", "#f2f3f5", "#9aa0aa"
COLORES = {"problema": "#ff6b6b", "aviso": "#f0b232", "regla": "#f0c674"}
ANCHO, ALTO, MARGEN = 400, 50, 6

MODOS = {"auto": "Automático (solo si hay una pantalla)", "siempre": "Siempre que el programa corra",
         "tecla": "Solo con la tecla"}


def _km(m):
    if m is None:
        return "-"
    return f"{float(m) / 1000:.2f} km".replace(".", ",") if float(m) >= 1000 else f"{float(m):.0f} m"


class PanelFlotante:
    def __init__(self, root, prefs, titulo_juego="Grand Theft Auto", n_monitores=None):
        self.root = root
        self.prefs = prefs                       # dict: {"modo": "auto", "opacidad": 0.8}
        self.titulo_juego = titulo_juego
        self._n_monitores = n_monitores          # para pruebas; None = consultar a Windows
        self.win = None
        self.override = None                     # None = según el modo; True/False = lo que pidió la tecla
        self._texto = None
        self._pos = None

    # ------------------------------------------------------------ reglas de visibilidad
    def monitores(self):
        if self._n_monitores is not None:
            return self._n_monitores
        try:
            return len(notificador.monitores())
        except Exception:  # noqa
            return 0

    def debe_verse(self, corriendo):
        if self.override is not None:
            return self.override
        modo = self.prefs.get("modo", "auto")
        if not corriendo:
            return False
        if modo == "siempre":
            return True
        if modo == "auto":
            return self.monitores() == 1
        return False

    def alternar(self, corriendo):
        """La tecla del panel: lo contrario de lo que se ve ahora."""
        self.override = not (self.win is not None)
        self.refrescar(corriendo)

    def reiniciar_override(self):
        self.override = None

    # ------------------------------------------------------------ ventana
    def _crear(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", float(self.prefs.get("opacidad", 0.8)))
        except tk.TclError:
            pass
        w.configure(bg=BG)
        self.l1 = tk.Label(w, text="", bg=BG, fg=FG, font=("Segoe UI", 11, "bold"), anchor="w", padx=10)
        self.l1.pack(fill="x", pady=(3, 0))
        self.l2 = tk.Label(w, text="", bg=BG, fg=TENUE, font=("Segoe UI", 9), anchor="w", padx=10)
        self.l2.pack(fill="x", pady=(0, 3))
        self.win = w
        self._pos = None
        self._colocar()
        notificador._no_activable(w)             # sin foco y sin clics (Windows)

    def _area(self):
        """Área de trabajo donde va el panel: la pantalla del juego o la principal."""
        a = None
        try:
            a = notificador.monitor_del_juego(self.titulo_juego)
            if a is None:
                m = notificador.monitores()
                a = m[0] if m else None
        except Exception:  # noqa
            a = None
        if a is None:
            a = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        return a

    def _colocar(self):
        x0, y0, x1, _y1 = self._area()
        x = int(x0 + (x1 - x0 - ANCHO) / 2)
        y = int(y0 + MARGEN)
        if (x, y) != self._pos:
            self.win.geometry(f"{ANCHO}x{ALTO}+{x}+{y}")
            self._pos = (x, y)

    def cerrar(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:  # noqa
                pass
            self.win = None
            self._texto = None

    # ------------------------------------------------------------ contenido
    @staticmethod
    def contenido(e):
        """(línea 1, línea 2, color de la línea 2) a partir del estado del autopiloto; e=None si no corre."""
        if not e:
            return "Autopiloto detenido", "", TENUE
        estados = {"CONDUCIENDO": "● Conduciendo", "ARRANCANDO": "● Arrancando", "RECUPERANDO": "● Maniobrando",
                   "INACTIVO": "○ Manejas tú", "TERMINADO": "✔ Terminado", "ESPERANDO_RUTA": "… Esperando al juego",
                   "GRABANDO": "● Grabando", "REPRODUCIENDO": "● Repitiendo grabación"}
        cond = e.get("condicion")
        l1 = (f"{estados.get(e.get('estado'), e.get('estado', ''))}   {int(e.get('kmh', 0))}/"
              f"{float(e.get('kmh_obj', 0)):.0f} km/h   {_km(e.get('metros'))}"
              + ("" if cond is None else f"   {cond}%"))
        prob = e.get("problemas") or []
        if prob:
            p = sorted(prob, key=lambda x: 0 if x["nivel"] == "problema" else 1)[0]
            return l1, "⚠ " + p["titulo"], COLORES["problema" if p["nivel"] == "problema" else "aviso"]
        regla = e.get("regla")
        if regla:
            return l1, "Regla: " + regla, COLORES["regla"]
        return l1, (e.get("motivo") or "").capitalize(), TENUE

    def refrescar(self, corriendo, estado=None):
        """Muestra, oculta o actualiza el panel. Se llama desde el bucle de la ventana (~10 veces por segundo)."""
        if not self.debe_verse(corriendo):
            self.cerrar()
            return
        if self.win is None:
            self._crear()
        l1, l2, col = self.contenido(estado if corriendo else None)
        if (l1, l2, col) != self._texto:
            self._texto = (l1, l2, col)
            self.l1.config(text=l1)
            self.l2.config(text=l2[:70] + ("…" if len(l2) > 70 else ""), fg=col)
        self._colocar()

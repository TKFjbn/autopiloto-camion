"""
Mapa de la ruta pequeño para la pestaña Conducir (3.4.0).

- Solo la ruta del tramo actual y el camión: sin reglas, puntos de interés ni edición.
- Rueda = zoom. Con el camión andando lo sigue y ajusta el zoom solo según la velocidad; si se hace zoom a mano,
  se respeta unos segundos y después vuelve al automático.
- Doble clic = abrir la pestaña «Mapa de ruta» en el mismo recorrido y tramo.
"""
import math
import os
import time
import tkinter as tk

import mapa

MANUAL_SEG = 8.0          # cuánto se respeta el zoom hecho a mano
COLOR_RUTA = "#4f545c"
COLOR_HECHO = "#2b2d31"
COLOR_FALTA = "#5865f2"


def _km(m):
    return f"{m / 1000:.2f} km".replace(".", ",") if m >= 1000 else f"{m:.0f} m"


class MapaMini:
    def __init__(self, padre, app, bg="#111214", al_doble_clic=None):
        self.app = app
        self.can = tk.Canvas(padre, bg=bg, highlightthickness=0, cursor="hand2")
        self.al_doble_clic = al_doble_clic
        self.puntos, self.clave = [], None
        self.rec, self.tramo = None, None
        self.zoom, self.cx, self.cy = 1.0, 0.0, 0.0
        self.manual_hasta = 0.0
        self.zoom_manual = None
        self._ultimo_ajuste = None
        self.can.bind("<Configure>", lambda _e: self.dibujar())
        self.can.bind("<MouseWheel>", self._rueda)
        self.can.bind("<Button-4>", lambda e: self._rueda(e, 1))
        self.can.bind("<Button-5>", lambda e: self._rueda(e, -1))
        self.can.bind("<Double-Button-1>", self._doble)

    # ------------------------------------------------------------ qué mostrar
    def _cual(self):
        """(recorrido, tramo, metros o None, rumbo en grados o None, kmh) del camión o de lo elegido en la ventana."""
        ap = self.app.ap
        if ap is not None and not getattr(ap, "terminado", False) and getattr(ap, "tramo", None) in (0, 1, 2):
            try:
                d = ap.dist_fina()
            except Exception:  # noqa
                d = None
            r = getattr(getattr(ap, "rumbo", None), "valor", None)
            return getattr(ap, "recorrido", None), str(ap.tramo), d, r, float(getattr(ap, "kmh", 0) or 0)
        rec = None
        try:
            nombre = self.app.var_recorrido.get()
            arch = dict(self.app.recorridos).get(nombre)
            if arch:
                rec = os.path.splitext(arch)[0]
        except Exception:  # noqa
            pass
        tramo = "1"
        try:
            t = self.app.var_tramo.get()[:1]          # «0 - Ir a cargar», «1 - …», «2 - …»
            tramo = t if t in ("0", "1", "2") else "1"
        except Exception:  # noqa
            pass
        return rec, tramo, None, None, 0.0

    def _archivo(self, rec, tramo):
        if tramo == "0":
            return mapa.ruta_camino()
        return mapa.ruta_archivo(rec) if rec else None

    def _mtime(self, rec, tramo):
        try:
            a = self._archivo(rec, tramo)
            return os.path.getmtime(a) if a and os.path.exists(a) else None
        except Exception:  # noqa
            return None

    def _cargar(self, rec, tramo):
        clave = (rec, tramo)
        ahora = time.time()
        if clave == self.clave:
            if ahora - getattr(self, "_t_mtime", 0.0) < 3.0:
                return
            self._t_mtime = ahora                # cada 3 s: ¿se armó o cambió el mapa (al detener un viaje)?
            if self._mtime(rec, tramo) == getattr(self, "_mt", None):
                return
        self._t_mtime = ahora
        self._mt = self._mtime(rec, tramo)
        self.clave = clave
        self.rec, self.tramo = rec, tramo
        self.puntos = []
        try:
            if tramo == "0":
                c = mapa.cargar_camino() or {}
                self.puntos = c.get("pts") or []
            elif rec:
                m = mapa.cargar(rec)
                self.puntos = ((m or {}).get("tramos") or {}).get(tramo) or []
        except Exception as e:  # noqa
            print(f"[i] Mapa (Conducir): no se pudo leer el mapa: {e}")
        self._ultimo_ajuste = None

    def recargar(self):
        self.clave = None
        self.actualizar()

    # ------------------------------------------------------------ vista
    def _a_pantalla(self, x, y):
        w, h = max(1, self.can.winfo_width()), max(1, self.can.winfo_height())
        return (x - self.cx) * self.zoom + w / 2, -(y - self.cy) * self.zoom + h / 2

    def _ajustar_todo(self):
        w, h = max(1, self.can.winfo_width()), max(1, self.can.winfo_height())
        if (w, h, self.clave) == self._ultimo_ajuste or len(self.puntos) < 2:
            return
        xs, ys = [p[1] for p in self.puntos], [p[2] for p in self.puntos]
        self.cx, self.cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        ancho, alto = max(30.0, max(xs) - min(xs)), max(30.0, max(ys) - min(ys))
        self.zoom = 0.88 * min(w / ancho, h / alto)
        self._ultimo_ajuste = (w, h, self.clave)

    def _rueda(self, e, delta=None):
        d = delta if delta is not None else e.delta
        self.zoom = max(0.01, min(20.0, self.zoom * (1.25 if d > 0 else 0.8)))
        self.zoom_manual = self.zoom
        self.manual_hasta = time.time() + MANUAL_SEG
        self._ultimo_ajuste = ("manual",)
        self.dibujar()

    def _doble(self, _e):
        if self.al_doble_clic:
            self.al_doble_clic(self.rec, self.tramo)

    # ------------------------------------------------------------ dibujo
    def actualizar(self):
        """Lo llama la ventana unas 4 veces por segundo mientras la vista está a la vista."""
        rec, tramo, d, rumbo, kmh = self._cual()
        self._cargar(rec, tramo)
        self.d, self.rumbo, self.kmh = d, rumbo, kmh
        self.dibujar()

    def dibujar(self):
        c = self.can
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        if len(self.puntos) < 2:
            c.create_text(w / 2, h / 2, fill="#80848e", font=("Segoe UI", 9), justify="center", width=w - 20,
                          text="Sin mapa de este tramo todavía.\n(Se arma solo con un viaje con «Rumbo exacto».)"
                          if self.rec or self.tramo == "0" else "Elige el recorrido para ver su mapa.")
            return
        d = getattr(self, "d", None)
        p_cam = mapa.punto_en(self.puntos, d) if d is not None else None
        ahora = time.time()
        if p_cam is not None:
            # sigue al camión; zoom según la velocidad (~6 s de camino en la mitad corta de la vista)
            self.cx, self.cy = p_cam[0], p_cam[1]
            if ahora < self.manual_hasta and self.zoom_manual:
                self.zoom = self.zoom_manual
            else:
                metros = max(220.0, min(1400.0, getattr(self, "kmh", 0) / 3.6 * 6 * 2 + 180))
                objetivo = min(w, h) / metros
                self.zoom += (objetivo - self.zoom) * 0.25
        elif ahora >= self.manual_hasta:
            self._ajustar_todo()
        pts = [self._a_pantalla(p[1], p[2]) for p in self.puntos]
        c.create_line(*[v for p in pts for v in p], fill=COLOR_RUTA, width=6, capstyle="round", joinstyle="round")
        if p_cam is not None:
            hecho = [self._a_pantalla(x, y) for x, y in mapa.tramo_entre(self.puntos, self.puntos[0][0], d)]
            falta = [self._a_pantalla(x, y) for x, y in mapa.tramo_entre(self.puntos, d, self.puntos[-1][0])]
            if len(hecho) >= 2:
                c.create_line(*[v for p in hecho for v in p], fill=COLOR_HECHO, width=6, capstyle="round")
            if len(falta) >= 2:
                c.create_line(*[v for p in falta for v in p], fill=COLOR_FALTA, width=6, capstyle="round",
                              joinstyle="round")
        # inicio y punto de llegada
        x0, y0 = pts[0]
        c.create_oval(x0 - 4, y0 - 4, x0 + 4, y0 + 4, fill="#80848e", outline="")
        xf, yf = pts[-1]
        c.create_rectangle(xf - 6, yf - 6, xf + 6, yf + 6, fill="#da373c", outline="#ffffff", width=2)
        if p_cam is not None:
            x, y, ang = p_cam
            ang = math.radians(self.rumbo) if self.rumbo is not None else ang
            sx, sy = self._a_pantalla(x, y)
            L = 13
            tri = [(sx + L * math.sin(ang), sy - L * math.cos(ang)),
                   (sx + 7 * math.sin(ang + 2.5), sy - 7 * math.cos(ang + 2.5)),
                   (sx + 7 * math.sin(ang - 2.5), sy - 7 * math.cos(ang - 2.5))]
            c.create_polygon(*[v for q in tri for v in q], fill="#ffffff", outline="#000000", width=2)
            c.create_text(8, h - 8, anchor="sw", fill="#b5bac1", font=("Segoe UI", 9),
                          text=f"{_km(d)} al punto")
        c.create_text(w - 8, h - 8, anchor="se", fill="#4e5058", font=("Segoe UI", 8),
                      text="rueda = zoom · doble clic = editar")

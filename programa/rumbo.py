"""
Rumbo exacto del camión (2.4.0, experimental).

El minimapa de GTA gira con la cámara. Dos fuentes:
  1. La "N" del norte, que recorre el borde del minimapa: su ángulo visto desde el CENTRO del minimapa da el
     rumbo absoluto (0 = norte, 90 = este...). En los costados es precisa; en las 4 esquinas se pierde precisión
     (la N queda "atascada" en la esquina) y a veces la tapa un ícono (el destino morado).
  2. Cuánto gira el dibujo del minimapa de un cuadro al siguiente (alrededor de la flecha del jugador): da el giro
     relativo, continuo, aunque la N no se vea.
Se combinan: el giro relativo lleva el rumbo cuadro a cuadro y la N lo corrige cuando se ve bien en un costado.
"""
import math
import os

import cv2
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
ESCALA_PLANTILLA = 0.977          # escala del minimapa (min(w,h)/176) de la captura de la que salió la plantilla


def dif_ang(a, b):
    """a - b en grados, entre -180 y 180."""
    return (a - b + 180.0) % 360.0 - 180.0


def region_ampliada(cfg_minimapa, margen_px):
    m = cfg_minimapa
    return {"x": int(m["x"]) - margen_px, "y": int(m["y"]) - margen_px,
            "w": int(m["w"]) + 2 * margen_px, "h": int(m["h"]) + 2 * margen_px}


class Rumbo:
    def __init__(self, cfg):
        m = cfg["minimapa"]
        self.w, self.h = int(m["w"]), int(m["h"])
        self.esc = min(self.w, self.h) / 176.0
        rc = cfg.get("rumbo", {})
        self.margen = int(round(rc.get("margen_px", 14) * self.esc))
        self.umbral = rc.get("umbral_n", 0.6)
        self.peso_n = rc.get("peso_n", 0.35)
        self.esquina_px = rc.get("esquina_px", 14) * self.esc
        j = cfg.get("jugador", {"x": self.w / 2, "y": self.h * 0.75})
        self.jx, self.jy = float(j["x"]), float(j["y"])
        p = cv2.imread(os.path.join(_DIR, "plantilla_norte.png"), cv2.IMREAD_GRAYSCALE)
        if p is None:
            raise RuntimeError("falta programa/plantilla_norte.png")
        f = self.esc / ESCALA_PLANTILLA
        if abs(f - 1) > 0.05:
            p = cv2.resize(p, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        self.plantilla = p
        self.region = region_ampliada(m, self.margen)
        self.hist_prev = None
        self._mascara = None
        self.bins = 360                  # medio grado por casilla (orientaciones de 0 a 180°)
        self.valor = None             # rumbo estimado (grados)
        self.fuente = "-"
        self.n = None                 # última N vista: (rumbo, puntaje, esquina)
        self._n_cons = []             # lecturas de N recientes para arrancar o resincronizar

    # ------------------------------------------------------------ la N
    def buscar_n(self, img_ampliada):
        """(rumbo, puntaje, en_esquina) o None. img_ampliada = minimapa con margen alrededor (BGR)."""
        g = cv2.cvtColor(img_ampliada, cv2.COLOR_BGR2GRAY) if img_ampliada.ndim == 3 else img_ampliada
        th, tw = self.plantilla.shape[:2]
        if g.shape[0] < th or g.shape[1] < tw:
            return None
        r = cv2.matchTemplate(g, self.plantilla, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx < self.umbral:
            return None
        nx = loc[0] + tw / 2.0 - self.margen          # en coordenadas del minimapa
        ny = loc[1] + th / 2.0 - self.margen
        borde = 8 * self.esc
        cerca_x = nx < borde or nx > self.w - borde
        cerca_y = ny < borde or ny > self.h - borde
        if not (cerca_x or cerca_y):
            return None                               # la N siempre está en el borde: otra cosa blanca
        cx, cy = self.w / 2.0, self.h / 2.0
        ang = math.degrees(math.atan2(nx - cx, -(ny - cy)))    # hacia dónde queda el norte en pantalla
        en_esquina = (nx < self.esquina_px or nx > self.w - self.esquina_px) and \
                     (ny < self.esquina_px or ny > self.h - self.esquina_px)
        return ((-ang) % 360.0, float(mx), en_esquina)

    # ------------------------------------------------------------ giro del dibujo del minimapa
    def _histograma(self, img_minimapa):
        """Histograma de la orientación de los bordes (calles) del minimapa. Si el mapa gira, el histograma se
        corre; si el camión solo avanza, casi no cambia."""
        g = cv2.cvtColor(img_minimapa, cv2.COLOR_BGR2GRAY) if img_minimapa.ndim == 3 else img_minimapa
        g = cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        if self._mascara is None or self._mascara.shape != mag.shape:
            h, w = mag.shape
            yy, xx = np.mgrid[0:h, 0:w]
            ok = ((xx - self.jx) ** 2 + (yy - self.jy) ** 2) > (14 * self.esc) ** 2      # sin la flecha
            borde = int(4 * self.esc)
            ok[:borde, :] = ok[-borde:, :] = ok[:, :borde] = ok[:, -borde:] = False
            self._mascara = ok
        sel = self._mascara & (mag > 8)
        if sel.sum() < 200:
            return None
        ang = (np.degrees(np.arctan2(gy[sel], gx[sel])) % 180.0)
        nb = self.bins
        hist = np.bincount((ang * nb / 180.0).astype(int) % nb, weights=mag[sel], minlength=nb).astype(np.float64)
        k = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
        hist = np.convolve(np.concatenate([hist[-4:], hist, hist[:4]]), k, mode="valid")
        hist -= hist.mean()
        n = np.linalg.norm(hist)
        return hist / n if n > 0 else None

    def giro_relativo(self, img_minimapa):
        """Grados que giró el camión desde el cuadro anterior (+ = a la derecha), o None si no se puede medir."""
        h = self._histograma(img_minimapa)
        prev, self.hist_prev = self.hist_prev, h
        if h is None or prev is None:
            return None
        nb = self.bins
        corr = np.real(np.fft.ifft(np.fft.fft(h) * np.conj(np.fft.fft(prev))))
        k = int(np.argmax(corr))
        if corr[k] < 0.5:
            return None                            # el mapa cambió demasiado (zoom, pantalla tapada)
        y0, y1, y2 = corr[(k - 1) % nb], corr[k], corr[(k + 1) % nb]
        den = y0 - 2 * y1 + y2
        sub = 0.5 * (y0 - y2) / den if den != 0 else 0.0
        desp = ((k + sub + nb / 2) % nb) - nb / 2   # bins, -nb/2..nb/2
        grados = desp * 180.0 / nb
        if abs(grados) > 30:
            return None
        return -grados

    # ------------------------------------------------------------ combinación
    def actualizar(self, img_ampliada, img_minimapa=None):
        n = self.buscar_n(img_ampliada) if img_ampliada is not None else None
        d = self.giro_relativo(img_minimapa) if img_minimapa is not None else None
        self.n = n
        if self.valor is not None and d is not None and abs(d) < 25:
            self.valor = (self.valor + d) % 360.0
            self.fuente = "giro"
        if n is not None:
            rn, _p, esquina = n
            if self.valor is None:
                if not esquina:
                    self._n_cons = (self._n_cons + [rn])[-3:]
                    if len(self._n_cons) == 3 and max(abs(dif_ang(x, rn)) for x in self._n_cons) < 10:
                        self.valor, self.fuente = rn, "N"
            else:
                diff = dif_ang(rn, self.valor)
                if esquina:
                    # en la esquina la N solo dice "entre tal y tal"; corrige apenas si está muy lejos
                    if abs(diff) > 30:
                        self.valor = (self.valor + 0.1 * diff) % 360.0
                elif abs(diff) > 40:
                    # muy distinto: resincronizar si la N lo confirma 3 veces
                    self._n_cons = (self._n_cons + [rn])[-3:]
                    if len(self._n_cons) == 3 and max(abs(dif_ang(x, rn)) for x in self._n_cons) < 10:
                        self.valor, self.fuente = rn, "N"
                else:
                    self._n_cons = []
                    self.valor = (self.valor + self.peso_n * diff) % 360.0
                    self.fuente = "N"
        return self.valor

    def texto(self):
        if self.valor is None:
            return "-"
        nombres = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
        return f"{self.valor:.0f}° {nombres[int((self.valor + 22.5) // 45) % 8]}"

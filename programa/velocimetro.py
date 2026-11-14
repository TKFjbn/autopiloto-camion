"""
Lectura del velocímetro del HUD (texto amarillo tipo "50 KM/h").

No necesita Tesseract: dibuja las cifras 0-9 con Arial (la fuente del HUD) y
compara cada cifra de la pantalla con esas plantillas.
- Si no hay texto amarillo -> 0 km/h (el HUD lo oculta cuando el camión está parado).
- Si hay texto pero no se entiende -> None (el autopiloto usa el último valor bueno).
"""
import os
import time

import cv2
import numpy as np

FUENTES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
TAM = (20, 30)  # ancho, alto normalizado de cada cifra


def _normalizar(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None, 1.0
    rec = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    aspecto = rec.shape[1] / rec.shape[0]
    rec = cv2.resize(rec, TAM, interpolation=cv2.INTER_AREA)
    rec -= rec.mean()
    n = np.linalg.norm(rec)
    return (rec / n if n > 0 else rec), aspecto


def _plantillas():
    from PIL import Image, ImageDraw, ImageFont
    ruta = next((f for f in FUENTES if os.path.exists(f)), None)
    fuente = ImageFont.truetype(ruta, 64) if ruta else ImageFont.load_default()
    res = {}
    for d in "0123456789KMh/km":
        img = Image.new("L", (80, 90), 0)
        ImageDraw.Draw(img).text((8, 4), d, fill=255, font=fuente)
        res[d] = _normalizar(np.array(img) > 127)
    return res


class Velocimetro:
    def __init__(self, cfg_vel):
        self.cfg = cfg_vel
        self.plantillas = _plantillas()
        self.ultimo = 0
        self.t_ultimo = 0.0
        self.captura = None
        self.t_cero_desde = None

    # --------------------------------------------------------------
    def mascara(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        r = self.cfg["color_hsv"]
        return cv2.inRange(hsv, np.array(r[:3], np.uint8), np.array(r[3:], np.uint8))

    def _clasificar(self, mask):
        vec, asp = _normalizar(mask)
        if vec is None:
            return None, 0
        if asp < self.cfg.get("aspecto_max_uno", 0.42):
            return "1", 0.9       # trazo muy estrecho: es un "1" (la plantilla no lo distingue bien)
        mejor, mejor_s = None, -1
        for d, (tpl, asp_t) in self.plantillas.items():
            s = float((vec * tpl).sum()) - 0.6 * abs(asp - asp_t)
            if s > mejor_s:
                mejor, mejor_s = d, s
        return mejor, mejor_s

    def leer_imagen(self, img):
        """Devuelve (kmh | None, detalle)."""
        mask = self.mascara(img)
        n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
        blobs = []
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if a >= 15 and h >= 8:
                blobs.append((x, y, w, h, i))
        if not blobs:
            return 0, "sin texto (0 km/h)"
        blobs.sort()
        alto = np.max([b[3] for b in blobs])
        # El número son las cifras del principio; se corta en la primera letra (K de KM/h)
        # o en un hueco muy grande. (El "1" deja mucho hueco a su derecha: no cortar por eso.)
        texto, peor, fin_prev = "", 1.0, None
        for x, y, w, h, i in blobs:
            if h < 0.6 * alto:          # basura pequeña
                continue
            if fin_prev is not None and x - fin_prev > 0.9 * alto:
                break
            d, s = self._clasificar(lab[y:y + h, x:x + w] == i)
            if d is None or not d.isdigit():
                break
            if s < self.cfg.get("confianza_min", 0.45):
                return None, f"cifra dudosa ({d}, {s:.2f})"
            texto += d
            peor = min(peor, s)
            fin_prev = x + w
        if not texto or len(texto) > 3:
            return None, f"texto raro '{texto}'"
        return int(texto), f"'{texto}' conf {peor:.2f}"

    # --------------------------------------------------------------
    def leer(self):
        """Lee de la pantalla (región configurada) con filtro anti-saltos."""
        if self.captura is None:
            import mss
            r = self.cfg["region"]
            self.sct = mss.mss()
            self.captura = {"left": r["x"], "top": r["y"], "width": r["w"], "height": r["h"]}
        img = cv2.cvtColor(np.asarray(self.sct.grab(self.captura)), cv2.COLOR_BGRA2BGR)
        v, _ = self.leer_imagen(img)
        ahora = time.time()
        # un 0 repentino yendo rápido suele ser un fallo de lectura: exigir que dure
        if v == 0 and self.ultimo > 12:
            self.t_cero_desde = self.t_cero_desde or ahora
            if ahora - self.t_cero_desde < 0.8:
                return self.ultimo
        else:
            self.t_cero_desde = None
        if v is not None:
            # descartar saltos imposibles: más de 35 km/h entre dos lecturas cercanas,
            # salvo que se repita (entonces es real)
            if abs(v - self.ultimo) > 35 and ahora - self.t_ultimo < 1.0:
                if getattr(self, "sospechoso", None) == v:
                    self.sospechoso = None
                else:
                    self.sospechoso = v
                    return self.ultimo
            if v > self.cfg.get("kmh_max_creible", 160):
                return self.ultimo
            self.ultimo, self.t_ultimo = v, ahora
        return self.ultimo

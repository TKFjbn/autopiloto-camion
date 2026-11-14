"""
Detección del carril en la imagen del juego (vista delantera).

Busca las líneas pintadas (blancas y amarillas) en la zona de la calzada delante
del camión, separa las del lado izquierdo y derecho, y calcula dónde está el
centro del carril respecto al camión.

  desvio (en anchos de carril): + = el centro del carril está a la DERECHA del camión
  confianza: 0..1 (1 = se ven bien las dos líneas y el ancho es coherente)

No necesita nada más que OpenCV. Funciona en primera persona; de noche, con las luces, la amarilla se reconoce por su color.
"""
import math

import cv2
import numpy as np


class DetectorCarrilIPM:
    """
    Vista desde arriba (perspectiva inversa): se calibra un trapecio con las 4 esquinas
    del carril (cerca-izq, lejos-izq, lejos-der, cerca-der) en coordenadas de pantalla,
    yendo centrado en una recta. En la vista enderezada el carril ocupa x=60..140 de 200.
    """
    W, H, XL, XR = 200, 300, 60, 140

    def __init__(self, cfg_carril):
        self.cfg = cfg_carril
        t = np.array(cfg_carril["trapecio"], np.float32)
        dst = np.array([[self.XL, self.H], [self.XL, 0], [self.XR, 0], [self.XR, self.H]], np.float32)
        # zona de pantalla que se necesita capturar (lo que cae dentro de la vista de 200x300)
        Minv = cv2.getPerspectiveTransform(dst, t)
        esquinas = np.array([[[0, 0]], [[self.W, 0]], [[0, self.H]], [[self.W, self.H]]], np.float32)
        src = cv2.perspectiveTransform(esquinas, Minv).reshape(-1, 2)
        x0, y0 = np.floor(src.min(axis=0)).astype(int)
        x1, y1 = np.ceil(src.max(axis=0)).astype(int)
        self.caja = (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        self.M = cv2.getPerspectiveTransform(t - np.array([x0, y0], np.float32), dst)
        self.xl, self.xr = float(self.XL), float(self.XR)
        self.centro_ref = cfg_carril.get("centro_ref", (self.XL + self.XR) / 2)
        self.desvio_prev, self.conf_prev = 0.0, 0.0
        self.sct = None
        self.lineas = DetectorCarril(cfg_carril)     # reutiliza la máscara de líneas

    def capturar(self, pantalla=None):
        """Devuelve la zona de pantalla necesaria. Si se pasa una captura completa, la recorta."""
        x, y, w, h = self.caja
        if pantalla is not None:
            H_, W_ = pantalla.shape[:2]
            out = np.zeros((h, w, 3), np.uint8)
            xa, ya, xb, yb = max(0, x), max(0, y), min(W_, x + w), min(H_, y + h)
            if xb > xa and yb > ya:
                out[ya - y:yb - y, xa - x:xb - x] = pantalla[ya:yb, xa:xb]
            return out
        if self.sct is None:
            import mss
            self.sct = mss.mss()
        img = np.asarray(self.sct.grab({"left": x, "top": y, "width": w, "height": h}))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def mascaras(self, zona):
        """Máscara general de líneas y máscara solo de la amarilla (por color, sirve de noche:
        con las luces la amarilla casi no es más clara que el asfalto, pero sí tiene otro tono)."""
        c = self.cfg
        m = self.lineas.mascara_lineas(zona)
        hsv = cv2.cvtColor(zona, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        B, G, R = (zona[..., i].astype(np.int16) for i in range(3))
        # "amarillez": cuánto más rojo/verde que azul tiene el píxel, comparado con su entorno
        # (de noche el asfalto se ve azulado y la amarilla apenas se aclara)
        d = (np.minimum(R, G) - B).astype(np.float32)
        d_rel = d - cv2.blur(d, (21, 21))
        amar = (H >= c.get("amarillo_h_min", 10)) & (H <= c.get("amarillo_h_max", 45)) \
            & (S >= c.get("amarillo_sat_min", 20)) & (V >= c.get("amarillo_v_min", 35)) \
            & (d_rel >= c.get("amarillo_dif_rel", 14))
        am = amar.astype(np.uint8) * 255
        m = m | am
        if c.get("bordillo_rojo", True):
            rojo = ((H <= 8) | (H >= 165)) & (S >= c.get("rojo_sat_min", 110)) & (V >= c.get("rojo_v_min", 30))
            m = m | (rojo.astype(np.uint8) * 255)
        return m, am          # sin "abrir": la amarilla lejana mide 1-2 px; lo suelto lo filtra la búsqueda de rectas

    def _linea(self, bandas, cerca_de, radio, umbral):
        """Busca una línea casi vertical cerca de 'cerca_de': un pico en cada franja horizontal,
        y solo vale si la mayoría de las franjas coinciden (lo diagonal, como el limpiaparabrisas,
        no coincide). Devuelve (x, calidad 0..1) o None."""
        a, b = int(max(0, cerca_de - radio)), int(min(self.W, cerca_de + radio))
        if b <= a:
            return None
        xs = []
        for h in bandas:
            seg = h[a:b]
            k = int(np.argmax(seg))
            if seg[k] >= umbral:
                xs.append(a + k)
        n = len(bandas)
        if len(xs) < max(2, n - 1):
            return None
        med = float(np.median(xs))
        tol = self.cfg.get("ipm_recta_tol_px", 8)
        buenos = [x for x in xs if abs(x - med) <= tol]
        if len(buenos) < max(2, n - 1):
            return None
        return float(np.mean(buenos)), len(buenos) / n

    def detectar(self, zona):
        c = self.cfg
        m, am = self.mascaras(zona)
        top = cv2.warpPerspective(m, self.M, (self.W, self.H), flags=cv2.INTER_NEAREST)
        top_am = cv2.warpPerspective(am, self.M, (self.W, self.H), flags=cv2.INTER_NEAREST)
        vista = cv2.warpPerspective(zona, self.M, (self.W, self.H))
        y0 = int(self.H * c.get("ipm_desde_rel", 0.3))
        filas = top[y0:]                                            # la parte cercana (más fiable)
        hist = (filas > 0).sum(axis=0).astype(np.float32)
        hist = cv2.GaussianBlur(hist.reshape(1, -1), (1, 9), 0).ravel() if hist.size else hist
        n = int(c.get("ipm_franjas", 4))
        bandas = []
        for f in np.array_split(filas, n, axis=0):
            hb = (f > 0).sum(axis=0).astype(np.float32)
            bandas.append(cv2.GaussianBlur(hb.reshape(1, -1), (1, 5), 0).ravel())
        umbral = c.get("ipm_pixeles_min", 18) / n
        ancho_cal = self.XR - self.XL
        ancho = getattr(self, "ancho", float(ancho_cal))
        radio = c.get("ipm_busqueda_px", 22)

        def buscar(actual, calibrado):
            return self._linea(bandas, actual, radio, umbral) or self._linea(bandas, calibrado, radio * 1.6, umbral)

        L, R = buscar(self.xl, self.XL), buscar(self.xr, self.XR)

        def es_amarilla(x):
            a, b = int(max(0, x - 4)), int(min(self.W, x + 5))
            tot = (filas[:, a:b] > 0).sum()
            return tot > 0 and (top_am[y0:, a:b] > 0).sum() >= 0.5 * tot

        am_l = L is not None and es_amarilla(L[0])
        am_r = R is not None and es_amarilla(R[0])
        conf = 0.0
        coherente = L is not None and R is not None and 0.6 * ancho_cal <= R[0] - L[0] <= 1.4 * ancho_cal
        if coherente:
            self.xl, self.xr, conf = L[0], R[0], 1.0
            self.ancho = 0.9 * ancho + 0.1 * (R[0] - L[0])
        else:
            if L is not None and R is not None:             # anchos raros: quedarse con la mejor
                if (L[1] + 0.1 * am_l) >= (R[1] + 0.1 * am_r):
                    R = None
                else:
                    L = None
            # una sola línea clara y recta: sirve, con menos confianza (más si es la amarilla)
            una = c.get("conf_una_linea", 0.65)
            if L is not None:
                self.xl, self.xr = L[0], L[0] + ancho
                conf = una * L[1] + (0.05 if am_l else 0.0)
            elif R is not None:
                self.xl, self.xr = R[0] - ancho, R[0]
                conf = una * R[1] + (0.05 if am_r else 0.0)
            else:
                # sin líneas: volver poco a poco a la posición calibrada
                self.xl += (self.XL - self.xl) * 0.1
                self.xr += (self.XR - self.xr) * 0.1
        if conf > 0:
            desvio = ((self.xl + self.xr) / 2 - self.centro_ref) / max(1.0, self.xr - self.xl)
            if self.conf_prev > 0.5 and abs(desvio - self.desvio_prev) > 0.3:
                conf *= 0.3                                   # salto brusco: desconfiar
            s = c.get("suavizado", 0.5)
            self.desvio_prev = s * self.desvio_prev + (1 - s) * desvio
        self.conf_prev = 0.7 * self.conf_prev + 0.3 * conf
        return {"desvio": self.desvio_prev, "confianza": self.conf_prev,
                "xl": self.xl if conf and L is not None else None,
                "xr": self.xr if conf and R is not None else None,
                "izq": None if L is None else ("amarilla" if am_l else "linea"),
                "der": None if R is None else ("amarilla" if am_r else "linea"),
                "vista": vista, "top": top, "top_am": top_am, "hist": hist}


def dibujar_ipm(res, det):
    vis = res["vista"].copy()
    vis[res["top"] > 0] = (0, 140, 255)
    if res.get("top_am") is not None:
        vis[res["top_am"] > 0] = (0, 255, 255)
    h, w = vis.shape[:2]
    cr = int(det.centro_ref)
    cv2.line(vis, (cr, h - 40), (cr, h - 1), (255, 255, 255), 2)
    for x in (res["xl"], res["xr"]):
        if x is not None:
            cv2.line(vis, (int(x), 0), (int(x), h - 1), (0, 255, 0), 1)
    hist = res["hist"]
    if hist is not None and hist.size:
        mx = max(1.0, float(hist.max()))
        for x in range(w):
            cv2.line(vis, (x, h - 1), (x, h - 1 - int(40 * hist[x] / mx)), (255, 0, 255), 1)
    vis = cv2.resize(vis, (w * 2, h * 2), interpolation=cv2.INTER_NEAREST)
    txt = f"carril {res['desvio']:+.2f}  conf {res['confianza']:.2f}"
    cv2.putText(vis, txt, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
    cv2.putText(vis, txt, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    if "izq" in res:
        for i, (lado, v) in enumerate((("izq", res["izq"]), ("der", res["der"]))):
            t2 = f"{lado}: {v if v else 'no se ve'}"
            col = (0, 255, 0) if v else (0, 0, 255)
            cv2.putText(vis, t2, (6, 44 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
            cv2.putText(vis, t2, (6, 44 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1)
    return vis


class DetectorCarril:
    def __init__(self, cfg_carril):
        self.cfg = cfg_carril
        self.ancho_prev = None          # ancho de carril (px) en la fila de referencia
        self.desvio_prev = 0.0
        self.conf_prev = 0.0
        self.sct = None

    # ------------------------------------------------------------------
    def capturar(self):
        if self.sct is None:
            import mss
            r = self.cfg["region"]
            self.sct = mss.mss()
            self.mon = {"left": r["x"], "top": r["y"], "width": r["w"], "height": r["h"]}
        img = np.asarray(self.sct.grab(self.mon))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def mascara_lineas(self, roi):
        c = self.cfg
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        # contraste local: las líneas son más claras que el asfalto que las rodea
        fondo = cv2.blur(V, (31, 31)).astype(np.int16)
        claro = V.astype(np.int16) > fondo + c.get("contraste_min", 22)
        asfalto = fondo < c.get("asfalto_v_max", 150)        # las marcas están sobre asfalto (oscuro)
        blanco = claro & (S < c.get("blanco_sat_max", 70)) & asfalto
        amarillo = (H >= 12) & (H <= 40) & (S > 90) & (V > 90) & claro & asfalto
        m = (blanco | amarillo).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        return m

    def detectar(self, img):
        """img = región capturada (la calzada delante del camión)."""
        c = self.cfg
        h, w = img.shape[:2]
        m = self.mascara_lineas(img)
        lineas = cv2.HoughLinesP(m, 1, np.pi / 180, threshold=c.get("hough_umbral", 15),
                                 minLineLength=int(h * 0.10), maxLineGap=int(h * 0.35))
        y_ref = h - 1
        cx = c.get("centro_x_rel", 0.5) * w
        izq, der = [], []
        segs = []
        if lineas is not None:
            for x1, y1, x2, y2 in np.asarray(lineas).reshape(-1, 4):
                if y1 == y2:
                    continue
                if y2 < y1:
                    x1, y1, x2, y2 = x2, y2, x1, y1
                dxdy = (x2 - x1) / float(y2 - y1)          # cuánto se mueve x al bajar 1 px
                ang = abs(math.degrees(math.atan(dxdy)))
                if ang < c.get("angulo_min", 15) or ang > c.get("angulo_max", 75):
                    continue                                  # horizontales (pasos de cebra) o verticales raras
                x_ref = x2 + dxdy * (y_ref - y2)
                largo = math.hypot(x2 - x1, y2 - y1)
                # perspectiva: las líneas del carril apuntan al horizonte, cerca del centro
                y_hor = c.get("horizonte_rel", -0.6) * h
                x_hor = x2 + dxdy * (y_hor - y2)
                if abs(x_hor - c.get("fuga_x_rel", 0.5) * w) > c.get("fuga_tolerancia_rel", 0.3) * w:
                    continue
                segs.append((x1, y1, x2, y2))
                if dxdy < 0 and x_ref < cx + w * 0.1:
                    izq.append((x_ref, largo))
                elif dxdy > 0 and x_ref > cx - w * 0.1:
                    der.append((x_ref, largo))

        def mas_cercana(cands, lado):
            if not cands:
                return None
            # la línea más cercana al camión por ese lado (ponderando largo)
            if lado < 0:
                return max(cands, key=lambda t: t[0] + 0.15 * t[1])[0]
            return min(cands, key=lambda t: t[0] - 0.15 * t[1])[0]

        xl, xr = mas_cercana(izq, -1), mas_cercana(der, 1)
        ancho_min, ancho_max = c.get("ancho_rel_min", 0.25) * w, c.get("ancho_rel_max", 1.3) * w
        conf, centro = 0.0, None
        if xl is not None and xr is not None and ancho_min <= xr - xl <= ancho_max:
            ancho = xr - xl
            self.ancho_prev = ancho if self.ancho_prev is None else 0.8 * self.ancho_prev + 0.2 * ancho
            centro, conf = (xl + xr) / 2, 1.0
        elif self.ancho_prev is not None and (xl is not None or xr is not None):
            # solo una línea: suponer el ancho de carril de los últimos fotogramas
            centro = (xl + self.ancho_prev / 2) if xl is not None else (xr - self.ancho_prev / 2)
            conf = 0.5
        if centro is None:
            self.conf_prev *= 0.7
            return {"desvio": self.desvio_prev, "confianza": self.conf_prev, "xl": None, "xr": None,
                    "segs": segs, "mask": m}
        ancho = self.ancho_prev or (xr - xl)
        desvio = (centro - cx) / max(1.0, ancho)
        # rechazar saltos bruscos (otra línea, sombra) salvo que se repitan
        if self.conf_prev > 0.5 and abs(desvio - self.desvio_prev) > 0.35:
            conf *= 0.3
        s = c.get("suavizado", 0.5)
        self.desvio_prev = s * self.desvio_prev + (1 - s) * desvio
        self.conf_prev = 0.6 * self.conf_prev + 0.4 * conf
        return {"desvio": self.desvio_prev, "confianza": self.conf_prev, "xl": xl, "xr": xr,
                "segs": segs, "mask": m}


def dibujar(img, res, cfg):
    vis = img.copy()
    vis[res["mask"] > 0] = (0, 200, 255)
    for x1, y1, x2, y2 in res["segs"]:
        cv2.line(vis, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 255), 2)
    h, w = img.shape[:2]
    cx = int(cfg.get("centro_x_rel", 0.5) * w)
    cv2.line(vis, (cx, h - 25), (cx, h - 1), (255, 255, 255), 2)
    for x, col in ((res["xl"], (0, 255, 0)), (res["xr"], (0, 255, 0))):
        if x is not None:
            cv2.circle(vis, (int(x), h - 4), 6, col, -1)
    txt = f"carril desvio {res['desvio']:+.2f}  conf {res['confianza']:.2f}"
    cv2.putText(vis, txt, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
    cv2.putText(vis, txt, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return vis

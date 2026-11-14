"""Notificaciones del trabajo de camionero (encima del minimapa):

  "Trabajo de camionero / Acción necesaria" (subtítulo NARANJA):
      "El camión ha sido cargado, llévalo al punto de entrega..."   -> cargado
      "El camión ha sido descargado, ahora tienes que regresarlo."  -> descargado
      (sin palabra verde: aviso de inicio del trabajo)              -> accion
  "Trabajo de camionero / Trabajo completado" (subtítulo VERDE)     -> completado

Se reconocen por los colores (no hace falta OCR). "cargado" y "descargado" se distinguen por
el largo de la palabra verde. Si hay OCR disponible, el texto lo confirma."""
import cv2
import numpy as np


def region(cfg, mon_left=0, mon_top=0):
    m = cfg["minimapa"]
    r = cfg.get("hud_texto", {}).get("region_notificacion", [-0.1, -1.1, 1.15, -0.02])
    w, h = m.get("w_real", m["w"]), m.get("h_real", m["h"])     # 3.0.0: tamaño real en pantalla
    x, y = m["x"] - mon_left, m["y"] - mon_top
    return (int(x + r[0] * w), int(y + r[1] * h), int(x + r[2] * w), int(y + r[3] * h))


def _lineas(m):
    rows = np.nonzero(m.sum(1) >= 3)[0]
    if not len(rows):
        return []
    g, s, pr = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - pr > 3:
            g.append((s, pr))
            s = y
        pr = y
    g.append((s, pr))
    out = []
    for a, b in g:
        c = np.nonzero(m[a:b + 1].sum(0))[0]
        out.append({"y0": int(a), "y1": int(b), "x0": int(c.min()), "x1": int(c.max()),
                    "px": int(m[a:b + 1].sum())})
    return out


def detectar(reg, tam=1.0):
    """Devuelve {"tipo": ..., "img": recorte} o None.
    tam (3.0.0): tamaño del HUD respecto al de referencia (1.0 = minimapa de 180 px de alto); los mínimos de
    píxeles se ajustan con él, así vale para cualquier resolución."""
    a = max(0.3, tam) ** 2                       # los mínimos cuentan píxeles (área)
    if reg is None or reg.size == 0:
        return None
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    H, S, V = (hsv[..., i].astype(np.int16) for i in range(3))
    W = reg.shape[1]
    corte = int(0.22 * W)                     # a la izquierda está la foto del contacto
    naranja = ((H >= 18) & (H <= 28) & (S > 70) & (V > 170))
    verde = ((H >= 54) & (H <= 70) & (S > 45) & (V > 140))
    blanco = ((S < 45) & (V > 190))
    for m in (naranja, verde, blanco):
        m[:, :corte] = False
    ln = [l for l in _lineas(naranja) if l["x1"] - l["x0"] >= 0.25 * W and l["px"] >= 120 * a]
    lv = [l for l in _lineas(verde) if l["px"] >= 60 * a]

    def titulo_encima(l):
        # debe haber texto blanco ("Trabajo de camionero") justo encima del subtítulo
        alto = max(6 * tam, l["y1"] - l["y0"] + 1)
        zona = blanco[max(0, l["y0"] - int(2 * alto)):l["y0"], l["x0"]:l["x0"] + int(0.4 * W)]
        return zona.sum() >= 40 * a

    if ln:
        sub = ln[0]
        if not titulo_encima(sub):
            return None
        ancho_sub = sub["x1"] - sub["x0"]
        palabras = [l for l in lv if l["y0"] > sub["y1"]]
        if not palabras:
            tipo = "accion"
        else:
            p = palabras[0]
            tipo = "descargado" if (p["x1"] - p["x0"]) > 0.49 * ancho_sub else "cargado"
        return {"tipo": tipo, "img": reg}
    largos = [l for l in lv if l["x1"] - l["x0"] >= 0.45 * W]
    if largos:
        l = largos[0]
        # el ícono verde "$" va en la línea del título: buscar el título blanco cerca del inicio
        zona = blanco[max(0, l["y0"] - int(25 * tam)):l["y0"] + int(20 * tam), l["x0"]:l["x0"] + int(0.45 * W)]
        if zona.sum() >= 60 * a:
            return {"tipo": "completado", "img": reg}
    return None


def confirmar_con_texto(tipo, texto):
    """Si hay OCR: corrige el tipo con el texto leído."""
    t = (texto or "").lower()
    if "complet" in t:
        return "completado"
    if "descarg" in t:
        return "descargado"
    if "cargad" in t:
        return "cargado"
    return tipo

"""Condición del camión: el "NN%" con el ícono del motor, abajo a la derecha del HUD.

Se lee con plantillas de Arial (como el velocímetro), sin instalar nada. A veces el juego
muestra más de 100 % (fallo del juego): se registra tal cual."""
import cv2
import numpy as np

from velocimetro import _normalizar, FUENTES

_PL = None


def _plantillas():
    global _PL
    if _PL is None:
        import os
        from PIL import Image, ImageDraw, ImageFont
        ruta = next((f for f in FUENTES if os.path.exists(f)), None)
        fuente = ImageFont.truetype(ruta, 64) if ruta else ImageFont.load_default()
        _PL = {}
        for d in "0123456789%":
            img = Image.new("L", (90, 90), 0)
            ImageDraw.Draw(img).text((8, 4), d, fill=255, font=fuente)
            _PL[d] = _normalizar(np.array(img) > 127)
    return _PL


def region(cfg, mon_left=0, mon_top=0):
    """3.0.0: el "NN%" está abajo a la DERECHA (junto al velocímetro), así que se ubica respecto a la región
    del velocímetro (esquina inferior derecha, en unidades de su alto) y no del minimapa: así vale para
    cualquier proporción de pantalla."""
    rv = cfg.get("velocimetro", {}).get("region")
    if rv:
        r = cfg.get("hud_texto", {}).get("region_condicion_vel", [-1.92, -0.07, 1.30, 1.04])
        xd, yb, u = rv["x"] + rv["w"] - mon_left, rv["y"] + rv["h"] - mon_top, float(rv["h"])
        return (int(xd + r[0] * u), int(yb + r[1] * u), int(xd + r[2] * u), int(yb + r[3] * u))
    m = cfg["minimapa"]
    r = cfg.get("hud_texto", {}).get("region_condicion", [6.55, 0.80, 7.2, 1.14])
    w, h = m.get("w_real", m["w"]), m.get("h_real", m["h"])
    x, y = m["x"] - mon_left, m["y"] - mon_top
    return (int(x + r[0] * w), int(y + r[1] * h), int(x + r[2] * w), int(y + r[3] * h))


def leer(reg):
    """reg: recorte BGR. Devuelve el porcentaje (int) o None."""
    if reg is None or reg.size == 0:
        return None
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 2] > 170) & (hsv[..., 1] < 60)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    altos = [st[i] for i in range(1, n) if st[i][4] >= 12 and 8 <= st[i][3] <= 0.7 * reg.shape[0]]
    if not altos:
        return None
    # banda de texto: la de las cifras (componentes altos y estrechos alineados abajo)
    # cifras: componentes más altos que anchos (el ícono del motor es ancho)
    cifras = [a for a in altos if a[2] <= a[3]] or altos
    alto = int(max(a[3] for a in cifras))
    base = int(max(a[1] + a[3] for a in cifras))
    top = max(0, base - alto)
    banda = mask[top:base + 1]
    col = banda.sum(0)
    trozos, x = [], 0
    while x < len(col):
        if col[x] > 0:
            a = x
            while x < len(col) and col[x] > 0:
                x += 1
            trozos.append((a, x))
        x += 1
    pl = _plantillas()
    clas = []
    for a, z in trozos:
        g = banda[:, a:z]
        if g.sum() < 6:
            continue
        vec, asp = _normalizar(g > 0)
        if vec is None:
            continue
        if asp < 0.33:
            clas.append(("1", 0.9, a, z))
            continue
        mejor, ms = None, -9
        for d, (tpl, asp_t) in pl.items():
            sc = float((vec * tpl).sum()) - 0.6 * abs(asp - asp_t)
            if sc > ms:
                mejor, ms = d, sc
        clas.append((mejor, ms, a, z))
    for k, (d, sc, a, z) in enumerate(clas):
        if d == "%" and sc > 0.15:
            cif, j = "", k - 1
            while j >= 0 and clas[j][0].isdigit() and clas[j][1] > 0.4 and len(cif) < 3:
                if clas[j + 1][2] - clas[j][3] > alto:
                    break
                cif = clas[j][0] + cif
                j -= 1
            if cif:
                v = int(cif)
                return v if 0 <= v <= 300 else None
    return None

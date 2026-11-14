"""
Reconoce en la pantalla del juego los avisos del trabajo de camionero:
  - menú "CARGAR CAMIÓN" (elegir el cargamento)
  - barra de progreso "Cargando ... / Descargando camión..." (amarilla, en un panel oscuro al centro)
Y en el minimapa:
  - el marcador de destino (círculo rojo con flecha negra hacia abajo)

Solo usa proporciones de la pantalla, así que vale para distintas resoluciones.
"""
import cv2
import numpy as np


def _rel(img, x0, y0, x1, y1):
    h, w = img.shape[:2]
    return img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def detectar(pantalla):
    """pantalla: captura completa (BGR). Devuelve {'menu': bool, 'barra': bool, 'progreso': 0..1 o None}."""
    out = {"menu": False, "barra": False, "progreso": None}

    # --- barra de progreso: panel oscuro al centro con una barra amarilla horizontal que
    #     SIEMPRE empieza en el borde izquierdo de la barra (así no se confunde con luces)
    panel = _rel(pantalla, 0.32, 0.29, 0.68, 0.46)
    ph, pw = panel.shape[:2]
    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
    oscuro = (hsv[..., 2] < 50).mean()
    amarillo = ((hsv[..., 0] >= 18) & (hsv[..., 0] <= 34) & (hsv[..., 1] > 110) &
                (hsv[..., 2] > 150)).astype(np.uint8)
    if oscuro > 0.45 and amarillo.any():
        n, lab, st, _ = cv2.connectedComponentsWithStats(amarillo, 8)
        for k in range(1, n):
            x, y, w, h, a = st[k]
            cy = (y + h / 2) / ph
            if (0.50 <= cy <= 0.82 and h <= ph * 0.14 and w >= pw * 0.025 and w >= 2.5 * h
                    and 0.06 * pw <= x <= 0.13 * pw and a >= 0.5 * w * h):
                out["barra"] = True
                x_ini, x_fin = pw * 0.095, pw * 0.905
                out["progreso"] = float(np.clip((x + w - x_ini) / (x_fin - x_ini), 0, 1))
                break

    # --- menú "CARGAR CAMIÓN": gran panel oscuro al centro + botón rojo "Cerrar" abajo al centro
    centro = _rel(pantalla, 0.27, 0.25, 0.73, 0.76)
    hc = cv2.cvtColor(centro, cv2.COLOR_BGR2HSV)
    oscuro_c = (hc[..., 2] < 60).mean()
    boton = _rel(pantalla, 0.46, 0.735, 0.54, 0.795)
    hb = cv2.cvtColor(boton, cv2.COLOR_BGR2HSV)
    rojo = (((hb[..., 0] <= 8) | (hb[..., 0] >= 170)) & (hb[..., 1] > 150) & (hb[..., 2] > 140)).mean()
    if oscuro_c > 0.30 and rojo > 0.20:
        out["menu"] = True
    return out


def _rodeado(rojo, cx, cy, r, n=16, minimo=0.8):
    """¿Hay rojo alrededor del punto en casi todas las direcciones? (círculo, no un trozo de ruta)"""
    H, W = rojo.shape
    hits = 0
    for k in range(n):
        ang = 2 * np.pi * k / n
        ok = False
        for rr in (r * 0.7, r * 0.85, r):
            x = int(round(cx + rr * np.cos(ang)))
            y = int(round(cy + rr * np.sin(ang)))
            if 0 <= x < W and 0 <= y < H and rojo[y, x]:
                ok = True
                break
        hits += ok
    return hits >= minimo * n


def _disco_rojo(rojo, hsv):
    """Centro de un disco rojo de radio >= ~4.5 px (la línea de la ruta mide ~5 px de ancho, o sea
    radio ~2.5) rodeado en su mayor parte por un borde oscuro. None si no hay."""
    H, W = rojo.shape
    esc = min(H, W) / 176.0
    # rellenar la V negra de dentro (si no, el disco no parece "grueso")
    lleno = cv2.morphologyEx((rojo > 0).astype(np.uint8), cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    dt = cv2.distanceTransform(lleno, cv2.DIST_L2, 3)
    r_min = 4.3 * esc
    if dt.max() < r_min:
        return None
    oscuro = hsv[..., 2] < 90
    mejor = None
    cand = np.argwhere(dt >= r_min)
    # agrupar candidatos cercanos: quedarnos con el máximo de cada zona
    usados = np.zeros_like(rojo, bool)
    for y, x in cand[np.argsort(-dt[cand[:, 0], cand[:, 1]])]:
        if usados[y, x]:
            continue
        rr = float(dt[y, x])
        usados[max(0, y - int(rr) - 2):y + int(rr) + 3, max(0, x - int(rr) - 2):x + int(rr) + 3] = True
        if rr > 12 * esc:           # demasiado grande para ser el marcador
            continue
        if x - rr < 4 or y - rr < 4 or x + rr > W - 5 or y + rr > H - 5:
            continue                # punto lejano dibujado en el borde del minimapa: no sirve para llegar
        # borde: anillo justo por fuera del disco
        n, osc, roj = 32, 0, 0
        for k in range(n):
            ang = 2 * np.pi * k / n
            hit_o = hit_r = False
            for d in (rr + 0.5, rr + 1.0, rr + 1.5, rr + 2.0, rr + 2.5):
                xx, yy = int(round(x + d * np.cos(ang))), int(round(y + d * np.sin(ang)))
                if not (0 <= xx < W and 0 <= yy < H):
                    continue
                if oscuro[yy, xx]:
                    hit_o = True
                    break
                if lleno[yy, xx]:
                    hit_r = True
            osc += hit_o
            roj += (hit_r and not hit_o)
        # casi todo el borde oscuro; el resto puede ser la línea roja que entra (un tramo)
        if osc >= 0.55 * n and osc + roj >= 0.7 * n and roj <= 0.3 * n:
            if mejor is None or rr > mejor[2]:
                mejor = (int(x), int(y), rr)
    return None if mejor is None else (mejor[0], mejor[1])


def marcador_destino(minimapa):
    """Busca el marcador de destino (círculo rojo con flecha negra) en el minimapa.
    Devuelve (x, y) en píxeles del minimapa o None."""
    hsv = cv2.cvtColor(minimapa, cv2.COLOR_BGR2HSV)
    rojo = (((hsv[..., 0] <= 8) | (hsv[..., 0] >= 172)) & (hsv[..., 1] > 140) & (hsv[..., 2] > 140)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(rojo, 8)
    mejor = None
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 25 or w < 6 or h < 6:
            continue
        aspecto = w / float(h)
        relleno = a / float(w * h)
        if 0.7 <= aspecto <= 1.4 and 0.45 <= relleno <= 0.95:     # redondo (con hueco de la flecha)
            # la flecha negra dentro: píxeles oscuros en el centro del círculo
            cx, cy = int(cen[i][0]), int(cen[i][1])
            zona = hsv[max(0, cy - h // 4):cy + h // 4 + 1, max(0, cx - w // 4):cx + w // 4 + 1, 2]
            if zona.size and (zona < 80).mean() > 0.15 and _rodeado(rojo, cx, cy, (w + h) / 4.0) \
                    and x > 0 and y > 0 and x + w < rojo.shape[1] and y + h < rojo.shape[0]:
                if mejor is None or a > mejor[2]:
                    mejor = (cx, cy, a)
    if mejor is not None:
        return (mejor[0], mejor[1])
    # respaldo 1: la línea de la ruta se dibuja ENCIMA del marcador y tapa la V negra. El círculo
    # sigue siendo una mancha roja "gruesa" (la línea es fina) con borde oscuro alrededor.
    r = _disco_rojo(rojo, hsv)
    if r is not None:
        return r
    # respaldo 2: si la línea de la ruta toca el círculo, ya no es "redondo". Se busca la flecha
    # negra (mancha oscura pequeña) rodeada casi por completo de rojo.
    oscuro = (hsv[..., 2] < 80).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(oscuro, 8)
    k3 = np.ones((3, 3), np.uint8)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (3 <= a <= 60 and w <= 12 and h <= 12):
            continue
        blob = (lab[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6] == i).astype(np.uint8)
        # junto a la flecha blanca del jugador hay sombras oscuras sobre la ruta: descartar
        blanco = ((hsv[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6, 2] > 190) &
                  (hsv[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6, 1] < 60)).astype(np.uint8)
        if (cv2.dilate(blob, k3, iterations=3) & blanco).any():
            continue
        anillo = cv2.dilate(blob, k3, iterations=2) & (1 - blob)
        zona = rojo[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6]
        if anillo.sum() and (zona[anillo > 0] > 0).mean() > 0.75 and \
                _rodeado(rojo, int(cen[i][0]), int(cen[i][1]), max(w, h) / 2.0 + 2.5):
            if mejor is None or a > mejor[2]:
                mejor = (int(cen[i][0]), int(cen[i][1]), a)
    return None if mejor is None else (mejor[0], mejor[1])

"""
Lectura del minimapa: encuentra la ruta roja y calcula hacia dónde girar.

Idea (tipo "pure pursuit"):
  1. Recorta el minimapa y filtra los píxeles del color de la ruta (HSV).
  2. Se queda con el trozo de ruta conectado al jugador (descarta otros
     iconos rojos sueltos del mapa).
  3. Mira dónde corta la ruta un círculo de radio R alrededor del jugador
     (punto de mira cercano) y otro de radio mayor (punto lejano, para frenar
     antes de las curvas).
  4. Ángulo 0° = recto hacia arriba del minimapa (= hacia delante en primera
     persona). Positivo = derecha, negativo = izquierda.
"""
import math
import numpy as np
import cv2


class Captura:
    """Captura rápida de una región de pantalla con mss.
    3.0.0: si la región trae "w_real"/"h_real", se captura ese tamaño real y se redimensiona a w x h
    (la unidad fija del minimapa), así la visión ve lo mismo en cualquier resolución."""

    def __init__(self, region):
        import mss
        self.sct = mss.mss()
        wr = int(round(region.get("w_real", region["w"])))
        hr = int(round(region.get("h_real", region["h"])))
        self.region = {"left": int(region["x"]), "top": int(region["y"]), "width": wr, "height": hr}
        self.salida = (int(region["w"]), int(region["h"]))
        self.redim = (wr, hr) != self.salida

    def leer(self):
        img = cv2.cvtColor(np.asarray(self.sct.grab(self.region)), cv2.COLOR_BGRA2BGR)  # BGRA -> BGR
        return redimensionar(img, self.salida) if self.redim else img


def redimensionar(img, salida):
    """Lleva una imagen al tamaño (ancho, alto) dado."""
    if (img.shape[1], img.shape[0]) == tuple(salida):
        return img
    f = salida[1] / max(1, img.shape[0])
    return cv2.resize(img, tuple(salida), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)


def recortar_minimapa(pantalla, m, x0=0, y0=0):
    """3.0.0: recorte del minimapa (posición real) de una captura completa, ya en la unidad fija.
    x0, y0: dónde empieza la captura en la pantalla."""
    wr = int(round(m.get("w_real", m["w"])))
    hr = int(round(m.get("h_real", m["h"])))
    x, y = int(m["x"]) - x0, int(m["y"]) - y0
    rec = pantalla[max(0, y):y + hr, max(0, x):x + wr]
    if rec.size == 0:
        return None
    return redimensionar(rec, (int(m["w"]), int(m["h"])))


def mascara_ruta(img_bgr, rangos_hsv):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for r in rangos_hsv:
        lo = np.array(r[:3], np.uint8)
        hi = np.array(r[3:], np.uint8)
        mask |= cv2.inRange(hsv, lo, hi)
    k = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    return mask


def mascara_calle(img_bgr, cfg):
    """
    Calles del minimapa: gris poco saturado y más claro que su entorno.
    - El fondo se mide LOCALMENTE (el minimapa es semitransparente y el fondo cambia).
    - Se descartan zonas anchas y uniformes (mar, lagos, explanadas): una calle es una franja.
    """
    c = cfg.get("calle", {})
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    S = hsv[..., 1]
    V = hsv[..., 2]
    k = int(c.get("ventana_fondo", 31)) | 1
    fondo = cv2.medianBlur(V, k).astype(np.int16)
    m = (S < c.get("saturacion_max", 45)) & (V.astype(np.int16) > fondo + c.get("claridad_sobre_fondo", 22)) & (V < 235)
    m = m.astype(np.uint8) * 255
    # zonas claras y uniformes respecto al fondo global también cuentan (calles anchas sobre fondo oscuro)
    fondo_g = int(np.median(V))
    m |= (((S < c.get("saturacion_max", 45)) & (V.astype(np.int16) > fondo_g + 30) & (V < 235)).astype(np.uint8) * 255)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # quitar manchas anchas (mar): donde cabe un cuadrado de N px entero no es una calle
    n = int(c.get("ancho_max_calle_px", 16))
    ancho = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((n, n), np.uint8))
    if ancho.any():
        m[cv2.dilate(ancho, np.ones((5, 5), np.uint8)) > 0] = 0
    return m


def _bifurcacion(transitable, pts, esc, d_min=12, d_max=95, ancho=18, ruta=None):
    """Distancia (px por la ruta) a la que la calle se ABRE EN DOS delante (separador, salida de
    autopista...). En el corte perpendicular a la ruta: primero una sola franja de calle y después
    otra franja ancha, separada de la de la ruta, que se aleja POCO A POCO (si se aleja rápido es
    una calle lateral de un cruce, no un separador). None si no hay."""
    t_ = transitable.copy()
    if ruta is not None:   # la línea roja tiene un borde oscuro: cuenta como calle
        t_ |= cv2.dilate(ruta, np.ones((5, 5), np.uint8))
    t_ = cv2.morphologyEx(t_, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    h, w = t_.shape
    W = int(round(ancho * esc))
    ancho_min = max(4, int(round(4 * esc)))
    muestras = []                       # (d, hueco hasta la otra franja o None)
    for k in range(1, len(pts) - 1):
        x, y, d = pts[k]
        if d < d_min * esc:
            continue
        if d > d_max * esc:
            break
        tx, ty = pts[k + 1][0] - pts[k - 1][0], pts[k + 1][1] - pts[k - 1][1]
        n_ = math.hypot(tx, ty)
        if n_ < 1e-6:
            continue
        nx, ny = -ty / n_, tx / n_
        perfil = []
        for t in range(-W, W + 1):
            xi, yi = int(round(x + t * nx)), int(round(y + t * ny))
            perfil.append(0 <= xi < w and 0 <= yi < h and t_[yi, xi] > 0)
        franjas, t0 = [], None
        for i, val_ in enumerate(perfil + [False]):
            if val_ and t0 is None:
                t0 = i
            elif not val_ and t0 is not None:
                franjas.append((t0 - W, i - 1 - W))
                t0 = None
        ruta_f = [f for f in franjas if f[0] <= 0 <= f[1]]
        if not ruta_f:
            muestras.append((d, None, False))
            continue
        r0, r1 = ruta_f[0]
        huecos = [f[0] - r1 for f in franjas if f[0] > r1 and f[1] - f[0] + 1 >= ancho_min] + \
                 [r0 - f[1] for f in franjas if f[1] < r0 and f[1] - f[0] + 1 >= ancho_min]
        hueco = min(huecos) if huecos else None
        muestras.append((d, hueco if hueco is not None and hueco >= 2 * esc else None, True))
    # buscar: >= 3 muestras con una sola franja y luego >= 4 seguidas con otra franja cuyo hueco
    # crece despacio (pendiente < 0.45 px por px de avance, ~25°)
    n = len(muestras)
    for i in range(3, n - 3):
        if not all(m[1] is None and m[2] for m in muestras[i - 3:i]):
            continue
        tramo = muestras[i:i + 4]
        if not all(m[1] is not None for m in tramo):
            continue
        dd = tramo[-1][0] - tramo[0][0]
        if dd <= 0:
            continue
        pendiente = (tramo[-1][1] - tramo[0][1]) / dd
        if 0 <= pendiente < 0.45:
            return tramo[0][0]
    return None


def _info_calle(transitable, ruta, pts, px, py, v):
    """
    Compara la línea del GPS con la calle gris alrededor:
      corr: cuánto (px) está el centro de la calle a la DERECHA de la línea del GPS
            (0 si la calle no es más ancha que la línea o no hay información)
      gps_fuera: el GPS no va sobre una calle y hay una calle paralela cerca
      en_calle: fracción de calle/ruta justo delante del camión (1 = bien, 0 = fuera)
    """
    h, w = ruta.shape
    def val(m, x, y):
        xi, yi = int(round(x)), int(round(y))
        return 0 <= xi < w and 0 <= yi < h and m[yi, xi] > 0
    r0 = v.get("radio_inicio", 13)
    r1 = v.get("radio_ajuste", 30) + 10
    corrs, fueras, lados = [], 0, []
    usados = 0
    for k in range(1, len(pts) - 1):
        x, y, d = pts[k]
        if d < r0 or d > r1:
            continue
        dx, dy = pts[k + 1][0] - pts[k - 1][0], pts[k + 1][1] - pts[k - 1][1]
        n = math.hypot(dx, dy)
        if n < 1e-6:
            continue
        nx, ny = -dy / n, dx / n               # normal hacia la DERECHA del sentido de la ruta
        ts = np.arange(-18, 18.5, 1.0)
        trans = np.array([val(transitable, x + t * nx, y + t * ny) for t in ts])
        rut = np.array([val(ruta, x + t * nx, y + t * ny) for t in ts])
        c0 = len(ts) // 2
        if not trans[c0]:
            continue
        usados += 1
        a = c0
        while a > 0 and trans[a - 1]:
            a -= 1
        b = c0
        while b < len(ts) - 1 and trans[b + 1]:
            b += 1
        ra = c0
        while ra > 0 and rut[ra - 1]:
            ra -= 1
        rb = c0
        while rb < len(ts) - 1 and rut[rb + 1]:
            rb += 1
        margen = (ra - a) + (b - rb)            # píxeles de calle gris a los lados de la línea roja
        ancho = ts[b] - ts[a]
        if ancho > v.get("calle_ancho_max_centrar", 12):
            continue                            # avenida/zona ancha: NO ir al centro (puede haber bandejón)
        if margen >= 2:
            corrs.append((ts[a] + ts[b]) / 2.0)
        else:
            # la línea roja no tiene calle a los lados: ¿hay una calle gris paralela cerca?
            fueras += 1
            # buscar a cada lado una franja gris de al menos 3 px separada de la línea roja
            for signo in (-1, 1):
                idx = range(c0, len(ts)) if signo > 0 else range(c0, -1, -1)
                ini = fin = None
                for k2 in idx:
                    if abs(ts[k2]) <= 4:
                        continue
                    if trans[k2] and not rut[k2]:
                        ini = ts[k2] if ini is None else ini
                        fin = ts[k2]
                    elif ini is not None:
                        break
                if ini is not None and abs(fin - ini) >= 2 and abs(ini) <= 12:
                    lados.append((ini + fin) / 2.0)
    out = {"corr": 0.0, "gps_fuera": False, "en_calle": 1.0, "muestras": usados}
    tope = v.get("calle_corr_max_px", 2.5)
    if corrs:
        out["corr"] = float(np.clip(np.median(corrs), -tope / 0.5, tope / 0.5))
    if usados >= 5 and fueras >= 0.85 * usados and len(lados) >= 0.85 * fueras:
        lados_a = np.array(lados)
        mismo_lado = (lados_a > 0).all() or (lados_a < 0).all()
        if mismo_lado and lados_a.std() <= 1.0:
            # GPS fuera de calle con UNA calle paralela constante al lado: ir hacia ella a medias
            out["gps_fuera"] = True
            out["corr"] = float(np.clip(np.median(lados_a) * 0.5, -tope / 0.5, tope / 0.5))
    # ¿hay calle delante del camión? (justo pasada la flecha, en su dirección)
    f0, f1 = v.get("radio_inicio", 13) - 4, v.get("radio_inicio", 13) + 4
    filas = []
    for f in np.arange(f0, f1 + 0.1, 1.0):
        # la fila cuenta como "calle" si hay calle/ruta a menos de 4 px del eje del camión
        filas.append(any(val(transitable, px + dx_, py - f) for dx_ in range(-4, 5)))
    out["en_calle"] = float(np.mean(filas))
    return out


def _componente_jugador(mask, px, py, max_dist):
    """
    Trozo de ruta que sale del jugador. La flecha blanca suele partir la ruta en dos
    (un trocito detrás y la ruta de delante): de los trozos que tocan al jugador se
    elige el más grande, no el más cercano.
    """
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None, None
    ys, xs = np.nonzero(mask)
    d = np.hypot(xs - px, ys - py)
    lab_px = etiquetas[ys, xs]
    mejor, mejor_area, mejor_d = None, 0, None
    dmin_global = None
    for lab in range(1, n):
        area = stats[lab, cv2.CC_STAT_AREA]
        if area < 12:
            continue
        dm = d[lab_px == lab].min()
        dmin_global = dm if dmin_global is None else min(dmin_global, dm)
        if dm <= max_dist and area > mejor_area:
            mejor, mejor_area, mejor_d = lab, area, dm
    if mejor is None:
        return None, dmin_global
    return (etiquetas == mejor), mejor_d


def _clusters_anillo(xs, ys, px, py, radio, tol):
    """Ángulos (en grados) de los grupos de píxeles que cortan el anillo."""
    dx = xs - px
    dy = ys - py
    d = np.hypot(dx, dy)
    sel = np.abs(d - radio) <= tol
    if not sel.any():
        return []
    ang = np.degrees(np.arctan2(dx[sel], -dy[sel]))  # 0 = arriba, + = derecha
    ang = np.sort(ang)
    grupos, actual = [], [ang[0]]
    for a in ang[1:]:
        if a - actual[-1] > 12:
            grupos.append(actual); actual = [a]
        else:
            actual.append(a)
    grupos.append(actual)
    # unir el grupo que cruza ±180°
    if len(grupos) > 1 and (grupos[0][0] + 360) - grupos[-1][-1] <= 12:
        grupos[0] = [a + 360 for a in grupos[0]] + grupos[-1]
        grupos.pop()
    res = []
    for g in grupos:
        m = float(np.mean(g))
        if m > 180:
            m -= 360
        res.append((m, len(g)))
    return res


def _punto(px, py, r, ang):
    a = math.radians(ang)
    return (px + r * math.sin(a), py - r * math.cos(a))


def _linea_central(xs, ys, px, py, v, ang_previo):
    """
    Recorre la ruta desde el punto más cercano al camión (fuera de la flecha blanca)
    avanzando por la propia línea, paso a paso. Devuelve [(x, y, distancia)], donde
    distancia = distancia al jugador del punto inicial + longitud recorrida.
    """
    r_excl = v.get("radio_inicio", 13)
    paso = v.get("paso_anillo", 3) + 1.0
    r_max = v.get("radio_anticipacion", v["radio_lejos"] * 1.5)
    P = np.stack([xs, ys], 1).astype(np.float64)
    d = np.hypot(P[:, 0] - px, P[:, 1] - py)
    fuera = d >= r_excl
    if not fuera.any():
        return []
    Q, dq = P[fuera], d[fuera]
    adelante = py - Q[:, 1]
    lateral = Q[:, 0] - px
    # el punto más cercano, penalizando lo que queda detrás del camión
    puntaje = dq + 0.8 * np.maximum(0, -adelante) + 0.15 * np.abs(lateral)
    s0 = Q[int(np.argmin(puntaje))]
    def centrar(c, radio=4.5, veces=4):
        """Mueve el punto al centro de la línea gruesa (mean-shift)."""
        for _ in range(veces):
            m = np.hypot(P[:, 0] - c[0], P[:, 1] - c[1]) <= radio
            if not m.any():
                break
            c = P[m].mean(axis=0)
        return c
    c = centrar(s0.copy())
    dist0 = float(np.hypot(c[0] - px, c[1] - py))

    def marchar(c, direc):
        pts = [(float(c[0]), float(c[1]), dist0)]
        recorrido = 0.0
        while recorrido < r_max and len(pts) < 80:
            rel = P - c
            dd = np.hypot(rel[:, 0], rel[:, 1])
            anillo = np.abs(dd - paso) <= 1.3
            if not anillo.any():
                break
            R = rel[anillo]
            cosang = (R @ direc) / np.maximum(1e-6, np.hypot(R[:, 0], R[:, 1]))
            ok = cosang >= 0.3                     # máx ~72° de giro por paso
            if not ok.any():
                break
            nuevo = c + R[ok].mean(axis=0)
            centrado = centrar(nuevo, veces=2)
            # en una esquina el centrado puede tirar hacia atrás: solo aceptarlo si seguimos avanzando
            if np.hypot(*(centrado - c)) >= paso * 0.6:
                nuevo = centrado
            paso_v = nuevo - c
            n = np.hypot(*paso_v)
            if n < 0.5:
                break
            direc = 0.5 * direc + 0.5 * (paso_v / n)
            direc /= np.hypot(*direc)
            c = nuevo
            recorrido += n
            pts.append((float(c[0]), float(c[1]), dist0 + recorrido))
        return pts

    # Direcciones posibles desde el punto inicial (grupos de píxeles alrededor).
    # Se prueba cada una y se queda la que avanza más lejos (descarta el trozo de atrás).
    adelante_v = np.array([0.0, -1.0])
    if ang_previo is not None and abs(ang_previo) < 100:
        a = math.radians(ang_previo)
        adelante_v = np.array([math.sin(a), -math.cos(a)])
    rel = P - c
    dd = np.hypot(rel[:, 0], rel[:, 1])
    r_sonda = max(10.0, paso * 2.5)          # más grande que el grosor de la línea
    R = rel[np.abs(dd - r_sonda) <= 1.5]
    if len(R) == 0:
        R = rel[np.abs(dd - paso) <= 1.3]
    if len(R) == 0:
        return [(float(c[0]), float(c[1]), dist0)]
    angs = np.degrees(np.arctan2(R[:, 0], -R[:, 1]))
    orden = np.argsort(angs)
    grupos, actual = [], [orden[0]]
    for a_, b_ in zip(orden, orden[1:]):
        if angs[b_] - angs[a_] > 30:
            grupos.append(actual); actual = [b_]
        else:
            actual.append(b_)
    grupos.append(actual)
    if len(grupos) > 1 and (angs[grupos[0][0]] + 360) - angs[grupos[-1][-1]] <= 30:
        grupos[0] = grupos[-1] + grupos[0]; grupos.pop()
    mejor, mejor_puntaje = None, -1e9
    for g in grupos:
        dvec = R[g].mean(axis=0)
        n = np.hypot(*dvec)
        if n < 1e-6:
            continue
        dvec = dvec / n
        camino = marchar(c.copy(), dvec)
        fin = camino[-1]
        lejos = math.hypot(fin[0] - px, fin[1] - py)
        puntaje = lejos + 0.3 * (fin[2] - dist0) + 15 * float(dvec @ adelante_v)
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = camino, puntaje
    return mejor or [(float(c[0]), float(c[1]), dist0)]


def _ajustar_recta(pts, px, py):
    """Recta por los puntos de la línea central (fuera de la flecha del jugador).
    Devuelve (rumbo°, desvío px). desvío = distancia del jugador a esa recta
    (+ = la ruta está a la DERECHA del jugador)."""
    P = np.array([(x - px, py - y) for x, y, _ in pts], np.float64)   # (lateral, adelante)
    if len(P) >= 3:
        c = P.mean(axis=0)
        _, _, vt = np.linalg.svd(P - c)
        u = vt[0]
    else:
        c = P[0]
        u = P[-1] - P[0]
    n = np.linalg.norm(u)
    if n < 1e-6:
        return 0.0, 0.0
    u = u / n
    if np.dot(u, P[-1] - P[0]) < 0:
        u = -u
    rumbo = math.degrees(math.atan2(u[0], u[1]))
    w = -c                                   # del punto medio al jugador
    desvio = u[0] * w[1] - u[1] * w[0]
    return rumbo, float(desvio)


def _desvio_curva(pts, px, py, v):
    """
    Distancia lateral del camión a la ruta en curva: se ajusta un círculo a los puntos
    cercanos de la línea central y se mide la distancia del camión a ese círculo.
    (Prolongar una recta en curva da un desvío falso.) + = la ruta está a la DERECHA.
    """
    r_max = v.get("radio_ajuste", 30) + 8
    cerca = [p for p in pts if p[2] <= r_max]
    if len(cerca) < 4:
        cerca = pts[:4]
    P = np.array([(x - px, py - y) for x, y, _ in cerca], np.float64)     # (lateral X, adelante F)
    recta = _ajustar_recta(cerca[:3], px, py)[1] if len(cerca) >= 2 else 0.0
    if len(P) < 4:
        return recta
    X, F = P[:, 0], P[:, 1]
    A = np.column_stack([X, F, np.ones(len(P))])
    b = -(X * X + F * F)
    try:
        (D, E, G), *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return recta
    cx, cf = -D / 2, -E / 2
    R2 = cx * cx + cf * cf - G
    if R2 <= 0:
        return recta
    R = math.sqrt(R2)
    resid = np.abs(np.hypot(X - cx, F - cf) - R).max()
    if R > v.get("desvio_radio_recta_px", 400) or resid > 2.5:
        return _ajustar_recta(cerca, px, py)[1]            # casi recta (o mal ajuste): usar recta
    # punto del círculo más cercano al camión (0,0) y tangente en el sentido de la ruta
    d0 = math.hypot(cx, cf)
    if d0 < 1e-6:
        return recta
    qx, qf = cx - cx / d0 * R, cf - cf / d0 * R            # Q = centro + R·(camión-centro)/|…|
    tx, tf = -(qf - cf), (qx - cx)                         # tangente (perpendicular al radio)
    sent = (P[-1, 0] - P[0, 0]) * tx + (P[-1, 1] - P[0, 1]) * tf
    if sent < 0:
        tx, tf = -tx, -tf
    n = math.hypot(tx, tf)
    tx, tf = tx / n, tf / n
    return float(tf * qx - tx * qf)                        # w = Q - camión = (qx, qf)


def _dif_ang(a, b):
    return (a - b + 180) % 360 - 180


def analizar(img, cfg, ang_previo=0.0):
    """
    Devuelve un dict con:
      encontrada, rumbo (° hacia donde va la ruta junto al jugador, + = derecha),
      desvio (px: + = la ruta está a la derecha del camión),
      giro_adelante (° que gira la ruta más adelante, para la velocidad),
      ang_cerca / ang_lejos / ang_anticipa (para mostrar), cerca_destino, puntos, mask, comp
    """
    v = cfg["vision"]
    px, py = cfg["jugador"]["x"], cfg["jugador"]["y"]
    mask = mascara_ruta(img, cfg["color_ruta_hsv"])
    comp, _ = _componente_jugador(mask, px, py, v["max_dist_inicio"])
    out = {"encontrada": False, "rumbo": None, "desvio": None, "giro_adelante": None, "giros": [], "tasas": [],
           "ang_cerca": None, "ang_lejos": None, "ang_anticipa": None,
           "cerca_destino": False, "puntos": [], "mask": mask, "comp": comp,
           "pixeles": int(mask.sum() // 255)}
    # marcador de destino (círculo rojo con flecha) en el minimapa: posición relativa al camión
    out["marcador_dist"] = out["marcador_ang"] = None
    try:
        import pantalla_estado
        mk = pantalla_estado.marcador_destino(img)
        if mk is not None:
            out["marcador_xy"] = (int(mk[0]), int(mk[1]))
            out["marcador_dist"] = float(math.hypot(mk[0] - px, mk[1] - py))
            out["marcador_ang"] = float(math.degrees(math.atan2(mk[0] - px, py - mk[1])))   # + = derecha
    except Exception:
        pass
    if comp is None:
        return out
    ys, xs = np.nonzero(comp)
    pts = _linea_central(xs, ys, px, py, v, ang_previo)
    if not pts:
        # trozo de ruta sin cruzar ningún anillo: destino pegado al camión
        d = np.hypot(xs - px, ys - py)
        k = int(np.argmax(d))
        pts = [(float(xs[k]), float(ys[k]), float(d[k]))]
    out["encontrada"] = True
    out["puntos"] = pts

    r_aj = v.get("radio_ajuste", 20)
    L = int(v.get("puntos_cuerda", 6))          # cuerdas de ~6 pasos (~24 px): suavizan zigzags del GPS

    def rumbo_cuerda(k):
        a, b = pts[k], pts[min(k + L, len(pts) - 1)]
        return math.degrees(math.atan2(b[0] - a[0], a[1] - b[1]))

    # Esquina: primer punto donde la ruta gira bruscamente respecto a su tramo inicial.
    # Mientras la esquina esté lejos, se dirige SOLO con el tramo de antes de la esquina
    # (si no, el camión empieza a girar antes de tiempo y corta la curva).
    esquina_k, esquina_dist = None, None
    if len(pts) > L + 2:
        h0 = rumbo_cuerda(0)
        for k in range(1, len(pts) - 3):
            a, b = pts[k], pts[min(k + 3, len(pts) - 1)]
            hk = math.degrees(math.atan2(b[0] - a[0], a[1] - b[1]))
            if abs(_dif_ang(hk, h0)) > v.get("esquina_grados", 35):
                esquina_k, esquina_dist = k, pts[k][2]
                break
    out["esquina_dist"] = esquina_dist
    out["esquina_giro"] = None
    if esquina_k is not None and esquina_k + L < len(pts):
        a_, b_ = pts[esquina_k], pts[min(esquina_k + L, len(pts) - 1)]
        out["esquina_giro"] = _dif_ang(math.degrees(math.atan2(b_[0] - a_[0], a_[1] - b_[1])), rumbo_cuerda(0))
    cerca = [p for p in pts if p[2] <= r_aj]
    if esquina_k is not None and esquina_dist > v.get("adelanto_giro_px", 16):
        cerca = [p for p in pts[:esquina_k + 1] if p[2] <= r_aj] or pts[:max(2, esquina_k + 1)]
    if len(cerca) < 2:
        cerca = pts[:3]
    rumbo, desvio = _ajustar_recta(cerca, px, py)
    if len(cerca) == 1:   # un solo punto: apuntar a él
        x, y, _ = cerca[0]
        rumbo, desvio = math.degrees(math.atan2(x - px, py - y)), 0.0
    out["rumbo"], out["desvio"] = rumbo, desvio
    # desvío LOCAL: distancia del camión a la línea medida con el tramo más cercano
    # (en curvas, una recta larga se tuerce y mide mal)
    # Esquina "oculta" bajo la flecha: si el primer tramo visible ya va muy de lado, calcular a qué
    # distancia por delante del camión cruza ese tramo su línea recta (ahí está la esquina)
    out["esquina_frente"] = None
    if abs(rumbo) >= 45 and len(pts) >= 2:
        q = pts[:min(4, len(pts))]
        (x1, y1, _), (x2, y2, _) = q[0], q[-1]
        X1, F1, X2, F2 = x1 - px, py - y1, x2 - px, py - y2
        if abs(X2 - X1) > 1e-6:
            t = -X1 / (X2 - X1)                       # punto del tramo con lateral 0 (delante del camión)
            F0 = F1 + t * (F2 - F1)
            if F0 > -5:
                out["esquina_frente"] = float(F0)
    # el desvío lateral se mide solo con el tramo ANTES de la esquina (si no, la mezcla con el
    # tramo de después da un desvío falso y el camión gira al revés)
    tramo_desvio = pts
    if esquina_k is not None and esquina_dist is not None and esquina_dist > v.get("radio_inicio", 13) + 2:
        tramo_desvio = pts[:esquina_k + 1]
    if len(tramo_desvio) >= 2:
        out["desvio_cerca"] = _desvio_curva(tramo_desvio, px, py, v)
    elif len(pts) >= 2:
        out["desvio_cerca"] = _ajustar_recta(pts[:2], px, py)[1]
    else:
        out["desvio_cerca"] = desvio

    # Calles grises: corregir la línea del GPS hacia el centro de la calle y saber si estamos fuera
    if cfg.get("calle", {}).get("activo", True):
        calle = mascara_calle(img, cfg)
        transitable = cv2.bitwise_or(calle, mask)
        info = _info_calle(transitable, mask, pts, px, py, v)
        out.update(calle_corr=info["corr"], gps_fuera=info["gps_fuera"], en_calle=info["en_calle"])
        try:
            out["bifurcacion_dist"] = _bifurcacion(calle, pts, min(img.shape[0], img.shape[1]) / 176.0, ruta=mask)
        except Exception:
            out["bifurcacion_dist"] = None
        out["calle"] = calle
    else:
        out.update(calle_corr=0.0, gps_fuera=False, en_calle=1.0)

    # Giros para la velocidad: cambio de dirección de la ruta respecto a SU tramo inicial,
    # medido con cuerdas largas (un zigzag del GPS que vuelve a su dirección no cuenta)
    giros, giro = [], 0.0
    if len(pts) > L + 1:
        h0 = rumbo_cuerda(0)
        crudos = [(pts[min(k + L, len(pts) - 1)][2], _dif_ang(rumbo_cuerda(k), h0))
                  for k in range(1, len(pts) - L)]
        # tasa de giro: cambio de dirección en ~5 pasos (~20 px) -> lo cerrada que es la curva
        crudas = []
        for k in range(1, len(pts) - L - 5):
            tasa = abs(_dif_ang(rumbo_cuerda(k + 5), rumbo_cuerda(k)))
            acum = abs(_dif_ang(rumbo_cuerda(k + 5), h0))       # cuánto ha girado la ruta en total
            crudas.append((pts[k + 5][2], min(tasa, acum + v.get("tasa_margen_acumulado", 8))))
        tasas = []
        for k in range(len(crudas)):
            ventana = sorted(t for _, t in crudas[max(0, k - 2):k + 3])
            tasas.append((crudas[k][0], ventana[len(ventana) // 2]))
        out["tasas"] = tasas
        for k in range(len(crudos)):
            ventana = sorted(g for _, g in crudos[max(0, k - 2):k + 3])
            g = ventana[len(ventana) // 2]       # mediana de 5: quita picos sueltos
            giros.append((crudos[k][0], g))
            if abs(g) > abs(giro):
                giro = g
    out["giro_adelante"] = giro
    out["giros"] = giros

    def ang_en(r):
        p = min(pts, key=lambda p: abs(p[2] - r))
        return math.degrees(math.atan2(p[0] - px, py - p[1]))
    out["ang_cerca"] = ang_en(v["radio_cerca"])
    out["ang_lejos"] = ang_en(v["radio_lejos"])
    out["ang_anticipa"] = ang_en(v.get("radio_anticipacion", v["radio_lejos"] * 1.5))
    # destino cerca: la ruta se acaba antes del radio cercano
    out["cerca_destino"] = pts[-1][2] < v["radio_cerca"]
    # fin de ruta visible (no porque salga del minimapa): distancia hasta él
    h, w = mask.shape
    xl, yl, rl = pts[-1]
    borde = min(xl, yl, w - 1 - xl, h - 1 - yl)
    r_max = v.get("radio_anticipacion", v["radio_lejos"] * 1.5)
    d_ult = math.hypot(xl - px, yl - py)
    dpx = np.hypot(xs - xl, ys - yl)
    mas_alla = int(((np.hypot(xs - px, ys - py) > d_ult + 6) & (dpx > 8)).sum())
    fin_real = mas_alla < v.get("fin_ruta_pixeles_max", 25)   # no queda ruta sin recorrer
    borde_min = v.get("fin_ruta_borde_px", 22)    # cerca del borde (o del icono de destino) no es el final
    cerca_fin = rl <= v.get("fin_ruta_max_px", 75)   # más lejos, la ruta se difumina arriba: no fiarse
    out["fin_ruta_dist"] = rl if (borde > borde_min and cerca_fin and fin_real) else None
    if not fin_real:
        out["cerca_destino"] = False
    return out


def movimiento(prev_gray, gray):
    """Cuánto cambió el minimapa (sirve para detectar si el camión está quieto)."""
    if prev_gray is None:
        return 999.0
    return float(cv2.absdiff(prev_gray, gray).mean())


def dibujar_debug(img, res, cfg, escala=3, texto=""):
    v = cfg["vision"]
    px, py = cfg["jugador"]["x"], cfg["jugador"]["y"]
    vis = img.copy()
    if res.get("calle") is not None:
        vis[res["calle"] > 0] = (200, 120, 0)
    if res["comp"] is not None:
        vis[res["comp"]] = (0, 160, 0)
    elif res["mask"] is not None:
        vis[res["mask"] > 0] = (0, 120, 255)
    vis = cv2.resize(vis, None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
    E = lambda x, y: (int(x * escala), int(y * escala))
    c = E(px, py)
    r_aj = v.get("radio_ajuste", 20)
    r_ant = v.get("radio_anticipacion", v["radio_lejos"] * 1.5)
    cv2.circle(vis, c, int(r_aj * escala), (255, 255, 0), 1)
    cv2.circle(vis, c, int(r_ant * escala), (0, 200, 255), 1)
    pts = res.get("puntos") or []
    for a, b in zip(pts, pts[1:]):
        col = (255, 255, 0) if b[2] <= r_aj else (0, 200, 255)
        cv2.line(vis, E(a[0], a[1]), E(b[0], b[1]), col, 2)
    if res.get("rumbo") is not None and res.get("calle_corr"):
        # objetivo corregido por la calle (punto blanco)
        a = math.radians(res["rumbo"])
        dpx = res["desvio"] + res["calle_corr"]
        cx_, cy_ = px + dpx * math.cos(a), py + dpx * math.sin(a)
        cv2.circle(vis, E(cx_, cy_), 4, (255, 255, 255), -1)
    if res.get("rumbo") is not None:
        a = math.radians(res["rumbo"])
        fin = E(px + 30 * math.sin(a), py - 30 * math.cos(a))
        cv2.arrowedLine(vis, c, fin, (255, 0, 255), 2, tipLength=0.25)
    cv2.drawMarker(vis, c, (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
    # marcador de destino detectado: círculo morado por encima de todo (gris si se descartó)
    mk = res.get("marcador_xy")
    if mk is not None:
        aceptado = res.get("marcador_dist") is not None
        col = (255, 60, 190) if aceptado else (150, 150, 150)
        cv2.circle(vis, E(mk[0], mk[1]), int(9 * escala), (0, 0, 0), 4)
        cv2.circle(vis, E(mk[0], mk[1]), int(9 * escala), col, 2)
        etiqueta = "destino" if aceptado else "descartado"
        if aceptado and res.get("dist_hud") is not None:
            etiqueta += f" {res['dist_hud']:.0f} m"
        q = E(mk[0] + 11, mk[1] + 3)
        cv2.putText(vis, etiqueta, q, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(vis, etiqueta, q, cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
    y = 18
    for linea in texto.split("\n"):
        cv2.putText(vis, linea, (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(vis, linea, (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y += 18
    return vis

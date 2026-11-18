"""
Calibración del autopiloto.

    python calibrar.py                      # en el juego pulsa F11 para capturar; luego ALT+TAB
    python calibrar.py --espera 5           # alternativa: cuenta atrás de 5 s
    python calibrar.py --imagen captura.png # calibrar desde una captura guardada

Pasos:
  1. Arrastra un rectángulo sobre el MINIMAPA y pulsa ENTER.
  2. Haz clic EXACTO sobre la flecha del jugador y pulsa ENTER.
  3. Haz clic sobre varios puntos de la RUTA ROJA (4-8 clics, en tramos distintos).
     Verás en vivo qué detecta (verde). Z = deshacer último clic. ENTER = guardar.

Consejo: haz la captura ya dentro del camión, en primera persona y con la ruta
visible. Pon el juego en "Ventana sin bordes" (borderless): en pantalla completa
exclusiva la captura puede salir negra.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np

import configuracion
import entrada
import vision


def _captura():
    try:
        import carpetas
        return os.path.join(carpetas.EQUIPO, "captura_calibracion.png")
    except Exception:  # noqa
        return "captura_calibracion.png"


def capturar_pantalla(espera, tecla="F11", continuar=None):
    import mss
    if entrada.ES_WINDOWS and espera <= 0:
        print(f"Ve al juego (dentro del camión, primera persona, ruta visible y EN MOVIMIENTO\n"
              f"para que se vea el velocímetro) y pulsa {tecla} para capturar.")
        hk = entrada.Hotkeys([tecla])
        while tecla not in hk.leer():
            time.sleep(0.02)
    else:
        for i in range(espera, 0, -1):
            print(f"Capturando en {i}... (cambia al juego)")
            time.sleep(1)
    titulo = entrada.titulo_ventana_activa()
    with mss.mss() as sct:
        img = np.asarray(sct.grab(sct.monitors[1]))
    cv2.imwrite(_captura(), cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
    print(f"Captura guardada en {_captura()}")
    if continuar is not None:
        print("Ahora sal del juego con ALT+TAB (o pausa con ESC) y pulsa CONTINUAR en el programa.")
        continuar()
    else:
        print("\nAhora sal del juego con ALT+TAB (o pausa con ESC) y pulsa ENTER aquí en la consola.")
        input()
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), titulo


def ventana_encima(nombre):
    cv2.namedWindow(nombre, cv2.WINDOW_AUTOSIZE)
    try:
        cv2.setWindowProperty(nombre, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass


def rangos_desde_muestras(muestras, margen_h=7, margen_s=45, margen_v=50):
    hsv = np.array(muestras, np.int32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    s_lo = int(max(40, np.percentile(s, 10) - margen_s))
    v_lo = int(max(40, np.percentile(v, 10) - margen_v))
    # el rojo cruza el 0 del tono: tratarlo en espacio circular
    hc = np.where(h > 90, h - 180, h) if (h.min() < 20 and h.max() > 160) else h
    h_lo = int(np.percentile(hc, 5) - margen_h)
    h_hi = int(np.percentile(hc, 95) + margen_h)
    rangos = []
    if h_lo < 0:
        rangos.append([0, s_lo, v_lo, max(0, h_hi), 255, 255])
        rangos.append([180 + h_lo, s_lo, v_lo, 179, 255, 255])
    elif h_hi > 179:
        rangos.append([h_lo, s_lo, v_lo, 179, 255, 255])
        rangos.append([0, s_lo, v_lo, h_hi - 180, 255, 255])
    else:
        rangos.append([h_lo, s_lo, v_lo, h_hi, 255, 255])
    return rangos


def calibrar_carril(pantalla, cfg, origen=(0, 0), rect=None):
    """Paso 5: 4 clics en las esquinas del carril (yendo centrado en una recta).
    3.0.0: pantalla puede ser solo la ventana del juego (origen = dónde empieza en la pantalla); se guarda
    también relativo a la ventana (rect)."""
    import carril
    alto = pantalla.shape[0]
    esc = 1.0 if alto <= 1100 else 1080 / alto
    vista = cv2.resize(pantalla, None, fx=esc, fy=esc)
    nombres = ["1 CERCA-IZQUIERDA", "2 LEJOS-IZQUIERDA", "3 LEJOS-DERECHA", "4 CERCA-DERECHA"]
    pts = []

    def clic(ev, mx, my, *_):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((mx / esc, my / esc))

    nombre = "5) Carril: 4 clics en las lineas del carril. Z=deshacer, ENTER=guardar, ESC=saltar"
    ventana_encima(nombre)
    cv2.setMouseCallback(nombre, clic)
    print("\n5) CARRIL: haz clic en las líneas que limitan TU carril, en este orden:\n"
          "   1 abajo-izquierda, 2 arriba-izquierda, 3 arriba-derecha, 4 abajo-derecha.\n"
          "   'Abajo' = justo delante del capó; 'arriba' = unos metros más adelante (no en el horizonte).\n"
          "   La captura debe ser en una RECTA, yendo CENTRADO en el carril. ESC para saltar.")
    while True:
        v = vista.copy()
        for k, (x, y) in enumerate(pts):
            cv2.circle(v, (int(x * esc), int(y * esc)), 6, (0, 255, 0), -1)
            cv2.putText(v, str(k + 1), (int(x * esc) + 8, int(y * esc) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if len(pts) >= 2:
            cv2.polylines(v, [np.int32([(x * esc, y * esc) for x, y in pts])], len(pts) == 4, (0, 255, 255), 2)
        txt = "Siguiente: " + nombres[len(pts)] if len(pts) < 4 else "ENTER para guardar"
        _rotular(v, [txt], 20, 40, 40, 1.0, 2)
        cv2.imshow(nombre, v)
        k = cv2.waitKey(30)
        if k == 27:
            cv2.destroyAllWindows()
            print("   Carril: se mantiene la calibración anterior.")
            return False
        if k in (ord("z"), ord("Z")) and pts:
            pts.pop()
        if k in (13, 10) and len(pts) == 4:
            break
    cv2.destroyAllWindows()
    local = [[int(round(x)), int(round(y))] for x, y in pts]
    cfg["carril"]["trapecio"] = [[x + origen[0], y + origen[1]] for x, y in local]
    cfg["carril"].pop("centro_ref", None)
    if rect and cfg.get("calibracion"):
        import geometria
        cfg["calibracion"]["carril"] = geometria.desde_absoluto(rect, cfg["minimapa"],
                                                                trapecio=cfg["carril"]["trapecio"])["carril"]
    det = carril.DetectorCarrilIPM(dict(cfg["carril"], trapecio=local))
    for _ in range(5):
        r = det.detectar(det.capturar(pantalla))
    print(f"   Carril guardado. Prueba en la captura: desvío {r['desvio']:+.2f} (≈0 si ibas centrado), "
          f"confianza {r['confianza']:.2f}")
    ventana_encima("Vista del carril desde arriba (cualquier tecla)")
    cv2.imshow("Vista del carril desde arriba (cualquier tecla)", carril.dibujar_ipm(r, det))
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return True


def mascara_yolo(pantalla, cfg, origen=(0, 0), rect=None):
    """3.6.0: rectángulos de la cabina que YOLO no debe mirar (tablero, parantes, espejos, limpiaparabrisas).
    Arrastra con el mouse para dibujar; Z = deshacer; ENTER = guardar; ESC = salir sin cambios.
    Se guardan en fracciones de la ventana del juego (siguen sirviendo si la mueves)."""
    import vision_yolo
    alto, ancho = pantalla.shape[:2]
    esc = min(1.0, 1000 / alto, 1700 / ancho)
    vista0 = cv2.resize(pantalla, None, fx=esc, fy=esc)
    yc = vision_yolo.configurar(cfg)
    rects = [list(r) for r in yc.get("mascara") or []]
    zona = None
    try:
        tr = [[x - origen[0], y - origen[1]] for x, y in cfg["carril"]["trapecio"]]
        g = vision_yolo.Geometria(tr, ancho, yc["ancho_carril_m"], yc["fov_horizontal_grados"])
        zona = g.zona((0, 0, ancho, alto))
    except Exception as e:  # noqa
        print(f"   (No se puede mostrar la zona que mira YOLO: {e})")
    estado = {"ini": None, "act": None}

    def clic(ev, mx, my, *_):
        fx, fy = mx / esc / ancho, my / esc / alto
        if ev == cv2.EVENT_LBUTTONDOWN:
            estado["ini"], estado["act"] = (fx, fy), (fx, fy)
        elif ev == cv2.EVENT_MOUSEMOVE and estado["ini"] is not None:
            estado["act"] = (fx, fy)
        elif ev == cv2.EVENT_LBUTTONUP and estado["ini"] is not None:
            (a, b), (c, d) = estado["ini"], (fx, fy)
            if abs(c - a) > 0.005 and abs(d - b) > 0.005:
                rects.append([round(min(a, c), 4), round(min(b, d), 4), round(max(a, c), 4), round(max(b, d), 4)])
            estado["ini"] = estado["act"] = None

    nombre = "Mascara de cabina (YOLO): arrastra = tapar, Z = deshacer, ENTER = guardar, ESC = salir"
    ventana_encima(nombre)
    cv2.setMouseCallback(nombre, clic)
    print("\nMÁSCARA DE CABINA (YOLO): arrastra con el mouse rectángulos sobre lo que es de la cabina y no de la "
          "calle (tablero, parantes, espejos, limpiaparabrisas). El recuadro verde es lo que mira YOLO.")
    while True:
        v = vista0.copy()
        if zona:
            x, y, w, h = zona
            cv2.rectangle(v, (int(x * esc), int(y * esc)), (int((x + w) * esc), int((y + h) * esc)), (0, 220, 0), 2)
        todos = rects + ([[*estado["ini"], *estado["act"]]] if estado["ini"] is not None else [])
        for fx0, fy0, fx1, fy1 in todos:
            a = (int(min(fx0, fx1) * ancho * esc), int(min(fy0, fy1) * alto * esc))
            b = (int(max(fx0, fx1) * ancho * esc), int(max(fy0, fy1) * alto * esc))
            capa = v.copy()
            cv2.rectangle(capa, a, b, (120, 120, 120), -1)
            v = cv2.addWeighted(capa, 0.6, v, 0.4, 0)
            cv2.rectangle(v, a, b, (0, 200, 255), 2)
        _rotular(v, [f"{len(rects)} rectangulo(s) · ENTER guardar · Z deshacer · ESC salir"], 20, 40, 40, 0.8, 2)
        cv2.imshow(nombre, v)
        k = cv2.waitKey(30)
        if k == 27:
            cv2.destroyAllWindows()
            print("   Máscara: sin cambios.")
            return False
        if k in (ord("z"), ord("Z")) and rects:
            rects.pop()
        if k in (13, 10):
            break
    cv2.destroyAllWindows()
    # 3.6.2: avisar si algún rectángulo tapa la calle de tu carril (ahí tiene que mirar YOLO)
    try:
        tr = [[x - origen[0], y - origen[1]] for x, y in cfg["carril"]["trapecio"]]
        chico = np.zeros((alto // 4, ancho // 4), np.uint8)
        cv2.fillPoly(chico, [np.int32([[x / 4, y / 4] for x, y in tr])], 1)
        total = max(1, int(chico.sum()))
        for i, (fx0, fy0, fx1, fy1) in enumerate(rects, 1):
            parte = chico[int(fy0 * alto / 4):int(fy1 * alto / 4) + 1, int(fx0 * ancho / 4):int(fx1 * ancho / 4) + 1]
            tapa = int(parte.sum()) / total
            if tapa > 0.05:
                print(f"   [!] El rectángulo {i} tapa {tapa * 100:.0f} % de la calle de tu carril: ahí YOLO no verá "
                      "los autos de delante. Si no es parte de la cabina, vuelve a hacer la máscara sin él.")
    except Exception:  # noqa
        pass
    cfg.setdefault("yolo", {})["mascara"] = rects
    print(f"   Máscara guardada: {len(rects)} rectángulo(s).")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imagen")
    ap.add_argument("--config", default=None)
    ap.add_argument("--solo", choices=["carril", "yolo", "color"], help="calibrar solo una parte (p. ej. --solo carril)")
    ap.add_argument("--espera", type=int, default=0,
                    help="0 = capturar con F11 (por defecto); N = cuenta atrás de N segundos")
    args = ap.parse_args()
    calibrar(args.config, args.solo, args.imagen, args.espera)


# ====================================================================== 3.0.0: calibración automática
def _vel_desde_texto(caja):
    """Región del velocímetro a partir de la caja del texto amarillo (deja sitio para 3 cifras)."""
    xa, ya, xb, yb = caja
    th = max(8, yb - ya)
    return {"x": int(xb + 0.25 * th - 8.3 * th), "y": int((ya + yb) / 2 - th), "w": int(8.3 * th), "h": int(2 * th)}


def detectar_barras(img):
    """Barras de vida y armadura (verde y azul) debajo del minimapa: dan su ancho y dónde termina abajo."""
    H, W = img.shape[:2]
    oy = int(H * 0.70)
    zona = img[oy:, :int(W * 0.40)]
    hsv = cv2.cvtColor(zona, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[..., i].astype(int) for i in range(3))
    m = (((h >= 35) & (h <= 85) & (s > 60) & (v > 60)) | ((h >= 90) & (h <= 125) & (s > 60) & (v > 40))).astype(np.uint8)
    filas = m.sum(1).astype(int)
    mejor = None
    for y in np.argsort(-filas)[:40]:
        xs = np.nonzero(m[y])[0]
        if len(xs) < 0.05 * W:
            continue
        segs, a, p = [], xs[0], xs[0]
        for x in xs[1:]:
            if x - p > 6:
                segs.append((a, p))
                a = x
            p = x
        segs.append((a, p))
        a, b = max(segs, key=lambda t: t[1] - t[0])
        if mejor is None or (b - a) > (mejor[2] - mejor[1]):
            mejor = (int(y), int(a), int(b))
    if mejor is None or mejor[2] - mejor[1] < 0.06 * W:
        return None
    y, a, b = mejor
    cov = m[:, a:b + 1].mean(1)
    grupo = [int(yy) for yy in np.nonzero(cov > 0.5)[0] if abs(int(yy) - y) < 12] or [y]
    return {"x0": a, "x1": b, "arriba": min(grupo) + oy, "abajo": max(grupo) + oy}


def detectar_flecha(img, barras):
    """La flecha blanca del jugador, encima de las barras, cerca del centro del minimapa."""
    w = barras["x1"] - barras["x0"] + 1
    x0, x1 = barras["x0"] + int(0.30 * w), barras["x0"] + int(0.70 * w)
    y1 = barras["arriba"]
    y0 = max(0, y1 - int(0.45 * w))
    z = img[y0:y1, x0:x1]
    if z.size == 0:
        return None
    hsv = cv2.cvtColor(z, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] > 200) & (hsv[..., 1] < 50)).astype(np.uint8)
    n, _lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    c = [(st[i][4], i) for i in range(1, n) if 0.015 * w <= st[i][2] <= 0.12 * w and 0.015 * w <= st[i][3] <= 0.12 * w]
    if not c:
        return None
    _a, i = max(c)
    return (x0 + float(cen[i][0]), y0 + float(cen[i][1]))


def detectar_velocimetro(img):
    """Texto amarillo «NN KM/h» abajo a la derecha (solo se ve con el camión en movimiento)."""
    H, W = img.shape[:2]
    x0, y0 = int(W * 0.75), int(H * 0.80)
    z = img[y0:, x0:]
    hsv = cv2.cvtColor(z, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 0] >= 18) & (hsv[..., 0] <= 38) & (hsv[..., 1] > 80) & (hsv[..., 2] > 120)).astype(np.uint8)
    n, _lab, st, _cen = cv2.connectedComponentsWithStats(m, 8)
    comps = [st[i] for i in range(1, n) if 0.012 * H <= st[i][3] <= 0.06 * H and st[i][4] >= 15]
    if len(comps) < 2:
        return None
    mejor = None
    for c in comps:
        base = c[1] + c[3]
        g = [k for k in comps if abs(k[1] + k[3] - base) <= 0.01 * H]
        if mejor is None or len(g) > len(mejor):
            mejor = g
    if len(mejor) < 2:
        return None
    xa, xb = min(k[0] for k in mejor), max(k[0] + k[2] for k in mejor)
    ya, yb = min(k[1] for k in mejor), max(k[1] + k[3] for k in mejor)
    return _vel_desde_texto((x0 + xa, y0 + ya, x0 + xb, y0 + yb))


def autodetectar(img):
    """Minimapa (en el marco de las reglas: la flecha queda en REF_JUGADOR) y velocímetro, en coordenadas de img."""
    import geometria
    H, W = img.shape[:2]
    out = {"minimapa": None, "como": "", "velocimetro": None, "flecha": None}
    b = detectar_barras(img)
    if b is not None:
        w = b["x1"] - b["x0"] + 1
        s = w / geometria.REF_W
        f = detectar_flecha(img, b)
        if f is not None:
            out["flecha"] = f
            x = f[0] - geometria.REF_JUGADOR[0] * s
            y = f[1] - geometria.REF_JUGADOR[1] * s
            out["como"] = "barras + flecha"
        else:
            x, y = b["x0"], b["arriba"] - geometria.REF_H * s
            out["como"] = "barras (sin flecha)"
        out["minimapa"] = {"x": int(round(x)), "y": int(round(y)),
                           "w": int(round(geometria.REF_W * s)), "h": int(round(geometria.REF_H * s))}
    else:
        # sin barras: tamaño típico según el alto de la ventana (anclado abajo a la izquierda)
        s = H / geometria.REF_VENTANA_H
        out["minimapa"] = {"x": int(round(0.027 * H)), "y": int(round(H - 0.035 * H - geometria.REF_H * s)),
                           "w": int(round(geometria.REF_W * s)), "h": int(round(geometria.REF_H * s))}
        out["como"] = "estimado por el tamaño de la ventana (revisa)"
    out["velocimetro"] = detectar_velocimetro(img)
    return out


def _cfg_prueba(cfg, mm, vr):
    import geometria
    c = dict(cfg)
    c["minimapa"] = {"x": mm["x"], "y": mm["y"], "w": geometria.REF_W, "h": geometria.REF_H,
                     "w_real": mm["w"], "h_real": mm["h"]}
    c["velocimetro"] = dict(cfg["velocimetro"], region=vr) if vr else cfg["velocimetro"]
    return c


def _lecturas(img, cfg, mm, vr):
    """Prueba rápida en la captura: ruta, distancia, punto cardinal, velocidad, condición."""
    import geometria
    import hud_texto
    import condicion
    c = _cfg_prueba(cfg, mm, vr)
    out = {}
    mini = vision.recortar_minimapa(img, c["minimapa"])
    out["ruta"] = vision.analizar(mini, c, 0.0)["encontrada"] if mini is not None else False
    regs = hud_texto.regiones(c)
    try:
        d = hud_texto.leer_distancia(geometria.a_referencia(hud_texto._recortar(img, regs["distancia"]), c))
        out["distancia"] = d["texto"] if d else None
    except Exception:  # noqa
        out["distancia"] = None
    try:
        z = hud_texto.analizar_zona(geometria.a_referencia(hud_texto._recortar(img, regs["zona"]), c))
        out["cardinal"] = z["cardinal"] if z else None
    except Exception:  # noqa
        out["cardinal"] = None
    if vr:
        try:
            import velocimetro
            out["velocidad"] = velocimetro.Velocimetro(c["velocimetro"]).leer_imagen(
                img[vr["y"]:vr["y"] + vr["h"], vr["x"]:vr["x"] + vr["w"]])[0]
        except Exception:  # noqa
            out["velocidad"] = None
        try:
            x0, y0, x1, y1 = condicion.region(c)
            out["condicion"] = condicion.leer(img[max(0, y0):y1, max(0, x0):x1])
        except Exception:  # noqa
            out["condicion"] = None
    return out, c


def _rotular(v, lineas, x, y0, paso, escala, grosor):
    """3.1.0: textos sobre la captura con un fondo oscuro detrás (si no, se mezclan con el chat del juego)."""
    anchos = [cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)[0][0] for t in lineas]
    alto_t = cv2.getTextSize("Ag", cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)[0][1]
    x0, y_a = max(0, x - 8), max(0, y0 - alto_t - 8)
    x1 = min(v.shape[1], x + max(anchos) + 8)
    y1 = min(v.shape[0], y0 + paso * (len(lineas) - 1) + 10)
    zona = v[y_a:y1, x0:x1]
    if zona.size:
        zona[:] = (zona * 0.25).astype(zona.dtype)                       # oscurece lo de atrás (75 %)
    for i, t in enumerate(lineas):
        cv2.putText(v, t, (x, y0 + paso * i), cv2.FONT_HERSHEY_SIMPLEX, escala, (255, 255, 255), grosor,
                    cv2.LINE_AA)


def _dibujar(img, c, lect, como, esc):
    import hud_texto
    import condicion
    import notificaciones
    v = cv2.resize(img, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
    S = lambda r: (int(r[0] * esc), int(r[1] * esc))          # noqa: E731
    m = c["minimapa"]
    cv2.rectangle(v, S((m["x"], m["y"])), S((m["x"] + m["w_real"], m["y"] + m["h_real"])), (0, 255, 0), 2)
    jx = m["x"] + c["jugador"]["x"] * m["w_real"] / m["w"]
    jy = m["y"] + c["jugador"]["y"] * m["h_real"] / m["h"]
    cv2.drawMarker(v, S((jx, jy)), (0, 0, 255), cv2.MARKER_CROSS, 18, 2)
    for nombre, r in hud_texto.regiones(c).items():
        cv2.rectangle(v, S(r[:2]), S(r[2:]), (255, 0, 255), 1)
    r = notificaciones.region(c)
    cv2.rectangle(v, S(r[:2]), S(r[2:]), (255, 255, 0), 1)
    rv = c["velocimetro"].get("region")
    if rv:
        cv2.rectangle(v, S((rv["x"], rv["y"])), S((rv["x"] + rv["w"], rv["y"] + rv["h"])), (0, 255, 255), 2)
        r = condicion.region(c)
        cv2.rectangle(v, S(r[:2]), S(r[2:]), (0, 128, 255), 1)
    si = lambda x: "-" if x in (None, False) else ("SI" if x is True else str(x))   # noqa: E731
    lineas = [f"Minimapa: {como}",
              f"Ruta: {si(lect.get('ruta'))}   Distancia: {si(lect.get('distancia'))}   Cardinal: {si(lect.get('cardinal'))}",
              f"Velocidad: {si(lect.get('velocidad'))}   Condicion: {si(lect.get('condicion'))}"
              + ("" if rv else "   (velocimetro no encontrado: muevete o pulsa V)"),
              "ENTER guardar   M minimapa a mano   F clic en la flecha   V velocimetro a mano   C color ruta   ESC salir"]
    _rotular(v, lineas, 12, 28, 26, 0.6, 1)
    return v


def _color_ruta(mini, cfg):
    """Paso opcional: clics sobre la ruta roja para ajustar su color."""
    E = 3
    hsv = cv2.cvtColor(mini, cv2.COLOR_BGR2HSV)
    clics, muestras = [], []

    def clic(ev, mx, my, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            cx, cy = mx // E, my // E
            muestras.append(hsv[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2].reshape(-1, 3).tolist())
            clics.append((cx, cy))

    nombre = "Color de la ruta: clics sobre la linea del GPS. Z=deshacer, ENTER=listo"
    ventana_encima(nombre)
    cv2.setMouseCallback(nombre, clic)
    rangos = cfg["color_ruta_hsv"]
    while True:
        if muestras:
            rangos = rangos_desde_muestras([m for g in muestras for m in g])
        c2 = dict(cfg, color_ruta_hsv=rangos)
        res = vision.analizar(mini, c2, 0.0)
        v = vision.dibujar_debug(mini, res, c2, escala=E, texto=f"clics {len(clics)}  ruta {'SI' if res['encontrada'] else 'NO'}")
        cv2.imshow(nombre, v)
        k = cv2.waitKey(30)
        if k in (13, 10):
            break
        if k in (ord("z"), ord("Z")) and clics:
            clics.pop()
            muestras.pop()
        if k == 27:
            rangos = cfg["color_ruta_hsv"]
            break
    cv2.destroyWindow(nombre)
    return rangos


def elegir_flecha(img, mm, actual):
    """3.2.1: elegir el centro de la flecha del jugador con zoom (como el color de la ruta).
    Muestra el minimapa ampliado; clic = poner el centro (se puede repetir), flechas del teclado = mover
    1 px, ENTER = aceptar, ESC = cancelar. Devuelve (x, y) en la captura, o None."""
    E = 6
    x0, y0 = int(mm["x"]), int(mm["y"])
    w, h = int(mm["w"]), int(mm["h"])
    # alrededor de la flecha: un recorte de ~1/2 del minimapa, ampliado
    rw, rh = max(40, w // 2), max(30, h // 2)
    cx, cy = actual
    ax0 = int(max(0, min(img.shape[1] - rw, cx - rw / 2)))
    ay0 = int(max(0, min(img.shape[0] - rh, cy - rh / 2)))
    rec = img[ay0:ay0 + rh, ax0:ax0 + rw]
    big = cv2.resize(rec, None, fx=E, fy=E, interpolation=cv2.INTER_NEAREST)
    punto = [float(cx), float(cy)]
    raton = [None]

    def clic(ev, mx, my, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            punto[0], punto[1] = ax0 + mx / E, ay0 + my / E
        elif ev == cv2.EVENT_MOUSEMOVE:
            raton[0] = (mx, my)

    nombre = "Flecha: clic en el CENTRO de la flecha (flechas = mover 1 px). ENTER=aceptar, ESC=cancelar"
    ventana_encima(nombre)
    cv2.imshow(nombre, big)
    cv2.setMouseCallback(nombre, clic)
    del x0, y0
    while True:
        v = big.copy()
        if raton[0] is not None:
            cv2.drawMarker(v, raton[0], (200, 200, 200), cv2.MARKER_CROSS, 24, 1)
        px_, py_ = int(round((punto[0] - ax0) * E)), int(round((punto[1] - ay0) * E))
        cv2.drawMarker(v, (px_, py_), (0, 0, 255), cv2.MARKER_CROSS, 40, 2)
        cv2.circle(v, (px_, py_), 3, (0, 255, 255), -1)
        _rotular(v, ["Clic en el centro de la flecha (no en la punta)",
                     "Flechas del teclado: mover 1 px   ENTER aceptar   ESC cancelar"], 8, 22, 22, 0.55, 1)
        cv2.imshow(nombre, v)
        k = cv2.waitKeyEx(30)
        if k in (13, 10):
            cv2.destroyWindow(nombre)
            return punto[0], punto[1]
        if k == 27:
            cv2.destroyWindow(nombre)
            return None
        # flechas: Windows (2424832...) / Linux (65361...)
        if k in (2424832, 65361):
            punto[0] -= 1
        elif k in (2555904, 65363):
            punto[0] += 1
        elif k in (2490368, 65362):
            punto[1] -= 1
        elif k in (2621440, 65364):
            punto[1] += 1


def capturar_juego(espera, tecla, continuar):
    """Captura SOLO la ventana del juego si se encuentra. Devuelve (img, origen (x, y), rect o None, título)."""
    import mss
    import ventana
    if entrada.ES_WINDOWS and espera <= 0:
        print(f"Ve al juego (dentro del camión, en primera persona, con la ruta visible y EN MOVIMIENTO para "
              f"que se vea el velocímetro) y pulsa {tecla} para capturar.")
        hk = entrada.Hotkeys([tecla])
        while tecla not in hk.leer():
            time.sleep(0.02)
    else:
        for i in range(espera, 0, -1):
            print(f"Capturando en {i}... (cambia al juego)")
            time.sleep(1)
    titulo = entrada.titulo_ventana_activa()
    rect = ventana.buscar()
    with mss.mss() as sct:
        if rect:
            mon = {"left": rect[0], "top": rect[1], "width": rect[2], "height": rect[3]}
        else:
            mon = sct.monitors[1]
        img = cv2.cvtColor(np.asarray(sct.grab(mon)), cv2.COLOR_BGRA2BGR)
    cv2.imwrite(_captura(), img)
    print(f"Captura guardada en {_captura()}" + (f" (ventana del juego {rect[2]}x{rect[3]})" if rect else
                                                 " (no encontré la ventana del juego: pantalla completa)"))
    if continuar is not None:
        print("Ahora sal del juego con ALT+TAB (o pausa con ESC) y pulsa CONTINUAR en el programa.")
        continuar()
    else:
        print("\nAhora sal del juego con ALT+TAB (o pausa con ESC) y pulsa ENTER aquí en la consola.")
        input()
    return img, (mon["left"], mon["top"]), rect, titulo


def calibrar(config=None, solo=None, imagen=None, espera=0, continuar=None):
    """Calibración (3.0.0: automática + confirmar). continuar(): espera a que el usuario siga (interfaz)."""
    import geometria
    ruta_cfg = config
    cfg = configuracion.cargar(ruta_cfg)

    if imagen:
        img, origen, rect, titulo = cv2.imread(imagen), (0, 0), None, ""
        if img is None:
            print(f"[!] No se pudo abrir la imagen {imagen}")
            return
        rect = (0, 0, img.shape[1], img.shape[0])          # se toma la imagen como la ventana del juego
    else:
        tecla = entrada.validar_tecla(cfg["teclas"].get("capturar", "F11"), "capturar")
        img, origen, rect, titulo = capturar_juego(espera, tecla, continuar)
        print(f"Ventana activa: '{titulo}'")
    ox, oy = origen

    if solo == "carril":
        if calibrar_carril(img, cfg, origen=origen, rect=rect):
            configuracion.guardar(cfg, ruta_cfg)
            print(f"Guardado en {cfg.get('_ruta')}")
        return
    if solo == "yolo":                                  # 3.6.0
        if rect:
            try:
                geometria.preparar(cfg, rect=rect, persistir=False, avisar=False)
            except Exception as e:  # noqa
                print(f"   (No se pudo ubicar la calibración en esta ventana: {e})")
        if mascara_yolo(img, cfg, origen=origen, rect=rect):
            configuracion.guardar(cfg, ruta_cfg)
            print(f"Guardado en {cfg.get('_ruta')}")
        return

    if solo == "color":                                 # 3.9.0: solo el color de la línea del GPS
        import copy
        c2 = copy.deepcopy(cfg)
        try:
            if rect:
                geometria.preparar(c2, rect=rect, persistir=False, avisar=False)
        except Exception as e:  # noqa
            print(f"   (No se pudo ubicar la calibración en esta ventana: {e})")
        m = dict(c2["minimapa"])
        m["x"], m["y"] = int(m["x"]) - ox, int(m["y"]) - oy
        mini = vision.recortar_minimapa(img, m)
        if mini is None or not getattr(mini, "size", 0):
            print("[!] No encontré el minimapa en la captura. Calibra todo primero («Calibrar todo»).")
            return
        rangos = _color_ruta(mini, cfg)
        if rangos != cfg["color_ruta_hsv"]:
            cfg["color_ruta_hsv"] = rangos
            configuracion.guardar(cfg, ruta_cfg)
            print(f"Color de la ruta guardado en {cfg.get('_ruta')}: {rangos}")
        else:
            print("Color de la ruta sin cambios.")
        return

    det = autodetectar(img)
    mm = det["minimapa"]
    vr = det["velocimetro"]
    if vr is None:                                      # no se vio el texto: la región guardada (si cae dentro)
        rv0 = cfg["velocimetro"].get("region")
        if rv0 and 0 <= rv0["x"] - ox < img.shape[1] and 0 <= rv0["y"] - oy < img.shape[0]:
            vr = {"x": rv0["x"] - ox, "y": rv0["y"] - oy, "w": rv0["w"], "h": rv0["h"]}
    cfg["jugador"] = {"x": geometria.REF_JUGADOR[0], "y": geometria.REF_JUGADOR[1]}
    for k in geometria.RADIOS:                          # radios en la unidad fija (los de siempre)
        cfg["vision"][k] = configuracion.DEFAULTS["vision"][k]
    print(f"\nDetectado: minimapa {mm} ({det['como']}), velocímetro {vr}")

    alto = img.shape[0]
    esc = min(1.0, 1000 / alto, 1700 / img.shape[1])
    nombre = "Calibracion: revisa los recuadros"
    while True:
        lect, c = _lecturas(img, cfg, mm, vr)
        ventana_encima(nombre)
        cv2.imshow(nombre, _dibujar(img, c, lect, det["como"], esc))
        k = cv2.waitKey(0) & 0xFF
        if k in (13, 10):
            break
        if k == 27:
            cv2.destroyAllWindows()
            print("Cancelado: no se guardó nada.")
            return
        if k in (ord("m"), ord("M")):
            cv2.destroyWindow(nombre)
            ventana_encima("Marca el minimapa y pulsa ENTER")
            x, y, w, h = cv2.selectROI("Marca el minimapa y pulsa ENTER", cv2.resize(img, None, fx=esc, fy=esc),
                                       showCrosshair=False)
            cv2.destroyWindow("Marca el minimapa y pulsa ENTER")
            if w and h:
                mm = {k_: int(round(v_ / esc)) for k_, v_ in zip("xywh", (x, y, w, h))}
                det["como"] = "a mano"
        if k in (ord("f"), ord("F")):
            s0 = mm["w"] / geometria.REF_W
            actual = (mm["x"] + geometria.REF_JUGADOR[0] * s0, mm["y"] + geometria.REF_JUGADOR[1] * s0)
            p_ = elegir_flecha(img, mm, actual)
            punto = [p_] if p_ else []
            if punto:
                s = mm["w"] / geometria.REF_W
                mm = dict(mm, x=int(round(punto[0][0] - geometria.REF_JUGADOR[0] * s)),
                          y=int(round(punto[0][1] - geometria.REF_JUGADOR[1] * s)))
                det["como"] += " + flecha a mano"
        if k in (ord("v"), ord("V")):
            cv2.destroyWindow(nombre)
            ventana_encima("Marca el velocimetro (deja sitio para 3 cifras) y ENTER")
            x, y, w, h = cv2.selectROI("Marca el velocimetro (deja sitio para 3 cifras) y ENTER",
                                       cv2.resize(img, None, fx=esc, fy=esc), showCrosshair=False)
            cv2.destroyWindow("Marca el velocimetro (deja sitio para 3 cifras) y ENTER")
            if w and h:
                vr = {k_: int(round(v_ / esc)) for k_, v_ in zip("xywh", (x, y, w, h))}
        if k in (ord("c"), ord("C")):
            mini = vision.recortar_minimapa(img, _cfg_prueba(cfg, mm, vr)["minimapa"])
            if mini is not None:
                cfg["color_ruta_hsv"] = _color_ruta(mini, cfg)
    cv2.destroyAllWindows()

    # guardar: posiciones absolutas (pantalla) + relativas a la ventana
    cfg["minimapa"] = {"x": mm["x"] + ox, "y": mm["y"] + oy, "w": mm["w"], "h": mm["h"]}
    if vr:
        cfg["velocimetro"]["region"] = {"x": vr["x"] + ox, "y": vr["y"] + oy, "w": vr["w"], "h": vr["h"]}
    rect_abs = (rect[0], rect[1], rect[2], rect[3]) if (rect and not imagen) else \
        ((ox, oy, img.shape[1], img.shape[0]) if imagen else None)
    if rect_abs:
        cfg["calibracion"] = geometria.desde_absoluto(rect_abs, cfg["minimapa"], cfg["velocimetro"].get("region"),
                                                      cfg.get("carril", {}).get("trapecio"))
    else:
        cfg["calibracion"] = None
        print("[i] No encontré la ventana del juego: se guardan posiciones fijas de pantalla. Calibra con el "
              "juego abierto para que se ajuste solo a la ventana.")
    if titulo and not cfg.get("ventana_juego"):
        cfg["ventana_juego"] = "Grand Theft Auto"
    print("\n¿Calibrar ahora la cámara de carril? (opcional; necesitas la captura en una recta, centrado)")
    calibrar_carril(img, cfg, origen=origen, rect=rect_abs)
    configuracion.guardar(cfg, ruta_cfg)
    print(f"\nGuardado en {cfg.get('_ruta')}:")
    print(f"  minimapa {cfg['minimapa']} (unidad de las reglas {geometria.REF_W}x{geometria.REF_H})")
    print(f"  velocímetro {cfg['velocimetro'].get('region')}")
    if cfg.get("calibracion"):
        print(f"  relativo a la ventana {cfg['calibracion']['ventana'][0]}x{cfg['calibracion']['ventana'][1]}: "
              "puedes mover la ventana o cambiar la resolución sin recalibrar.")


if __name__ == "__main__":
    main()

"""
3.0.0: calibración independiente de la resolución.

Antes todo se guardaba en píxeles de la pantalla, así que con otra resolución, o con la ventana movida,
había que calibrar de nuevo, y las reglas (desplazamientos, trazados) se veían a otra escala.

Ahora:
  * La calibración se guarda RELATIVA a la ventana del juego (config.json -> "calibracion"):
      - minimapa:     distancia al borde izquierdo y al de abajo, ancho y alto, en unidades del ALTO de la ventana
                      (GTA dibuja el minimapa anclado abajo a la izquierda y lo escala con el alto)
      - velocímetro:  igual, pero anclado abajo a la DERECHA
      - carril:       las 4 esquinas como fracción del ancho y el alto de la ventana
  * Al arrancar se busca la ventana del juego (ventana.py) y se calculan las posiciones reales.
    Si la ventana se mueve o cambia de tamaño, se recalculan solas.
  * El minimapa se captura en su tamaño real y se REDIMENSIONA a un tamaño fijo de referencia
    (REF_W x REF_H = el del PC donde se hicieron las reglas). Todo lo que se mide en píxeles del minimapa
    (reglas, trazados, radios, la flecha del jugador...) queda en esa misma unidad en cualquier resolución.
  * Los textos del HUD (distancia, zona, notificaciones) también se llevan a esa escala antes de leerlos.

En tiempo de ejecución cfg["minimapa"] queda así:
    {"x", "y": posición real en pantalla, "w": REF_W, "h": REF_H, "w_real", "h_real": tamaño real}
"""
import cv2

REF_W, REF_H = 272, 180          # unidad de las reglas: minimapa de 272 x 180 px (ventana de 1914 x 1051)
REF_JUGADOR = (135, 136)         # la flecha del jugador en esa unidad
REF_VENTANA_H = 1051
VERSION_CAL = 1

# velocímetro por defecto (anclado abajo a la derecha, en unidades del alto de la ventana)
VEL_DEF = [0.0, 31.0 / REF_VENTANA_H, 225.0 / REF_VENTANA_H, 55.0 / REF_VENTANA_H]


# ------------------------------------------------------------------ medidas
def tam_real(m):
    """(ancho, alto) reales del minimapa en pantalla."""
    return float(m.get("w_real", m["w"])), float(m.get("h_real", m["h"]))


def escala_hud(cfg):
    """Factor para llevar un recorte del HUD a la escala de referencia (1.0 = igual que el PC de las reglas)."""
    _w, h = tam_real(cfg["minimapa"])
    return REF_H / h if h > 0 else 1.0


def a_referencia(img, cfg, minimo=0.05):
    """Redimensiona un recorte del HUD a la escala de referencia (si hace falta)."""
    if img is None:
        return None
    f = escala_hud(cfg)
    if abs(f - 1.0) < minimo or img.size == 0:
        return img
    return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)


def region_ampliada_real(cfg, margen_ref):
    """Región de captura alrededor del minimapa (real) con un margen dado en unidad de referencia,
    con tamaño de salida en la unidad de referencia (para Rumbo)."""
    m = cfg["minimapa"]
    wr, hr = tam_real(m)
    f = hr / REF_H
    mr = int(round(margen_ref * f))
    return {"x": int(m["x"]) - mr, "y": int(m["y"]) - mr, "w": int(m["w"]) + 2 * int(margen_ref),
            "h": int(m["h"]) + 2 * int(margen_ref), "w_real": int(round(wr)) + 2 * mr, "h_real": int(round(hr)) + 2 * mr}


# ------------------------------------------------------------------ relativo <-> absoluto
def desde_absoluto(rect, minimapa, vel_region=None, trapecio=None):
    """Calibración relativa a partir de posiciones absolutas (en pantalla) y el rect de la ventana."""
    X, Y, W, H = rect
    x, y, w, h = (float(minimapa[k]) for k in ("x", "y", "w", "h"))
    cal = {"version": VERSION_CAL, "ventana": [int(W), int(H)],
           "minimapa": [round((x - X) / H, 5), round((Y + H - (y + h)) / H, 5), round(w / H, 5), round(h / H, 5)]}
    if vel_region:
        vx, vy, vw, vh = (float(vel_region[k]) for k in ("x", "y", "w", "h"))
        cal["velocimetro"] = [round((X + W - (vx + vw)) / H, 5), round((Y + H - (vy + vh)) / H, 5),
                              round(vw / H, 5), round(vh / H, 5)]
    if trapecio:
        cal["carril"] = [[round((px - X) / W, 5), round((py - Y) / H, 5)] for px, py in trapecio]
    return cal


def a_absoluto(cal, rect):
    """Posiciones absolutas {minimapa, velocimetro, trapecio} para la ventana `rect`."""
    X, Y, W, H = rect
    iz, ab, w, h = cal["minimapa"]
    mm = {"x": int(round(X + iz * H)), "y": int(round(Y + H - ab * H - h * H)),
          "w": int(round(w * H)), "h": int(round(h * H))}
    out = {"minimapa": mm, "velocimetro": None, "trapecio": None}
    if cal.get("velocimetro"):
        de, ab, vw, vh = cal["velocimetro"]
        out["velocimetro"] = {"x": int(round(X + W - de * H - vw * H)), "y": int(round(Y + H - ab * H - vh * H)),
                              "w": int(round(vw * H)), "h": int(round(vh * H))}
    if cal.get("carril"):
        out["trapecio"] = [[int(round(X + fx * W)), int(round(Y + fy * H))] for fx, fy in cal["carril"]]
    return out


def avisos_ventana(cal, rect):
    """Textos de aviso si la ventana cambió mucho desde la calibración."""
    if not cal or not cal.get("ventana") or not rect:
        return []
    W0, H0 = cal["ventana"]
    _x, _y, W, H = rect
    out = []
    if (W, H) != (W0, H0):
        a0, a1 = W0 / H0, W / H
        if abs(a1 - a0) / a0 > 0.03:
            out.append(f"La ventana del juego cambió de proporción ({W0}x{H0} -> {W}x{H}). El minimapa y el HUD "
                       "se ajustan solos, pero la cámara de carril puede quedar corrida: recalibra si notas algo raro.")
        else:
            out.append(f"La ventana del juego cambió de tamaño ({W0}x{H0} -> {W}x{H}): ajusto las zonas solo.")
    return out


# ------------------------------------------------------------------ preparar la configuración en ejecución
def preparar(cfg, rect="buscar", persistir=True, avisar=True):
    """Calcula las posiciones reales para esta ventana y deja cfg listo para el autopiloto.
    - Con la ventana encontrada y calibración relativa: usa la relativa.
    - Con la ventana y una calibración vieja (solo absoluta): la convierte y la guarda (una vez).
    - Sin la ventana (juego cerrado, o no es Windows): usa las posiciones absolutas guardadas.
    Devuelve el rect usado (o None)."""
    import ventana
    if rect == "buscar":
        rect = ventana.buscar(cfg.get("ventana_juego") or "Grand Theft Auto")
    m = cfg["minimapa"]
    wr, hr = tam_real(m)
    m_abs = {"x": m["x"], "y": m["y"], "w": wr, "h": hr}
    cal = cfg.get("calibracion")
    if rect is not None and not cal:
        cal = desde_absoluto(rect, m_abs, cfg.get("velocimetro", {}).get("region"),
                             cfg.get("carril", {}).get("trapecio"))
        cfg["calibracion"] = cal
        if persistir:
            _guardar_calibracion(cfg, cal)
        if avisar:
            print(f"[i] Calibración convertida al formato 3.0.0 (relativa a la ventana del juego "
                  f"{rect[2]}x{rect[3]}). Ahora puedes mover la ventana sin recalibrar.")
    if rect is not None and cal:
        ab = a_absoluto(cal, rect)
        m_abs = ab["minimapa"]
        if ab["velocimetro"]:
            cfg["velocimetro"]["region"] = ab["velocimetro"]
        if ab["trapecio"]:
            cfg.setdefault("carril", {})["trapecio"] = ab["trapecio"]
        if avisar:
            for a in avisos_ventana(cal, rect):
                print("[i] " + a)
    cfg["minimapa"] = {"x": int(m_abs["x"]), "y": int(m_abs["y"]), "w": REF_W, "h": REF_H,
                       "w_real": int(round(m_abs["w"])), "h_real": int(round(m_abs["h"]))}
    cfg["_ventana"] = list(rect) if rect else None
    return rect


def _guardar_calibracion(cfg, cal):
    """Guarda solo la clave "calibracion" en el config.json del disco (sin tocar lo demás)."""
    ruta = cfg.get("_ruta")
    if not ruta:
        return
    try:
        import configuracion
        disco = configuracion.cargar(ruta, guardar_migracion=False)
        disco["calibracion"] = cal
        configuracion.guardar(disco, ruta)
    except Exception as e:  # noqa
        print(f"[!] No se pudo guardar la calibración convertida: {e}")


# ------------------------------------------------------------------ conversión de unidades (config vieja)
RADIOS = ("radio_cerca", "radio_lejos", "radio_anticipacion", "radio_inicio", "radio_ajuste", "max_dist_inicio")


def convertir_unidades(usuario):
    """config.json de antes de la 3.0.0: la flecha del jugador y los radios de visión estaban en píxeles del
    minimapa REAL. Se pasan a la unidad de referencia (REF_W x REF_H). Devuelve True si cambió algo."""
    m = usuario.get("minimapa")
    if not m or not m.get("w") or not m.get("h"):
        return False
    fx, fy = REF_W / float(m["w"]), REF_H / float(m["h"])
    if abs(fx - 1) < 0.005 and abs(fy - 1) < 0.005:
        return False
    j = usuario.get("jugador")
    if j:
        usuario["jugador"] = {"x": round(float(j["x"]) * fx, 1), "y": round(float(j["y"]) * fy, 1)}
    f = min(fx, fy)
    v = usuario.get("vision", {})
    for k in RADIOS:
        if k in v:
            v[k] = round(float(v[k]) * f, 1)
    return True

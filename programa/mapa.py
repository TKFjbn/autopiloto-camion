"""
Mapa de la ruta (2.4.0, experimental).

Se arma desde el CSV de un viaje hecho con el rumbo exacto (columna rumbo_abs): con el rumbo y la velocidad se
va trazando el camino (como un GPS de papel), y cada punto queda con su "metros al punto" del HUD, que es lo que
usan las reglas. Así cada regla, trazado y grabación se puede dibujar en su lugar.

    datos/mapas/<recorrido>.json
      {"recorrido": "Drogas - Granja 1", "origen": "viaje_....csv",
       "tramos": {"0": [[metros, x, y], ...], "1": [...], "2": [...]}}     x = este, y = norte, en metros
"""
import csv
import math
import os
import re
import time

import carpetas

CARPETA = os.path.join(carpetas.DATOS, "mapas")
PASO_M = 5.0


def _slug(t):
    t = (t or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "recorrido"


def ruta_archivo(recorrido):
    return os.path.join(CARPETA, _slug(recorrido) + ".json")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def leer_viaje(ruta_csv):
    with open(ruta_csv, encoding="utf-8", errors="ignore") as fh:
        filas = list(csv.DictReader(l for l in fh if not l.startswith("#")))
    return filas


def tiene_rumbo(ruta_csv):
    try:
        with open(ruta_csv, encoding="utf-8", errors="ignore") as fh:
            for l in fh:
                if not l.startswith("#"):
                    return "rumbo_abs" in l
    except Exception:  # noqa
        pass
    return False


def construir(filas):
    """{recorrido: {tramo: [[metros, x, y], ...]}} desde las filas de un viaje."""
    x = y = 0.0
    t_prev = None
    rumbo = None
    s_odo = 0.0
    por_tramo = {}            # (recorrido, tramo) -> lista de puntos
    estado_t = {}             # (recorrido, tramo) -> {"min": ..., "hud": ..., "odo_hud": ...}
    recorrido_tramo = {}
    segmentos = {}            # tramos interrumpidos por un salto de etapa: se queda el más largo
    for f in filas:
        t = _f(f.get("t"))
        if t is None:
            continue
        dt = 0.0 if t_prev is None else max(0.0, min(0.5, t - t_prev))
        t_prev = t
        r = _f(f.get("rumbo_abs"))
        if r is not None:
            rumbo = r
        kmh = _f(f.get("kmh")) or 0.0
        v = kmh / 3.6
        # marcha atrás: maniobra con freno y sin acelerador
        if f.get("estado") == "RECUPERANDO" and (_f(f.get("freno")) or 0) > 0 and (_f(f.get("acelerador")) or 0) == 0:
            v = -v
        if rumbo is not None:
            x += v * dt * math.sin(math.radians(rumbo))
            y += v * dt * math.cos(math.radians(rumbo))
        s_odo += v * dt
        try:
            tramo = int(f.get("tramo") or 0)
        except ValueError:
            tramo = 0
        rec = (f.get("ruta") or "").strip()
        if rec:
            recorrido_tramo[tramo] = rec
        d = _f(f.get("dist_punto_m"))
        if rumbo is None or d is None:
            continue
        clave = tramo
        e = estado_t.get(clave)
        if e is not None and d > e["min"] + 400:
            # ¿etapa nueva (la distancia saltó) o una lectura mala del HUD? Se confirma con 3 lecturas seguidas
            if e.get("t_salto") is None or abs(d - e.get("d_salto", d)) >= 60:
                e["t_salto"], e["d_salto"] = t, d
            if t - e["t_salto"] < 4.0:                 # una mala lectura del HUD dura 1-3 s
                continue
            segs = segmentos.setdefault(clave, [])
            segs.append(por_tramo.get(clave, []))
            e = None
        if e is None:
            e = estado_t[clave] = {"min": d, "hud": d, "odo_hud": s_odo}
            por_tramo[clave] = []
        e["t_salto"] = None
        if d < e["hud"] - 150:
            # bajada brusca: casi siempre una mala lectura del HUD (p. ej. 1060 en vez de 3060); 3 lecturas
            if e.get("t_baja") is None or abs(d - e.get("d_baja", d)) >= 60:
                e["t_baja"], e["d_baja"] = t, d
            if t - e["t_baja"] < 4.0:
                continue
        e["t_baja"] = None
        if d != e["hud"]:
            e["hud"], e["odo_hud"] = d, s_odo
        paso = 10.0 if d >= 1000 else 1.0
        m = e["hud"] - (s_odo - e["odo_hud"])                  # entre lecturas del HUD: odometría
        m = max(e["hud"] - paso, min(e["hud"] + paso, m))
        if m > e["min"] + 3:                                     # va hacia atrás o volvió por la ruta: no se dibuja
            continue
        e["min"] = min(e["min"], m)
        pts = por_tramo[clave]
        if not pts or pts[-1][0] - m >= PASO_M:
            pts.append([round(m, 1), round(x, 1), round(y, 1)])
    for clave, segs in segmentos.items():
        candidatos = segs + [por_tramo.get(clave, [])]
        por_tramo[clave] = max(candidatos, key=lambda p: (p[0][0] - p[-1][0]) if len(p) > 1 else 0)
    salida = {}
    for tramo, pts in por_tramo.items():
        if len(pts) < 10:
            continue
        rec = recorrido_tramo.get(tramo) or recorrido_tramo.get(1) or recorrido_tramo.get(2) or ""
        if tramo == 0:
            rec = recorrido_tramo.get(1) or rec               # el camino a cargar va con el recorrido del viaje
        salida.setdefault(rec, {})[str(tramo)] = pts
    return salida


def guardar(recorrido, tramos, origen):
    import version
    os.makedirs(CARPETA, exist_ok=True)
    ruta = ruta_archivo(recorrido)
    previo = carpetas.leer_json(ruta, {}) if os.path.exists(ruta) else {}
    t = dict(previo.get("tramos") or {})
    t.update(tramos)                                 # se reemplazan solo los tramos que trae este viaje
    datos = {"formato": 1, "programa_minimo": "2.4.0", "recorrido": recorrido, "origen": os.path.basename(origen),
             "fecha": time.strftime("%Y-%m-%d %H:%M"), "programa": version.VERSION, "tramos": t}
    carpetas.guardar_json(ruta, datos)
    return ruta


def desde_viaje(ruta_csv, solo_si_falta=False):
    """Arma y guarda los mapas de un viaje. Devuelve [(recorrido, tramos, archivo)]."""
    if not tiene_rumbo(ruta_csv):
        raise ValueError("ese viaje no tiene rumbo (se grabó con una versión anterior a la 2.4.0 o sin "
                         "«Rumbo exacto» en Experimental)")
    mapas = construir(leer_viaje(ruta_csv))
    hechos = []
    for rec, tramos in mapas.items():
        if not rec or "desconocido" in rec:
            continue
        if solo_si_falta:
            previo = cargar(rec)
            tramos = {k: v for k, v in tramos.items() if k not in ((previo or {}).get("tramos") or {})}
            if not tramos:
                continue
        hechos.append((rec, sorted(tramos), guardar(rec, tramos, ruta_csv)))
    return hechos


def cargar(recorrido):
    ruta = ruta_archivo(recorrido)
    return carpetas.leer_json(ruta, None) if os.path.exists(ruta) else None


def lista():
    if not os.path.isdir(CARPETA):
        return []
    out = []
    for n in sorted(os.listdir(CARPETA)):
        if n.endswith(".json"):
            d = carpetas.leer_json(os.path.join(CARPETA, n), {})
            if d.get("recorrido"):
                out.append(d["recorrido"])
    return out


def punto_en(pts, metros):
    """(x, y, ángulo) del mapa en esa distancia al punto (interpolando), o None."""
    if not pts or metros is None:
        return None
    if metros >= pts[0][0]:
        a, b = pts[0], pts[1]
    elif metros <= pts[-1][0]:
        a, b = pts[-2], pts[-1]
    else:
        lo, hi = 0, len(pts) - 1
        while hi - lo > 1:                     # metros va bajando en la lista
            mid = (lo + hi) // 2
            if pts[mid][0] >= metros:
                lo = mid
            else:
                hi = mid
        a, b = pts[lo], pts[hi]
    f = 0.0 if a[0] == b[0] else (a[0] - metros) / (a[0] - b[0])
    f = max(0.0, min(1.0, f))
    x = a[1] + (b[1] - a[1]) * f
    y = a[2] + (b[2] - a[2]) * f
    return x, y, math.atan2(b[1] - a[1], b[2] - a[2])


def tramo_entre(pts, desde, hasta):
    """Puntos del mapa entre dos distancias (desde > hasta), con los extremos interpolados."""
    if not pts:
        return []
    dentro = [(p[1], p[2]) for p in pts if hasta <= p[0] <= desde]
    a, b = punto_en(pts, desde), punto_en(pts, hasta)
    out = ([a[:2]] if a else []) + dentro + ([b[:2]] if b else [])
    return out if len(out) >= 2 else []

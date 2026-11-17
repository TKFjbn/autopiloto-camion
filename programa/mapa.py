"""
Mapa de la ruta (2.4.0, experimental).

Se arma desde el CSV de un viaje hecho con el rumbo exacto (columna rumbo_abs): con el rumbo y la velocidad se
va trazando el camino (como un GPS de papel), y cada punto queda con su "metros al punto" del HUD, que es lo que
usan las reglas. Así cada regla, trazado y grabación se puede dibujar en su lugar.

    datos/mapas/<recorrido>.json
      {"recorrido": "Drogas - Granja 1", "origen": "viaje_....csv",
       "tramos": {"1": [[metros, x, y], ...], "2": [...]}}     x = este, y = norte, en metros
       "calles": {"1": [[metros, "Strawberry Avenue"], ...]}, "zonas": {"1": [[metros, "Vinewood Hills"], ...]}

3.3.0: el camino a cargar es uno solo para todos los recorridos (datos/mapas/_camino_a_cargar.json): se juntan
los viajes, alineados por el punto de carga; lo que cada viaje hizo antes de llegar a la calle común es su
"aparición" (el camión aparece en distintos lugares del depósito).
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


def _etiquetas(lista, minimo=80):
    """[(metros, nombre)] en orden de viaje (metros bajando) -> [[metros, nombre]] donde empieza cada nombre.
    Los tramos más cortos que 'minimo' (lecturas sueltas o cruces) se descartan."""
    tramos = []
    for m, n in lista:
        if not n:
            continue
        if tramos and tramos[-1][1] == n:
            tramos[-1][2] = m
        else:
            tramos.append([m, n, m])
    largos = [t for t in tramos if t[0] - t[2] >= minimo]
    out = []
    for m0, n, _m1 in largos:
        if not out or out[-1][1] != n:
            out.append([round(m0, 1), n])
    return out


def construir(filas, extras=None):
    """{recorrido: {tramo: [[metros, x, y], ...]}} desde las filas de un viaje.
    3.3.0: si se pasa 'extras' (dict), se llena con {recorrido: {tramo: {"calles": [...], "zonas": [...]}}}."""
    x = y = 0.0
    t_prev = None
    rumbo = None
    s_odo = 0.0
    por_tramo = {}            # (recorrido, tramo) -> lista de puntos
    estado_t = {}             # (recorrido, tramo) -> {"min": ..., "hud": ..., "odo_hud": ...}
    recorrido_tramo = {}
    nombres = {}              # 3.3.0: tramo -> [(metros, calle, zona)] de los puntos guardados
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
            nombres.setdefault(("viejo", clave), []).append(nombres.get(clave, []))
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
            if not pts:
                nombres[clave] = []
            pts.append([round(m, 1), round(x, 1), round(y, 1)])
            nombres[clave].append((m, (f.get("calle") or "").strip(), (f.get("zona") or "").strip()))
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
        if extras is not None:
            todos = nombres.get(tramo, []) + [x for l in nombres.get(("viejo", tramo), []) for x in l]
            desde, hasta = pts[0][0], pts[-1][0]
            sel = sorted([n for n in todos if hasta - 1 <= n[0] <= desde + 1], key=lambda n: -n[0])
            extras.setdefault(rec, {})[str(tramo)] = {
                "calles": _etiquetas([(m, c) for m, c, _z in sel], 60),
                "zonas": _etiquetas([(m, z) for m, _c, z in sel], 150)}
    return salida


def guardar(recorrido, tramos, origen, extras=None):
    import version
    os.makedirs(CARPETA, exist_ok=True)
    ruta = ruta_archivo(recorrido)
    previo = carpetas.leer_json(ruta, {}) if os.path.exists(ruta) else {}
    t = dict(previo.get("tramos") or {})
    t.update(tramos)                                 # se reemplazan solo los tramos que trae este viaje
    t.pop("0", None)                                 # 3.3.0: el camino a cargar va aparte (_camino_a_cargar.json)
    calles = dict(previo.get("calles") or {})
    zonas = dict(previo.get("zonas") or {})
    for k, e in (extras or {}).items():
        if k in tramos and k != "0":
            calles[k], zonas[k] = e.get("calles", []), e.get("zonas", [])
    datos = {"formato": 1, "programa_minimo": "2.4.0", "recorrido": recorrido, "origen": os.path.basename(origen),
             "fecha": time.strftime("%Y-%m-%d %H:%M"), "programa": version.VERSION, "tramos": t,
             "calles": calles, "zonas": zonas}
    carpetas.guardar_json(ruta, datos)
    return ruta


def desde_viaje(ruta_csv, solo_si_falta=False, renombrar=None):
    """Arma y guarda los mapas de un viaje. Devuelve [(recorrido, tramos, archivo)].
    renombrar (3.7.1): {nombre en el viaje: nombre nuevo} (la ruta nueva que se nombró en las observaciones)."""
    if not tiene_rumbo(ruta_csv):
        raise ValueError("ese viaje no tiene rumbo (se grabó con una versión anterior a la 2.4.0 o sin "
                         "«Rumbo exacto» en Experimental)")
    extras = {}
    filas = leer_viaje(ruta_csv)
    if renombrar:
        for f in filas:
            r = (f.get("ruta") or "").strip()
            if r in renombrar:
                f["ruta"] = renombrar[r]
    mapas = construir(filas, extras)
    hechos = []
    for rec, tramos in mapas.items():
        if "0" in tramos:                            # 3.3.0: camino a cargar común a todos los recorridos
            if agregar_camino(tramos["0"], (extras.get(rec) or {}).get("0", {}), ruta_csv):
                hechos.append((NOMBRE_CAMINO, ["0"], ruta_camino()))
        tramos = {k: v for k, v in tramos.items() if k != "0"}
        if not rec or "desconocido" in rec or not tramos:
            continue
        if solo_si_falta:
            previo = cargar(rec)
            if previo:                                # 3.3.0: los mapas viejos no tenían calles ni zonas
                completar_nombres(rec, previo, extras.get(rec) or {})
            tramos = {k: v for k, v in tramos.items() if k not in ((previo or {}).get("tramos") or {})}
            if not tramos:
                continue
        hechos.append((rec, sorted(tramos), guardar(rec, tramos, ruta_csv, extras.get(rec))))
    return hechos


def completar_nombres(recorrido, previo, extras):
    """Agrega calles y zonas a un mapa que ya existía y no las tenía (no toca la ruta)."""
    cambio = False
    for clave in ("calles", "zonas"):
        d = previo.setdefault(clave, {})
        for k, e in extras.items():
            if k != "0" and k in (previo.get("tramos") or {}) and not d.get(k) and e.get(clave):
                d[k] = e[clave]
                cambio = True
    if cambio:
        carpetas.guardar_json(ruta_archivo(recorrido), previo)
    return cambio


# ------------------------------------------------------------------ 3.3.0: camino a cargar común
NOMBRE_CAMINO = "Camino a cargar"
MAX_VIAJES_CAMINO = 8
UNION_M = 12.0          # a menos de esto de la ruta común, el viaje ya va por la calle común


def ruta_camino():
    return os.path.join(CARPETA, "_camino_a_cargar.json")


def camino_valido(pts):
    """Un camino a cargar de verdad: llega al punto de carga y empieza cerca (no un viaje marcado mal como etapa 0)."""
    if not (len(pts) >= 10 and pts[-1][0] <= 40 and pts[0][0] <= 1500):
        return False
    largo = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(pts, pts[1:]))
    return largo <= 1.6 * (pts[0][0] - pts[-1][0]) + 60      # si anduvo mucho más que lo que bajó la distancia, no


def agregar_camino(pts, extras, origen):
    """Suma el camino a cargar de un viaje al mapa común (si no estaba ya). Devuelve True si lo agregó."""
    if not camino_valido(pts):
        return False
    os.makedirs(CARPETA, exist_ok=True)
    ruta = ruta_camino()
    previo = carpetas.leer_json(ruta, {}) if os.path.exists(ruta) else {}
    viajes = [v for v in previo.get("viajes", []) if v.get("origen") != os.path.basename(origen)]
    viajes.append({"origen": os.path.basename(origen), "pts": pts,
                   "calles": (extras or {}).get("calles", []), "zonas": (extras or {}).get("zonas", [])})
    viajes = viajes[-MAX_VIAJES_CAMINO:]
    import version
    carpetas.guardar_json(ruta, {"formato": 1, "programa_minimo": "3.3.0", "recorrido": NOMBRE_CAMINO,
                                 "fecha": time.strftime("%Y-%m-%d %H:%M"), "programa": version.VERSION,
                                 "viajes": viajes})
    return True


def migrar_camino():
    """3.3.0: los caminos a cargar que estaban dentro de cada recorrido pasan al mapa común (una vez)."""
    if not os.path.isdir(CARPETA):
        return 0
    n = 0
    for nom in sorted(os.listdir(CARPETA)):
        if not nom.endswith(".json") or nom.startswith("_"):
            continue
        ruta = os.path.join(CARPETA, nom)
        d = carpetas.leer_json(ruta, {})
        t0 = (d.get("tramos") or {}).get("0")
        if t0:
            if agregar_camino(t0, {}, f"{d.get('origen') or nom} (de {d.get('recorrido', nom)})"):
                n += 1
            d["tramos"].pop("0", None)
            carpetas.guardar_json(ruta, d)
    return n


def _dist_a_linea(x, y, linea):
    mejor = 1e9
    for (ax, ay), (bx, by) in zip(linea, linea[1:]):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
        px, py = ax + t * dx, ay + t * dy
        mejor = min(mejor, math.hypot(x - px, y - py))
    return mejor


ALINEAR_M = 150.0       # metros antes del punto de carga que se usan para superponer los viajes


def _ajuste_rigido(a, b):
    """Giro y corrimiento que llevan los puntos a sobre los b (mínimos cuadrados). Devuelve (ángulo, dx, dy)."""
    if len(a) < 2:
        return 0.0, (b[0][0] - a[0][0]) if a else 0.0, (b[0][1] - a[0][1]) if a else 0.0
    ax = sum(p[0] for p in a) / len(a)
    ay = sum(p[1] for p in a) / len(a)
    bx = sum(p[0] for p in b) / len(b)
    by = sum(p[1] for p in b) / len(b)
    sxx = sum((p[0] - ax) * (q[0] - bx) + (p[1] - ay) * (q[1] - by) for p, q in zip(a, b))
    sxy = sum((p[0] - ax) * (q[1] - by) - (p[1] - ay) * (q[0] - bx) for p, q in zip(a, b))
    ang = math.atan2(sxy, sxx)
    if abs(ang) > math.radians(25):                 # más que eso no es error de rumbo: solo correr
        ang = 0.0
    c, s = math.cos(ang), math.sin(ang)
    return ang, bx - (c * ax - s * ay), by - (s * ax + c * ay)


def combinar_camino(datos):
    """De los viajes guardados arma:
      pts: la ruta común (desde donde el camión ya va por la calle hasta el punto de carga),
      apariciones: [{"x", "y", "m", "rama": [[x, y], ...], "origen"}] lo que hizo cada viaje antes de la calle común,
      comun_desde: metros desde los que la ruta es la misma para todos (antes, la distancia depende de dónde
                   apareció el camión), calles, zonas."""
    viajes = [v for v in (datos or {}).get("viajes", []) if camino_valido(v.get("pts", []))]
    if not viajes:
        return None
    # alinear todos con la referencia: en los últimos metros antes del punto de carga todos van por el mismo
    # camino, así que se busca el giro y el corrimiento que mejor los superponen (el rumbo de cada viaje puede
    # venir girado unos grados y la velocidad acumula error)
    ref = max(viajes, key=lambda v: len(v["pts"]))
    m_fin = max(v["pts"][-1][0] for v in viajes)
    m_ini = min(min(v["pts"][0][0] for v in viajes), m_fin + ALINEAR_M)
    muestras = [m_fin + (m_ini - m_fin) * k / 20.0 for k in range(21)]
    pr = [punto_en(ref["pts"], m) for m in muestras]
    alineados = []
    for v in viajes:
        if v is ref:
            alineados.append((v, [list(p) for p in v["pts"]]))
            continue
        q = [punto_en(v["pts"], m) for m in muestras]
        par = [(a, b) for a, b in zip(q, pr) if a and b]
        ang, dx, dy = _ajuste_rigido([(a[0], a[1]) for a, _b in par], [(b[0], b[1]) for _a, b in par])
        c, s_ = math.cos(ang), math.sin(ang)
        alineados.append((v, [[p[0], c * p[1] - s_ * p[2] + dx, s_ * p[1] + c * p[2] + dy] for p in v["pts"]]))
    pts_ref = next(a for v, a in alineados if v is ref)
    linea_ref = [(p[1], p[2]) for p in pts_ref]
    # para cada viaje: desde qué metros va por la ruta común (de ahí al final siempre cerca)
    uniones = []
    for v, a in alineados:
        if v is ref:
            continue
        ds = [_dist_a_linea(p[1], p[2], linea_ref) for p in a]
        cerca = sorted(d_ for p, d_ in zip(a, ds) if p[0] <= m_fin + ALINEAR_M)
        if cerca and cerca[len(cerca) // 2] > UNION_M * 0.8:
            continue                       # no calza con los demás (rumbo malo en ese viaje): no se usa
        # desde el punto de carga hacia atrás, mientras siga cerca (se perdonan 2 puntos sueltos)
        j, fallas = a[-1][0], 0
        for p, d_ in zip(reversed(a), reversed(ds)):
            if d_ <= UNION_M:
                j, fallas = p[0], 0
            else:
                fallas += 1
                if fallas > 2:
                    break
        uniones.append((v, a, j))
    if uniones:
        js = sorted(j for _v, _a, j in uniones)
        comun = js[len(js) // 2]          # la mediana: un viaje con error de rumbo no achica la ruta común
    else:
        comun = max(pts_ref[-1][0], pts_ref[0][0] - 15.0)   # un solo viaje: los primeros 15 m son la aparición
    comun = min(comun, pts_ref[0][0])
    pts = [p for p in pts_ref if p[0] <= comun + 0.01]
    q = punto_en(pts_ref, comun)
    if q and (not pts or pts[0][0] < comun - 0.5):
        pts = [[round(comun, 1), round(q[0], 1), round(q[1], 1)]] + pts
    apariciones = []
    for v, a in [(ref, pts_ref)] + [(v, a) for v, a, _j in uniones]:
        rama = [[p[1], p[2]] for p in a if p[0] >= comun - 0.01]
        if q:
            rama.append([q[0], q[1]])
        apariciones.append({"x": a[0][1], "y": a[0][2], "m": a[0][0], "rama": rama, "origen": v.get("origen")})
    return {"pts": pts, "comun_desde": comun, "apariciones": apariciones,
            "calles": ref.get("calles", []), "zonas": ref.get("zonas", []), "origen": ref.get("origen")}


def cargar_camino():
    if not os.path.exists(ruta_camino()):
        migrar_camino()
    d = carpetas.leer_json(ruta_camino(), None) if os.path.exists(ruta_camino()) else None
    return combinar_camino(d) if d else None


# ------------------------------------------------------------------ 3.3.0: un viaje sobre el mapa
EVENTOS = (("control manual", "manual", "Tomaste el control"), ("choque", "choque", "Choque"),
           ("atascado", "atascado", "Atascado"))


def viaje_sobre_mapa(ruta_csv):
    """Lo que hizo un viaje, para dibujarlo encima del mapa:
      {"recorrido": ..., "huella": {tramo: [(metros, kmh, kmh_obj)]}, "eventos": [{tramo, metros, tipo, texto, t}]}"""
    filas = leer_viaje(ruta_csv)
    rec = ""
    huella, eventos = {}, []
    fuera_desde = None
    for f in filas:
        tr = (f.get("tramo") or "").strip()
        m = _f(f.get("dist_punto_m"))
        r = (f.get("ruta") or "").strip()
        if r and tr in ("1", "2"):
            rec = rec or r
        if m is None or tr not in ("0", "1", "2"):
            continue
        if f.get("estado") not in ("INACTIVO", "TERMINADO", None, ""):
            lista = huella.setdefault(tr, [])
            k, o = _f(f.get("kmh")), _f(f.get("kmh_obj"))
            if k is not None and (not lista or abs(lista[-1][0] - m) >= 5):
                lista.append((m, k, o))
        ev = (f.get("evento") or "").strip()
        for clave, tipo, txt in EVENTOS:
            if ev.startswith(clave):
                eventos.append({"tramo": tr, "metros": m, "tipo": tipo, "texto": f"{txt}: {ev}"[:90],
                                "t": _f(f.get("t"))})
        ec = _f(f.get("en_calle"))
        t = _f(f.get("t")) or 0.0
        if ec is not None and ec < 0.3 and f.get("estado") == "CONDUCIENDO":
            if fuera_desde is None:
                fuera_desde = (t, m, tr)
        else:
            if fuera_desde is not None and t - fuera_desde[0] >= 2.0:
                eventos.append({"tramo": fuera_desde[2], "metros": fuera_desde[1], "tipo": "fuera",
                                "texto": "Fuera de la calle", "t": fuera_desde[0]})
            fuera_desde = None
    return {"recorrido": rec, "huella": huella, "eventos": _juntar_eventos(eventos),
            "origen": os.path.basename(ruta_csv)}


_PESO_EVENTO = {"choque": 3, "atascado": 2, "manual": 1, "fuera": 0}


def _juntar_eventos(eventos, metros=40.0):
    """Varias marcas en el mismo lugar (atascado + fuera de la calle + tomaste el control) quedan en una sola,
    con el tipo más grave y todos los textos."""
    out = []
    for e in sorted(eventos, key=lambda e: (e["tramo"], -e["metros"])):
        u = out[-1] if out else None
        if u is not None and u["tramo"] == e["tramo"] and abs(u["metros"] - e["metros"]) <= metros:
            if e["texto"] not in u["texto"]:
                u["texto"] += "\n" + e["texto"]
            if _PESO_EVENTO.get(e["tipo"], 0) > _PESO_EVENTO.get(u["tipo"], 0):
                u["tipo"] = e["tipo"]
            continue
        out.append(dict(e))
    return out


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

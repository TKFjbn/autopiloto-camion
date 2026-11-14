"""
Tramos compartidos entre recorridos (2.5.0).

Dos recorridos que van por las mismas calles tienen el mismo dibujo de curvas, pero el GPS marca otra
distancia en el mismo lugar (el destino es otro). Ejemplo: en la ida, Granja 2 marca 160 m menos que Granja 1
desde el puente de Elysian Island hasta la salida a Vinewood Park Drive.

1. Perfil: con cada viaje que tiene rumbo exacto se guarda, por tramo, el rumbo del camión cada 10 m de
   "metros al punto" (datos/perfiles/<recorrido>.json).
2. Detección: se comparan los perfiles de todos los recorridos (mismo tramo). Un tramo compartido es una parte
   de al menos 200 m, con curvas (al menos 45° de giro dentro), donde los rumbos coinciden con una diferencia de
   metros constante (error medio de menos de 5°).
3. Los tramos encontrados quedan en datos/compartidos.json como "pendiente"; se usan solo cuando el jugador
   los confirma (pestaña Experimental o mapa de la ruta).

    datos/compartidos.json
      {"formato": 1, "tramos": [
         {"id": "...", "tramo": 1, "a": "drogas_granja_1", "b": "drogas_granja_2",
          "a_desde": 5690, "a_hasta": 2210, "desfase": -160, "error": 2.9, "giro": 179,
          "estado": "confirmado" | "pendiente" | "apagado", "nota": "..."}]}

   En ese tramo: metros de b = metros de a + desfase.

Una regla de un recorrido cuyo centro cae dentro de un tramo compartido confirmado vale también para el
otro recorrido (corrida con el desfase), salvo que tenga "solo_esta_ruta": true.
"""
import csv
import math
import os
import time

import carpetas

PERFILES = os.path.join(carpetas.DATOS, "perfiles")
ARCHIVO = os.path.join(carpetas.DATOS, "compartidos.json")
PASO = 10                  # metros por casilla del perfil
TOL_GRADOS = 18            # diferencia de rumbo que todavía cuenta como "misma calle"
MIN_LARGO = 200
MIN_GIRO = 45
MAX_ERROR = 5.0
MAX_DESFASE = 800


def _slug(nombre):
    import mapa
    return mapa._slug(nombre)


def _dif(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


# ------------------------------------------------------------------ perfiles
def perfil_de_filas(filas):
    """{recorrido: {tramo: {"lo": casilla_inicial, "rumbo": [grados o None, ...]}}} desde las filas de un viaje."""
    bins = {}
    for x in filas:
        rec = (x.get("ruta") or "").strip()
        if not rec or "desconocido" in rec:
            continue
        try:
            tr = str(int(float(x.get("tramo"))))
            d = float(x.get("dist_punto_m"))
            r = float(x.get("rumbo_abs"))
            v = float(x.get("kmh") or 0)
        except (TypeError, ValueError):
            continue
        if v < 3 or x.get("estado") in ("RECUPERANDO", "TERMINADO", "MARCHA_ATRAS"):
            continue
        k = int(round(d / PASO))
        bins.setdefault(rec, {}).setdefault(tr, {}).setdefault(k, []).append(math.radians(r))
    out = {}
    for rec, tramos in bins.items():
        for tr, b in tramos.items():
            if len(b) < MIN_LARGO // PASO:
                continue
            lo, hi = min(b), max(b)
            ang = [None] * (hi - lo + 1)
            for k, v in b.items():
                ang[k - lo] = round(math.degrees(math.atan2(sum(map(math.sin, v)), sum(map(math.cos, v)))) % 360, 1)
            out.setdefault(rec, {})[tr] = {"lo": lo, "rumbo": _rellenar(ang)}
    return out


def _rellenar(ang, max_hueco=15):
    """Interpola huecos de hasta 150 m (a velocidad, el HUD a veces se queda pegado y salta casillas)."""
    n = len(ang)
    out = list(ang)
    i = 0
    while i < n:
        if out[i] is None:
            j = i
            while j < n and out[j] is None:
                j += 1
            if 0 < i and j < n and j - i <= max_hueco:
                a, b = out[i - 1], out[j]
                d = (b - a + 180) % 360 - 180
                for q in range(i, j):
                    out[q] = round((a + d * (q - i + 1) / (j - i + 1)) % 360, 1)
            i = j
        else:
            i += 1
    return out


def ruta_perfil(recorrido):
    return os.path.join(PERFILES, _slug(recorrido) + ".json")


def cargar_perfil(recorrido_o_slug):
    nombre = recorrido_o_slug if recorrido_o_slug.endswith(".json") else _slug(recorrido_o_slug) + ".json"
    ruta = os.path.join(PERFILES, nombre)
    return carpetas.leer_json(ruta, None) if os.path.exists(ruta) else None


def guardar_perfiles(perfiles, origen):
    """Guarda/actualiza el perfil de cada recorrido. Un tramo se reemplaza si el nuevo cubre al menos lo mismo."""
    hechos = []
    os.makedirs(PERFILES, exist_ok=True)
    for rec, tramos in perfiles.items():
        previo = cargar_perfil(rec) or {"recorrido": rec, "tramos": {}}
        cambio = []
        for tr, p in tramos.items():
            viejo = previo["tramos"].get(tr)
            util = sum(1 for a in p["rumbo"] if a is not None)
            util_v = sum(1 for a in (viejo or {}).get("rumbo", []) if a is not None)
            if viejo is None or util >= 0.9 * util_v:
                previo["tramos"][tr] = p
                cambio.append(tr)
        if cambio:
            previo["recorrido"] = rec
            previo["origen"] = os.path.basename(origen)
            previo["fecha"] = time.strftime("%Y-%m-%d %H:%M")
            carpetas.guardar_json(ruta_perfil(rec), previo)
            hechos.append((rec, sorted(cambio)))
    return hechos


def desde_viaje(ruta_csv):
    import mapa
    if not mapa.tiene_rumbo(ruta_csv):
        return []
    return guardar_perfiles(perfil_de_filas(mapa.leer_viaje(ruta_csv)), ruta_csv)


def todos_los_perfiles():
    out = {}
    if not os.path.isdir(PERFILES):
        return out
    for n in sorted(os.listdir(PERFILES)):
        if n.endswith(".json"):
            p = carpetas.leer_json(os.path.join(PERFILES, n), None)
            if p and p.get("recorrido"):
                out[os.path.splitext(n)[0]] = p
    return out


# ------------------------------------------------------------------ comparación
def comparar(pa, pb):
    """Tramos donde el perfil b coincide con el a corrido en un desfase constante.
    Devuelve [(largo_m, desfase_m, a_desde, a_hasta, giro, error)] sin solaparse en a."""
    loA, a = pa["lo"], pa["rumbo"]
    loB, b = pb["lo"], pb["rumbo"]
    cand = []
    for o in range(-MAX_DESFASE // PASO, MAX_DESFASE // PASO + 1):
        d = []
        for i, va in enumerate(a):
            j = i + loA + o - loB
            vb = b[j] if 0 <= j < len(b) else None
            d.append(None if va is None or vb is None else _dif(va, vb))
        i, n = 0, len(d)
        while i < n:
            if d[i] is not None and d[i] < TOL_GRADOS:
                j = i
                while j < n and ((d[j] is not None and d[j] < TOL_GRADOS) or
                                 any(q is not None and q < TOL_GRADOS for q in d[j:j + 4])):
                    j += 1
                largo = (j - i) * PASO
                if largo >= MIN_LARGO:
                    vals = [x for x in a[i:j] if x is not None]
                    giro = max((_dif(vals[p], vals[q]) for p in range(0, len(vals), 3)
                                for q in range(p, len(vals), 3)), default=0)
                    errs = [x for x in d[i:j] if x is not None]
                    err = sum(errs) / len(errs) if errs else 99
                    if giro >= MIN_GIRO and err <= MAX_ERROR:
                        cand.append((largo, o * PASO, (j - 1 + loA) * PASO, (i + loA) * PASO, round(giro),
                                     round(err, 1)))
                i = j
            i += 1
    cand.sort(key=lambda c: (-c[0], c[5]))
    fin = []
    for c in cand:
        if all(c[2] < f[3] - 50 or c[3] > f[2] + 50 for f in fin):
            fin.append(c)
    return fin


def cargar():
    d = carpetas.leer_json(ARCHIVO, None) if os.path.exists(ARCHIVO) else None
    return d if isinstance(d, dict) else {"formato": 1, "tramos": []}


def guardar(d):
    carpetas.guardar_json(ARCHIVO, d)


def _mismo(g, h):
    """¿Es el mismo tramo compartido (mismos recorridos y tramo, rangos que se solapan)?"""
    if g["tramo"] != h["tramo"] or {g["a"], g["b"]} != {h["a"], h["b"]}:
        return False
    hd, hh = h["a_desde"], h["a_hasta"]
    if g["a"] != h["a"]:                                   # dado vuelta: pasar h a los metros de g["a"]
        hd, hh = hd + h["desfase"], hh + h["desfase"]
    return min(g["a_desde"], hd) - max(g["a_hasta"], hh) > 0


def detectar():
    """Compara todos los perfiles y agrega a datos/compartidos.json los tramos nuevos como "pendiente".
    Devuelve la lista de tramos nuevos."""
    perf = todos_los_perfiles()
    d = cargar()
    nuevos = []
    slugs = sorted(perf)
    for i, sa in enumerate(slugs):
        for sb in slugs[i + 1:]:
            for tr in sorted(set(perf[sa]["tramos"]) & set(perf[sb]["tramos"])):
                for largo, des, desde, hasta, giro, err in comparar(perf[sa]["tramos"][tr], perf[sb]["tramos"][tr]):
                    g = {"id": f"{sa}~{sb}~{tr}~{desde}", "tramo": int(tr), "a": sa, "b": sb,
                         "a_desde": int(desde), "a_hasta": int(hasta), "desfase": int(des),
                         "error": err, "giro": giro, "estado": "pendiente",
                         "nota": f"encontrado {time.strftime('%Y-%m-%d')}"}
                    if any(_mismo(h, g) for h in d["tramos"]):
                        continue
                    d["tramos"].append(g)
                    nuevos.append(g)
    if nuevos:
        guardar(d)
    return nuevos


def describir(g, nombres=None):
    nombres = nombres or {}
    import rutas
    na, nb = nombres.get(g["a"], g["a"]), nombres.get(g["b"], g["b"])
    tr = {0: "camino a cargar", 1: "ida", 2: "vuelta"}.get(int(g["tramo"]), str(g["tramo"]))
    return (f"{tr}: {na} {rutas.km(g['a_desde'])} → {rutas.km(g['a_hasta'])} = {nb} "
            f"{rutas.km(g['a_desde'] + g['desfase'])} → {rutas.km(g['a_hasta'] + g['desfase'])}")

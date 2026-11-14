"""
2.7.0: tiempos de los viajes (ida, vuelta y total de cada trabajo) y promedios por recorrido y modo.

Un trabajo va de la notificación «camión CARGADO» a «TRABAJO COMPLETADO»:
  ida = CARGADO -> DESCARGADO, vuelta = DESCARGADO -> COMPLETADO.
Solo cuentan los trabajos completos. El modo es «rápido» si la mayor parte del trabajo se hizo con el modo
rápido prendido (columna modo_lento = 2), si no «normal».
Los resultados se guardan en mi_equipo/tiempos_viajes.json (por nombre, tamaño y fecha del archivo), así cada
viaje se lee una sola vez.
"""
import csv
import os

import carpetas

CACHE = os.path.join(carpetas.EQUIPO, "tiempos_viajes.json")


def _clave(ruta):
    try:
        st = os.stat(ruta)
        return f"{os.path.basename(ruta)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return None


def calcular(ruta):
    """[{"recorrido", "modo", "ida", "vuelta", "total"}] de los trabajos completos del viaje."""
    trabajos = []
    actual = None
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        filas = csv.DictReader(l for l in fh if not l.startswith("#"))
        for x in filas:
            ev = x.get("evento") or ""
            try:
                t = float(x.get("t") or 0)
            except ValueError:
                continue
            if "camión CARGADO" in ev:
                actual = {"t0": t, "td": None, "rapido": 0, "n": 0, "recs": {}}
                continue
            if actual is None:
                continue
            actual["n"] += 1
            if (x.get("modo_lento") or "") == "2":
                actual["rapido"] += 1
            rec = (x.get("ruta") or "").strip()
            if rec:
                actual["recs"][rec] = actual["recs"].get(rec, 0) + 1
            if "camión DESCARGADO" in ev and actual["td"] is None:
                actual["td"] = t
            elif "TRABAJO COMPLETADO" in ev:
                if actual["td"] is not None:
                    rec = max(actual["recs"], key=actual["recs"].get) if actual["recs"] else "-"
                    trabajos.append({"recorrido": rec,
                                     "modo": "rápido" if actual["rapido"] > actual["n"] / 2 else "normal",
                                     "ida": round(actual["td"] - actual["t0"]),
                                     "vuelta": round(t - actual["td"]),
                                     "total": round(t - actual["t0"])})
                actual = None
    return trabajos


def _leer_cache():
    try:
        return carpetas.leer_json(CACHE, {}) or {}
    except Exception:  # noqa
        return {}


def de_viaje(ruta, cache=None):
    """Tiempos del viaje (usa la caché si el archivo no cambió). Devuelve (trabajos, cache_modificada)."""
    cache = _leer_cache() if cache is None else cache
    k = _clave(ruta)
    if k and k in cache:
        return cache[k], False
    try:
        r = calcular(ruta)
    except Exception:  # noqa
        r = []
    if k:
        cache[k] = r
    return r, True


def guardar_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        carpetas.guardar_json(CACHE, cache)
    except Exception:  # noqa
        pass


def promedios(todos):
    """{(recorrido, modo): (segundos_promedio, cantidad)} a partir de una lista de trabajos."""
    acc = {}
    for tr in todos:
        k = (tr["recorrido"], tr["modo"])
        s, n = acc.get(k, (0, 0))
        acc[k] = (s + tr["total"], n + 1)
    return {k: (s / n, n) for k, (s, n) in acc.items()}


def mmss(seg):
    if seg is None:
        return "-"
    seg = int(round(seg))
    return f"{seg // 60}:{seg % 60:02d}"

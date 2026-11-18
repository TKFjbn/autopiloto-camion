"""
Reglas de los modos sin rutas (3.9.0). Por ahora: el modo libre.

datos/modos/libre.json:
    {"formato": 1, "programa_minimo": "3.9.0", "reglas": [ {regla}, ... ]}
Cada regla es como las del mapa de la ruta pero SIEMPRE general (vale en todo el viaje, sin desde/hasta):
max_kmh, esquina_kmh, avance_esquina_px, desplazamiento_px, sin_freno, modo, exp, nota, activa...
Varias reglas se suman como las generales del camionero (rutas.combinar): la última que pide algo manda.
"""
import json
import os
import shutil
import time

import carpetas

NOMBRE = {"libre": "Libre"}


def archivo(modo="libre"):
    return os.path.join(carpetas.MODOS, f"{modo}.json")


def cargar_reglas(modo="libre"):
    ruta = archivo(modo)
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        return [r for r in (d.get("reglas") or []) if isinstance(r, dict)]
    except Exception as e:  # noqa
        print(f"[!] No se pudieron leer las reglas del modo {modo}: {e}")
        return []


def guardar_reglas(reglas, modo="libre"):
    ruta = archivo(modo)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    if os.path.exists(ruta):
        dest = os.path.join(carpetas.RESPALDOS, "modos")
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(ruta, os.path.join(dest, f"{modo}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
    limpias = []
    for r in reglas:
        r = {k: v for k, v in r.items() if not k.startswith("_") and k not in ("desde", "hasta")}
        r["general"] = True
        limpias.append(r)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"formato": 1, "programa_minimo": "3.9.0", "reglas": limpias}, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)


def datos_modo(modo="libre"):
    """Datos de rutas «de mentira» para el autopiloto: una sola ruta sin lugar, con las reglas del modo como
    generales en el tramo 1 (el único que se usa). Así no se cuela ninguna regla del camionero."""
    reglas = [dict(r, general=True) for r in cargar_reglas(modo)]
    ruta = {"_archivo": f"_{modo}.json", "nombre": NOMBRE.get(modo, modo.capitalize()), "cargamento": None,
            "reglas": {"1": reglas}}
    return {"rutas": [ruta], "inicio_comun": [], "regreso_comun": [], "compartidos": []}, ruta

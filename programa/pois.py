"""
Puntos de interés del mapa de la ruta (3.3.0).

Sirven para ubicarse en el mapa (que se arma con el rumbo y la velocidad, como un GPS de papel, y por eso no
calza con el mapa de Los Santos): «Puente de Elysian Island», «Grúa del puerto», «Esquina de Banning»...

    datos/pois.json
      {"formato": 1, "pois": [{"id": "p12", "nombre": "...", "icono": "puente",
                               "recorrido": "drogas_granja_1" | "_camino" | "_regreso", "tramo": "1",
                               "metros": 5690}]}

  recorrido "_camino": camino a cargar (común a todos); "_regreso": parte común de la vuelta (todos los recorridos).
  Los de un recorrido que caen en un tramo compartido confirmado se muestran también en el otro.
"""
import os
import time

import carpetas

RUTA = os.path.join(carpetas.DATOS, "pois.json")
CAMINO = "_camino"
REGRESO = "_regreso"

# icono -> (símbolo que se dibuja, descripción)
ICONOS = {
    "punto": ("●", "Punto"),
    "puente": ("≡", "Puente"),
    "esquina": ("↱", "Esquina"),
    "curva": ("↷", "Curva"),
    "edificio": ("▣", "Edificio"),
    "peligro": ("!", "Peligro / obstáculo"),
    "subida": ("▲", "Subida / bajada"),
    "salida": ("⇗", "Salida / bifurcación"),
    "gasolinera": ("⛽", "Gasolinera"),
    "rotonda": ("◎", "Rotonda"),
    "carga": ("■", "Punto de carga"),
    "meta": ("⚑", "Punto final / granja"),
}

INICIALES = [
    # camino a cargar (común)
    (CAMINO, "0", 210, "Poste de madera", "peligro"),
    (CAMINO, "0", 150, "Esquina al patio (grúa del puerto)", "esquina"),
    (CAMINO, "0", 5, "Punto de carga", "carga"),
    # ida de Granja 1 (lo compartido se ve también en Granja 2)
    ("drogas_granja_1", "1", 5690, "Puente de Elysian Island", "puente"),
    ("drogas_granja_1", "1", 5580, "Esquina de Banning (salida del puente)", "esquina"),
    ("drogas_granja_1", "1", 5350, "Banning: curva cerrada", "curva"),
    ("drogas_granja_1", "1", 5000, "Subida de Autopia Parkway", "subida"),
    ("drogas_granja_1", "1", 4880, "Maze Bank Arena", "edificio"),
    ("drogas_granja_1", "1", 4720, "Davis Avenue: farolas al centro", "peligro"),
    ("drogas_granja_1", "1", 3360, "Separador de Strawberry", "peligro"),
    ("drogas_granja_1", "1", 3100, "Barrera de Mirror Park", "peligro"),
    ("drogas_granja_1", "1", 2600, "Autopista de Vinewood Hills", "punto"),
    ("drogas_granja_1", "1", 2130, "Salida a Vinewood Park Drive", "salida"),
    ("drogas_granja_1", "1", 1750, "Señora Road", "punto"),
    ("drogas_granja_1", "1", 1100, "Curva en bajada", "curva"),
    ("drogas_granja_2", "1", 2050, "Se separan Granja 1 y Granja 2", "salida"),
    ("drogas_granja_2", "1", 130, "Entrada a la granja", "meta"),
    # vuelta
    ("drogas_granja_1", "2", 5330, "Señora Road (vuelta)", "punto"),
    ("drogas_granja_1", "2", 3950, "Paso sobre la autopista", "puente"),
    ("drogas_granja_1", "2", 3650, "Esquina muy cerrada", "esquina"),
    ("drogas_granja_2", "2", 3720, "Cambio de carril (Vinewood Hills)", "peligro"),
    ("drogas_granja_2", "2", 2820, "Salida a la derecha", "salida"),
    (REGRESO, "2", 2190, "Árbol de Textile City", "peligro"),
    (REGRESO, "2", 1400, "Carteles de Strawberry Avenue", "peligro"),
    (REGRESO, "2", 1000, "Esquina de Maze Bank", "esquina"),
    (REGRESO, "2", 800, "Poste gigante (Maze Bank Arena)", "peligro"),
    (REGRESO, "2", 620, "Banning: postes de madera", "peligro"),
    (REGRESO, "2", 60, "Punto final (B)", "meta"),
]


def cargar():
    if not os.path.exists(RUTA):
        d = {"formato": 1, "programa_minimo": "3.3.0",
             "pois": [{"id": f"p{i + 1}", "recorrido": r, "tramo": t, "metros": m, "nombre": n, "icono": ic}
                      for i, (r, t, m, n, ic) in enumerate(INICIALES)]}
        try:
            guardar(d)
        except Exception:  # noqa
            pass
        return d
    d = carpetas.leer_json(RUTA, {}) or {}
    d.setdefault("pois", [])
    return d


def guardar(d):
    d["fecha"] = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    carpetas.guardar_json(RUTA, d)


def _nuevo_id(d):
    usados = {p.get("id") for p in d.get("pois", [])}
    n = len(usados) + 1
    while f"p{n}" in usados:
        n += 1
    return f"p{n}"


def agregar(recorrido, tramo, metros, nombre, icono="punto"):
    d = cargar()
    p = {"id": _nuevo_id(d), "recorrido": recorrido, "tramo": str(tramo), "metros": round(float(metros)),
         "nombre": nombre.strip() or "Punto", "icono": icono if icono in ICONOS else "punto"}
    d["pois"].append(p)
    guardar(d)
    return p


def editar(pid, **cambios):
    d = cargar()
    for p in d["pois"]:
        if p.get("id") == pid:
            p.update({k: v for k, v in cambios.items() if v is not None})
            guardar(d)
            return p
    return None


def borrar(pid):
    d = cargar()
    antes = len(d["pois"])
    d["pois"] = [p for p in d["pois"] if p.get("id") != pid]
    if len(d["pois"]) != antes:
        guardar(d)
        return True
    return False


def slug(archivo):
    return os.path.splitext(os.path.basename(archivo or ""))[0]


def para_tramo(recorrido_archivo, tramo, compartidos=None, regreso_desde=None):
    """Puntos que se ven en este recorrido y tramo: [(poi, metros_aqui, de_otro)].
    compartidos: [(otro_slug, lo, hi, corrimiento)] (de rutas.tramos_compartidos) para traer los de otros
    recorridos; regreso_desde: desde qué metros la vuelta es común (para los de "_regreso")."""
    tramo = str(tramo)
    yo = CAMINO if tramo == "0" else slug(recorrido_archivo)
    out = []
    for p in cargar().get("pois", []):
        if str(p.get("tramo")) != tramo:
            continue
        m = float(p.get("metros", 0))
        r = p.get("recorrido")
        if r == yo:
            out.append((p, m, False))
        elif r == REGRESO and tramo == "2" and (regreso_desde is None or m <= regreso_desde + 50):
            out.append((p, m, False))
        else:
            for otro, lo, hi, corr in (compartidos or []):
                if otro == r and lo - 40 <= m + corr <= hi + 40:
                    out.append((p, m + corr, True))
                    break
    return out


def cerca_de(lista, metros, maximo=400):
    """El punto de interés más cercano a esos metros (de para_tramo), o None."""
    mejor = None
    for p, m, _o in lista:
        d = abs(m - metros)
        if d <= maximo and (mejor is None or d < mejor[0]):
            mejor = (d, p)
    return mejor[1] if mejor else None

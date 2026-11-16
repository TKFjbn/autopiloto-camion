"""
Grabación y repetición de recorridos cortos (v38).

Idea: en los tramos donde el GPS no sirve (entrada a una granja sin caminos, la salida en reversa
de Medicamentos, el punto final con árboles) conduces TÚ una vez con el teclado mientras el programa
anota lo que haces: qué teclas están apretadas (W, A, S, D, espacio), a qué velocidad vas y a qué
distancia del punto estás. Después, cada vez que el camión llega al mismo sitio, el programa repite
esos movimientos con el mando virtual, corrigiendo el acelerador para ir a la misma velocidad que tú.

Cada grabación es un archivo JSON en la carpeta `datos/grabaciones/`:
  {
    "nombre": "Granja 2 - entrada",
    "recorrido": "Drogas - Granja 2",     (o "" si vale para cualquier recorrido)
    "tramo": 1,
    "disparo": {"tipo": "distancia", "metros": 130}     cuando la distancia del HUD baja de 130 m
             | {"tipo": "descargado"}                   justo después de la notificación "descargado"
             | {"tipo": "cargado"}                      justo después de "cargado"
             | {"tipo": "final", "metros": 60}          en la vuelta, al bajar de 60 m del punto final
    "al_terminar": "parar" | "seguir",   parar: queda INACTIVO; seguir: vuelve a conducir con el GPS
    "cardinal_inicio": "N", "kmh_inicio": 12, "duracion": 23.4,
    "muestras": [[t, dir, acel, freno, kmh, metros], ...]   dir -1/0/1, acel 0/1, freno 0/1
  }
Nada de esto toca el juego: solo se leen las teclas físicas (como las teclas de atajo) y se mueve el
mando virtual al repetir.
"""
import json
import os
import re
import time

try:
    import carpetas as _carpetas
    CARPETA = _carpetas.GRABACIONES
except Exception:  # noqa
    CARPETA = "grabaciones"


def _slug(texto):
    s = re.sub(r"[^a-z0-9]+", "_", texto.lower().strip())
    return s.strip("_") or "grabacion"


def cargar_todas(carpeta=CARPETA):
    """Lista de grabaciones (dicts) leídas de la carpeta. Las que no se pueden leer se saltan."""
    out = []
    if not os.path.isdir(carpeta):
        return out
    for f in sorted(os.listdir(carpeta)):
        if not f.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(carpeta, f), encoding="utf-8") as fh:
                g = json.load(fh)
            if g.get("muestras"):
                g["_archivo"] = f
                out.append(g)
        except Exception as e:  # noqa
            print(f"[!] Grabación {f} no se pudo leer: {e}")
    return out


def existe(nombre, trazado=False):
    """3.5.0: ¿ya hay una grabación (o trazado) con ese nombre? Devuelve la ruta del archivo o None."""
    carpeta = CARPETA_TRAZADOS if trazado else CARPETA
    ruta = os.path.join(carpeta, _slug(nombre or ("trazado" if trazado else "grabacion")) + ".json")
    return ruta if os.path.exists(ruta) else None


def _respaldar(ruta):
    try:
        import carpetas
        import shutil
        import time
        dest = os.path.join(carpetas.RESPALDOS, "grabaciones")
        os.makedirs(dest, exist_ok=True)
        base = os.path.splitext(os.path.basename(ruta))[0]
        shutil.copy2(ruta, os.path.join(dest, f"{base}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
    except Exception as e:  # noqa
        print(f"[i] No se pudo respaldar {ruta}: {e}")


def guardar(g, carpeta=CARPETA):
    """g["_reemplazar"] = True (3.5.0): si ya existe una con el mismo nombre, la reemplaza (con copia antes)."""
    os.makedirs(carpeta, exist_ok=True)
    base = _slug(g.get("nombre", "grabacion"))
    ruta = os.path.join(carpeta, base + ".json")
    if g.get("_reemplazar") and os.path.exists(ruta):
        _respaldar(ruta)
    n = 2
    while os.path.exists(ruta) and not g.get("_reemplazar"):
        ruta = os.path.join(carpeta, f"{base}_{n}.json")
        n += 1
    g = {k: v for k, v in g.items() if not k.startswith("_")}
    try:
        import version
        g.setdefault("programa", version.VERSION)
    except Exception:  # noqa
        pass
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(g, fh, ensure_ascii=False)
    return ruta


def buscar(grabs, tipo, recorrido, tramo, metros=None, tolerancia_m=60):
    """La grabación que corresponde a este disparo, o None.
    'distancia'/'final': la que tenga sus metros más cerca de `metros` (dentro de la tolerancia)."""
    cand = []
    for g in grabs:
        d = g.get("disparo", {})
        if d.get("tipo") != tipo:
            continue
        if g.get("recorrido") and recorrido and g["recorrido"] != recorrido:
            continue
        if g.get("recorrido") and not recorrido:
            continue
        if tipo != "final" and g.get("tramo") is not None and int(g["tramo"]) != int(tramo):
            continue
        if tipo in ("distancia", "final"):
            if metros is None or d.get("metros") is None:
                continue
            dif = abs(float(d["metros"]) - float(metros))
            if dif > tolerancia_m:
                continue
            cand.append((dif, g))
        else:
            cand.append((0, g))
    if not cand:
        return None
    cand.sort(key=lambda x: x[0])
    return cand[0][1]


class Grabadora:
    """Anota lo que haces tú con el teclado mientras conduces."""

    def __init__(self, leer_tecla, teclas=None):
        # leer_tecla(nombre) -> bool (tecla física apretada). Nombres: W A S D SPACE
        self.leer_tecla = leer_tecla
        self.teclas = teclas or {"acel": "W", "freno": "S", "izq": "A", "der": "D", "mano": "SPACE"}
        self.muestras = []
        self.t0 = None
        self.inicio = {}

    def empezar(self, contexto):
        self.muestras = []
        self.t0 = time.time()
        self.inicio = dict(contexto)      # recorrido, tramo, metros, cardinal, kmh

    def muestra(self, kmh, metros, dist_fina=None, lateral=None, en_calle=None):
        """lateral: desvío del camión respecto a la línea del GPS (px del minimapa, + = izquierda)."""
        if self.t0 is None:
            return
        t = time.time() - self.t0
        d = (1 if self.leer_tecla(self.teclas["der"]) else 0) - (1 if self.leer_tecla(self.teclas["izq"]) else 0)
        a = 1 if self.leer_tecla(self.teclas["acel"]) else 0
        f = 1 if (self.leer_tecla(self.teclas["freno"]) or self.leer_tecla(self.teclas["mano"])) else 0
        self.muestras.append([round(t, 3), d, a, f, int(kmh or 0), None if metros is None else int(metros),
                              None if dist_fina is None else round(float(dist_fina), 1),
                              None if lateral is None else round(float(lateral), 2),
                              None if en_calle is None else round(float(en_calle), 2)])

    def terminar(self):
        """Devuelve la grabación (sin nombre ni disparo: los pone la interfaz) o None si está vacía."""
        if self.t0 is None:
            return None
        dur = time.time() - self.t0
        self.t0 = None
        if len(self.muestras) < 5 or dur < 1.0:
            return None
        # recortar el tiempo muerto del final (sin teclas) para que no se quede esperando
        ult = len(self.muestras)
        while ult > 5 and self.muestras[ult - 1][1] == 0 and self.muestras[ult - 1][2] == 0 \
                and self.muestras[ult - 1][3] == 0:
            ult -= 1
        muestras = self.muestras[:min(len(self.muestras), ult + 6)]
        return {"recorrido": self.inicio.get("recorrido") or "", "tramo": self.inicio.get("tramo", 1),
                "metros_inicio": self.inicio.get("metros"), "cardinal_inicio": self.inicio.get("cardinal") or "",
                "kmh_inicio": self.inicio.get("kmh", 0), "duracion": round(muestras[-1][0], 2),
                "escala": self.inicio.get("escala", 1.0), "muestras": muestras,
                "_todas": self.muestras}


class Reproductor:
    """Repite una grabación con el mando virtual, ajustando el acelerador a la velocidad grabada."""

    def __init__(self, g, cfg):
        self.g = g
        self.m = g["muestras"]
        self.cfg = cfg or {}
        self.t0 = time.time()
        self.tv = 0.0                # tiempo "virtual" de la grabación (avanza según la distancia recorrida)
        self.t_prev = None
        self.i = 0
        self.dir = 0.0
        self.t_desvio = None
        self.t_quieto = None
        self.motivo_fin = None

    def _muestra(self, t):
        m = self.m
        while self.i + 1 < len(m) and m[self.i + 1][0] <= t:
            self.i += 1
        return m[self.i]

    def paso(self, kmh, dt):
        """-> (direccion, acelerador, freno, terminado). Si terminado, motivo en self.motivo_fin."""
        c = self.cfg
        ahora = time.time()
        dt_real = 0.0 if self.t_prev is None else max(0.0, min(0.5, ahora - self.t_prev))
        self.t_prev = ahora
        # 2.1.1: por distancia. Mientras tú ibas en movimiento, la grabación avanza al ritmo del camión
        # (si va más lento que tú, la grabación también): cada volantazo cae a los mismos metros.
        kmh_rec = self.m[self.i][4]
        if kmh_rec >= c.get("kmh_por_distancia", 3):
            self.tv += dt_real * max(0.25, min(2.0, float(kmh or 0) / max(1.0, kmh_rec)))
        else:
            self.tv += dt_real                       # parado o arrancando: por tiempo
        t = self.tv
        if t > self.m[-1][0] + 0.3:
            self.motivo_fin = "fin de la grabación"
            return 0.0, 0.0, 0.0, True
        mu = self._muestra(t)
        d, a, f, kmh_g = mu[1], mu[2], mu[3], mu[4]
        # volante: como el teclado del juego, sube de a poco hasta el tope y vuelve rápido al centro
        tope = c.get("volante_max", 0.7)
        objetivo = d * tope
        paso_sube = c.get("volante_por_seg", 2.5) * dt
        paso_baja = c.get("volante_vuelta_por_seg", 5.0) * dt
        if objetivo == 0:
            if abs(self.dir) <= paso_baja:
                self.dir = 0.0
            else:
                self.dir -= paso_baja if self.dir > 0 else -paso_baja
        else:
            if (objetivo > 0) != (self.dir > 0) and self.dir != 0:
                self.dir = 0.0           # cambio de lado: pasar por el centro
            if abs(self.dir) < abs(objetivo):
                self.dir += paso_sube if objetivo > 0 else -paso_sube
                self.dir = max(-abs(objetivo), min(abs(objetivo), self.dir))
        # pedales: la tecla grabada manda, y la velocidad grabada corrige cuánto acelerador
        err = kmh_g - kmh
        acel = freno = 0.0
        if f:
            freno = c.get("freno", 0.6)
        elif a:
            acel = max(0.0, min(1.0, c.get("acelerador_base", 0.45) + c.get("acelerador_por_kmh", 0.035) * err))
        elif err > c.get("mantener_kmh", 4):
            acel = c.get("acelerador_mantener", 0.3)     # tú no acelerabas pero vas más lento: un poco
        # seguridad: muy lejos de la velocidad grabada demasiado tiempo, o quieto cuando tú te movías
        lim = c.get("desvio_kmh_max", 15)
        if -err > lim and kmh_g >= 5:               # 2.1.1: solo si va MUCHO más rápido (más lento ya se compensa)
            self.t_desvio = self.t_desvio or time.time()
            if time.time() - self.t_desvio > c.get("desvio_seg", 3.0):
                self.motivo_fin = f"va mucho más rápido que en la grabación ({kmh} vs {kmh_g} km/h)"
                return 0.0, 0.0, 0.0, True
        else:
            self.t_desvio = None
        if kmh < 1 and kmh_g >= 4 and not f:
            self.t_quieto = self.t_quieto or time.time()
            if time.time() - self.t_quieto > c.get("quieto_seg", 3.0):
                self.motivo_fin = "el camión no avanza (¿chocó?)"
                return 0.0, 0.0, 0.0, True
        else:
            self.t_quieto = None
        return self.dir, acel, freno, False

    def progreso(self):
        return min(1.0, self.tv / max(0.1, self.m[-1][0]))


# ---------------------------------------------------------------- trazados (2.1.0)
# Un trazado guarda, metro a metro, a qué lado de la línea del GPS ibas tú (y a qué velocidad).
# El autopiloto sigue manejando con el GPS, pero en ese tramo se corre al mismo lado que tú.
# Archivo en datos/trazados/:
#   {"nombre", "recorrido", "tramo", "desde", "hasta", "puntos": [[metros, desplazamiento_px, kmh], ...]}
#   desplazamiento_px con el mismo signo que en las reglas: - izquierda, + derecha.
try:
    CARPETA_TRAZADOS = _carpetas.TRAZADOS
except Exception:  # noqa
    CARPETA_TRAZADOS = "trazados"


FILTRO_TRAZADO = 3          # versión del filtro: si sube, los trazados con datos crudos se reprocesan solos


def _mediana(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0.0


def suavizar(puntos, ventana_m=25.0, tope=2.5, paso_m=2.0):
    """puntos [(metros, desplazamiento_px, kmh)] -> lado general suavizado cada paso_m metros.
    Mediana por casilla de 2 m y después promedio en una ventana de ±ventana_m/2 (el minimapa mide el lado
    con unos ±5 px de ruido: así queda el lado general de cada tramo de 20-30 m, sin volantazos)."""
    cubos = {}
    for d, lat, kmh in puntos:
        k = round(d / paso_m) * paso_m
        cubos.setdefault(k, []).append((lat, kmh))
    claves = sorted(cubos, reverse=True)
    base = [(k, _mediana([x for x, _ in cubos[k]]), sum(y for _, y in cubos[k]) / len(cubos[k])) for k in claves]
    out = []
    for k, _l, kmh in base:
        vec = [l for kk, l, _ in base if abs(kk - k) <= ventana_m / 2]
        lat = sum(vec) / len(vec)
        out.append([round(k, 1), round(max(-tope, min(tope, lat)), 2), int(round(kmh))])
    return out


def _limpiar_crudo(crudo):
    """crudo [(metros, desplazamiento_px, kmh, en_calle, t)] -> válidos [(metros, desplazamiento_px, kmh)].
    Para cada muestra se calcula "distancia + lo recorrido desde el inicio": en las buenas da siempre lo mismo
    (la distancia al empezar). Las lecturas que no cuadran con la mayoría (p. ej. un 4040 que el HUD mostró
    varios segundos en vez de 4640) se descartan. También los puntos fuera de la calle."""
    n = len(crudo)
    recorrido, cum, t_ant = [], 0.0, None
    for c in crudo:
        t = c[4] if len(c) >= 5 and c[4] is not None else None
        if t_ant is not None and t is not None:
            cum += max(0.0, float(c[2] or 0)) / 3.6 * max(0.0, min(0.5, t - t_ant))
        t_ant = t
        recorrido.append(cum)
    tiene_t = any(len(c) >= 5 and c[4] is not None for c in crudo)
    if tiene_t:
        inicio = _mediana([c[0] + r for c, r in zip(crudo, recorrido)])
        buenos = [c for c, r in zip(crudo, recorrido) if abs(c[0] + r - inicio) <= 40 + 0.08 * r]
    else:                                                # trazados viejos sin tiempo: vecinas
        ds = [c[0] for c in crudo]
        buenos = [c for i, c in enumerate(crudo) if abs(c[0] - _mediana(ds[max(0, i - 7):i + 8])) <= 30]
    validos = []
    for c in buenos:
        d, lat, kmh = c[0], c[1], c[2]
        en_calle = c[3] if len(c) >= 4 else None
        if lat is None or (en_calle is not None and en_calle < 0.5) or abs(lat) > 8:
            continue
        validos.append((d, lat, kmh))
    return validos, n


def reprocesar(t):
    """Vuelve a calcular los puntos de un trazado a partir de sus datos crudos (si los tiene)."""
    crudo = t.get("crudo")
    if not crudo:
        return t
    validos, _ = _limpiar_crudo(crudo)
    if len(validos) >= 10:
        t["puntos"] = suavizar(validos)
        t["desde"], t["hasta"] = t["puntos"][0][0], t["puntos"][-1][0]
        t["filtro"] = FILTRO_TRAZADO
    return t


def aplicar_ajustes(t):
    """2.5.1: "ajustes": [{"desde": m, "hasta": m, "lado": px}] fija el lado del trazado en esa parte (corrige una
    parte mal grabada sin regrabar todo). Se aplica sobre los puntos (también después de reprocesar)."""
    for a in t.get("ajustes") or []:
        try:
            hi, lo = max(float(a["desde"]), float(a["hasta"])), min(float(a["desde"]), float(a["hasta"]))
            lado = float(a.get("lado", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        for p in t.get("puntos", []):
            if lo <= p[0] <= hi:
                p[1] = lado
    return t


def construir_trazado(g, paso_m=2.0, motivo=None):
    """Convierte una grabación (con distancia fina y lateral) en un trazado. None si no sirve
    (motivo[0] dice por qué). Guarda también los datos crudos para poder reprocesarlo."""
    motivo = motivo if motivo is not None else []
    esc = float(g.get("escala") or 1.0) or 1.0
    todas = [m for m in g.get("_todas", g.get("muestras", [])) if len(m) >= 8 and m[6] is not None]
    if len(todas) < 5:
        motivo.append("no hay datos de distancia")
        return None
    crudo = [[round(m[6], 1), None if m[7] is None else round(-m[7] / esc, 2), m[4],
              m[8] if len(m) >= 9 else None, m[0]] for m in todas]
    validos, _ = _limpiar_crudo(crudo)
    en_mov = [m for m in todas if m[4] >= 3]
    fuera = sum(1 for m in en_mov if m[7] is None or (len(m) >= 9 and m[8] is not None and m[8] < 0.5)
                or abs(m[7] / esc) > 8)
    if len(validos) < 10 or (en_mov and fuera > 0.5 * len(en_mov)):
        motivo.append("casi todo el tramo está fuera de la calle del GPS (para eso usa la grabación de teclas)")
        return None
    puntos = suavizar(validos, paso_m=paso_m)
    if len(puntos) < 3 or puntos[0][0] - puntos[-1][0] < 10:
        motivo.append("el tramo es demasiado corto")
        return None
    t = {"formato": 1, "programa_minimo": "2.1.2", "tipo": "trazado", "nombre": g.get("nombre", "trazado"),
         "recorrido": g.get("recorrido", ""), "tramo": g.get("tramo", 1), "filtro": FILTRO_TRAZADO,
         "desde": puntos[0][0], "hasta": puntos[-1][0], "puntos": puntos, "crudo": crudo}
    if int(t["tramo"]) == 2 and t["desde"] <= COMUN_VUELTA_DESDE_M:
        t["comun"] = True                   # 2.3.2: final de la vuelta, igual para todos los recorridos
        t["programa_minimo"] = "2.3.2"
    return t


def guardar_trazado(t, carpeta=None):
    carpeta = carpeta or CARPETA_TRAZADOS
    os.makedirs(carpeta, exist_ok=True)
    base = _slug(t.get("nombre", "trazado"))
    ruta = os.path.join(carpeta, base + ".json")
    if t.get("_reemplazar") and os.path.exists(ruta):
        _respaldar(ruta)
    n = 2
    while os.path.exists(ruta) and not t.get("_reemplazar"):
        ruta = os.path.join(carpeta, f"{base}_{n}.json")
        n += 1
    t = {k: v for k, v in t.items() if not k.startswith("_")}
    try:
        import version
        t.setdefault("programa", version.VERSION)
    except Exception:  # noqa
        pass
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(t, fh, ensure_ascii=False)
    return ruta


def cargar_trazados(carpeta=None):
    carpeta = carpeta or CARPETA_TRAZADOS
    out = []
    if not os.path.isdir(carpeta):
        return out
    for f in sorted(os.listdir(carpeta)):
        if not f.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(carpeta, f), encoding="utf-8") as fh:
                t = json.load(fh)
            if t.get("crudo") and int(t.get("filtro", 0)) < FILTRO_TRAZADO:
                reprocesar(t)                       # filtro más nuevo: recalcular con los datos crudos
            aplicar_ajustes(t)
            if t.get("puntos"):
                t["_archivo"] = f
                out.append(t)
        except Exception as e:  # noqa
            print(f"[!] Trazado {f} no se pudo leer: {e}")
    return out


COMUN_VUELTA_DESDE_M = 2300      # 2.3.2: desde aquí la vuelta es la misma para todos los recorridos


def trazado_en(trazados, recorrido, tramo, metros, comunes=True):
    """(desplazamiento_px, kmh, trazado) en esta distancia, o None.
    Primero los del recorrido; si no hay, los marcados "comun" (vuelta, mismo final para todos)."""
    if metros is None:
        return None
    propios, comun = [], []
    for t in trazados:
        if int(t.get("tramo", 1)) != int(tramo):
            continue
        if not (t["hasta"] <= metros <= t["desde"]):
            continue
        if t.get("recorrido") and recorrido and t["recorrido"] == recorrido:
            propios.append(t)
        elif not t.get("recorrido"):
            propios.append(t)
        elif comunes and t.get("comun") and int(tramo) == 2:
            comun.append(t)
    for t in propios + comun:
        p = t["puntos"]                     # de mayor a menor distancia
        for i in range(len(p) - 1):
            a, b = p[i], p[i + 1]
            if b[0] <= metros <= a[0]:
                f = 0.0 if a[0] == b[0] else (a[0] - metros) / (a[0] - b[0])
                return a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, t
        return p[-1][1], p[-1][2], t
    return None

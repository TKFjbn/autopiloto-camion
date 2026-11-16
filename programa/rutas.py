"""Rutas conocidas y reglas por lugar.

Cada ruta se reconoce por la DISTANCIA INICIAL que muestra el minimapa justo después de cargar
(p. ej. 5.690 m -> Drogas - Granja 1). Si se leyó el cargamento en la barra
("Cargando drogas..."), solo se comparan rutas de ese "cargamento". La distancia que va bajando sirve de
"posición" a lo largo de la ruta, así que las reglas se escriben como tramos de distancia:

    {"desde": 5480, "hasta": 5330, "max_kmh": 30, "desplazamiento_px": 0, "nota": "..."}

  desde/hasta        metros al punto (desde > hasta, porque la distancia baja)
  max_kmh            velocidad máxima en ese tramo
  desplazamiento_px  dónde ir respecto a la línea roja: - = izquierda, + = derecha, 0 = encima
  nota               texto que aparece en el registro
  (opcionales)
  esquina_kmh        velocidad para las esquinas de ese tramo (en vez de la normal, 20)
  giro_tardio_px     a cuántos px de la esquina empieza a girar (MÁS = gira antes; normal 3-7)
  sin_freno          true: en ese tramo no pisa el freno, solo suelta el acelerador (subidas)
  sin_bifurcacion    true: no baja la velocidad por bifurcaciones en ese tramo
  entregar_control   true: al entrar al tramo frena hasta parar y deja el autopiloto INACTIVO (tramo manual)
  aprox_recto_seg    al final: segundos que avanza recto antes de doblar hacia el punto
  anticipacion       0.4-1.5: <1 = mira más cerca y gira más tarde en curvas
  activa             false: la regla queda en el archivo pero no se aplica (2.4.0, desde el mapa de la ruta)
  solo_esta_ruta     true: aunque esté en un tramo compartido, no se copia a los otros recorridos (2.5.0)
  solo_rapido        true: solo se aplica con el modo rápido prendido (2.7.0)
  (3.5.0)
  solo_lento         true: solo se aplica con el modo lento prendido
  modo               "lento" / "rapido" / "normal": en la zona de la regla conduce con ese modo de velocidad
  avance_esquina_px  esquinas: px que avanza de más antes de girar (+ = gira después, − = gira antes; relativo al
                     normal). giro_tardio_px (valor fijo) manda si está.
  exp                {"velocidad_sin_vaiven": false, ...}: prende o apaga funciones experimentales en la zona
  general            true: vale en TODO el tramo de este recorrido (sin desde/hasta). Una regla de un lugar manda
                     sobre la general en lo que pida; lo demás de la general sigue valiendo.

Tramos compartidos (2.5.0, datos/compartidos.json): si dos recorridos van por las mismas calles, las reglas de
uno que caen en ese tramo valen también para el otro, corridas con la diferencia de metros (ver compartidos.py).

Las reglas de "regreso_comun" valen para la vuelta (tramo 2) de TODAS las rutas: el final hasta la
zona de trabajo es el mismo.

Desde la 2.0.0 cada recorrido es un archivo en datos/rutas/ (p. ej. drogas_granja_1.json) y las reglas
compartidas están en datos/rutas/_comunes.json. Para agregar un recorrido, crea otro archivo igual.
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def cargar(carpeta=None):
    """Lee todos los archivos de datos/rutas/: uno por recorrido + _comunes.json (reglas compartidas).
    Avisa si algún archivo necesita una versión más nueva del programa."""
    import carpetas
    import version
    carpeta = carpeta or carpetas.RUTAS
    datos = {"rutas": [], "inicio_comun": [], "regreso_comun": [], "_archivo": None}
    if not os.path.isdir(carpeta):
        return datos
    archivos = sorted(f for f in os.listdir(carpeta) if f.lower().endswith(".json"))
    for nombre in archivos:
        ruta = os.path.join(carpeta, nombre)
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as e:  # noqa
            print(f"[!] No se pudo leer datos/rutas/{nombre}: {e}")
            continue
        minimo = d.get("programa_minimo")
        if not version.cumple(minimo):
            print(f"[!] datos/rutas/{nombre} necesita el programa {minimo} o más nuevo (tienes {version.VERSION}). "
                  "Algunas reglas pueden no funcionar: actualiza la carpeta programa/.")
        if nombre.startswith("_"):
            datos["inicio_comun"] += d.get("inicio_comun", [])
            datos["regreso_comun"] += d.get("regreso_comun", [])
        else:
            d["_archivo"] = nombre
            datos["rutas"].append(d)
    datos["_archivo"] = f"datos/rutas ({len(archivos)} archivos)"
    try:                                          # 2.5.0: tramos compartidos entre recorridos
        import compartidos
        datos["compartidos"] = [g for g in compartidos.cargar().get("tramos", []) if g.get("estado") == "confirmado"]
    except Exception as e:  # noqa
        print(f"[!] No se pudo leer datos/compartidos.json: {e}")
        datos["compartidos"] = []
    return datos


CARGAMENTOS = ("Drogas", "Ropa", "Productos varios", "Medicamentos")


def km(m):
    """Distancia como en el minimapa: '1,70 km' desde 1 km, '740 m' por debajo."""
    if m is None:
        return "-"
    m = float(m)
    return f"{m / 1000:.2f} km".replace(".", ",") if m >= 1000 else f"{m:.0f} m"


def cargamento_de_texto(texto):
    """'Cargando drogas...' (leído con OCR, puede tener letras mal) -> 'Drogas'. None si no se reconoce."""
    import difflib
    import unicodedata
    if not texto:
        return None
    t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    claves = {"drog": "Drogas", "ropa": "Ropa", "product": "Productos varios", "varios": "Productos varios",
              "medic": "Medicamentos", "mento": "Medicamentos"}
    for k, v in claves.items():
        if k in t:
            return v
    for pal in t.replace(".", " ").split():
        m = difflib.get_close_matches(pal, ["drogas", "ropa", "productos", "medicamentos"], n=1, cutoff=0.7)
        if m:
            return {"drogas": "Drogas", "ropa": "Ropa", "productos": "Productos varios",
                    "medicamentos": "Medicamentos"}[m[0]]
    return None


def nombre_recorrido(ruta, cargamento=None, dist_inicial=None):
    """'Drogas - Granja 1'; ruta desconocida: 'Drogas - desconocido (5.120 m)'."""
    if ruta is not None:
        c = ruta.get("cargamento") or cargamento or "(cargamento)"
        return f"{c} - {ruta.get('nombre', '?')}"
    extra = f" ({km(dist_inicial)})" if dist_inicial is not None else ""
    return f"{cargamento or '(cargamento)'} - desconocido{extra}"


# 2.7.2: dígitos que el lector del HUD puede confundir (sobre todo con otra resolución)
# leído -> pudo ser (2.7.3: el 0 se lee como 9, 8 o 6; el 3 como 6)
CONFUSIONES = {"0": "689", "6": "0583", "5": "63", "8": "0631", "3": "856", "1": "7", "7": "1", "9": "08"}


_ULT_AVISO = None


def _variantes(dist):
    """Distancias que salen de cambiar UN dígito por uno con el que se confunde (5090 -> 5690, ...)."""
    txt = str(int(round(dist)))
    out = []
    for i, c in enumerate(txt):
        for o in CONFUSIONES.get(c, ""):
            if i == 0 and o == "0":
                continue
            out.append(float(txt[:i] + o + txt[i + 1:]))
    return out


def _mejor_ruta(datos, dist, cargamento):
    mejor = None
    for r in datos.get("rutas", []):
        if cargamento and r.get("cargamento") and r["cargamento"] != cargamento:
            continue
        d = abs(r.get("distancia_inicial", -1e9) - dist)
        if d <= r.get("tolerancia", 80) and (mejor is None or d < mejor[0]):
            mejor = (d, r)
    return mejor


def reconocer(datos, dist_inicial, cargamento=None):
    """Ruta cuya distancia inicial coincide (con su tolerancia). None si ninguna.
    Si se sabe el cargamento, solo se buscan rutas de ese cargamento (o sin cargamento puesto).
    2.7.2: si ninguna coincide, prueba cambiando un dígito mal leído; solo la usa si calza UNA ruta."""
    if dist_inicial is None:
        return None
    mejor = _mejor_ruta(datos, dist_inicial, cargamento)
    if mejor is not None:
        return mejor[1]
    halladas = {}
    for v in _variantes(dist_inicial):
        m = _mejor_ruta(datos, v, cargamento)
        if m is not None:
            halladas[id(m[1])] = m[1]
    global _ULT_AVISO
    if len(halladas) == 1:
        r = next(iter(halladas.values()))
        if _ULT_AVISO != round(dist_inicial):
            _ULT_AVISO = round(dist_inicial)
            print(f"[i] Distancia inicial leída {dist_inicial:.0f} m: parece un dígito mal leído, "
                  f"es {r.get('nombre', '?')} ({r.get('distancia_inicial', 0):.0f} m).")
        return r
    return None


def _comunes(datos, ruta, tramo, dist):
    """Reglas compartidas: "inicio_comun" (tramo 0, camino a cargar) y "regreso_comun" (tramo 2).
    Una ruta puede decir desde qué distancia de la vuelta valen las comunes ("regreso_comun_desde"),
    porque al principio de su vuelta va por otras calles."""
    if tramo == 0:
        return list(datos.get("inicio_comun", []))
    if tramo == 2:
        desde = (ruta or {}).get("regreso_comun_desde")
        comunes = datos.get("regreso_comun", [])
        if desde is not None:
            comunes = [r for r in comunes if r.get("desde", 0) <= desde]
        return list(comunes)
    return []


MARGEN_COMPARTIDO = 40     # m: una regla justo en el borde de un tramo compartido también cuenta


def _slug(ruta):
    return os.path.splitext((ruta or {}).get("_archivo") or "")[0]


def tramos_compartidos(datos, ruta, tramo):
    """2.5.0: [(otro_slug, lo, hi, corrimiento, grupo)] de los tramos compartidos confirmados de esta ruta.
    lo/hi = metros de ESTA ruta; corrimiento = lo que se suma a los metros del otro recorrido para pasar a esta."""
    slug = _slug(ruta)
    out = []
    if not slug:
        return out
    for g in datos.get("compartidos", []):
        if int(g.get("tramo", -1)) != int(tramo):
            continue
        a_lo, a_hi = sorted((float(g["a_hasta"]), float(g["a_desde"])))
        des = float(g.get("desfase", 0))
        if g.get("a") == slug:
            out.append((g.get("b"), a_lo, a_hi, -des, g))
        elif g.get("b") == slug:
            out.append((g.get("a"), a_lo + des, a_hi + des, des, g))
    return out


def reglas_compartidas(datos, ruta, tramo):
    """2.5.0: reglas de OTROS recorridos que valen aquí por un tramo compartido, ya corridas a los metros de esta
    ruta. Devuelve [(copia, archivo_del_otro, indice, corrimiento)]. Se guarda en caché (se rehace al recargar)."""
    cache = datos.setdefault("_cache_compartidas", {})
    clave = (_slug(ruta), str(tramo))
    if clave in cache:
        return cache[clave]
    out = []
    por_slug = {os.path.splitext(r.get("_archivo") or "")[0]: r for r in datos.get("rutas", [])}
    for otro, lo, hi, corr, _g in tramos_compartidos(datos, ruta, tramo):
        r_otro = por_slug.get(otro)
        if r_otro is None:
            continue
        for i, r in enumerate(r_otro.get("reglas", {}).get(str(tramo), [])):
            if r.get("solo_esta_ruta") or r.get("entregar_control") or r.get("general"):
                continue
            centro = (float(r.get("desde", 0)) + float(r.get("hasta", 0))) / 2 + corr
            if not (lo - MARGEN_COMPARTIDO <= centro <= hi + MARGEN_COMPARTIDO):
                continue
            c = dict(r)
            c["desde"] = round(float(r.get("desde", 0)) + corr)
            c["hasta"] = round(float(r.get("hasta", 0)) + corr)
            c["_compartida_de"] = r_otro.get("nombre", otro)
            out.append((c, r_otro.get("_archivo"), i, corr))
    cache[clave] = out
    return out


def _candidatas(datos, ruta, tramo, dist):
    c = []
    if ruta is not None:
        c += ruta.get("reglas", {}).get(str(tramo), [])
        c += [x[0] for x in reglas_compartidas(datos, ruta, tramo)]
    return c + _comunes(datos, ruta, tramo, dist)


def _vale(r, rapido, lento=False):
    return (r.get("activa", True) and (rapido or not r.get("solo_rapido")) and (lento or not r.get("solo_lento"))
            and not r.get("general"))


def reglas_generales(datos, ruta, tramo, rapido=False, lento=False):
    """3.5.0: reglas «general» (todo el tramo) de este recorrido; en el camino a cargar, las de las comunes."""
    lista = list((ruta or {}).get("reglas", {}).get(str(tramo), []))
    if int(tramo) == 0:
        lista += list(datos.get("inicio_comun", []))
    elif int(tramo) == 2:
        lista += list(datos.get("regreso_comun", []))
    return [r for r in lista if r.get("general") and r.get("activa", True)
            and (rapido or not r.get("solo_rapido")) and (lento or not r.get("solo_lento"))]


def combinar(generales, local):
    """3.5.0: la regla que vale ahora = generales + la del lugar encima (la del lugar manda en lo que pida)."""
    if not generales:
        return local
    out, exp = {}, {}
    for g in generales:
        exp.update(g.get("exp") or {})
        out.update({k: v for k, v in g.items() if k not in ("exp", "general", "desde", "hasta")})
    out["nota"] = "General: " + " · ".join(g.get("nota") or "regla general" for g in generales)
    if local is not None:
        exp.update(local.get("exp") or {})
        out.update({k: v for k, v in local.items() if k != "exp"})
    if exp:
        out["exp"] = exp
    out["_con_general"] = True
    return out


def regla_activa(datos, ruta, tramo, dist, rapido=False, lento=False):
    """Regla que aplica ahora (la más restrictiva si se solapan). None si ninguna.
    rapido: modo rápido prendido (2.7.0: las reglas «solo_rapido» solo valen entonces); lento igual (3.5.0).
    Las reglas «general» no cuentan aquí (ver reglas_generales / combinar)."""
    if dist is None:
        return None
    candidatas = _candidatas(datos, ruta, tramo, dist)
    activas = [r for r in candidatas if _vale(r, rapido, lento) and r.get("hasta", 0) <= dist <= r.get("desde", 0)]
    if not activas:
        return None
    return min(activas, key=lambda r: r.get("max_kmh", 999))


def regla_proxima(datos, ruta, tramo, dist, ventana=80.0, rapido=False, lento=False):
    """Regla con límite de velocidad que empieza en los próximos `ventana` metros (para ir bajando)."""
    if dist is None:
        return None
    candidatas = _candidatas(datos, ruta, tramo, dist)
    prox = [r for r in candidatas if _vale(r, rapido, lento) and "max_kmh" in r and dist - ventana <= r.get("desde", 0) < dist]
    return min(prox, key=lambda r: r["max_kmh"]) if prox else None


def reglas_de(datos, ruta, tramo):
    """2.4.0: todas las reglas que pueden aplicar en un tramo, con su origen (para el mapa de la ruta).
    Devuelve [(regla, archivo, clave_lista)]: archivo = nombre en datos/rutas/, clave_lista = "1"/"2" o
    "inicio_comun"/"regreso_comun"."""
    out = []
    if ruta is not None:
        for r in ruta.get("reglas", {}).get(str(tramo), []):
            out.append((r, ruta.get("_archivo"), str(tramo)))
        for c, arch, _i, _corr in reglas_compartidas(datos, ruta, tramo):
            out.append((c, arch, str(tramo)))
    if tramo in (0, 2):
        for r in _comunes(datos, ruta, tramo, None):
            out.append((r, "_comunes.json", "inicio_comun" if tramo == 0 else "regreso_comun"))
    return out

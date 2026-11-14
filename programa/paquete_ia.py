"""
2.5.3: paquete en UN solo archivo para otro asistente de IA (mi_equipo/para_llm/para_ia.txt).

Los planes gratis de algunos asistentes limitan los adjuntos (ChatGPT: pocos archivos por día) o no leen
archivos grandes (Gemini se quedó solo con las observaciones de un CSV de 4 MB). Aquí va todo junto y chico:
- el viaje resumido, separado por trabajo: todas las observaciones, filas cada ~0,3 s desde 12 s antes hasta
  3 s después de cada punto o hito, una fila cada 2 s en el resto, y las filas con evento; columnas útiles;
- las reglas del recorrido (y de los recorridos con los que comparte tramos), _comunes.json y compartidos.json;
- los trazados del recorrido, sin los datos crudos y con un punto cada ~6 m.
"""
import csv
import io
import json
import os
import re

COLUMNAS = ("t", "estado", "tramo", "kmh", "kmh_obj", "rumbo", "giro_adelante", "direccion", "acelerador",
            "freno", "en_calle", "motivo", "dist_punto_m", "zona", "calle", "desvio_cerca", "desplazamiento",
            "condicion", "regla", "rumbo_abs", "evento")
ANTES_S, DESPUES_S = 20.0, 3.0   # 2.5.4: 20 s antes (el hito se marca después de lo que pasó)
PASO_CERCA_S, PASO_LEJOS_S = 0.3, 2.0


def _num(x, dec=1):
    if x in (None, "None"):
        return ""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return x
    return str(int(v)) if v == int(v) and abs(v) < 1e9 else f"{v:.{dec}f}"


def _filas_viaje(ruta):
    coment, datos = [], []
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            (coment if linea.startswith("#") else datos).append(linea)
    filas = list(csv.DictReader(datos)) if datos else []
    return coment, filas


def trabajos_del_viaje(ruta):
    """(comentarios, [(recorrido, filas)], marcas) con los trabajos del viaje (cada «TRABAJO COMPLETADO» cierra uno;
    los pedazos cortos o sin recorrido se juntan con el anterior)."""
    coment, filas = _filas_viaje(ruta)
    marcas = []
    for c in coment:
        m = re.search(r"#\s*(punto|hito)\s+\d+:\s*t=([\d.]+)", c)
        if m:
            marcas.append(float(m.group(2)))
    trabajos, actual = [], []
    for x in filas:
        actual.append(x)
        if "TRABAJO COMPLETADO" in (x.get("evento") or ""):
            trabajos.append(actual)
            actual = []
    if actual:
        trabajos.append(actual)
    juntos = []
    for tr in trabajos:
        if juntos and (len(tr) < 600 or not any((x.get("ruta") or "").strip() for x in tr)
                       or not any(x.get("estado") in ("CONDUCIENDO", "ARRANCANDO", "REPRODUCIENDO") for x in tr)):
            juntos[-1].extend(tr)
        else:
            juntos.append(tr)
    out = []
    for tr in juntos:
        recs = [(x.get("ruta") or "").strip() for x in tr if (x.get("ruta") or "").strip()]
        out.append((max(set(recs), key=recs.count) if recs else "-", tr))
    return coment, out, marcas, len(filas)


def _comentarios_de(coment, recorrido):
    """Cabecera + solo los bloques de observaciones de ese recorrido."""
    out, bloque, rec = [], [], None
    cab = True
    for c in coment:
        if c.startswith("# === OBSERVACIONES"):
            if bloque and (recorrido is None or rec == recorrido):
                out += bloque
            bloque, rec, cab = [c], None, False
            continue
        if cab:
            out.append(c)
            continue
        m = re.match(r"#\s*recorrido:\s*(.+)", c)
        if m and rec is None:
            rec = m.group(1).strip()
        bloque.append(c)
    if bloque and (recorrido is None or rec == recorrido):
        out += bloque
    return out


def _escribir_trabajo(out, n, rec, tr, marcas, cols):
    try:
        t0, t1 = float(tr[0]["t"]), float(tr[-1]["t"])
    except (KeyError, ValueError, IndexError):
        t0 = t1 = 0
    out.write(f"\n=== TRABAJO {n}: {rec} (t {t0:.0f}–{t1:.0f} s) ===\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(cols)
    ult, prev = -1e9, {}
    for x in tr:
        try:
            t = float(x["t"])
        except (KeyError, ValueError):
            continue
        cerca = any(m - ANTES_S <= t <= m + DESPUES_S for m in marcas)
        paso = PASO_CERCA_S if cerca else PASO_LEJOS_S
        if not ((x.get("evento") or "").strip() or t - ult >= paso - 1e-6):
            continue
        ult = t
        fila = []
        for c in cols:
            v = x.get(c)
            if c in ("zona", "calle", "regla"):       # 2.5.5: solo cuando cambian (achica el archivo)
                v = (v or "")[:60] if c == "regla" else (v or "")
                fila.append("" if prev.get(c) == v else (v or "-"))
                prev[c] = v
            elif c in ("estado", "motivo", "evento"):
                fila.append(v or "")
            else:
                fila.append(_num(v, 2 if c in ("direccion", "acelerador", "freno", "en_calle") else 1))
        w.writerow(fila)


def _version_datos_actual():
    try:
        import carpetas
        with open(os.path.join(carpetas.DATOS, "datos.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except Exception:  # noqa
        return None


def resumir_viaje(ruta, indice=None):
    """Texto CSV resumido (con sus observaciones), separado por trabajo. indice: solo ese trabajo (1, 2…)."""
    coment, trabajos, marcas, n_filas = trabajos_del_viaje(ruta)
    elegidos = list(enumerate(trabajos, 1)) if indice is None else [(indice, trabajos[indice - 1])]
    rec_sel = None if indice is None else trabajos[indice - 1][0]
    todas = [x for _r, tr in trabajos for x in tr]
    cols = [c for c in COLUMNAS if todas and c in todas[0]]
    out = io.StringIO()
    out.write("".join(_comentarios_de(coment, rec_sel)).rstrip() + "\n\n")
    m = next((re.match(r"#\s*datos:\s*(\S+)", c) for c in coment if c.startswith("# datos")), None)
    v_viaje, v_hoy = (m.group(1) if m else None), _version_datos_actual()
    if v_viaje and v_hoy and v_viaje != v_hoy:
        out.write(f"(OJO: el viaje se hizo con los datos {v_viaje} y los archivos de reglas que vienen en este "
                  f"paquete son los de AHORA ({v_hoy}): pueden haber cambiado después del viaje. Lo que estaba activo "
                  "en el viaje es la columna «regla»; los archivos son lo que hay hoy.)\n")
    out.write(f"(Resumen: filas cada ~{PASO_CERCA_S} s desde {ANTES_S:.0f} s antes hasta {DESPUES_S:.0f} s después "
              f"de cada punto/hito, una cada {PASO_LEJOS_S:.0f} s en el resto y todas las filas con evento. "
              "zona, calle y regla vacías = igual que la fila anterior. "
              f"El CSV completo tiene {n_filas} filas.)\n")
    for n, (rec, tr) in elegidos:
        _escribir_trabajo(out, n, rec, tr, marcas, cols)
    return out.getvalue()


def trazado_compacto(t, paso_m=6.0):
    t = {k: v for k, v in t.items() if k not in ("crudo",) and not k.startswith("_")}
    pts, ult = [], None
    for p in t.get("puntos", []):
        if ult is None or abs(ult - p[0]) >= paso_m:
            pts.append(p)
            ult = p[0]
    if t.get("puntos") and pts and pts[-1] is not t["puntos"][-1]:
        pts.append(t["puntos"][-1])
    t["puntos"] = pts
    t["_nota"] = (f"puntos cada ~{paso_m:.0f} m (sin datos crudos); [metros, lado_px (− izq, + der), kmh]; "
                  "los 'ajustes' ya están aplicados")
    return t


def armar(destino, viaje, archivos_json, trazados, prompt=None, indice=None):
    """archivos_json: [(nombre, ruta)] ; trazados: [(nombre, dict ya cargado con ajustes aplicados)].
    2.5.4: si viene el prompt, va al principio (basta con adjuntar este archivo y escribir «analiza y pregunta»)."""
    partes = []
    if prompt:
        partes.append("##### INSTRUCCIONES (léelas antes que los datos)\n" + prompt.strip() + "\n\n"
                      "##### FIN DE LAS INSTRUCCIONES. Siguen los datos.\n")
    partes += ["PAQUETE PARA CALIBRAR (Autopiloto de camión). Contiene el viaje resumido, los archivos de reglas, "
              "los tramos compartidos y los trazados. Cada parte empieza con '##### ARCHIVO: nombre'.\n"]
    if viaje and os.path.exists(viaje):
        cual = "" if indice is None else f", solo el trabajo {indice}"
        partes.append(f"##### ARCHIVO: {os.path.basename(viaje)} (resumido{cual})\n{resumir_viaje(viaje, indice)}")
    for nombre, ruta in archivos_json:
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
            partes.append(f"##### ARCHIVO: {nombre}\n{json.dumps(d, ensure_ascii=False, indent=1)}\n")
        except Exception as e:  # noqa
            partes.append(f"##### ARCHIVO: {nombre}\n(no se pudo leer: {e})\n")
    for nombre, t in trazados:
        partes.append(f"##### ARCHIVO: {nombre} (trazado, compacto)\n"
                      f"{json.dumps(trazado_compacto(t), ensure_ascii=False)}\n")
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("\n".join(partes))
    return destino

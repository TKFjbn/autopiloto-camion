"""
Ventana "Mapa de la ruta" (2.4.0, experimental).

- Dibuja el recorrido (ida, vuelta o camino a cargar) armado desde un viaje con rumbo exacto (ver mapa.py).
- Pinta las reglas como tramos de color, los trazados y las grabaciones.
- Al hacer clic en una regla (en el mapa o en la lista) se puede editar, desactivar o borrar. Antes de guardar
  se hace una copia del archivo en mi_equipo/respaldos/rutas/.
- Con el programa en marcha muestra dónde va el camión y cuál es la próxima regla.
"""
import json
import math
import os
import shutil
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import carpetas
import mapa
import rutas
import version

TRAMOS = (("1", "Ida"), ("2", "Vuelta"), ("0", "Camino a cargar"))
CAMPOS_NUM = (("max_kmh", "Velocidad máxima (km/h)"), ("desplazamiento_px", "Lado (− izq, + der, px)"),
              ("esquina_kmh", "Velocidad en esquinas"), ("giro_tardio_px", "Giro en esquinas (más = antes)"),
              ("anticipacion", "Anticipación (0,4 a 1,5)"), ("curva_larga_kmh", "Mínimo en curvas largas"),
              ("aprox_kmh", "Velocidad de llegada"), ("aprox_recto_seg", "Segundos recto al llegar"))
CAMPOS_BOOL = (("sin_freno", "Sin freno (solo soltar)"), ("sin_bifurcacion", "No frenar por bifurcaciones"),
               ("entregar_control", "Entregar el control (tramo manual)"), ("sin_reversa", "Sin marcha atrás"),
               ("solo_esta_ruta", "Solo en esta ruta (no compartir)"),
               ("solo_rapido", "Solo en modo rápido"))


def _color(r):
    if r.get("activa", True) is False:
        return "#7a7a7a"
    if r.get("entregar_control"):
        return "#e24b4a"
    if "esquina_kmh" in r or "giro_tardio_px" in r:
        return "#a35bd6"
    if "max_kmh" in r:
        return "#e08a1e"
    return "#3b82f6"


def _km(m):
    return rutas.km(m)


class VentanaMapa:
    def __init__(self, app):
        self.app = app
        T = app.T
        self.T = T
        self.win = tk.Toplevel(app.root)
        self.win.title("Mapa de la ruta (experimental)")
        self.win.configure(bg=T["bg"])
        self.win.geometry(app.prefs.get("geometria", {}).get("ventana_mapa", "1180x760"))
        self.zoom, self.cx, self.cy = 1.0, 0.0, 0.0
        self.sel = None                   # (archivo, clave_lista, indice)
        self.items = []                   # reglas visibles: (regla, archivo, clave, indice)
        self.corr = {}                    # 2.5.0: (archivo, clave, indice) -> metros a sumar (regla de otro recorrido)
        self.rangos = []                  # 2.5.0: tramos compartidos de este recorrido: (lo, hi, otro, estado)
        self.archivos = {}                # archivo -> json cargado
        self.respaldados = set()
        self.puntos = []
        self.arrastre = None
        self.nueva_pendiente = False
        self._construir()
        self.cargar_recorridos()
        self.win.protocol("WM_DELETE_WINDOW", self.cerrar)
        self._tic()

    # ------------------------------------------------------------ interfaz
    def _construir(self):
        T = self.T
        barra = ttk.Frame(self.win, padding=6)
        barra.pack(fill="x")
        ttk.Label(barra, text="Recorrido:").pack(side="left")
        self.var_rec = tk.StringVar()
        self.cb_rec = ttk.Combobox(barra, textvariable=self.var_rec, state="readonly", width=34)
        self.cb_rec.pack(side="left", padx=4)
        self.cb_rec.bind("<<ComboboxSelected>>", lambda _e: self.recargar(ajustar=True))
        self.var_tramo = tk.StringVar(value="1")
        for v, t in TRAMOS:
            ttk.Radiobutton(barra, text=t, value=v, variable=self.var_tramo,
                            command=lambda: self.recargar(ajustar=True)).pack(side="left", padx=(6, 0))
        ttk.Button(barra, text="Ajustar", command=self.ajustar).pack(side="left", padx=(12, 0))
        self.var_seguir = tk.BooleanVar(value=True)
        ttk.Checkbutton(barra, text="Seguir al camión", variable=self.var_seguir).pack(side="left", padx=6)
        self.var_auto = tk.BooleanVar(value=True)          # 2.7.0: cambiar solo de recorrido/tramo
        ttk.Checkbutton(barra, text="Cambiar solo de tramo", variable=self.var_auto).pack(side="left", padx=6)
        ttk.Button(barra, text="Construir desde viaje…", command=self.construir_desde_viaje).pack(side="right")

        cuerpo = ttk.Frame(self.win)
        cuerpo.pack(fill="both", expand=True)
        self.can = tk.Canvas(cuerpo, bg=T["vista_bg"], highlightthickness=0)
        self.can.pack(side="left", fill="both", expand=True)
        self.can.bind("<Configure>", lambda _e: self.dibujar())
        self.can.bind("<ButtonPress-1>", self._click)
        self.can.bind("<B1-Motion>", self._arrastrar)
        self.can.bind("<ButtonRelease-1>", lambda _e: setattr(self, "arrastre", None))
        self.can.bind("<MouseWheel>", self._rueda)
        self.can.bind("<Button-4>", lambda e: self._rueda(e, 120))
        self.can.bind("<Button-5>", lambda e: self._rueda(e, -120))
        self.can.bind("<Motion>", self._mover_mouse)

        der = ttk.Frame(cuerpo, padding=6, width=360)
        der.pack(side="left", fill="y")
        der.pack_propagate(False)
        ttk.Label(der, text="Reglas de este tramo", style="Titulo.TLabel").pack(anchor="w")
        self.tv = ttk.Treeview(der, columns=("n", "tramo", "nota"), show="headings", height=10)
        for c, t, w in (("n", "#", 30), ("tramo", "Desde → hasta", 110), ("nota", "Nota", 200)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w")
        self.tv.pack(fill="x")
        self.tv.bind("<<TreeviewSelect>>", self._sel_lista)
        fila = ttk.Frame(der)
        fila.pack(fill="x", pady=(4, 0))
        ttk.Button(fila, text="Nueva regla…", command=self.nueva_regla).pack(side="left")
        self.lbl_prox = tk.Label(der, text="", bg=T["bg"], fg=T["morado"], justify="left", wraplength=340, anchor="w")
        self.lbl_prox.pack(fill="x", pady=(6, 0))

        ed = ttk.LabelFrame(der, text=" Editar regla ", padding=6)
        ed.pack(fill="both", expand=True, pady=(6, 0))
        self.ed = ed
        self.var = {}
        r = 0
        for k, t in (("desde", "Desde (m al punto)"), ("hasta", "Hasta (m al punto)")):
            ttk.Label(ed, text=t + ":").grid(row=r, column=0, sticky="w")
            self.var[k] = tk.StringVar()
            ttk.Entry(ed, textvariable=self.var[k], width=10).grid(row=r, column=1, sticky="w")
            r += 1
        ttk.Label(ed, text="Nota:").grid(row=r, column=0, sticky="w")
        self.var["nota"] = tk.StringVar()
        ttk.Entry(ed, textvariable=self.var["nota"], width=30).grid(row=r, column=1, sticky="ew")
        r += 1
        for k, t in CAMPOS_NUM:
            ttk.Label(ed, text=t + ":").grid(row=r, column=0, sticky="w")
            self.var[k] = tk.StringVar()
            ttk.Entry(ed, textvariable=self.var[k], width=10).grid(row=r, column=1, sticky="w")
            r += 1
        for k, t in CAMPOS_BOOL + (("activa", "Activa"),):
            self.var[k] = tk.BooleanVar(value=(k == "activa"))
            ttk.Checkbutton(ed, text=t, variable=self.var[k]).grid(row=r, column=0, columnspan=2, sticky="w")
            r += 1
        ttk.Label(ed, text="Vacío = no se usa ese valor.", style="Tenue.TLabel").grid(row=r, column=0, columnspan=2,
                                                                                    sticky="w")
        r += 1
        bot = ttk.Frame(ed)
        bot.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(bot, text="Guardar", style="Acento.TButton", command=self.guardar_regla).pack(side="left")
        self.btn_act = ttk.Button(bot, text="Desactivar", command=self.alternar_activa)
        self.btn_act.pack(side="left", padx=4)
        ttk.Button(bot, text="Borrar", command=self.borrar_regla).pack(side="left")
        ed.columnconfigure(1, weight=1)

        self.lbl_pie = ttk.Label(self.win, text="", style="Tenue.TLabel", padding=(6, 2))
        self.lbl_pie.pack(fill="x")
        self.tip = None

    # ------------------------------------------------------------ datos
    def cargar_recorridos(self):
        datos = rutas.cargar()
        self.recorridos = {}
        for r in datos["rutas"]:
            self.recorridos[rutas.nombre_recorrido(r)] = r.get("_archivo")
        nombres = list(self.recorridos)
        self.cb_rec.config(values=nombres)
        ap = self.app.ap
        actual = getattr(ap, "recorrido", None) if ap is not None else None
        self.var_rec.set(actual if actual in self.recorridos else (nombres[0] if nombres else ""))
        if ap is not None and getattr(ap, "tramo", None) in (0, 1, 2):
            self.var_tramo.set(str(ap.tramo))
        self.recargar(ajustar=True)

    def _leer(self, archivo):
        ruta = os.path.join(carpetas.RUTAS, archivo)
        with open(ruta, encoding="utf-8") as fh:
            self.archivos[archivo] = json.load(fh)
        return self.archivos[archivo]

    def recargar(self, ajustar=False):
        rec = self.var_rec.get()
        tramo = self.var_tramo.get()
        self.archivos = {}
        self.items = []
        arch = self.recorridos.get(rec)
        ruta = self._leer(arch) if arch else None
        try:
            com = self._leer("_comunes.json")
        except Exception:  # noqa
            com = None
        if ruta is not None:
            for i, r in enumerate(ruta.get("reglas", {}).get(tramo, [])):
                self.items.append((r, arch, tramo, i))
        self.corr = {}
        self.rangos = []
        try:                                                    # 2.5.0: reglas de tramos compartidos
            datos = rutas.cargar()
            r_obj = next((r for r in datos["rutas"] if r.get("_archivo") == arch), None)
            self.nombres = {os.path.splitext(r["_archivo"])[0]: r.get("nombre", r["_archivo"]) for r in datos["rutas"]}
            if r_obj is not None:
                for c, arch_o, i, corr in rutas.reglas_compartidas(datos, r_obj, tramo):
                    if arch_o not in self.archivos:
                        self._leer(arch_o)
                    self.items.append((c, arch_o, tramo, i))
                    self.corr[(arch_o, tramo, i)] = corr
                import compartidos
                todos = dict(datos, compartidos=[g for g in compartidos.cargar().get("tramos", [])
                                                 if g.get("estado") in ("confirmado", "pendiente")])
                for otro, lo, hi, _c, g in rutas.tramos_compartidos(todos, r_obj, tramo):
                    self.rangos.append((lo, hi, self.nombres.get(otro, otro), g.get("estado")))
        except Exception as e:  # noqa
            print(f"[i] Mapa: no se pudieron leer los tramos compartidos: {e}")
        if com is not None and tramo in ("0", "2"):
            clave = "inicio_comun" if tramo == "0" else "regreso_comun"
            desde = (ruta or {}).get("regreso_comun_desde")
            for i, r in enumerate(com.get(clave, [])):
                if tramo == "2" and desde is not None and r.get("desde", 0) > desde:
                    continue
                self.items.append((r, "_comunes.json", clave, i))
        self.items.sort(key=lambda it: -float(it[0].get("desde", 0)))
        m = mapa.cargar(rec) if rec else None
        self.puntos = ((m or {}).get("tramos") or {}).get(tramo) or []
        self.origen = (m or {}).get("origen")
        self._llenar_lista()
        if ajustar:
            self.ajustar()
        else:
            self.dibujar()

    def _llenar_lista(self):
        self.tv.delete(*self.tv.get_children())
        for n, (r, arch, clave, i) in enumerate(self.items, 1):
            com = " (común)" if arch == "_comunes.json" else ""
            if r.get("solo_rapido"):
                com += " (rápido)"
            if (arch, clave, i) in self.corr:
                com = f" (de {r.get('_compartida_de', '?')}, compartida)" + (" (rápido)" if r.get("solo_rapido") else "")
            elif self._en_compartido(r):
                com = " (compartida)"
            apag = " [apagada]" if r.get("activa", True) is False else ""
            self.tv.insert("", "end", iid=f"{arch}|{clave}|{i}",
                           values=(n, f"{_km(r.get('desde'))} → {_km(r.get('hasta'))}",
                                   (r.get("nota") or "") + com + apag))

    def _en_compartido(self, r):
        """¿Esta regla propia cae en un tramo compartido confirmado (y por eso vale también para el otro)?"""
        if r.get("solo_esta_ruta") or r.get("entregar_control"):
            return False
        centro = (float(r.get("desde", 0)) + float(r.get("hasta", 0))) / 2
        m = rutas.MARGEN_COMPARTIDO
        return any(lo - m <= centro <= hi + m for lo, hi, _o, est in self.rangos if est == "confirmado")

    def _mostrada(self, arch, clave, i):
        """La regla como se ve en este recorrido (las de otro recorrido, ya corridas)."""
        for it in self.items:
            if it[1:] == (arch, clave, i):
                return it[0]
        return self._regla(arch, clave, i)

    # ------------------------------------------------------------ dibujo
    def _a_pantalla(self, x, y):
        w = max(1, self.can.winfo_width())
        h = max(1, self.can.winfo_height())
        return (x - self.cx) * self.zoom + w / 2, -(y - self.cy) * self.zoom + h / 2

    def _a_mundo(self, sx, sy):
        w = max(1, self.can.winfo_width())
        h = max(1, self.can.winfo_height())
        return (sx - w / 2) / self.zoom + self.cx, -(sy - h / 2) / self.zoom + self.cy

    def ajustar(self):
        if not self.puntos:
            self.dibujar()
            return
        xs = [p[1] for p in self.puntos]
        ys = [p[2] for p in self.puntos]
        self.cx, self.cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w = max(200, self.can.winfo_width())
        h = max(200, self.can.winfo_height())
        ancho = max(50.0, max(xs) - min(xs))
        alto = max(50.0, max(ys) - min(ys))
        self.zoom = 0.85 * min(w / ancho, h / alto)
        self.dibujar()

    def dibujar(self):
        c = self.can
        c.delete("all")
        T = self.T
        if not self.puntos:
            c.create_text(20, 20, anchor="nw", fill=T["texto2"], width=600, text=(
                "No hay mapa para este tramo todavía.\n\nHaz un viaje con «Rumbo exacto» encendido (pestaña "
                "Experimental): al detener el programa el mapa se arma solo. También puedes usar «Construir desde "
                "viaje…» con un viaje hecho con la 2.4.0 o más nueva.\n\nLas reglas igual se pueden editar en la "
                "lista de la derecha."))
            self.lbl_pie.config(text="")
            return
        for lo, hi, otro, est in self.rangos:                     # 2.5.0: tramos compartidos
            seg = mapa.tramo_entre(self.puntos, hi, lo)
            if len(seg) >= 2:
                sp = [self._a_pantalla(x, y) for x, y in seg]
                c.create_line(*[v for p in sp for v in p], fill="#f1c40f", width=18, capstyle="round",
                              dash=(6, 6) if est != "confirmado" else None)
                mx, my = sp[0]
                c.create_text(mx + 12, my, anchor="w", fill="#f1c40f", font=("Segoe UI", 8, "bold"),
                              text=f"compartido con {otro}" + ("" if est == "confirmado" else " (sin confirmar)"))
        pts = [self._a_pantalla(p[1], p[2]) for p in self.puntos]
        c.create_line(*[v for p in pts for v in p], fill="#9aa0a6", width=5, capstyle="round", joinstyle="round")
        # marcas de kilómetro
        for p in self.puntos:
            if int(p[0]) % 500 == 0 or (len(self.puntos) and p is self.puntos[0]):
                sx, sy = self._a_pantalla(p[1], p[2])
                c.create_oval(sx - 3, sy - 3, sx + 3, sy + 3, fill="#cfd3d7", outline="")
                c.create_text(sx + 6, sy - 6, text=_km(p[0]), fill=T["tenue"], anchor="sw", font=("Segoe UI", 8))
        self._dibujar_trazados()
        for n, (r, arch, clave, i) in enumerate(self.items, 1):
            seg = mapa.tramo_entre(self.puntos, float(r.get("desde", 0)), float(r.get("hasta", 0)))
            if len(seg) < 2:
                continue
            sp = [self._a_pantalla(x, y) for x, y in seg]
            tag = f"r|{arch}|{clave}|{i}"
            elegido = self.sel == (arch, clave, i)
            c.create_line(*[v for p in sp for v in p], fill=_color(r), width=12 if elegido else 8,
                          capstyle="round", tags=("regla", tag),
                          dash=(4, 3) if r.get("activa", True) is False else None)
            mx, my = sp[len(sp) // 2]
            c.create_oval(mx - 9, my - 9, mx + 9, my + 9, fill=T["panel"], outline=_color(r), width=2,
                          tags=("regla", tag))
            c.create_text(mx, my, text=str(n), fill=T["texto"], font=("Segoe UI", 8, "bold"), tags=("regla", tag))
        self._dibujar_grabaciones()
        self._dibujar_camion()
        pend = sum(1 for *_x, est in self.rangos if est != "confirmado")
        self.lbl_pie.config(text=f"Mapa armado desde {self.origen or '-'} · rueda = zoom · arrastrar = mover · "
                                 "clic en una regla = editarla"
                                 + (f" · {pend} tramo(s) compartido(s) sin confirmar: confírmalos en Experimental"
                                    if pend else ""))

    def _dibujar_trazados(self):
        try:
            import grabaciones
            rec, tramo = self.var_rec.get(), int(self.var_tramo.get())
            for t in grabaciones.cargar_trazados():
                if int(t.get("tramo", 1)) != tramo:
                    continue
                if t.get("recorrido") and t["recorrido"] != rec and not (t.get("comun") and tramo == 2):
                    continue
                seg = mapa.tramo_entre(self.puntos, float(t["desde"]), float(t["hasta"]))
                if len(seg) >= 2:
                    sp = [self._a_pantalla(x, y) for x, y in seg]
                    self.can.create_line(*[v for p in sp for v in p], fill="#23a55a", width=3, dash=(6, 4))
        except Exception:  # noqa
            pass

    def _dibujar_grabaciones(self):
        try:
            import grabaciones
            rec, tramo = self.var_rec.get(), int(self.var_tramo.get())
            for g in grabaciones.cargar_todas():
                if g.get("recorrido") != rec or int(g.get("tramo", 1)) != tramo:
                    continue
                disp = g.get("disparo") or {}
                m = disp.get("metros") if disp.get("tipo") == "distancia" else g.get("metros_inicio")
                p = mapa.punto_en(self.puntos, m if m is not None else self.puntos[0][0])
                if p is None:
                    continue
                sx, sy = self._a_pantalla(p[0], p[1])
                self.can.create_rectangle(sx - 6, sy - 6, sx + 6, sy + 6, fill="#c0392b", outline="white")
                self.can.create_text(sx + 9, sy, text="● " + g.get("nombre", "grabación"), anchor="w",
                                     fill=self.T["texto"], font=("Segoe UI", 8))
        except Exception:  # noqa
            pass

    def _dibujar_camion(self):
        ap = self.app.ap
        self.lbl_prox.config(text="")
        if ap is None or getattr(ap, "terminado", False):
            return
        if getattr(ap, "recorrido", None) != self.var_rec.get() or str(getattr(ap, "tramo", "")) != self.var_tramo.get():
            self.lbl_prox.config(text="El camión no está en este recorrido/tramo.")
            return
        try:
            d = ap.dist_fina()
        except Exception:  # noqa
            d = None
        p = mapa.punto_en(self.puntos, d)
        if p is None:
            return
        x, y, ang = p
        r = getattr(getattr(ap, "rumbo", None), "valor", None)
        ang = math.radians(r) if r is not None else ang
        sx, sy = self._a_pantalla(x, y)
        L = 14
        pts = [(sx + L * math.sin(ang), sy - L * math.cos(ang)),
               (sx + 7 * math.sin(ang + 2.5), sy - 7 * math.cos(ang + 2.5)),
               (sx + 7 * math.sin(ang - 2.5), sy - 7 * math.cos(ang - 2.5))]
        self.can.create_polygon(*[v for q in pts for v in q], fill="#ffffff", outline="#000000", width=2)
        if self.var_seguir.get():
            self.cx, self.cy = x, y
        # regla actual y próxima
        actual = getattr(ap, "regla", None)
        prox = None
        for it in self.items:
            r_ = it[0]
            if r_.get("activa", True) is False:
                continue
            if float(r_.get("desde", 0)) < d and (prox is None or float(r_["desde"]) > float(prox["desde"])):
                prox = r_
        partes = [f"Camión a {_km(d)} del punto."]
        if actual:
            partes.append(f"Ahora: {actual.get('nota', '')}")
        if prox is not None:
            partes.append(f"Próxima en {d - float(prox['desde']):.0f} m: {prox.get('nota', '')}"
                          + (f" (máx {prox['max_kmh']} km/h)" if "max_kmh" in prox else ""))
        self.lbl_prox.config(text="\n".join(partes))

    def _seguir_tramo(self):
        """2.7.0: con el autopiloto andando, el mapa pasa solo al recorrido y tramo en que va el camión
        (camino a cargar, ida, vuelta), salvo que se esté editando una regla."""
        ap = self.app.ap
        if ap is None or not self.var_auto.get() or getattr(ap, "terminado", False) or self.sel is not None:
            return
        rec, tramo = getattr(ap, "recorrido", None), getattr(ap, "tramo", None)
        if tramo not in (0, 1, 2):
            return
        cambio = False
        if rec and rec in self.recorridos and rec != self.var_rec.get():
            self.var_rec.set(rec)
            cambio = True
        if str(tramo) != self.var_tramo.get():
            self.var_tramo.set(str(tramo))
            cambio = True
        if cambio:
            self.recargar(ajustar=True)

    def _tic(self):
        try:
            if not self.win.winfo_exists():
                return
            self._seguir_tramo()
            if self.app.ap is not None and self.puntos:
                self.dibujar()
        except tk.TclError:
            return
        except Exception:  # noqa
            pass
        self.win.after(500, self._tic)

    # ------------------------------------------------------------ mouse
    def _item_en(self, e):
        for it in self.can.find_overlapping(e.x - 3, e.y - 3, e.x + 3, e.y + 3)[::-1]:
            for t in self.can.gettags(it):
                if t.startswith("r|"):
                    _r, arch, clave, i = t.split("|")
                    return arch, clave, int(i)
        return None

    def _click(self, e):
        if self.nueva_pendiente and self.puntos:
            self.nueva_pendiente = False
            x, y = self._a_mundo(e.x, e.y)
            p = min(self.puntos, key=lambda q: (q[1] - x) ** 2 + (q[2] - y) ** 2)
            self._crear_regla(round(p[0] + 40), max(0, round(p[0] - 40)))
            return
        k = self._item_en(e)
        if k is not None:
            self.seleccionar(*k)
            return
        self.arrastre = (e.x, e.y, self.cx, self.cy)

    def _arrastrar(self, e):
        if self.arrastre is None:
            return
        x0, y0, cx, cy = self.arrastre
        self.var_seguir.set(False)
        self.cx = cx - (e.x - x0) / self.zoom
        self.cy = cy + (e.y - y0) / self.zoom
        self.dibujar()

    def _rueda(self, e, delta=None):
        d = delta if delta is not None else e.delta
        f = 1.2 if d > 0 else 1 / 1.2
        x, y = self._a_mundo(e.x, e.y)
        self.zoom = max(0.02, min(50.0, self.zoom * f))
        nx, ny = self._a_mundo(e.x, e.y)
        self.cx += x - nx
        self.cy += y - ny
        self.dibujar()

    def _mover_mouse(self, e):
        k = self._item_en(e)
        self.can.delete("tip")              # 2.4.2: texto y recuadro (antes el recuadro quedaba pegado)
        self.tip = None
        if k is None:
            return
        r = self._mostrada(*k)
        if r is None:
            return
        txt = f"{r.get('nota', '')}\n{_km(r.get('desde'))} → {_km(r.get('hasta'))}"
        if k in self.corr:
            txt += f"\n(regla de {r.get('_compartida_de', '?')}, compartida)"
        extras = [f"{t.split(' (')[0]}: {r[c]}" for c, t in CAMPOS_NUM if c in r]
        if extras:
            txt += "\n" + " · ".join(extras)
        self.tip = self.can.create_text(e.x + 14, e.y + 14, text=txt, anchor="nw", fill="#ffffff", width=320,
                                        font=("Segoe UI", 9), tags=("tip",))
        bb = self.can.bbox(self.tip)
        if bb:
            fondo = self.can.create_rectangle(bb[0] - 4, bb[1] - 3, bb[2] + 4, bb[3] + 3, fill="#202225",
                                              outline="#5865f2", tags=("tip",))
            self.can.tag_raise(self.tip, fondo)

    # ------------------------------------------------------------ edición
    def _regla(self, arch, clave, i):
        js = self.archivos.get(arch)
        if js is None:
            return None
        lista = js.get("reglas", {}).get(clave) if clave in ("0", "1", "2") else js.get(clave)
        if lista is None or not (0 <= i < len(lista)):
            return None
        return lista[i]

    def _lista(self, arch, clave):
        js = self.archivos[arch]
        if clave in ("0", "1", "2"):
            return js.setdefault("reglas", {}).setdefault(clave, [])
        return js.setdefault(clave, [])

    def _sel_lista(self, _e=None):
        s = self.tv.selection()
        if s:
            arch, clave, i = s[0].split("|")
            self.seleccionar(arch, clave, int(i), desde_lista=True)

    def seleccionar(self, arch, clave, i, desde_lista=False):
        r = self._regla(arch, clave, i)
        if r is None:
            return
        self.sel = (arch, clave, i)
        corr = self.corr.get((arch, clave, i), 0)
        for k in ("desde", "hasta"):
            self.var[k].set(str(round(float(r.get(k, 0)) + corr)))
        self.var["nota"].set(str(r.get("nota", "")))
        for k, _t in CAMPOS_NUM:
            self.var[k].set("" if k not in r else str(r[k]))
        for k, _t in CAMPOS_BOOL:
            self.var[k].set(bool(r.get(k, False)))
        self.var["activa"].set(r.get("activa", True) is not False)
        self.btn_act.config(text="Activar" if r.get("activa", True) is False else "Desactivar")
        com = " (común a todos los recorridos)" if arch == "_comunes.json" else ""
        if (arch, clave, i) in self.corr:
            com = " · compartida: vale para los dos recorridos"
        elif self._en_compartido(r):
            com = " · compartida: también vale para el otro recorrido"
        self.ed.config(text=f" Editar regla · {arch}{com} ")
        if not desde_lista:
            iid = f"{arch}|{clave}|{i}"
            if self.tv.exists(iid):
                self.tv.selection_set(iid)
                self.tv.see(iid)
        self.dibujar()

    def _num(self, k, entero=False):
        t = self.var[k].get().strip().replace(",", ".")
        if not t:
            return None
        v = float(t)
        return int(round(v)) if entero else (int(v) if v == int(v) and k.endswith("kmh") else v)

    def _escribir(self, arch):
        ruta = os.path.join(carpetas.RUTAS, arch)
        if arch not in self.respaldados:
            dest = os.path.join(carpetas.RESPALDOS, "rutas")
            os.makedirs(dest, exist_ok=True)
            shutil.copy2(ruta, os.path.join(dest, f"{os.path.splitext(arch)[0]}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
            self.respaldados.add(arch)
        js = self.archivos[arch]
        usa_activa = any(r.get("activa", True) is False for lst in
                         list((js.get("reglas") or {}).values()) + [js.get("inicio_comun", []), js.get("regreso_comun", [])]
                         for r in lst)
        if usa_activa and not version.cumple_minimo_de(js.get("programa_minimo"), "2.4.0"):
            js["programa_minimo"] = "2.4.0"
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(js, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
        if self.app.ap is not None:
            self.app.orden("recargar_rutas")

    def guardar_regla(self):
        if self.sel is None:
            messagebox.showinfo("Mapa de la ruta", "Elige una regla (en el mapa o en la lista).", parent=self.win)
            return
        arch, clave, i = self.sel
        r = self._regla(arch, clave, i)
        try:
            desde, hasta = self._num("desde", True), self._num("hasta", True)
            if desde is None or hasta is None or desde <= hasta:
                raise ValueError("«Desde» tiene que ser mayor que «Hasta» (la distancia al punto va bajando).")
            nuevos = {k: self._num(k) for k, _t in CAMPOS_NUM}
        except ValueError as e:
            messagebox.showerror("Mapa de la ruta", f"Revisa los valores: {e}", parent=self.win)
            return
        corr = self.corr.get((arch, clave, i), 0)
        r["desde"], r["hasta"] = int(round(desde - corr)), int(round(hasta - corr))
        r["nota"] = self.var["nota"].get().strip() or r.get("nota", "regla")
        for k, v in nuevos.items():
            if v is None:
                r.pop(k, None)
            else:
                r[k] = v
        for k, _t in CAMPOS_BOOL:
            if self.var[k].get():
                r[k] = True
            else:
                r.pop(k, None)
        if self.var["activa"].get():
            r.pop("activa", None)
        else:
            r["activa"] = False
        try:
            self._escribir(arch)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo guardar:\n{e}", parent=self.win)
            return
        print(f"[OK] Regla guardada: {r['nota']} ({arch}).")
        self.recargar()
        self.seleccionar(arch, clave, i)

    def alternar_activa(self):
        if self.sel is None:
            return
        r = self._regla(*self.sel)
        self.var["activa"].set(r.get("activa", True) is False)
        self.guardar_regla()

    def borrar_regla(self):
        if self.sel is None:
            return
        arch, clave, i = self.sel
        r = self._regla(arch, clave, i)
        com = "\n\nOjo: es una regla COMÚN, vale para todos los recorridos." if arch == "_comunes.json" else ""
        if (arch, clave, i) in self.corr or self._en_compartido(r):
            com = "\n\nOjo: está en un tramo COMPARTIDO, se borra para los dos recorridos."
        if not messagebox.askyesno("Borrar regla", f"¿Borrar «{r.get('nota', '')}»?\n\nSe guarda una copia del "
                                   f"archivo en mi_equipo/respaldos/rutas/.{com}", parent=self.win):
            return
        del self._lista(arch, clave)[i]
        try:
            self._escribir(arch)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo guardar:\n{e}", parent=self.win)
            return
        print(f"[OK] Regla borrada: {r.get('nota', '')} ({arch}).")
        self.sel = None
        self.recargar()

    def nueva_regla(self):
        if self.puntos:
            self.nueva_pendiente = True
            self.lbl_pie.config(text="Haz clic en el mapa donde va la regla nueva (se crea de 80 m; después ajusta "
                                     "«Desde» y «Hasta»).")
        else:
            ap = self.app.ap
            d = None
            try:
                d = ap.dist_fina() if ap is not None else None
            except Exception:  # noqa
                pass
            centro = round(d) if d else 1000
            self._crear_regla(centro + 40, max(0, centro - 40))

    def _crear_regla(self, desde, hasta):
        tramo = self.var_tramo.get()
        rec = self.var_rec.get()
        arch = self.recorridos.get(rec)
        clave = tramo
        if tramo == "0" or arch is None:
            arch, clave = "_comunes.json", "inicio_comun" if tramo == "0" else "regreso_comun"
        if arch not in self.archivos:
            self._leer(arch)
        lista = self._lista(arch, clave)
        lista.append({"desde": int(desde), "hasta": int(hasta), "nota": "Regla nueva (desde el mapa)"})
        lista.sort(key=lambda r: -float(r.get("desde", 0)))
        i = next(n for n, r in enumerate(lista) if r.get("nota") == "Regla nueva (desde el mapa)" and
                 r["desde"] == int(desde))
        try:
            self._escribir(arch)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo guardar:\n{e}", parent=self.win)
            return
        self.recargar()
        self.seleccionar(arch, clave, i)

    # ------------------------------------------------------------ viajes
    def construir_desde_viaje(self):
        ruta = filedialog.askopenfilename(parent=self.win, initialdir=carpetas.VIAJES, title="Viaje con rumbo",
                                          filetypes=(("Viajes", "viaje_*.csv"), ("CSV", "*.csv")))
        if not ruta:
            return
        try:
            hechos = mapa.desde_viaje(ruta)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo armar el mapa:\n{e}", parent=self.win)
            return
        if not hechos:
            messagebox.showinfo("Mapa de la ruta", "Ese viaje no tiene tramos con recorrido reconocido.",
                                parent=self.win)
            return
        txt = "\n".join(f"• {rec}: tramos {', '.join(t)}" for rec, t, _a in hechos)
        print(f"[OK] Mapa armado desde {os.path.basename(ruta)}.")
        messagebox.showinfo("Mapa de la ruta", f"Mapa guardado en datos/mapas/:\n\n{txt}", parent=self.win)
        if hechos[0][0] in self.recorridos:
            self.var_rec.set(hechos[0][0])
        self.recargar(ajustar=True)

    def cerrar(self):
        try:
            self.app.prefs.setdefault("geometria", {})["ventana_mapa"] = self.win.geometry()
            self.app.guardar_prefs()
        except Exception:  # noqa
            pass
        self.win.destroy()
        if getattr(self.app, "ventana_mapa", None) is self:
            self.app.ventana_mapa = None


def abrir(app):
    v = getattr(app, "ventana_mapa", None)
    try:
        if v is not None and v.win.winfo_exists():
            v.win.lift()
            return v
    except Exception:  # noqa
        pass
    app.ventana_mapa = VentanaMapa(app)
    return app.ventana_mapa

"""
Ventana "Mapa de la ruta" (2.4.0; rehecha en la 3.3.0).

- Dibuja el recorrido (ida, vuelta o camino a cargar) armado desde viajes con rumbo exacto (ver mapa.py).
- Reglas como tramos de color; trazados y grabaciones.
- 3.3.0:
  * Nueva regla arrastrando sobre la ruta; la regla elegida tiene extremos para alargarla o acortarla.
  * Bajo el mouse: km y calle de ese punto.
  * Editar por tipo («Bajar velocidad», «Ir más a la izquierda/derecha», «Esquina»...) o en «Avanzado».
  * Puntos de interés (datos/pois.json), calles y zonas sacadas de los viajes, para ubicarse.
  * Abrir un viaje: por dónde pasó (color según la velocidad) y dónde se tomó el control, se chocó o se atascó;
    clic en una marca = crear una regla ahí.
  * Buscador (calle, zona, punto de interés o km), deshacer y aviso de reglas que se pisan.
  * El camino a cargar es uno solo para todos los recorridos, con los puntos donde aparece el camión.
- 3.4.0: vive en la pestaña «Mapa de ruta» de la ventana principal (contenedor); sin él sigue siendo una ventana.
- Antes de guardar se hace una copia del archivo en mi_equipo/respaldos/rutas/.
"""
import copy
import json
import math
import os
import re
import shutil
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import carpetas
import mapa
import pois
import rutas
import version

TRAMOS = (("1", "Ida"), ("2", "Vuelta"), ("0", "Camino a cargar"))
CAMPOS_NUM = (("max_kmh", "Velocidad máxima (km/h)"), ("desplazamiento_px", "Lado (− izq, + der, px)"),
              ("esquina_kmh", "Velocidad en esquinas"), ("giro_tardio_px", "Giro en esquinas (más = antes)"),
              ("anticipacion", "Anticipación (0,4 a 1,5)"), ("curva_larga_kmh", "Mínimo en curvas largas"),
              ("aprox_kmh", "Velocidad de llegada"), ("aprox_recto_seg", "Segundos recto al llegar"),
              ("avance_esquina_px", "Avanzar antes de girar (px, + más / − menos)"))
CAMPOS_BOOL = (("sin_freno", "Sin freno (solo soltar)"), ("sin_bifurcacion", "No frenar por bifurcaciones"),
               ("entregar_control", "Entregar el control (tramo manual)"), ("sin_reversa", "Sin marcha atrás"),
               ("solo_esta_ruta", "Solo en esta ruta (no compartir)"),
               ("solo_rapido", "Solo en modo rápido"), ("solo_lento", "Solo en modo lento"))
# 3.5.0: funciones experimentales que una regla puede prender o apagar en su zona
EXP_REGLA = (("velocidad_sin_vaiven", "Velocidad sin sube y baja"),
             ("velocidad_suave_curvas", "Velocidad suave en curvas"),
             ("lado_suave_autopista", "Lado suave en autopista"),
             ("usar_grabaciones", "Usar grabaciones de teclas"),
             ("yolo_frena", "YOLO frena de verdad"))
EXP_OPC = ("como siempre", "prendida", "apagada")
MODOS = (("lento", "lento"), ("rapido", "rápido"), ("normal", "normal"))
AVANCE_MAX = 5.0
# 3.3.0: tipos de regla -> campos que se muestran
TIPOS = (("velocidad", "Bajar velocidad", ("max_kmh",), ()),
         ("lado", "Ir más a izquierda / derecha", ("desplazamiento_px",), ()),
         ("esquina", "Esquina: velocidad y avanzar antes de girar", ("esquina_kmh", "avance_esquina_px"), ()),
         ("sin_freno", "No frenar (subida)", (), ("sin_freno",)),
         ("entregar", "Entregar el control", (), ("entregar_control",)),
         ("modo", "Modo de velocidad aquí", (), ()),
         ("exp", "Funciones experimentales aquí", (), ()),
         ("avanzado", "Avanzado…", tuple(k for k, _t in CAMPOS_NUM), tuple(k for k, _t in CAMPOS_BOOL)))
LADO_MAX = 6.0
NUEVA_NOTA = "Regla nueva (desde el mapa)"


COLOR_OBS = "#2ecc71"        # 3.4.2: creada desde las observaciones y todavía sin cambios
COLOR_VACIA = "#e08a1e"      # 3.4.2: no pide nada
COLOR_VEL = "#f0c419"        # «Bajar velocidad» (antes naranja)
LEYENDA = (("Creada en observaciones", COLOR_OBS), ("Vacía", COLOR_VACIA), ("Velocidad", COLOR_VEL),
           ("Esquina", "#a35bd6"), ("Lado / otras", "#3b82f6"), ("Entregar control", "#e24b4a"),
           ("Apagada", "#7a7a7a"))
SIN_EFECTO = ("solo_esta_ruta", "solo_rapido")


def vacia(r):
    """3.4.2: la regla no pide nada (sin velocidad, lado, esquina, no frenar, entregar control…)."""
    if r.get("modo") or r.get("exp"):
        return False
    for k, _t in CAMPOS_NUM:
        v = r.get(k)
        if v is not None and not (k == "desplazamiento_px" and float(v) == 0):
            return False
    return not any(r.get(k) for k, _t in CAMPOS_BOOL if k not in SIN_EFECTO)


def _color(r):
    if r.get("origen") == "observacion":
        return COLOR_OBS
    if r.get("activa", True) is False:
        return "#7a7a7a"
    if vacia(r):
        return COLOR_VACIA
    if r.get("entregar_control"):
        return "#e24b4a"
    if "esquina_kmh" in r or "giro_tardio_px" in r:
        return "#a35bd6"
    if "max_kmh" in r:
        return COLOR_VEL
    return "#3b82f6"


def agregar_reglas_observaciones(recorrido, nuevas):
    """3.4.2: escribe reglas creadas en la ventana de observaciones. nuevas = [(tramo, regla)].
    Tramo 0 -> _comunes (camino a cargar); 1 y 2 -> archivo del recorrido (vuelta sin recorrido -> regreso común).
    Guarda antes una copia en mi_equipo/respaldos/rutas/. Devuelve cuántas se escribieron."""
    arch_rec = None
    for r in rutas.cargar()["rutas"]:
        if rutas.nombre_recorrido(r) == recorrido:
            arch_rec = r.get("_archivo")
    por_arch = {}
    for tramo, r in nuevas:
        tramo = int(tramo)
        if tramo == 0:
            arch, clave = "_comunes.json", "inicio_comun"
        elif arch_rec:
            arch, clave = arch_rec, str(tramo)
        elif tramo == 2:
            arch, clave = "_comunes.json", "regreso_comun"
        else:
            print(f"[!] Regla «{r.get('nota')}» no guardada: el recorrido no se reconoció (ida).")
            continue
        r = dict(r, origen="observacion")
        por_arch.setdefault(arch, []).append((clave, r))
    n = 0
    for arch, lst in por_arch.items():
        ruta = os.path.join(carpetas.RUTAS, arch)
        dest = os.path.join(carpetas.RESPALDOS, "rutas")
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(ruta, os.path.join(dest, f"{os.path.splitext(arch)[0]}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
        with open(ruta, encoding="utf-8") as fh:
            js = json.load(fh)
        for clave, r in lst:
            lista = js.setdefault(clave, []) if arch == "_comunes.json" else \
                js.setdefault("reglas", {}).setdefault(clave, [])
            lista.append(r)
            lista.sort(key=lambda x: -float(x.get("desde", 0)))
            n += 1
            print(f"[OK] Regla desde observaciones: {r.get('nota')} ({_km(r['desde'])} → {_km(r['hasta'])}, {arch}).")
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(js, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    return n


def _km(m):
    return rutas.km(m)


def _color_vel(kmh, obj):
    if obj is None or kmh is None:
        return "#9aa0a6"
    if kmh <= obj + 3:
        return "#2ecc71"
    if kmh <= obj + 10:
        return "#f1c40f"
    return "#e74c3c"


def _norm(t):
    t = (t or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    return t


class VentanaMapa:
    def __init__(self, app, contenedor=None):
        self.app = app
        T = app.T
        self.T = T
        self.embebida = contenedor is not None       # 3.4.0: dentro de la pestaña «Mapa de ruta»
        if self.embebida:
            self.win = contenedor
        else:
            self.win = tk.Toplevel(app.root)
            self.win.title("Mapa de la ruta")
            self.win.configure(bg=T["bg"])
            self.win.geometry(app.prefs.get("geometria", {}).get("ventana_mapa", "1280x800"))
        self.zoom, self.cx, self.cy = 1.0, 0.0, 0.0
        self.sel = None                   # (archivo, clave_lista, indice)
        self.items = []                   # reglas visibles: (regla, archivo, clave, indice)
        self.corr = {}                    # 2.5.0: (archivo, clave, indice) -> metros a sumar (regla de otro recorrido)
        self.rangos = []                  # 2.5.0: tramos compartidos de este recorrido: (lo, hi, otro, estado)
        self.comp = []                    # 3.3.0: [(otro_slug, lo, hi, corrimiento)] para los puntos de interés
        self.archivos = {}                # archivo -> json cargado
        self.respaldados = set()
        self.puntos = []
        self.calles, self.zonas, self.lista_pois = [], [], []
        self.camino = None                # 3.3.0: camino a cargar común (apariciones)
        self.viaje = None                 # 3.3.0: viaje abierto encima del mapa
        self.historial = []               # 3.3.0: para deshacer: (archivo o "pois", contenido anterior)
        self.arrastre = None
        self.modo = None                  # None | "nueva" | "creando" | "extremo"
        self.nueva_ini = None
        self.extremo = None               # "desde" | "hasta" mientras se arrastra un extremo
        self.marca = None                 # (x, y, hasta) lugar buscado, se resalta un rato
        self._construir()
        self.cargar_recorridos()
        if not self.embebida:
            self.win.protocol("WM_DELETE_WINDOW", self.cerrar)
        self._tic()

    # ------------------------------------------------------------ interfaz
    def _construir(self):
        T = self.T
        barra = ttk.Frame(self.win, padding=6)
        barra.pack(fill="x")
        ttk.Label(barra, text="Recorrido:").pack(side="left")
        self.var_rec = tk.StringVar()
        self.cb_rec = ttk.Combobox(barra, textvariable=self.var_rec, state="readonly", width=30)
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
        self.btn_viaje = ttk.Button(barra, text="Abrir viaje…", command=self.abrir_viaje)
        self.btn_viaje.pack(side="right", padx=4)
        self.var_buscar = tk.StringVar()
        e = ttk.Entry(barra, textvariable=self.var_buscar, width=26)
        e.pack(side="right", padx=(4, 8))
        e.bind("<Return>", lambda _e: self.buscar())
        ttk.Button(barra, text="Buscar", command=self.buscar).pack(side="right")

        cuerpo = ttk.Frame(self.win)
        cuerpo.pack(fill="both", expand=True)
        self.can = tk.Canvas(cuerpo, bg=T["vista_bg"], highlightthickness=0, cursor="crosshair")
        self.can.pack(side="left", fill="both", expand=True)
        self.can.bind("<Configure>", lambda _e: self.dibujar())
        self.can.bind("<ButtonPress-1>", self._click)
        self.can.bind("<B1-Motion>", self._arrastrar)
        self.can.bind("<ButtonRelease-1>", self._soltar)
        self.can.bind("<ButtonPress-3>", self._menu)
        self.can.bind("<MouseWheel>", self._rueda)
        self.can.bind("<Button-4>", lambda e: self._rueda(e, 120))
        self.can.bind("<Button-5>", lambda e: self._rueda(e, -120))
        self.can.bind("<Motion>", self._mover_mouse)
        self.can.bind("<Leave>", lambda _e: self.can.delete("tip"))
        for w in (self.win, self.can):           # en la pestaña, el teclado llega al mapa al pasar el mouse
            w.bind("<Escape>", lambda _e: self._cancelar_modo())
            w.bind("<Control-z>", lambda _e: self.deshacer())
        self.can.bind("<Enter>", lambda _e: self.can.focus_set(), add="+")

        # 3.6.1: divisor que se arrastra para cambiar el ancho del panel (se recuerda)
        ancho0 = int(self.app.prefs.get("mapa_panel_ancho", 400) or 400)
        divisor = tk.Frame(cuerpo, width=6, bg=T.get("borde", "#3f4147"), cursor="sb_h_double_arrow")
        divisor.pack(side="left", fill="y")
        der_ext = ttk.Frame(cuerpo, width=ancho0)
        der_ext.pack(side="left", fill="y")
        der_ext.pack_propagate(False)
        self._der_ext = der_ext

        def arrastrar(e):
            total = cuerpo.winfo_width()
            x = e.x_root - cuerpo.winfo_rootx()
            ancho = int(max(300, min(total - 300, total - x - 3)))
            der_ext.configure(width=ancho)
            self.tv.column("nota", width=max(240, ancho - 170))

        def soltar(_e):
            self.app.prefs["mapa_panel_ancho"] = int(der_ext.cget("width"))
            try:
                self.app.guardar_prefs()
            except Exception:  # noqa
                pass
        divisor.bind("<B1-Motion>", arrastrar)
        divisor.bind("<ButtonRelease-1>", soltar)
        import desplazable                         # 3.4.1: barra a la derecha si el panel no cabe en la pantalla
        marco, der, self._lienzo_der = desplazable.crear(der_ext, bg=T["bg"], estilo="TFrame", padding=6,
                                                         horizontal=True)      # 3.6.1: y abajo si no cabe a lo ancho
        marco.pack(fill="both", expand=True)
        ttk.Label(der, text="Reglas de este tramo", style="Titulo.TLabel").pack(anchor="w")
        self.tv = ttk.Treeview(der, columns=("n", "tramo", "nota"), show="headings", height=9)
        for c, t, w in (("n", "#", 28), ("tramo", "Desde → hasta", 100), ("nota", "Nota", max(240, ancho0 - 170))):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w")
        self.tv.pack(fill="x")
        self.tv.tag_configure("obs", foreground=COLOR_OBS)        # 3.5.0: verde en la lista también
        self.tv.tag_configure("vacia", foreground=COLOR_VACIA)
        self.tv.bind("<<TreeviewSelect>>", self._sel_lista)
        fila = ttk.Frame(der)
        fila.pack(fill="x", pady=(4, 0))
        ttk.Button(fila, text="+ Nueva regla", style="Acento.TButton", command=self.nueva_regla).pack(side="left")
        self.btn_deshacer = ttk.Button(fila, text="↶ Deshacer", command=self.deshacer, state="disabled")
        self.btn_deshacer.pack(side="left", padx=6)
        self.lbl_prox = tk.Label(der, text="", bg=T["bg"], fg=T["morado"], justify="left", wraplength=370, anchor="w")
        self.lbl_prox.pack(fill="x", pady=(4, 0))

        ed = ttk.LabelFrame(der, text=" Editar regla ", padding=6)
        ed.pack(fill="both", expand=True, pady=(4, 0))
        self.ed = ed
        self.var = {}
        cab = ttk.Frame(ed)
        cab.pack(fill="x")
        self.ent_dh = []
        for k, t in (("desde", "Desde"), ("hasta", "Hasta")):
            ttk.Label(cab, text=t + " (m):").pack(side="left")
            self.var[k] = tk.StringVar()
            e = ttk.Entry(cab, textvariable=self.var[k], width=7)
            e.pack(side="left", padx=(2, 8))
            self.ent_dh.append(e)
        self.var["general"] = tk.BooleanVar(value=False)              # 3.5.0
        ttk.Checkbutton(ed, text="Regla general (todo el tramo de este recorrido)", variable=self.var["general"],
                        command=self._cambio_general).pack(anchor="w")
        self.lbl_cerca = ttk.Label(ed, text="", style="Tenue.TLabel")
        self.lbl_cerca.pack(anchor="w")
        f = ttk.Frame(ed)
        f.pack(fill="x", pady=(2, 0))
        ttk.Label(f, text="Nota:").pack(side="left")
        self.var["nota"] = tk.StringVar()
        ttk.Entry(f, textvariable=self.var["nota"]).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(ed, text="¿Qué quieres que haga?", style="Tenue.TLabel").pack(anchor="w", pady=(6, 0))
        tip = ttk.Frame(ed)
        tip.pack(fill="x")
        self.var_tipo = {}
        for n, (k, t, _c, _b) in enumerate(TIPOS):
            self.var_tipo[k] = tk.BooleanVar(value=False)
            ttk.Checkbutton(tip, text=t, variable=self.var_tipo[k], command=lambda k=k: self._cambio_tipo(k)) \
                .grid(row=n // 2, column=n % 2, sticky="w", padx=(0, 8))
        for k, _t in CAMPOS_NUM:
            self.var[k] = tk.StringVar()
        for k, _t in CAMPOS_BOOL:
            self.var[k] = tk.BooleanVar(value=False)
        self.var["activa"] = tk.BooleanVar(value=True)
        self.var_lado = tk.DoubleVar(value=0.0)
        self.var_avance = tk.DoubleVar(value=0.0)                     # 3.5.0
        self.var["modo"] = tk.StringVar(value="")
        self.var_exp = {k: tk.StringVar(value=EXP_OPC[0]) for k, _t in EXP_REGLA}
        self.campos = ttk.Frame(ed)
        self.campos.pack(fill="x", pady=(4, 0))
        self.lbl_aviso = tk.Label(ed, text="", bg=T["bg"], fg="#f1c40f", justify="left", wraplength=360, anchor="w")
        self.lbl_aviso.pack(fill="x", pady=(4, 0))
        bot = ttk.Frame(ed)
        bot.pack(fill="x", pady=(6, 0), side="bottom")
        ttk.Button(bot, text="Guardar", style="Acento.TButton", command=self.guardar_regla).pack(side="left")
        self.btn_act = ttk.Button(bot, text="Desactivar", command=self.alternar_activa)
        self.btn_act.pack(side="left", padx=4)
        ttk.Button(bot, text="Borrar", command=self.borrar_regla).pack(side="left")
        self._armar_campos()

        pie = ttk.Frame(self.win)
        pie.pack(fill="x")
        ley = ttk.Frame(pie)                      # 3.4.2: leyenda de colores de las reglas
        ley.pack(side="right", padx=6)
        for txt, col in LEYENDA:
            tk.Label(ley, text="■", fg=col, bg=T["bg"], font=("Segoe UI", 10)).pack(side="left")
            ttk.Label(ley, text=txt, style="Tenue.TLabel").pack(side="left", padx=(0, 8))
        self.lbl_pie = ttk.Label(pie, text="", style="Tenue.TLabel", padding=(6, 2))
        self.lbl_pie.pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------ editor por tipos
    def _tipos_de(self, r):
        act = set()
        if "max_kmh" in r:
            act.add("velocidad")
        if "desplazamiento_px" in r:
            act.add("lado")
        if "esquina_kmh" in r or "giro_tardio_px" in r or "avance_esquina_px" in r:
            act.add("esquina")
        if r.get("sin_freno"):
            act.add("sin_freno")
        if r.get("entregar_control"):
            act.add("entregar")
        if r.get("modo"):
            act.add("modo")
        if r.get("exp"):
            act.add("exp")
        otros_num = {k for k, _t in CAMPOS_NUM} - {"max_kmh", "desplazamiento_px", "esquina_kmh", "avance_esquina_px"}
        otros_bool = {k for k, _t in CAMPOS_BOOL} - {"sin_freno", "entregar_control"}
        if any(k in r for k in otros_num) or any(r.get(k) for k in otros_bool):
            act.add("avanzado")
        return act

    def _cambio_tipo(self, k):
        on = self.var_tipo[k].get()
        tipo = next(t for t in TIPOS if t[0] == k)
        if k == "modo":
            self.var["modo"].set(("lento" if not self.var["modo"].get() else self.var["modo"].get()) if on else "")
        if k == "exp" and not on:
            for v in self.var_exp.values():
                v.set(EXP_OPC[0])
        if k == "entregar" and on and self.var["general"].get():
            messagebox.showinfo("Mapa de la ruta", "«Entregar el control» no puede ser general: se usa en un lugar.",
                                parent=self.win)
            self.var_tipo[k].set(False)
            return
        if k != "avanzado":
            for c in tipo[2]:
                if not on:
                    self.var[c].set("")
                elif not self.var[c].get().strip():
                    self.var[c].set({"max_kmh": "40", "esquina_kmh": "25", "giro_tardio_px": "4",
                                     "desplazamiento_px": "0", "avance_esquina_px": "0"}.get(c, ""))
            for c in tipo[3]:
                self.var[c].set(on)
        if k == "lado":
            self._lado_desde_var()
        if k == "esquina":
            self._avance_desde_var()
        self._armar_campos()

    def _cambio_general(self):
        g = self.var["general"].get()
        for e in self.ent_dh:
            e.configure(state="disabled" if g else "normal")
        if g and self.var_tipo["entregar"].get():
            self.var_tipo["entregar"].set(False)
            self.var["entregar_control"].set(False)
            self._armar_campos()
        self.dibujar()

    def _avance_desde_var(self):
        try:
            self.var_avance.set(float(self.var["avance_esquina_px"].get().replace(",", ".") or 0))
        except ValueError:
            self.var_avance.set(0.0)

    def _mover_avance(self, _v=None):
        v = round(self.var_avance.get() * 2) / 2
        self.var["avance_esquina_px"].set(("%g" % v).replace(".", ","))

    def _lado_desde_var(self):
        try:
            self.var_lado.set(float(self.var["desplazamiento_px"].get().replace(",", ".") or 0))
        except ValueError:
            self.var_lado.set(0.0)

    def _mover_lado(self, _v=None):
        v = round(self.var_lado.get() * 2) / 2
        self.var["desplazamiento_px"].set(("%g" % v).replace(".", ","))
        self.dibujar()

    def _armar_campos(self):
        for w in self.campos.winfo_children():
            w.destroy()
        av = self.var_tipo["avanzado"].get()
        nums, bools = [], []
        for k, _t, cn, cb in TIPOS:
            if self.var_tipo[k].get() and k != "avanzado":
                nums += [c for c in cn if c not in nums]
        if av:
            nums = [k for k, _t in CAMPOS_NUM]
            bools = [k for k, _t in CAMPOS_BOOL]
        r = 0
        nombres = dict(CAMPOS_NUM)
        for k in nums:
            if k == "desplazamiento_px" and not av:
                ttk.Label(self.campos, text="Lado:").grid(row=r, column=0, sticky="w")
                fr = ttk.Frame(self.campos)
                fr.grid(row=r, column=1, sticky="ew")
                ttk.Label(fr, text="izq.", style="Tenue.TLabel").pack(side="left")
                ttk.Scale(fr, from_=-LADO_MAX, to=LADO_MAX, variable=self.var_lado, orient="horizontal",
                          command=self._mover_lado).pack(side="left", fill="x", expand=True, padx=4)
                ttk.Label(fr, text="der.", style="Tenue.TLabel").pack(side="left")
                ttk.Label(fr, textvariable=self.var["desplazamiento_px"], width=4).pack(side="left", padx=(4, 0))
            elif k == "avance_esquina_px" and not av:                    # 3.5.0
                ttk.Label(self.campos, text="Avanzar antes\nde girar:").grid(row=r, column=0, sticky="w")
                fr = ttk.Frame(self.campos)
                fr.grid(row=r, column=1, sticky="ew")
                ttk.Label(fr, text="girar antes", style="Tenue.TLabel").pack(side="left")
                ttk.Scale(fr, from_=-AVANCE_MAX, to=AVANCE_MAX, variable=self.var_avance, orient="horizontal",
                          command=self._mover_avance).pack(side="left", fill="x", expand=True, padx=4)
                ttk.Label(fr, text="avanzar más", style="Tenue.TLabel").pack(side="left")
                ttk.Label(fr, textvariable=self.var["avance_esquina_px"], width=4).pack(side="left", padx=(4, 0))
            else:
                ttk.Label(self.campos, text=nombres[k] + ":").grid(row=r, column=0, sticky="w")
                ttk.Entry(self.campos, textvariable=self.var[k], width=8).grid(row=r, column=1, sticky="w")
            r += 1
        if self.var_tipo["modo"].get() or av:                         # 3.5.0
            ttk.Label(self.campos, text="Modo aquí:").grid(row=r, column=0, sticky="w")
            cb = ttk.Combobox(self.campos, state="readonly", width=10, values=[t for _k, t in MODOS] + ["(ninguno)"])
            actual = dict(MODOS).get(self.var["modo"].get(), "(ninguno)")
            cb.set(actual)
            cb.bind("<<ComboboxSelected>>", lambda _e, cb=cb: self.var["modo"].set(
                next((k for k, t in MODOS if t == cb.get()), "")))
            cb.grid(row=r, column=1, sticky="w")
            r += 1
        if self.var_tipo["exp"].get() or av:
            for k, t in EXP_REGLA:
                ttk.Label(self.campos, text=t + ":").grid(row=r, column=0, sticky="w")
                ttk.Combobox(self.campos, state="readonly", width=12, values=EXP_OPC,
                             textvariable=self.var_exp[k]).grid(row=r, column=1, sticky="w")
                r += 1
        nb = dict(CAMPOS_BOOL)
        for k in bools:
            ttk.Checkbutton(self.campos, text=nb[k], variable=self.var[k]).grid(row=r, column=0, columnspan=2,
                                                                               sticky="w")
            r += 1
        if av:
            ttk.Checkbutton(self.campos, text="Activa", variable=self.var["activa"]).grid(row=r, column=0,
                                                                                         sticky="w")
            r += 1
            ttk.Label(self.campos, text="Vacío = no se usa ese valor.", style="Tenue.TLabel") \
                .grid(row=r, column=0, columnspan=2, sticky="w")
        self.campos.columnconfigure(1, weight=1)

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
        self.comp = []
        r_obj = None
        try:                                                    # 2.5.0: reglas de tramos compartidos
            datos = rutas.cargar()
            r_obj = next((r for r in datos["rutas"] if r.get("_archivo") == arch), None)
            self.nombres = {os.path.splitext(r["_archivo"])[0]: r.get("nombre", r["_archivo"]) for r in datos["rutas"]}
            if r_obj is not None and tramo != "0":
                for c, arch_o, i, corr in rutas.reglas_compartidas(datos, r_obj, tramo):
                    if arch_o not in self.archivos:
                        self._leer(arch_o)
                    self.items.append((c, arch_o, tramo, i))
                    self.corr[(arch_o, tramo, i)] = corr
                import compartidos
                todos = dict(datos, compartidos=[g for g in compartidos.cargar().get("tramos", [])
                                                 if g.get("estado") in ("confirmado", "pendiente")])
                for otro, lo, hi, c_, g in rutas.tramos_compartidos(todos, r_obj, tramo):
                    self.rangos.append((lo, hi, self.nombres.get(otro, otro), g.get("estado")))
                    if g.get("estado") == "confirmado":
                        self.comp.append((otro, lo, hi, c_))
        except Exception as e:  # noqa
            print(f"[i] Mapa: no se pudieron leer los tramos compartidos: {e}")
        if com is not None and tramo in ("0", "2"):
            clave = "inicio_comun" if tramo == "0" else "regreso_comun"
            desde = (ruta or {}).get("regreso_comun_desde")
            for i, r in enumerate(com.get(clave, [])):
                if tramo == "2" and desde is not None and r.get("desde", 0) > desde:
                    continue
                self.items.append((r, "_comunes.json", clave, i))
        self.items.sort(key=lambda it: (0 if it[0].get("general") else 1, -float(it[0].get("desde", 0))))
        self.camino = None
        if tramo == "0":                                         # 3.3.0: camino a cargar común
            try:
                self.camino = mapa.cargar_camino()
            except Exception as e:  # noqa
                print(f"[i] Mapa: no se pudo armar el camino a cargar: {e}")
            c = self.camino or {}
            self.puntos = c.get("pts") or []
            self.origen = c.get("origen")
            self.calles, self.zonas = c.get("calles") or [], c.get("zonas") or []
        else:
            m = mapa.cargar(rec) if rec else None
            self.puntos = ((m or {}).get("tramos") or {}).get(tramo) or []
            self.origen = (m or {}).get("origen")
            self.calles = ((m or {}).get("calles") or {}).get(tramo) or []
            self.zonas = ((m or {}).get("zonas") or {}).get(tramo) or []
        try:
            self.lista_pois = pois.para_tramo(arch, tramo, self.comp, (r_obj or {}).get("regreso_comun_desde"))
        except Exception as e:  # noqa
            print(f"[i] Mapa: no se pudieron leer los puntos de interés: {e}")
            self.lista_pois = []
        if self.sel is not None and self._regla(*self.sel) is None:
            self.sel = None
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
            if r.get("origen") == "observacion":
                apag += " [de observaciones]"
            elif vacia(r):
                apag += " [vacía]"
            if r.get("modo"):
                apag += f" [modo {dict(MODOS).get(r['modo'], r['modo'])}]"
            if r.get("general"):
                rango, cerca = "todo el tramo", ""
            else:
                p = pois.cerca_de(self.lista_pois, (float(r.get("desde", 0)) + float(r.get("hasta", 0))) / 2)
                cerca = f" · cerca de: {p['nombre']}" if p else ""
                rango = f"{_km(r.get('desde'))} → {_km(r.get('hasta'))}"
            etq = ("obs",) if r.get("origen") == "observacion" else (("vacia",) if vacia(r) else ())
            self.tv.insert("", "end", iid=f"{arch}|{clave}|{i}", tags=etq,
                           values=(n, rango, (r.get("nota") or "") + com + apag + cerca))

    def _en_compartido(self, r):
        """¿Esta regla propia cae en un tramo compartido confirmado (y por eso vale también para el otro)?"""
        if r.get("solo_esta_ruta") or r.get("entregar_control") or r.get("general"):
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

    # ------------------------------------------------------------ geometría
    def _a_pantalla(self, x, y):
        w = max(1, self.can.winfo_width())
        h = max(1, self.can.winfo_height())
        return (x - self.cx) * self.zoom + w / 2, -(y - self.cy) * self.zoom + h / 2

    def _a_mundo(self, sx, sy):
        w = max(1, self.can.winfo_width())
        h = max(1, self.can.winfo_height())
        return (sx - w / 2) / self.zoom + self.cx, -(sy - h / 2) / self.zoom + self.cy

    def _metros_en(self, sx, sy):
        """Punto de la ruta más cercano al mouse: (metros, distancia en px) o (None, inf)."""
        if len(self.puntos) < 2:
            return None, float("inf")
        x, y = self._a_mundo(sx, sy)
        mejor = (None, float("inf"))
        for a, b in zip(self.puntos, self.puntos[1:]):
            dx, dy = b[1] - a[1], b[2] - a[2]
            L = dx * dx + dy * dy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - a[1]) * dx + (y - a[2]) * dy) / L))
            px, py = a[1] + t * dx, a[2] + t * dy
            d = math.hypot(x - px, y - py) * self.zoom
            if d < mejor[1]:
                mejor = (a[0] + (b[0] - a[0]) * t, d)
        return mejor

    def _calle_en(self, metros):
        nombre = None
        for m, n in self.calles:                  # empiezan en m y siguen mientras la distancia baja
            if m >= metros:
                nombre = n
        return nombre

    def _zona_en(self, metros):
        nombre = None
        for m, n in self.zonas:
            if m >= metros:
                nombre = n
        return nombre

    def ajustar(self):
        pts = [(p[1], p[2]) for p in self.puntos]
        for a in (self.camino or {}).get("apariciones", []):
            pts += [tuple(q) for q in a.get("rama", [])] + [(a["x"], a["y"])]
        if not pts:
            self.dibujar()
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.cx, self.cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w = max(200, self.can.winfo_width())
        h = max(200, self.can.winfo_height())
        ancho = max(50.0, max(xs) - min(xs))
        alto = max(50.0, max(ys) - min(ys))
        self.zoom = 0.85 * min(w / ancho, h / alto)
        self.dibujar()

    # ------------------------------------------------------------ dibujo
    def dibujar(self):
        c = self.can
        c.delete("all")
        T = self.T
        if not self.puntos:
            if self.var_tramo.get() == "0":
                txt = ("No hay mapa del camino a cargar todavía.\n\nEl camino a cargar es uno solo para todos los "
                       "recorridos: se arma con tus viajes (con «Rumbo exacto» encendido) al detener el programa, o "
                       "con «Construir desde viaje…».")
            else:
                txt = ("No hay mapa para este tramo todavía.\n\nHaz un viaje con «Rumbo exacto» encendido (pestaña "
                       "Experimental): al detener el programa el mapa se arma solo. También puedes usar «Construir "
                       "desde viaje…» con un viaje hecho con la 2.4.0 o más nueva.\n\nLas reglas igual se pueden "
                       "editar en la lista de la derecha.")
            c.create_text(20, 20, anchor="nw", fill=T["texto2"], width=600, text=txt)
            self.lbl_pie.config(text="")
            return
        self._ocupado, self._ocupado_zonas = [], []
        self._dibujar_zonas()
        for lo, hi, otro, est in self.rangos:                     # 2.5.0: tramos compartidos
            seg = mapa.tramo_entre(self.puntos, hi, lo)
            if len(seg) >= 2:
                sp = [self._a_pantalla(x, y) for x, y in seg]
                c.create_line(*[v for p in sp for v in p], fill="#f1c40f", width=18, capstyle="round",
                              dash=(6, 6) if est != "confirmado" else None)
                mx, my = sp[0]
                c.create_text(mx + 12, my, anchor="w", fill="#f1c40f", font=("Segoe UI", 8, "bold"),
                              text=f"compartido con {otro}" + ("" if est == "confirmado" else " (sin confirmar)"))
        self._dibujar_apariciones()
        pts = [self._a_pantalla(p[1], p[2]) for p in self.puntos]
        c.create_line(*[v for p in pts for v in p], fill="#9aa0a6", width=5, capstyle="round", joinstyle="round")
        # marcas de kilómetro
        paso = 500 if self.zoom < 0.5 else 100
        for p in self.puntos:
            if int(p[0]) % paso == 0 or p is self.puntos[0]:
                sx, sy = self._a_pantalla(p[1], p[2])
                c.create_oval(sx - 3, sy - 3, sx + 3, sy + 3, fill="#cfd3d7", outline="")
                c.create_text(sx + 6, sy - 6, text=_km(p[0]), fill=T["tenue"], anchor="sw", font=("Segoe UI", 8))
        self._dibujar_trazados()
        self._dibujar_huella()
        generales = []
        for n, (r, arch, clave, i) in enumerate(self.items, 1):
            if r.get("general"):                          # 3.5.0: no tiene lugar en la ruta
                if r.get("activa", True) is not False:
                    generales.append(f"{n}. {r.get('nota') or 'regla general'}")
                continue
            elegido = self.sel == (arch, clave, i)
            desde, hasta = float(r.get("desde", 0)), float(r.get("hasta", 0))
            if elegido and self.modo == "extremo":
                try:
                    desde, hasta = float(self.var["desde"].get()), float(self.var["hasta"].get())
                except ValueError:
                    pass
            seg = mapa.tramo_entre(self.puntos, desde, hasta)
            if len(seg) < 2:
                continue
            sp = [self._a_pantalla(x, y) for x, y in seg]
            tag = f"r|{arch}|{clave}|{i}"
            extra = ("obs",) if r.get("origen") == "observacion" else ()     # 3.5.0: encima de todo
            if elegido:
                c.create_line(*[v for p in sp for v in p], fill="#ffffff", width=15, capstyle="round",
                              tags=("elegida",))
            c.create_line(*[v for p in sp for v in p], fill=_color(r), width=10 if elegido else 8,
                          capstyle="round", tags=("regla", tag) + extra,
                          dash=(4, 3) if r.get("activa", True) is False else None)
            mx, my = sp[len(sp) // 2]
            c.create_oval(mx - 9, my - 9, mx + 9, my + 9, fill=T["panel"], outline=_color(r), width=2,
                          tags=("regla", tag, "icono") + extra)
            c.create_text(mx, my, text=str(n), fill=T["texto"], font=("Segoe UI", 8, "bold"),
                          tags=("regla", tag, "icono") + extra)
            if elegido:
                self._dibujar_elegida(sp, desde, hasta, r)
        if self.modo == "creando" and self.nueva_ini is not None:
            a, b = self.nueva_ini
            seg = mapa.tramo_entre(self.puntos, max(a, b), min(a, b))
            if len(seg) >= 2:
                sp = [self._a_pantalla(x, y) for x, y in seg]
                c.create_line(*[v for p in sp for v in p], fill="#5865f2", width=10, capstyle="round")
                ex, ey = sp[-1] if b < a else sp[0]
                self._cartel(ex + 14, ey - 34, f"{_km(max(a, b))} → {_km(min(a, b))}  ({abs(a - b):.0f} m)")
        self._dibujar_pois()                   # primero los puntos de interés: si no caben, se esconde la calle
        self._dibujar_calles()
        self._dibujar_eventos()
        self._dibujar_grabaciones()
        self._dibujar_camion()
        if self.marca and time.time() < self.marca[2]:
            sx, sy = self._a_pantalla(self.marca[0], self.marca[1])
            c.create_oval(sx - 22, sy - 22, sx + 22, sy + 22, outline="#f1c40f", width=3)
        # 3.5.0: las reglas nuevas (de observaciones) y la elegida, encima de la ruta, calles y otras reglas
        capas = ["obs"]
        if self.sel is not None:
            capas += ["elegida", "r|{}|{}|{}".format(*self.sel), "extremo", "cartel"]
        for t in capas:
            try:
                c.tag_raise(t)
            except tk.TclError:
                pass
        if generales:
            self._cartel(12, 12, "Reglas generales de este tramo:\n" + "\n".join(generales[:5]), tag="generales")
        self._pie()

    def _pie(self):
        if self.modo == "nueva":
            txt = "Nueva regla: mantén apretado el clic donde empieza y arrastra por la ruta hasta donde termina (Esc = cancelar)."
        elif self.modo == "creando":
            txt = "Suelta donde termina la regla."
        else:
            pend = sum(1 for *_x, est in self.rangos if est != "confirmado")
            txt = (f"Mapa armado desde {self.origen or '-'} · rueda = zoom · arrastrar = mover · clic en una regla = "
                   "editarla · clic derecho en la ruta = punto de interés o regla"
                   + (" · clic en ▲ = crear regla ahí" if self.viaje else "")
                   + (f" · {pend} tramo(s) compartido(s) sin confirmar" if pend else ""))
        self.lbl_pie.config(text=txt)

    def _cartel(self, x, y, texto, borde="#5865f2", tag="cartel"):
        t = self.can.create_text(x, y, text=texto, anchor="nw", fill="#ffffff", font=("Segoe UI", 9, "bold"),
                                 tags=(tag,))
        bb = self.can.bbox(t)
        if bb:
            f = self.can.create_rectangle(bb[0] - 5, bb[1] - 3, bb[2] + 5, bb[3] + 3, fill="#202225", outline=borde,
                                          tags=(tag,))
            self.can.tag_raise(t, f)

    def _dibujar_elegida(self, sp, desde, hasta, r):
        c = self.can
        for (x, y), cual in ((sp[0], "desde"), (sp[-1], "hasta")):
            c.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#ffffff", outline="#5865f2", width=3,
                          tags=("extremo", f"h|{cual}"))
        mx, my = sp[len(sp) // 2]
        self._cartel(mx + 16, my - 40, f"{_km(desde)} → {_km(hasta)}  ({desde - hasta:.0f} m)\n"
                                        "arrastra los extremos para ajustar")
        # vista previa del lado: una línea corrida hacia donde irá el camión
        try:
            lado = float((self.var["desplazamiento_px"].get() or "0").replace(",", "."))
        except ValueError:
            lado = 0.0
        if abs(lado) >= 0.5 and len(sp) >= 2:
            off = lado * 5.0                   # px del minimapa -> px en pantalla, solo para ver hacia dónde
            corr = []
            for k in range(len(sp)):
                a, b = sp[max(0, k - 1)], sp[min(len(sp) - 1, k + 1)]
                dx, dy = b[0] - a[0], b[1] - a[1]
                n = math.hypot(dx, dy) or 1.0
                corr.append((sp[k][0] - dy / n * off, sp[k][1] + dx / n * off))
            c.create_line(*[v for p in corr for v in p], fill="#ffffff", width=2, dash=(4, 4))

    def _lugar_libre(self, item, margen=4, lista=None):
        """3.3.0: True si el texto no tapa a otro ya puesto; si lo tapa, lo borra (queda solo el ícono)."""
        bb = self.can.bbox(item)
        if not bb:
            return False
        a = (bb[0] - margen, bb[1] - margen, bb[2] + margen, bb[3] + margen)
        lista = self._ocupado if lista is None else lista
        for o in lista:
            if a[0] < o[2] and a[2] > o[0] and a[1] < o[3] and a[3] > o[1]:
                self.can.delete(item)
                return False
        lista.append(a)
        return True

    def _dibujar_zonas(self):
        for m, n in self.zonas:
            p = mapa.punto_en(self.puntos, m - 120)
            if p is None:
                continue
            sx, sy = self._a_pantalla(p[0], p[1])
            t = self.can.create_text(sx + 28, sy - 10, text=n.upper(), anchor="w", fill="#3e424a",
                                     font=("Segoe UI", 16 if self.zoom < 0.6 else 20, "bold"))
            self._lugar_libre(t, 8, self._ocupado_zonas)     # las zonas van de fondo: solo no se pisan entre sí

    def _dibujar_calles(self):
        if self.zoom < 0.3:                        # alejado: solo las zonas (si no, se amontonan)
            return
        for m, n in self.calles:
            p = mapa.punto_en(self.puntos, m)
            if p is None:
                continue
            sx, sy = self._a_pantalla(p[0], p[1])
            t = self.can.create_text(sx + 12, sy + 14, text="→ " + n, anchor="nw", fill="#b9bbbe",
                                     font=("Segoe UI", 8))
            bb = self.can.bbox(t) if self._lugar_libre(t) else None
            if bb:
                f = self.can.create_rectangle(bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2, fill="#2b2d31", outline="")
                self.can.tag_raise(t, f)

    def _dibujar_pois(self):
        c = self.can
        for p, m, otro in self.lista_pois:
            q = mapa.punto_en(self.puntos, min(m, self.puntos[0][0]))
            if q is None:
                continue
            sx, sy = self._a_pantalla(q[0], q[1])
            tag = f"poi|{p['id']}"
            sim = pois.ICONOS.get(p.get("icono"), pois.ICONOS["punto"])[0]
            c.create_oval(sx - 11, sy - 11, sx + 11, sy + 11, fill="#5865f2", outline="#ffffff", width=2,
                          tags=("poi", tag))
            self._ocupado.append((sx - 12, sy - 12, sx + 12, sy + 12))
            c.create_text(sx, sy, text=sim, fill="#ffffff", font=("Segoe UI", 9, "bold"), tags=("poi", tag))
            if self.zoom >= 0.12:
                t = c.create_text(sx + 16, sy, text=p.get("nombre", ""), anchor="w", fill="#ffffff",
                                  font=("Segoe UI", 9, "bold"), tags=("poi", tag))
                bb = c.bbox(t) if self._lugar_libre(t) else None
                if bb:
                    f = c.create_rectangle(bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2,
                                           fill="#4752c4" if not otro else "#3d4373", outline="", tags=("poi", tag))
                    c.tag_raise(t, f)

    def _dibujar_apariciones(self):
        cam = self.camino
        if not cam:
            return
        c = self.can
        aps = cam.get("apariciones", [])
        if aps:
            xs = [a["x"] for a in aps]
            ys = [a["y"] for a in aps]
            (x0, y0), (x1, y1) = self._a_pantalla(min(xs), max(ys)), self._a_pantalla(max(xs), min(ys))
            pad = 18
            c.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad, outline="#2ecc71", width=2, fill="#2ecc71",
                               stipple="gray25")
            c.create_text(x0 - pad, y0 - pad - 4, text="Zona de aparición del camión", anchor="sw", fill="#2ecc71",
                          font=("Segoe UI", 9, "bold"))
        for a in aps:
            rama = [self._a_pantalla(x, y) for x, y in a.get("rama", [])]
            if len(rama) >= 2:
                c.create_line(*[v for p in rama for v in p], fill="#2ecc71", width=2, dash=(4, 4))
            sx, sy = self._a_pantalla(a["x"], a["y"])
            c.create_rectangle(sx - 5, sy - 5, sx + 5, sy + 5, fill="#2ecc71", outline="#ffffff",
                               tags=("aparicion",))
        # dónde empieza la ruta común
        p0 = self.puntos[0]
        sx, sy = self._a_pantalla(p0[1], p0[2])
        c.create_text(sx + 10, sy + 12, text=f"Aquí el camión ya va por la calle ({_km(cam.get('comun_desde'))})",
                      anchor="nw", fill="#2ecc71", font=("Segoe UI", 8))

    def _dibujar_huella(self):
        v = self.viaje
        if not v:
            return
        tramo = self.var_tramo.get()
        if tramo != "0" and v.get("recorrido") and v["recorrido"] != self.var_rec.get():
            return
        prev, m_prev = None, None
        for m, k, o in v.get("huella", {}).get(tramo, []):
            q = mapa.punto_en(self.puntos, m)
            if q is None:
                prev = None
                continue
            p = self._a_pantalla(q[0], q[1])
            # un salto en la distancia (lectura mala, ruta recalculada) corta la línea: no se une con una recta
            if prev is not None and abs(m - m_prev) <= 150:
                self.can.create_line(prev[0], prev[1], p[0], p[1], fill=_color_vel(k, o), width=3)
            prev, m_prev = p, m

    def _dibujar_eventos(self):
        v = self.viaje
        if not v:
            return
        tramo = self.var_tramo.get()
        if tramo != "0" and v.get("recorrido") and v["recorrido"] != self.var_rec.get():
            return
        c = self.can
        for n, e in enumerate(v.get("eventos", [])):
            if e.get("tramo") != tramo:
                continue
            q = mapa.punto_en(self.puntos, e["metros"])
            if q is None:
                continue
            sx, sy = self._a_pantalla(q[0], q[1])
            sx, sy = sx - 14, sy + 14
            color = {"choque": "#e74c3c", "manual": "#e67e22", "atascado": "#c0392b", "fuera": "#f1c40f"}.get(
                e["tipo"], "#e74c3c")
            c.create_polygon(sx, sy - 10, sx - 9, sy + 7, sx + 9, sy + 7, fill=color, outline="#ffffff",
                             tags=("evento", f"e|{n}"))

    def _dibujar_trazados(self):
        try:
            import grabaciones
            rec, tramo = self.var_rec.get(), int(self.var_tramo.get())
            for t in grabaciones.cargar_trazados():
                if int(t.get("tramo", 1)) != tramo:
                    continue
                if t.get("recorrido") and t["recorrido"] != rec and not (t.get("comun") and tramo == 2) \
                        and tramo != 0:
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
                if (g.get("recorrido") != rec and tramo != 0) or int(g.get("tramo", 1)) != tramo:
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
        tramo = self.var_tramo.get()
        if str(getattr(ap, "tramo", "")) != tramo or \
                (tramo != "0" and getattr(ap, "recorrido", None) != self.var_rec.get()):
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
        if self.var_seguir.get() and self.modo is None:
            self.cx, self.cy = x, y
        actual = getattr(ap, "regla", None)
        prox = None
        for it in self.items:
            r_ = it[0]
            if r_.get("activa", True) is False or r_.get("general"):
                continue
            if float(r_.get("desde", 0)) < d and (prox is None or float(r_["desde"]) > float(prox["desde"])):
                prox = r_
        calle = self._calle_en(d)
        partes = [f"Camión a {_km(d)} del punto" + (f" · {calle}" if calle else "") + "."]
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
        if ap is None or not self.var_auto.get() or getattr(ap, "terminado", False) or self.sel is not None \
                or self.modo is not None:
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
            if self.embebida and self.app.nb.select() != str(getattr(self.app, "tab_mapa", self.win)):
                self.win.after(500, self._tic)               # pestaña escondida: no dibujar
                return
            self._seguir_tramo()
            if (self.app.ap is not None and self.puntos and self.modo is None) or \
                    (self.marca and time.time() > self.marca[2] - 0.6):
                if self.marca and time.time() > self.marca[2]:
                    self.marca = None
                self.dibujar()
        except tk.TclError:
            return
        except Exception:  # noqa
            pass
        self.win.after(500, self._tic)

    # ------------------------------------------------------------ mouse
    def _item_en(self, e, prefijo="r|"):
        for it in self.can.find_overlapping(e.x - 3, e.y - 3, e.x + 3, e.y + 3)[::-1]:
            for t in self.can.gettags(it):
                if t.startswith(prefijo):
                    return t
        return None

    def _regla_en(self, e):
        t = self._item_en(e, "r|")
        if t is None:
            return None
        _r, arch, clave, i = t.split("|")
        return arch, clave, int(i)

    def _cancelar_modo(self):
        self.modo, self.nueva_ini, self.extremo = None, None, None
        self.dibujar()

    def _click(self, e):
        if self.modo == "nueva":
            m, d = self._metros_en(e.x, e.y)
            if m is None or d > 25:
                self.lbl_pie.config(text="Apreta sobre la ruta (la línea gris). Esc = cancelar.")
                return
            self.modo = "creando"
            self.nueva_ini = (m, m)
            self.dibujar()
            return
        h = self._item_en(e, "h|")
        if h is not None and self.sel is not None:
            self.modo, self.extremo = "extremo", h.split("|")[1]
            return
        ev = self._item_en(e, "e|")
        if ev is not None and self.viaje:
            self._regla_desde_evento(self.viaje["eventos"][int(ev.split("|")[1])])
            return
        k = self._regla_en(e)
        if k is not None:
            self.seleccionar(*k)
            return
        self.arrastre = (e.x, e.y, self.cx, self.cy)

    def _arrastrar(self, e):
        if self.modo == "creando":
            m, _d = self._metros_en(e.x, e.y)
            if m is not None:
                self.nueva_ini = (self.nueva_ini[0], m)
                self.dibujar()
            return
        if self.modo == "extremo":
            m, _d = self._metros_en(e.x, e.y)
            if m is not None:
                try:
                    desde, hasta = float(self.var["desde"].get()), float(self.var["hasta"].get())
                except ValueError:
                    return
                if self.extremo == "desde":
                    desde = max(m, hasta + 10)
                else:
                    hasta = min(m, desde - 10)
                self.var["desde"].set(str(round(desde)))
                self.var["hasta"].set(str(round(max(0.0, hasta))))
                self.dibujar()
            return
        if self.arrastre is None:
            return
        x0, y0, cx, cy = self.arrastre
        self.var_seguir.set(False)
        self.cx = cx - (e.x - x0) / self.zoom
        self.cy = cy + (e.y - y0) / self.zoom
        self.dibujar()

    def _soltar(self, _e):
        self.arrastre = None
        if self.modo == "creando":
            a, b = self.nueva_ini
            self.modo, self.nueva_ini = None, None
            desde, hasta = max(a, b), min(a, b)
            if desde - hasta < 20:                  # un clic sin arrastrar: 80 m alrededor
                c = (desde + hasta) / 2
                desde, hasta = c + 40, max(0.0, c - 40)
            self._crear_regla(round(desde), round(hasta))
            return
        if self.modo == "extremo":
            self.modo, self.extremo = None, None
            self.guardar_regla()

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
        self.can.delete("tip")
        lineas = []
        k = self._regla_en(e)
        poi = self._item_en(e, "poi|")
        ev = self._item_en(e, "e|")
        if ev is not None and self.viaje:
            x = self.viaje["eventos"][int(ev.split("|")[1])]
            lineas = [x["texto"], f"a {_km(x['metros'])} · clic = crear una regla aquí"]
        elif poi is not None:
            p = next((p for p, _m, _o in self.lista_pois if p["id"] == poi.split("|")[1]), None)
            if p:
                lineas = [p["nombre"], "clic derecho = renombrar, cambiar ícono o borrar"]
        elif k is not None:
            r = self._mostrada(*k)
            if r is not None:
                lineas = [r.get("nota", ""), f"{_km(r.get('desde'))} → {_km(r.get('hasta'))}"]
                if k in self.corr:
                    lineas.append(f"(regla de {r.get('_compartida_de', '?')}, compartida)")
                extras = [f"{t.split(' (')[0]}: {r[c]}" for c, t in CAMPOS_NUM if c in r]
                if extras:
                    lineas.append(" · ".join(extras))
        else:
            m, d = self._metros_en(e.x, e.y)
            if m is not None and d <= 14:
                calle = self._calle_en(m)
                lineas = [f"{_km(m)}" + (f" · {calle}" if calle else "")]
                zona = self._zona_en(m)
                if zona:
                    lineas.append(zona)
                if self.camino and m > self.camino.get("comun_desde", 1e9):
                    lineas.append("zona de aparición: la distancia depende de dónde apareció el camión")
        if not lineas:
            return
        t = self.can.create_text(e.x + 14, e.y + 14, text="\n".join(lineas), anchor="nw", fill="#ffffff", width=340,
                                 font=("Segoe UI", 9), tags=("tip",))
        bb = self.can.bbox(t)
        if bb:
            f = self.can.create_rectangle(bb[0] - 4, bb[1] - 3, bb[2] + 4, bb[3] + 3, fill="#202225",
                                          outline="#5865f2", tags=("tip",))
            self.can.tag_raise(t, f)

    def _menu(self, e):
        menu = tk.Menu(self.win, tearoff=0)
        poi = self._item_en(e, "poi|")
        if poi is not None:
            pid = poi.split("|")[1]
            p = next((p for p, _m, _o in self.lista_pois if p["id"] == pid), None)
            if p:
                menu.add_command(label=f"«{p['nombre']}»", state="disabled")
                menu.add_command(label="Renombrar…", command=lambda: self._renombrar_poi(p))
                sub = tk.Menu(menu, tearoff=0)
                for k, (s, t) in pois.ICONOS.items():
                    sub.add_command(label=f"{s}  {t}", command=lambda k=k: self._icono_poi(p, k))
                menu.add_cascade(label="Ícono", menu=sub)
                menu.add_command(label="Borrar", command=lambda: self._borrar_poi(p))
        else:
            m, d = self._metros_en(e.x, e.y)
            if m is None or d > 20:
                return
            menu.add_command(label=f"{_km(m)}" + (f" · {self._calle_en(m)}" if self._calle_en(m) else ""),
                             state="disabled")
            menu.add_command(label="Agregar punto de interés aquí…", command=lambda: self._nuevo_poi(m))
            menu.add_command(label="Crear regla aquí (120 m)",
                             command=lambda: self._crear_regla(round(m + 60), round(max(0.0, m - 60))))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------ puntos de interés
    def _recorrido_poi(self):
        if self.var_tramo.get() == "0":
            return pois.CAMINO
        return pois.slug(self.recorridos.get(self.var_rec.get()))

    def _guardar_pois_antes(self):
        try:
            self.historial.append(("pois", copy.deepcopy(pois.cargar())))
            self.btn_deshacer.config(state="normal")
        except Exception:  # noqa
            pass

    def _nuevo_poi(self, metros):
        win = tk.Toplevel(self.win)
        win.title("Punto de interés")
        win.configure(bg=self.T["bg"])
        win.transient(self.win.winfo_toplevel())
        fr = ttk.Frame(win, padding=10)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=f"En {_km(metros)}" + (f" · {self._calle_en(metros)}" if self._calle_en(metros) else "")) \
            .grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(fr, text="Nombre:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        var_n = tk.StringVar()
        en = ttk.Entry(fr, textvariable=var_n, width=34)
        en.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(fr, text="Ícono:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        opciones = [f"{s}  {t}" for s, t in pois.ICONOS.values()]
        var_i = tk.StringVar(value=opciones[0])
        ttk.Combobox(fr, textvariable=var_i, values=opciones, state="readonly", width=31) \
            .grid(row=2, column=1, sticky="w", pady=(6, 0))
        comun = ""
        if self.var_tramo.get() == "0":
            comun = "Se guarda en el camino a cargar (vale para todos los recorridos)."
        elif any(lo - 40 <= metros <= hi + 40 for _o, lo, hi, _c in self.comp):
            comun = "Está en un tramo compartido: también se ve en el otro recorrido."
        if comun:
            ttk.Label(fr, text=comun, style="Tenue.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok():
            nombre = var_n.get().strip()
            if not nombre:
                return
            icono = list(pois.ICONOS)[opciones.index(var_i.get())]
            self._guardar_pois_antes()
            # en un tramo compartido se guarda en metros de ESTE recorrido; el otro lo ve corrido (pois.para_tramo)
            pois.agregar(self._recorrido_poi(), self.var_tramo.get(), metros, nombre, icono)
            print(f"[OK] Punto de interés agregado: {nombre} ({_km(metros)}).")
            win.destroy()
            self.recargar()

        bot = ttk.Frame(fr)
        bot.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(bot, text="Agregar", style="Acento.TButton", command=ok).pack(side="left")
        ttk.Button(bot, text="Cancelar", command=win.destroy).pack(side="left", padx=(6, 0))
        en.focus_set()
        en.bind("<Return>", lambda _e: ok())

    def _renombrar_poi(self, p):
        n = simpledialog.askstring("Punto de interés", "Nombre nuevo:", initialvalue=p.get("nombre", ""),
                                   parent=self.win)
        if n and n.strip():
            self._guardar_pois_antes()
            pois.editar(p["id"], nombre=n.strip())
            self.recargar()

    def _icono_poi(self, p, icono):
        self._guardar_pois_antes()
        pois.editar(p["id"], icono=icono)
        self.recargar()

    def _borrar_poi(self, p):
        if messagebox.askyesno("Punto de interés", f"¿Borrar «{p.get('nombre')}»?", parent=self.win):
            self._guardar_pois_antes()
            pois.borrar(p["id"])
            self.recargar()

    # ------------------------------------------------------------ buscador
    def buscar(self):
        q = self.var_buscar.get().strip()
        if not q or not self.puntos:
            return
        metros = None
        mt = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(km|m)?", q.lower())
        if mt:
            v = float(mt.group(1).replace(",", "."))
            metros = v * 1000 if (mt.group(2) == "km" or (mt.group(2) is None and v < 30)) else v
            que = _km(metros)
        else:
            n = _norm(q)
            cand = [(m, p["nombre"]) for p, m, _o in self.lista_pois if n in _norm(p.get("nombre"))]
            cand += [(m, c) for m, c in self.calles if n in _norm(c)]
            cand += [(m - 100, z) for m, z in self.zonas if n in _norm(z)]
            if not cand:
                self.lbl_pie.config(text=f"No encontré «{q}» en este tramo (busca una calle, zona, punto de interés o km).")
                return
            metros, que = cand[0]
        p = mapa.punto_en(self.puntos, metros)
        if p is None:
            return
        self.var_seguir.set(False)
        self.cx, self.cy = p[0], p[1]
        self.zoom = max(self.zoom, 0.6)
        self.marca = (p[0], p[1], time.time() + 3.0)
        self.dibujar()
        self.lbl_pie.config(text=f"→ {que} ({_km(metros)})")

    # ------------------------------------------------------------ viaje sobre el mapa
    def abrir_viaje(self):
        if self.viaje is not None:
            self.viaje = None
            self.btn_viaje.config(text="Abrir viaje…")
            self.dibujar()
            return
        ruta = filedialog.askopenfilename(parent=self.win, initialdir=carpetas.VIAJES, title="Viaje a mostrar",
                                          filetypes=(("Viajes", "viaje_*.csv"), ("CSV", "*.csv")))
        if not ruta:
            return
        try:
            self.viaje = mapa.viaje_sobre_mapa(ruta)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo leer el viaje:\n{e}", parent=self.win)
            return
        self.btn_viaje.config(text=f"Quitar viaje ({os.path.basename(ruta)[6:21]})")
        rec = self.viaje.get("recorrido")
        if rec in self.recorridos and rec != self.var_rec.get():
            self.var_rec.set(rec)
            self.recargar(ajustar=True)
        else:
            self.dibujar()
        n = len(self.viaje.get("eventos", []))
        self.lbl_pie.config(text=f"Viaje {os.path.basename(ruta)}: verde = en el límite, amarillo = +3 a +10 km/h, "
                                 f"rojo = pasado · {n} marca(s): ▲ naranjo = tomaste el control, rojo = choque o "
                                 "atasco, amarillo = fuera de la calle. Clic en una ▲ = crear una regla ahí.")

    def _regla_desde_evento(self, ev):
        m = float(ev["metros"])
        if self.var_tramo.get() != ev.get("tramo"):
            return
        self._crear_regla(round(m + 60), round(max(0.0, m - 60)), nota=f"{ev['texto'].splitlines()[0][:60]} (desde el viaje)")

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
            self.var[k].set("" if r.get("general") else str(round(float(r.get(k, 0)) + corr)))
        self.var["general"].set(bool(r.get("general")))
        for e in self.ent_dh:
            e.configure(state="disabled" if r.get("general") else "normal")
        self.var["modo"].set(r.get("modo") or "")
        for k, v in self.var_exp.items():
            x = (r.get("exp") or {}).get(k)
            v.set(EXP_OPC[0] if x is None else (EXP_OPC[1] if x else EXP_OPC[2]))
        self.var["nota"].set(str(r.get("nota", "")))
        for k, _t in CAMPOS_NUM:
            self.var[k].set("" if k not in r else str(r[k]).replace(".", ","))
        for k, _t in CAMPOS_BOOL:
            self.var[k].set(bool(r.get(k, False)))
        self.var["activa"].set(r.get("activa", True) is not False)
        act = self._tipos_de(r)
        for k, _t, _c, _b in TIPOS:
            self.var_tipo[k].set(k in act)
        self._lado_desde_var()
        self._avance_desde_var()
        self._armar_campos()
        self.btn_act.config(text="Activar" if r.get("activa", True) is False else "Desactivar")
        com = " (común a todos los recorridos)" if arch == "_comunes.json" else ""
        if (arch, clave, i) in self.corr:
            com = " · compartida: vale para los dos recorridos"
        elif self._en_compartido(r):
            com = " · compartida: también vale para el otro recorrido"
        self.ed.config(text=f" Editar regla · {arch}{com} ")
        rm = self._mostrada(arch, clave, i) or r
        if rm.get("general"):
            p, calle = None, "todo el tramo"
        else:
            p = pois.cerca_de(self.lista_pois, (float(rm.get("desde", 0)) + float(rm.get("hasta", 0))) / 2)
            calle = self._calle_en(float(rm.get("desde", 0)))
        self.lbl_cerca.config(text=" · ".join(x for x in ((f"cerca de: {p['nombre']}" if p else ""),
                                                           (calle or "")) if x))
        self.lbl_aviso.config(text=self._choques(rm, (arch, clave, i)))
        if not desde_lista:
            iid = f"{arch}|{clave}|{i}"
            if self.tv.exists(iid):
                self.tv.selection_set(iid)
                self.tv.see(iid)
        self.dibujar()

    def _choques(self, r, clave):
        """3.3.0: otras reglas activas que se pisan con esta y piden otra cosa."""
        if r.get("activa", True) is False:
            return ""
        if r.get("general"):
            return "Regla general: vale en todo este tramo; una regla de un lugar manda sobre ella en lo que pida."
        a1, b1 = float(r.get("hasta", 0)), float(r.get("desde", 0))
        avisos = []
        for o, arch, cl, i in self.items:
            if (arch, cl, i) == clave or o.get("activa", True) is False or o.get("general"):
                continue
            a2, b2 = float(o.get("hasta", 0)), float(o.get("desde", 0))
            if min(b1, b2) - max(a1, a2) < 5:
                continue
            que = []
            for k, txt in (("desplazamiento_px", "un lado distinto"), ("max_kmh", "otra velocidad máxima"),
                           ("esquina_kmh", "otra velocidad en esquinas"), ("giro_tardio_px", "otro giro en esquinas")):
                if k in r and k in o and float(r[k]) != float(o[k]):
                    que.append(txt)
            if que:
                avisos.append(f"⚠ Se pisa con «{o.get('nota', '')[:50]}» ({_km(b2)} → {_km(a2)}): "
                              f"piden {' y '.join(que)}. Se usa la más estricta o la primera.")
        return "\n".join(avisos[:3])

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
        try:                                             # 3.3.0: para deshacer
            with open(ruta, encoding="utf-8") as fh:
                self.historial.append((arch, fh.read()))
            self.historial = self.historial[-30:]
            self.btn_deshacer.config(state="normal")
        except Exception:  # noqa
            pass
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

    def deshacer(self):
        if not self.historial:
            return
        arch, previo = self.historial.pop()
        try:
            if arch == "pois":
                pois.guardar(previo)
                print("[OK] Deshecho el último cambio de puntos de interés.")
            else:
                ruta = os.path.join(carpetas.RUTAS, arch)
                tmp = ruta + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(previo)
                os.replace(tmp, ruta)
                print(f"[OK] Deshecho el último cambio en {arch}.")
                if self.app.ap is not None:
                    self.app.orden("recargar_rutas")
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo deshacer:\n{e}", parent=self.win)
        if not self.historial:
            self.btn_deshacer.config(state="disabled")
        self.sel = None
        self.recargar()

    def guardar_regla(self):
        if self.sel is None:
            messagebox.showinfo("Mapa de la ruta", "Elige una regla (en el mapa o en la lista).", parent=self.win)
            return
        arch, clave, i = self.sel
        r = self._regla(arch, clave, i)
        general = self.var["general"].get()
        try:
            desde, hasta = self._num("desde", True), self._num("hasta", True)
            if general:
                desde = hasta = None
            elif desde is None or hasta is None or desde <= hasta:
                raise ValueError("«Desde» tiene que ser mayor que «Hasta» (la distancia al punto va bajando).")
            nuevos = {k: self._num(k) for k, _t in CAMPOS_NUM}
        except ValueError as e:
            messagebox.showerror("Mapa de la ruta", f"Revisa los valores: {e}", parent=self.win)
            return
        if nuevos.get("desplazamiento_px") == 0 and not self.var_tipo["avanzado"].get():
            nuevos["desplazamiento_px"] = None            # lado en el centro = sin desplazamiento
        if nuevos.get("avance_esquina_px") == 0 and not self.var_tipo["avanzado"].get():
            nuevos["avance_esquina_px"] = None            # 3.5.0: avance normal = sin valor
        antes = json.dumps({k: v for k, v in r.items() if k != "origen"}, sort_keys=True)
        corr = self.corr.get((arch, clave, i), 0)
        if general:                                       # 3.5.0: todo el tramo
            r.pop("desde", None)
            r.pop("hasta", None)
            r["general"] = True
        else:
            r.pop("general", None)
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
        if general:
            r.pop("entregar_control", None)
        if self.var["modo"].get():
            r["modo"] = self.var["modo"].get()
        else:
            r.pop("modo", None)
        exp = {k: v.get() == EXP_OPC[1] for k, v in self.var_exp.items() if v.get() != EXP_OPC[0]}
        if exp:
            r["exp"] = exp
        else:
            r.pop("exp", None)
        if self.var["activa"].get():
            r.pop("activa", None)
        else:
            r["activa"] = False
        if json.dumps({k: v for k, v in r.items() if k != "origen"}, sort_keys=True) != antes:
            r.pop("origen", None)                 # 3.4.2: ya tiene cambios -> deja de verse en verde
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
        if not messagebox.askyesno("Borrar regla", f"¿Borrar «{r.get('nota', '')}»?\n\nSe puede deshacer, y se "
                                   f"guarda una copia del archivo en mi_equipo/respaldos/rutas/.{com}", parent=self.win):
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
            self.modo = "nueva"
            self.sel = None
            self.dibujar()
        else:
            ap = self.app.ap
            d = None
            try:
                d = ap.dist_fina() if ap is not None else None
            except Exception:  # noqa
                pass
            centro = round(d) if d else 1000
            self._crear_regla(centro + 40, max(0, centro - 40))

    def _crear_regla(self, desde, hasta, nota=None):
        tramo = self.var_tramo.get()
        if tramo == "0" and self.camino and desde > self.camino.get("comun_desde", 1e9) + 5:
            if not messagebox.askyesno(
                    "Zona de aparición",
                    f"La regla empieza en {_km(desde)}, antes de que el camión llegue a la calle común "
                    f"({_km(self.camino['comun_desde'])}).\n\nAhí la distancia depende de dónde apareció el camión, "
                    "así que la regla puede caer en otro lugar. ¿Crearla igual?", parent=self.win):
                return
        rec = self.var_rec.get()
        arch = self.recorridos.get(rec)
        clave = tramo
        if tramo == "0" or arch is None:
            arch, clave = "_comunes.json", "inicio_comun" if tramo == "0" else "regreso_comun"
        if arch not in self.archivos:
            self._leer(arch)
        lista = self._lista(arch, clave)
        nueva = {"desde": int(desde), "hasta": int(hasta), "nota": nota or NUEVA_NOTA}
        lista.append(nueva)
        lista.sort(key=lambda r: -float(r.get("desde", 0)))
        i = next(n for n, r in enumerate(lista) if r is nueva)
        try:
            self._escribir(arch)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo guardar:\n{e}", parent=self.win)
            return
        self.recargar()
        self.seleccionar(arch, clave, i)
        self.lbl_pie.config(text="Regla creada: elige qué quieres que haga (a la derecha) y aprieta Guardar. "
                                 "Arrastra sus extremos para ajustarla.")

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

    def ir_a(self, rec=None, tramo=None):
        """3.4.0: mostrar ese recorrido (nombre o archivo sin .json) y tramo, ajustado a la vista."""
        if rec:
            nombre = rec if rec in self.recorridos else next(
                (n for n, a in self.recorridos.items() if a and os.path.splitext(a)[0] == rec), None)
            if nombre:
                self.var_rec.set(nombre)
        if tramo in ("0", "1", "2"):
            self.var_tramo.set(tramo)
        self.recargar(ajustar=True)

    def cerrar(self):
        if self.embebida:
            return
        try:
            self.app.prefs.setdefault("geometria", {})["ventana_mapa"] = self.win.geometry()
            self.app.guardar_prefs()
        except Exception:  # noqa
            pass
        self.win.destroy()
        if getattr(self.app, "ventana_mapa", None) is self:
            self.app.ventana_mapa = None


def abrir(app):
    if hasattr(app, "ir_a_mapa"):                    # 3.4.0: es una pestaña de la ventana principal
        app.ir_a_mapa()
        return getattr(app, "ventana_mapa", None)
    v = getattr(app, "ventana_mapa", None)
    try:
        if v is not None and v.win.winfo_exists():
            v.win.lift()
            return v
    except Exception:  # noqa
        pass
    app.ventana_mapa = VentanaMapa(app)
    return app.ventana_mapa

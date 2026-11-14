"""
Interfaz gráfica del autopiloto de camión (2.0.0).

    Doble clic en  Autopiloto.bat   (o, desde la carpeta programa:  python interfaz.py)

- Barra de estado, tarjetas (velocidad, distancia, condición, motivo) y registro con colores.
- Pestañas: Conducir, Grabaciones, Viajes, Calibración y Ajustes.
- Tema oscuro o claro; vista completa, compacta o mini; minimapa y cámara desacoplables.
- Notificaciones en pantalla encima del juego (no le quitan el foco).
- Ayuda al pasar el mouse por cada control.
Las teclas del juego (INSERT, RE PÁG, SUPR...) siguen funcionando mientras juegas.
"""
import datetime
import time
import json
import os
import queue
import shutil
import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carpetas                                      # noqa: E402

MOVIDOS = carpetas.preparar()                        # entra en la carpeta Autopiloto/ y ordena archivos viejos

import tkinter as tk                                 # noqa: E402
from tkinter import ttk, filedialog, messagebox, simpledialog   # noqa: E402

import cv2                                           # noqa: E402
from PIL import Image, ImageTk                       # noqa: E402

import configuracion                                 # noqa: E402
import notificador                                   # noqa: E402
import version                                       # noqa: E402
import ventanas_extra                                # noqa: E402
import panel                                         # noqa: E402
import ventana_actualizar                            # noqa: E402
import entrada                                       # noqa: E402

CONFIG = carpetas.CONFIG


def _km(m):
    """'1,70 km' desde 1 km, '740 m' por debajo (como el minimapa)."""
    if m is None:
        return "-"
    return f"{float(m) / 1000:.2f} km".replace(".", ",") if float(m) >= 1000 else f"{float(m):.0f} m"


ESTADOS = {  # estado interno -> (texto, color)
    "INACTIVO": ("Inactivo", "#6d6f78"), "ARRANCANDO": ("Arrancando", "#3ba55d"),
    "CONDUCIENDO": ("Conduciendo", "#23a55a"), "RECUPERANDO": ("Maniobrando", "#e08a1e"),
    "ESPERANDO_RUTA": ("Esperando al juego", "#2f7fd1"), "TERMINADO": ("Terminado", "#8e5cc4"),
    "GRABANDO": ("Grabando", "#da373c"), "REPRODUCIENDO": ("Repitiendo grabación", "#16a085"),
    "DETENIDO": ("Detenido", "#4e5058"), "TAREA": ("Calibrando / probando", "#16a085"),
}
AUTO_RECORRIDO = "Automático"
TRAMOS = ["0 - Ir a cargar", "1 - Ir al punto de entrega (A)", "2 - Volver a la zona de trabajo (B)"]

TEMAS = {
    "oscuro": {"bg": "#1e1f22", "panel": "#2b2d31", "panel2": "#383a40", "borde": "#3f4147",
               "texto": "#f2f3f5", "texto2": "#b5bac1", "tenue": "#80848e", "acento": "#5865f2",
               "acento_on": "#ffffff", "campo": "#1e1f22", "sel": "#404249", "log_bg": "#111214",
               "log_fg": "#dbdee1", "vista_bg": "#111214", "morado": "#c9a6ff",
               "error": "#ff6b6b", "aviso": "#f0b232", "info": "#6fc3ff", "ok": "#57d982", "cambio": "#c9a6ff",
               "verde": "#23a55a", "rojo": "#da373c", "azul": "#5865f2", "naranja": "#e08a1e",
               "regla_bg": "#4a3b10", "regla_fg": "#f0c674"},
    "claro": {"bg": "#f2f3f5", "panel": "#ffffff", "panel2": "#e3e5e8", "borde": "#d4d7dc",
              "texto": "#1e1f22", "texto2": "#4e5058", "tenue": "#80848e", "acento": "#4752c4",
              "acento_on": "#ffffff", "campo": "#ffffff", "sel": "#d4d7dc", "log_bg": "#ffffff",
              "log_fg": "#2e3338", "vista_bg": "#202225", "morado": "#7b3fbf",
              "error": "#c62828", "aviso": "#9a6700", "info": "#1565c0", "ok": "#2e7d32", "cambio": "#6a1b9a",
              "verde": "#2e9e44", "rojo": "#c83a3a", "azul": "#4752c4", "naranja": "#c46f0a",
              "regla_bg": "#fdf0c8", "regla_fg": "#7a5a00"},
}

PREFS_DEFECTO = {
    "sesion": {"tramo": 0, "recorrido": ""},   # 3.2.6: etapa y recorrido donde quedó el programa al detenerse
    "tema": "oscuro",
    "vista": "completa",                 # completa, compacta, mini
    "ayuda": True,                       # mensajes al pasar el mouse
    "separadas": {"minimapa": False, "carril": False},
    "geometria": {"completa": "1280x940", "compacta": "860x840", "mini": "640x560"},
    "notificaciones": dict(notificador.DEFECTO),
    "tutorial_visto": False,             # 2.2.0: el tutorial se abre solo la primera vez
    "panel": {"modo": "auto", "opacidad": 0.8},                       # 3.1.0: panel flotante (una sola pantalla)
    "actualizaciones": {"revisar": True, "ignorar": ""},              # 3.1.0: buscar versiones nuevas al abrir
}


# ---------------------------------------------------------------- registro
class Redireccion:
    """Envía print() al registro de la ventana y a mi_equipo/registro.txt."""

    def __init__(self, cola, archivo):
        self.cola, self.archivo = cola, archivo

    def write(self, texto):
        if not texto:
            return
        texto = texto.replace("\r", "")
        if not texto:
            return
        self.cola.put(texto)
        try:
            self.archivo.write(texto)
            self.archivo.flush()
        except Exception:
            pass

    def flush(self):
        pass


class Puente:
    """El autopiloto (en su hilo) deja aquí su estado, imágenes y avisos; la ventana los recoge."""

    def __init__(self):
        self.lock = threading.Lock()
        self._estado = None
        self._imgs = None
        self.pedidos = queue.Queue()       # observaciones / guardar grabación
        self.avisos = queue.Queue()        # notificaciones en pantalla

    def estado(self, d):
        with self.lock:
            self._estado = d

    def imagenes(self, d):
        with self.lock:
            self._imgs = d

    def tomar(self):
        with self.lock:
            e, i = self._estado, self._imgs
            self._imgs = None
        return e, i

    def pedir_observaciones(self, datos):
        self.pedidos.put(datos)

    def pedir_guardar_grabacion(self, datos):
        self.pedidos.put(dict(datos, _tipo="grabacion"))

    def notificar(self, tipo, titulo, texto=""):
        self.avisos.put((tipo, titulo, texto))


class Ayuda:
    """Mensaje que aparece al dejar el mouse sobre un control."""

    def __init__(self, app, widget, texto):
        self.app, self.widget, self.texto = app, widget, texto
        self.win = None
        self.id = None
        widget.bind("<Enter>", self._entrar, add="+")
        widget.bind("<Leave>", self._salir, add="+")
        widget.bind("<ButtonPress>", self._salir, add="+")

    def _entrar(self, _e=None):
        if not self.app.prefs.get("ayuda", True):
            return
        self.id = self.widget.after(550, self._mostrar)

    def _mostrar(self):
        if self.win is not None:
            return
        T = self.app.T
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.win = tk.Toplevel(self.widget)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        tk.Label(self.win, text=self.texto, justify="left", wraplength=320, bg=T["panel2"], fg=T["texto"],
                 relief="solid", borderwidth=1, padx=8, pady=5, font=("Segoe UI", 9)).pack()
        self.win.geometry(f"+{x}+{y}")

    def _salir(self, _e=None):
        if self.id:
            try:
                self.widget.after_cancel(self.id)
            except Exception:  # noqa
                pass
            self.id = None
        if self.win is not None:
            self.win.destroy()
            self.win = None


# ---------------------------------------------------------------- ventana
OBS_RAPIDAS = (                                   # 2.5.4: selecciones rápidas en las observaciones
    ("que", "Qué pasó:", ("tocó barrera o muro", "tocó poste, farol o cartel", "tocó otro vehículo",
                          "giró antes de tiempo", "giró tarde", "se abrió en la curva", "se pegó a un lado",
                          "muy lento", "muy rápido", "se salió de la calle", "otro"), 24),
    ("lado", "Lado:", ("izquierda", "derecha", "los dos"), 10),
    ("causa", "Causa:", ("autopiloto", "tráfico u otro jugador", "lo hice yo", "no sé"), 20),
)


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"Autopiloto de camión {version.VERSION}")
        root.minsize(560, 380)
        self.cola_log = queue.Queue()
        self.puente = Puente()
        self.ap = None                    # Autopiloto en marcha
        self.hilo = None
        self.hilo_tarea = None            # calibración / prueba
        self.parar_prueba = threading.Event()
        self.evento_continuar = threading.Event()
        self.esperando_continuar = False
        self.fotos = {}
        self._tk = []                     # widgets tk (no ttk) con colores del tema
        self.ventanas = {}                # vistas separadas: "minimapa"/"carril" -> (Toplevel, Label)

        carpetas.limpiar_capturas()       # 2.2.0: restos de un cierre forzado
        usuario_nuevo = not os.path.exists(carpetas.INTERFAZ) and not os.path.exists(CONFIG)
        self.prefs = self._cargar_prefs()
        if not usuario_nuevo and not self.prefs.get("tutorial_visto"):
            self.prefs["tutorial_visto"] = True        # ya usaba el programa: no mostrar el tutorial solo
        elif usuario_nuevo:
            self.guardar_prefs()                       # así el tutorial vuelve a salir si se cierra a la fuerza
        self.T = TEMAS.get(self.prefs["tema"], TEMAS["oscuro"])

        self.archivo_log = open(carpetas.REGISTRO, "a", encoding="utf-8")
        sys.stdout = Redireccion(self.cola_log, self.archivo_log)
        sys.stderr = sys.stdout

        self.est = ttk.Style()
        try:
            self.est.theme_use("clam")
        except tk.TclError:
            pass
        self.panel = panel.PanelFlotante(root, self.prefs["panel"], self._titulo_juego())
        self._estado_ult = None
        self._tecla_panel = False
        self._t_panel = 0.0
        self._construir()
        self._restaurar_sesion()
        self.aplicar_tema(self.prefs["tema"], guardar=False)
        self.notif = notificador.Notificador(root, self.prefs["notificaciones"], self._titulo_juego())
        self.poner_vista(self.prefs["vista"], guardar=False)
        for nombre in ("minimapa", "carril"):
            if self.prefs["separadas"].get(nombre):
                self.separar(nombre)
        self._cargar_teclas()
        print(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  Autopiloto {version.VERSION} =====")
        if MOVIDOS:
            print("[i] Ordené tus archivos en las carpetas nuevas (nada se borró):")
            for m in MOVIDOS:
                print(f"     {m}")
        self._comprobar_datos()
        self._comprobar_config()
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        if not self.prefs.get("tutorial_visto"):
            root.after(500, lambda: ventanas_extra.ventana_tutorial(self))
        if self.prefs["actualizaciones"].get("revisar", True):
            root.after(2500, lambda: ventana_actualizar.revisar(self, manual=False))
        self._bucle()

    # ------------------------------------------------------------ preferencias de la interfaz
    def _cargar_prefs(self):
        p = json.loads(json.dumps(PREFS_DEFECTO))
        g = carpetas.leer_json(carpetas.INTERFAZ, {})
        for k, v in g.items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
        n = dict(notificador.DEFECTO)
        n.update(p["notificaciones"])
        n["tipos"] = dict(notificador.DEFECTO["tipos"], **p["notificaciones"].get("tipos", {}))
        p["notificaciones"] = n
        return p

    def _restaurar_sesion(self):
        """3.2.6: «Empezar en» y «Recorrido» vuelven a donde quedaron al detener o cerrar el programa."""
        ses = self.prefs.get("sesion") or {}
        t = ses.get("tramo", 0)
        if isinstance(t, int) and 0 <= t < len(TRAMOS):
            self.var_tramo.set(TRAMOS[t])
        arch = ses.get("recorrido") or ""
        nombre = next((n for n, a in self.recorridos if a == arch), None) if arch else None
        self.var_recorrido.set(nombre or AUTO_RECORRIDO)
        if t or nombre:
            print(f"[i] Sigo donde quedé: {TRAMOS[t] if 0 <= t < len(TRAMOS) else t}"
                  + (f", recorrido {nombre}" if nombre else "") + ".")

    def _guardar_sesion(self, e):
        t = e.get("tramo")
        if not isinstance(t, int) or not 0 <= t < len(TRAMOS):
            return
        if self.var_tramo.get() != TRAMOS[t]:
            self.var_tramo.set(TRAMOS[t])            # 3.2.6: «Empezar en» sigue la etapa (al terminar vuelve a 0)
        ses = {"tramo": t, "recorrido": (e.get("recorrido_archivo") or "") if t in (1, 2) else ""}
        if ses != self.prefs.get("sesion"):
            self.prefs["sesion"] = ses
            self.guardar_prefs()

    def guardar_prefs(self):
        try:
            carpetas.guardar_json(carpetas.INTERFAZ, self.prefs)
        except Exception as e:  # noqa
            print(f"[!] No se pudieron guardar las preferencias: {e}")

    def _titulo_juego(self):
        try:
            return carpetas.leer_json(CONFIG).get("ventana_juego") or configuracion.DEFAULTS.get("ventana_juego")
        except Exception:  # noqa
            return "Grand Theft Auto"

    def notificar(self, tipo, titulo, texto=""):
        """Aviso en pantalla (desde el hilo de la ventana)."""
        try:
            self.notif.mostrar(tipo, titulo, texto)
        except Exception as e:  # noqa
            print(f"[!] Notificación: {e}")

    # ------------------------------------------------------------ tema
    def _tkw(self, w, **roles):
        """Registra un widget tk con sus colores del tema (bg='panel', fg='texto'...)."""
        self._tk.append((w, roles))
        self._pintar(w, roles)
        return w

    def _pintar(self, w, roles):
        try:
            w.configure(**{k: self.T[v] for k, v in roles.items()})
        except Exception:  # noqa
            pass

    def aplicar_tema(self, nombre, guardar=True):
        self.prefs["tema"] = nombre if nombre in TEMAS else "oscuro"
        T = self.T = TEMAS[self.prefs["tema"]]
        st = self.est
        fuente = ("Segoe UI", 10)
        st.configure(".", background=T["bg"], foreground=T["texto"], fieldbackground=T["campo"],
                     bordercolor=T["borde"], lightcolor=T["panel"], darkcolor=T["panel"], troughcolor=T["bg"],
                     focuscolor=T["acento"], selectbackground=T["sel"], selectforeground=T["texto"],
                     insertcolor=T["texto"], arrowcolor=T["texto2"], font=fuente)
        st.configure("TFrame", background=T["bg"])
        st.configure("Panel.TFrame", background=T["panel"])
        st.configure("TLabel", background=T["bg"], foreground=T["texto"])
        st.configure("Panel.TLabel", background=T["panel"], foreground=T["texto"])
        st.configure("Tenue.TLabel", background=T["panel"], foreground=T["texto2"], font=("Segoe UI", 9))
        st.configure("Titulo.TLabel", background=T["panel"], foreground=T["texto"], font=("Segoe UI", 10, "bold"))
        st.configure("Mono.TLabel", background=T["panel"], foreground=T["texto2"], font=("Consolas", 9))
        st.configure("TButton", background=T["panel2"], foreground=T["texto"], bordercolor=T["borde"],
                     lightcolor=T["panel2"], darkcolor=T["panel2"], padding=(10, 6), focusthickness=0)
        st.map("TButton", background=[("disabled", T["panel"]), ("pressed", T["sel"]), ("active", T["sel"])],
               foreground=[("disabled", T["tenue"])])
        st.configure("Grande.TButton", font=("Segoe UI", 11, "bold"), padding=(12, 8))
        st.configure("Acento.TButton", background=T["acento"], foreground=T["acento_on"], lightcolor=T["acento"],
                     darkcolor=T["acento"], font=("Segoe UI", 11, "bold"), padding=(12, 8))
        st.map("Acento.TButton", background=[("disabled", T["panel2"]), ("active", T["azul"])],
               foreground=[("disabled", T["tenue"])])
        st.configure("Seg.TButton", padding=(8, 3), font=("Segoe UI", 9))
        st.configure("SegOn.TButton", padding=(8, 3), font=("Segoe UI", 9, "bold"), background=T["acento"],
                     foreground=T["acento_on"], lightcolor=T["acento"], darkcolor=T["acento"])
        st.map("SegOn.TButton", background=[("active", T["acento"])])
        for c in ("TCheckbutton", "TRadiobutton"):
            st.configure(c, background=T["panel"], foreground=T["texto"], indicatorbackground=T["campo"],
                         indicatorforeground=T["texto"], focuscolor=T["panel"])
            st.map(c, background=[("active", T["panel"])], indicatorbackground=[("selected", T["acento"])])
        st.configure("TEntry", fieldbackground=T["campo"], foreground=T["texto"], bordercolor=T["borde"],
                     lightcolor=T["borde"], darkcolor=T["borde"], padding=4)
        for c in ("TCombobox", "TSpinbox"):
            st.configure(c, fieldbackground=T["campo"], foreground=T["texto"], background=T["panel2"],
                         bordercolor=T["borde"], lightcolor=T["borde"], darkcolor=T["borde"], arrowcolor=T["texto2"],
                         padding=3)
            st.map(c, fieldbackground=[("readonly", T["campo"])], foreground=[("readonly", T["texto"])],
                   selectbackground=[("readonly", T["campo"])], selectforeground=[("readonly", T["texto"])])
        self.root.option_add("*TCombobox*Listbox.background", T["campo"])
        self.root.option_add("*TCombobox*Listbox.foreground", T["texto"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", T["acento"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", T["acento_on"])
        st.configure("TNotebook", background=T["bg"], bordercolor=T["borde"], tabmargins=(0, 4, 0, 0))
        st.configure("TNotebook.Tab", background=T["bg"], foreground=T["texto2"], padding=(14, 6),
                     bordercolor=T["borde"], lightcolor=T["bg"], darkcolor=T["bg"])
        st.map("TNotebook.Tab", background=[("selected", T["panel"])], foreground=[("selected", T["texto"])],
               lightcolor=[("selected", T["panel"])])
        st.configure("TLabelframe", background=T["panel"], bordercolor=T["borde"], lightcolor=T["panel"],
                     darkcolor=T["panel"], padding=8)
        st.configure("TLabelframe.Label", background=T["panel"], foreground=T["texto2"],
                     font=("Segoe UI", 9, "bold"))
        st.configure("Treeview", background=T["campo"], fieldbackground=T["campo"], foreground=T["texto"],
                     bordercolor=T["borde"], rowheight=24)
        st.map("Treeview", background=[("selected", T["acento"])], foreground=[("selected", T["acento_on"])])
        st.configure("Treeview.Heading", background=T["panel2"], foreground=T["texto2"], bordercolor=T["borde"],
                     lightcolor=T["panel2"], darkcolor=T["panel2"], font=("Segoe UI", 9, "bold"))
        st.map("Treeview.Heading", background=[("active", T["sel"])])
        st.configure("Vertical.TScrollbar", background=T["panel2"], troughcolor=T["bg"], bordercolor=T["bg"],
                     arrowcolor=T["texto2"], lightcolor=T["panel2"], darkcolor=T["panel2"])
        st.configure("Horizontal.TScale", background=T["panel"], troughcolor=T["campo"])
        self.root.configure(bg=T["bg"])
        for w, roles in list(self._tk):
            self._pintar(w, roles)
        if hasattr(self, "txt_log"):
            for tag in ("error", "aviso", "info", "ok", "cambio"):
                self.txt_log.tag_configure(tag, foreground=T[tag])
        for nombre, (win, _lbl) in self.ventanas.items():
            win.configure(bg=T["bg"])
        self._pintar_barras(0.0, 0.0, 0.0)
        if guardar:
            self.guardar_prefs()

    # ------------------------------------------------------------ construcción
    def _ayuda(self, w, texto):
        Ayuda(self, w, texto)
        return w

    def _tarjeta(self, padre, titulo, ayuda):
        f = self._tkw(tk.Frame(padre, padx=12, pady=8), bg="panel")
        self._tkw(tk.Label(f, text=titulo, font=("Segoe UI", 9), anchor="w"), bg="panel", fg="texto2").pack(fill="x")
        v = self._tkw(tk.Label(f, text="-", font=("Segoe UI", 20, "bold"), anchor="w"), bg="panel", fg="texto")
        v.pack(fill="x")
        self._ayuda(f, ayuda)
        return f, v

    def _construir(self):
        self.cont = ttk.Frame(self.root, padding=8)
        self.cont.pack(fill="both", expand=True)

        # ---------------- barra de estado
        cab = self.f_cab = self._tkw(tk.Frame(self.cont, padx=10, pady=7), bg="panel")
        cab.pack(fill="x")
        self.lbl_estado = tk.Label(cab, text="Detenido", font=("Segoe UI", 11, "bold"), fg="white",
                                   bg=ESTADOS["DETENIDO"][1], padx=10, pady=2)
        self.lbl_estado.pack(side="left")
        self._ayuda(self.lbl_estado, "Estado del autopiloto. Verde: conduciendo. Gris: inactivo (manejas tú). "
                                     "Rojo: grabando. Azul: esperando al juego (menú o barra).")
        self.lbl_recorrido = self._tkw(tk.Label(cab, text="Sin recorrido", font=("Segoe UI", 11, "bold"), padx=10),
                                       bg="panel", fg="texto")
        self.lbl_recorrido.pack(side="left")
        self._ayuda(self.lbl_recorrido, "Cargamento y recorrido reconocidos al cargar (p. ej. Drogas - Granja 1).")
        self.lbl_etapa = self._tkw(tk.Label(cab, text="", font=("Segoe UI", 10)), bg="panel", fg="texto2")
        self.lbl_etapa.pack(side="left")
        seg = self._tkw(tk.Frame(cab), bg="panel")
        seg.pack(side="right")
        self.btn_vista = {}
        for clave, txt, ayuda in (("completa", "Completa", "Todo: controles, minimapa y cámara."),
                                  ("compacta", "Compacta", "Sin las vistas de minimapa y cámara (salvo las "
                                                           "que tengas en ventana aparte)."),
                                  ("mini", "Mini", "Solo estado, tarjetas, botones básicos y registro.")):
            b = ttk.Button(seg, text=txt, style="Seg.TButton", command=lambda c=clave: self.poner_vista(c))
            b.pack(side="left", padx=1)
            self._ayuda(b, "Vista " + txt.lower() + ": " + ayuda)
            self.btn_vista[clave] = b
        self.btn_nueva = ttk.Button(cab, text="", style="Acento.TButton",
                                    command=lambda: ventana_actualizar.mostrar_ultima(self))     # 3.1.0
        self._ayuda(self.btn_nueva, "Hay una versión nueva del programa. Clic para ver qué cambia y actualizar.")
        self.lbl_control = self._tkw(tk.Label(cab, text="", font=("Segoe UI", 9), padx=8), bg="panel", fg="texto2")
        self.lbl_control.pack(side="right")
        self._ayuda(self.lbl_control, "Cómo maneja el programa: mando virtual o teclado.")
        self.lbl_usuario = self._tkw(tk.Label(cab, text="", font=("Segoe UI", 9), padx=8), bg="panel", fg="texto2")
        self.lbl_usuario.pack(side="right")
        self._ayuda(self.lbl_usuario, "Usuario que se anota en cada viaje. Se cambia en Ajustes.")

        # ---------------- tarjetas
        tar = self.f_tarjetas = ttk.Frame(self.cont)
        tar.pack(fill="x", pady=(8, 0))
        f, self.v_vel = self._tarjeta(tar, "Velocidad / objetivo",
                                      "Velocidad del velocímetro y la velocidad a la que quiere ir el autopiloto.")
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        f, self.v_dist = self._tarjeta(tar, "Al punto", "Distancia al punto según el minimapa del juego.")
        f.grid(row=0, column=1, sticky="nsew", padx=4)
        f, self.v_cond = self._tarjeta(tar, "Condición", "Condición del camión (icono del motor del HUD).")
        f.grid(row=0, column=2, sticky="nsew", padx=4)
        f, self.v_motivo = self._tarjeta(tar, "Motivo", "Por qué va a esa velocidad: recta, curva, esquina, "
                                                         "regla del lugar, destino...")
        self.v_motivo.configure(font=("Segoe UI", 13, "bold"))
        f.grid(row=0, column=3, sticky="nsew", padx=(4, 0))
        for i in range(4):
            tar.columnconfigure(i, weight=1, uniform="t")

        # ---------------- lugar y regla
        lug = self.f_lugar = self._tkw(tk.Frame(self.cont, padx=10, pady=6), bg="panel")
        lug.pack(fill="x", pady=(8, 0))
        self.lbl_lugar = self._tkw(tk.Label(lug, text="Lugar: -", font=("Segoe UI", 10), anchor="w"),
                                   bg="panel", fg="texto")
        self.lbl_lugar.pack(side="left")
        self._ayuda(self.lbl_lugar, "Zona y calle leídas del HUD del juego.")
        self.lbl_regla = self._tkw(tk.Label(lug, text="", font=("Segoe UI", 9, "bold"), padx=8, pady=1),
                                   bg="regla_bg", fg="regla_fg")
        self.lbl_regla.pack(side="right")
        self._ayuda(self.lbl_regla, "Regla del lugar activa ahora (datos/rutas): velocidad máxima, ir más a un "
                                    "lado, esquinas, etc.")
        self.lbl_pantalla = self._tkw(tk.Label(lug, text="", font=("Segoe UI", 9, "bold"), padx=8),
                                      bg="panel", fg="morado")
        self.lbl_pantalla.pack(side="right")

        # ---------------- avisos de problemas de base (3.1.0): solo se ven cuando hay alguno
        self.f_avisos = self._tkw(tk.Frame(self.cont, padx=10, pady=4), bg="regla_bg")
        self._avisos_claves = None

        # ---------------- botones de uso diario (3.1.0): siempre a la vista
        self._barra_diaria()

        # ---------------- pestañas
        nb = self.nb = ttk.Notebook(self.cont)
        nb.pack(fill="both", expand=True, pady=(8, 0))
        self._pestana_conducir()
        self._pestana_grabaciones()
        self._pestana_viajes()
        self._pestana_calibracion()
        self._pestana_ajustes()
        self._pestana_experimental()
        nb.bind("<<NotebookTabChanged>>", self._cambio_pestana)
        try:
            self.root.after(1500, self.cargar_lista_viajes)    # 2.7.0: «último viaje» al abrir
        except Exception:  # noqa
            pass

        # ---------------- registro
        reg = self.f_reg = self._tkw(tk.Frame(self.cont, padx=6, pady=6), bg="panel")
        reg.pack(fill="both", expand=False, pady=(8, 0))
        barra = self._tkw(tk.Frame(reg), bg="panel")
        barra.pack(fill="x")
        self._tkw(tk.Label(barra, text="Registro", font=("Segoe UI", 9, "bold")), bg="panel", fg="texto2").pack(
            side="left")
        b = ttk.Button(barra, text="Limpiar", style="Seg.TButton", command=lambda: self.txt_log.delete("1.0", "end"))
        b.pack(side="right")
        self._ayuda(b, "Borra el registro de la ventana (el archivo mi_equipo/registro.txt se mantiene).")
        b = ttk.Button(barra, text="Copiar todo", style="Seg.TButton", command=self.copiar_log)
        b.pack(side="right", padx=4)
        self._ayuda(b, "Copia todo el registro al portapapeles.")
        cuerpo = self._tkw(tk.Frame(reg), bg="panel")
        cuerpo.pack(fill="both", expand=True, pady=(4, 0))
        self.txt_log = self._tkw(tk.Text(cuerpo, height=9, font=("Consolas", 10), wrap="word", relief="flat",
                                         borderwidth=0, padx=6, pady=4),
                                 bg="log_bg", fg="log_fg", insertbackground="texto")
        sb = ttk.Scrollbar(cuerpo, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(fill="both", expand=True)

    def _seccion(self, padre, titulo):
        return ttk.LabelFrame(padre, text=f" {titulo} ")

    def _barra_diaria(self):
        """Los botones de todos los días, siempre visibles (en cualquier vista): iniciar, detener, activar,
        saltar etapa, ayuda de carril, grabar y marcar hito; y debajo la etapa de partida y las opciones."""
        f = self.f_diario = ttk.Frame(self.cont)
        fila = ttk.Frame(f)
        fila.pack(fill="x")
        defs = (
            ("btn_iniciar", "▶  Iniciar", "Acento.TButton", self.iniciar_programa,
             "Empieza a leer la pantalla del juego. Después activa el autopiloto con INSERT (o el botón Activar)."),
            ("btn_detener", "■  Detener", "TButton", self.detener,
             "Detiene el programa y guarda el viaje. Pregunta si quieres hacer observaciones."),
            ("btn_activar", "Activar / desactivar", "Grande.TButton", lambda: self.orden("activar"),
             "Activa o desactiva el autopiloto. En el juego: INSERT. Para tomar el control al instante: S o ESPACIO."),
            ("btn_saltar", "Saltar etapa", "TButton", lambda: self.orden("saltar"),
             "Pasa a la siguiente etapa del trabajo (AV PÁG). Úsalo si el programa se desfasó, por ejemplo si lo "
             "activaste con el camión ya cargado."),
            ("btn_carril", "Ayuda de carril", "TButton", lambda: self.orden("carril"),
             "Usa también la cámara para mantenerse en el carril (SUPR)."),
            ("btn_grabar", "●  Grabar", "TButton", lambda: self.orden("grabar"),
             "Graba cómo conduces tú un tramo para que el programa lo repita (entrada a granjas, salidas, punto "
             "final)."),
            ("btn_hito", "⚑  Hito", "TButton", lambda: self.orden("hito"),
             "Marca este momento (por ejemplo, «va muy lento aquí») con 3 capturas, para explicarlo en las "
             "observaciones al terminar. En el juego: F9."))
        self.btns_ap = []
        for i, (attr, txt, estilo, cmd, ayuda) in enumerate(defs):
            b = ttk.Button(fila, text=txt, style=estilo, command=cmd)
            b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0))
            fila.columnconfigure(i, weight=1, uniform="bd")
            self._ayuda(b, ayuda)
            setattr(self, attr, b)
            if attr not in ("btn_iniciar", "btn_detener"):
                self.btns_ap.append(b)
        opc = self.f_diario_opc = ttk.Frame(f)
        opc.pack(fill="x", pady=(5, 0))
        ttk.Label(opc, text="Empezar en:").pack(side="left")
        self.var_tramo = tk.StringVar(value=TRAMOS[0])
        cb = ttk.Combobox(opc, textvariable=self.var_tramo, values=TRAMOS, state="readonly", width=34)
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", self.cambiar_tramo)
        self._ayuda(cb, "En qué etapa del trabajo estás. Normalmente se detecta sola; cámbiala si se desincroniza "
                        "(p. ej. si cancelaste un trabajo).")
        # 3.2.5: recorrido elegido a mano (si se activa a mitad de camino no se puede reconocer por la distancia)
        ttk.Label(opc, text="Recorrido:").pack(side="left")
        self.recorridos = self._lista_recorridos()
        self.var_recorrido = tk.StringVar(value=AUTO_RECORRIDO)
        cb = self.cb_recorrido = ttk.Combobox(opc, textvariable=self.var_recorrido, state="readonly", width=24,
                                              values=[AUTO_RECORRIDO] + [n for n, _a in self.recorridos])
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", self.cambiar_recorrido)
        self._ayuda(cb, "Qué recorrido es. «Automático»: se reconoce por la distancia justo después de cargar. Si "
                        "activas a mitad de camino, elígelo aquí para que use sus reglas en la ida y la vuelta. "
                        "Al terminar el trabajo vuelve solo a «Automático».")
        self.var_debug = tk.BooleanVar(value=True)
        self.var_csv = tk.BooleanVar(value=True)
        c = ttk.Checkbutton(opc, text="Vista de depuración", variable=self.var_debug, command=self.cambiar_debug)
        c.pack(side="left", padx=(0, 12))
        self._ayuda(c, "Dibuja lo que ve el programa en el minimapa y la cámara. Usa algo más de CPU.")
        c = ttk.Checkbutton(opc, text="Guardar viaje (CSV)", variable=self.var_csv)
        c.pack(side="left")
        self._ayuda(c, "Guarda los datos del viaje en la carpeta viajes/ (lo que me envías para analizar).")

    def _pestana_conducir(self):
        tab = self.tab_conducir = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Conducir  ")
        izq = self.f_ctrl = ttk.Frame(tab, style="Panel.TFrame")
        izq.pack(side="left", fill="y")

        ped = self._seccion(izq, "Mandos")
        ped.pack(fill="x", pady=(8, 0))
        self.can = {}
        for i, (clave, txt, ayuda) in enumerate((("dir", "Volante", "Hacia dónde gira (centro = recto)."),
                                                  ("acel", "Acelerador", "Cuánto acelera."),
                                                  ("freno", "Freno", "Cuánto frena."))):
            ttk.Label(ped, text=txt, style="Panel.TLabel", width=10).grid(row=i, column=0, sticky="w", pady=2)
            cv = self._tkw(tk.Canvas(ped, width=250, height=12, highlightthickness=0), bg="campo")
            cv.grid(row=i, column=1, sticky="w", pady=2)
            self._ayuda(cv, ayuda)
            self.can[clave] = cv
        ind = ttk.Frame(ped, style="Panel.TFrame")
        ind.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.ind = {}
        for k, txt, ayuda in (("lento", "LENTO", "Modo lento activado."),
                              ("rapido", "RÁPIDO", "Modo rápido (experimental) activado."),
                              ("carril", "CARRIL", "Ayuda de carril: verde = usándola ahora."),
                              ("fuera", "FUERA DE CALLE", "El minimapa muestra al camión fuera de la calle."),
                              ("ruta", "RUTA", "Ve la ruta del GPS en el minimapa.")):
            l = tk.Label(ind, text=txt, font=("Segoe UI", 8, "bold"), padx=6, pady=1)
            l.pack(side="left", padx=(0, 4))
            self._ayuda(l, ayuda)
            self.ind[k] = l
        self.lbl_ultimo = ttk.Label(ped, text="Último viaje: -", style="Tenue.TLabel")   # 2.7.0
        self.lbl_ultimo.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._ayuda(self.lbl_ultimo, "Cuánto duró el último trabajo completo (de «cargado» a «trabajo completado»). "
                                     "En la pestaña Viajes están todos y el promedio de cada recorrido.")
        self.lbl_info = ttk.Label(ped, text="", style="Mono.TLabel")
        self.lbl_info.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._ayuda(self.lbl_info, "Datos técnicos: rumbo hacia la ruta, desvío lateral, curva por delante, "
                                   "control y velocímetro.")
        self.lbl_teclas = ttk.Label(izq, text="", style="Tenue.TLabel", wraplength=420, justify="left")
        self.lbl_teclas.pack(fill="x", pady=(8, 0))

        # vistas (minimapa y cámara)
        der = self.f_vistas = ttk.Frame(tab, style="Panel.TFrame")
        der.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.slot = {}
        for nombre, titulo, ayuda in (("minimapa", "Minimapa (depuración)",
                                       "Lo que ve el programa en el minimapa: ruta, punto que sigue, marcador."),
                                      ("carril", "Cámara / carril",
                                       "Vista desde arriba del carril (si la ayuda de carril está calibrada).")):
            f = self._seccion(der, titulo)
            f.pack(side="left", fill="both", expand=(nombre == "minimapa"), padx=(0, 6) if nombre == "minimapa"
                   else 0)
            cab = ttk.Frame(f, style="Panel.TFrame")
            cab.pack(fill="x")
            b = ttk.Button(cab, text="⧉ Separar", style="Seg.TButton", command=lambda n=nombre: self.separar(n))
            b.pack(side="right")
            self._ayuda(b, "Abre esta vista en una ventana aparte (por ejemplo, para ponerla en otra pantalla). "
                           "Cierra esa ventana para volver a acoplarla.")
            lbl = self._tkw(tk.Label(f, text="Sin imagen", padx=60 if nombre == "carril" else 100, pady=80),
                            bg="vista_bg", fg="tenue")
            lbl.pack(fill="both", expand=True, pady=(4, 0))
            self._ayuda(lbl, ayuda)
            self.slot[nombre] = (f, lbl, b)

    def _pestana_grabaciones(self):
        tab = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Grabaciones  ")
        self.tab_grab = tab
        cols = ("nombre", "recorrido", "tramo", "disparo", "fin", "dur")
        tv = self.tv_grab = ttk.Treeview(tab, columns=cols, show="headings", height=8)
        for c, t, w in (("nombre", "Nombre", 220), ("recorrido", "Recorrido", 170), ("tramo", "Tramo", 70),
                        ("disparo", "Cuándo se repite", 200), ("fin", "Al terminar", 110), ("dur", "Duración", 70)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True)
        self._ayuda(tv, "Grabaciones (datos/grabaciones) y trazados (datos/trazados). Se comparten con la "
                        "carpeta datos/.")
        bar = ttk.Frame(tab, style="Panel.TFrame")
        bar.pack(fill="x", pady=(8, 0))
        for txt, cmd, ayuda in (("Actualizar", self.cargar_lista_grab, "Vuelve a leer la carpeta."),
                                ("Renombrar…", self.renombrar_grab, "Cambia el nombre de la grabación elegida."),
                                ("Borrar", self.borrar_grab, "Borra la grabación elegida (pide confirmación)."),
                                ("Al terminar: seguir / parar", self.alternar_fin_grab,
                                 "Cambia qué hace la grabación elegida al terminar: seguir con el GPS o parar y "
                                 "dejarte el control. (Los trazados siempre siguen.)"),
                                ("Abrir carpeta", lambda: self.abrir_carpeta(carpetas.GRABACIONES),
                                 "Abre datos/grabaciones en el explorador.")):
            b = ttk.Button(bar, text=txt, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self._ayuda(b, ayuda)
        ttk.Label(tab, text="Para grabar: botón «● Grabar recorrido» en Conducir. Puedes grabar en tercera "
                            "persona; para repetir, vuelve a primera persona.", style="Tenue.TLabel").pack(
            fill="x", pady=(8, 0))

    def _pestana_viajes(self):
        tab = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Viajes  ")
        self.tab_viajes = tab
        cols = ("fecha", "recorrido", "duracion", "usuario", "programa", "puntos", "hitos", "obs", "tam")
        tv = self.tv_viajes = ttk.Treeview(tab, columns=cols, show="headings", height=8)
        for c, t, w in (("fecha", "Fecha", 140), ("recorrido", "Recorrido", 190), ("duracion", "Duración", 110),
                        ("usuario", "Usuario", 90),
                        ("programa", "Versión", 70), ("puntos", "Puntos críticos", 100), ("hitos", "Hitos", 50),
                        ("obs", "Observaciones", 100), ("tam", "Tamaño", 70)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True)
        tv.bind("<Double-1>", lambda _e: self.ver_obs_viaje())
        tv.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_tiempos())
        self.lbl_tiempos = ttk.Label(tab, text="Elige un viaje para ver cuánto duró y el promedio de su recorrido.",
                                     style="Tenue.TLabel", wraplength=900, justify="left")
        self.lbl_tiempos.pack(fill="x", pady=(6, 0))
        self._ayuda(tv, "Últimos viajes guardados en viajes/. Doble clic para ver las observaciones.")
        bar = ttk.Frame(tab, style="Panel.TFrame")
        bar.pack(fill="x", pady=(8, 0))
        for txt, cmd, ayuda in (("Actualizar", self.cargar_lista_viajes, "Vuelve a leer la carpeta viajes/."),
                                ("Ver observaciones", self.ver_obs_viaje,
                                 "Muestra las observaciones y puntos críticos guardados en el viaje elegido."),
                                ("Abrir archivo", self.abrir_viaje, "Abre el CSV del viaje elegido."),
                                ("Abrir carpeta", lambda: self.abrir_carpeta(carpetas.VIAJES),
                                 "Abre la carpeta viajes/ (de ahí sacas los archivos para enviarlos)."),
                                ("Calibrar con IA…", self.prompt_viaje_elegido,
                                 "Copia el prompt de calibración y prepara los archivos de este viaje para "
                                 "adjuntarlos en otro asistente de IA.")):
            b = ttk.Button(bar, text=txt, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self._ayuda(b, ayuda)

    def _pestana_calibracion(self):
        tab = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Calibración  ")
        cal = self._seccion(tab, "Pantalla del juego")
        cal.pack(fill="x")
        items = (("Calibrar todo", lambda: self.calibrar(None),
                  "Encuentra solo el minimapa, el velocímetro y los textos del HUD; tú revisas y confirmas. Sigue a la ventana del juego."),
                 ("Calibrar solo carril", lambda: self.calibrar("carril"),
                  "Calibra la vista de la cámara para la ayuda de carril (opcional)."),
                 ("Calibrar desde imagen…", self.calibrar_imagen, "Calibra usando una captura guardada."),
                 ("Continuar ▶", self.continuar, "Sigue con la calibración después de capturar con F11."),
                 ("Probar con video o imagen…", self.probar,
                  "Prueba la visión con un video o captura, sin el juego."),
                 ("Detener prueba", lambda: self.parar_prueba.set(), "Detiene la prueba con video."),
                 ("Medir zona muerta (mando)", self.medir_zona_muerta,
                  "Mide desde qué punto el volante del mando virtual hace girar al camión."))
        self.btn_continuar = None
        for i, (txt, cmd, ayuda) in enumerate(items):
            b = ttk.Button(cal, text=txt, command=cmd)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            self._ayuda(b, ayuda)
            if txt.startswith("Continuar"):
                self.btn_continuar = b
        cal.columnconfigure(0, weight=1)
        cal.columnconfigure(1, weight=1)
        arch = self._seccion(tab, "Archivos de tu equipo")
        arch.pack(fill="x", pady=(8, 0))
        for i, (txt, cmd, ayuda) in enumerate((
                ("Editar ajustes (config.json)", self.editar_config,
                 "Abre mi_equipo/config.json: calibración y ajustes finos. Los cambios valen al reiniciar."),
                ("Abrir mi_equipo", lambda: self.abrir_carpeta(carpetas.EQUIPO),
                 "Tu calibración de pantalla, preferencias y registro. No sirve para otra resolución."))):
            b = ttk.Button(arch, text=txt, command=cmd)
            b.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self._ayuda(b, ayuda)
        arch.columnconfigure(0, weight=1)
        arch.columnconfigure(1, weight=1)
        ia = self._seccion(tab, "Calibrar con otro asistente de IA")
        ia.pack(fill="x", pady=(8, 0))
        for i, (txt, cmd, ayuda) in enumerate((
                ("Copiar prompt + archivos", lambda: ventanas_extra.copiar_prompt_llm(self),
                 "Copia un prompt que le explica el programa a cualquier asistente de IA (ChatGPT, Gemini, "
                 "Claude…) y abre una carpeta con el último viaje y las reglas de su ruta, listos para adjuntar."),
                ("Ver el prompt", lambda: self.abrir_carpeta(ventanas_extra.ARCHIVO_PROMPT),
                 "Abre PROMPT_CALIBRACION.md."))):
            b = ttk.Button(ia, text=txt, command=cmd, style="Acento.TButton" if i == 0 else "TButton")
            b.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self._ayuda(b, ayuda)
        ia.columnconfigure(0, weight=1)
        ia.columnconfigure(1, weight=1)

    def prompt_viaje_elegido(self):
        v = self._viaje_elegido()
        if v:
            ventanas_extra.copiar_prompt_llm(self, v[0], v[1].get("recorrido"))

    def _pestana_ajustes(self):
        tab = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Ajustes  ")
        izq = ttk.Frame(tab, style="Panel.TFrame")
        izq.pack(side="left", fill="both", expand=True)
        der = ttk.Frame(tab, style="Panel.TFrame")
        der.pack(side="left", fill="both", expand=True, padx=(10, 0))

        u = self._seccion(izq, "Usuario")
        u.pack(fill="x")
        self.var_usuario = tk.StringVar(value=self._usuario_guardado())
        e = ttk.Entry(u, textvariable=self.var_usuario, width=28)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<FocusOut>", lambda _e: self._guardar_usuario())
        e.bind("<Return>", lambda _e: self._guardar_usuario())
        self._ayuda(e, "Tu nombre. Se anota en cada viaje y en las observaciones.")
        ttk.Button(u, text="Guardar", command=self._guardar_usuario).pack(side="left", padx=(6, 0))

        he = self._seccion(izq, "Teclas, instalación y ayuda")
        he.pack(fill="x", pady=(8, 0))
        for i, (txt, cmd, ayuda) in enumerate((
                ("Cambiar teclas…", lambda: ventanas_extra.ventana_teclas(self),
                 "Cambia las teclas del programa (activar, modo lento, tomar el control…) y si el camión se "
                 "maneja con teclado o con mando virtual."),
                ("Comprobar instalación…", lambda: ventanas_extra.ventana_diagnostico(self),
                 "Revisa que estén las librerías y herramientas que usa el programa y dice qué hacer si falta algo."),
                ("Ver tutorial", lambda: ventanas_extra.ventana_tutorial(self),
                 "Los primeros pasos para usar el programa."))):
            b = ttk.Button(he, text=txt, command=cmd)
            b.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self._ayuda(b, ayuda)
            he.columnconfigure(i, weight=1)

        ap = self._seccion(izq, "Apariencia")
        ap.pack(fill="x", pady=(8, 0))
        self.var_tema = tk.StringVar(value=self.prefs["tema"])
        ttk.Label(ap, text="Tema:", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        for i, (v, t) in enumerate((("oscuro", "Oscuro"), ("claro", "Claro"))):
            r = ttk.Radiobutton(ap, text=t, value=v, variable=self.var_tema,
                                command=lambda: self.aplicar_tema(self.var_tema.get()))
            r.grid(row=0, column=1 + i, sticky="w", padx=(6, 0))
            self._ayuda(r, f"Tema {t.lower()} para la ventana del programa.")
        self.var_vista = tk.StringVar(value=self.prefs["vista"])
        ttk.Label(ap, text="Vista:", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        for i, (v, t) in enumerate((("completa", "Completa"), ("compacta", "Compacta"), ("mini", "Mini"))):
            r = ttk.Radiobutton(ap, text=t, value=v, variable=self.var_vista,
                                command=lambda: self.poner_vista(self.var_vista.get()))
            r.grid(row=1, column=1 + i, sticky="w", padx=(6, 0), pady=(6, 0))
        self.var_ayuda = tk.BooleanVar(value=self.prefs.get("ayuda", True))
        c = ttk.Checkbutton(ap, text="Mostrar ayuda al pasar el mouse", variable=self.var_ayuda,
                            command=self._cambio_ayuda)
        c.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        pf = self._seccion(izq, "Panel flotante (para jugar con una sola pantalla)")
        pf.pack(fill="x", pady=(8, 0))
        self.var_panel = tk.StringVar(value=panel.MODOS.get(self.prefs["panel"].get("modo", "auto"),
                                                             panel.MODOS["auto"]))
        ttk.Label(pf, text="Mostrar:", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(pf, textvariable=self.var_panel, values=list(panel.MODOS.values()), state="readonly",
                          width=36)
        cb.grid(row=0, column=1, sticky="w", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._cambio_panel())
        self._ayuda(cb, "Tira chica y semitransparente arriba al centro de la pantalla del juego, con estado, "
                        "velocidad, distancia y avisos. No roba el foco ni tapa lo que el programa lee. "
                        "Automático = se muestra solo si el PC tiene una sola pantalla.")
        self.lbl_panel_tecla = ttk.Label(pf, text="", style="Tenue.TLabel", wraplength=420, justify="left")
        self.lbl_panel_tecla.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._texto_tecla_panel()

        info = self._seccion(izq, "Versión y carpetas")
        info.pack(fill="x", pady=(8, 0))
        self.lbl_versiones = ttk.Label(info, text="", style="Panel.TLabel", justify="left")
        self.lbl_versiones.grid(row=0, column=0, columnspan=2, sticky="w")
        self._ayuda(self.lbl_versiones, "Versión del programa y de los datos. Si alguien te pasa datos más "
                                        "nuevos, el programa avisa si necesita actualizarse.")
        for i, (txt, cmd, ayuda) in enumerate((
                ("Abrir datos/", lambda: self.abrir_carpeta(carpetas.DATOS),
                 "Rutas, grabaciones y trazados. Para compartirlos, envía esta carpeta."),
                ("Ver cambios", lambda: self.abrir_carpeta(os.path.join(carpetas.RAIZ, "CAMBIOS.md")),
                 "Historial de versiones (CAMBIOS.md)."),
                ("Ver manual", lambda: self.abrir_carpeta(os.path.join(carpetas.RAIZ, "LEEME.md")),
                 "Instrucciones completas (LEEME.md)."))):
            b = ttk.Button(info, text=txt, command=cmd)
            b.grid(row=1, column=i, sticky="ew", padx=2, pady=(6, 0))
            self._ayuda(b, ayuda)
        self.var_revisar = tk.BooleanVar(value=self.prefs["actualizaciones"].get("revisar", True))
        c = ttk.Checkbutton(info, text="Buscar versiones nuevas al abrir el programa", variable=self.var_revisar,
                            command=self._cambio_revisar)
        c.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._ayuda(c, "Al abrir, consulta en GitHub si hay una versión nueva (solo lee un número; no envía nada "
                       "tuyo). Si la hay, te muestra qué cambia y tú decides si actualizar.")
        for i, (txt, cmd, ayuda) in enumerate((
                ("Buscar actualizaciones", lambda: ventana_actualizar.revisar(self, manual=True),
                 "Consulta ahora en GitHub si hay una versión nueva."),
                ("Actualizar desde .zip…", lambda: ventana_actualizar.desde_zip(self),
                 "Instala una versión desde un .zip que te pasaron (sin internet). Guarda antes una copia de lo "
                 "que reemplaza."))):
            b = ttk.Button(info, text=txt, command=cmd)
            b.grid(row=3, column=i, sticky="ew", padx=2, pady=(6, 0))
            self._ayuda(b, ayuda)
        for i in range(3):
            info.columnconfigure(i, weight=1)

        n = self._seccion(der, "Notificaciones en pantalla")
        n.pack(fill="both", expand=True)
        a = self.prefs["notificaciones"]
        self.var_n_activas = tk.BooleanVar(value=a.get("activas", True))
        c = ttk.Checkbutton(n, text="Mostrar notificaciones encima del juego", variable=self.var_n_activas,
                            command=self._cambio_notif)
        c.grid(row=0, column=0, columnspan=2, sticky="w")
        self._ayuda(c, "Avisos tipo Discord encima del juego. No le quitan el foco. Se ven con el juego en "
                       "ventana o pantalla completa sin bordes (no en pantalla completa exclusiva).")
        self.var_n_tipo = {}
        for i, (k, (_col, _ic, nombre)) in enumerate(notificador.TIPOS.items()):
            v = tk.BooleanVar(value=a["tipos"].get(k, True))
            self.var_n_tipo[k] = v
            ttk.Checkbutton(n, text=nombre, variable=v, command=self._cambio_notif).grid(
                row=1 + i, column=0, columnspan=2, sticky="w")
        fila = 1 + len(notificador.TIPOS)
        self.var_n = {}
        esquinas = {"arriba_derecha": "Arriba a la derecha", "arriba_izquierda": "Arriba a la izquierda",
                    "abajo_derecha": "Abajo a la derecha", "abajo_izquierda": "Abajo a la izquierda"}
        pantallas = {"juego": "Pantalla del juego", "principal": "Pantalla principal"}
        for i in range(max(1, len(notificador.monitores()))):
            pantallas[str(i + 1)] = f"Pantalla {i + 1}"
        sonidos = {"ninguno": "Sin sonido", "problemas": "Solo problemas", "todos": "Todos"}
        tamanos = {"chico": "Chico", "normal": "Normal", "grande": "Grande"}
        for j, (clave, etiqueta, opciones, ayuda) in enumerate((
                ("esquina", "Esquina", esquinas, "Dónde aparecen los avisos."),
                ("pantalla", "Pantalla", pantallas, "En qué pantalla aparecen. «Pantalla del juego» busca la "
                                                    "ventana del juego."),
                ("sonido", "Sonido", sonidos, "Sonido corto de Windows al aparecer un aviso."),
                ("tamano", "Tamaño", tamanos, "Tamaño de los avisos."))):
            ttk.Label(n, text=etiqueta + ":", style="Panel.TLabel").grid(row=fila + j, column=0, sticky="w",
                                                                      pady=(6, 0))
            var = tk.StringVar(value=opciones.get(str(a.get(clave)), list(opciones.values())[0]))
            cb = ttk.Combobox(n, textvariable=var, values=list(opciones.values()), state="readonly", width=22)
            cb.grid(row=fila + j, column=1, sticky="w", pady=(6, 0))
            cb.bind("<<ComboboxSelected>>", lambda _e: self._cambio_notif())
            self._ayuda(cb, ayuda)
            self.var_n[clave] = (var, opciones)
        fila += 4
        ttk.Label(n, text="Duración (s):", style="Panel.TLabel").grid(row=fila, column=0, sticky="w", pady=(6, 0))
        self.var_n_dur = tk.StringVar(value=str(int(float(a.get("duracion_seg", 4)))))
        sp = ttk.Spinbox(n, from_=2, to=15, textvariable=self.var_n_dur, width=5, command=self._cambio_notif)
        sp.grid(row=fila, column=1, sticky="w", pady=(6, 0))
        sp.bind("<FocusOut>", lambda _e: self._cambio_notif())
        b = ttk.Button(n, text="Probar notificación", command=self._probar_notif)
        b.grid(row=fila + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._ayuda(b, "Muestra un aviso de ejemplo de cada tipo, para ver dónde y cómo aparecen.")

    # ------------------------------------------------------------ experimental (2.3.2)
    EXPERIMENTAL = (
        ("velocidad_suave_curvas", "Velocidad suave en curvas, esquinas y reglas lentas", "2.3.2",
         "Con límite de menos de 50 km/h (reglas, curvas y, desde la 2.3.4, curvas cerradas y esquinas) acelera con "
         "menos fuerza y frena solo si se pasa más de 10 km/h. Evita el sube y baja de velocidad (19 ↔ 51 km/h en la "
         "curva de Banning, frenadas en la esquina de Maze Bank) que pasa porque el velocímetro del HUD llega 1-2 s "
         "tarde. Si entra muy rápido a alguna esquina, apágala."),
        ("velocidad_sin_vaiven", "Velocidad sin sube y baja", "3.2.4",
         "Al pasarse un poco del límite (hasta 8 km/h) baja el acelerador a la mitad del que mantiene la velocidad en "
         "vez de soltarlo del todo (en GTA soltarlo ya frena ~15 km/h por segundo), se anticipa a si la velocidad "
         "viene subiendo o bajando y, tras frenar, vuelve enseguida al acelerador de mantener. Evita el vaivén "
         "24 ↔ 48 km/h con límite 40 (Banning). Si se pasa de velocidad en algún lugar, apágala."),
        ("trazados_comunes_vuelta", "Trazados comunes en la vuelta", "2.3.2",
         "Los trazados de la vuelta grabados desde 2,3 km (el final, igual para todos los recorridos) se usan en "
         "todos los recorridos, no solo en el que se grabaron."),
        ("lado_suave_autopista", "Corrección de lado suave en autopista", "2.5.2",
         "A 70 km/h o más, el programa corrige el lado según la línea del GPS promediada en ~0,5 s, no cuadro a "
         "cuadro. La línea del minimapa a veces se corre de lado un instante sin que el camión se mueva (así chocó "
         "con la barrera a 3,16 km en Mirror Park): con esto casi no mueve el volante por eso. Las curvas no "
         "cambian. Si en autopista lo notas lento para volver a la línea, apágala."),
        ("usar_grabaciones", "Usar grabaciones de teclas", "2.4.1",
         "Apágalo para hacer a mano las entradas, salidas y llegadas que tienen grabación, sin borrar nada: "
         "mientras esté apagado ninguna grabación se repite sola. Vale al momento."),
        ("rumbo_norte", "Rumbo exacto (la N del minimapa)", "2.4.0",
         "Detecta la N que recorre el borde del minimapa y mide cuánto gira el mapa de un cuadro a otro: da hacia "
         "dónde apunta el camión en grados. Se guarda en el viaje (columna rumbo_abs) y con él se arma el mapa de "
         "la ruta. Se aplica al iniciar el programa."),
        ("mapa_ruta", "Mapa de la ruta", "2.4.0",
         "Al detener el programa, si el viaje tiene rumbo y el recorrido aún no tiene mapa, se arma solo "
         "(datos/mapas/). En el mapa se ven las reglas, trazados y grabaciones, se pueden editar, apagar o borrar "
         "reglas, y se ve el camión en tiempo real."),
    )

    def _pestana_experimental(self):
        tab = ttk.Frame(self.nb, style="Panel.TFrame", padding=8)
        self.nb.add(tab, text="  Experimental  ")
        aviso = self._tkw(tk.Label(tab, text="⚠  Funciones en prueba: pueden fallar o cambiar. Si algo sale mal, "
                                             "apágalas aquí. Los cambios se aplican al momento.",
                                   anchor="w", justify="left", padx=10, pady=6, font=("Segoe UI", 9, "bold")),
                          bg="regla_bg", fg="regla_fg")
        aviso.pack(fill="x")
        caja = self._seccion(tab, "Funciones")
        caja.pack(fill="x", pady=(8, 0))
        crudo = carpetas.leer_json(CONFIG, {}) if os.path.exists(CONFIG) else {}
        actual = dict(configuracion.DEFAULTS.get("experimental", {}), **(crudo.get("experimental") or {}))
        self.var_exp = {}
        for i, (clave, nombre, desde, ayuda) in enumerate(self.EXPERIMENTAL):
            var = tk.BooleanVar(value=bool(actual.get(clave, True)))
            self.var_exp[clave] = var
            c = ttk.Checkbutton(caja, text=nombre, variable=var, command=lambda k=clave: self._cambio_experimental(k))
            c.grid(row=i, column=0, sticky="w", pady=2)
            self._ayuda(c, ayuda)
            ttk.Label(caja, text=f"en prueba desde {desde}", style="Tenue.TLabel").grid(row=i, column=1, sticky="w",
                                                                                     padx=(12, 0))
        b = ttk.Button(tab, text="Abrir mapa de la ruta…", style="Acento.TButton", command=self.abrir_mapa)
        b.pack(anchor="w", pady=(10, 0))
        self._ayuda(b, "Ventana con el recorrido dibujado, sus reglas (editar, apagar, borrar), trazados, grabaciones "
                       "y el camión en tiempo real.")
        self._seccion_modos(tab)
        self._seccion_compartidos(tab)
        ttk.Label(tab, text="Cuando una función ya está probada y funciona bien, pasa a ser fija en una versión "
                            "siguiente y sale de esta pestaña.", style="Tenue.TLabel", wraplength=700,
                  justify="left").pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------ modos lento / rápido (2.6.0)
    def _seccion_modos(self, tab):
        caja = self._seccion(tab, "Modos de velocidad")
        caja.pack(fill="x", pady=(10, 0))
        ttk.Label(caja, text="Se prenden y apagan mientras manejas, con el botón o con su tecla (Ajustes → Cambiar "
                             "teclas → Experimental). Uno apaga al otro. Las reglas de cada lugar mandan igual.",
                  style="Tenue.TLabel", wraplength=760, justify="left").pack(anchor="w")
        fila = ttk.Frame(caja)
        fila.pack(fill="x", pady=(4, 0))
        try:
            import ventanas_extra
            t = ventanas_extra._leer_teclas()[0]
        except Exception:  # noqa
            t = {}
        for txt, cmd, ayuda in (("Modo lento", "lento", f"Limita la velocidad a 15 km/h un rato (se apaga solo a los "
                                                       f"90 s). Tecla: {t.get('modo_lento', 'PAGEUP')}."),
                                ("Modo rápido", "rapido", "Más velocidad (recta 90, recta larga 110 y más fácil de "
                                                          "alcanzar, curvas +15 %, esquinas +5) y curvas más fluidas "
                                                          "(suelta en vez de frenar, ignora curvas de un instante, "
                                                          "acelera antes al salir). Puede chocar más. Tecla: "
                                                          f"{t.get('modo_rapido', 'F10')}.")):
            b = ttk.Button(fila, text=txt, command=lambda c=cmd: self.orden(c))
            b.pack(side="left", padx=(0, 6))
            self._ayuda(b, ayuda)
            self._btns_modos = getattr(self, "_btns_modos", []) + [b]
            self.btns_ap.append(b)

    # ------------------------------------------------------------ tramos compartidos (2.5.0)
    def _seccion_compartidos(self, tab):
        caja = self._seccion(tab, "Tramos compartidos entre recorridos")
        caja.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(caja, text="Partes donde dos recorridos van por las mismas calles (se encuentran solas comparando "
                             "el rumbo de los viajes). En un tramo CONFIRMADO, las reglas de un recorrido valen "
                             "también para el otro. Los nuevos quedan pendientes hasta que los confirmes.",
                  style="Tenue.TLabel", wraplength=760, justify="left").pack(anchor="w")
        self.tv_comp = ttk.Treeview(caja, columns=("estado", "donde", "desfase", "error"), show="headings", height=5)
        for c, t, w in (("estado", "Estado", 100), ("donde", "Dónde", 470), ("desfase", "Diferencia", 80),
                        ("error", "Coincidencia", 90)):
            self.tv_comp.heading(c, text=t)
            self.tv_comp.column(c, width=w, anchor="w")
        self.tv_comp.pack(fill="x", pady=(4, 0))
        fila = ttk.Frame(caja)
        fila.pack(fill="x", pady=(4, 0))
        b = ttk.Button(fila, text="Confirmar", style="Acento.TButton", command=lambda: self._estado_comp("confirmado"))
        b.pack(side="left")
        self._ayuda(b, "Desde ahora las reglas de ese tramo valen para los dos recorridos. Revísalo antes en el mapa "
                       "de la ruta (se ve en amarillo).")
        b = ttk.Button(fila, text="Apagar", command=lambda: self._estado_comp("apagado"))
        b.pack(side="left", padx=4)
        self._ayuda(b, "No se usa (queda anotado para que no vuelva a aparecer como nuevo).")
        b = ttk.Button(fila, text="Buscar ahora", command=self._buscar_comp)
        b.pack(side="left")
        self._ayuda(b, "Vuelve a comparar los recorridos (datos/perfiles/). Se hace solo al detener el programa "
                       "después de un viaje con rumbo exacto.")
        b = ttk.Button(fila, text="Agregar viaje…", command=self._viaje_comp)
        b.pack(side="left", padx=4)
        self._ayuda(b, "Usa un viaje guardado (hecho con rumbo exacto) para el perfil de su recorrido y busca tramos "
                       "compartidos.")
        self._llenar_comp()

    def _llenar_comp(self):
        import compartidos
        import rutas
        tv = getattr(self, "tv_comp", None)
        if tv is None:
            return
        tv.delete(*tv.get_children())
        try:
            nombres = {os.path.splitext(r["_archivo"])[0]: r.get("nombre", r["_archivo"])
                       for r in rutas.cargar()["rutas"]}
        except Exception:  # noqa
            nombres = {}
        txt = {"confirmado": "✓ confirmado", "pendiente": "? pendiente", "apagado": "— apagado"}
        for n, g in enumerate(compartidos.cargar().get("tramos", [])):
            tv.insert("", "end", iid=str(n), values=(txt.get(g.get("estado"), g.get("estado")),
                                                    compartidos.describir(g, nombres),
                                                    f"{g.get('desfase', 0):+d} m", f"±{g.get('error', '?')}°"))

    def _estado_comp(self, estado):
        import compartidos
        sel = self.tv_comp.selection()
        if not sel:
            messagebox.showinfo("Tramos compartidos", "Elige un tramo de la lista.", parent=self.root)
            return
        d = compartidos.cargar()
        for iid in sel:
            d["tramos"][int(iid)]["estado"] = estado
        try:
            compartidos.guardar(d)
        except Exception as e:  # noqa
            messagebox.showerror("Tramos compartidos", f"No se pudo guardar:\n{e}", parent=self.root)
            return
        print(f"[OK] Tramo(s) compartido(s): {estado}.")
        self._llenar_comp()
        if self.ap is not None:
            self.orden("recargar_rutas")
        v = getattr(self, "ventana_mapa", None)
        try:
            if v is not None and v.win.winfo_exists():
                v.recargar()
        except Exception:  # noqa
            pass

    def _buscar_comp(self):
        import compartidos
        try:
            nuevos = compartidos.detectar()
        except Exception as e:  # noqa
            messagebox.showerror("Tramos compartidos", f"No se pudo buscar:\n{e}", parent=self.root)
            return
        self._llenar_comp()
        messagebox.showinfo("Tramos compartidos", f"Tramos nuevos encontrados: {len(nuevos)}." +
                            ("\nQuedan pendientes: revísalos en el mapa y confírmalos." if nuevos else ""),
                            parent=self.root)

    def _viaje_comp(self):
        import compartidos
        ruta = filedialog.askopenfilename(parent=self.root, initialdir=carpetas.VIAJES, title="Viaje con rumbo",
                                          filetypes=(("Viajes", "viaje_*.csv"), ("CSV", "*.csv")))
        if not ruta:
            return
        try:
            hechos = compartidos.desde_viaje(ruta)
        except Exception as e:  # noqa
            messagebox.showerror("Tramos compartidos", f"No se pudo leer el viaje:\n{e}", parent=self.root)
            return
        if not hechos:
            messagebox.showinfo("Tramos compartidos", "Ese viaje no tiene rumbo exacto o recorrido reconocido.",
                                parent=self.root)
            return
        print(f"[OK] Perfil guardado: {', '.join(rec for rec, _t in hechos)}.")
        self._buscar_comp()

    def abrir_mapa(self):
        import ventana_mapa
        try:
            ventana_mapa.abrir(self)
        except Exception as e:  # noqa
            messagebox.showerror("Mapa de la ruta", f"No se pudo abrir el mapa:\n{e}", parent=self.root)

    def _cambio_experimental(self, clave):
        val = bool(self.var_exp[clave].get())
        try:
            if os.path.exists(CONFIG):
                crudo = carpetas.leer_json(CONFIG, {})
                if not crudo:
                    raise ValueError("mi_equipo/config.json no se puede leer")
                crudo.setdefault("experimental", {})[clave] = val
                carpetas.guardar_json(CONFIG, crudo)
            else:
                cfg = configuracion.cargar(CONFIG, guardar_migracion=False)
                cfg.setdefault("experimental", {})[clave] = val
                os.makedirs(carpetas.EQUIPO, exist_ok=True)
                configuracion.guardar(cfg, CONFIG)
        except Exception as e:  # noqa
            messagebox.showerror("Experimental", f"No se pudo guardar:\n{e}", parent=self.root)
            return
        nombre = next(n for k, n, _d, _a in self.EXPERIMENTAL if k == clave)
        if self.ap is not None:
            self.orden(f"experimental:{clave}:{1 if val else 0}")     # el programa lo anota en el registro
        else:
            print(f"[i] Experimental: {nombre} {'ACTIVADO' if val else 'desactivado'}.")

    # ------------------------------------------------------------ vistas
    def poner_vista(self, vista, guardar=True):
        vista = vista if vista in ("completa", "compacta", "mini") else "completa"
        actual = getattr(self, "_vista", None)
        if actual and guardar:
            self.prefs["geometria"][actual] = self.root.geometry()
        self._vista = vista
        self.prefs["vista"] = vista
        if hasattr(self, "var_vista"):
            self.var_vista.set(vista)
        for k, b in self.btn_vista.items():
            b.configure(style="SegOn.TButton" if k == vista else "Seg.TButton")
        # orden de arriba a abajo
        for w in (self.f_tarjetas, self.f_lugar, self.f_avisos, self.f_diario, self.nb, self.f_reg):
            w.pack_forget()
        self.f_tarjetas.pack(fill="x", pady=(8, 0))
        self.f_lugar.pack(fill="x", pady=(8, 0))
        if self._avisos_claves:
            self.f_avisos.pack(fill="x", pady=(8, 0))
        self.f_diario.pack(fill="x", pady=(8, 0))
        if vista == "mini":
            self.f_diario_opc.pack_forget()
            self.f_reg.pack(fill="both", expand=True, pady=(8, 0))
            self.txt_log.configure(height=6)
        else:
            self.f_diario_opc.pack(fill="x", pady=(5, 0))
            self.nb.pack(fill="both", expand=True, pady=(8, 0))
            self.f_reg.pack(fill="both", expand=False, pady=(8, 0))
            self.txt_log.configure(height=9 if vista == "completa" else 7)
        if vista == "completa":
            self.f_vistas.pack(side="left", fill="both", expand=True, padx=(10, 0))
        else:
            self.f_vistas.pack_forget()
        geo = self.prefs["geometria"].get(vista) or PREFS_DEFECTO["geometria"][vista]
        try:
            self.root.geometry(geo)
        except tk.TclError:
            self.root.geometry(PREFS_DEFECTO["geometria"][vista])
        if guardar:
            self.guardar_prefs()

    def separar(self, nombre):
        """Abre la vista (minimapa o cámara) en una ventana aparte."""
        if nombre in self.ventanas:
            self.ventanas[nombre][0].lift()
            return
        win = tk.Toplevel(self.root)
        win.title("Minimapa (depuración)" if nombre == "minimapa" else "Cámara / carril")
        win.configure(bg=self.T["bg"])
        geo = self.prefs["geometria"].get("ventana_" + nombre) or ("420x420" if nombre == "minimapa" else "300x420")
        try:
            win.geometry(geo)
        except tk.TclError:
            pass
        lbl = tk.Label(win, text="Sin imagen", bg=self.T["vista_bg"], fg=self.T["tenue"])
        lbl.pack(fill="both", expand=True)
        win.protocol("WM_DELETE_WINDOW", lambda: self.acoplar(nombre))
        self.ventanas[nombre] = (win, lbl)
        f, lbl_slot, b = self.slot[nombre]
        lbl_slot.configure(image="", text="En ventana aparte.\nCiérrala para volver a acoplarla.")
        b.configure(text="⧉ Acoplar", command=lambda: self.acoplar(nombre))
        self.prefs["separadas"][nombre] = True
        self.guardar_prefs()

    def acoplar(self, nombre):
        if nombre not in self.ventanas:
            return
        win, _ = self.ventanas.pop(nombre)
        self.prefs["geometria"]["ventana_" + nombre] = win.geometry()
        win.destroy()
        f, lbl_slot, b = self.slot[nombre]
        lbl_slot.configure(text="Sin imagen")
        b.configure(text="⧉ Separar", command=lambda: self.separar(nombre))
        self.prefs["separadas"][nombre] = False
        self.guardar_prefs()

    def _destino_imagen(self, nombre):
        """Label donde dibujar la vista, o None si no se ve (para no gastar CPU)."""
        if nombre in self.ventanas:
            return self.ventanas[nombre][1]
        if self._vista == "completa":
            return self.slot[nombre][1]
        return None

    def _cambio_pestana(self, _e=None):
        try:
            actual = self.nb.select()
        except tk.TclError:
            return
        if actual == str(self.tab_grab):
            self.cargar_lista_grab()
        elif actual == str(self.tab_viajes):
            self.cargar_lista_viajes()

    def _cambio_panel(self):
        inv = {v: k for k, v in panel.MODOS.items()}
        self.prefs["panel"]["modo"] = inv.get(self.var_panel.get(), "auto")
        self.panel.override = None
        self.guardar_prefs()

    def _texto_tecla_panel(self):
        try:
            tecla = ventanas_extra._leer_teclas()[0].get("panel") or "F6"
        except Exception:  # noqa
            tecla = "F6"
        n = self.panel.monitores()
        pantallas = ("Este PC tiene una sola pantalla: en modo automático el panel se verá solo."
                     if n == 1 else (f"Este PC tiene {n} pantallas: en modo automático el panel no se muestra."
                                     if n > 1 else ""))
        self.lbl_panel_tecla.config(text=f"En el juego, la tecla {tecla} prende o apaga el panel. {pantallas}".strip())

    def _cambio_revisar(self):
        self.prefs["actualizaciones"]["revisar"] = bool(self.var_revisar.get())
        self.guardar_prefs()

    def _cambio_ayuda(self):
        self.prefs["ayuda"] = bool(self.var_ayuda.get())
        self.guardar_prefs()

    # ------------------------------------------------------------ notificaciones (ajustes)
    def _cambio_notif(self):
        a = self.prefs["notificaciones"]
        a["activas"] = bool(self.var_n_activas.get())
        a["tipos"] = {k: bool(v.get()) for k, v in self.var_n_tipo.items()}
        for clave, (var, opciones) in self.var_n.items():
            inv = {v: k for k, v in opciones.items()}
            a[clave] = inv.get(var.get(), a.get(clave))
        try:
            a["duracion_seg"] = max(2, min(15, int(float(self.var_n_dur.get()))))
        except ValueError:
            pass
        self.notif.configurar(a)
        self.guardar_prefs()

    def _probar_notif(self):
        self._cambio_notif()
        ejemplos = (("etapa", "Recorrido reconocido", "Drogas - Granja 1 · 5,69 km"),
                    ("problema", "Choque", "Textile City / Strawberry Avenue · 2,10 km · 81 km/h"),
                    ("grabacion", "Repitiendo grabación", "Granja 1 - entrada"),
                    ("control", "Tomaste el control", "Vinewood Hills · 1,53 km"))
        for i, (t, ti, tx) in enumerate(ejemplos):
            self.root.after(i * 700, lambda t=t, ti=ti, tx=tx: self.notif.mostrar(t, ti, tx, forzar=True))

    # ------------------------------------------------------------ grabaciones (pestaña)
    def cargar_lista_grab(self):
        import grabaciones
        tv = self.tv_grab
        tv.delete(*tv.get_children())
        self._grabs = {}
        for g in grabaciones.cargar_todas():
            d = g.get("disparo", {})
            tipo = d.get("tipo")
            disparo = {"distancia": f"Al llegar a {_km(d.get('metros'))}", "cargado": "Tras «cargado»",
                       "descargado": "Tras «descargado»",
                       "final": f"Punto final, a {_km(d.get('metros'))}"}.get(tipo, tipo or "-")
            tramo = {0: "Ir a cargar", 1: "Ida", 2: "Vuelta"}.get(g.get("tramo"), str(g.get("tramo")))
            iid = tv.insert("", "end", values=(g.get("nombre", "?"), g.get("recorrido") or "Cualquiera", tramo,
                                               disparo, "Seguir con GPS" if g.get("al_terminar") == "seguir"
                                               else "Parar", f"{g.get('duracion', 0):.0f} s"))
            g["_carpeta"] = carpetas.GRABACIONES
            self._grabs[iid] = g
        for t in grabaciones.cargar_trazados():
            tramo = {0: "Ir a cargar", 1: "Ida", 2: "Vuelta"}.get(t.get("tramo"), str(t.get("tramo")))
            iid = tv.insert("", "end", values=(t.get("nombre", "?"), t.get("recorrido") or "Cualquiera", tramo,
                                               f"Trazado {_km(t.get('desde'))} → {_km(t.get('hasta'))}",
                                               "-", f"{len(t.get('puntos', []))} pts"))
            t["_carpeta"] = carpetas.TRAZADOS
            self._grabs[iid] = t

    def _grab_elegida(self):
        sel = self.tv_grab.selection()
        if not sel:
            messagebox.showinfo("Grabaciones", "Elige una grabación de la lista.", parent=self.root)
            return None
        return self._grabs.get(sel[0])

    def renombrar_grab(self):
        g = self._grab_elegida()
        if g is None:
            return
        nuevo = simpledialog.askstring("Renombrar", "Nombre nuevo:", initialvalue=g.get("nombre", ""),
                                       parent=self.root)
        if not nuevo or not nuevo.strip():
            return
        ruta = os.path.join(g.get("_carpeta", carpetas.GRABACIONES), g["_archivo"])
        try:
            d = carpetas.leer_json(ruta)
            d["nombre"] = nuevo.strip()
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            print(f"[OK] Grabación renombrada: {nuevo.strip()}")
        except Exception as e:  # noqa
            print(f"[!] No se pudo renombrar: {e}")
        self.cargar_lista_grab()
        self.orden("recargar_grabaciones")

    def alternar_fin_grab(self):
        g = self._grab_elegida()
        if g is None:
            return
        if g.get("tipo") == "trazado":
            messagebox.showinfo("Grabaciones", "Los trazados no paran: el autopiloto sigue manejando todo el "
                                               "tramo.", parent=self.root)
            return
        ruta = os.path.join(g.get("_carpeta", carpetas.GRABACIONES), g["_archivo"])
        try:
            d = carpetas.leer_json(ruta)
            d["al_terminar"] = "parar" if d.get("al_terminar") == "seguir" else "seguir"
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            print(f"[OK] {d.get('nombre')}: al terminar → "
                  f"{'seguir con el GPS' if d['al_terminar'] == 'seguir' else 'parar y dejarte el control'}")
        except Exception as e:  # noqa
            print(f"[!] No se pudo cambiar: {e}")
        self.cargar_lista_grab()
        self.orden("recargar_grabaciones")

    def borrar_grab(self):
        g = self._grab_elegida()
        if g is None:
            return
        if not messagebox.askyesno("Borrar grabación", f"¿Borrar «{g.get('nombre')}»?", parent=self.root):
            return
        try:
            os.remove(os.path.join(g.get("_carpeta", carpetas.GRABACIONES), g["_archivo"]))
            print(f"[OK] Grabación borrada: {g.get('nombre')}")
        except Exception as e:  # noqa
            print(f"[!] No se pudo borrar: {e}")
        self.cargar_lista_grab()
        self.orden("recargar_grabaciones")

    # ------------------------------------------------------------ viajes (pestaña)
    @staticmethod
    def _resumen_viaje(ruta):
        """Lee solo el principio y el final del CSV (pueden pesar 10 MB)."""
        r = {"recorrido": "-", "usuario": "-", "programa": "anterior", "puntos": 0, "hitos": 0, "obs": "No",
             "lineas": []}
        try:
            with open(ruta, "rb") as fh:
                cab = fh.read(800).decode("utf-8", "ignore").splitlines()
                fh.seek(0, 2)
                tam = fh.tell()
                fh.seek(max(0, tam - 200000))
                cola = fh.read().decode("utf-8", "ignore").splitlines()
        except Exception:  # noqa
            return r
        for l in cab:
            if l.startswith("# programa:"):
                r["programa"] = l.split(":", 1)[1].strip()
            elif l.startswith("# usuario:"):
                r["usuario"] = l.split(":", 1)[1].strip()
        notas = [l for l in cola if l.startswith("#")]
        r["lineas"] = notas
        for l in notas:
            if l.startswith("# recorrido:") and l.split(":", 1)[1].strip() not in ("", "-"):
                r["recorrido"] = l.split(":", 1)[1].strip()
            elif l.startswith("# usuario:"):
                r["usuario"] = l.split(":", 1)[1].strip()
            elif l.startswith("# punto"):
                r["puntos"] += 1
            elif l.startswith("# hito"):
                r["hitos"] += 1
            elif l.startswith("# === OBSERVACIONES"):
                r["obs"] = "Sí"
        if r["recorrido"] == "-":
            # sin observaciones: el recorrido sale de la última fila
            import csv as _csv
            cabecera = next((l for l in cab if l.startswith("t,estado")), "")
            idx = cabecera.split(",").index("ruta") if ",ruta," in cabecera else 33
            for l in reversed(cola[-50:]):
                if l and not l.startswith("#"):
                    try:
                        partes = next(_csv.reader([l]))
                    except Exception:  # noqa
                        partes = []
                    if len(partes) > idx and partes[idx]:      # 2.4.0: columnas nuevas al final
                        r["recorrido"] = partes[idx]
                    break
        return r

    def cargar_lista_viajes(self):
        tv = self.tv_viajes
        tv.delete(*tv.get_children())
        self._viajes = {}
        try:
            archivos = sorted((f for f in os.listdir(carpetas.VIAJES) if f.startswith("viaje_") and
                               f.endswith(".csv")), reverse=True)[:60]
        except Exception:  # noqa
            archivos = []
        for f in archivos:
            ruta = os.path.join(carpetas.VIAJES, f)
            r = self._resumen_viaje(ruta)
            try:
                fecha = datetime.datetime.strptime(f[6:21], "%Y%m%d_%H%M%S").strftime("%d-%m-%Y %H:%M")
            except ValueError:
                fecha = f
            tam = os.path.getsize(ruta) / 1e6
            iid = tv.insert("", "end", values=(fecha, r["recorrido"], "…", r["usuario"], r["programa"],
                                               r["puntos"], r["hitos"], r["obs"], f"{tam:.1f} MB"))
            self._viajes[iid] = (ruta, r)
        self._calcular_tiempos()

    # ------------------------------------------------------------ tiempos (2.7.0)
    def _calcular_tiempos(self):
        """Lee los tiempos de los viajes en segundo plano (la primera vez cada viaje se lee entero)."""
        import threading
        import tiempos
        lista = list(self._viajes.items())

        def trabajo():
            cache = tiempos._leer_cache()
            cambio = False
            res = {}
            for iid, (ruta, _r) in lista:
                tr, c = tiempos.de_viaje(ruta, cache)
                res[iid] = tr
                cambio = cambio or c
            if cambio:
                tiempos.guardar_cache(cache)
            try:
                self.root.after(0, lambda: self._poner_tiempos(res))
            except Exception:  # noqa
                pass
        threading.Thread(target=trabajo, daemon=True).start()

    def _poner_tiempos(self, res):
        import tiempos
        self._tiempos = res
        todos = []
        for iid, trs in res.items():
            todos += trs
            try:
                txt = " + ".join(tiempos.mmss(t["total"]) + (" R" if t["modo"] == "rápido" else "") for t in trs) \
                    or "-"
                self.tv_viajes.set(iid, "duracion", txt)
            except Exception:  # noqa
                pass
        self._promedios = tiempos.promedios(todos)
        # último viaje (el más nuevo con algún trabajo completo)
        ult = next((trs[-1] for iid in self.tv_viajes.get_children() for trs in [res.get(iid) or []] if trs), None)
        lbl = getattr(self, "lbl_ultimo", None)
        if lbl is not None:
            lbl.config(text="Último viaje: -" if ult is None else
                       f"Último viaje: {ult['recorrido']} · {tiempos.mmss(ult['total'])} "
                       f"(ida {tiempos.mmss(ult['ida'])}, vuelta {tiempos.mmss(ult['vuelta'])}, modo {ult['modo']})")
        self._mostrar_tiempos()

    def _mostrar_tiempos(self):
        import tiempos
        sel = self.tv_viajes.selection()
        if not sel or not hasattr(self, "_tiempos"):
            return
        trs = self._tiempos.get(sel[0])
        if not trs:
            self.lbl_tiempos.config(text="Este viaje no tiene ningún trabajo completo (de «cargado» a «trabajo "
                                         "completado»), así que no tiene tiempo.")
            return
        partes = []
        for n, t in enumerate(trs, 1):
            prom = []
            for modo in ("normal", "rápido"):
                p = self._promedios.get((t["recorrido"], modo))
                if p:
                    prom.append(f"{modo} {tiempos.mmss(p[0])} ({p[1]} viaje{'s' if p[1] != 1 else ''})")
            pre = f"Trabajo {n}: " if len(trs) > 1 else ""
            partes.append(f"{pre}{t['recorrido']} en modo {t['modo']}: ida {tiempos.mmss(t['ida'])} · vuelta "
                          f"{tiempos.mmss(t['vuelta'])} · total {tiempos.mmss(t['total'])}.   Promedio de este "
                          f"recorrido: {', '.join(prom) or '-'}")
        self.lbl_tiempos.config(text="\n".join(partes))

    def _viaje_elegido(self):
        sel = self.tv_viajes.selection()
        if not sel:
            messagebox.showinfo("Viajes", "Elige un viaje de la lista.", parent=self.root)
            return None
        return self._viajes.get(sel[0])

    def ver_obs_viaje(self):
        v = self._viaje_elegido()
        if v is None:
            return
        ruta, r = v
        win = tk.Toplevel(self.root)
        win.title(f"Observaciones · {os.path.basename(ruta)}")
        win.configure(bg=self.T["bg"])
        win.geometry("860x480")
        txt = tk.Text(win, wrap="word", bg=self.T["log_bg"], fg=self.T["log_fg"], font=("Consolas", 10),
                      relief="flat", padx=8, pady=6)
        txt.pack(fill="both", expand=True)
        lineas = r["lineas"] or ["(Este viaje no tiene observaciones guardadas.)"]
        txt.insert("end", "\n".join(l.lstrip("# ") for l in lineas))
        txt.configure(state="disabled")

    def abrir_viaje(self):
        v = self._viaje_elegido()
        if v is not None:
            self.abrir_carpeta(v[0])

    # ------------------------------------------------------------ utilidades
    def _cargar_teclas(self):
        try:
            cfg = configuracion.cargar(CONFIG, guardar_migracion=False)
            t = cfg["teclas"]
            self.lbl_teclas.config(text=(
                f"En el juego: {t['activar']} activar · {t['modo_lento']} modo lento · "
                f"{t.get('carril', 'DELETE')} carril · {t['saltar_etapa']} saltar etapa · {t['salir']} detener · "
                f"{'/'.join(t['tomar_control'])} tomar el control · {t.get('hito', 'F9')} marcar hito"))
            self.lbl_control.config(text="Mando" if cfg["control"].get("backend") == "mando" else "Teclado")
        except Exception as e:  # noqa
            self.lbl_teclas.config(text=f"(no se pudo leer mi_equipo/config.json: {e})")
        self.lbl_usuario.config(text=self.var_usuario.get().strip() or "Sin usuario")

    def _comprobar_datos(self):
        info = carpetas.leer_json(carpetas.DATOS_INFO, {})
        v_datos = info.get("version", "?")
        minimo = info.get("programa_minimo")
        self.lbl_versiones.config(text=f"Programa {version.VERSION}  ·  Datos {v_datos}"
                                       + (f" (necesitan {minimo}+)" if minimo else ""))
        if not version.cumple(minimo):
            print(f"[!] Los datos ({v_datos}) necesitan el programa {minimo} o más nuevo; tienes "
                  f"{version.VERSION}. Actualiza la carpeta programa/.")

    def _comprobar_config(self):
        if not os.path.exists(CONFIG):
            print("[i] No hay mi_equipo/config.json todavía: se creará con valores por defecto. "
                  "Usa Calibración → Calibrar todo.")
            return
        try:
            cfg = configuracion.cargar(CONFIG)
            if cfg["minimapa"] == configuracion.DEFAULTS["minimapa"] and not cfg.get("calibracion"):
                print("[!] Todavía no calibraste: usa Calibración → Calibrar todo (es automático: solo revisas "
                      "los recuadros y confirmas).")
            elif not cfg.get("calibracion"):
                print("[i] Tu calibración se convertirá al formato 3.0.0 (relativa a la ventana del juego) la "
                      "próxima vez que actives el autopiloto con GTA abierto.")
            if cfg.get("carril", {}).get("activo") and not cfg["carril"].get("trapecio"):
                print("[i] El carril no está calibrado: usa 'Calibrar solo carril' (opcional).")
        except Exception as e:  # noqa
            print(f"[!] Error leyendo mi_equipo/config.json: {e}")

    def _escribir_log(self, texto):
        for linea in texto.splitlines(keepends=True):
            l = linea.strip()
            tag = None
            if l.startswith("[!]") or "Error" in l or "Traceback" in l:
                tag = "error" if ("Error" in l or "Traceback" in l) else "aviso"
            elif l.startswith("[i]") or l.startswith("[>]"):
                tag = "info"
            elif l.startswith("[OK]") or "Guardado" in l:
                tag = "ok"
            elif l.startswith("[REC]") or ("->" in l and l.startswith("[")):
                tag = "cambio"
            if tag:
                self.txt_log.insert("end", linea, tag)
            else:
                self.txt_log.insert("end", linea)
        if int(self.txt_log.index("end-1c").split(".")[0]) > 3000:
            self.txt_log.delete("1.0", "1000.0")
        self.txt_log.see("end")

    def copiar_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.txt_log.get("1.0", "end"))

    def _mostrar_imagen(self, label, img_bgr, clave):
        max_w = max(160, label.winfo_width() - 8)
        max_h = max(140, label.winfo_height() - 8)
        if clave == "carril" and clave not in self.ventanas:
            max_w = min(max_w, 260)                 # acoplada: columna angosta
        h, w = img_bgr.shape[:2]
        esc = min(max_w / w, max_h / h, 3.0)
        if esc <= 0:
            return
        img = cv2.resize(img_bgr, (max(1, int(w * esc)), max(1, int(h * esc))), interpolation=cv2.INTER_AREA)
        foto = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        self.fotos[clave] = foto                     # mantener referencia
        label.config(image=foto, text="")

    def _ocupado(self):
        return (self.hilo is not None and self.hilo.is_alive()) or \
               (self.hilo_tarea is not None and self.hilo_tarea.is_alive())

    def _botones(self):
        corriendo = self.hilo is not None and self.hilo.is_alive()
        tarea = self.hilo_tarea is not None and self.hilo_tarea.is_alive()
        estado = (corriendo, tarea, self.esperando_continuar)
        if estado == getattr(self, "_ult_botones", None):
            return
        self._ult_botones = estado
        self.btn_iniciar.config(state="disabled" if (corriendo or tarea) else "normal")
        self.btn_detener.config(state="normal" if corriendo else "disabled")
        for b in self.btns_ap:
            b.config(state="normal" if corriendo else "disabled")
        if self.btn_continuar is not None:
            self.btn_continuar.config(state="normal" if self.esperando_continuar else "disabled")
        if not corriendo:
            clave = "TAREA" if tarea else "DETENIDO"
            self.lbl_estado.config(text=ESTADOS[clave][0], bg=ESTADOS[clave][1])
            self._poner_avisos(None)
            self._estado_ult = None
            self.panel.reiniciar_override()

    def _pintar_barras(self, d, a, f):
        if not hasattr(self, "can"):
            return
        T = self.T
        for clave, valor, color in (("dir", d, T["azul"]), ("acel", a, T["verde"]), ("freno", f, T["rojo"])):
            c = self.can[clave]
            c.delete("all")
            w, h = 250, 12
            if clave == "dir":
                c.create_line(w / 2, 0, w / 2, h, fill=T["tenue"])
                x = w / 2 + max(-1.0, min(1.0, float(valor))) * w / 2
                c.create_rectangle(min(w / 2, x), 2, max(w / 2, x), h - 2, fill=color, width=0)
            else:
                c.create_rectangle(0, 2, max(0.0, min(1.0, float(valor))) * w, h - 2, fill=color, width=0)

    # ------------------------------------------------------------ bucle de la ventana
    def _bucle(self):
        try:
            n = 0
            while n < 200:
                self._escribir_log(self.cola_log.get_nowait())
                n += 1
        except queue.Empty:
            pass
        est, imgs = self.puente.tomar()
        if est is not None and self.hilo is not None and self.hilo.is_alive():
            self._actualizar_estado(est)
        if imgs:
            for nombre, clave in (("minimapa", "minimapa"), ("carril", "carril")):
                lbl = self._destino_imagen(nombre)
                if lbl is not None and imgs.get(clave) is not None:
                    self._mostrar_imagen(lbl, imgs[clave], nombre)
        self._botones()
        self._vigilar_panel(self.hilo is not None and self.hilo.is_alive())
        for _ in range(6):
            try:
                t, ti, tx = self.puente.avisos.get_nowait()
            except queue.Empty:
                break
            self.notificar(t, ti, tx)
        if not getattr(self, "_dialogo_abierto", False):
            try:
                self._preguntar_observaciones(self.puente.pedidos.get_nowait())
            except queue.Empty:
                pass
        self.root.after(60, self._bucle)

    def _poner_avisos(self, lista):
        """3.1.0: franja con los problemas de base que detectó el programa (mando, distancia, millas...)."""
        claves = tuple((p["clave"], p["nivel"]) for p in lista) if lista else None
        if claves == self._avisos_claves:
            return
        self._avisos_claves = claves
        for w in self.f_avisos.winfo_children():
            w.destroy()
        if not lista:
            self.f_avisos.pack_forget()
            return
        T = self.T
        ancho = max(300, self.root.winfo_width() - 70)
        for p in sorted(lista, key=lambda x: 0 if x["nivel"] == "problema" else 1):
            col = T["error"] if p["nivel"] == "problema" else T["aviso"]
            tk.Label(self.f_avisos, text="⚠  " + p["titulo"], bg=T["regla_bg"], fg=col, anchor="w",
                     font=("Segoe UI", 10, "bold")).pack(fill="x")
            tk.Label(self.f_avisos, text=p["texto"], bg=T["regla_bg"], fg=T["regla_fg"], anchor="w", justify="left",
                     wraplength=ancho, font=("Segoe UI", 9)).pack(fill="x", pady=(0, 4))
        self.f_avisos.configure(bg=T["regla_bg"])
        self.f_avisos.pack(fill="x", pady=(8, 0), before=self.f_diario)

    def _tecla_del_panel(self):
        ahora = time.monotonic()
        if ahora - getattr(self, "_t_cfg_panel", -99.0) > 3.0:
            self._t_cfg_panel = ahora
            try:
                self._nombre_panel = str(ventanas_extra._leer_teclas()[0].get("panel") or "F6").upper()
            except Exception:  # noqa
                self._nombre_panel = "F6"
        return getattr(self, "_nombre_panel", "F6")

    def _vigilar_panel(self, corriendo):
        """La tecla del panel (F6) lo prende o apaga; además se actualiza unas 4 veces por segundo."""
        vk = entrada.VK.get(self._tecla_del_panel())
        if vk is not None:
            p = entrada.tecla_pulsada(vk)
            if p and not self._tecla_panel:
                self.panel.alternar(corriendo)
            self._tecla_panel = p
        ahora = time.monotonic()
        if ahora - self._t_panel > 0.25:
            self._t_panel = ahora
            try:
                self.panel.refrescar(corriendo, self._estado_ult)
            except Exception as e:  # noqa
                print(f"[!] Panel flotante: {e}")
                self.panel.override = False

    def _actualizar_estado(self, e):
        self._estado_ult = e
        self._poner_avisos(e.get("problemas"))
        txt, col = ESTADOS.get(e["estado"], (e["estado"], "#555"))
        self.lbl_estado.config(text=txt, bg=col)
        self.lbl_recorrido.config(text=(e.get("recorrido") or "Sin recorrido")
                                  + (" (elegido)" if e.get("recorrido_elegido") else ""))
        if not e.get("recorrido_elegido") and self.var_recorrido.get() != AUTO_RECORRIDO \
                and getattr(self, "_elegido_visto", False):
            self.var_recorrido.set(AUTO_RECORRIDO)       # 3.2.5: terminó el trabajo: vuelve a automático
        self._elegido_visto = bool(e.get("recorrido_elegido"))
        self._guardar_sesion(e)
        self.lbl_etapa.config(text=e["etapa"])
        self.v_vel.config(text=f"{int(e['kmh'])} / {float(e['kmh_obj']):.0f}")
        self.v_dist.config(text=_km(e.get("metros")))
        cond = e.get("condicion")
        self.v_cond.config(text="-" if cond is None else f"{cond}%",
                           fg=self.T["texto"] if cond is None or cond >= 70 else
                           (self.T["aviso"] if cond >= 40 else self.T["error"]))
        self.v_motivo.config(text=(e.get("motivo") or "-").capitalize())
        lugar = " / ".join(x for x in (e.get("zona"), e.get("calle")) if x)
        self.lbl_lugar.config(text="Lugar: " + (lugar or "-"))
        regla = e.get("regla")
        self.lbl_regla.config(text=("Regla: " + regla) if regla else "")
        if regla:
            self.lbl_regla.pack(side="right")
        else:
            self.lbl_regla.pack_forget()
        self.lbl_pantalla.config(text=e.get("pantalla", ""))
        usuario = e.get("usuario")
        if usuario is not None:
            self.lbl_usuario.config(text=usuario or "Sin usuario")
        self.lbl_control.config(text=e.get("control", ""))
        self._pintar_barras(e["direccion"], e["acelerador"], e["freno"])
        T = self.T

        def ind(k, on, color):
            self.ind[k].config(fg="white" if on else T["tenue"], bg=color if on else T["panel2"])
        ind("lento", e["lento"], T["naranja"])
        ind("rapido", e.get("rapido", False), T["naranja"])
        if e["carril_usado"]:
            ind("carril", True, T["verde"])
        else:
            self.ind["carril"].config(fg=T["verde"] if e["carril_activo"] and e["carril_conf"] is not None
                                      else T["tenue"], bg=T["panel2"])
        ind("fuera", e["fuera_calle"], T["rojo"])
        ind("ruta", e["ruta"], T["azul"])
        r = "--" if e["rumbo"] is None else f"{e['rumbo']:+5.1f}°"
        dv = "--" if e["desvio"] is None else f"{e['desvio']:+5.1f}px"
        cu = "--" if e["curva"] is None else f"{e['curva']:+4.0f}°"
        cc = "--" if e["carril_conf"] is None else f"{e['carril_conf']:.2f}"
        self.lbl_info.config(text=f"rumbo {r}  desvío {dv}  curva {cu}\nvelocímetro "
                                  f"{'sí' if e['velocimetro'] else 'NO'}  conf. carril {cc}")

    # ------------------------------------------------------------ usuario y observaciones (v33)
    def _usuario_guardado(self):
        return (carpetas.leer_json(CONFIG).get("usuario") or "") if os.path.exists(CONFIG) else ""

    def _guardar_usuario(self):
        nombre = self.var_usuario.get().strip()
        self.lbl_usuario.config(text=nombre or "Sin usuario") if hasattr(self, "lbl_usuario") else None
        if nombre == self._usuario_guardado():
            return
        try:
            cfg = configuracion.cargar(CONFIG, guardar_migracion=False)
            cfg["usuario"] = nombre
            configuracion.guardar(cfg, CONFIG)
            print(f"[i] Usuario guardado: {nombre or '(sin nombre)'}")
        except Exception as e:  # noqa
            print(f"[!] No se pudo guardar el usuario: {e}")

    def _preguntar_observaciones(self, datos, modal=False):
        """Siempre pregunta; si dices que sí, muestra los puntos críticos con su causa probable."""
        if datos.get("_tipo") == "grabacion":
            self._ventana_grabacion(datos)
            return
        if not datos.get("archivo"):
            return
        n_h = sum(1 for p in datos["puntos"] if p.get("hito"))
        n = len(datos["puntos"]) - n_h
        que = "Terminó el trabajo" if datos["motivo"] == "trabajo terminado" else "Se detuvo el programa"
        txt = (f"{que}.\n\nPuntos críticos registrados: {n}."
               + (f"\nHitos que marcaste: {n_h} (si no escribes por qué, no se guardan)." if n_h else "")
               + "\n\n¿Quieres hacer observaciones de este viaje?")
        self._dialogo_abierto = True
        self.notificar("reporte", "¿Observaciones del viaje?",
                       f"{que}. {n} puntos críticos" + (f" y {n_h} hitos" if n_h else "") +
                       ". Responde en la ventana del programa.")
        try:
            si = messagebox.askyesno("Observaciones del viaje", txt, parent=self.root)
        finally:
            self._dialogo_abierto = False
        if si:
            self._ventana_observaciones(datos, modal)

    def _ventana_observaciones(self, datos, modal):
        self._dialogo_abierto = True
        win = tk.Toplevel(self.root)
        win.configure(bg=self.T["bg"])
        win.title("Observaciones del viaje")
        win.geometry("820x640")
        cab = ttk.Frame(win, padding=8)
        cab.pack(fill="x")
        ttk.Label(cab, text=f"Recorrido: {datos.get('recorrido') or '-'}", style="Titulo.TLabel").pack(anchor="w")
        fila_u = ttk.Frame(cab)
        fila_u.pack(fill="x", pady=(4, 0))
        ttk.Label(fila_u, text="Usuario:").pack(side="left")
        var_u = tk.StringVar(value=self.var_usuario.get())
        ttk.Entry(fila_u, textvariable=var_u, width=30).pack(side="left", padx=4)
        ttk.Label(cab, text="Puntos críticos (lo que vio el programa y la causa probable). "
                            "Escribe qué pasó de verdad si lo sabes:", wraplength=780).pack(anchor="w", pady=(6, 0))
        ttk.Label(cab, text="Ayuda mucho anotar: qué tocó o qué hizo mal (barrera, poste, cartel, auto, giró "
                            "antes/tarde…), de qué lado, desde dónde empezó (unos metros antes del hito, en la curva…) "
                            "y si fue por tráfico u otro jugador.", style="Tenue.TLabel",
                  wraplength=780, justify="left").pack(anchor="w", pady=(2, 0))
        marco = ttk.Frame(win)
        marco.pack(fill="both", expand=True, padx=8)
        lienzo = tk.Canvas(marco, highlightthickness=0, bg=self.T["bg"])
        barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        interior = ttk.Frame(lienzo)
        interior.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
        lienzo.create_window((0, 0), window=interior, anchor="nw")
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        entradas = []
        fotos = []                                   # referencias a las miniaturas (si no, Tk las borra)
        win._fotos = fotos
        if not datos["puntos"]:
            ttk.Label(interior, text="(No hubo choques, atascos, tomas de control ni hitos.)").pack(anchor="w", pady=6)
        n_critico = 0
        for p in datos["puntos"]:
            if not p.get("hito"):
                n_critico += 1
            i = p["hito"] if p.get("hito") else n_critico      # mismo número que en el reporte guardado
            titulo = f" ⚑ Hito {i} (lo marcaste tú) " if p.get("hito") else f" {i}. {p['que']} "
            caja = ttk.LabelFrame(interior, text=titulo, padding=6)
            caja.pack(fill="x", pady=3)
            lugar = " / ".join(x for x in (p.get("zona"), p.get("calle")) if x) or "-"
            dist = _km(p.get("metros"))
            ttk.Label(caja, text=f"t={p['t']:.0f} s · tramo {p['tramo']} · {dist} al punto · {lugar} · "
                                 f"{p.get('kmh', 0)} km/h" + (f" · regla: {p['regla']}" if p.get("regla") else ""),
                      wraplength=740).pack(anchor="w")
            if p.get("causa"):
                tk.Label(caja, text="Causa probable: " + p["causa"], fg=self.T["morado"], bg=self.T["panel"], wraplength=740,
                         justify="left").pack(anchor="w")
            if p.get("capturas"):
                self._miniaturas(caja, p, i, datos, fotos)
            v = tk.StringVar()
            sel = {}                                  # 2.5.4: selecciones rápidas (qué pasó, lado, causa)
            fila_s = ttk.Frame(caja)
            fila_s.pack(fill="x", pady=(3, 0))
            for clave, etiqueta, opciones, ancho in OBS_RAPIDAS:
                ttk.Label(fila_s, text=etiqueta).pack(side="left", padx=(0, 2))
                sv = tk.StringVar(value="")
                ttk.Combobox(fila_s, textvariable=sv, values=("",) + opciones, state="readonly",
                             width=ancho).pack(side="left", padx=(0, 8))
                sel[clave] = sv
            fila = ttk.Frame(caja)
            fila.pack(fill="x", pady=(3, 0))
            ttk.Label(fila, text="¿Por qué lo marcaste?" if p.get("hito") else "Tu observación:").pack(side="left")
            ttk.Entry(fila, textvariable=v).pack(side="left", fill="x", expand=True, padx=4)
            entradas.append((p, v, sel))
        ttk.Label(win, text="Observación general:", padding=(8, 4, 8, 0)).pack(anchor="w")
        txt = tk.Text(win, height=4, wrap="word", bg=self.T["campo"], fg=self.T["texto"],
                      insertbackground=self.T["texto"], relief="flat", highlightthickness=1,
                      highlightbackground=self.T["borde"])
        txt.pack(fill="x", padx=8)
        botones = ttk.Frame(win, padding=8)
        botones.pack(fill="x")

        def limpio(t):
            return " ".join(str(t).replace("|", "/").split())

        def guardar():
            usuario = var_u.get().strip()
            if usuario != self.var_usuario.get().strip():
                self.var_usuario.set(usuario)
                self._guardar_usuario()
            lineas = [f"# === OBSERVACIONES ({datos['motivo']}) {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n",
                      f"# usuario: {limpio(usuario) or '(sin nombre)'}\n",
                      f"# recorrido: {limpio(datos.get('recorrido') or '-')}\n"]
            n_punto = 0
            for p, v, sel in entradas:
                lugar = " / ".join(x for x in (p.get("zona"), p.get("calle")) if x) or "-"
                dist = _km(p.get("metros"))
                caps = " | capturas: " + ", ".join(p["_guardadas"]) if p.get("_guardadas") else ""
                rapidas = "".join(f"{etq.rstrip(':').lower()}: {sel[c].get()} | "
                                  for c, etq, _o, _a in OBS_RAPIDAS if sel[c].get())
                if p.get("hito"):                    # 2.3.0: un hito sin explicación no se guarda
                    if limpio(v.get()) or rapidas:
                        lineas.append(f"# hito {p['hito']}: t={p['t']:.1f} s | tramo {p['tramo']} | {dist} | "
                                      f"{limpio(lugar)} | {p.get('kmh', 0)} km/h | estado {p.get('estado', '-')} | "
                                      f"regla: {limpio(p.get('regla') or '-')} | {rapidas}"
                                      f"observación: {limpio(v.get()) or '-'}{caps}\n")
                    continue
                n_punto += 1
                i = n_punto
                lineas.append(f"# punto {i}: t={p['t']:.1f} s | tramo {p['tramo']} | {dist} | {limpio(lugar)} | "
                              f"{p.get('kmh', 0)} km/h | {limpio(p['que'])} | causa probable: {limpio(p.get('causa', ''))} | "
                              f"{rapidas}observación: {limpio(v.get()) or '-'}{caps}\n")
            gen = limpio(txt.get("1.0", "end"))
            lineas.append(f"# observación general: {gen or '-'}\n")
            ap = datos.get("ap")
            if ap is not None and not getattr(ap, "terminado", False):
                ap.escribir_observaciones(lineas)     # el programa sigue: lo escribe su hilo
            else:
                try:
                    with open(datos["archivo"], "a", encoding="utf-8") as fh:
                        fh.writelines(lineas)
                except Exception as e:  # noqa
                    print(f"[!] No se pudieron guardar las observaciones: {e}")
                    return
            print(f"[OK] Observaciones guardadas en {datos['archivo']}")
            self.notificar("reporte", "Reporte guardado", os.path.basename(datos["archivo"]))
            cerrar_win()

        def cerrar_win():
            self._dialogo_abierto = False
            win.destroy()
            try:                                   # 2.7.0: actualizar tiempos y «último viaje»
                self.root.after(300, self.cargar_lista_viajes)
            except Exception:  # noqa
                pass

        ttk.Button(botones, text="Guardar observaciones", style="Grande.TButton", command=guardar).pack(side="right")
        ttk.Button(botones, text="No guardar", command=cerrar_win).pack(side="right", padx=6)
        win.protocol("WM_DELETE_WINDOW", cerrar_win)
        if modal:
            win.transient(self.root)
            win.grab_set()
            self.root.wait_window(win)

    # ------------------------------------------------------------ capturas de incidentes (2.2.0)
    ETIQ_CAPTURA = {"antes3": "3 s antes", "antes": "1,5 s antes", "momento": "En el momento",
                    "despues": "1 s después", "minimapa": "Minimapa (tamaño real)", "detector": "Lo que vio el programa"}

    def _guardar_captura(self, p, i, datos, etiqueta, ruta, boton=None):
        """Copia una captura temporal a viajes/capturas/ (junto al CSV del viaje) para conservarla."""
        try:
            carpeta = os.path.join(os.path.dirname(os.path.abspath(datos["archivo"])), "capturas")
            os.makedirs(carpeta, exist_ok=True)
            base = os.path.splitext(os.path.basename(datos["archivo"]))[0]
            nombre = f"{base}_{'hito' + str(p['hito']) if p.get('hito') else 'punto' + str(i)}_{etiqueta}.jpg"
            shutil.copy2(ruta, os.path.join(carpeta, nombre))
        except Exception as e:  # noqa
            messagebox.showerror("Captura", f"No se pudo guardar la captura:\n{e}")
            return
        p.setdefault("_guardadas", [])
        if nombre not in p["_guardadas"]:
            p["_guardadas"].append(nombre)
        print(f"[OK] Captura guardada: viajes/capturas/{nombre}")
        for b in (boton, getattr(self, "_boton_captura_grande", None)):
            try:
                if b is not None and b.winfo_exists() and getattr(b, "_ruta", ruta) == ruta:
                    b.config(text="Guardada ✓", state="disabled")
            except tk.TclError:
                pass

    def _miniaturas(self, caja, p, i, datos, fotos):
        fila = ttk.Frame(caja)
        fila.pack(fill="x", pady=(4, 0))
        for etiqueta, ruta in p["capturas"]:
            col = ttk.Frame(fila)
            col.pack(side="left", padx=(0, 8))
            ttk.Label(col, text=self.ETIQ_CAPTURA.get(etiqueta, etiqueta)).pack(anchor="w")
            if not os.path.exists(ruta):
                ttk.Label(col, text="(no alcanzó a tomarse)", width=26).pack(anchor="w", pady=20)
                continue
            try:
                im = Image.open(ruta)
                im.thumbnail((224, 126))
                foto = ImageTk.PhotoImage(im)
            except Exception:  # noqa
                ttk.Label(col, text="(no se pudo abrir)").pack(anchor="w")
                continue
            fotos.append(foto)
            lbl = tk.Label(col, image=foto, cursor="hand2", bd=1, relief="solid", bg=self.T["borde"])
            lbl.pack(anchor="w")
            b = ttk.Button(col, text="Guardar esta captura")
            b._ruta = ruta
            b.config(command=lambda e=etiqueta, r=ruta, b=b: self._guardar_captura(p, i, datos, e, r, b))
            b.pack(anchor="w", pady=(2, 0))
            self._ayuda(b, "Copia esta captura a viajes/capturas/, junto al archivo del viaje. Las que no "
                           "guardes se borran al cerrar el programa.")
            lbl.bind("<Button-1>", lambda _e, e=etiqueta, r=ruta, b=b: self._ver_captura(p, i, datos, e, r, b))
            self._ayuda(lbl, "Clic para verla en grande.")

    def _ver_captura(self, p, i, datos, etiqueta, ruta, boton):
        win = tk.Toplevel(self.root)
        win.configure(bg=self.T["bg"])
        win.title(f"Punto {i}: {p['que']} · {self.ETIQ_CAPTURA.get(etiqueta, etiqueta)}")
        try:
            im = Image.open(ruta)
            maxw = min(1280, win.winfo_screenwidth() - 80)
            maxh = min(760, win.winfo_screenheight() - 160)
            im.thumbnail((maxw, maxh))
            foto = ImageTk.PhotoImage(im)
        except Exception as e:  # noqa
            win.destroy()
            messagebox.showerror("Captura", f"No se pudo abrir la captura:\n{e}")
            return
        win._foto = foto
        tk.Label(win, image=foto, bg=self.T["bg"]).pack(padx=8, pady=8)
        barra = ttk.Frame(win, padding=(8, 0, 8, 8))
        barra.pack(fill="x")
        b = ttk.Button(barra, text="Guardar esta captura")
        b._ruta = ruta
        b.config(command=lambda: self._guardar_captura(p, i, datos, etiqueta, ruta, boton))
        b.pack(side="right")
        if boton is not None and str(boton.cget("state")) == "disabled":
            b.config(text="Guardada ✓", state="disabled")
        self._boton_captura_grande = b
        ttk.Button(barra, text="Cerrar", command=win.destroy).pack(side="right", padx=6)

    def _ventana_grabacion(self, datos):
        """Nombre, disparo y qué hacer al terminar para una grabación recién hecha."""
        g, ap = datos["grab"], datos.get("ap")
        self._dialogo_abierto = True
        win = tk.Toplevel(self.root)
        win.configure(bg=self.T["bg"])
        win.title("Guardar grabación")
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        rec = g.get("recorrido") or "(cualquiera)"
        ttk.Label(f, text=f"Duración {g['duracion']:.1f} s · recorrido: {rec} · tramo {g.get('tramo')} · "
                          f"empezó a {_km(g.get('metros_inicio'))} del punto", wraplength=460).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Nombre:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        var_n = tk.StringVar(value=f"{rec} - tramo {g.get('tramo')}" if g.get("recorrido") else "")
        ttk.Entry(f, textvariable=var_n, width=40).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(f, text="Cuándo repetirla:").grid(row=2, column=0, sticky="nw", pady=(8, 0))
        var_d = tk.StringVar(value="distancia")
        fd = ttk.Frame(f)
        fd.grid(row=2, column=1, sticky="w", pady=(8, 0))
        m0 = g.get("metros_inicio")
        ttk.Radiobutton(fd, text=f"Al llegar a {_km(m0)} del punto (donde empezaste a grabar)",
                        variable=var_d, value="distancia").pack(anchor="w")
        ttk.Radiobutton(fd, text="Justo después de \"camión CARGADO\"", variable=var_d, value="cargado").pack(anchor="w")
        ttk.Radiobutton(fd, text="Justo después de \"camión DESCARGADO\" (salida del punto A, hacia adelante o en reversa)",
                        variable=var_d, value="descargado").pack(anchor="w")
        ttk.Radiobutton(fd, text=f"Punto final de la vuelta, al llegar a {_km(m0)} (vale para todos los recorridos)",
                        variable=var_d, value="final").pack(anchor="w")
        ttk.Radiobutton(fd, text="Trazado: no repetir teclas; ir por el mismo lado de la calle que yo, metro a "
                                 "metro (farolas, postes)", variable=var_d, value="trazado").pack(anchor="w")
        ttk.Label(f, text="Al terminar:").grid(row=3, column=0, sticky="nw", pady=(8, 0))
        var_t = tk.StringVar(value="seguir")
        ft = ttk.Frame(f)
        ft.grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(ft, text="Seguir conduciendo con el GPS", variable=var_t, value="seguir").pack(anchor="w")
        ttk.Radiobutton(ft, text="Parar y dejarme el control", variable=var_t, value="parar").pack(anchor="w")
        ttk.Label(f, text="Tramo:").grid(row=6, column=0, sticky="nw", pady=(8, 0))
        var_tr = tk.StringVar(value=str(g.get("tramo", 1)))
        ftr = ttk.Frame(f)
        ftr.grid(row=6, column=1, sticky="w", pady=(8, 0))
        for val, txt in (("0", "Camino a cargar"), ("1", "Ida (hacia el punto A)"), ("2", "Vuelta (hacia el punto B)")):
            ttk.Radiobutton(ftr, text=txt, variable=var_tr, value=val).pack(side="left", padx=(0, 8))
        var_todos = tk.BooleanVar(value=not g.get("recorrido"))
        ttk.Checkbutton(f, text="Vale para cualquier recorrido (no solo " + rec + ")", variable=var_todos).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        bot = ttk.Frame(f)
        bot.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def cerrar_win():
            self._dialogo_abierto = False
            win.destroy()

        def guardar():
            nombre = var_n.get().strip()
            if not nombre:
                messagebox.showwarning("Grabación", "Ponle un nombre.", parent=win)
                return
            g["nombre"] = nombre
            tipo = var_d.get()
            if tipo == "trazado":
                g["tramo"] = int(var_tr.get())
                if var_todos.get():
                    g["recorrido"] = ""
                try:
                    if ap is not None:
                        ok = ap.agregar_trazado(g)
                    else:
                        import grabaciones
                        t = grabaciones.construir_trazado(g)
                        ok = t is not None and bool(grabaciones.guardar_trazado(dict(t, nombre=nombre)))
                except Exception as e:  # noqa
                    messagebox.showerror("Trazado", f"No se pudo guardar: {e}", parent=win)
                    return
                if not ok:
                    mot = getattr(ap, "ultimo_motivo_trazado", None) if ap is not None else None
                    messagebox.showwarning("Trazado", "No se guardó el trazado: " + (mot or "no hubo datos "
                                           "suficientes") + ".\n\nEl trazado solo sirve en calles donde se ve la "
                                           "ruta del GPS. Para la granja o lugares sin calle, guarda la grabación "
                                           "con otra opción (repetir teclas).", parent=win)
                    return
                cerrar_win()
                return
            g["disparo"] = {"tipo": tipo}
            if tipo in ("distancia", "final"):
                g["disparo"]["metros"] = m0 if m0 is not None else 0
            if tipo == "final":
                g["tramo"] = 2
            g["al_terminar"] = var_t.get()
            g["tramo"] = int(var_tr.get())
            if tipo == "cargado":
                g["tramo"] = 1          # tras cargar empieza la ida
            elif tipo in ("descargado", "final"):
                g["tramo"] = 2          # tras descargar empieza la vuelta
            if var_todos.get() or tipo == "final":
                g["recorrido"] = ""
            try:
                if ap is not None:
                    ap.agregar_grabacion(g)
                else:
                    import grabaciones
                    grabaciones.guardar(g)
            except Exception as e:  # noqa
                messagebox.showerror("Grabación", f"No se pudo guardar: {e}", parent=win)
                return
            cerrar_win()

        ttk.Button(bot, text="Guardar", style="Grande.TButton", command=guardar).pack(side="right")
        ttk.Button(bot, text="Descartar", command=cerrar_win).pack(side="right", padx=6)
        f.columnconfigure(1, weight=1)
        win.protocol("WM_DELETE_WINDOW", cerrar_win)

    # ------------------------------------------------------------ acciones
    def iniciar_programa(self):
        if self._ocupado():
            return
        self._guardar_usuario()
        tramo = TRAMOS.index(self.var_tramo.get()) if self.var_tramo.get() in TRAMOS else 0
        log = None
        if self.var_csv.get():
            log = os.path.join(carpetas.VIAJES, f"viaje_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")

        def trabajo():
            try:
                import autopiloto
                import entrada
                if not entrada.ES_WINDOWS:
                    print("[!] El modo en vivo solo funciona en Windows. Usa 'Probar con video o imagen'.")
                    return
                cfg = configuracion.cargar(CONFIG)
                self.ap = autopiloto.Autopiloto(cfg, tramo, self.var_debug.get(), log, interfaz=self.puente)
                arch = self._archivo_recorrido()
                if arch:
                    self.ap.comandos.put(f"recorrido:{arch}")
                if log:
                    print(f"[i] Guardando el viaje en {os.path.relpath(log, carpetas.RAIZ)}")
                self.ap.ejecutar()
            except SystemExit as e:              # p. ej. tecla mal escrita en config.json
                print(f"[!] {e}")
            except Exception:
                print("[!] Error en el autopiloto:\n" + traceback.format_exc())
                self.puente.notificar("problema", "Error en el autopiloto", "Mira el registro del programa.")
            finally:
                self.ap = None

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def detener(self):
        if self.ap is not None:
            self.ap.parar.set()

    def orden(self, cmd):
        if self.ap is not None:
            self.ap.comandos.put(cmd)

    @staticmethod
    def _lista_recorridos():
        try:
            import rutas
            d = rutas.cargar()
            out = []
            for r in d.get("rutas", []):
                n = r.get("nombre") or r.get("_archivo")
                if r.get("cargamento"):
                    n = f"{n} ({r['cargamento']})"
                out.append((n, r.get("_archivo")))
            return sorted(out)
        except Exception as e:  # noqa
            print(f"[!] No se pudo leer la lista de recorridos: {e}")
            return []

    def _archivo_recorrido(self):
        return dict(self.recorridos).get(self.var_recorrido.get())

    def cambiar_recorrido(self, _evt=None):
        if self.ap is not None:
            self.ap.comandos.put(f"recorrido:{self._archivo_recorrido() or ''}")

    def cambiar_tramo(self, _evt=None):
        if self.ap is not None and self.var_tramo.get() in TRAMOS:
            self.ap.comandos.put(f"tramo:{TRAMOS.index(self.var_tramo.get())}")

    def cambiar_debug(self):
        if self.ap is not None:
            self.ap.comandos.put("debug")

    # -- calibración: corre en su propio hilo con las ventanas de OpenCV
    def _esperar_continuar(self):
        self.evento_continuar.clear()
        self.esperando_continuar = True
        self.evento_continuar.wait()
        self.esperando_continuar = False

    def continuar(self):
        self.evento_continuar.set()

    def calibrar(self, solo, imagen=None):
        if self._ocupado():
            messagebox.showinfo("Autopiloto", "Detén el programa (o la prueba) antes de calibrar.")
            return

        def trabajo():
            try:
                import calibrar as cal
                print(f"\n[i] Calibración {'del carril' if solo == 'carril' else 'completa'}"
                      f"{' desde ' + imagen if imagen else ''}")
                if not imagen:
                    print("[i] Ve al juego y pulsa F11 para capturar la pantalla. Después vuelve aquí "
                          "y pulsa 'Continuar'.")
                    self.notificar("calibracion", "Calibración: pulsa F11 en el juego",
                                   "Después vuelve al programa y pulsa Continuar.")
                cal.calibrar(CONFIG, solo=solo, imagen=imagen, continuar=self._esperar_continuar)
                print("[OK] Calibración terminada.")
                self.notificar("calibracion", "Calibración terminada", "Se guardó en mi_equipo/config.json.")
            except Exception:
                print("[!] Error en la calibración:\n" + traceback.format_exc())
                self.notificar("problema", "Error en la calibración", "Mira el registro del programa.")
            finally:
                try:
                    cv2.destroyAllWindows()
                except Exception:
                    pass
                self.esperando_continuar = False
                self.root.after(0, self._cargar_teclas)

        self.hilo_tarea = threading.Thread(target=trabajo, daemon=True)
        self.hilo_tarea.start()

    def calibrar_imagen(self):
        ruta = filedialog.askopenfilename(title="Captura de pantalla del juego",
                                          filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.bmp")])
        if not ruta:
            return
        solo = "carril" if messagebox.askyesno("Calibrar desde imagen",
                                               "¿Calibrar SOLO el carril?\n(No = calibración completa)") else None
        self.calibrar(solo, ruta)

    def probar(self):
        if self._ocupado():
            messagebox.showinfo("Autopiloto", "Detén el programa antes de probar con un video.")
            return
        ruta = filedialog.askopenfilename(title="Video o captura del juego",
                                          filetypes=[("Videos e imágenes", "*.mp4 *.avi *.mkv *.mov *.png *.jpg *.jpeg"),
                                                     ("Todos", "*.*")])
        if not ruta:
            return
        self.parar_prueba.clear()

        def trabajo():
            try:
                import autopiloto
                cfg = configuracion.cargar(CONFIG)
                print(f"\n[i] Probando con {os.path.basename(ruta)} (pulsa 'Detener prueba' para parar)")
                autopiloto.simular(cfg, ruta, mostrar=self.puente.imagenes, parar=self.parar_prueba)
                print("[OK] Prueba terminada.")
            except Exception:
                print("[!] Error en la prueba:\n" + traceback.format_exc())

        self.hilo_tarea = threading.Thread(target=trabajo, daemon=True)
        self.hilo_tarea.start()

    def medir_zona_muerta(self):
        if self._ocupado():
            messagebox.showinfo("Autopiloto", "Detén el programa antes de medir la zona muerta.")
            return
        if not messagebox.askokcancel(
                "Medir zona muerta del mando",
                "Pon el camión PARADO en un sitio ABIERTO y llano (p. ej. un estacionamiento grande), "
                "en primera persona.\n\nAl pulsar Aceptar tendrás 5 segundos para volver al juego. "
                "El camión avanzará despacio haciendo pequeños giros (~1 minuto).\n\n"
                "Pulsa S o ESPACIO en el juego para cancelar."):
            return
        self.parar_prueba.clear()

        def trabajo():
            try:
                import zona_muerta
                zona_muerta.medir(CONFIG, parar=self.parar_prueba)
            except Exception:
                print("[!] Error midiendo la zona muerta:\n" + traceback.format_exc())

        self.hilo_tarea = threading.Thread(target=trabajo, daemon=True)
        self.hilo_tarea.start()

    def editar_config(self):
        if not os.path.exists(CONFIG):
            configuracion.cargar(CONFIG)
        try:
            carpetas.abrir(CONFIG)
            print("[i] Los cambios en config.json se aplican al volver a iniciar el programa.")
        except Exception as e:  # noqa
            print(f"[!] No se pudo abrir config.json: {e}")

    def abrir_carpeta(self, ruta):
        try:
            os.makedirs(ruta, exist_ok=True) if not os.path.splitext(ruta)[1] else None
            carpetas.abrir(ruta)
        except Exception as e:  # noqa
            print(f"[!] No se pudo abrir {ruta}: {e}")

    def cerrar(self):
        self.detener()
        self.parar_prueba.set()
        self.evento_continuar.set()
        if self.hilo is not None:
            self.hilo.join(timeout=2)
        while True:                           # v33: preguntar por las observaciones antes de cerrar
            try:
                datos = self.puente.pedidos.get_nowait()
            except queue.Empty:
                break
            self._preguntar_observaciones(datos, modal=True)
        try:
            self.prefs["geometria"][self._vista] = self.root.geometry()
            for nombre, (win, _l) in self.ventanas.items():
                self.prefs["geometria"]["ventana_" + nombre] = win.geometry()
            self.guardar_prefs()
        except Exception:  # noqa
            pass
        carpetas.limpiar_capturas()       # 2.2.0: las capturas de incidentes no se acumulan
        self.panel.cerrar()
        try:
            self.archivo_log.close()
        except Exception:
            pass
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

"""
Autopiloto de camión para GTA V RP (v2: control por velocímetro).

Uso:
    python autopiloto.py                 # modo normal
    python autopiloto.py --debug         # + ventana con lo que "ve" el programa
    python autopiloto.py --tramo 2       # empezar desde el tramo 2 (si reiniciaste a mitad)
    python autopiloto.py --log viaje.csv # guarda datos para ajustar
    python autopiloto.py --simular captura.png|video.mp4|carpeta   # probar sin juego

Teclas por defecto (cámbialas en config.json -> "teclas"):
    INSERT   activar / desactivar autopiloto
    RE PÁG   modo lento ON/OFF (antes del puente estrecho)
    AV PÁG   saltar a la siguiente etapa
    FIN      salir
    S o ESPACIO -> tomas el control y el autopiloto se desactiva
"""
import argparse
import collections
import math
import os
import queue
import sys
import threading
import time

import cv2
import numpy as np

import configuracion
import entrada
import vision
from configuracion import interpolar


def _f(x):
    return "" if x is None else f"{x:.1f}"


def _txt(x):
    return "" if not x else '"' + str(x).replace('"', "'") + '"'

ETAPAS = {
    1: "Contratar (manual)",
    2: "Ir a cargar",
    3: "Cargar (elige la mercancía en el menú)",
    4: "Ir al punto de entrega A",
    5: "Descargando camión...",
    6: "Volver a la zona de trabajo B",
    7: "Terminar",
}
ETAPA_TRAMO = {0: 2, 1: 4, 2: 6}
ETAPA_ESPERA = {0: 3, 1: 5, 2: 7}


def _mediana(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _km(m):
    """'1,70 km' desde 1 km, '740 m' por debajo (como el minimapa)."""
    if m is None:
        return "-"
    return f"{float(m) / 1000:.2f} km".replace(".", ",") if float(m) >= 1000 else f"{float(m):.0f} m"


class Autopiloto:
    def __init__(self, cfg, tramo_inicial=0, debug=False, log=None, interfaz=None):
        self.cfg = cfg
        # 3.0.0: posiciones según la ventana del juego (y minimapa en la unidad fija de las reglas)
        import geometria
        import ventana
        rect = geometria.preparar(cfg)
        self.vigia = ventana.Vigia(cfg.get("ventana_juego") or "Grand Theft Auto")
        self.vigia.rect = rect
        if rect is None and ventana.ES_WINDOWS:
            print("[!] No encontré la ventana del juego: uso las últimas posiciones guardadas. Abre GTA antes "
                  "que el autopiloto para que se ajuste solo a la ventana.")
        self.ui = interfaz                    # interfaz gráfica (None = consola)
        self.ruta_config = cfg.get("_ruta", "mi_equipo/config.json")
        self.comandos = queue.Queue()         # órdenes de los botones de la interfaz
        self.parar = threading.Event()
        c = cfg["control"]
        self.ctrl = entrada.crear_control(c["backend"], c["periodo_pwm"], c.get("mando_zona_muerta", 0.0))
        import salud                          # 3.1.0: avisos de problemas de base
        self.salud = salud.Salud(c["backend"], self.ctrl.nombre)
        self.problemas = []
        self.debug = debug
        self.log = open(log, "w", encoding="utf-8") if log else None
        if self.log:
            import version
            datos_v = "?"
            try:
                import carpetas
                datos_v = carpetas.leer_json(carpetas.DATOS_INFO).get("version", "?")
            except Exception:  # noqa
                pass
            self.log.write(f"# programa: {version.VERSION}\n# datos: {datos_v}\n"
                           f"# usuario: {(cfg.get('usuario') or '').strip() or '(sin nombre)'}\n"
                           f"# inicio: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log.write("t,estado,tramo,kmh,kmh_obj,rumbo,desvio,giro_adelante,"
                           "direccion,acelerador,freno,en_calle,calle_corr,gps_fuera,motivo,modo_lento,"
                           "carril_desvio,carril_conf,carril_usado,marcador_dist,marcador_ang,fin_ruta,largo_ruta,"
                           "dist_punto_m,flecha,cardinal,zona,calle,evento,bifurcacion,desvio_cerca,desplazamiento,condicion,ruta,regla,"
                           "rumbo_abs,rumbo_fuente,yolo_accion,yolo_objeto,yolo_dist,yolo_ttc,yolo_n\n")
        # incidentes (choques, maniobras, desactivaciones...) con el lugar, en un archivo acumulado
        self.ruta_incidentes = os.path.join(os.path.dirname(os.path.abspath(log)) if log else "viajes",
                                            "incidentes.csv")
        self.evento = ""
        self.puntos = []                      # v33: puntos críticos del viaje (para las observaciones)
        self.cola_obs = queue.Queue()
        self.usuario = (cfg.get("usuario") or "").strip()
        self.hud = None
        if cfg.get("hud_texto", {}).get("activo", True):
            try:
                import hud_texto
                self.hud = hud_texto.MonitorHud(cfg)
            except Exception as e:  # noqa
                print(f"[!] Lectura de textos del HUD desactivada ({e})")

        self.vel = None
        if cfg["velocimetro"]["activo"]:
            try:
                import velocimetro
                self.vel = velocimetro.Velocimetro(cfg["velocimetro"])
            except Exception as e:  # noqa
                print(f"[!] Velocímetro desactivado ({e}). Uso acelerador fijo.")

        self.integral_lat = 0.0
        self.desp_f = 0.0                     # desplazamiento lateral deseado (filtrado), px
        self.recto = None                     # tras chocar girando: avanzar recto unos metros
        self.choques_giro = []
        self.hist_volante = []
        self.aprox = False                    # yendo directo al marcador de destino
        self.t_aprox_visto = 0.0
        self.t_en_marcador = None
        self.t_recta_larga_desde = None
        self.conf_reset()
        # v29: rutas conocidas y reglas por lugar
        try:
            import rutas
            self.rutas_mod = rutas
            self.rutas = rutas.cargar()
            if self.rutas.get("_archivo"):
                print(f"[i] Reglas por lugar: {len(self.rutas.get('rutas', []))} rutas conocidas ({self.rutas['_archivo']}).")
        except Exception as e:  # noqa
            self.rutas_mod, self.rutas = None, {"rutas": [], "regreso_comun": []}
        self.ruta_act = None
        self.ruta_elegida = None              # 3.2.5: recorrido elegido a mano (archivo de datos/rutas)
        self.regla = None
        self._tramo_visto = None
        # v38: grabaciones de recorridos (entrada a granjas, reversa, punto final)
        import grabaciones
        self.grab_mod = grabaciones
        self.grabs = grabaciones.cargar_todas() if cfg.get("experimental", {}).get("usar_grabaciones", True) else []
        if self.grabs:
            print(f"[i] Grabaciones de recorridos: {len(self.grabs)} ({', '.join(g.get('nombre', '?') for g in self.grabs)}).")
        self.grabadora = grabaciones.Grabadora(lambda n: entrada.tecla_pulsada(entrada.VK[n]))
        self.trazados = grabaciones.cargar_trazados()
        if self.trazados:
            print(f"[i] Trazados: {len(self.trazados)} ({', '.join(t.get('nombre', '?') for t in self.trazados)}).")
        self.traz = None                       # (desplazamiento_px, kmh, trazado) activo ahora
        self.odo = 0.0                         # metros recorridos (para afinar la distancia del HUD)
        self._hud_m = None
        self._est = None
        self._est_odo = 0.0
        self.grab_hecha = set()
        self.lim_grab = None
        self.repro = None
        self.grab_pendiente = None
        self.grab_final_hecha = None
        self.ruta_buscar_desde = None
        self.pantalla = {"menu": False, "barra": False, "progreso": None}
        self.t_pantalla = 0.0
        self.sct_pantalla = None
        self.capturas = collections.deque(maxlen=14)     # 2.2.0: (t, jpg) de los últimos ~6 s de pantalla
        self.capturas_pend = []                          # (t_objetivo, ruta) para la captura "después"
        self.n_captura = 0
        self.carril = None
        self.res_carril = None
        self.sesgo_carril = float(cfg.get("carril", {}).get("sesgo", 0.0))
        self.muestras_sesgo = 0
        self.usar_carril = True
        cc = cfg.get("carril", {})
        if cc.get("activo") and cc.get("trapecio"):
            try:
                import carril
                self.carril = carril.DetectorCarrilIPM(cc)
            except Exception as e:  # noqa
                print(f"[!] Detección de carril desactivada ({e})")
        elif cc.get("activo"):
            print("[i] Carril sin calibrar: ejecuta  python calibrar.py --solo carril")
        # 3.6.0: YOLO en modo sombra (no maneja: muestra y anota lo que habría hecho)
        self.yolo = None
        self.yolo_est = {}
        self._yolo_accion_ant = "nada"
        if (cfg.get("yolo") or {}).get("activo", True) and cfg.get("experimental", {}).get("yolo", True):
            try:
                import vision_yolo
                hay, txt = vision_yolo.disponible()
                if hay:
                    self.yolo = vision_yolo.VigiaYolo(cfg)
                    if self.yolo.error:
                        print(f"[i] YOLO: {self.yolo.error}")
                    self.yolo.iniciar()
                else:
                    print(f"[i] {txt}")
            except Exception as e:  # noqa
                print(f"[i] YOLO desactivado ({e})")
                self.yolo = None

        self.estado = "INACTIVO"
        self.fuera_de_calle = False
        self.t_estado = time.time()
        self.tramo = tramo_inicial
        self.modo_lento = False
        self.modo_rapido = False                          # 2.6.0; fijo desde la 3.4.0
        self.direccion = 0.0
        self.err_prev = None
        self.deriv = 0.0
        self.int_vel = 0.0
        self.kmh = 0
        self.kmh_obj = 0
        self.ang_previo = 0.0
        self.t_ultima_ruta = 0.0
        self.t_ruta_visible_desde = None
        self.t_quieto_desde = None
        self.gris_ref, self.t_gris_ref, self.mov = None, 0.0, 999.0
        self.t0 = time.time()

        t = cfg["teclas"]
        t.setdefault("hito", "F9")
        t.setdefault("modo_rapido", "F10")
        t.setdefault("grabar", "F5")                      # 3.5.0 (F7 oculta el HUD)
        for campo in ("activar", "modo_lento", "saltar_etapa", "salir", "carril", "hito", "modo_rapido", "grabar"):
            t[campo] = entrada.validar_tecla(t.get(campo, "DELETE"), campo)
        t["tomar_control"] = [entrada.validar_tecla(k, "tomar_control") for k in t["tomar_control"]]
        self.hotkeys = entrada.Hotkeys([t["activar"], t["modo_lento"], t["saltar_etapa"], t["salir"], t["carril"],
                                        t["hito"], t["modo_rapido"], t["grabar"]])

    # ------------------------------------------------------------ incidentes y lugar
    def _csv_lugar(self):
        e = self.hud.estado if self.hud else {}
        return (f"{_f(e.get('metros'))},{e.get('flecha') or ''},{e.get('cardinal') or ''},"
                f"{_txt(e.get('zona'))},{_txt(e.get('calle'))}")

    def lugar(self):
        t = self.hud.texto() if self.hud else ""
        c = getattr(self, "condicion", None)
        t = (t + (" | " if t else "") + f"condición {c}%") if c is not None else t
        if getattr(self, "regla", None):
            t += f" | regla: {self.regla.get('nota', '')}"
        return t

    # ------------------------------------------------------------ notificaciones en pantalla (2.0.0)
    AVISOS = (  # (prefijo del incidente, tipo, título)
        ("choque", "problema", "Choque"),
        ("atascado", "problema", "Atascado"),
        ("condición", "problema", "Bajó la condición"),
        ("grabación interrumpida", "problema", "Grabación interrumpida"),
        ("no consigue tomar el giro", "problema", "No consigue girar"),
        ("bloqueado", "problema", "Bloqueado cerca del punto"),
        ("posible falso choque", "aviso", "Falso choque ignorado"),
        ("marcha atrás cancelada", "aviso", "Marcha atrás cancelada"),
        ("salto de ruta ignorado", "aviso", "Salto falso de la ruta ignorado"),
        ("descargado no detectado", "aviso", "Descargado no detectado"),
        ("recorrido sin reglas", "aviso", "Recorrido nuevo"),
        ("control manual", "control", "Tomaste el control"),
        ("desactivado con la tecla", "autopiloto", "Autopiloto desactivado"),
        ("tramo manual", "etapa", "Tramo manual: llévalo tú"),
        ("recorrido reconocido", "etapa", "Recorrido reconocido"),
        ("recorrido corregido", "etapa", "Recorrido corregido"),
        ("cargamento", "etapa", "Cargamento"),
        ("llegada al punto", "etapa", "Llegaste al punto"),
        ("notificación: camión CARGADO", "etapa", "Camión cargado"),
        ("notificación: camión DESCARGADO", "etapa", "Camión descargado"),
        ("notificación: TRABAJO COMPLETADO", "etapa", "Trabajo completado"),
        ("grabación guardada", "grabacion", "Grabación guardada"),
        ("grabación:", "grabacion", "Repitiendo grabación"),
    )

    def _revisar_salud(self, ahora):
        """3.1.0: problemas de base (mando, distancia, millas, recorrido, etapa) para mostrar en la ventana."""
        try:
            e = self.hud.estado if self.hud else {}
            self.problemas, nuevos = self.salud.actualizar(
                ahora, self.estado, self.tramo, e.get("metros"), self.kmh, self.vel is not None,
                getattr(self, "recorrido", None))
        except Exception:  # noqa
            return
        for p in nuevos:
            print(f"\n[!] {p['titulo']}. {p['texto']}")
            self.avisar("problema" if p["nivel"] == "problema" else "aviso", p["titulo"], "Mira el aviso en la ventana.")

    def avisar(self, tipo, titulo, texto=""):
        """Notificación en pantalla (la muestra la interfaz, si la hay)."""
        if self.ui is not None and hasattr(self.ui, "notificar"):
            try:
                self.ui.notificar(tipo, titulo, texto)
            except Exception:  # noqa
                pass

    def _aviso_de_incidente(self, que):
        for pref, tipo, titulo in self.AVISOS:
            if que.startswith(pref):
                e = self.hud.estado if self.hud else {}
                detalle = que.split(":", 1)[1].strip() if ":" in que and pref.endswith((":", "reconocido", "corregido",
                                                                                        "cargamento", "guardada",
                                                                                        "sin reglas")) else ""
                detalle = detalle.split(" [cond")[0]
                lugar = " / ".join(x for x in (e.get("zona"), e.get("calle")) if x)
                donde = tipo in ("problema", "control", "aviso")
                partes = [p for p in (detalle, lugar if donde else "",
                                      _km(e.get("metros")) if donde and e.get("metros") is not None else "") if p]
                if tipo in ("problema", "control", "aviso") and self.kmh:
                    partes.append(f"{self.kmh} km/h")
                self.avisar(tipo, titulo, " · ".join(partes))
                return

    def incidente(self, que):
        """Anota un incidente (choque, maniobra, desactivación...) con el lugar del HUD."""
        self._aviso_de_incidente(que)
        c = getattr(self, "condicion", None)
        if c is not None and not que.startswith("condición"):
            que = f"{que} [cond {c}%]"
        self.evento = (self.evento + "; " if self.evento else "") + que
        self.anotar_punto_critico(que)
        if not self.cfg.get("hud_texto", {}).get("registrar_incidentes", True):
            return
        try:
            nuevo = not os.path.exists(self.ruta_incidentes)
            os.makedirs(os.path.dirname(self.ruta_incidentes) or ".", exist_ok=True)
            e = self.hud.estado if self.hud else {}
            with open(self.ruta_incidentes, "a", encoding="utf-8") as fh:
                if nuevo:
                    fh.write("fecha,tramo,evento,kmh,dist_punto_m,flecha,cardinal,zona,calle\n")
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},{self.tramo},{_txt(que)},{self.kmh},"
                         f"{_f(e.get('metros'))},{e.get('flecha') or ''},{e.get('cardinal') or ''},"
                         f"{_txt(e.get('zona'))},{_txt(e.get('calle'))}\n")
        except Exception:
            pass

    # ------------------------------------------------------------ grabaciones de recorridos (v38)
    def t_fin_juego_ref(self):
        """Identifica el trabajo actual (para hacer la grabación del final una sola vez por trabajo)."""
        return (self.tramo, self.conf.get("t_fin_juego"), getattr(self, "recorrido", None))

    def alternar_grabacion(self):
        if self.estado == "GRABANDO":
            g = self.grabadora.terminar()
            self.cambiar("INACTIVO")
            if g is None:
                print("\n[i] Grabación demasiado corta: descartada.")
                return
            self.avisar("grabacion", "Grabación terminada", f"{g['duracion']:.0f} s. Ponle nombre en el programa.")
            print(f"\n[i] Grabación terminada: {g['duracion']:.1f} s, {len(g['muestras'])} muestras. "
                  "Ponle nombre en la ventana.")
            if self.ui is not None and hasattr(self.ui, "pedir_guardar_grabacion"):
                self.ui.pedir_guardar_grabacion({"grab": g, "ap": self})
            else:
                g["nombre"] = f"grabacion_{time.strftime('%H%M%S')}"
                g["disparo"] = {"tipo": "distancia", "metros": g.get("metros_inicio") or 0}
                g["al_terminar"] = "parar"
                self.agregar_grabacion(g)
            return
        if self.estado == "REPRODUCIENDO":
            self.repro = None
        e = self.hud.estado if self.hud else {}
        m_ = self.cfg["minimapa"]
        self.grabadora.empezar({"escala": min(m_["w"], m_["h"]) / 176.0,
                                "recorrido": getattr(self, "recorrido", None) or "", "tramo": self.tramo,
                                "metros": e.get("metros"), "cardinal": e.get("cardinal"), "kmh": self.kmh})
        self.cambiar("GRABANDO")
        print(f"\n[REC] Grabando tu conducción (W/A/S/D/espacio). Tramo {self.tramo}, "
              f"{_km(e.get('metros'))} al punto. Vuelve a pulsar Grabar (o {self.cfg['teclas']['activar']}) para terminar.")

    def dist_fina(self):
        """Distancia al punto afinada (2.1.1): se descuenta lo recorrido (odómetro con la velocidad) y cada
        lectura nueva del HUD la corrige. Usa la distancia filtrada (sin lecturas sueltas erróneas)."""
        return getattr(self, "_est", None)

    def _actualizar_dist_fina(self):
        m = getattr(self, "dist_filtrada", None)
        if m is None:
            m = self.dist_punto()
        if m is None:
            self._est = None
            return
        est = getattr(self, "_est", None)
        nueva = m != self._hud_m
        if est is None or (nueva and abs(est - m) > 150):
            est = float(m)
        else:
            est -= self.odo - self._est_odo
        if nueva:
            paso = 10.0 if m >= 1000 else 1.0
            est = min(max(est, m - paso), m + paso)
            self._hud_m = m
        self._est_odo = self.odo
        self._est = est

    def agregar_trazado(self, g):
        motivo = []
        t = self.grab_mod.construir_trazado(g, motivo=motivo)
        if t is None:
            print(f"[!] El trazado no se guardó: {motivo[0] if motivo else 'sin datos'}.")
            self.ultimo_motivo_trazado = motivo[0] if motivo else "sin datos"
            return False
        t["nombre"] = g.get("nombre", t["nombre"])
        if g.get("_reemplazar"):                       # 3.5.0: reemplaza al antiguo del mismo nombre
            t["_reemplazar"] = True
        ruta = self.grab_mod.guardar_trazado(t)
        if g.get("_reemplazar"):
            base = os.path.basename(ruta)
            self.trazados = [x for x in self.trazados if x.get("_archivo") != base]
        t["_archivo"] = os.path.basename(ruta)
        self.trazados.append(t)
        print(f"[OK] Trazado guardado: {ruta} ({_km(t['desde'])} a {_km(t['hasta'])}, {len(t['puntos'])} puntos)")
        self.incidente(f"grabación guardada: {t['nombre']} (trazado)")
        return True

    def agregar_grabacion(self, g):
        """Guarda la grabación en disco y la deja disponible desde ya."""
        ruta = self.grab_mod.guardar(g)
        g["_archivo"] = os.path.basename(ruta)
        if g.get("_reemplazar"):                       # 3.5.0: quitar la antigua de la memoria
            self.grabs = [x for x in self.grabs if x.get("_archivo") != g["_archivo"]]
        if self.experimental("usar_grabaciones"):
            self.grabs.append(g)
        print(f"[OK] Grabación guardada: {ruta}")
        self.incidente(f"grabación guardada: {g.get('nombre', '?')}")

    def _grabs_ahora(self):
        """3.5.0: una regla puede apagar las grabaciones en su zona (exp usar_grabaciones = false)."""
        return self.grabs if self.experimental("usar_grabaciones") else []

    def iniciar_reproduccion(self, g):
        e = self.hud.estado if self.hud else {}
        card = e.get("cardinal")
        if g.get("cardinal_inicio") and card and card != g["cardinal_inicio"]:
            print(f"\n[!] Ojo: al grabar mirabas al {g['cardinal_inicio']} y ahora al {card}. "
                  "Si sale mal, toma el control.")
        gc = self.cfg.get("grabacion", {})
        self.repro = self.grab_mod.Reproductor(g, gc)
        print(f"\n[>] Repitiendo grabación \"{g.get('nombre', '?')}\" ({g.get('duracion', 0):.0f} s). "
              f"{'/'.join(self.cfg['teclas']['tomar_control'])} para tomar el control.")
        self.incidente(f"grabación: {g.get('nombre', '?')}")
        self.cambiar("REPRODUCIENDO")

    # ------------------------------------------------------------ puntos críticos y observaciones (v33)
    CRITICOS = ("choque", "atascado", "control manual", "ruta atrás", "no consigue", "condición",
                "posible falso choque", "marcha atrás cancelada", "salto de ruta")

    # ------------------------------------------------------------ capturas de incidentes (2.2.0)
    def guardar_en_buffer(self, img, ahora):
        """Guarda la pantalla (achicada, JPG en memoria) para poder mostrar qué pasó en un incidente."""
        cc = self.cfg.get("capturas", {})
        if not cc.get("activo", True):
            return
        if self.capturas and ahora - self.capturas[-1][0] < cc.get("cada_seg", 0.45):
            if not self.capturas_pend:
                return
        try:
            h, w = img.shape[:2]
            ancho = int(cc.get("ancho", 1280))
            peq = cv2.resize(img, (ancho, int(h * ancho / w)), interpolation=cv2.INTER_AREA) if w > ancho else img
            ok, jpg = cv2.imencode(".jpg", peq, [cv2.IMWRITE_JPEG_QUALITY, int(cc.get("calidad", 80))])
            if not ok:
                return
            jpg = jpg.tobytes()
            self.capturas.append((ahora, jpg))
            quedan = []
            for t_obj, ruta in self.capturas_pend:
                if ahora >= t_obj:
                    self._escribir_captura(ruta, jpg)
                else:
                    quedan.append((t_obj, ruta))
            self.capturas_pend = quedan
        except Exception as e:  # noqa
            if not getattr(self, "_aviso_capturas", False):
                print(f"[!] No se pudieron tomar capturas de incidentes: {e}")
                self._aviso_capturas = True

    @staticmethod
    def _escribir_captura(ruta, jpg):
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "wb") as fh:
                fh.write(jpg)
        except Exception:  # noqa
            pass

    def capturas_incidente(self, hito=False):
        """3 capturas: ~1,5 s antes, en el momento y ~1 s después (esta se escribe cuando llegue).
        2.4.2: en los hitos (F9 se aprieta después de lo que pasó): 3 s antes, 1,5 s antes y el momento."""
        import carpetas
        if not self.cfg.get("capturas", {}).get("activo", True) or not self.capturas:
            return []
        ahora = time.time()
        self.n_captura += 1
        base = os.path.join(carpetas.CAPTURAS_TEMP, f"{time.strftime('%Y%m%d_%H%M%S')}_{self.n_captura:03d}")
        salida = []
        tomas = (("antes3", -3.0), ("antes", -1.5), ("momento", 0.0)) if hito else (("antes", -1.5), ("momento", 0.0))
        for etiqueta, dt in tomas:
            t, jpg = min(self.capturas, key=lambda c: abs(c[0] - (ahora + dt)))
            ruta = f"{base}_{etiqueta}.jpg"
            self._escribir_captura(ruta, jpg)
            salida.append((etiqueta, ruta))
        if not hito:
            ruta = f"{base}_despues.jpg"
            self.capturas_pend.append((ahora + 1.0, ruta))
            salida.append(("despues", ruta))
        return salida

    def capturas_minimapa(self, img, res):
        """2.4.2: guarda el minimapa en tamaño real (ampliado x3) y lo que vio el detector, en ese mismo cuadro."""
        import carpetas
        if not self.cfg.get("capturas", {}).get("activo", True) or img is None:
            return []
        salida = []
        try:
            self.n_captura += 1
            base = os.path.join(carpetas.CAPTURAS_TEMP, f"{time.strftime('%Y%m%d_%H%M%S')}_{self.n_captura:03d}")
            os.makedirs(carpetas.CAPTURAS_TEMP, exist_ok=True)
            grande = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
            ruta = f"{base}_minimapa.jpg"
            if cv2.imwrite(ruta, grande, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                salida.append(("minimapa", ruta))
            try:
                dbg = vision.dibujar_debug(img, res, self.cfg, escala=3, texto="salto de ruta")
                ruta = f"{base}_detector.jpg"
                if cv2.imwrite(ruta, dbg, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                    salida.append(("detector", ruta))
            except Exception:  # noqa
                pass
        except Exception:  # noqa
            pass
        return salida

    # ------------------------------------------------------------ 2.4.2: saltos falsos de la ruta
    def filtrar_salto_ruta(self, res, img, ahora):
        """Si la línea del GPS salta de golpe hacia un lado (curva fuerte que aparece en un cuadro, fuera de la
        calle) yendo rápido, es un error de lectura del minimapa: se sigue con la última lectura buena hasta que
        la línea vuelva (o máximo ~1,5 s). Firma vista en Granja 2 (vuelta, 2,6 km): desvío +19 px,
        curva -24°→+56° y fuera de calle en un solo cuadro, con el rumbo exacto sin moverse."""
        cs = self.cfg.get("salto_ruta", {})
        if not cs.get("activo", True):
            return res
        ref = getattr(self, "_ruta_ref", None)
        enc = res.get("encontrada") and res.get("desvio_cerca") is not None and res.get("giro_adelante") is not None
        rb = getattr(self, "rumbo", None)
        rumbo_ahora = None if rb is None else rb.valor

        def lejos(r, a):
            return (abs(r["desvio_cerca"] - a["desvio_cerca"]) > cs.get("desvio_px", 12) and
                    abs(r["giro_adelante"] - a["giro_adelante"]) > cs.get("giro_grados", 35))

        t_ini = getattr(self, "_salto_desde", None)
        if t_ini is not None:
            volvio = enc and abs(res["desvio_cerca"] - ref["desvio_cerca"]) < cs.get("vuelta_desvio_px", 8) and \
                abs(res["giro_adelante"] - ref["giro_adelante"]) < cs.get("vuelta_giro_grados", 25) and \
                res.get("en_calle", 1.0) >= 0.5
            giro_real = rumbo_ahora is not None and getattr(self, "_salto_rumbo", None) is not None and \
                abs(vision._dif_ang(rumbo_ahora, self._salto_rumbo)) > cs.get("rumbo_real_grados", 8)
            if volvio or giro_real or ahora - t_ini > cs.get("max_seg", 1.5) or self.kmh < cs.get("kmh_min", 50) - 10:
                dur = ahora - t_ini
                self._salto_desde = None
                if not volvio:
                    print(f"\n[i] La ruta siguió en el lugar nuevo ({dur:.1f} s): la acepto.")
                    self._ruta_ref = res if enc else None
                    return res
                self._ruta_ref = res
                return res
            fijo = dict(ref)
            for k in ("mask", "comp", "pixeles", "marcador_dist", "marcador_ang", "marcador_xy", "dist_hud"):
                if k in res:
                    fijo[k] = res[k]
            fijo["salto_ignorado"] = True
            return fijo
        if not enc:
            return res
        if ref is not None and self.estado == "CONDUCIENDO" and self.kmh >= cs.get("kmh_min", 50) and \
                ref.get("en_calle", 1.0) >= 0.7 and res.get("en_calle", 1.0) < 0.3 and lejos(res, ref) and \
                ahora - getattr(self, "_ruta_ref_t", 0) < 0.4:
            self._salto_desde = ahora
            self._salto_rumbo = rumbo_ahora
            self._saltos_n = getattr(self, "_saltos_n", 0) + 1
            print(f"\n[i] Salto raro de la línea del GPS ({res['desvio_cerca']:+.0f} px, curva "
                  f"{res['giro_adelante']:+.0f}°): lo ignoro y sigo derecho.")
            self.incidente("salto de ruta ignorado")
            try:
                if self.puntos and self.puntos[-1]["que"].startswith("salto de ruta"):
                    self.puntos[-1]["capturas"] = self.capturas_minimapa(img, res) + \
                        (self.puntos[-1].get("capturas") or [])
            except Exception:  # noqa
                pass
            fijo = dict(ref)
            for k in ("mask", "comp", "pixeles", "marcador_dist", "marcador_ang", "marcador_xy", "dist_hud"):
                if k in res:
                    fijo[k] = res[k]
            fijo["salto_ignorado"] = True
            return fijo
        self._ruta_ref = res
        self._ruta_ref_t = ahora
        return res

    def anotar_punto_critico(self, que):
        if not que.startswith(self.CRITICOS):
            return
        self.puntos.append(self._datos_punto(que))

    def marcar_hito(self):
        """2.3.0: el jugador marca un momento para comentarlo después en las observaciones."""
        n = sum(1 for p in self.puntos if p.get("hito")) + 1
        p = self._datos_punto(f"hito {n}")
        p["hito"] = n
        self.puntos.append(p)
        lugar = " / ".join(x for x in (p.get("zona"), p.get("calle")) if x)
        texto = " · ".join(x for x in (_km(p.get("metros")) if p.get("metros") is not None else "", lugar) if x)
        print(f"\n[i] Hito {n} creado{(': ' + texto) if texto else ''}. Explícalo en las observaciones al terminar.")
        self.incidente(f"hito {n} (marcado por el jugador)")
        self.avisar("hito", f"Hito {n} creado", texto or "Explícalo en las observaciones al terminar.")

    def _datos_punto(self, que):
        r = getattr(self, "res_ult", None) or {}
        e = self.hud.estado if self.hud else {}
        dc = r.get("desvio_cerca")
        return {
            "t": round(time.time() - self.t0, 1) if hasattr(self, "t0") else 0.0,
            "que": que, "tramo": self.tramo, "kmh": self.kmh, "estado": self.estado,
            "metros": e.get("metros"), "zona": e.get("zona") or "", "calle": e.get("calle") or "",
            "regla": (self.regla or {}).get("nota", ""), "motivo": getattr(self, "motivo", ""),
            "ruta_vista": bool(r.get("encontrada")), "rumbo": r.get("rumbo"), "giro": r.get("giro_adelante"),
            "lado_px": None if dc is None else dc - self.desp_f, "en_calle": r.get("en_calle", 1.0),
            "foco": getattr(self, "_foco", True), "recorrido": getattr(self, "recorrido", None) or "",
            "capturas": self.capturas_incidente(hito=que.startswith("hito"))}

    @staticmethod
    def causa_probable(p):
        """Explicación sencilla de lo que pudo pasar, según lo que veía el programa en ese momento."""
        que, v = p["que"], p.get("kmh") or 0
        rb, g, lado = abs(p.get("rumbo") or 0), abs(p.get("giro") or 0), p.get("lado_px")
        m_lado = None if lado is None else abs(lado) * 0.76          # ~0,76 m por px del minimapa
        hacia = None if lado is None or abs(lado) < 4 else ("derecha" if lado < 0 else "izquierda")
        import re
        mv = re.search(r"\((\d+)->", que)
        vmax = int(mv.group(1)) if mv else v
        if que.startswith("salto de ruta"):
            return ("La línea del GPS del minimapa saltó de golpe hacia un lado; el programa la ignoró y siguió "
                    "derecho. Mira las capturas \"Minimapa\" y \"Lo que vio el programa\" para ver qué la confundió.")
        if que.startswith(("posible falso choque", "marcha atrás cancelada")):
            return "No fue un choque: no se veía el minimapa (pantalla tapada o tirón del juego)."
        if not p.get("foco", True):
            extra = "el juego no tenía el foco (otra ventana activa)"
        else:
            extra = ""
        if que.startswith("choque"):
            if not p.get("ruta_vista"):
                return "Sin minimapa en ese momento: pantalla tapada o tirón del juego (quizá no fue choque)."
            if hacia:
                return f"Iba unos {m_lado:.0f} m a la {hacia} de la línea: rozó o chocó con algo de ese lado."
            if rb < 12 and g < 12 and vmax >= 50:
                return (f"Iba recto a {vmax} km/h, sin curva: obstáculo que no sale en el minimapa "
                        "(árbol, poste, vehículo u otro jugador).")
            if rb >= 55:
                return "En una esquina: giró tarde o la esquina era muy cerrada para el camión."
            if g >= 25:
                return f"En curva a {vmax} km/h: quizá iba rápido o cortó por dentro."
            return "Chocó con algo que no aparece en el minimapa."
        if que.startswith("atascado"):
            if p.get("en_calle") is not None and p["en_calle"] < 0.5:
                return "Se salió de la calle (berma, barrera o vereda) y no pudo avanzar."
            if rb >= 55:
                return "Atascado en una esquina: no alcanzó a girar."
            return "Algo bloqueaba el paso (vehículo, barrera) o se trabó con la berma."
        if que.startswith("control manual"):
            if p.get("metros") is not None and p["metros"] < 160:
                return "Llegando al punto: normal (el final lo llevas tú)."
            partes = []
            if hacia:
                partes.append(f"se iba unos {m_lado:.0f} m hacia la {hacia} de la línea")
            if g >= 25 and v >= 50:
                partes.append(f"curva a {v} km/h")
            if rb >= 55:
                partes.append("esquina cerrada")
            if extra:
                partes.append(extra)
            return ("Tomaste el control: " + ", ".join(partes) + ".") if partes else \
                "Tomaste el control (el programa no vio nada raro: cuéntalo en la observación)."
        if que.startswith(("ruta atrás", "no consigue")):
            return "No pudo tomar el giro: la ruta quedó detrás y tuvo que maniobrar."
        if que.startswith("condición"):
            return "Golpe o roce: bajó la condición del camión." + (f" Iba a {v} km/h." if v else "")
        return ""

    def pedir_observaciones(self, motivo):
        """Pide a la interfaz que pregunte si quieres hacer observaciones (siempre pregunta)."""
        puntos, self.puntos = self.puntos, []
        if self.ui is None or not hasattr(self.ui, "pedir_observaciones"):
            return
        for p in puntos:
            p["causa"] = self.causa_probable(p)
        self.ui.pedir_observaciones({
            "motivo": motivo, "puntos": puntos, "recorrido": getattr(self, "recorrido", None) or "",
            "cargamento": getattr(self, "cargamento", None), "dist_inicial": getattr(self, "dist_inicial_est", None),
            "desconocido": self.ruta_act is None,
            "archivo": self.log.name if self.log else None, "ap": self})

    def escribir_observaciones(self, lineas):
        """La interfaz entrega las líneas; se escriben en el archivo del viaje desde el hilo del autopiloto."""
        self.cola_obs.put(lineas)

    def _volcar_observaciones(self):
        while True:
            try:
                lineas = self.cola_obs.get_nowait()
            except queue.Empty:
                break
            if self.log:
                try:
                    self.log.write("".join(lineas))
                    self.log.flush()
                except Exception:
                    pass

    def resumen_incidentes(self, n=8):
        """Lugares con más incidentes (todas las sesiones guardadas en incidentes.csv)."""
        try:
            import csv
            from collections import Counter
            if not os.path.exists(self.ruta_incidentes):
                return
            c = Counter()
            with open(self.ruta_incidentes, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r.get("evento", "").startswith(("desactivado con la tecla",)):
                        continue
                    lugar = " / ".join(x for x in (r.get("zona"), r.get("calle")) if x)
                    if lugar:
                        c[lugar] += 1
            if c:
                print("\n[i] Lugares con más incidentes (choques, atascos, maniobras):")
                for lugar, k in c.most_common(n):
                    print(f"     {k:3d}  {lugar}")
        except Exception:
            pass

    # ------------------------------------------------------------ utilidades
    def cambiar(self, estado, motivo=None):
        if estado == self.estado:
            return
        if motivo:
            self.incidente(motivo)
        antes = self.estado
        self.estado = estado
        self.t_estado = time.time()
        if estado == "ARRANCANDO" and antes in ("INACTIVO", "TERMINADO"):
            self.avisar("autopiloto", "Autopiloto activado", self.texto_etapa())
        elif estado == "INACTIVO" and antes in ("ARRANCANDO", "CONDUCIENDO") and not motivo:
            self.avisar("autopiloto", "Autopiloto desactivado")
        if estado == "GRABANDO":
            self.avisar("grabacion", "Grabando recorrido", "Conduce tú. Pulsa Grabar o INSERT para terminar.")
        if estado == "TERMINADO":
            self.pedir_observaciones("trabajo terminado")
        if estado == "ESPERANDO_RUTA":
            self.t_ruta_visible_desde = None      # la ruta que se veía al llegar no es una ruta nueva
        if estado == "CONDUCIENDO":
            self.tramo_notif = None
        if estado in ("INACTIVO", "ESPERANDO_RUTA", "TERMINADO", "GRABANDO"):
            self.ctrl.soltar_todo()
            self.recto = None
            self.aprox = False
            self.t_en_marcador = None
        if estado == "ARRANCANDO":
            self.err_prev, self.deriv, self.int_vel = None, 0.0, 0.0
            self.hist_obj = []
            self.hist_dir = []
            self.hist_ang = []
            self.refuerzo = 0.0
            self.integral_lat = 0.0
            self.acel_prev = 0.0
            self.t_parado_desde = None
            self.lecturas = []
            self.obj_filtrado = self.cfg["velocidad"]["objetivo_curva"]
            self.t_quieto_desde = None
        print(f"\n[{time.strftime('%H:%M:%S')}] -> {estado}   |   {self.texto_etapa()}")

    def texto_etapa(self):
        if self.estado == "TERMINADO":
            return f"Etapa 7: {ETAPAS[7]}"
        tabla = ETAPA_ESPERA if self.estado == "ESPERANDO_RUTA" else ETAPA_TRAMO
        e = tabla.get(self.tramo, 7)
        return f"Etapa {e}/7: {ETAPAS[e]}"

    def actualizar_movimiento(self, img):
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ahora = time.time()
        if self.gris_ref is None or ahora - self.t_gris_ref >= 0.5:
            self.mov = vision.movimiento(self.gris_ref, gris)
            self.gris_ref, self.t_gris_ref = gris, ahora

    def juego_con_foco(self):
        """¿La ventana activa de Windows es el juego? (solo se lee el título de la ventana)"""
        ahora = time.time()
        if ahora - getattr(self, "_t_foco", -99.0) < 0.25:
            return getattr(self, "_foco", True)
        self._t_foco = ahora
        nombre = self.cfg.get("ventana_juego", "")
        try:
            titulo = entrada.titulo_ventana_activa()
            foco = not nombre or nombre.lower() in titulo.lower()
        except Exception:
            titulo, foco = "", True
        if foco and nombre:
            self._ventana_vista = True
        elif not getattr(self, "_ventana_vista", False):
            # todavía no se vio ninguna ventana con ese título (quizá se llama distinto): no bloquear nada
            if titulo and titulo != getattr(self, "_titulo_avisado", None) and ahora - self.t0 > 20:
                print(f"\n[i] Ventana activa: \"{titulo}\". Si es el juego, pon ese nombre en "
                      f"\"ventana_juego\" de config.json (ahora: \"{nombre}\").")
                self._titulo_avisado = titulo
            foco = True
        if foco != getattr(self, "_foco", True):
            if not foco:
                self.avisar("aviso", "El juego no tiene el foco",
                            "Pausa (teclado)" if self.cfg["control"].get("backend") == "teclado"
                            else "Sigo manejando con el mando; las teclas del programa no cuentan.")
            if foco:
                print("\n[i] El juego vuelve a tener el foco: las teclas del programa funcionan otra vez.")
            elif self.cfg["control"].get("backend") == "teclado":
                print("\n[!] El juego perdió el foco: con control por TECLADO el autopiloto queda en pausa "
                      "(las teclas irían a la otra ventana). Vuelve al juego para seguir.")
            else:
                print("\n[i] El juego perdió el foco: sigo manejando con el mando. Las teclas del programa "
                      "(tomar control, INSERT, FIN...) no cuentan hasta que vuelvas al juego.")
        self._foco = foco
        return foco

    # ------------------------------------------------------------ teclas
    def procesar_teclas(self):
        t = self.cfg["teclas"]
        if self.parar.is_set():
            return False
        pulsadas = list(self.hotkeys.leer())
        foco = self.juego_con_foco()
        if not foco:
            pulsadas = []                      # escribiendo en otra ventana: ninguna tecla del programa cuenta
        # órdenes desde la interfaz: se traducen a la tecla equivalente
        mapa = {"activar": t["activar"], "lento": t["modo_lento"], "rapido": t["modo_rapido"],
                "saltar": t["saltar_etapa"],
                "carril": t["carril"], "salir": t["salir"], "hito": t["hito"]}
        while True:
            try:
                cmd = self.comandos.get_nowait()
            except queue.Empty:
                break
            if cmd == "grabar":
                self.alternar_grabacion()
                continue
            if cmd == "recargar_grabaciones":
                self.grabs = self.grab_mod.cargar_todas() if self.experimental("usar_grabaciones") else []
                self.trazados = self.grab_mod.cargar_trazados()
                print(f"[i] Grabaciones recargadas: {len(self.grabs)} grabaciones, {len(self.trazados)} trazados.")
                continue
            if cmd == "recargar_rutas" and self.rutas_mod is not None:     # 2.4.0: se editó desde el mapa
                arch = (self.ruta_act or {}).get("_archivo")
                self.rutas = self.rutas_mod.cargar()
                if arch:
                    self.ruta_act = next((r for r in self.rutas["rutas"] if r.get("_archivo") == arch), self.ruta_act)
                self.regla = None
                print("[i] Reglas recargadas (cambios del mapa de la ruta).")
                continue
            if cmd.startswith("experimental:"):
                _x, clave, val = cmd.split(":", 2)
                self.cfg.setdefault("experimental", {})[clave] = val == "1"
                if clave == "usar_grabaciones":
                    self.grabs = self.grab_mod.cargar_todas() if val == "1" else []
                    self.grab_pendiente = None
                print(f"[i] Experimental: {clave} {'ACTIVADO' if val == '1' else 'desactivado'}.")
                continue
            if cmd.startswith("recorrido:"):                 # 3.2.5: elegir el recorrido a mano
                self.elegir_recorrido(cmd.split(":", 1)[1] or None)
                continue
            if cmd.startswith("tramo:"):
                self.tramo = max(0, min(2, int(cmd.split(":")[1])))
                print(f"[i] Tramo fijado: {self.texto_etapa()}")
            elif cmd == "debug":
                self.debug = not self.debug
            elif cmd in mapa:
                pulsadas.append(mapa[cmd])
        for k in pulsadas:
            if k == t["salir"]:
                return False
            if k == t["activar"]:
                if self.estado == "GRABANDO":
                    self.alternar_grabacion()
                elif self.estado in ("INACTIVO", "TERMINADO"):
                    if self.estado == "TERMINADO":
                        self.tramo = 0 if getattr(self, "tramo_notif", None) is None else self.tramo_notif
                    self.cambiar("ARRANCANDO")
                else:
                    print(f"\n[i] Autopiloto desactivado con la tecla {t['activar']}.")
                    self.cambiar("INACTIVO", f"desactivado con la tecla {t['activar']}")
            elif k == t["modo_lento"]:
                self.modo_lento = not self.modo_lento
                self.t_modo_lento = time.time()
                if self.modo_lento:
                    self.modo_rapido = False
                print(f"\n[i] Modo lento {'ACTIVADO' if self.modo_lento else 'desactivado'}: "
                      + ("menos velocidad en todo (rectas, curvas y esquinas); las reglas mandan igual."
                         if self.modo_lento else "velocidad normal."))
            elif k == t["modo_rapido"]:
                self.modo_rapido = not self.modo_rapido
                if self.modo_rapido:
                    self.modo_lento = False
                print(f"\n[i] Modo rápido {'ACTIVADO' if self.modo_rapido else 'desactivado'}: "
                      + ("más velocidad y curvas más fluidas; las reglas mandan igual." if self.modo_rapido else
                         "velocidad normal."))
            elif k == t["carril"]:
                self.usar_carril = not self.usar_carril
                print(f"\n[i] Ayuda de carril {'ACTIVADA' if self.usar_carril else 'desactivada'}")
            elif k == t["hito"]:
                self.marcar_hito()
            elif k == t.get("grabar"):                     # 3.5.0: empezar / terminar de grabar
                self.alternar_grabacion()
            elif k == t["saltar_etapa"]:
                self.tramo = min(self.tramo + 1, 2)
                print(f"\n[i] Saltando a tramo {self.tramo}: {self.texto_etapa()}")
        if foco and self.estado not in ("INACTIVO", "TERMINADO", "ESPERANDO_RUTA", "GRABANDO"):
            propias = self.ctrl.teclas_propias()
            for k in t["tomar_control"]:
                if k not in propias and entrada.tecla_pulsada(entrada.VK[k]):
                    print(f"\n[!] Control manual detectado (tecla {k}): autopiloto desactivado")
                    self.cambiar("INACTIVO", f"control manual (tecla {k})")
                    break
        return True

    # ------------------------------------------------------------ dirección
    def punto_persecucion(self, res):
        """Ángulo (°) hacia el punto de la ruta a la distancia de persecución (+ = derecha)."""
        c = self.cfg["control"]
        m = self.cfg["minimapa"]
        escala = min(m["w"], m["h"]) / 176.0
        L = interpolar(self.kmh, c["persecucion_px_por_velocidad"]) * escala
        # en curvas cerradas mirar más cerca: así no corta camino por dentro
        tasa_cerca = max([t for r_, t in res.get("tasas", []) if r_ <= L * 2] or [0.0])
        L *= interpolar(tasa_cerca, c.get("persecucion_acortar_en_curva", [[0, 1.0]]))
        # v30: regla por lugar con "anticipacion" < 1: mirar más cerca = girar más tarde (no cortar por dentro)
        if getattr(self, "regla", None) is not None and "anticipacion" in self.regla:
            L *= max(0.4, min(1.5, float(self.regla["anticipacion"])))
        pts = res.get("puntos") or []
        if not pts:
            return res["rumbo"], L
        px, py = self.cfg["jugador"]["x"], self.cfg["jugador"]["y"]
        objetivo = next((p for p in pts if p[2] >= L), pts[-1])
        # Esquina cerrada: seguir RECTO por el tramo de antes hasta llegar a ella, y entonces girar fuerte
        es = self.cfg.get("esquinas", {})
        eg, ed = res.get("esquina_giro"), res.get("esquina_dist")
        self.en_giro_tardio = False

        def px_tardio(grados):
            # v31: una regla puede decir cuánto avanzar antes de girar en esa esquina (menos = girar antes)
            rg = getattr(self, "regla", None) or {}
            if "giro_tardio_px" in rg:
                return float(rg["giro_tardio_px"]) * escala
            # esquinas muy cerradas (calles angostas): avanzar más antes de girar
            # (solo esquinas de calle, ~80-110°; las horquillas más cerradas se toman como siempre)
            if es.get("giro_tardio_muy_cerrada_grados", 80) <= abs(grados or 0) < 110:
                base = es.get("giro_tardio_muy_cerrada_px", 3)
            else:
                base = es.get("giro_tardio_px", 7)
            # 3.5.0: «avanzar antes de girar» relativo al normal (+ = avanza más, gira después)
            return max(0.0, base - float(rg.get("avance_esquina_px", 0) or 0)) * escala
        # 3.2.1: la línea del GPS nace en la PUNTA de la flecha, no en su centro: con la esquina ya bajo la
        # flecha, su distancia se mide desde la punta (si no, en esquinas de 90° nunca baja del margen y sigue de largo)
        frente = es.get("frente_flecha_px", 7.0) * escala
        if eg is not None and ed is not None and abs(eg) >= es.get("giro_tardio_grados", 55):
            k_esq = next((i for i, p in enumerate(pts) if p[2] >= ed), len(pts) - 1)
            if ed > px_tardio(eg):
                antes = pts[:k_esq + 1]
                objetivo = next((p for p in antes if p[2] >= min(L, ed - 1)), antes[-1])
            else:
                despues = pts[k_esq:]
                objetivo = next((p for p in despues if p[2] >= ed + 10 * escala), despues[-1])
                self.en_giro_tardio = True
        # esquina ya oculta bajo la flecha: seguir recto hasta alcanzarla
        ef = res.get("esquina_frente")
        # bloqueado frente a la esquina (no avanza): no seguir esperando, girar ya
        bloqueado = self.kmh < 3 and getattr(self, "t_lento_desde", None) is not None and \
            time.time() - self.t_lento_desde > es.get("girar_si_bloqueado_seg", 0.8)
        if bloqueado and ((eg is not None and ed is not None and abs(eg) >= es.get("giro_tardio_grados", 55)
                           and ed < 30 * escala) or ef is not None):
            base = ed if ed is not None else pts[0][2]
            k_esq = next((i for i, p in enumerate(pts) if p[2] >= base), 0)
            despues = pts[k_esq:] or pts
            objetivo = next((p for p in despues if p[2] >= base + 14 * escala), despues[-1])
            self.en_giro_tardio = True
            self.esperando_esquina = False
            return math.degrees(math.atan2(objetivo[0] - px, py - objetivo[1])), L
        if ef is not None and abs(res.get("rumbo") or 0) >= es.get("giro_tardio_grados", 55):
            if ef - frente > px_tardio(max(abs(eg or 0), abs(res.get("rumbo") or 0))):
                self.esperando_esquina = True
                return 0.0, L                                   # todavía no: recto
            self.en_giro_tardio = True
        self.esperando_esquina = False
        # camión largo: antes de una esquina cerrada, apuntar un poco hacia fuera
        es = self.cfg.get("esquinas", {})
        eg, ed = res.get("esquina_giro"), res.get("esquina_dist")
        x, y = objetivo[0], objetivo[1]
        ang = math.degrees(math.atan2(x - px, py - y))
        if eg is not None and ed is not None and abs(eg) >= es.get("giro_esquina_grados", 75) \
                and L < ed <= es.get("abrir_desde_px", 45):
            ang -= (1 if eg > 0 else -1) * math.degrees(math.atan2(es.get("abrir_antes_px", 2.0), max(L, 1)))
        return ang, L

    @staticmethod
    def fuerza_carril(rc, cfc):
        """Cuánto se usa la cámara de carril (0..1): entera si ve las dos líneas (confianza alta),
        a medias si ve solo una línea recta y clara (p. ej. la amarilla de noche), nada si no."""
        conf = rc.get("confianza") or 0.0
        if conf >= cfc.get("conf_min", 0.75):
            return 1.0
        if conf >= cfc.get("conf_min_una_linea", 0.55):
            return cfc.get("peso_una_linea", 0.5)
        return 0.0

    def termino_carril(self, rc, cfc, res=None):
        """Corrección por carril, limitada y filtrada para que cambie despacio (evita el zigzag).
        El 'centro' del carril se ajusta solo con la línea del GPS: cuando el GPS dice que vamos
        centrados en una recta, lo que mida el carril en ese momento es sesgo de calibración."""
        if res is not None and res.get("desvio_cerca") is not None and abs(res["desvio_cerca"] - self.desp_f) < 1.5 \
                and abs(res.get("rumbo") or 0) < 8 and abs(res.get("giro_adelante") or 0) < 15 and self.kmh > 25:
            a = cfc.get("aprendizaje_sesgo", 0.995)
            self.sesgo_carril = a * self.sesgo_carril + (1 - a) * rc["desvio"]
            self.muestras_sesgo += 1
        tc = cfc.get("tope_grados", 8)
        bruto = max(-tc, min(tc, cfc.get("peso_grados", 12) * (rc["desvio"] - self.sesgo_carril)))
        f = cfc.get("filtro_correccion", 0.92)
        self.termino_carril_f = f * getattr(self, "termino_carril_f", 0.0) + (1 - f) * bruto
        return self.termino_carril_f

    def calcular_direccion(self, res, dt):
        if self.cfg["control"].get("modo_direccion", "persecucion") == "persecucion":
            return self.calcular_direccion_persecucion(res, dt)
        return self.calcular_direccion_rumbo(res, dt)

    def calcular_direccion_persecucion(self, res, dt):
        c = self.cfg["control"]
        ang_p, L = self.punto_persecucion(res)
        # ir desplazado de la línea (por defecto un poco a la izquierda). Desvío deseado: + = la ruta
        # queda a la derecha del camión. En curvas/esquinas hacia el lado del desplazamiento se anula
        # (si no, cortaría por dentro); hacia el otro lado se mantiene (abre la curva: aleja de postes).
        m = self.cfg["minimapa"]
        escala = min(m["w"], m["h"]) / 176.0
        desp = c.get("desplazamiento_carril_px", 0.0) * escala
        objetivo_desp = -desp
        if desp != 0:
            lado = -1 if desp < 0 else 1
            rb = res.get("rumbo") or 0.0
            eg, ed = res.get("esquina_giro"), res.get("esquina_dist")
            giro_cerca = [g for r_, g in res.get("giros", []) if r_ <= 80 * escala]
            # v26: también curvas SUAVES hacia ese lado (un separador de vías suele estar justo ahí)
            ug = c.get("desplazamiento_quitar_curva_grados", 12)
            ga = res.get("giro_adelante") or 0.0       # giro total que se ve por delante
            hacia_lado = (rb * lado > ug * 0.7 or ga * lado > ug or (eg is not None and ed is not None and eg * lado > ug
                                                   and ed < 80 * escala) or any(g * lado > ug for g in giro_cerca))
            bif = res.get("bifurcacion_dist")
            if hacia_lado or self.fuera_de_calle or self.kmh < 8 or (bif is not None and bif < 110 * escala):
                objetivo_desp = 0.0
        vel_desp = 3.0 * escala * max(dt, 0.0)          # px/s: cambia de lado suavemente
        if self.regla is not None and "desplazamiento_px" in self.regla:
            objetivo_desp = -float(self.regla["desplazamiento_px"]) * escala   # la regla manda
        eg_, ed_ = res.get("esquina_giro"), res.get("esquina_dist")
        en_esquina = str(getattr(self, "motivo", "")).startswith(("esquina", "en esquina")) or \
            (eg_ is not None and ed_ is not None and abs(eg_) >= 55 and ed_ < 40 * escala)
        if self.traz is not None and en_esquina and not getattr(self, "_aviso_traz_esq", False):
            print("\n[i] Esquina: el trazado se pausa (maneja la lógica de esquinas) y sigue después.")
            self._aviso_traz_esq = True
        if self.traz is None or not en_esquina:
            self._aviso_traz_esq = False
        if self.traz is not None and not en_esquina:    # 2.1.0: trazado grabado (2.3.3: no en esquinas)
            objetivo_desp = -float(self.traz[0]) * escala
            vel_desp = self.cfg.get("trazado", {}).get("cambio_px_seg", 6.0) * escala * max(dt, 0.0)
        self.desp_f += max(-vel_desp, min(vel_desp, objetivo_desp - self.desp_f))
        if abs(self.desp_f) > 0.01:
            ang_p -= math.degrees(math.atan2(self.desp_f, max(L, 1.0)))
        self.hist_ang = (getattr(self, "hist_ang", []) + [ang_p])[-3:]
        err = sorted(self.hist_ang)[len(self.hist_ang) // 2]          # mediana de 3: quita saltos
        # mantenerse SOBRE la línea: corregir el desvío lateral medido junto al camión
        dc = self.desvio_suave(res.get("desvio_cerca"), dt, res)
        dc_lado = dc
        if dc is not None:
            dc = dc - self.desp_f
            zm_d = c.get("persecucion_desvio_zona_muerta_px", 1.0)
            dc = 0.0 if abs(dc) < zm_d else dc - zm_d * (1 if dc > 0 else -1)
            tope_d = c.get("persecucion_desvio_tope", 12)
            # cuando la ruta gira fuerte junto al camión, la línea queda DELANTE, no a un lado:
            # la corrección lateral pierde fuerza (cos² del rumbo) para no luchar contra el giro
            fuerza = max(0.0, math.cos(math.radians(min(90.0, abs(res.get("rumbo") or 0.0))))) ** 2
            err += fuerza * max(-tope_d, min(tope_d, c.get("persecucion_desvio_grados_px", 0.8) * dc))
            # parte lenta: si en recta el desvío persiste hacia un lado, ir corrigiendo poco a poco
            recta = abs(res.get("rumbo") or 0) < 10 and abs(res.get("giro_adelante") or 0) < 20 and self.kmh > 20
            ti = c.get("integral_desvio_tope_grados", 6)
            if recta:
                self.integral_lat = max(-ti, min(ti, self.integral_lat +
                                        c.get("integral_desvio_grados_px_seg", 0.6) * (dc_lado - self.desp_f) * dt))
            else:
                self.integral_lat *= (1 - 0.3 * dt)
            err += self.integral_lat
        # calle gris: corrección pequeña hacia el centro de la calle
        cc = self.cfg.get("calle", {})
        tope = self.cfg["vision"].get("calle_corr_max_px", 2.5)
        if not self.fuera_de_calle:
            # v29: siempre (salvo camión fuera de la calle). GPS sobre una calle: el "centro de la calle gris" en calles anchas/autopistas queda a un
            # lado de la línea y empujaba el camión hacia la derecha (barandas, farolas): solo un poco
            tope = min(tope, cc.get("correccion_max_px", 0.8))
        corr = max(-tope, min(tope, cc.get("peso_correccion", 0.5) * res.get("calle_corr", 0.0)))
        err += c["peso_desvio"] * corr
        # carril detectado en la imagen: corrección fina
        self.carril_usado = False
        rc, cfc = self.res_carril, self.cfg.get("carril", {})
        if rc is not None and self.usar_carril and self.fuerza_carril(rc, cfc) > 0 \
                and abs(res.get("giro_adelante") or 0) < cfc.get("giro_max", 35) \
                and (res.get("esquina_dist") is None or res["esquina_dist"] > 40) \
                and self.kmh >= cfc.get("kmh_min", 15) and not self.fuera_de_calle:
            err += self.fuerza_carril(rc, cfc) * self.termino_carril(rc, cfc, res)
            self.carril_usado = True
        else:
            self.termino_carril_f = 0.0
        zm = c["zona_muerta_grados"]
        err = 0.0 if abs(err) < zm else err - zm * (1 if err > 0 else -1)
        if self.err_prev is not None:
            d = (err - self.err_prev) / max(dt, 1e-3)
            self.deriv = 0.7 * self.deriv + 0.3 * d
        self.err_prev = err
        ganancia = interpolar(self.kmh, c["ganancia_por_velocidad"])
        es = self.cfg.get("esquinas", {})
        if getattr(self, "en_giro_tardio", False) or abs(res.get("rumbo") or 0) >= es.get("giro_tardio_grados", 55):
            ganancia *= es.get("giro_tardio_ganancia", 1.8)      # en la esquina: girar decidido
        elif self.kmh >= c.get("curva_rapida_kmh", 45):
            # v28: a alta velocidad, si la carretera ya se va hacia un lado (>= 10°), girar con más
            # decisión (antes casi no movía el volante y se salía en las curvas en bajada)
            curva_vista = max(abs(res.get("rumbo") or 0.0),
                              c.get("curva_rapida_peso_giro", 0.6) * abs(res.get("giro_adelante") or 0.0))
            ganancia *= interpolar(curva_vista, c.get("curva_rapida_ganancia", [[10, 1.0], [25, 1.6]]))
        objetivo = ganancia * (c["kp_persecucion"] * err + c["kd"] * 0.5 * self.deriv)
        if c.get("invertir_direccion"):
            objetivo = -objetivo
        objetivo = max(-1.0, min(1.0, objetivo))
        s = c["suavizado"]
        objetivo = s * self.direccion + (1 - s) * objetivo
        paso = c["cambio_max_por_seg"] * dt
        self.direccion += max(-paso, min(paso, objetivo - self.direccion))
        return self.direccion

    def calcular_direccion_rumbo(self, res, dt):
        """Rumbo de la ruta junto al camión + corrección por desvío lateral (tipo Stanley)."""
        c = self.cfg["control"]
        # mediana de los 3 últimos fotogramas: elimina saltos sueltos de la detección
        self.hist_dir = (getattr(self, "hist_dir", []) + [(res["rumbo"], res["desvio"])])[-3:]
        rumbo = sorted(h[0] for h in self.hist_dir)[len(self.hist_dir) // 2]
        desvio = sorted(h[1] for h in self.hist_dir)[len(self.hist_dir) // 2]
        desvio -= c.get("desplazamiento_carril_px", 0.0)
        # calle gris: ir hacia el centro de la calle (o hacia la calle si el GPS va por fuera)
        cc = self.cfg.get("calle", {})
        tope = self.cfg["vision"].get("calle_corr_max_px", 2.5)
        if not self.fuera_de_calle:
            tope = min(tope, cc.get("correccion_max_px", 0.8))
        desvio += max(-tope, min(tope, cc.get("peso_correccion", 0.5) * res.get("calle_corr", 0.0)))
        # camión largo: antes de una esquina cerrada, abrirse hacia el lado de fuera
        es = self.cfg.get("esquinas", {})
        eg, ed = res.get("esquina_giro"), res.get("esquina_dist")
        if eg is not None and ed is not None and abs(eg) >= es.get("giro_esquina_grados", 75) \
                and ed <= es.get("abrir_desde_px", 45):
            desvio -= (1 if eg > 0 else -1) * es.get("abrir_antes_px", 2.0)
        peso = c["peso_desvio"] * interpolar(self.kmh, c["peso_desvio_por_velocidad"])
        limite = c["limite_desvio_fuera_calle"] if self.fuera_de_calle else c["limite_desvio_grados"]
        termino = max(-limite, min(limite, peso * desvio))
        # carril detectado en la imagen del juego: corrección fina dentro del carril
        self.carril_usado = False
        rc, cfc = self.res_carril, self.cfg.get("carril", {})
        if rc is not None and self.usar_carril and self.fuerza_carril(rc, cfc) > 0 \
                and abs(res.get("giro_adelante") or 0) < cfc.get("giro_max", 35) \
                and (res.get("esquina_dist") is None or res["esquina_dist"] > 40) \
                and self.kmh >= cfc.get("kmh_min", 15) and not self.fuera_de_calle:
            f_c = self.fuerza_carril(rc, cfc)
            termino *= (1 - cfc.get("reduccion_gps", 0.6) * rc["confianza"] * f_c)
            termino += f_c * self.termino_carril(rc, cfc, res)
            self.carril_usado = True
        else:
            self.termino_carril_f = 0.0
        err = rumbo + termino
        zm = c["zona_muerta_grados"]
        err = 0.0 if abs(err) < zm else err - zm * (1 if err > 0 else -1)

        if self.err_prev is not None:
            d = (err - self.err_prev) / max(dt, 1e-3)
            self.deriv = 0.7 * self.deriv + 0.3 * d
        self.err_prev = err
        ganancia = interpolar(self.kmh, c["ganancia_por_velocidad"])
        objetivo = ganancia * (c["kp"] * err + c["kd"] * self.deriv)
        if c.get("invertir_direccion"):
            objetivo = -objetivo
        objetivo = max(-1.0, min(1.0, objetivo))
        s = c["suavizado"]
        objetivo = s * self.direccion + (1 - s) * objetivo
        paso = c["cambio_max_por_seg"] * dt
        self.direccion += max(-paso, min(paso, objetivo - self.direccion))
        return self.direccion

    # ------------------------------------------------------------ velocidad
    def en_autopista(self):
        """La calle leída del HUD es una autopista (Autopista ..., ... Freeway/Fwy)."""
        calle = ((self.hud.estado.get("calle") if self.hud else None) or "").lower()
        return any(k in calle for k in ("autopista", "freeway", "fwy"))

    def modo_vel(self):
        """3.5.0: modo de velocidad que vale ahora: el que pide la regla («modo») o el elegido con las teclas.
        Devuelve "rapido", "lento" o None (normal)."""
        m = (getattr(self, "regla", None) or {}).get("modo")
        if m in ("rapido", "lento"):
            return m
        if m == "normal":
            return None
        if getattr(self, "modo_rapido", False):
            return "rapido"
        if getattr(self, "modo_lento", False):
            return "lento"
        return None

    def vcfg(self):
        """2.6.0: valores de velocidad; con el modo rápido (o lento, 3.5.0), los de su bloque encima de los
        normales."""
        v = self.cfg["velocidad"]
        modo = self.modo_vel()
        if modo is None:
            return v
        clave = (id(self.cfg), modo)
        cache = getattr(self, "_vcfg_modo", {})
        self._vcfg_modo = cache
        if clave not in cache:
            mr = self.cfg.get("modo_" + modo, {})
            f = float(mr.get("factor_curvas", 1.15 if modo == "rapido" else 0.85))
            r = dict(v)
            r["objetivo_curva"] = round(v["objetivo_curva"] * f, 1)
            r["objetivo_curva_cerrada"] = round(v["objetivo_curva_cerrada"] * f, 1)
            r["objetivo_por_tasa_giro"] = [[g, round(k * f, 1)] for g, k in v["objetivo_por_tasa_giro"]]
            if modo == "lento":
                r["objetivo_por_giro_total"] = [[g, round(k * f, 1)] for g, k in v["objetivo_por_giro_total"]]
            r.update(mr.get("velocidad", {}))
            cache[clave] = r
        return cache[clave]

    def ecfg(self):
        """2.6.0: esquinas para la VELOCIDAD (con el modo rápido, +5 km/h en las que no tienen regla)."""
        es = self.cfg.get("esquinas", {})
        modo = self.modo_vel()
        if modo is None:
            return es
        extra = float(self.cfg.get("modo_" + modo, {}).get("extra_esquina_kmh", 5 if modo == "rapido" else -3))
        r = dict(es)
        for k in ("objetivo_esquina_kmh", "objetivo_esquina_muy_cerrada_kmh"):
            if k in r:
                r[k] = max(6, r[k] + extra)
        return r

    def velocidad_objetivo(self, res, dt):
        v = self.vcfg()
        tabla = [[0, v["objetivo_recta"]],
                 [v["curva_suave_grados"], v["objetivo_recta"]],
                 [v["curva_ref_grados"], v["objetivo_curva"]],
                 [v["curva_cerrada_grados"], v["objetivo_curva_cerrada"]]]
        r_aj = self.cfg["vision"].get("radio_ajuste", 20)
        esc_v = min(self.cfg["minimapa"]["w"], self.cfg["minimapa"]["h"]) / 176.0
        limites = [(v["objetivo_recta"], "recta")]
        if abs(res["rumbo"]) >= v["rumbo_que_cuenta_como_curva"]:
            limites.append((interpolar(abs(res["rumbo"]), tabla), "camion torcido"))
        ahora_ = time.time()
        if abs(res["desvio"]) >= v["desvio_para_ir_lento_px"]:
            self.t_fuera_desde = getattr(self, "t_fuera_desde", None) or ahora_
            if ahora_ - self.t_fuera_desde > v["desvio_para_ir_lento_seg"]:
                limites.append((v["objetivo_fuera_de_ruta"], "fuera de ruta"))
        else:
            self.t_fuera_desde = None
        for r, g in res.get("giros", []):
            limites.append((interpolar(abs(g), tabla) + v["kmh_extra_por_px"] * max(0.0, r - r_aj), "curva"))
        for r, tasa in res.get("tasas", []):
            limites.append((interpolar(tasa, v["objetivo_por_tasa_giro"]) +
                            v["kmh_extra_por_px"] * max(0.0, r - r_aj), "curva cerrada"))
        es = self.ecfg()
        for r, g in res.get("giros", []):
            if abs(g) >= es.get("giro_esquina_grados", 75):
                base_e = es["objetivo_esquina_muy_cerrada_kmh"] if abs(g) >= 110 else es["objetivo_esquina_kmh"]
                if self.regla is not None and "esquina_kmh" in self.regla:
                    base_e = float(self.regla["esquina_kmh"])     # v31: esta esquina, a otra velocidad
                limites.append((base_e + v["kmh_extra_por_px"] * max(0.0, r - r_aj), "esquina"))
                break
        if abs(res["rumbo"]) >= es.get("giro_esquina_grados", 75):
            o_e = es.get("objetivo_esquina_kmh", 12)
            if self.regla is not None and "esquina_kmh" in self.regla:
                o_e = float(self.regla["esquina_kmh"])
            limites.append((o_e, "en esquina"))
        if self.fuera_de_calle:
            limites.append((self.cfg["calle"]["objetivo_fuera_de_calle"], "fuera de calle"))
        # v29: regla por lugar (rutas conocidas)
        if self.regla is not None and "max_kmh" in self.regla:
            limites.append((float(self.regla["max_kmh"]), "regla"))
        if self.traz is not None:
            tz = self.cfg.get("trazado", {})
            limites.append((max(tz.get("kmh_minimo", 15), self.traz[1] + tz.get("kmh_margen", 5)), "trazado"))
        if self.lim_grab is not None:
            limites.append((self.lim_grab, "hacia grabación"))
        # v31: regla que empieza más adelante: bajar de a poco antes de llegar (sin frenazo al entrar)
        rp, d_hud = getattr(self, "regla_prox", None), self.dist_punto()
        if rp is not None and "max_kmh" in rp and d_hud is not None and d_hud > rp.get("desde", 0):
            limites.append((float(rp["max_kmh"]) + v.get("regla_antes_kmh_por_m", 0.5) * (d_hud - rp["desde"]),
                            "regla (antes)"))
        # v29: curva larga y suave (giro total que se ve por delante): antes se iba a 80 como "recta"
        ga = abs(res.get("giro_adelante") or 0.0)
        tabla_g = v.get("objetivo_por_giro_total", [[15, 80], [25, 65], [45, 50], [70, 40]])
        if ga >= tabla_g[0][0]:
            r_mitad = next((r_ for r_, g_ in res.get("giros", []) if abs(g_) >= ga / 2), r_aj)
            o_cl = interpolar(ga, tabla_g) + v.get("giro_total_extra_por_px", 0.2) * max(0.0, r_mitad - r_aj)
            if self.regla is not None and "curva_larga_kmh" in self.regla:
                o_cl = max(o_cl, float(self.regla["curva_larga_kmh"]))   # v34: esta curva larga, más rápido
            limites.append((o_cl, "curva larga"))
        # v26: la calle se abre en dos delante (separador, salida): pasar más despacio
        bif = res.get("bifurcacion_dist")
        o_bif = v.get("objetivo_bifurcacion", 55)
        if self.en_autopista():
            o_bif = v.get("objetivo_bifurcacion_autopista", 70)    # v30: en autopista no hace falta tanto
        if self.regla is not None and self.regla.get("sin_bifurcacion"):
            o_bif = 0                                               # v33: p. ej. en la subida de Autopia Parkway
        if bif is not None and o_bif > 0:
            limites.append((o_bif + v["kmh_extra_por_px"] * max(0.0, bif - r_aj), "bifurcación"))
        # v26: desviado de la línea (de donde debería ir) a mucha velocidad: bajar hasta volver
        dc = res.get("desvio_cerca")
        if dc is not None and v.get("objetivo_desviado", 0) > 0 and \
                abs(dc - self.desp_f) > v.get("desviado_px", 5.0) * esc_v:
            self.t_desviado = getattr(self, "t_desviado", None) or ahora_
            if ahora_ - self.t_desviado > 0.4:
                limites.append((v.get("objetivo_desviado", 55), "desviado"))
        else:
            self.t_desviado = None
        # distancia real al punto leída del minimapa: si está lejos, no frenar "por destino"
        # (la ruta puede verse corta o cortada en el minimapa sin que el punto esté cerca)
        dist_hud = self.hud.estado.get("metros") if self.hud else None
        lejos = dist_hud is not None and dist_hud > self.cfg.get("hud_texto", {}).get("destino_lejos_m", 150)
        if res["cerca_destino"] and not lejos:
            limites.append((v["objetivo_cerca_destino"], "destino"))
        md = res.get("marcador_dist")
        if md is not None and not lejos and md < self.cfg.get("etapas_pantalla", {}).get("marcador_frenar_px", 70):
            limites.append((v["objetivo_cerca_destino"] + v["kmh_extra_por_px"] * max(0.0, md - 15), "destino"))
        if res.get("fin_ruta_dist") is not None and not lejos:
            limites.append((v["objetivo_cerca_destino"] +
                            v["kmh_extra_por_px"] * max(0.0, res["fin_ruta_dist"] - r_aj), "destino"))
        # recta larga y despejada: subir a la velocidad de recta larga (por defecto 100)
        m_ = self.cfg["minimapa"]
        esc = min(m_["w"], m_["h"]) / 176.0
        gmax = v.get("recta_larga_giro_max", 8)
        pts = res.get("puntos") or []
        recta_larga = (v.get("objetivo_recta_larga", v["objetivo_recta"]) > v["objetivo_recta"]
                       and pts and pts[-1][2] >= v.get("recta_larga_px", 90) * esc
                       and abs(res["rumbo"]) < v.get("recta_larga_rumbo_max", 6)
                       and abs(res["desvio"]) < v.get("recta_larga_desvio_max", 4)
                       and all(abs(g) < gmax for _, g in res.get("giros", []))
                       and all(t_ < gmax for _, t_ in res.get("tasas", []))
                       and res.get("esquina_dist") is None and not res["cerca_destino"]
                       and res.get("fin_ruta_dist") is None and md is None
                       and not self.fuera_de_calle)
        if recta_larga:
            self.t_recta_larga_desde = self.t_recta_larga_desde or ahora_
        else:
            self.t_recta_larga_desde = None
        if self.t_recta_larga_desde is not None and ahora_ - self.t_recta_larga_desde >= v.get("recta_larga_seg", 2.0):
            limites = [(o, mo) for o, mo in limites if mo not in ("recta", "curva", "curva cerrada")]
            limites.append((v["objetivo_recta_larga"], "recta larga"))
        # v28: en bajada, las curvas y esquinas más despacio (el camión gana velocidad solo)
        if ahora_ - getattr(self, "t_bajada", -99.0) < v.get("bajada_seg", 4.0):
            red = v.get("bajada_reduccion_kmh", 10)
            esq_regla = self.regla is not None and "esquina_kmh" in self.regla
            limites = [(o - red, m + " (bajada)") if m in ("curva", "curva cerrada", "esquina", "en esquina")
                       and not (esq_regla and m in ("esquina", "en esquina"))
                       else ((v["objetivo_recta"], "recta (bajada)") if m == "recta larga" else (o, m))
                       for o, m in limites]
        crudo, motivo = min(limites, key=lambda x: x[0])
        # memoria: si hace poco vimos una curva, no volver a acelerar todavía
        ahora = time.time()
        self.hist_obj = [(t, o, m) for t, o, m in getattr(self, "hist_obj", [])
                         if ahora - t <= v["memoria_curva_seg"]] + [(ahora, crudo, motivo)]
        # el 3er valor más bajo (no el mínimo): un fotograma suelto con ruido no frena el camión
        orden = sorted(((o, m) for _, o, m in self.hist_obj), key=lambda x: x[0])
        minimo, motivo_min = orden[min(len(orden) - 1, v.get("objetivo_ignorar_fotogramas", 2))]
        prev = getattr(self, "obj_filtrado", minimo)
        obj = min(minimo, prev + v["subida_objetivo_kmh_seg"] * dt)
        self.motivo = motivo_min if obj <= minimo + 0.5 else "subiendo"
        self.obj_filtrado = obj
        return obj

    def calcular_pedales(self, res, dt):
        v = self.vcfg()
        if self.vel is None:   # sin velocímetro: acelerador fijo
            curva = max(abs(res["giro_adelante"]), abs(res["rumbo"]))
            acel = v["sin_velocimetro_curva"] if curva > v["curva_ref_grados"] else v["sin_velocimetro_recta"]
            if self.estado == "ARRANCANDO" or self.mov < self.cfg["atasco"]["umbral_movimiento"]:
                acel = v["acelerador_arranque"]
            return acel, 0.0

        obj = self.kmh_obj = self.velocidad_objetivo(res, dt)
        ahora = time.time()
        vpred, pendiente = self.velocidad_predicha(ahora)
        if self.kmh < 3:
            self.t_parado_desde = getattr(self, "t_parado_desde", None) or ahora
        else:
            self.t_parado_desde = None
        parado = self.t_parado_desde is not None and \
            ahora - self.t_parado_desde > v["segundos_parado_para_arranque"]
        prev = getattr(self, "acel_prev", 0.0)
        # v28: ¿bajada? gana velocidad casi sin acelerar, o no pierde aunque frene. Se acumula
        # "evidencia" (sube con cada indicio, baja despacio) para no depender de un solo instante
        fprev = getattr(self, "freno_prev", 0.0)
        cand = self.kmh > 30 and prev <= 0.25 and (
            (fprev == 0 and pendiente > 0.5) or (fprev > 0 and pendiente > -2.0) or
            (self.kmh > obj + 4 and pendiente > -1.0))
        sc = getattr(self, "bajada_score", 0.0)
        sc = min(3.0, sc + dt) if cand else max(0.0, sc - 0.4 * dt)
        self.bajada_score = sc
        if sc >= v.get("bajada_detectar_seg", 1.2):
            if ahora - getattr(self, "t_bajada", -99.0) > 5:
                print("\n[i] Bajada: curvas más despacio.")
            self.t_bajada = ahora
        err = obj - vpred
        # error "amortiguado": si ya va subiendo/bajando rápido, anticipar (evita pasarse por el retraso del HUD)
        err_d = err - v.get("amortiguacion_seg", 0.25) * pendiente
        suave_v = self.experimental("velocidad_sin_vaiven")      # 3.2.4
        freno = 0.0
        crucero = interpolar(obj, v["acelerador_crucero_por_velocidad"])
        acel_max = min(v["acelerador_max_en_marcha"], interpolar(obj, v["acelerador_max_por_objetivo"]))
        integ = getattr(self, "integ_acel", 0.0)
        margen = (v["margen_sin_frenar_curva_kmh"] if obj < v["objetivo_recta"] - 10 else v["margen_sin_frenar_kmh"])
        if obj <= 30:
            margen = max(margen, v.get("margen_sin_frenar_lento_kmh", 9))
        # v30: curvas largas/suaves: soltar el acelerador basta (en GTA soltarlo ya frena ~15 km/h/s)
        motivo_ = getattr(self, "motivo", "")
        if motivo_ in ("curva larga", "bifurcación", "subiendo"):
            margen = max(margen, v.get("margen_sin_frenar_curva_suave_kmh", 8))
        # v30: en tramos suaves no frenar solo por la predicción: el HUD tiene que marcar ya más que el
        # objetivo (al acelerar en curva la predicción se pasaba y frenaba a 54 con objetivo 56).
        # En esquinas, curvas cerradas y al llegar se sigue frenando por adelantado.
        suave = motivo_ in ("curva larga", "bifurcación", "subiendo", "regla", "regla (antes)", "recta", "trazado",
                            "camion torcido")
        lectura_ok = not suave or self.kmh - obj > v.get("frenar_exceso_lectura_kmh", 3)
        # v33: regla "sin_freno" (subida): solo soltar el acelerador, salvo en esquinas o al llegar
        if self.regla is not None and self.regla.get("sin_freno") and \
                not motivo_.startswith(("esquina", "en esquina", "destino", "al marcador", "fuera de calle",
                                        "camion torcido", "curva cerrada")):
            lectura_ok = False
        # 2.3.2 (experimental): con límite bajo en reglas y curvas, el HUD llega 1-2 s tarde y el control
        # oscilaba (19 <-> 51 km/h con límite 40). Acelerar con menos fuerza y frenar solo si se pasa bastante.
        suave_lenta = self.experimental("velocidad_suave_curvas") and self.modo_vel() != "rapido" and obj < 50 and \
            (motivo_ in ("regla", "regla (antes)", "curva", "curva larga", "trazado", "camion torcido") or
             motivo_.startswith(("curva cerrada", "esquina", "en esquina")))      # 2.3.4: también esquinas
        if suave_lenta:
            margen = max(margen, v.get("suave_lenta_margen_kmh", 10))
            acel_max = min(acel_max, v.get("suave_lenta_acel_max", 0.6))
        critico = motivo_.startswith(("esquina", "en esquina", "destino", "al marcador", "curva cerrada"))
        if suave_v and not critico:
            # 3.2.8: fuera de esquinas y llegadas, frenar solo si el HUD YA marca el exceso (la predicción con el
            # retraso del HUD frenaba de más y después el camión caía 20 km/h)
            lectura_ok = lectura_ok and self.kmh - obj > margen
        frenar = -err > margen and lectura_ok and self.kmh >= 8 and \
            not (self.kmh < v["sin_freno_bajo_kmh"] and -err < v["sin_freno_bajo_margen_kmh"])
        if obj > 0 and (parado or (self.estado == "ARRANCANDO" and self.kmh < 5)):
            acel = min(v["acelerador_arranque"], max(acel_max, 0.6))   # arrancar parado (sin pasarse)
        elif not frenar:
            # acelerador PROPORCIONAL y suave (sin todo-o-nada): crucero + lo aprendido + corrección.
            # El término integral aprende cuánto acelerador hace falta de verdad (carga, cuestas).
            acel = crucero + integ + v.get("kp_acelerador", 0.03) * err_d
            tope = acel_max
            if suave_v:
                # 3.2.8: el camión cargado pierde ~15 km/h/s con el acelerador bajo y gana solo ~8 con el máximo,
                # y responde ~1 s tarde. Bajar el acelerador "porque se pasó 7" lo hacía caer de 47 a 24 (y luego
                # pasarse de nuevo). Por eso: alrededor del acelerador de mantener, poca corrección hacia abajo,
                # sin soltar del todo por poco exceso, y sin subir a tope estando cerca del objetivo.
                mant = max(0.05, crucero + integ)
                kp_sub = v.get("kp_subir", 0.01)
                kp_baj = v.get("kp_bajar", 0.008)
                acel = mant + (kp_sub if err_d > 0 else kp_baj) * err_d
                if err < v.get("cerca_objetivo_kmh", 10):
                    tope = min(acel_max, mant + v.get("cerca_extra", 0.05) + 0.012 * max(0.0, err))
                if -err <= v.get("sin_soltar_kmh", 8):
                    acel = max(acel, v.get("piso_mantener", 0.9) * mant)
            acel = max(0.0, min(acel, tope))
            if 0.0 < acel < acel_max and abs(err) < 15:
                integ += (v.get("ki_sin_vaiven", 0.004) if suave_v else v.get("ki_acelerador", 0.012)) * err * dt
                integ = max(-0.25, min(v.get("integral_acelerador_max", 0.4), integ))
            # justo después de frenar el HUD aún no muestra toda la bajada: no acelerar de golpe
            if ahora - getattr(self, "t_ultimo_freno_ped", -99.0) < v.get("tras_freno_seg", 0.8) and err < 10:
                acel = min(acel, crucero)
            sube = v["subida_acelerador_por_seg"] * dt * (v.get("suave_lenta_subida_factor", 0.5) if suave_lenta else 1.0)
            baja = v.get("bajada_acelerador_por_seg", 1.5) * dt
            base = prev
            if suave_v and err > -2:
                base = max(prev, min(acel, crucero))   # 3.2.4: tras soltar/frenar, volver al de mantener de inmediato
            acel = max(prev - baja, min(base + sube, acel))
        else:
            acel = 0.0
            freno = min(v["freno_max"], 0.10 + (-err) / 50)
            if suave_v and self.kmh - obj < v.get("freno_fuerte_exceso_kmh", 15) and not critico:
                # 3.2.4: con poco exceso, toque de freno suave (un pulso de 0,3 bajaba ~20 km/h en GTA)
                freno = min(freno, v.get("freno_suave", 0.15))
        self.integ_acel = integ
        # frenar a pulsos: GTA frena fuerte y el HUD tarda en mostrarlo
        if freno > 0:
            if ahora < getattr(self, "freno_bloqueado_hasta", 0):
                freno = 0.0
            else:
                self.t_freno_ini = getattr(self, "t_freno_ini", None) or ahora
                exceso = max(0.0, vpred - obj)
                pulso = v["freno_pulso_seg"] * (1 + min(1.0, exceso / 25))   # muy pasado: pulso más largo
                if ahora - self.t_freno_ini > pulso:
                    freno = 0.0
                    self.t_freno_ini = None
                    self.freno_bloqueado_hasta = ahora + v["freno_espera_seg"]
        else:
            self.t_freno_ini = None
        # Subida / volante a tope: si lleva rato por debajo del objetivo sin acercarse, reforzar el acelerador
        # (solo si NO está ganando velocidad: en llano, acelerando normal, no hace falta)
        # (no justo después de frenar: el HUD aún muestra la caída y parecería una subida)
        if freno > 0:
            self.t_ultimo_freno_ped = ahora
        bajo = obj > 0 and self.kmh < obj - 4 and self.kmh < 25
        if bajo:
            self.t_bajo_desde = getattr(self, "t_bajo_desde", None) or ahora
        else:
            self.t_bajo_desde = None
        if bajo and freno == 0 and -1.0 < pendiente < 1.5 and acel >= acel_max * 0.9 \
                and ahora - self.t_bajo_desde > 1.5 \
                and ahora - getattr(self, "t_ultimo_freno_ped", -99.0) > 2.5:
            self.refuerzo = min(v.get("subida_refuerzo_max", 0.5),
                                getattr(self, "refuerzo", 0.0) + v.get("subida_refuerzo_por_seg", 0.35) * dt)
        else:
            # mantener el refuerzo mientras siga por debajo del objetivo; soltarlo al acercarse
            caida = 2.0 if self.kmh >= obj - 2 else (0.15 if pendiente > 3 else 0.0)
            self.refuerzo = max(0.0, getattr(self, "refuerzo", 0.0) - caida * dt)
        if self.refuerzo > 0 and freno == 0:
            acel = min(1.0, max(acel, acel_max) + self.refuerzo)
        acel = max(0.0, acel)
        self.acel_prev = acel
        self.freno_prev = freno
        self.kmh_pred = vpred
        return acel, freno

    def velocidad_predicha(self, ahora):
        """Estima la velocidad ACTUAL a partir de las últimas lecturas del HUD (que llegan tarde)."""
        v = self.cfg["velocidad"]
        lect = getattr(self, "lecturas", [])
        if not lect or lect[-1][1] != self.kmh:
            lect = (lect + [(ahora, self.kmh)])[-3:]
            self.lecturas = lect
        if len(lect) < 2:
            return float(self.kmh), 0.0
        (t1, v1), (t2, v2) = lect[-2], lect[-1]
        if ahora - t2 > 1.2 or t2 - t1 < 0.2:     # sin cambios hace rato: velocidad estable
            return float(self.kmh), 0.0
        pendiente = max(-40.0, min(40.0, (v2 - v1) / (t2 - t1)))   # km/h por segundo
        adelanto = min(0.8, (ahora - t2) + v["retraso_hud_seg"])
        return max(0.0, v2 + pendiente * adelanto), pendiente

    # ------------------------------------------------------------ paso
    def paso(self, img, dt, kmh=None):
        cfg = self.cfg
        ahora = time.time()
        if kmh is not None:
            self.kmh = kmh
        if self.kmh < 3 and self.estado in ("CONDUCIENDO", "ARRANCANDO"):
            self.t_lento_desde = getattr(self, "t_lento_desde", None) or ahora
        else:
            self.t_lento_desde = None
        self.actualizar_movimiento(img)
        self.odo += max(0.0, float(self.kmh or 0)) / 3.6 * max(0.0, min(dt, 0.5))
        self._actualizar_dist_fina()
        res = vision.analizar(img, cfg, self.ang_previo)
        self.filtrar_marcador(res, ahora)
        res["dist_hud"] = self.dist_punto()
        res = self.filtrar_salto_ruta(res, img, ahora)
        self.res_ult = res
        cc = cfg.get("calle", {})
        if res["encontrada"] and res.get("en_calle", 1.0) < cc.get("fuera_umbral", 0.35):
            self.t_fuera_calle = getattr(self, "t_fuera_calle", None) or ahora
        else:
            self.t_fuera_calle = None
        self.fuera_de_calle = (self.t_fuera_calle is not None and
                               ahora - self.t_fuera_calle > cc.get("fuera_seg", 0.4))
        if res["encontrada"]:
            self.ang_previo = res["ang_cerca"]
            self.t_ultima_ruta = ahora
            if self.t_ruta_visible_desde is None:
                self.t_ruta_visible_desde = ahora
        else:
            self.t_ruta_visible_desde = None

        direccion = acel = freno = 0.0
        e = self.estado

        # v38: grabación pendiente (tras cargado/descargado): arranca cuando el juego suelta el camión
        if self.grab_pendiente is not None and e in ("INACTIVO", "ESPERANDO_RUTA") and self.kmh < 2 \
                and not (self.pantalla.get("menu") or self.pantalla.get("barra")) \
                and ahora - self.t_estado > 1.0:
            g, self.grab_pendiente = self.grab_pendiente, None
            self.iniciar_reproduccion(g)
            e = self.estado
        # v38: punto final con grabación (vuelta)
        if e == "CONDUCIENDO" and self.tramo == 2 and self._grabs_ahora() and getattr(self, "vuelta_lejos", False) \
                and self.grab_final_hecha != self.t_fin_juego_ref():
            d_ = self.dist_punto()
            g = self.grab_mod.buscar(self._grabs_ahora(), "final", getattr(self, "recorrido", None), 2, d_, 25) \
                if d_ is not None else None
            if g is not None and d_ <= float(g["disparo"].get("metros", 0)):
                self.grab_final_hecha = self.t_fin_juego_ref()
                self.iniciar_reproduccion(g)
                e = self.estado

        if e == "GRABANDO":
            self.grabadora.muestra(self.kmh, self.dist_punto(), self.dist_fina(),
                                   res.get("desvio_cerca") if res.get("encontrada") else None,
                                   res.get("en_calle", 1.0) if res.get("encontrada") else None)
            self.motivo = "grabando"
            return res, (0, 0, 0)

        if e == "REPRODUCIENDO":
            if self.repro is None:
                self.cambiar("INACTIVO")
                return res, (0, 0, 0)
            d_, a_, f_, fin = self.repro.paso(self.kmh, dt)
            self.motivo = f"grabación {self.repro.progreso() * 100:.0f}%"
            self.kmh_obj = self.repro.m[self.repro.i][4]
            if fin:
                g = self.repro.g
                mot = self.repro.motivo_fin
                self.repro = None
                ok = mot == "fin de la grabación"
                print(f"\n[{'OK' if ok else '!'}] Grabación \"{g.get('nombre', '?')}\": {mot}.")
                if ok and g.get("al_terminar") == "seguir":
                    self.cambiar("ARRANCANDO")
                else:
                    self.cambiar("INACTIVO", None if ok else f"grabación interrumpida: {mot}")
                    if not ok:
                        self.incidente(f"grabación interrumpida: {mot}")
                return res, (0, 0, 0)
            self.ctrl.set(d_, a_, f_)
            return res, (d_, a_, f_)

        if e in ("ARRANCANDO", "CONDUCIENDO"):
            if not self.juego_con_foco() and self.cfg["control"].get("backend") == "teclado":
                self.ctrl.soltar_todo()               # con teclado: pausa (las teclas irían al bloc de notas)
                return res, (0, 0, 0)
            if e == "ARRANCANDO" and (self.kmh >= 8 or ahora - self.t_estado > 6):
                self.cambiar("CONDUCIENDO")
            # v37: regla "entregar_control" (p. ej. entrada a la granja sin caminos): frenar y pasar a INACTIVO
            rg = self.regla or {}
            clave = (self.tramo, rg.get("nota"))
            if rg.get("entregar_control") and getattr(self, "control_entregado", None) != clave:
                if self.kmh >= 1:
                    self.motivo = "tramo manual"
                    self.kmh_obj = 0
                    fr = 0.6 if self.kmh > 3 else 0.0          # parado, el freno sería marcha atrás
                    self.ctrl.set(0.0, 0.0, fr)
                    return res, (0.0, 0.0, fr)
                self.control_entregado = clave           # si lo reactivas aquí, no vuelve a parar
                g = self.grab_mod.buscar(self._grabs_ahora(), "distancia", getattr(self, "recorrido", None), self.tramo,
                                         rg.get("desde"))
                if g is not None:
                    self.iniciar_reproduccion(g)
                    return res, (0, 0, 0)
                print(f"\n[i] Tramo manual: llévalo tú ({rg.get('nota', '')}). Actívalo de nuevo cuando quieras.")
                self.cambiar("INACTIVO", "tramo manual: control entregado")
                return res, (0, 0, 0)
            # 2.1.0: grabación "al llegar a X m": ir bajando, parar justo ahí y repetirla (con o sin regla)
            self.lim_grab = None
            d_g = getattr(self, "dist_filtrada", None)
            if d_g is None:
                d_g = self.dist_punto()
            g = self.grab_mod.buscar(self._grabs_ahora(), "distancia", getattr(self, "recorrido", None), self.tramo, d_g, 60) \
                if self._grabs_ahora() and d_g is not None else None
            if g is not None and self.tramo == 1 and float(g["disparo"].get("metros") or 0) >= 1000:
                g = None          # en la ida solo valen las del final (p. ej. entrada a la granja)
            if g is not None and float(g["disparo"].get("metros") or 0) >= 1000 and \
                    not (e == "ARRANCANDO" and self.kmh < 3):
                g = None          # 2.1.1: las que empiezan lejos (salida del punto A) solo al activar parado
            if g is not None and g.get("_archivo") not in self.grab_hecha:
                m_g = float(g["disparo"].get("metros") or 0)
                if d_g > m_g + 2 and not (self.kmh < 3 and d_g <= m_g + 8):
                    self.lim_grab = 12 + 0.8 * (d_g - m_g)          # llegar despacio al punto de inicio
                elif self.kmh > 3:
                    self.motivo = "parando para la grabación"
                    self.kmh_obj = 0
                    self.ctrl.set(0.0, 0.0, 0.7)
                    return res, (0.0, 0.0, 0.7)
                elif self.kmh >= 1:
                    # 2.1.1: casi parado: soltar todo (frenar parado en GTA es marcha atrás)
                    self.motivo = "parando para la grabación"
                    self.kmh_obj = 0
                    self.ctrl.set(0.0, 0.0, 0.0)
                    return res, (0.0, 0.0, 0.0)
                else:
                    self.grab_hecha.add(g.get("_archivo"))
                    self.iniciar_reproduccion(g)
                    return res, (0, 0, 0)
            # 2.1.0: trazado grabado en esta distancia
            self.traz = self.grab_mod.trazado_en(self.trazados, getattr(self, "recorrido", None), self.tramo,
                                                 self.dist_fina(), comunes=self.experimental("trazados_comunes_vuelta")
                                                 ) if self.trazados else None
            es = cfg.get("esquinas", {})
            largo_ruta = res["puntos"][-1][2] if res.get("puntos") else 0
            # final del tramo: ir directo al marcador de destino hasta entrar en él
            aprox = self.paso_aproximacion(res, largo_ruta, ahora, dt)
            if aprox is not None:
                if aprox == "llegado":
                    return res, (0, 0, 0)
                direccion, acel, freno = aprox
                self.ctrl.set(direccion, acel, freno)
                return res, (direccion, acel, freno)
            if res["encontrada"] and abs(res["rumbo"]) >= es.get("maniobra_rumbo_grados", 110) \
                    and self.kmh <= es.get("maniobra_kmh_max", 15) \
                    and not res["cerca_destino"] and largo_ruta > 40:
                self.t_ruta_atras = getattr(self, "t_ruta_atras", None) or ahora
            else:
                self.t_ruta_atras = None
            if self.t_ruta_atras is not None and ahora - self.t_ruta_atras > es.get("maniobra_seg", 1.0):
                self.t_ruta_atras = None
                intentos = [t for t in getattr(self, "maniobras", []) if ahora - t < 40]
                if len(intentos) >= es.get("maniobra_max_intentos", 4):
                    print("\n[!] No consigo tomar este giro. Autopiloto desactivado: toma el control.")
                    self.maniobras = []
                    self.cambiar("INACTIVO", "no consigue tomar el giro (4 maniobras)")
                    return res, (0, 0, 0)
                self.maniobras = intentos + [ahora]
                print(f"\n[!] La ruta quedó atrás (rumbo {res['rumbo']:+.0f}°): maniobra marcha atrás  {self.lugar()}")
                self.incidente(f"ruta atrás: maniobra (rumbo {res['rumbo']:+.0f})")
                self.iniciar_recuperacion(res, es.get("maniobra_reversa_seg", 2.5), alternar=False)
                return res, (0, 0, 0)
            if res["encontrada"]:
                direccion = self.calcular_direccion(res, dt)
                direccion = self.limitar_tras_choque(direccion, res, ahora, dt)
                acel, freno = self.calcular_pedales(res, dt)
            elif ahora - self.t_ultima_ruta > cfg["etapas"]["llegada_seg"]:
                d_ = self.dist_punto()
                print(f"\n[i] Ruta GPS desaparecida{'' if d_ is None else f' (a {_km(d_)} del punto)'}: "
                      f"espero al juego.  {self.lugar()}")
                self.esperar_juego()
                return res, (0, 0, 0)
            else:
                self.direccion *= 0.85        # pérdida breve: recto y suave
                direccion, acel = self.direccion, 0.3

            # atasco: acelerando pero sin moverse, o choque (caída brusca de velocidad sin frenar)
            a = cfg["atasco"]
            self.hist_vel = [(t, k, fr) for t, k, fr in getattr(self, "hist_vel", [])
                             if ahora - t <= a["choque_ventana_seg"]] + [(ahora, self.kmh, freno)]
            if self.vel is not None:
                quieto = self.kmh <= a["kmh_max"]
                vmax = max(k for _, k, _ in self.hist_vel)
                # el HUD muestra la velocidad con retraso: una caída justo después de frenar no es un choque
                if freno > 0:
                    self.t_ultimo_freno = ahora
                frenando = (any(fr > 0 for _, _, fr in self.hist_vel) or
                            ahora - getattr(self, "t_ultimo_freno", -99) < a["choque_ventana_seg"] + 1.0)
                choque = (vmax - self.kmh >= a["choque_caida_kmh"] and self.kmh < 10 and not frenando)
                # v33: si en este momento no se ve el minimapa (pantalla tapada, tirón del juego), la
                # lectura de 0 km/h no es fiable: no es un choque
                if choque and (not res["encontrada"] or ahora - self.t_ultima_ruta > 0.3):
                    if ahora - getattr(self, "t_aviso_falso", -99.0) > 5:
                        print(f"\n[i] Caída de velocidad ({vmax}->{self.kmh}) sin ver el minimapa: no la tomo como choque.")
                        self.incidente(f"posible falso choque ignorado ({vmax}->{self.kmh} km/h, sin minimapa)")
                        self.t_aviso_falso = ahora
                    choque = False
            else:
                quieto = self.mov < a["umbral_movimiento"]
                choque = False
            self.hist_volante = [(t_, d_) for t_, d_ in self.hist_volante if ahora - t_ <= 1.5] + [(ahora, direccion)]
            if a["activo"] and choque:
                print(f"\n[!] Choque detectado ({vmax}->{self.kmh} km/h): marcha atrás  {self.lugar()}")
                self.incidente(f"choque ({vmax}->{self.kmh} km/h)")
                self.iniciar_recuperacion(res)
            elif a["activo"] and acel > 0.85 and quieto:
                self.t_quieto_desde = self.t_quieto_desde or ahora
                if ahora - self.t_quieto_desde > a["segundos"]:
                    print(f"\n[!] Atascado: marcha atrás  {self.lugar()}")
                    self.incidente("atascado")
                    self.iniciar_recuperacion(res)
            else:
                self.t_quieto_desde = None

        elif e == "RECUPERANDO" and self.kmh > cfg["atasco"].get("cancelar_reversa_kmh", 20) \
                and ahora - self.t_estado < 3.0:
            # v33: el camión sigue avanzando rápido: no hubo choque (lectura falsa). Volver a conducir.
            print(f"\n[!] Marcha atrás cancelada: el camión sigue avanzando a {self.kmh} km/h.")
            self.incidente(f"marcha atrás cancelada (seguía a {self.kmh} km/h)")
            self.reversa_fuerza_tmp = None
            self.recto_pendiente = None
            self.cambiar("ARRANCANDO")
        elif e == "RECUPERANDO":
            # marcha atrás suave: gatillo moderado y se suelta si ya va rápido hacia atrás
            at = cfg["atasco"]
            vmax_r = at.get("reversa_kmh_max", 6)
            f_rev = getattr(self, "reversa_fuerza_tmp", None) or at.get("reversa_fuerza", 0.55)
            if self.kmh < vmax_r * 0.6:
                fr = f_rev
            elif self.kmh < vmax_r:
                fr = f_rev * 0.5
            else:
                fr = 0.0
            direccion, acel, freno = getattr(self, "dir_reversa", 0.0), 0.0, fr
            if ahora - self.t_estado > getattr(self, "reversa_dur", cfg["atasco"]["reversa_seg"]):
                self.ctrl.soltar_todo()
                time.sleep(0.4)
                self.direccion = 0.0
                self.recto = getattr(self, "recto_pendiente", None)
                self.recto_pendiente = None
                self.reversa_fuerza_tmp = None
                if self.recto:
                    print(f"[i] Choque girando: avanzo ~{self.recto['meta']:.0f} m casi recto antes de volver a girar.")
                self.cambiar("ARRANCANDO")

        elif e == "ESPERANDO_RUTA":
            if self.pantalla.get("menu") or self.pantalla.get("barra"):
                self.t_ruta_visible_desde = None          # el juego aún tiene el control
            md = res.get("marcador_dist")
            m_ = cfg["minimapa"]
            esc = min(m_["w"], m_["h"]) / 176.0
            largo = res["puntos"][-1][2] if res.get("puntos") else 0
            if md is not None and md < cfg.get("etapas_pantalla", {}).get("aproximar_px", 35) * esc \
                    and largo < md + 15 * esc:
                self.t_ruta_visible_desde = None          # es el resto de la ruta al marcador, no una nueva
            d_cerca = self.dist_punto()
            if d_cerca is not None and d_cerca < 60 and largo < 25 * esc:
                self.t_ruta_visible_desde = None          # 2.3.0: pedacito de ruta junto al punto (sin marcador)
            cj = self.conf
            if cj["juego_visto"] and not (self.pantalla.get("menu") or self.pantalla.get("barra")):
                cj["t_fin_juego"] = cj.get("t_fin_juego") or ahora
            if (self.t_ruta_visible_desde is not None and
                    ahora - self.t_ruta_visible_desde > cfg["etapas"]["ruta_estable_seg"]):
                d_ = self.dist_punto()
                nueva = (cj["juego_visto"] or not self.confirmar_con_pantalla() or
                         (d_ is not None and cj["dist"] is not None and d_ > max(200.0, cj["dist"] + 150.0)))
                de = getattr(self, "d_espera", None)
                if nueva and getattr(self, "tramo_notif", None) is None and de is not None and de > 400 and \
                        d_ is not None and abs(d_ - de) < 400:
                    # 2.4.1: la ruta se perdió lejos del punto (a 5,48 km, tras salir de la granja) y volvió la
                    # misma: no es una etapa nueva (antes pasaba de la vuelta a "camino a cargar")
                    print(f"\n[i] La ruta volvió ({_km(d_)}): sigo en el tramo {self.tramo}.")
                    self.t_ruta_visible_desde = None
                    self.cambiar("ARRANCANDO")
                elif nueva:
                    if getattr(self, "tramo_notif", None) is not None:
                        self.tramo = self.tramo_notif        # la notificación dice la etapa exacta
                        self.tramo_notif = None
                    elif self.tramo >= 2:
                        print("[i] Nueva ruta después del punto final: empiezo un trabajo nuevo (tramo 0).")
                        self.tramo = 0
                    else:
                        self.tramo += 1
                    print(f"[i] Nueva ruta{'' if d_ is None else f' ({_km(d_)})'}. "
                          f"Tramo {self.tramo}: {cfg['etapas']['tramos'][self.tramo]}")
                    self.conf_reset()
                    ep_ = cfg.get("etapas_pantalla", {})
                    if self.grab_pendiente is not None:
                        g, self.grab_pendiente = self.grab_pendiente, None
                        self.iniciar_reproduccion(g)          # v38: tu grabación reemplaza el retroceso
                    elif self.tramo == 1 and ep_.get("retroceso_tras_cargar_seg", 0) > 0:
                        self.iniciar_retroceso_carga(ep_, res)
                    else:
                        self.cambiar("ARRANCANDO")
                elif not cj["no_llego"] and ahora - self.t_estado > 2.0:
                    # misma ruta, mismo punto, el juego no reaccionó: aún no hemos llegado
                    print(f"[i] Aún no llego al punto{'' if d_ is None else f' ({_km(d_)})'}: sigo.")
                    self.t_ruta_visible_desde = None
                    self.cambiar("ARRANCANDO")
            # v30: el trabajo solo se da por TERMINADO con la notificación "Trabajo completado"
            # (antes: tramo 2 + 5 s sin ver ruta, y eso cortaba la vuelta tras "descargado")

        if self.estado in ("ARRANCANDO", "CONDUCIENDO"):           # 3.7.0: YOLO puede frenar o hacer esperar
            acel, freno = self._yolo_frenar(acel, freno, ahora)
        if self.estado in ("ARRANCANDO", "CONDUCIENDO", "RECUPERANDO"):
            self.ctrl.set(direccion, acel, freno)
        return res, (direccion, acel, freno)

    def iniciar_retroceso_carga(self, ep, res=None):
        """v30: recién cargado, retroceder un poco recto: más espacio para girar hacia el puente."""
        print(f"[i] Camión cargado: retrocedo un poco ({ep.get('retroceso_tras_cargar_seg', 0.9):.1f} s) "
              f"para tener espacio al girar.")
        self.recto_pendiente = None
        self.recto = None
        # v32: si la ruta sale torcida (p. ej. 60° a la izquierda), retroceder con el volante hacia el
        # otro lado: la trompa gira hacia la ruta y el camión arranca más derecho
        rb = res.get("rumbo") if res and res.get("encontrada") else None
        vol = ep.get("retroceso_tras_cargar_volante", 0.5)
        self.dir_reversa = 0.0 if rb is None or abs(rb) < 15 else (-vol if rb > 0 else vol)
        self.reversa_dur = ep.get("retroceso_tras_cargar_seg", 0.9)
        self.reversa_fuerza_tmp = ep.get("retroceso_tras_cargar_fuerza", 0.5)
        self.t_retroceso_carga = time.time()
        self.hist_vel = []
        self.t_quieto_desde = None
        self.cambiar("RECUPERANDO")

    def iniciar_recuperacion(self, res, duracion=None, alternar=True):
        """Marcha atrás girando al revés de hacia donde queremos ir (así el morro apunta a la ruta)."""
        a = self.cfg["atasco"]
        ahora = time.time()
        recientes = [t for t in getattr(self, "recuperaciones", []) if ahora - t < 15]
        self.recuperaciones = recientes + [ahora]
        n = len(recientes)
        c = self.cfg["control"]
        err = (res["rumbo"] + c["peso_desvio"] * res["desvio"]) if res.get("encontrada") else -self.direccion
        lado = -1.0 if err > 0 else 1.0
        if alternar and n % 2 == 1:
            lado = -lado            # si ya lo intentamos, probar hacia el otro lado
        # ¿chocó GIRANDO? (p. ej. un poste por dentro de la curva). Marcha atrás con el volante hacia
        # ese mismo lado (el morro se aleja del obstáculo) y luego avanzar casi recto unos metros.
        vol = [d_ for t_, d_ in self.hist_volante if ahora - t_ <= 1.5]
        media = sum(vol) / len(vol) if vol else 0.0
        self.recto = None
        if alternar and abs(media) >= 0.3 and a.get("recto_tras_choque_m", 5.0) > 0:
            s_ = 1.0 if media > 0 else -1.0
            lado = s_
            self.choques_giro = [t_ for t_ in self.choques_giro if ahora - t_ < 40] + [ahora]
            rep = len(self.choques_giro) - 1
            self.recto_pendiente = {"lado": s_, "m": 0.0, "t0": None,
                                    "meta": a.get("recto_tras_choque_m", 5.0) +
                                    a.get("recto_tras_choque_extra_m", 3.0) * min(rep, 3)}
        else:
            self.recto_pendiente = None
        self.hist_volante = []
        self.dir_reversa = 0.8 * lado
        self.reversa_fuerza_tmp = None
        self.reversa_dur = (duracion if duracion is not None else a["reversa_seg"]) + \
            a["reversa_extra_si_repite"] * min(n, 2)
        self.hist_vel = []
        self.t_quieto_desde = None
        self.cambiar("RECUPERANDO")

    def filtrar_marcador(self, res, ahora):
        """Un marcador que aparece de golpe pegado al camión casi siempre es un falso positivo
        (p. ej. la sombra de la flecha sobre la ruta). Solo se acepta cerca si antes se le vio
        acercarse desde más lejos."""
        md = res.get("marcador_dist")
        m = self.cfg["minimapa"]
        esc = min(m["w"], m["h"]) / 176.0
        if md is None:
            return
        ult = getattr(self, "mk_ult", None)
        seguido = ult is not None and ahora - ult[1] < 3.0 and abs(md - ult[0]) < 10 * esc
        d_hud = self.dist_punto()
        cerca_hud = d_hud is not None and d_hud < 80      # el minimapa dice que el punto está cerca
        lejos_hud = d_hud is not None and d_hud > 300
        if md < 20 * esc and (lejos_hud or not (seguido or cerca_hud)):
            res["marcador_dist"] = res["marcador_ang"] = None
            return
        self.mk_ult = (md, ahora)

    # ------------------------------------------------------------ etapas y llegada
    def conf_reset(self):
        self.conf = {"juego_visto": False, "dist": None, "no_llego": False, "t_fin_juego": None}

    def confirmar_con_pantalla(self):
        ep = self.cfg.get("etapas_pantalla", {})
        return ep.get("activo", True) and ep.get("confirmar_etapas", True)

    def _yolo_paso(self, res):
        """3.6.0: le pasa al vigía la velocidad y la curva; anota (solo anota) cuando «habría frenado»."""
        self.yolo.contexto(self.kmh, res.get("giro_adelante") or 0.0)
        est = self.yolo.ultima()
        self.yolo_est = est
        acc = est.get("accion") or "nada"
        frena = self.experimental("yolo_frena")
        if acc != self._yolo_accion_ant and self.estado == "CONDUCIENDO":
            if acc in ("frenar", "frenar a fondo", "esperar") and not frena:
                txt = f"YOLO (sombra): habría {acc.upper()}: {est.get('texto')}"
                print(f"\n[i] {txt}")
                self.evento = (self.evento + " | " if self.evento else "") + txt
        self._yolo_accion_ant = acc

    def _yolo_frenar(self, acel, freno, ahora):
        """3.7.0 (etapa 2) y 3.8.0 (etapa 3): YOLO maneja en estos casos:
        - «frenar a fondo» (choca en menos de ~1 s): freno a fondo, sin acelerar, al menos 0,8 s.
        - «frenar» (choca en menos de 2 s, o a menos de 1 s de camino del de adelante): freno suave según lo
          cerca (30-80 %), al menos 0,5 s; al soltar, 1,5 s con el acelerador limitado al 30 %.
        - «esperar» (parado con algo delante a menos de ~12 m): no arranca, freno suave para quedarse quieto.
        «seguir» sigue en sombra. Se apaga en Experimental («YOLO frena de verdad») o por regla."""
        if self.yolo is None or not self.experimental("yolo_frena"):
            return acel, freno
        est = self.yolo_est or {}
        acc = est.get("accion") or "nada"
        fresco = ahora - float(est.get("t") or 0) < 0.5            # detección de hace menos de medio segundo
        if fresco and acc == "frenar a fondo":
            self._yolo_freno_hasta = ahora + 0.8
        if fresco and acc == "frenar":                     # 3.8.0 (etapa 3): frenar suave, según lo cerca
            self._yolo_suave_hasta = ahora + 0.5
            self._yolo_suave_nivel = self._yolo_nivel_freno(est)
        activo = None
        if ahora < getattr(self, "_yolo_freno_hasta", 0.0):
            activo = "frenar a fondo"
        elif ahora < getattr(self, "_yolo_suave_hasta", 0.0):
            activo = "frenar"
        elif fresco and acc == "esperar" and (self.kmh or 0) < 3:
            # no esperar para siempre a algo quieto (un NPC parado, un auto estacionado mal visto)
            oid = (est.get("causa") or {}).get("id")
            if oid != getattr(self, "_yolo_espera_id", None):
                self._yolo_espera_id, self._yolo_espera_t0 = oid, ahora
            maximo = float((self.cfg.get("yolo") or {}).get("esperar_max_s", 10.0))
            if ahora - self._yolo_espera_t0 < maximo:
                activo = "esperar"
            elif not getattr(self, "_yolo_espera_avisado", None) == oid:
                self._yolo_espera_avisado = oid
                print(f"\n[i] YOLO: lleva {maximo:.0f} s delante y no se mueve; sigo (tómalo tú si hace falta).")
        if activo is None:
            if getattr(self, "_yolo_actuando", None):
                if self._yolo_actuando in ("frenar", "frenar a fondo"):
                    self._yolo_tope_hasta = ahora + 1.5        # 3.8.0: no acelerar de golpe tras frenar
                print("\n[i] YOLO: libre, sigo.")
                self._yolo_actuando = None
            if ahora < getattr(self, "_yolo_tope_hasta", 0.0):
                return min(acel, 0.3), freno
            return acel, freno
        if activo != getattr(self, "_yolo_actuando", None):
            txt = est.get("texto") or ""
            if activo == "frenar":
                txt += f" (freno {self._yolo_suave_nivel * 100:.0f} %)"
            print(f"\n[!] YOLO: {({'frenar a fondo': 'FRENO A FONDO', 'frenar': 'FRENO'}).get(activo, 'ESPERO')}: {txt}")
            self.evento = (self.evento + " | " if self.evento else "") + f"YOLO {activo}: {txt}"
            if self.ui is not None:
                try:
                    self.ui.notificar("problema", "YOLO: " + ({"frenar a fondo": "frenó a fondo",
                                                               "frenar": "frenó"}).get(activo, "espera"), txt)
                except Exception:  # noqa
                    pass
            self._yolo_actuando = activo
        self.motivo = "YOLO " + activo
        if activo == "frenar a fondo":
            return 0.0, 1.0
        if activo == "frenar":
            return 0.0, max(freno, float(getattr(self, "_yolo_suave_nivel", 0.35)))
        return 0.0, max(freno, 0.3)

    def _yolo_nivel_freno(self, est):
        """3.8.0: fuerza del freno para «frenar»: por el tiempo hasta chocar (2 s -> 35 %, 1 s -> 80 %) y por lo
        pegado que va (a menos de 1 s de camino del de adelante: de 30 % a 70 %). El mayor de los dos."""
        c = est.get("causa") or {}
        nivel = 0.3
        ttc = c.get("ttc")
        if ttc is not None:
            k = max(0.0, min(1.0, (2.0 - float(ttc)) / 1.0))
            nivel = max(nivel, 0.35 + 0.45 * k)
        v = (self.kmh or 0) / 3.6
        z = c.get("z")
        if z is not None and v > 0.5:
            h = float(z) / v
            if h < 1.0:
                nivel = max(nivel, 0.3 + 0.4 * (1.0 - h))
        return min(0.8, nivel)

    def _csv_yolo(self):
        est = getattr(self, "yolo_est", None) or {}
        if not est:
            return ",,,,"
        c = est.get("causa") or {}
        return (f"{est.get('accion', '')},{c.get('clase', '')},{_f(c.get('z'))},{_f(c.get('ttc'))},"
                f"{len(est.get('objetos') or [])}")

    def _csv_rumbo(self):
        r = getattr(self, "rumbo", None)
        if r is None or r.valor is None:
            return ","
        return f"{r.valor:.1f},{r.fuente}"

    def desvio_suave(self, dc, dt, res=None):
        """2.5.2 (Experimental «lado_suave_autopista»): a 70 km/h o más, la corrección de lado usa el desvío
        promediado (~0,5 s) en vez del de cada cuadro: un salto de lado de un instante (la línea del minimapa se
        corre 6-7 px sin que el camión se mueva) casi no mueve el volante. Solo en tramos rectos: con curva por
        delante (o más lento) se usa el desvío de cada cuadro, para no entrar tarde a la curva."""
        if dc is None:
            self.dc_suave = None
            return None
        cs = self.cfg.get("lado_suave", {})
        prev = getattr(self, "dc_suave", None)
        res = res or {}
        recta = abs(res.get("rumbo") or 0.0) < cs.get("rumbo_max", 10) and \
            abs(res.get("giro_adelante") or 0.0) < cs.get("giro_max", 25)
        if not self.experimental("lado_suave_autopista") or self.kmh < cs.get("kmh_desde", 70) or prev is None \
                or not recta:
            self.dc_suave = dc
            return dc
        tau = max(0.05, cs.get("segundos", 0.5))
        a = max(0.0, min(1.0, dt / (tau + dt)))
        self.dc_suave = prev + a * (dc - prev)
        return self.dc_suave

    def experimental(self, clave):
        """2.3.2: funciones en prueba (pestaña Experimental). Encendidas por defecto.
        3.5.0: una regla (de un lugar o general) puede prenderlas o apagarlas en su zona («exp»)."""
        e = (getattr(self, "regla", None) or {}).get("exp") or {}
        if clave in e:
            return bool(e[clave])
        return bool(self.cfg.get("experimental", {}).get(clave, True))

    def _hud_metros(self):
        return self.hud.estado.get("metros") if self.hud else None

    def dist_punto(self):
        """Distancia al punto del HUD; 3.2.3: si la lectura es un dígito mal leído (5090 en vez de 5690),
        la que cuadra con lo recorrido."""
        m = self._hud_metros()
        c = getattr(self, "_corr_dist", None)
        if c is not None and m is not None and m == c["raw"]:
            return c["v"]
        return m

    def _corregir_distancia(self, m):
        """3.2.3: una lectura que no cuadra con lo que el camión anduvo (más de 150 m de diferencia) y que,
        cambiando UN dígito de los que se confunden, sí cuadra, se toma como mal leída y se reemplaza por la
        distancia esperada (la última buena menos lo recorrido). Los saltos reales del GPS no se tocan."""
        self._corr_dist = None
        ref = getattr(self, "_dref", None)
        if m is None or ref is None or ref["tramo"] != self.tramo or self.rutas_mod is None:
            return m
        recorrido = max(0.0, self.odo - ref["odo"])
        esperado = ref["d"] - recorrido
        # 3.2.7: margen que crece con lo recorrido desde la referencia (el odómetro por velocidad también se desvía)
        if abs(m - esperado) <= 150 + 0.1 * recorrido or esperado < 300:
            return m
        try:
            variantes = self.rutas_mod._variantes(m)
        except Exception:  # noqa
            return m
        if not any(abs(v - esperado) <= 100 for v in variantes):      # 3.2.7: 100 m (5,00 leído por 5,67)
            return m
        v = float(round(esperado))
        self._corr_dist = {"raw": m, "v": v}
        if getattr(self, "_corr_aviso", None) != m:
            self._corr_aviso = m
            print(f"\n[i] Distancia mal leída: {_km(m)} -> uso {_km(v)} (cuadra con lo recorrido).")
            self.incidente(f"distancia mal leída: {m:.0f} -> {v:.0f}")
        return v

    def esperar_juego(self):
        """Hemos llegado (o la ruta desapareció): esperar el menú/barra y la ruta siguiente."""
        if not self.conf["juego_visto"]:
            self.conf["dist"] = self.dist_punto()
        self.d_espera = self.dist_punto()            # 2.4.1: a qué distancia del punto empezó a esperar
        self.aprox = False
        self.cambiar("ESPERANDO_RUTA")

    def llegada_o_bloqueo(self, res, ahora):
        """Parado junto al marcador sin que el juego reaccione: ¿estamos en el punto o algo nos tapa?"""
        ep = self.cfg.get("etapas_pantalla", {})
        d_ = self.dist_punto()
        if d_ is None or d_ <= ep.get("llegada_m", 8):
            print(f"[OK] En el punto{'' if d_ is None else f' ({_km(d_)})'}: espero al juego.  {self.lugar()}")
            self.incidente(f"en el punto{'' if d_ is None else f' ({_km(d_)})'}, esperando al juego")
            self.esperar_juego()
            return "llegado"
        self.bloqueos_punto = [t for t in getattr(self, "bloqueos_punto", []) if ahora - t < 90] + [ahora]
        if len(self.bloqueos_punto) > ep.get("intentos_llegar", 3):
            self.bloqueos_punto = []
            print(f"\n[!] No consigo llegar al punto (a {_km(d_)}). Llévalo tú: el autopiloto sigue solo "
                  f"cuando aparezca el menú o la barra.  {self.lugar()}")
            self.incidente(f"no llega al punto (a {_km(d_)})")
            self.esperar_juego()
            self.conf["no_llego"] = True
            return "llegado"
        if (self.regla or {}).get("sin_reversa"):
            # 2.1.0: aquí retroceder es peor (árboles): dejar el final al jugador
            print(f"\n[i] Parado a {_km(d_)} del punto: aquí no retrocedo. Llévalo tú.  {self.lugar()}")
            self.cambiar("INACTIVO", f"cerca del punto ({_km(d_)}): llévalo tú")
            self.avisar("etapa", "Llévalo tú", f"Estás a {_km(d_)} del punto; aquí no retrocedo.")
            return "llegado"
        print(f"\n[!] Parado a {_km(d_)} del punto sin llegar: marcha atrás y otro intento.  {self.lugar()}")
        self.incidente(f"bloqueado a {_km(d_)} del punto")
        self.iniciar_recuperacion(res)
        return "llegado"

    def limitar_tras_choque(self, direccion, res, ahora, dt):
        """Tras chocar girando: no volver a girar hacia el obstáculo hasta avanzar unos metros."""
        r = self.recto
        if not r:
            return direccion
        a = self.cfg["atasco"]
        r["t0"] = r["t0"] or ahora
        r["m"] += max(0.0, self.kmh) / 3.6 * dt
        if r["m"] >= r["meta"] or ahora - r["t0"] > 15 or abs(res.get("rumbo") or 0) >= 110:
            self.recto = None
            return direccion
        tope = a.get("recto_tras_choque_volante", 0.15)
        if r["lado"] > 0:
            direccion = min(direccion, tope)
        else:
            direccion = max(direccion, -tope)
        self.direccion = direccion
        return direccion

    def paso_aproximacion(self, res, largo_ruta, ahora, dt):
        """Al final del tramo, ir directo al marcador (círculo rojo) hasta entrar en él.
        Devuelve None (conducción normal), (dir, acel, freno) o "llegado"."""
        ep = self.cfg.get("etapas_pantalla", {})
        if not ep.get("aproximar_marcador", True):
            self.aprox = False
            return None
        m = self.cfg["minimapa"]
        esc = min(m["w"], m["h"]) / 176.0
        md, ma = res.get("marcador_dist"), res.get("marcador_ang")
        llegar = ep.get("llegar_px", 4) * esc
        if md is not None:
            # se sigue la ruta hasta que se acaba (o se pierde) y entonces se va directo al marcador
            ruta_acaba = (not res["encontrada"]) or largo_ruta < 12 * esc
            cerca = md < ep.get("aproximar_px", 35) * esc * (1.0 if res["encontrada"] else 1.7)
            if cerca and ruta_acaba:
                if not self.aprox:
                    print("\n[i] Cerca del destino: voy directo al marcador.")
                self.aprox = True
                self.t_aprox_visto = ahora
            elif self.aprox and md > ep.get("aproximar_px", 35) * esc * 1.8:
                self.aprox = False
        elif self.aprox and ahora - self.t_aprox_visto > 1.0 and res["encontrada"] and largo_ruta > 30 * esc:
            self.aprox = False                       # apareció ruta otra vez: seguirla
        if not self.aprox:
            self.t_en_marcador = None
            self.aprox_rev = None
            self.aprox_md_ult = 99
            self.aprox_recto_hecho = 0.0
            self.aprox_recto_t = 0.0
            return None
        # marcador tapado por la flecha del camión, o muy cerca (o justo detrás): hemos llegado
        if md is not None:
            self.aprox_md_ult = md
        # la distancia del minimapa manda: si dice que aún faltan metros, NO estamos en el punto
        # aunque el marcador no se vea (la línea roja lo tapa) o parezca encima
        d_hud = self.dist_punto()
        lejos = d_hud is not None and d_hud > ep.get("llegada_m", 8)
        oculto = md is None and getattr(self, "aprox_md_ult", 99) < 3 * llegar     # tapado por la flecha
        if md is None and (lejos or not oculto):
            # marcador no visible pero aún lejos: seguir despacio hacia donde se vio por última vez
            self.direccion *= 0.95
            self.motivo = "al marcador"
            self.kmh_obj = 8
            return self.direccion, (0.45 if self.kmh < 6 else (0.25 if self.kmh < 10 else 0.0)), 0.0
        dentro = (oculto or md <= llegar or (abs(ma) > 120 and md < 6 * esc)) and not lejos
        self.motivo = "al marcador"
        if dentro:
            self.kmh_obj = 0
            self.t_en_marcador = self.t_en_marcador or ahora
            if self.kmh <= 1 and ahora - self.t_en_marcador > 1.0:
                self.aprox = False
                self.t_en_marcador = None
                return self.llegada_o_bloqueo(res, ahora)
            self.direccion *= 0.8
            return self.direccion, 0.0, (0.45 if self.kmh > 2 else 0.2)
        self.t_en_marcador = None
        # v35: regla "aprox_recto_m" (p. ej. punto final con árboles): avanzar recto unos metros más
        # antes de doblar hacia el marcador
        # v36: por tiempo ("aprox_recto_seg", p. ej. 3 s), con acelerador suficiente para no quedarse parado
        rg = self.regla or {}
        recto_m = float(rg.get("aprox_recto_m", 0) or 0)
        recto_s = float(rg.get("aprox_recto_seg", 0) or 0)
        if (recto_m > 0 or recto_s > 0) and md is not None and abs(ma) > 30:
            hecho = getattr(self, "aprox_recto_hecho", 0.0)
            t_r = getattr(self, "aprox_recto_t", 0.0)
            if (recto_s > 0 and t_r < recto_s) or (recto_s <= 0 and hecho < recto_m):
                self.aprox_recto_hecho = hecho + max(self.kmh, 3) / 3.6 * dt
                self.aprox_recto_t = t_r + dt
                self.motivo = "al marcador (recto)"
                self.kmh_obj = 15
                self.direccion *= 0.8
                acel = 0.65 if self.kmh < 8 else (0.5 if self.kmh < 15 else 0.0)
                return self.direccion, acel, (0.3 if self.kmh > 20 else 0.0)
        # marcador muy de lado o detrás y cerca: el camión no gira tan cerrado -> marcha atrás
        # girando al revés (el morro se orienta hacia el marcador) y luego seguir hacia delante
        at = self.cfg["atasco"]
        rv = getattr(self, "aprox_rev", None)
        if rv is None and abs(ma) > 75 and md < 45 * esc and self.kmh <= 12 and not (self.regla or {}).get("sin_reversa"):
            rv = self.aprox_rev = {"t0": ahora, "lado": 1.0 if ma > 0 else -1.0}
            print("[i] Marcador muy de lado: marcha atrás para encararlo.")
        if rv is not None:
            if ahora - rv["t0"] > 10.0 or (ahora - rv["t0"] > 1.5 and abs(ma) < 35):
                self.aprox_rev = None
                self.direccion = 0.0
            else:
                self.motivo = "al marcador (atrás)"
                self.kmh_obj = 0
                if ahora - rv["t0"] < 1.0:
                    return 0.0, 0.0, 0.6                  # parar primero
                vmax_r = at.get("reversa_kmh_max", 6)
                fr = at.get("reversa_fuerza", 0.55) if self.kmh < vmax_r * 0.6 else \
                    (at.get("reversa_fuerza", 0.55) * 0.5 if self.kmh < vmax_r else 0.0)
                self.direccion = -0.8 * rv["lado"]
                return self.direccion, 0.0, max(fr, 0.51)
        obj = ep.get("objetivo_aproximar_kmh", 20)      # el juego frena el camión al llegar
        if (self.regla or {}).get("aprox_kmh"):
            obj = float(self.regla["aprox_kmh"])        # 2.1.0: por lugar
        self.kmh_obj = obj
        # parado mientras acelera hacia el marcador: el juego lo detuvo (ya llegó) o algo lo bloquea
        if self.kmh <= 1:
            self.t_aprox_parado = getattr(self, "t_aprox_parado", None) or ahora
        else:
            self.t_aprox_parado = None
            if self.kmh >= 4:
                self.aprox_empuje = None
        if self.t_aprox_parado is not None and ahora - self.t_aprox_parado > ep.get("parado_es_llegada_seg", 2.5):
            d_ = self.dist_punto()
            if d_ is not None and d_ > ep.get("llegada_m", 8):
                # antes de retroceder: acelerar más fuerte un momento (quizás solo iba muy despacio)
                emp = getattr(self, "aprox_empuje", None)
                if emp is None:
                    self.aprox_empuje = ahora
                    print(f"[i] Parado a {_km(d_)} del punto: acelero para entrar.")
                if ahora - self.aprox_empuje < ep.get("empuje_seg", 2.5):
                    objetivo = max(-1.0, min(1.0, ma / 30.0))
                    self.direccion += max(-0.1, min(0.1, objetivo - self.direccion))
                    return self.direccion, ep.get("empuje_acelerador", 0.9), 0.0
            self.aprox_empuje = None
            self.t_aprox_parado = None
            self.aprox = False
            return self.llegada_o_bloqueo(res, ahora)
        objetivo = max(-1.0, min(1.0, ma / 30.0))
        if abs(ma) > 60:
            obj = min(obj, 6)                     # muy de lado: girar despacio
        paso = self.cfg["control"]["cambio_max_por_seg"] * dt
        self.direccion += max(-paso, min(paso, objetivo - self.direccion))
        tope = interpolar(obj, self.cfg["velocidad"]["acelerador_max_por_objetivo"])
        if self.kmh < obj - 2:
            acel, freno = max(0.5, min(tope, 0.7)), 0.0
        elif self.kmh > obj + 6:
            acel, freno = 0.0, 0.15
        else:
            acel, freno = interpolar(obj, self.cfg["velocidad"]["acelerador_crucero_por_velocidad"]) + 0.05, 0.0
        return self.direccion, acel, freno

    def revisar_pantalla(self, ahora):
        """Mira la pantalla completa cada ~0.4 s: menú de carga y barras Cargando/Descargando."""
        ep = self.cfg.get("etapas_pantalla", {})
        if not ep.get("activo", True) or ahora - self.t_pantalla < ep.get("cada_seg", 0.4):
            return
        self.t_pantalla = ahora
        try:
            import pantalla_estado
            if self.sct_pantalla is None:
                import mss
                self.sct_pantalla = mss.mss()
            vr = self.cfg.get("_ventana")                    # 3.0.0: solo la ventana del juego
            if vr:
                mon = {"left": vr[0], "top": vr[1], "width": vr[2], "height": vr[3]}
            else:
                mon = self.sct_pantalla.monitors[1]
            img = cv2.cvtColor(np.asarray(self.sct_pantalla.grab(mon)), cv2.COLOR_BGRA2BGR)
            self.guardar_en_buffer(img, ahora)
            nuevo = pantalla_estado.detectar(img)
            d_m, d_fm = self.dist_punto(), getattr(self, "dist_filtrada", None)
            if (nuevo["menu"] or nuevo["barra"]) and d_m is not None and d_m > 400 and (d_fm is None or d_fm > 400):
                # 2.3.3: lejos del punto no hay menú ni barra de carga (a 4,78 km se vio una barra falsa y la
                # ida pasó a ser vuelta)
                if not getattr(self, "_aviso_barra_lejos", False):
                    print(f"\n[i] Barra/menú ignorado: faltan {_km(d_m)} para el punto.")
                    self._aviso_barra_lejos = True
                nuevo = dict(nuevo, menu=False, barra=False)
            else:
                self._aviso_barra_lejos = False
            if self.kmh > self.cfg.get("etapas_pantalla", {}).get("barra_max_kmh", 12) and \
                    self.estado in ("ARRANCANDO", "CONDUCIENDO", "RECUPERANDO"):
                nuevo = dict(nuevo, menu=False, barra=False)   # en movimiento no hay menú ni barra
            if ahora - getattr(self, "t_retroceso_carga", -99.0) < 6.0 and self.tramo == 1:
                nuevo = dict(nuevo, menu=False, barra=False)   # v30: recién cargado, aún en la zona
            if self.hud is not None and ahora - getattr(self, "t_hud", 0) >= \
                    self.cfg.get("hud_texto", {}).get("cada_seg", 1.0):
                self.t_hud = ahora
                antes_z = (self.hud.estado.get("zona"), self.hud.estado.get("calle"))
                self.hud.actualizar(img, mon.get("left", 0), mon.get("top", 0))
                ahora_z = (self.hud.estado.get("zona"), self.hud.estado.get("calle"))
                if ahora_z != antes_z and any(ahora_z):
                    print(f"\n[i] Lugar: {self.lugar()}")
                self.revisar_condicion(img, mon)
                self.revisar_ruta_y_reglas(ahora)
            self.revisar_notificacion(img, mon, ahora)
        except Exception as e:  # noqa
            if not getattr(self, "_aviso_pantalla", False):
                print(f"[!] No se pudo revisar la pantalla: {e}")
                self._aviso_pantalla = True
            return
        antes = self.pantalla
        self.pantalla = nuevo
        if nuevo["menu"] or nuevo["barra"]:
            if not self.conf["juego_visto"]:
                self.conf["dist"] = self.dist_punto()
            self.conf["juego_visto"] = True
            self.conf["t_fin_juego"] = None
        if nuevo["menu"] and not antes["menu"]:
            print("\n[i] Menú CARGAR CAMIÓN abierto: elige el cargamento.")
        if nuevo["barra"] and not antes["barra"]:
            que = "Cargando" if self.tramo == 0 else ("Descargando camión" if self.tramo == 1 else "Terminando")
            print(f"\n[i] {que}... (el juego tiene el control)")
            self.t_leer_carga = 0.0
        # v32: nombre del cargamento en la barra ("Cargando drogas..."), una lectura por segundo hasta tenerlo
        if nuevo["barra"] and self.tramo == 0 and not getattr(self, "cargamento", None) and \
                ahora - getattr(self, "t_leer_carga", 0.0) > 1.0:
            self.t_leer_carga = ahora
            self.leer_cargamento(img)
        if antes["barra"] and not nuevo["barra"]:
            print("[OK] Barra de progreso terminada.")
        # el juego tomó el control: soltar todo y esperar la siguiente ruta
        if (nuevo["menu"] or nuevo["barra"]) and self.estado == "GRABANDO" and not (antes["menu"] or antes["barra"]):
            print("[i] Llegaste al punto: termino la grabación aquí.")
            self.alternar_grabacion()
        if (nuevo["menu"] or nuevo["barra"]) and self.estado in ("ARRANCANDO", "CONDUCIENDO", "RECUPERANDO",
                                                                  "REPRODUCIENDO"):
            if self.estado == "REPRODUCIENDO":
                print("[OK] Llegó al punto durante la grabación.")
                self.repro = None
            self.incidente("llegada al punto (" + ("menú de carga" if nuevo["menu"] else "barra de progreso") + ")")
            self.esperar_juego()

    # ------------------------------------------------------------ rutas y reglas por lugar
    # ------------------------------------------------------------ reconocer el recorrido (2.3.1)
    REC_VENTANA_SEG = 40          # durante cuánto tiempo después de cargar se puede corregir
    REC_ACUERDO_M = 30            # cuánto pueden diferir las lecturas que "coinciden"

    def _reconocer_recorrido(self, ahora, d):
        """La distancia inicial se estima con cada lectura del HUD: distancia + lo recorrido desde que se empezó
        a buscar. Se reconoce con la mediana de las primeras lecturas y, durante 40 s, si 3 lecturas seguidas
        coinciden con OTRO recorrido, se corrige (p. ej. el HUD mostró 5630 varios segundos y era 5530)."""
        nueva = self.ruta_elegida == "__nueva__"           # 3.7.1: «Ruta nueva / desconocida»
        if self.ruta_elegida is not None and not nueva:   # 3.2.5: elegido a mano: no reconocer, solo revisar
            self._revisar_elegida(d)
            return
        if self.ruta_buscar_desde is None or self.tramo != 1 or d is None:
            return
        if d < 300:                              # ninguna ruta empieza tan cerca: esperar la distancia nueva
            self.ruta_buscar_desde = ahora
            self._rec = None
            return
        rec = getattr(self, "_rec", None)
        if rec is None:
            rec = self._rec = {"t0": ahora, "odo0": self.odo, "m": []}
        rec["m"].append(float(d) + (self.odo - rec["odo0"]))
        m = rec["m"]
        carg = getattr(self, "cargamento", None)
        if ahora - rec["t0"] > self.REC_VENTANA_SEG:
            self.ruta_buscar_desde = None
            self._rec = None
            return
        if self.ruta_act is None and not getattr(self, "_rec_desconocido", False):
            if len(m) < 2:
                return
            est = _mediana(m[-5:])
            self.dist_inicial_est = est                      # 3.7.1: para crear la ruta nueva en observaciones
            r = None if nueva else self.rutas_mod.reconocer(self.rutas, est, carg)
            if r is not None:
                d0 = r.get("distancia_inicial")
                if d0 is not None and abs(est - d0) > r.get("tolerancia", 80):
                    # 3.2.3: se reconoció cambiando un dígito: la distancia de ahora es la de la ruta menos lo recorrido
                    self._dref_semilla = float(d0) - (self.odo - rec["odo0"])
                self._fijar_recorrido(r, carg, est, "reconocido")
            elif ahora - rec["t0"] > 10 or (nueva and len(m) >= 3):
                self._rec_desconocido = True
                self.recorrido = self.rutas_mod.nombre_recorrido(None, carg, est)
                print(f"\n[i] Recorrido nuevo: {self.recorrido}. Todavía no hay reglas para él.")
                self.incidente(f"recorrido sin reglas: {self.recorrido}")
            return
        ult = m[-3:]
        if nueva or len(ult) < 3 or max(ult) - min(ult) > self.REC_ACUERDO_M:
            return
        est = _mediana(ult)
        r = self.rutas_mod.reconocer(self.rutas, est, carg)
        if r is not None and r is not self.ruta_act:
            antes = self.recorrido
            self._fijar_recorrido(r, carg, est, "corregido")
            print(f"[i] (antes: {antes})")

    def elegir_recorrido(self, archivo):
        """3.2.5: recorrido elegido a mano (None = automático). Vale hasta que termine el trabajo."""
        if not archivo or self.rutas_mod is None:
            if self.ruta_elegida is not None:
                print("[i] Recorrido: automático (se reconoce por la distancia al cargar).")
            self.ruta_elegida = None
            return
        if archivo == "__nueva__":                         # 3.7.1: ruta que el programa no conoce
            self.ruta_elegida = archivo
            self.ruta_act = None
            self.regla = None
            self._rec_desconocido = self.tramo != 1 or self.ruta_buscar_desde is None
            self.recorrido = self.rutas_mod.nombre_recorrido(None, getattr(self, "cargamento", None),
                                                             getattr(self, "dist_inicial_est", None))
            print("\n[i] Recorrido: ruta nueva / desconocida. No se usan reglas de otras rutas (solo las comunes); "
                  "al terminar puedes ponerle nombre en las observaciones.")
            return
        r = next((x for x in self.rutas.get("rutas", []) if x.get("_archivo") == archivo), None)
        if r is None:
            print(f"[!] No encuentro el recorrido {archivo} en datos/rutas.")
            return
        self.ruta_elegida = archivo
        self._aviso_elegida = False
        self._aplicar_elegida()
        print(f"\n[i] Recorrido elegido a mano: {self.recorrido}. Se usan sus reglas hasta terminar el trabajo.")

    def _aplicar_elegida(self):
        if self.ruta_elegida is None or self.rutas_mod is None or self.ruta_elegida == "__nueva__":
            return
        r = next((x for x in self.rutas.get("rutas", []) if x.get("_archivo") == self.ruta_elegida), None)
        if r is None:
            return
        self.ruta_act = r
        self._rec = None
        self._rec_desconocido = False
        self.ruta_buscar_desde = None
        self.recorrido = self.rutas_mod.nombre_recorrido(r, getattr(self, "cargamento", None))
        self.regla = None

    def _revisar_elegida(self, d):
        """Aviso (una vez) si la distancia no puede ser de ese recorrido: más que su distancia inicial."""
        r = self.ruta_act
        if r is None or d is None or self.tramo != 1 or getattr(self, "_aviso_elegida", False):
            return
        d0 = r.get("distancia_inicial")
        if d0 is not None and d > d0 + 300:
            self._aviso_elegida = True
            print(f"\n[!] Elegiste {r.get('nombre')}, pero faltan {_km(d)} (ese recorrido empieza en {_km(d0)}). "
                  f"Revisa la elección.")
            self.avisar("aviso", "¿Recorrido equivocado?", f"Elegiste {r.get('nombre')} y la distancia no cuadra.")

    def _fijar_recorrido(self, r, carg, est, como):
        self.ruta_act = r
        self._rec_desconocido = False
        self.recorrido = self.rutas_mod.nombre_recorrido(r, carg, est)
        print(f"\n[i] Recorrido {como}: {self.recorrido} ({_km(est)}).")
        self.incidente(f"recorrido {como}: {self.recorrido}")

    def revisar_ruta_y_reglas(self, ahora):
        if self.rutas_mod is None:
            return
        # distancia filtrada: una lectura suelta que salta más de 150 m (mala lectura, o el GPS
        # recalculando un instante) no cambia de regla; si se repite, sí
        d_raw = self._corregir_distancia(self._hud_metros())
        d_f = getattr(self, "dist_filtrada", None)
        if d_raw is None:
            d = d_f
        elif d_f is None or abs(d_raw - d_f) <= 150:
            d = self.dist_filtrada = d_raw
            self._salto = None
            self._salto_n = 0
        elif getattr(self, "_salto", None) is not None and abs(d_raw - self._salto) <= 60 and \
                (d_raw > d_f or getattr(self, "_salto_n", 0) >= 1):
            # 2.3.4: una BAJADA brusca necesita 3 lecturas seguidas (el HUD leyó "8 m" dos veces en vez de 867)
            # v39: en la ida, la distancia salta de "casi llegado" a varios km: ya descargó aunque no se
            # haya visto la notificación -> pasar a la vuelta
            if self.tramo == 1 and self._tramo_visto == 1 and d_f < 200 and d_raw > 1000 and \
                    ahora - getattr(self, "_t_tramo", ahora) > 60 and \
                    time.time() - getattr(self, "t_cargado", -999.0) > 90:   # 2.3.0: no justo después de cargar
                print("\n[i] Descargado no detectado: la distancia saltó a la vuelta. Paso al tramo 2.")
                self.incidente("descargado no detectado: paso a la vuelta")
                self.tramo = 2
                self.tramo_notif = 2 if self.estado in ("INACTIVO", "TERMINADO", "GRABANDO") else None
            d = self.dist_filtrada = d_raw
            self._salto = None
            self._salto_n = 0
        else:
            if getattr(self, "_salto", None) is not None and abs(d_raw - self._salto) <= 60:
                self._salto_n = getattr(self, "_salto_n", 0) + 1
            else:
                self._salto_n = 0
            self._salto = d_raw
            d = d_f
        if self.tramo != self._tramo_visto:
            if self.tramo == 1:
                self.ruta_buscar_desde = ahora        # justo después de cargar: reconocer la ruta
                self.ruta_act = None
                self._rec = None
                self._rec_desconocido = False
                self._aplicar_elegida()
            elif self.tramo == 0:
                self.ruta_act = None
                self.ruta_buscar_desde = None
                self.recorrido = None
                self.cargamento = None
                self.grab_pendiente = None
                if self.ruta_elegida is not None and self._tramo_visto in (1, 2):
                    print("[i] Trabajo terminado: el recorrido vuelve a «Automático».")
                    self.ruta_elegida = None
            self.control_entregado = None       # v37: en el próximo trabajo vuelve a entregar el control
            self.grab_hecha = set()             # 2.1.0: grabaciones por distancia, una vez por tramo
            self.vuelta_lejos = False
            self._d_inicio_tramo = d_raw
            self._t_tramo = ahora
            self.dist_filtrada = d_raw          # nueva etapa: la distancia salta a un punto nuevo
            d = d_raw
            self._tramo_visto = self.tramo
        self._reconocer_recorrido(ahora, d_raw if d_raw is not None else d)
        if getattr(self, "_dref_semilla", None) is not None:        # 3.2.3: recorrido reconocido con un dígito mal leído
            d = self.dist_filtrada = self._dref_semilla
            self._dref_semilla = None
        if d is not None:
            ref = getattr(self, "_dref", None)
            # 3.2.7: la referencia se renueva solo cuando la lectura CAMBIA: si el HUD se queda pegado en un
            # valor (3,66 km durante 5 s a 90 km/h), lo recorrido se cuenta desde la primera vez que lo mostró
            if ref is None or ref["tramo"] != self.tramo or abs(float(d) - ref["d_leida"]) >= 1:
                self._dref = {"d": float(d), "d_leida": float(d), "odo": self.odo, "tramo": self.tramo}
        if self.tramo == 2 and not getattr(self, "vuelta_lejos", False) and d is not None:
            # recién descargado la distancia vieja (p. ej. 17 m) no es del punto final: esperar a la nueva
            d0 = getattr(self, "_d_inicio_tramo", None)
            if d > 1000 or (d0 is not None and abs(d - d0) > 50):
                self.vuelta_lejos = True
        if self.tramo == 2 and not getattr(self, "vuelta_lejos", False):
            d = None
        rapido = bool(getattr(self, "modo_rapido", False))
        lento = bool(getattr(self, "modo_lento", False))
        nueva = self.rutas_mod.regla_activa(self.rutas, self.ruta_act, self.tramo, d, rapido=rapido, lento=lento)
        if self.tramo in (0, 1, 2) and hasattr(self.rutas_mod, "reglas_generales"):     # 3.5.0
            gen = self.rutas_mod.reglas_generales(self.rutas, self.ruta_act, self.tramo, rapido=rapido, lento=lento)
            nueva = self.rutas_mod.combinar(gen, nueva)
        self.regla_prox = self.rutas_mod.regla_proxima(self.rutas, self.ruta_act, self.tramo, d,
                                                       self.cfg["velocidad"].get("regla_antes_m", 80), rapido=rapido,
                                                       lento=lento)
        if (nueva or {}).get("nota") != (self.regla or {}).get("nota"):
            if nueva is not None:
                extra = f"máx {nueva['max_kmh']} km/h" if "max_kmh" in nueva else ""
                print(f"\n[i] Regla: {nueva.get('nota', '')} ({extra}).  {self.lugar()}")
            elif self.regla is not None:
                print(f"[i] Fin de la regla: {self.regla.get('nota', '')}.")
        self.regla = nueva

    def leer_cargamento(self, img):
        """Lee "Cargando drogas..." del título de la barra de progreso (OCR)."""
        if self.hud is None or self.hud.ocr is None or not self.hud.ocr.disponible() or self.rutas_mod is None:
            return
        h, w = img.shape[:2]
        tit = img[int(h * 0.30):int(h * 0.375), int(w * 0.34):int(w * 0.66)]
        try:
            texto = self.hud.ocr.leer(tit)
        except Exception:
            texto = None
        c = self.rutas_mod.cargamento_de_texto(texto)
        if c is None:
            return
        self.cargamento = c
        print(f"\n[i] Cargamento: {c}  (barra: \"{texto}\")")
        self.incidente(f"cargamento: {c}")

    # ------------------------------------------------------------ condición y notificaciones
    def revisar_condicion(self, img, mon):
        """Condición del camión (% con el ícono del motor). Si baja, se anota como incidente."""
        try:
            import condicion
            x0, y0, x1, y1 = condicion.region(self.cfg, mon.get("left", 0), mon.get("top", 0))
            v = condicion.leer(img[max(0, y0):y1, max(0, x0):x1])
        except Exception:
            v = None
        if v is None:
            return
        previo = getattr(self, "cond_lectura", None)
        self.cond_lectura = v
        if previo != v:
            return                                  # esperar dos lecturas iguales seguidas
        estable = getattr(self, "condicion", None)
        if estable is not None and v <= estable - self.cfg.get("hud_texto", {}).get("condicion_aviso", 2):
            print(f"\n[!] Condición del camión: {estable}% -> {v}%  {self.lugar()}")
            self.incidente(f"condición {estable}->{v}%")
        self.condicion = v

    def revisar_notificacion(self, img, mon, ahora):
        """Notificaciones del trabajo: fijan la etapa aunque lleves tú el camión."""
        if not self.cfg.get("hud_texto", {}).get("notificaciones", True):
            return
        try:
            import notificaciones
            x0, y0, x1, y1 = notificaciones.region(self.cfg, mon.get("left", 0), mon.get("top", 0))
            import geometria
            d = notificaciones.detectar(img[max(0, y0):y1, max(0, x0):x1], 1.0 / geometria.escala_hud(self.cfg))
        except Exception:
            d = None
        if d is None:
            return
        tipo = d["tipo"]
        ult = getattr(self, "notif_ult", (None, -99.0))
        if ult[0] == tipo and ahora - ult[1] < 20:
            self.notif_ult = (tipo, ahora)                   # la misma notificación sigue en pantalla
            return
        if self.hud is not None and self.hud.ocr is not None and self.hud.ocr.disponible():
            try:
                tipo = notificaciones.confirmar_con_texto(tipo, self.hud.ocr.leer(d["img"]))
            except Exception:
                pass
        self.notif_ult = (tipo, ahora)
        textos = {"accion": "trabajo iniciado (acción necesaria)", "cargado": "camión CARGADO",
                  "descargado": "camión DESCARGADO", "completado": "TRABAJO COMPLETADO"}
        print(f"\n[i] Notificación: {textos.get(tipo, tipo)}.")
        self.incidente(f"notificación: {textos.get(tipo, tipo)}")
        if tipo == "completado":
            self.tramo_notif = None
            self.trabajo_completado = True
            if self.estado != "TERMINADO":
                self.cambiar("TERMINADO")
                print("[OK] Trabajo completado.")
            return
        if tipo == "accion" and self.tramo >= 1 and self.estado != "TERMINADO" \
                and not getattr(self, "trabajo_completado", False):
            # v39: el juego repite "acción necesaria" cada pocos segundos durante todo el trabajo.
            # Solo cuenta como trabajo nuevo después de "Trabajo completado".
            if time.time() - getattr(self, "t_aviso_accion", -99.0) > 30:
                print(f"[i] Aviso repetido del juego a mitad del trabajo: sigo en el tramo {self.tramo}.")
                self.t_aviso_accion = time.time()
            return
        objetivo = {"accion": 0, "cargado": 1, "descargado": 2}[tipo]
        self.conf["juego_visto"] = True
        if tipo == "accion":
            self.trabajo_completado = False
        if tipo in ("cargado", "descargado"):
            g = self.grab_mod.buscar(self._grabs_ahora(), tipo, getattr(self, "recorrido", None), objetivo)
            self.grab_pendiente = g            # se reproduce cuando el juego suelte el camión
        if tipo == "cargado":                  # 2.3.0: reconocer el recorrido con la distancia nueva
            self.t_cargado = time.time()
            self.ruta_act = None
            self.recorrido = None
            self.ruta_buscar_desde = time.time()
            self._rec = None
            self._rec_desconocido = False
            self._aplicar_elegida()
        if self.estado == "ESPERANDO_RUTA":
            self.tramo_notif = objetivo          # se aplica cuando aparezca la ruta nueva
        else:
            if self.tramo != objetivo:
                print(f"[i] Etapa corregida por la notificación: tramo {self.tramo} -> {objetivo}.")
            self.tramo = objetivo
            self.tramo_notif = objetivo if self.estado in ("INACTIVO", "TERMINADO") else None
            if self.estado == "TERMINADO":
                self.cambiar("INACTIVO")

    # ------------------------------------------------------------ bucle
    def _ventana_cambio(self, rect, cap_norte):
        """3.0.0: la ventana del juego se movió o cambió de tamaño: recalcular las zonas y las capturas."""
        import geometria
        geometria.preparar(self.cfg, rect=rect, persistir=False)
        print(f"\n[i] La ventana del juego cambió ({rect[2]}x{rect[3]} en {rect[0]},{rect[1]}): ajusto las zonas.")
        cap = vision.Captura(self.cfg["minimapa"])
        if self.vel is not None:
            self.vel.captura = None                    # vuelve a leer la región nueva
        if self.carril is not None and self.cfg.get("carril", {}).get("trapecio"):
            try:
                import carril
                self.carril = carril.DetectorCarrilIPM(self.cfg["carril"])
            except Exception as e:  # noqa
                print(f"[!] Carril: {e}")
        if self.yolo is not None:                      # 3.6.0
            self.yolo.reconfigurar(self.cfg)
        if cap_norte is not None and self.rumbo is not None:
            cap_norte = vision.Captura(geometria.region_ampliada_real(self.cfg, self.rumbo.margen))
        return cap, cap_norte

    def ejecutar(self):
        cap = vision.Captura(self.cfg["minimapa"])
        self.rumbo, cap_norte = None, None
        if self.experimental("rumbo_norte"):             # 2.4.0: rumbo exacto (N del minimapa + giro del mapa)
            try:
                import rumbo as rumbo_mod
                self.rumbo = rumbo_mod.Rumbo(self.cfg)
                import geometria
                cap_norte = vision.Captura(geometria.region_ampliada_real(self.cfg, self.rumbo.margen))
                print("[i] Rumbo exacto (experimental): buscando la N del minimapa.")
            except Exception as e:  # noqa
                self.rumbo = None
                print(f"[!] Rumbo exacto no disponible: {e}")
        periodo = 1.0 / self.cfg["fps"]
        t_prev = time.time()
        t_print = 0
        t = self.cfg["teclas"]
        print(f"Listo. Entra al camión en PRIMERA PERSONA y pulsa {t['activar']}.\n"
              f"  {t['modo_lento']} = modo lento   {t['saltar_etapa']} = saltar etapa   "
              f"{t['salir']} = salir   {'/'.join(t['tomar_control'])} = tomar el control")
        print(f"Control: {self.ctrl.nombre}.  Velocímetro: {'SI' if self.vel else 'NO'}.  "
              f"{self.texto_etapa()}")
        if self.hud is not None:
            try:
                self.hud.iniciar_ocr()
            except Exception as e:  # noqa
                print(f"[!] OCR no disponible: {e}")
        n_frame = 0
        try:
            while not self.parar.is_set():
                t_ini = time.time()
                n_frame += 1
                if not self.procesar_teclas():
                    break
                nuevo_rect = self.vigia.revisar()            # 3.0.0: ¿se movió la ventana del juego?
                if nuevo_rect is not None:
                    cap, cap_norte = self._ventana_cambio(nuevo_rect, cap_norte)
                img = cap.leer()
                if self.rumbo is not None:
                    try:
                        self.rumbo.actualizar(cap_norte.leer(), img)
                    except Exception as e:  # noqa
                        print(f"[!] Rumbo exacto desactivado por un error: {e}")
                        self.rumbo = None
                kmh = self.vel.leer() if self.vel else None
                self.revisar_pantalla(t_ini)
                if self.carril is not None:
                    self.res_carril = self.carril.detectar(self.carril.capturar())
                dt = t_ini - t_prev
                t_prev = t_ini
                res, (d, a, f) = self.paso(img, dt, kmh)
                if self.yolo is not None:                  # 3.6.0: modo sombra
                    self._yolo_paso(res)
                self._volcar_observaciones()

                if self.log:
                    self.log.write(f"{t_ini - self.t0:.2f},{self.estado},{self.tramo},{self.kmh},"
                                   f"{self.kmh_obj:.0f},{res['rumbo']},{res['desvio']},"
                                   f"{res['giro_adelante']},{d:.3f},{a:.3f},{f:.3f},"
                                   f"{res.get('en_calle', 1.0):.2f},{res.get('calle_corr', 0.0):.1f},{int(res.get('gps_fuera', False))},"
                                   f"{getattr(self, 'motivo', '-')},{ {'rapido': 2, 'lento': 1}.get(self.modo_vel(), 0)},"
                                   f"{(self.res_carril or {}).get('desvio', 0):.3f},{(self.res_carril or {}).get('confianza', 0):.2f},"
                                   f"{int(getattr(self, 'carril_usado', False))},"
                                   f"{_f(res.get('marcador_dist'))},{_f(res.get('marcador_ang'))},"
                                   f"{_f(res.get('fin_ruta_dist'))},{_f(res['puntos'][-1][2] if res.get('puntos') else None)},"
                                   f"{self._csv_lugar()},{_txt(self.evento)},"
                                   f"{_f(res.get('bifurcacion_dist'))},{_f(res.get('desvio_cerca'))},{self.desp_f:.2f},"
                                   f"{'' if getattr(self, 'condicion', None) is None else self.condicion},"
                                   f"{_txt(getattr(self, 'recorrido', None) or '')},{_txt((self.regla or {}).get('nota'))},"
                                   f"{self._csv_rumbo()},{self._csv_yolo()}\n")
                    self.evento = ""
                if t_ini - getattr(self, "_t_salud", 0.0) > 0.25:
                    self._t_salud = t_ini
                    self._revisar_salud(t_ini)
                if self.ui is not None and t_ini - t_print > 0.1:
                    t_print = t_ini
                    self.ui.estado({
                        "estado": self.estado, "etapa": self.texto_etapa(), "tramo": self.tramo,
                        "kmh": self.kmh, "kmh_obj": self.kmh_obj, "motivo": getattr(self, "motivo", "-"),
                        "direccion": d, "acelerador": a, "freno": f,
                        "lento": self.modo_vel() == "lento", "rapido": self.modo_vel() == "rapido",
                        "carril_activo": self.usar_carril,
                        "carril_usado": getattr(self, "carril_usado", False),
                        "carril_conf": (self.res_carril or {}).get("confianza"),
                        "fuera_calle": self.fuera_de_calle, "ruta": res["encontrada"],
                        "rumbo": res.get("rumbo"), "desvio": res.get("desvio"),
                        "curva": res.get("giro_adelante"), "control": self.ctrl.nombre,
                        "velocimetro": self.vel is not None, "debug": self.debug,
                        "lugar": self.lugar(),
                        "recorrido": getattr(self, "recorrido", None),
                        "recorrido_elegido": self.ruta_elegida,
                        "recorrido_archivo": (self.ruta_act or {}).get("_archivo"),
                        "zona": (self.hud.estado.get("zona") if self.hud else None),
                        "calle": (self.hud.estado.get("calle") if self.hud else None),
                        "metros": (self.hud.estado.get("metros") if self.hud else None),
                        "condicion": getattr(self, "condicion", None),
                        "regla": (self.regla or {}).get("nota"),
                        "rumbo_abs": None if self.rumbo is None else self.rumbo.valor,
                        "yolo": None if self.yolo is None else (self.yolo_est.get("accion") or "nada"),
                        "usuario": self.usuario, "problemas": self.problemas,
                        "pantalla": ("Menú de carga" if self.pantalla.get("menu") else
                                     (f"Barra de progreso {100 * (self.pantalla.get('progreso') or 0):.0f}%"
                                      if self.pantalla.get("barra") else ""))})
                elif self.ui is None and t_ini - t_print > 0.25:
                    t_print = t_ini
                    if res["encontrada"]:
                        ang = f"rumbo {res['rumbo']:+5.1f}° desvío {res['desvio']:+5.1f}px curva {res['giro_adelante']:+4.0f}°"
                    else:
                        ang = "sin ruta" + " " * 34
                    sys.stdout.write(f"\r{self.estado:<14} {self.kmh:3d}/{self.kmh_obj:3.0f} km/h "
                                     f"({getattr(self, 'motivo', '-'):<14}) "
                                     f"{ang}  dir {d:+.2f}  acel {a:.2f}  freno {f:.2f}  "
                                     f"{'LENTO' if self.modo_lento else '     '} "
                                     f"{'FUERA DE CALLE' if self.fuera_de_calle else '              '} "
                                     f"{'CARRIL' if getattr(self, 'carril_usado', False) else '      '}  ")
                    sys.stdout.flush()
                if self.debug and (self.ui is None or n_frame % 3 == 0):
                    txt = (f"{self.estado} T{self.tramo}  {self.kmh}/{self.kmh_obj:.0f} km/h ({getattr(self, 'motivo', '-')})"
                           f"{'  LENTO' if self.modo_lento else ''}\ndir {d:+.2f} acel {a:.2f} freno {f:.2f}")
                    if res["encontrada"]:
                        txt += f"\nrumbo {res['rumbo']:+.0f} desvio {res['desvio']:+.1f}px curva {res['giro_adelante']:+.0f}"
                    vis = vision.dibujar_debug(img, res, self.cfg, texto=txt)
                    vis_c = None
                    if self.res_carril is not None:
                        import carril
                        vis_c = carril.dibujar_ipm(self.res_carril, self.carril)
                    vis_y = None
                    if self.yolo is not None and self.ui is not None:
                        try:
                            vis_y = self.yolo.dibujar()
                        except Exception:  # noqa
                            vis_y = None
                    if self.ui is not None:
                        self.ui.imagenes({"minimapa": vis, "carril": vis_c, "yolo": vis_y})
                    else:
                        cv2.imshow("autopiloto (debug)", vis)
                        if vis_c is not None:
                            cv2.imshow("carril (debug)", vis_c)
                        cv2.waitKey(1)
                restante = periodo - (time.time() - t_ini)
                if restante > 0:
                    time.sleep(restante)
        except KeyboardInterrupt:
            pass
        finally:
            if getattr(self, "yolo", None) is not None:
                self.yolo.parar()
            self.ctrl.soltar_todo()
            self.ctrl.cerrar()
            if self.log:
                self._volcar_observaciones()
                try:
                    self.log.write(f"# usuario: {self.usuario or '(sin nombre)'}\n"
                                   f"# recorrido: {getattr(self, 'recorrido', None) or '-'}\n"
                                   f"# fin: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                except Exception:
                    pass
                self.log.close()
                if getattr(self, "rumbo", None) is not None:   # 3.4.0: el mapa ya no es experimental
                    try:                                   # 2.4.0: mapa de la ruta, si aún no existe
                        import mapa
                        for rec, tramos, _a in mapa.desde_viaje(self.log.name, solo_si_falta=True):
                            print(f"[OK] Mapa de la ruta: {rec} (tramos {', '.join(tramos)}) guardado en datos/mapas/.")
                    except Exception as e:  # noqa
                        print(f"[i] No se armó el mapa de la ruta: {e}")
                    try:                                   # 2.5.0: perfil de rumbo y tramos compartidos
                        import compartidos
                        compartidos.desde_viaje(self.log.name)
                        nuevos = compartidos.detectar()
                        if nuevos:
                            print(f"[i] Encontré {len(nuevos)} tramo(s) compartido(s) entre recorridos. Revísalos y "
                                  "confírmalos en la pestaña Experimental (no se usan hasta que los confirmes):")
                            for g in nuevos:
                                print(f"    • {compartidos.describir(g)}")
                    except Exception as e:  # noqa
                        print(f"[i] No se revisaron los tramos compartidos: {e}")
            self.terminado = True
            try:                                     # 2.7.2: guardar los números del HUD aprendidos
                import hud_texto
                hud_texto.APRENDIDAS.guardar(forzar=True)
                if self.hud is not None and (getattr(self.hud, "descartadas", 0) or getattr(self.hud, "corregidas", 0)):
                    print(f"[i] Lecturas de distancia: {getattr(self.hud, 'corregidas', 0)} corregidas (dígito mal "
                          f"leído) y {getattr(self.hud, 'descartadas', 0)} descartadas por imposibles.")
            except Exception:  # noqa
                pass
            self.pedir_observaciones("programa detenido")
            if self.ui is None:
                cv2.destroyAllWindows()
            if self.muestras_sesgo > 300:
                try:
                    cfg_disco = configuracion.cargar(self.ruta_config, guardar_migracion=False)
                    cfg_disco.setdefault("carril", {})["sesgo"] = round(self.sesgo_carril, 3)
                    configuracion.guardar(cfg_disco, self.ruta_config)
                    print(f"[i] Centro del carril ajustado con el GPS: sesgo {self.sesgo_carril:+.3f} (guardado)")
                except Exception as e:  # noqa
                    print(f"[!] No se pudo guardar el sesgo del carril: {e}")
            self.resumen_incidentes()
            print("\nAutopiloto cerrado, teclas liberadas.")


# ---------------------------------------------------------------- simulación
def simular(cfg, ruta, mostrar=None, parar=None):
    """Prueba visión y velocímetro sobre capturas de pantalla completa o un video.
    mostrar(dict) / parar (Event): para usarlo desde la interfaz gráfica."""
    import geometria
    geometria.preparar(cfg, rect=None, persistir=False, avisar=False)   # capturas guardadas: posiciones absolutas

    def fuentes():
        if os.path.isdir(ruta):
            for n in sorted(os.listdir(ruta)):
                if n.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    yield n, cv2.imread(os.path.join(ruta, n))
        elif ruta.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            yield os.path.basename(ruta), cv2.imread(ruta)
        else:
            vid = cv2.VideoCapture(ruta)
            i = 0
            while True:
                ok, fr = vid.read()
                if not ok:
                    break
                i += 1
                yield f"frame {i}", fr

    vel = None
    if cfg["velocimetro"]["activo"]:
        import velocimetro
        vel = velocimetro.Velocimetro(cfg["velocimetro"])
    m, rv = cfg["minimapa"], cfg["velocimetro"]["region"]
    det_carril = None
    if cfg.get("carril", {}).get("activo") and cfg["carril"].get("trapecio"):
        import carril
        det_carril = carril.DetectorCarrilIPM(cfg["carril"])
    ang = 0.0
    n_sim = 0
    for nombre, img in fuentes():
        if img is None:
            continue
        kmh = "?"
        rcar = None
        if img.shape[1] > m["w"] * 2:   # pantalla completa
            if det_carril is not None:
                es_img = os.path.isdir(ruta) or ruta.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))
                for _ in range(6 if es_img else 1):       # imagen suelta: dejar que se asiente
                    rcar = det_carril.detectar(det_carril.capturar(img))
            if vel:
                kmh = vel.leer_imagen(img[rv["y"]:rv["y"] + rv["h"], rv["x"]:rv["x"] + rv["w"]])
            img = vision.recortar_minimapa(img, m)
        res = vision.analizar(img, cfg, ang)
        if res["encontrada"]:
            ang = res["ang_cerca"]
        r1 = lambda x: None if x is None else round(x, 1)
        txt = (f"ruta {'SI' if res['encontrada'] else 'NO'}  vel {kmh}\n"
               f"rumbo {r1(res['rumbo'])}  desvio {r1(res['desvio'])}px  curva {r1(res['giro_adelante'])}")
        if rcar is not None:
            txt += f"\ncarril {rcar['desvio']:+.2f} conf {rcar['confianza']:.2f}"
        n_sim += 1
        if mostrar is None or n_sim % 30 == 1:
            print(f"{nombre}: {txt.replace(chr(10), '  ')}")
        if parar is not None and parar.is_set():
            break
        if mostrar is not None:
            mostrar({"minimapa": vision.dibujar_debug(img, res, cfg, texto=txt),
                     "carril": carril.dibujar_ipm(rcar, det_carril) if rcar is not None else None})
            es_imagen = os.path.isdir(ruta) or ruta.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))
            time.sleep(1.5 if es_imagen else 1 / 30)
            continue
        if os.environ.get("SIN_VENTANA"):
            continue
        cv2.imshow("simulacion", vision.dibujar_debug(img, res, cfg, texto=txt))
        if rcar is not None:
            cv2.imshow("carril (simulacion)", carril.dibujar_ipm(rcar, det_carril))
        es_imagen = os.path.isdir(ruta) or ruta.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))
        if cv2.waitKey(0 if es_imagen else 30) == 27:
            break
    cv2.destroyAllWindows()


def main():
    import carpetas
    carpetas.preparar()
    ap = argparse.ArgumentParser(description="Autopiloto de camión (minimapa)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--tramo", type=int, default=0, help="0=ir a cargar, 1=ir a A, 2=volver a B")
    ap.add_argument("--log", help="guardar CSV con datos de conducción")
    ap.add_argument("--simular", help="imagen, video o carpeta para probar sin el juego")
    args = ap.parse_args()

    cfg = configuracion.cargar(args.config)
    if args.simular:
        simular(cfg, args.simular)
        return
    if not entrada.ES_WINDOWS:
        print("El modo en vivo solo funciona en Windows. Usa --simular para probar.")
        return
    Autopiloto(cfg, args.tramo, args.debug, args.log).ejecutar()


if __name__ == "__main__":
    main()

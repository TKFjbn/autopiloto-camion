"""
Detección de vehículos y personas delante del camión con YOLO (3.6.0, MODO SOMBRA).

En esta versión NO maneja: detecta, calcula a qué distancia está cada cosa y si viene hacia el camión, y dice qué
*habría hecho* (seguir, frenar, frenar a fondo, esperar). Eso se ve en la vista «YOLO» y queda en el CSV del viaje.

- Primera persona: se usa la misma calibración que la cámara de carril (el trapecio). Con él se saca:
    · el horizonte (donde se juntan los lados del carril),
    · la altura de la cámara (con el ancho de carril, ~3,6 m),
    · el centro y el ancho del carril a cada altura de la imagen.
  Distancia aproximada  Z = f·h / (y − y_horizonte)   (f sale del campo de visión; puede tener un error de escala)
  Lado                  X = ancho_carril · (x − centro(y)) / ancho(y)
  El tiempo hasta chocar (Z dividido por cuánto se acerca) NO depende de ese error de escala: con él se decide.
- Máscara de cabina: rectángulos (en fracciones de la ventana del juego) que se tapan antes de detectar
  (tablero, parantes, espejos). Se dibujan en Calibración → «Máscara de cabina (YOLO)».
- Corre en un hilo aparte, unas `hz` veces por segundo, con la tarjeta de video si hay (CUDA) o el procesador.
- No lee la memoria del juego ni toca su carpeta: solo mira la pantalla, como el resto del programa.

Necesita (opcional): pip install ultralytics  (y PyTorch; para usar la tarjeta, PyTorch con CUDA).
Si no está, el resto del programa funciona igual.
"""
import math
import threading
import time

import numpy as np

try:
    import cv2
except Exception:  # noqa
    cv2 = None

# clases COCO que interesan -> nombre corto
CLASES = {0: "persona", 1: "bicicleta", 2: "auto", 3: "moto", 5: "bus", 7: "camión"}
PERSONAS = {"persona", "bicicleta"}


def grupo(clase):
    """3.6.3: para seguir un objeto entre cuadros, todo lo que no es persona es «vehículo» (el modelo a veces
    llama camión a un auto de GTA y al cuadro siguiente auto)."""
    return "persona" if clase == "persona" else "vehiculo"

DEFECTO = {
    "activo": True,
    "modelo": "yolo11n.pt",          # se descarga solo la primera vez (~6 MB)
    "hz": 10,                        # detecciones por segundo (más = más uso de la tarjeta)
    "confianza": 0.35,
    "confianza_noche": 0.5,          # de noche (imagen oscura) pide más
    "tamano": 640,
    "dispositivo": "auto",           # "auto", "cuda", "cpu"
    "ancho_carril_m": 3.6,           # para sacar la altura de la cámara con el trapecio
    "fov_horizontal_grados": 60,     # campo de visión horizontal en primera persona (escala de la distancia)
    "ancho_camion_m": 3.07,          # Pounder
    "margen_lado_m": 0.6,            # el pasillo de peligro: ancho del camión + esto a cada lado
    "pasillo_seg": 4.0,              # largo del pasillo: lo que recorre en estos segundos (mínimo 25 m)
    "persistencia": 3,               # cuadros seguidos que tiene que verse algo antes de contar
    "ttc_seguir": 4.0,               # tiempo hasta chocar (s): menos de esto = seguirlo / bajar
    "ttc_frenar": 2.0,
    "ttc_fondo": 1.0,
    "factor_personas": 2.0,          # con personas, todo el doble de prudente
    "distancia_min_seg": 1.0,        # ir a menos de esto (en segundos de camino) de algo = frenar
    "esperar_m": 12.0,
    "esperar_max_s": 10.0,           # 3.7.0: si lo mismo sigue delante tanto rato (un NPC quieto), sigue igual               # parado con algo a menos de esto delante = esperar
    "decidir_max_m": 40.0,           # frenar firme / a fondo solo por cosas a menos de esto (la distancia
                                     # lejana es menos precisa: la cámara se mueve al frenar o en baches)
    "mascara": [],                   # [[x0, y0, x1, y1], ...] en fracciones de la ventana del juego
}

ACCIONES = ("nada", "seguir", "frenar", "frenar a fondo", "esperar")


def ruta_modelo(nombre):
    """El modelo vive en mi_equipo/yolo/ (las actualizaciones del programa no lo borran). Un nombre suelto
    (yolo11n.pt) se descarga ahí la primera vez."""
    import os
    if os.path.dirname(nombre):
        return nombre
    try:
        import carpetas
        carpeta = os.path.join(carpetas.EQUIPO, "yolo")
    except Exception:  # noqa
        carpeta = "yolo"
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, nombre)


def cargar_modelo(nombre):
    from ultralytics import YOLO                       # noqa (opcional)
    return YOLO(ruta_modelo(nombre))


def configurar(cfg):
    y = dict(DEFECTO)
    y.update(cfg.get("yolo") or {})
    return y


# ---------------------------------------------------------------- geometría de la cámara (primera persona)
def _interseccion(p1, p2, p3, p4):
    """Intersección de la recta p1-p2 con la p3-p4 (None si son paralelas)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / d, (a * (y3 - y4) - (y1 - y2) * b) / d)


class Geometria:
    """Con el trapecio del carril (cerca-izq, lejos-izq, lejos-der, cerca-der, en pantalla): distancia y lado de
    un punto del suelo. Las coordenadas son de pantalla (las mismas del trapecio)."""

    def __init__(self, trapecio, ancho_juego_px, ancho_carril_m=3.6, fov_grados=60.0):
        (cix, ciy), (lix, liy), (ldx, ldy), (cdx, cdy) = [tuple(map(float, p)) for p in trapecio]
        self.izq = ((cix, ciy), (lix, liy))
        self.der = ((cdx, cdy), (ldx, ldy))
        fuga = _interseccion((cix, ciy), (lix, liy), (cdx, cdy), (ldx, ldy))
        if fuga is None or fuga[1] >= min(ciy, cdy):
            raise ValueError("el trapecio del carril no tiene horizonte (calibra el carril de nuevo)")
        self.fx, self.yh = fuga
        self.y_cerca = (ciy + cdy) / 2
        self.W = float(ancho_carril_m)
        w_cerca = self.ancho_en(self.y_cerca)
        self.h = self.W * (self.y_cerca - self.yh) / max(1.0, w_cerca)          # altura de la cámara (m)
        self.f = (ancho_juego_px / 2) / math.tan(math.radians(fov_grados) / 2)  # focal en px

    def _x_en(self, recta, y):
        (x1, y1), (x2, y2) = recta
        if abs(y2 - y1) < 1e-9:
            return x1
        return x1 + (x2 - x1) * (y - y1) / (y2 - y1)

    def ancho_en(self, y):
        return self._x_en(self.der, y) - self._x_en(self.izq, y)

    def centro_en(self, y):
        return (self._x_en(self.der, y) + self._x_en(self.izq, y)) / 2

    def distancia(self, y):
        """Metros adelante (aprox.) de un punto del suelo en la fila y de la pantalla; None sobre el horizonte."""
        if y <= self.yh + 1:
            return None
        return self.f * self.h / (y - self.yh)

    def lado(self, x, y):
        """Metros al lado del centro del carril (+ = derecha) de un punto del suelo."""
        w = self.ancho_en(y)
        if w <= 1:
            return None
        return self.W * (x - self.centro_en(y)) / w

    def a_pantalla(self, z, x_m):
        """Al revés: punto del suelo (z adelante, x_m al lado) -> pantalla."""
        y = self.yh + self.f * self.h / max(0.5, z)
        return self.centro_en(y) + x_m * self.ancho_en(y) / self.W, y

    def zona(self, rect=None):
        """Recuadro de pantalla a mirar: casi todo el parabrisas (3.6.2): bien arriba del horizonte (camiones y buses
        delante se ven enteros) hasta casi el tablero (autos pegados al capó), unas 3 pistas a cada lado.
        Lo que tapa la máscara de cabina no se mira. Recortado a la ventana del juego si se conoce."""
        w = self.ancho_en(self.y_cerca)
        cx = self.centro_en(self.y_cerca)
        alto = self.y_cerca - self.yh
        x0, x1 = cx - 3.2 * w, cx + 3.2 * w
        y0, y1 = self.yh - 1.3 * alto, self.y_cerca + 0.45 * alto
        if rect:
            rx, ry, rw, rh = rect
            x0, y0 = max(x0, rx), max(y0, ry)
            x1, y1 = min(x1, rx + rw), min(y1, ry + rh)
        return int(x0), int(y0), int(max(32, x1 - x0)), int(max(32, y1 - y0))


# ---------------------------------------------------------------- seguimiento de objetos entre cuadros
def _iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


class Rastreador:
    """3.6.3: sigue por grupo (vehículo / persona), suaviza distancia y lado con la mediana de los últimos
    cuadros, y solo da tiempo hasta chocar si el acercamiento es claramente mayor que el temblor de la caja."""
    SUAVE = 5                          # cuadros para la mediana
    PERDIDO_S = 0.6                    # un objeto que no se ve por menos de esto sigue siendo el mismo

    def __init__(self, ventana_s=1.0):
        self.pistas = {}
        self.sig = 1
        self.ventana_s = ventana_s

    def actualizar(self, dets, t, kmh=None):
        """dets: [{clase, conf, caja (x0,y0,x1,y1) en pantalla, z, x}] -> la misma lista con id, vistos, ttc,
        z y x suavizados, la clase más repetida y si estaba en el pasillo (en_pasillo_ant)."""
        usadas = set()
        for d in sorted(dets, key=lambda d: -d["conf"]):
            mejor, mi = None, 0.25
            for pid, p in self.pistas.items():
                if pid in usadas or p["grupo"] != grupo(d["clase"]):
                    continue
                v = _iou(p["caja"], d["caja"])
                if v > mi:
                    mejor, mi = pid, v
            if mejor is None:
                mejor = self.sig
                self.sig += 1
                self.pistas[mejor] = {"grupo": grupo(d["clase"]), "hist": [], "vistos": 0, "clases": {},
                                      "zs": [], "xs": [], "en_pasillo": False}
            p = self.pistas[mejor]
            usadas.add(mejor)
            p["caja"], p["t"] = d["caja"], t
            p["vistos"] += 1
            p["clases"][d["clase"]] = p["clases"].get(d["clase"], 0) + 1
            if d.get("z") is not None:
                p["zs"] = (p["zs"] + [d["z"]])[-self.SUAVE:]
                p["xs"] = (p["xs"] + [d["x"]])[-self.SUAVE:]
                d["z"] = float(np.median(p["zs"]))
                d["x"] = float(np.median(p["xs"]))
                p["hist"].append((t, d["z"]))
            p["hist"] = [h for h in p["hist"] if t - h[0] <= self.ventana_s]
            d["clase"] = max(p["clases"], key=p["clases"].get)
            d["id"], d["vistos"], d["en_pasillo_ant"] = mejor, p["vistos"], p["en_pasillo"]
            d["ttc"], d["acerca_ms"] = self._ttc(p["hist"], kmh)
        for pid in [k for k, p in self.pistas.items() if t - p["t"] > self.PERDIDO_S]:
            del self.pistas[pid]
        return dets

    def marcar_pasillo(self, dets):
        for d in dets:
            if d.get("id") in self.pistas:
                self.pistas[d["id"]]["en_pasillo"] = bool(d.get("en_pasillo"))

    @staticmethod
    def _ttc(hist, kmh=None):
        """Tiempo hasta chocar con una recta ajustada a la distancia (suavizada) del último segundo.
        Solo si se acerca claramente: más de 0,8 m/s y más de 2,5 veces el error de la recta. Con el camión
        parado y la distancia casi igual, nunca. Devuelve (ttc s o None, m/s que se acerca)."""
        if len(hist) < 4 or hist[-1][0] - hist[0][0] < 0.35:
            return None, 0.0
        t = np.array([h[0] for h in hist]) - hist[-1][0]
        z = np.array([h[1] for h in hist])
        pend, base = (float(v) for v in np.polyfit(t, z, 1))
        resto = z - (pend * t + base)
        sxx = float(((t - t.mean()) ** 2).sum())
        se = float(np.sqrt((resto ** 2).sum() / max(1, len(t) - 2) / max(1e-6, sxx)))
        acerca = -pend
        if kmh is not None and kmh < 3 and acerca < 1.5:
            return None, 0.0
        if acerca < max(0.8, 2.5 * se):
            return None, max(0.0, acerca)
        return float(z[-1] / acerca), acerca


# ---------------------------------------------------------------- qué habría hecho
def desplazamiento_pasillo(z, giro_grados):
    """Cuánto se corre el pasillo hacia el lado de la curva a z metros (la vista gira con el camión al doblar):
    se reparte el giro de la ruta (grados en los próximos ~40 m) como un arco."""
    g = math.radians(max(-90.0, min(90.0, giro_grados or 0.0)))
    return z * math.tan(g * min(1.0, z / 40.0) / 2)


def decidir(objetos, kmh, giro_grados, c):
    """Devuelve (acción, objeto que la causa o None, texto)."""
    v = max(0.0, (kmh or 0) / 3.6)
    largo = max(25.0, v * c["pasillo_seg"])
    medio = c["ancho_camion_m"] / 2 + c["margen_lado_m"]
    peor, accion, causa = 0, "nada", None
    for o in objetos:
        z, x = o.get("z"), o.get("x")
        o["en_pasillo"] = False
        if z is None or x is None or o.get("vistos", 0) < c["persistencia"]:
            continue
        tol = medio + (0.4 if o.get("en_pasillo_ant") else 0.0)       # 3.6.3: no parpadear en el borde
        if z > largo or abs(x - desplazamiento_pasillo(z, giro_grados)) > tol:
            continue
        o["en_pasillo"] = True
        f = c["factor_personas"] if o["clase"] in PERSONAS else 1.0
        ttc = o.get("ttc")
        a = "nada"
        if kmh is not None and kmh < 3 and z <= c["esperar_m"]:
            a = "esperar"
        elif ttc is not None and z <= c["decidir_max_m"] and ttc < c["ttc_fondo"] * f:
            a = "frenar a fondo"
        elif ttc is not None and z <= c["decidir_max_m"] and ttc < c["ttc_frenar"] * f:
            a = "frenar"
        elif v > 0 and z < v * c["distancia_min_seg"] * f:
            a = "frenar"                          # demasiado pegado (menos de ~1 s), venga o no hacia el camión
        elif ttc is not None and ttc < c["ttc_seguir"] * f:
            a = "seguir"
        n = {"nada": 0, "seguir": 1, "esperar": 2, "frenar": 3, "frenar a fondo": 4}[a]
        if n > peor:
            peor, accion, causa = n, a, o
    texto = "" if causa is None else (f"{causa['clase']} a {causa['z']:.0f} m"
                                      + (f", choca en {causa['ttc']:.1f} s" if causa.get("ttc") else ""))
    return accion, causa, texto


# ---------------------------------------------------------------- el vigía (hilo)
class VigiaYolo:
    def __init__(self, cfg):
        self.c = configurar(cfg)
        self.cfg = cfg
        self.geo = None
        self.error = None
        self.dispositivo = None
        self.modelo = None
        self.lock = threading.Lock()
        self.estado = {"accion": "nada", "texto": "", "objetos": [], "fps": 0.0, "t": 0.0}
        self.kmh, self.giro = 0, 0.0
        self.img_ultima = None
        self.zona_ultima = None
        self.rastreador = Rastreador()
        self._parar = threading.Event()
        self.hilo = None
        self.reconfigurar(cfg)

    def reconfigurar(self, cfg):
        """Con la ventana movida o el carril recalibrado."""
        self.cfg = cfg
        self.c = configurar(cfg)
        tr = (cfg.get("carril") or {}).get("trapecio")
        rect = cfg.get("_ventana")
        try:
            if not tr:
                raise ValueError("falta calibrar el carril (la distancia sale de esa calibración)")
            ancho = rect[2] if rect else 1920
            self.geo = Geometria(tr, ancho, self.c["ancho_carril_m"], self.c["fov_horizontal_grados"])
            self.error = None
        except Exception as e:  # noqa
            self.geo = None
            self.error = str(e)

    # -- modelo
    def _cargar_modelo(self):
        disp = self.c.get("dispositivo", "auto")
        if disp == "auto":
            try:
                import torch
                disp = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:  # noqa
                disp = "cpu"
        self.modelo = cargar_modelo(self.c["modelo"])
        self.dispositivo = disp
        print(f"[OK] YOLO listo ({self.c['modelo']}, {'tarjeta de video' if disp == 'cuda' else 'procesador'}). "
              "Modo sombra: no maneja, solo muestra y anota lo que habría hecho.")

    def iniciar(self):
        if self.hilo is not None:
            return
        self.hilo = threading.Thread(target=self._bucle, daemon=True, name="yolo")
        self.hilo.start()

    def parar(self):
        self._parar.set()

    def contexto(self, kmh, giro):
        self.kmh, self.giro = kmh, giro

    def ultima(self):
        with self.lock:
            return dict(self.estado)

    # -- detección
    def _tapar(self, img, x0, y0):
        rect = self.cfg.get("_ventana")
        if not rect or not self.c.get("mascara"):
            return img
        rx, ry, rw, rh = rect
        for fx0, fy0, fx1, fy1 in self.c["mascara"]:
            a = int(rx + fx0 * rw - x0), int(ry + fy0 * rh - y0)
            b = int(rx + fx1 * rw - x0), int(ry + fy1 * rh - y0)
            cv2.rectangle(img, a, b, (114, 114, 114), -1)
        return img

    def detectar(self, img, x0, y0, t=None):
        """img: recorte de pantalla que empieza en (x0, y0). Se usa también en las pruebas (con detecciones
        hechas a mano, ver procesar)."""
        oscura = float(img.mean()) < 55
        conf = self.c["confianza_noche"] if oscura else self.c["confianza"]
        r = self.modelo.predict(img, imgsz=self.c["tamano"], conf=conf, classes=list(CLASES), verbose=False,
                                device=self.dispositivo)[0]
        cajas = []
        for b, k, cf in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            cajas.append((CLASES.get(int(k), "?"), float(cf), (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0)))
        return self.procesar(cajas, t)

    def procesar(self, cajas, t=None):
        """cajas: [(clase, confianza, (x0, y0, x1, y1) en pantalla)] -> estado (y lo guarda)."""
        t = time.time() if t is None else t
        dets = []
        for clase, cf, caja in cajas:
            xb, yb = (caja[0] + caja[2]) / 2, caja[3]           # donde toca el suelo
            z = self.geo.distancia(yb) if self.geo else None
            x = self.geo.lado(xb, yb) if self.geo else None
            dets.append({"clase": clase, "conf": cf, "caja": caja, "z": z, "x": x})
        dets = self.rastreador.actualizar(dets, t, self.kmh)
        accion, causa, texto = decidir(dets, self.kmh, self.giro, self.c)
        self.rastreador.marcar_pasillo(dets)
        est = {"accion": accion, "texto": texto, "objetos": dets, "t": t,
               "causa": None if causa is None else {k: causa.get(k) for k in ("clase", "z", "x", "ttc", "id")}}
        with self.lock:
            fps = self.estado.get("fps", 0.0)
            est["fps"] = fps
            self.estado = est
        return est

    def _bucle(self):
        try:
            self._cargar_modelo()
        except Exception as e:  # noqa
            self.error = f"no se pudo cargar YOLO: {e}"
            print(f"[i] YOLO desactivado: {e}. Instala con «Instalar YOLO.bat» (opcional).")
            return
        import mss
        sct = mss.mss()
        periodo = 1.0 / max(1.0, float(self.c.get("hz", 10)))
        n, t_fps = 0, time.time()
        while not self._parar.is_set():
            t0 = time.time()
            if self.geo is None:
                time.sleep(0.5)
                continue
            try:
                x, y, w, h = self.geo.zona(self.cfg.get("_ventana"))
                img = cv2.cvtColor(np.asarray(sct.grab({"left": x, "top": y, "width": w, "height": h})),
                                   cv2.COLOR_BGRA2BGR)
                img = self._tapar(img, x, y)
                self.detectar(img, x, y, t0)
                self.img_ultima, self.zona_ultima = img, (x, y)
                n += 1
                if time.time() - t_fps >= 2.0:
                    with self.lock:
                        self.estado["fps"] = n / (time.time() - t_fps)
                    n, t_fps = 0, time.time()
            except Exception as e:  # noqa
                if self.error != str(e):
                    print(f"[!] YOLO: {e}")
                self.error = str(e)
                time.sleep(0.5)
            resto = periodo - (time.time() - t0)
            if resto > 0:
                time.sleep(resto)

    # -- vista
    def dibujar(self):
        """Imagen para la vista «YOLO»: recorte con las cajas, la distancia y el pasillo de peligro."""
        if self.img_ultima is None or self.zona_ultima is None:
            return None
        return dibujar(self.img_ultima, self.zona_ultima, self.ultima(), self.geo, self.giro, self.kmh, self.c)


COLORES = {"nada": (160, 160, 160), "seguir": (0, 200, 255), "esperar": (255, 200, 0), "frenar": (0, 140, 255),
           "frenar a fondo": (0, 0, 255)}


def dibujar(img, origen, est, geo, giro, kmh, c):
    v = img.copy()
    x0, y0 = origen
    if geo is not None:                                    # pasillo de peligro
        largo = max(25.0, max(0.0, (kmh or 0) / 3.6) * c["pasillo_seg"])
        medio = c["ancho_camion_m"] / 2 + c["margen_lado_m"]
        izq, der = [], []
        z = 3.0
        while z <= largo:
            s = desplazamiento_pasillo(z, giro)
            for lista, lado in ((izq, -medio), (der, medio)):
                px, py = geo.a_pantalla(z, s + lado)
                lista.append((int(px - x0), int(py - y0)))
            z += 2.0
        if len(izq) >= 2:
            poli = np.array(izq + der[::-1], np.int32)
            capa = v.copy()
            cv2.fillPoly(capa, [poli], (60, 60, 200) if est.get("accion") in ("frenar", "frenar a fondo")
                         else (80, 160, 80))
            v = cv2.addWeighted(capa, 0.22, v, 0.78, 0)
    for o in est.get("objetos", []):
        a, b = (int(o["caja"][0] - x0), int(o["caja"][1] - y0)), (int(o["caja"][2] - x0), int(o["caja"][3] - y0))
        col = (0, 140, 255) if o.get("en_pasillo") else (200, 200, 200)
        cv2.rectangle(v, a, b, col, 2)
        txt = o["clase"]
        if o.get("z") is not None:
            txt += f" {o['z']:.0f}m"
        if o.get("ttc") is not None:
            txt += f" {o['ttc']:.1f}s"
        cv2.putText(v, txt, (a[0], max(12, a[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    acc = est.get("accion", "nada")
    cab = f"Sombra: habria {acc.upper()}" if acc != "nada" else "Sombra: nada delante"
    if est.get("texto"):
        cab += f" ({est['texto']})"
    cv2.rectangle(v, (0, 0), (v.shape[1], 24), (20, 20, 20), -1)
    cv2.putText(v, cab, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORES.get(acc, (255, 255, 255)), 1, cv2.LINE_AA)
    cv2.putText(v, f"{est.get('fps', 0):.0f} det/s", (v.shape[1] - 90, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 200, 200), 1, cv2.LINE_AA)
    return v


def disponible():
    """(hay_ultralytics, texto para «Comprobar instalación»)."""
    try:
        import ultralytics  # noqa
    except Exception:  # noqa
        return False, "YOLO (opcional): no instalado. Usa «Instalar YOLO.bat» si quieres la detección de vehículos."
    try:
        import torch
        if torch.cuda.is_available():
            return True, f"YOLO: listo, con la tarjeta de video ({torch.cuda.get_device_name(0)})."
        return True, "YOLO: listo, con el procesador (más lento; para usar la tarjeta instala PyTorch con CUDA)."
    except Exception as e:  # noqa
        return False, f"YOLO: ultralytics está, pero PyTorch no ({e})."

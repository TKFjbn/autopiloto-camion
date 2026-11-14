"""Lectura de textos del HUD (sin tocar el juego, solo mirando la pantalla):

- distancia al próximo punto que muestra el minimapa ("↑ 925m", "→ 2.10km")
- punto cardinal de la caja de zona ("NE", "SO", ...)
- nombre de la zona y de la calle ("Desierto de Grand Señora" / "Autopista de Señora")

La distancia y el punto cardinal se leen con plantillas propias (no hace falta instalar nada).
El nombre de zona y calle necesita un lector de texto (OCR):
  * Windows: `pip install winsdk` (usa el OCR de Windows, el mismo de la herramienta Recortes)
  * o Tesseract: instalar Tesseract-OCR y `pip install pytesseract`
Si no hay OCR, se guarda una imagen de cada zona nueva en la carpeta zonas/ y se identifica
con un código (z1, z2...).
"""
import os
import re
import threading
import hashlib

import cv2
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = None


def _plantillas():
    global _P
    if _P is None:
        d = np.load(os.path.join(_DIR, "plantillas_hud.npz"))
        t = d["dist_t"].reshape(len(d["dist_t"]), -1).astype(np.float32)
        lt = list(d["dist_l"])
        ut, ul = APRENDIDAS.vectores()          # 2.7.2: números aprendidos en este PC (van primero)
        if len(ut):
            t = np.vstack([ut, t])
            lt = ul + lt
        c = d["card_t"].reshape(len(d["card_t"]), -1)
        _P = {"dist": (t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-6), [str(x) for x in lt]),
              "card": (c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-6), [str(x) for x in d["card_l"]])}
    return _P


class PlantillasAprendidas:
    """2.7.2: cómo se ven los números del HUD en ESTE PC (otra resolución los dibuja distinto y el 6 se
    confunde con el 0). Se aprenden solos de las lecturas que cuadran con la anterior, y se guardan en
    mi_equipo/plantillas_hud_usuario_v3.npz (3.0.0: a la escala de referencia). Borrar ese archivo las olvida."""
    POR_CARACTER = 8
    ETIQUETAS = "0123456789.km"

    def __init__(self):
        self.ruta = None
        self.datos = {}            # etiqueta -> [vector 320]
        self.cambios = 0
        self.t_guardado = 0.0

    def cargar(self, ruta):
        self.ruta = ruta
        self.datos = {}
        try:
            d = np.load(ruta)
            for v, l in zip(d["t"], d["l"]):
                self.datos.setdefault(str(l), []).append(v.astype(np.float32).reshape(-1))
        except Exception:  # noqa  (no existe todavía o está dañado)
            pass

    def vectores(self):
        ts, ls = [], []
        for l, vs in self.datos.items():
            for v in vs:
                ts.append(v)
                ls.append(l)
        return (np.array(ts, np.float32) if ts else np.zeros((0, 320), np.float32)), ls

    def cuantos(self):
        return sum(len(v) for v in self.datos.values())

    def aprender(self, glifos):
        """glifos: [(etiqueta, vector 20x16, puntaje, margen)] de una lectura confiable.
        2.7.3: solo aprende caracteres leídos con seguridad (puntaje alto y el segundo candidato lejos)."""
        global _P
        nuevo = False
        for g in glifos:
            lab, vec, s = g[0], g[1], g[2]
            margen = g[3] if len(g) > 3 else 1.0
            if lab not in self.ETIQUETAS or s < 0.85 or margen < 0.04:
                continue
            v = vec.reshape(-1).astype(np.float32)
            v = v / (np.linalg.norm(v) + 1e-6)
            lista = self.datos.setdefault(lab, [])
            if any(float(u @ v) > 0.985 for u in lista):
                continue                          # ya hay uno casi igual
            if len(lista) >= self.POR_CARACTER:
                lista.pop(0)
            lista.append(v)
            nuevo = True
        if nuevo:
            self.cambios += 1
            _P = None                             # recargar plantillas con las nuevas
        return nuevo

    def guardar(self, forzar=False):
        import time
        if not self.ruta or not self.cambios or (not forzar and time.monotonic() - self.t_guardado < 30):
            return
        t, l = self.vectores()
        try:
            os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
            np.savez_compressed(self.ruta, t=t, l=np.array(l))
            self.cambios = 0
            self.t_guardado = time.monotonic()
        except OSError:
            pass


APRENDIDAS = PlantillasAprendidas()


def _blanco(img, umbral=150):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return ((g > umbral) & (hsv[..., 1] < 70)).astype(np.uint8)


def _clasificar(vec, cual):
    t, l = _plantillas()[cual]
    v = vec.reshape(-1)
    v = v / (np.linalg.norm(v) + 1e-6)
    s = t @ v
    i = int(np.argmax(s))
    return l[i], float(s[i])


def _clasificar_margen(vec, cual):
    """Como _clasificar, y además cuánto le gana al mejor carácter DISTINTO (2.7.3, para aprender seguro)."""
    t, l = _plantillas()[cual]
    v = vec.reshape(-1)
    v = v / (np.linalg.norm(v) + 1e-6)
    s = t @ v
    i = int(np.argmax(s))
    otros = [float(s[j]) for j in range(len(l)) if l[j] != l[i]]
    return l[i], float(s[i]), float(s[i]) - (max(otros) if otros else 0.0)


# ------------------------------------------------------------------ regiones
def regiones(cfg, mon_left=0, mon_top=0):
    """Rectángulos (x0, y0, x1, y1) en la captura de pantalla completa, relativos al minimapa."""
    m = cfg["minimapa"]
    w, h = m.get("w_real", m["w"]), m.get("h_real", m["h"])     # 3.0.0: tamaño real en pantalla
    x, y = m["x"] - mon_left, m["y"] - mon_top
    ht = cfg.get("hud_texto", {})
    rd = ht.get("region_distancia", [-0.05, 0.62, 0.65, 1.12])
    rz = ht.get("region_zona", [1.02, 0.55, 3.4, 1.22])
    f = lambda r: (int(x + r[0] * w), int(y + r[1] * h), int(x + r[2] * w), int(y + r[3] * h))
    return {"distancia": f(rd), "zona": f(rz)}


def _recortar(img, r):
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, r[0]), max(0, r[1]), min(W, r[2]), min(H, r[3])
    if x1 - x0 < 10 or y1 - y0 < 8:
        return None
    return img[y0:y1, x0:x1]


# ------------------------------------------------------------------ distancia
def leer_distancia(reg):
    """reg: recorte BGR alrededor de la esquina inferior izquierda del minimapa.
    Devuelve {"metros", "texto", "flecha", "glifos"} o None (glifos: para aprender, 2.7.2)."""
    if reg is None:
        return None
    b = _blanco(reg)
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    H_reg = reg.shape[0]
    cand = [st[i] for i in range(1, n) if 6 <= st[i][3] <= 0.6 * H_reg and st[i][2] <= 1.6 * st[i][3]
            and st[i][4] >= 8]
    if len(cand) < 2:
        return None
    # agrupar por línea de base (parte de abajo)
    mejor = None
    for c in cand:
        base = c[1] + c[3]
        grupo = [k for k in cand if abs(k[1] + k[3] - base) <= 3]
        if mejor is None or len(grupo) > len(mejor):
            mejor = grupo
    if len(mejor) < 2:
        return None
    Hl = max(k[3] for k in mejor)          # altura de línea: el carácter más alto
    base = max(k[1] + k[3] for k in mejor)
    top = max(0, min(k[1] for k in mejor))
    Hl = base - top
    x0 = max(0, min(k[0] for k in mejor) - int(2.5 * Hl))
    x1 = min(b.shape[1], max(k[0] + k[2] for k in mejor) + 2)
    banda = b[top:base, x0:x1]
    col = banda.sum(0)
    trozos, x = [], 0
    while x < len(col):
        if col[x] > 0:
            a = x
            while x < len(col) and col[x] > 0:
                x += 1
            trozos.append((a, x))
        x += 1
    texto, flecha, gap_prev = "", None, None
    glifos = []
    Wc = int(round(Hl * 0.9))
    for a, z in trozos:
        sub = banda[:, a:z].astype(np.float32)
        if sub.sum() < 3:
            continue
        can = np.zeros((Hl, Wc), np.float32)
        w = min(z - a, Wc)
        can[:min(Hl, sub.shape[0]), :w] = sub[:Hl, :w]
        vec = cv2.resize(can, (16, 20), interpolation=cv2.INTER_AREA)
        lab_, s, margen = _clasificar_margen(vec, "dist")
        if s < 0.72:
            continue
        if lab_ in "^<>/\\":
            if not texto:
                flecha = {"^": "↑", "<": "←", ">": "→", "/": "↗", "\\": "↖"}[lab_]
            continue
        texto += lab_
        glifos.append((lab_, vec, s, margen))
    mt = re.search(r"(\d+(?:\.\d+)?)(km|m)", texto)
    if not mt:
        return None
    if mt.group(2) == "km" and "." not in mt.group(1) and len(mt.group(1)) >= 3:
        # el punto a veces no se ve (fondo claro): los km siempre llevan 2 decimales
        texto = mt.group(1)[:-2] + "." + mt.group(1)[-2:] + "km"
        mt = re.search(r"(\d+(?:\.\d+)?)(km|m)", texto)
    v = float(mt.group(1))
    metros = v * 1000 if mt.group(2) == "km" else v
    if metros > 30000:
        return None
    return {"metros": metros, "texto": mt.group(0), "flecha": flecha, "glifos": glifos}


# ------------------------------------------------------------------ caja de zona
def analizar_zona(reg):
    """Caja de zona: 'NE | Vinewood Hills / Autopista de Los Santos'.
    Devuelve {"cardinal", "img_zona", "img_calle"} o None."""
    if reg is None:
        return None
    g = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    b = ((g > 170) & (hsv[..., 1] < 60)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    barras = [i for i in range(1, n) if st[i][3] >= 14 and st[i][3] >= 4 * st[i][2] and st[i][2] <= 8]
    if not barras:
        return None
    bi = min(barras, key=lambda i: st[i][0])
    bx, by, bw, bh = st[bi][:4]
    letras = sorted([i for i in range(1, n) if st[i][0] + st[i][2] <= bx - 2 and st[i][3] >= 0.6 * bh
                     and st[i][0] > bx - 4 * bh and abs((st[i][1] + st[i][3] / 2) - (by + bh / 2)) < bh * 0.4],
                    key=lambda i: st[i][0])
    card = ""
    for i in letras[-2:]:
        x, y, w, h = st[i][:4]
        sub = (lab[y:y + h, x:x + w] == i).astype(np.float32)
        l, s = _clasificar(cv2.resize(sub, (16, 24), interpolation=cv2.INTER_AREA), "card")
        if s > 0.8:
            card += l
    if card not in ("N", "S", "E", "O", "NE", "NO", "SE", "SO"):
        card = None
    # texto a la derecha de la barra: línea naranja (zona) y línea blanca (calle)
    xd = bx + bw + 4
    der = reg[max(0, by - 4):by + bh + 6, xd:]
    if der.shape[1] < 20:
        return {"cardinal": card, "img_zona": None, "img_calle": None}
    hd = cv2.cvtColor(der, cv2.COLOR_BGR2HSV)
    naranja = ((hd[..., 0] >= 8) & (hd[..., 0] <= 30) & (hd[..., 1] > 120) & (hd[..., 2] > 150)).astype(np.uint8)
    blanco = ((cv2.cvtColor(der, cv2.COLOR_BGR2GRAY) > 170) & (hd[..., 1] < 60)).astype(np.uint8)

    # fin del bloque de texto: primer hueco ancho de columnas vacías (a la derecha suele haber
    # otras cosas del HUD, como el velocímetro)
    cols = (naranja | blanco).sum(0) > 0
    fin, vacio = len(cols), 0
    empezo = False
    for xx, c in enumerate(cols):
        if c:
            empezo, vacio = True, 0
        elif empezo:
            vacio += 1
            if vacio > max(8, 0.6 * bh):
                fin = xx - vacio + 1
                break
    naranja[:, fin:] = 0
    blanco[:, fin:] = 0

    def linea(mask, desde=0):
        mask = mask.copy()
        mask[:desde] = 0
        filas = np.nonzero(mask.sum(1) >= 2)[0]
        if len(filas) < 4:
            return None, desde
        # primera línea de texto (filas seguidas, con huecos de 1-2 px)
        y0 = y1 = filas[0]
        for f in filas[1:]:
            if f - y1 > 3:
                break
            y1 = f
        cols_ = np.nonzero(mask[y0:y1 + 1].sum(0))[0]
        if len(cols_) < 4:
            return None, desde
        x0, x1 = max(0, cols_[0] - 2), min(der.shape[1], cols_[-1] + 3)
        return der[max(0, y0 - 2):min(der.shape[0], y1 + 3), x0:x1], y1 + 1
    iz, fin_z = linea(naranja)
    ic, _ = linea(blanco, fin_z)
    return {"cardinal": card, "img_zona": iz, "img_calle": ic}


def huella(img):
    """Código corto de una imagen de texto (para agrupar zonas aunque no haya OCR)."""
    if img is None or img.size == 0:
        return None
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (32, 8), interpolation=cv2.INTER_AREA)
    bits = (g > g.mean()).astype(np.uint8).reshape(-1)
    return hashlib.md5(bits.tobytes()).hexdigest()[:8]


# ------------------------------------------------------------------ OCR (opcional)
class LectorTexto:
    """OCR de Windows (winsdk / winrt) o Tesseract. Se usa en un hilo aparte."""

    def __init__(self):
        self.nombre = None
        self._fn = None
        try:
            self._fn = self._crear_windows()
            self.nombre = "OCR de Windows"
        except Exception:
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._fn = lambda im: pytesseract.image_to_string(im, lang=self._lang_tess(pytesseract),
                                                                  config="--psm 7")
                self.nombre = "Tesseract"
            except Exception:
                self._fn = None

    @staticmethod
    def _lang_tess(pt):
        try:
            return "spa" if "spa" in pt.get_languages(config="") else "eng"
        except Exception:
            return "eng"

    @staticmethod
    def _crear_windows():
        import asyncio
        try:
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
            from winsdk.windows.storage.streams import DataWriter
        except ImportError:
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
            from winrt.windows.storage.streams import DataWriter
        motor = OcrEngine.try_create_from_user_profile_languages()
        if motor is None:
            raise RuntimeError("sin idioma OCR")

        def leer(im):
            bgra = cv2.cvtColor(im, cv2.COLOR_BGR2BGRA)
            h, w = bgra.shape[:2]
            dw = DataWriter()
            dw.write_bytes(bytes(bgra.tobytes()))
            bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h,
                                                         BitmapAlphaMode.PREMULTIPLIED)

            async def r():
                return await motor.recognize_async(bmp)
            return asyncio.run(r()).text
        leer(np.full((40, 120, 3), 255, np.uint8))     # prueba
        return leer

    def disponible(self):
        return self._fn is not None

    def leer(self, img):
        if self._fn is None or img is None or img.size == 0:
            return None
        # texto claro sobre fondo oscuro -> invertir y agrandar ayuda al OCR
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(255 - g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        g = cv2.copyMakeBorder(g, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        try:
            t = self._fn(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
        except Exception:
            return None
        t = " ".join((t or "").split()).strip(" |_-—.,;:'\"")
        return t or None


class MonitorHud:
    """Lee distancia, punto cardinal, zona y calle de vez en cuando (hilo aparte para el OCR)."""

    def __init__(self, cfg, carpeta_zonas=None):
        self.cfg = cfg
        self.estado = {"metros": None, "dist_texto": None, "flecha": None, "cardinal": None,
                       "zona": None, "calle": None}
        self.carpeta = carpeta_zonas or os.path.join(os.path.dirname(cfg.get("_ruta", _DIR + "/x")), "zonas")
        self.ocr = None
        self._cache = {}
        import queue
        self._cola = queue.Queue()
        self._hilo = None
        self._codigos = {}
        try:                                                    # 2.7.2: números aprendidos en este PC
            import carpetas
            APRENDIDAS.cargar(os.path.join(carpetas.EQUIPO, "plantillas_hud_usuario_v3.npz"))
            global _P
            _P = None
            if APRENDIDAS.cuantos():
                print(f"[i] Números del HUD aprendidos en este PC: {APRENDIDAS.cuantos()}.")
        except Exception:  # noqa
            pass

    # ---------------------------------------------------------- 2.7.2: lecturas imposibles
    def _filtrar_distancia(self, d):
        """La distancia baja de a poco. Una lectura que salta (5540 -> 6640 -> 5530, o 5540 -> 500) no se usa.
          - si cambiando un dígito confundible cuadra (2970 viniendo de 2120: el 0 leído como 9), se corrige;
          - 2.7.3: un salto solo se acepta como real si se repite varias lecturas seguidas (salto_lecturas),
            salvo un salto hacia arriba justo al llegar a un punto (menos de 300 m: al cargar o descargar),
            que basta con que se repita una vez.
        Las lecturas que cuadran con la anterior enseñan cómo se ven los números en este PC."""
        import time
        hc = self.cfg.get("hud_texto", {})
        ahora = time.monotonic()
        m = d["metros"]
        ult = getattr(self, "_d_ult", None)
        margen = hc.get("distancia_margen_m", 30)
        if ult is None or not hc.get("filtrar_distancia", True):
            self._d_ult, self._d_cand = (m, ahora), None
            return d
        m0, t0 = ult
        dt = max(0.05, ahora - t0)
        baja = m0 - m
        tol_baja = hc.get("distancia_max_mps", 45) * dt + margen
        if -margen <= baja <= tol_baja:
            self._d_ult, self._d_cand = (m, ahora), None
            if hc.get("aprender_numeros", True) and -10 <= baja <= hc.get("aprender_baja_max_m", 40) \
                    and dt <= 2.5 and d.get("glifos") and ahora - getattr(self, "_t_salto", -99.0) > 15:
                APRENDIDAS.aprender(d["glifos"])
                APRENDIDAS.guardar()
            return d
        # ¿es un dígito mal leído? -> se corrige
        import rutas
        buenas = [v for v in rutas._variantes(m) if -margen <= m0 - v <= tol_baja]
        if buenas:
            v = min(buenas, key=lambda x: abs(m0 - x))      # la que menos se aleja de la anterior
            self._d_ult, self._d_cand = (v, ahora), None
            self.corregidas = getattr(self, "corregidas", 0) + 1
            return dict(d, metros=v, texto=f"{d['texto']}→{v:.0f}m", glifos=[])
        # salto: contar cuántas lecturas seguidas lo repiten (cada una cuadra con la anterior del salto)
        cand = getattr(self, "_d_cand", None)          # (último valor, cuántas, t)
        if cand is not None:
            c_m, c_n, c_t = cand
            c_dt = max(0.05, ahora - c_t)
            if -margen - 15 <= c_m - m <= hc.get("distancia_max_mps", 45) * c_dt + margen + 15:
                c_n += 1
                necesarias = 2 if (m0 < 300 and m > m0) else hc.get("salto_lecturas", 5)
                if c_n >= necesarias:
                    self._d_ult, self._d_cand = (m, ahora), None
                    self._t_salto = ahora
                    self.saltos = getattr(self, "saltos", 0) + 1
                    return d
                self._d_cand = (m, c_n, ahora)
                self.descartadas = getattr(self, "descartadas", 0) + 1
                return None
        self._d_cand = (m, 1, ahora)
        self.descartadas = getattr(self, "descartadas", 0) + 1
        return None

    def iniciar_ocr(self):
        self.ocr = LectorTexto()
        if self.ocr.disponible():
            print(f"[i] Nombres de zona y calle: {self.ocr.nombre}.")
        else:
            print("[i] Nombres de zona/calle: sin OCR (instala 'winsdk' con pip para leerlos). "
                  "Se guardan imágenes en la carpeta zonas/.")
        self._hilo = threading.Thread(target=self._trabajo, daemon=True)
        self._hilo.start()

    def _nombre(self, img, tipo):
        h = huella(img)
        if h is None:
            return None
        if h in self._cache:
            return self._cache[h]
        self._cache[h] = None                 # en cola (el hilo lo rellenará)
        self._cola.put((h, img.copy(), tipo))
        return None

    def _trabajo(self):
        while True:
            h, img, tipo = self._cola.get()
            txt = self.ocr.leer(img) if self.ocr and self.ocr.disponible() else None
            if not txt:
                cod = self._codigos.setdefault(h, f"{tipo[0]}{len(self._codigos) + 1}-{h[:4]}")
                txt = f"[{cod}]"
                try:
                    os.makedirs(self.carpeta, exist_ok=True)
                    ruta = os.path.join(self.carpeta, f"{cod}.png")
                    if not os.path.exists(ruta):
                        cv2.imwrite(ruta, cv2.resize(img, None, fx=2, fy=2))
                except Exception:
                    pass
            self._cache[h] = txt

    def actualizar(self, pantalla, mon_left=0, mon_top=0):
        r = regiones(self.cfg, mon_left, mon_top)
        import geometria                                     # 3.0.0: textos a la escala de referencia
        try:
            d = leer_distancia(geometria.a_referencia(_recortar(pantalla, r["distancia"]), self.cfg))
        except Exception:
            d = None
        if d is not None:
            d = self._filtrar_distancia(d)
        if d is not None:
            self.estado.update({"metros": d["metros"], "dist_texto": d["texto"], "flecha": d["flecha"]})
        try:
            z = analizar_zona(geometria.a_referencia(_recortar(pantalla, r["zona"]), self.cfg))
        except Exception:
            z = None
        if z is not None:
            if z["cardinal"]:
                self.estado["cardinal"] = z["cardinal"]
            nz = self._nombre(z["img_zona"], "zona")
            nc = self._nombre(z["img_calle"], "calle")
            if nz:
                self.estado["zona"] = nz
            if nc:
                self.estado["calle"] = nc
        return self.estado

    def texto(self):
        e = self.estado
        partes = []
        if e["metros"] is not None:
            partes.append(f"{e['flecha'] or ''} {e['dist_texto']}".strip())
        if e["cardinal"]:
            partes.append(e["cardinal"])
        if e["zona"]:
            partes.append(e["zona"])
        if e["calle"]:
            partes.append(e["calle"])
        return " | ".join(partes)

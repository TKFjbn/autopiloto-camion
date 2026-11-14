"""
Mide la zona muerta del stick del mando en GTA (el valor por debajo del cual GTA
ignora el volante). Con ese valor el autopiloto compensa las correcciones pequeñas
y el camión deja de quedarse desviado de la línea del GPS.

Cómo funciona:
  1. Pon el camión en un sitio ABIERTO y llano (un estacionamiento grande), parado,
     en primera persona, y vuelve al juego.
  2. El programa avanza despacio (~12 km/h) en línea recta y prueba volantes cada vez
     mayores (0.04, 0.08, ...), a izquierda y derecha, midiendo si el camión gira
     (rotación del minimapa).
  3. El primer valor que hace girar al camión es la zona muerta. Se guarda en config.json.
Pulsa S o ESPACIO en cualquier momento para cancelar.
"""
import math
import time

import cv2
import numpy as np

import configuracion
import entrada
import vision


def _rotacion(orb, a, b, mascara):
    ka, da = orb.detectAndCompute(a, mascara)
    kb, db = orb.detectAndCompute(b, mascara)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return None
    mt = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
    if len(mt) < 10:
        return None
    A = np.float32([ka[m.queryIdx].pt for m in mt])
    B = np.float32([kb[m.trainIdx].pt for m in mt])
    M, inl = cv2.estimateAffinePartial2D(A, B, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None or inl is None or inl.sum() < 8:
        return None
    return math.degrees(math.atan2(M[1, 0], M[0, 0]))


def medir(config=None, parar=None):
    cfg = configuracion.cargar(config)
    import geometria
    geometria.preparar(cfg)                     # 3.0.0: según la ventana del juego, minimapa en unidad fija
    m = cfg["minimapa"]
    px, py = cfg["jugador"]["x"], cfg["jugador"]["y"]
    try:
        ctrl = entrada.ControlMando(0.0)        # sin compensar: queremos ver la zona muerta real
    except Exception as e:  # noqa
        print(f"[!] Hace falta el mando virtual (vgamepad) para medir la zona muerta: {e}")
        return None
    cap = vision.Captura(m)
    vel = None
    if cfg["velocimetro"].get("activo", True):
        try:
            import velocimetro
            vel = velocimetro.Velocimetro(cfg["velocimetro"])
        except Exception:
            vel = None
    orb = cv2.ORB_create(nfeatures=600, scaleFactor=1.2, nlevels=4, edgeThreshold=10, patchSize=15, fastThreshold=6)
    mascara = np.full((m["h"], m["w"]), 255, np.uint8)
    mascara[int(m["h"] * 0.8):, :] = 0                       # texto de distancia abajo
    cv2.circle(mascara, (px, py), 14, 0, -1)                 # la flecha
    toma = [k for k in cfg["teclas"]["tomar_control"]]

    def cancelado():
        if parar is not None and parar.is_set():
            return True
        return any(entrada.tecla_pulsada(entrada.VK[entrada.validar_tecla(k, "tomar_control")]) for k in toma)

    def tramo(direccion, segundos, medir_giro=True):
        """Mantiene un volante durante X s y devuelve el giro medio (°/s) de la segunda mitad.
        La rotación se mide entre imágenes separadas ~0.4 s (más precisa que entre fotogramas seguidos)."""
        t0 = time.time()
        hist = []
        giros = []
        while time.time() - t0 < segundos:
            if cancelado():
                raise KeyboardInterrupt
            try:
                kmh = vel.leer() if vel else 12
            except Exception:
                kmh = 12
            acel = 0.45 if kmh < 10 else (0.25 if kmh < 14 else 0.0)
            ctrl.set(direccion, acel, 0.0)
            time.sleep(0.05)
            ahora = time.time()
            g = cv2.cvtColor(cap.leer(), cv2.COLOR_BGR2GRAY)
            hist.append((ahora, g))
            viejos = [h for h in hist if ahora - h[0] >= 0.4]
            if medir_giro and viejos and ahora - t0 > segundos * 0.45:
                t1, g1 = viejos[-1]
                r = _rotacion(orb, g1, g, mascara)
                if r is not None:
                    giros.append(-r / (ahora - t1))
            hist = [h for h in hist if ahora - h[0] < 1.0]
        return float(np.median(giros)) if giros else 0.0

    print("[i] Medición de zona muerta: tienes 5 s para volver al juego (camión parado, sitio abierto).")
    for i in range(5, 0, -1):
        print(f"    {i}...")
        time.sleep(1)
        if cancelado():
            ctrl.soltar_todo()
            print("[i] Cancelado.")
            return None
    resultado = None
    try:
        print("[i] Avanzando en recta para medir el giro sin volante...")
        tramo(0.0, 3.0, medir_giro=False)
        base = abs(tramo(0.0, 1.5))
        print(f"    giro con volante 0: {base:.1f} °/s (ruido)")
        umbral = max(1.5, base * 2 + 0.8)
        datos = []
        for paso in np.arange(0.04, 0.50, 0.04):
            gi = tramo(+paso, 1.6)
            tramo(0.0, 0.6, medir_giro=False)
            gd = tramo(-paso, 1.6)
            tramo(0.0, 0.6, medir_giro=False)
            giro = (abs(gi) + abs(gd)) / 2
            print(f"    volante {paso:.2f}: giro {giro:4.1f} °/s")
            datos.append((paso, giro))
            sobre = [(p, g) for p, g in datos if g > umbral]
            if len(sobre) >= 3:
                # recta giro = k·(volante - zona_muerta) con los puntos que ya giran
                P = np.array(sobre)
                k, b = np.polyfit(P[:, 0], P[:, 1], 1)
                if k > 0:
                    resultado = round(float(np.clip(-b / k, 0.0, sobre[0][0])), 2)
                else:
                    resultado = round(sobre[0][0] - 0.02, 2)
                break
    except KeyboardInterrupt:
        print("[i] Cancelado por el usuario.")
    finally:
        ctrl.set(0.0, 0.0, 0.6)
        time.sleep(1.0)
        ctrl.soltar_todo()
        ctrl.cerrar()
    if resultado is None:
        print("[!] No se pudo medir (¿el camión no avanzó o el minimapa no se veía?). Se mantiene el valor actual.")
        return None
    cfg = configuracion.cargar(config)
    cfg["control"]["mando_zona_muerta"] = float(resultado)
    configuracion.guardar(cfg, config)
    print(f"[OK] Zona muerta del mando: {resultado:.2f}. Guardado en config.json (control.mando_zona_muerta).")
    return resultado


if __name__ == "__main__":
    medir()

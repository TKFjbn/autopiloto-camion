"""
Configuración por defecto + carga/migración de config.json.

Tu config.json solo necesita los valores que quieras cambiar; el resto sale de
aquí. Si vienes de la versión 1, se conserva tu calibración (minimapa, jugador,
color, radios) y se guarda una copia en config_v1_respaldo.json.
"""
import copy
import json
import os
import shutil

VERSION = 34   # 3.0.0: calibración relativa a la ventana y unidad fija del minimapa

DEFAULTS = {
    "version": VERSION,
    "minimapa": {"x": 28, "y": 872, "w": 272, "h": 180},   # posición real en pantalla (la última conocida)
    "jugador": {"x": 135, "y": 136},                      # 3.0.0: en la unidad fija del minimapa (272 x 180)
    "calibracion": None,                                  # 3.0.0: relativa a la ventana del juego (geometria.py)
    "color_ruta_hsv": [[0, 120, 120, 8, 255, 255], [172, 120, 120, 179, 255, 255]],
    "vision": {
        "radio_cerca": 30,
        "radio_lejos": 60,
        "radio_anticipacion": 125,    # hasta dónde se mira para frenar antes de curvas
        "radio_inicio": 13,           # primer anillo: fuera de la flecha blanca (tapa la ruta)
        "paso_anillo": 3,
        "radio_ajuste": 30,           # tramo junto al camión que se usa para dirigir
        "esquina_grados": 35,         # giro brusco de la ruta = esquina
        "adelanto_giro_px": 16,       # empieza a girar cuando la esquina está a X px (más = gira antes)
        "calle_ancho_max_centrar": 12,  # calles más anchas (avenidas) no se centran: se sigue el GPS
        "calle_corr_max_px": 2.5,       # máximo que se aparta del GPS hacia el centro de la calle
        "puntos_cuerda": 6,           # suavizado de la ruta para medir curvas (más = ignora más zigzags)
        "tolerancia_anillo": 2.5,
        "angulo_max": 120,
        "max_dist_inicio": 30,
    },
    "velocimetro": {
        "activo": True,
        "region": {"x": 1690, "y": 965, "w": 225, "h": 55},
        "color_hsv": [18, 80, 120, 38, 255, 255],
        "confianza_min": 0.45,
    },
    "calle": {
        "correccion_max_px": 0.8,     # v27: empuje máximo hacia el centro de la calle gris si el GPS va por una calle
        "activo": True,               # usar las calles grises del minimapa
        "saturacion_max": 45,
        "claridad_sobre_fondo": 22,   # cuánto más clara que su entorno debe ser una calle
        "ventana_fondo": 31,          # tamaño de la zona para medir el fondo (minimapa semitransparente)
        "ancho_max_calle_px": 16,     # manchas más anchas (mar, lagos) no son calle
        "peso_correccion": 0.5,       # cuánto se mueve hacia el centro de la calle (0 = solo GPS)
        "fuera_umbral": 0.35,         # menos calle que esto delante = fuera de la calle
        "fuera_seg": 0.4,
        "objetivo_fuera_de_calle": 20,
    },
    "carril": {
        "activo": True,               # detectar el carril en la imagen del juego (requiere calibrar el trapecio)
        "trapecio": None,             # 4 esquinas del carril en pantalla: cerca-izq, lejos-izq, lejos-der, cerca-der
        "conf_min": 0.75,             # solo dirige con el carril si la detección es así de segura
        "peso_grados": 12,            # grados de corrección por cada ancho de carril de desvío
        "tope_grados": 8,
        "filtro_correccion": 0.92,    # la corrección cambia despacio (0.9-0.97: más alto = más suave)
        "sesgo": 0.0,                 # desplazamiento del centro del carril (se aprende solo con el GPS)
        "aprendizaje_sesgo": 0.995,
        "reduccion_gps": 0.6,         # cuánto se reduce la corrección por GPS cuando se usa el carril
        "giro_max": 35,               # no usar en curvas más fuertes que esto ni cerca de esquinas
        "kmh_min": 15,
        "suavizado": 0.5,
        "contraste_min": 22,
        "asfalto_v_max": 150,
        "ipm_pixeles_min": 18,
        "ipm_busqueda_px": 22,
        # 3.2.0: una sola línea (recta y clara) también sirve, con menos fuerza
        "conf_min_una_linea": 0.55,   # desde esta confianza se usa la cámara aunque vea una sola línea
        "peso_una_linea": 0.5,        # fuerza de la corrección en ese caso (1 = como con dos líneas)
        "conf_una_linea": 0.65,       # confianza que da una sola línea perfecta (+0.05 si es la amarilla)
        "ipm_franjas": 4,             # la línea debe verse en casi todas estas franjas, en la misma columna
        "ipm_recta_tol_px": 8,        # cuánto se puede correr entre franjas (lo diagonal no cuenta)
        "amarillo_dif_rel": 14,       # amarilla por color: cuánto más amarilla que su entorno
        "bordillo_rojo": True,        # contar el borde rojo de la calzada como línea
    },
    "esquinas": {
        "giro_esquina_grados": 75,    # esquina cerrada: la ruta gira esto o más
        "objetivo_esquina_kmh": 20,   # velocidad para esquinas cerradas
        "objetivo_esquina_muy_cerrada_kmh": 14,  # 110° o más
        # giro TARDÍO en esquinas: seguir recto hasta llegar a la esquina y entonces girar fuerte
        "giro_tardio_grados": 55,     # esquinas de este ángulo o más se toman así
        "giro_tardio_px": 6,          # empieza a girar cuando la esquina está a X px (menos = más tarde)
        "frente_flecha_px": 7.0,      # 3.2.1: de centro a donde el programa ve nacer la línea del GPS (3.2.2: 4,5 -> 7)
        "giro_tardio_ganancia": 1.4,  # fuerza extra del volante al girar en la esquina (menos = giro más abierto)
        "giro_tardio_muy_cerrada_grados": 80,  # esquinas aún más cerradas (calles angostas)...
        "giro_tardio_muy_cerrada_px": 3,       # ...avanzar más antes de girar
        "girar_si_bloqueado_seg": 0.8,  # si está parado frente a una esquina pendiente, girar ya
        "abrir_antes_px": 0.0,        # antes de la esquina, abrirse hacia fuera X px (0 = seguir el centro de la ruta)
        "abrir_desde_px": 45,         # empezar a abrirse cuando la esquina está a menos de X px
        "maniobra_rumbo_grados": 110, # la ruta queda detrás/al lado: maniobrar marcha atrás
        "maniobra_kmh_max": 15,
        "maniobra_seg": 1.0,
        "maniobra_reversa_seg": 3.5,
        "maniobra_max_intentos": 6,   # en 40 s; después se desactiva y avisa
    },
    "control": {
        "backend": "teclado",
        "mando_zona_muerta": 0.20,    # zona muerta del stick en GTA (se compensa). Mídela con la herramienta de la interfaz
        "periodo_pwm": 0.12,
        # "persecucion": apunta a un punto de la ruta a cierta distancia (como conduces tú, medido
        #  en tus videos: ~27 px por delante). "rumbo": método anterior (dirección del tramo + desvío).
        "modo_direccion": "persecucion",
        "persecucion_px_por_velocidad": [[0, 20], [30, 24], [60, 28], [90, 34]],  # para un minimapa de ~176 px de alto
        "kp_persecucion": 0.011,      # fuerza del volante por grado de ángulo al punto
        "persecucion_desvio_grados_px": 1.0,  # además, corregir el desvío lateral respecto a la línea (° por px)
        "persecucion_desvio_tope": 12,
        "persecucion_desvio_zona_muerta_px": 1.0,
        # corrección LENTA del desvío que persiste en rectas (quita la tendencia a ir hacia un lado)
        "integral_desvio_grados_px_seg": 0.4,
        "integral_desvio_tope_grados": 6,
        "persecucion_acortar_en_curva": [[0, 1.0], [20, 0.85], [40, 0.7]],  # [tasa de giro, factor de la distancia]
        "kp": 0.020,                  # fuerza del volante (modo "rumbo")
        "kd": 0.0015,
        "peso_desvio": 3.5,           # grados de corrección por cada px que te sales de la ruta
        "peso_desvio_por_velocidad": [[0, 1.0], [40, 1.15], [80, 1.4]],  # a más velocidad, cada px son más metros
        "limite_desvio_grados": 25,   # tope de la corrección lateral (que no anule el giro de la curva)
        "limite_desvio_fuera_calle": 40,
        # ir desplazado respecto a la línea roja: - = más a la IZQUIERDA (suele haber menos postes y
        # señales), + = derecha. En curvas a la izquierda se reduce solo (para no cortar por dentro).
        "desplazamiento_carril_px": 0.0,    # v31: sobre la línea; a la izquierda solo donde lo diga una regla
        "desplazamiento_quitar_curva_grados": 12,  # volver a la línea antes de curvas hacia ese lado desde X°
        "zona_muerta_grados": 0.5,
        "cambio_max_por_seg": 2.5,    # límite de rapidez del volante (anti-zigzag)
        "suavizado": 0.4,
        "ganancia_por_velocidad": [[0, 1.7], [15, 1.3], [35, 1.0], [60, 0.8], [90, 0.65]],
        "curva_rapida_kmh": 45,       # v28: desde esta velocidad, si la carretera ya dobla...
        "curva_rapida_ganancia": [[10, 1.0], [25, 1.6]],  # ...girar más fuerte (grados de rumbo -> factor)
        "curva_rapida_peso_giro": 0.6,  # v29: también cuenta la curva que se ve venir (giro total x 0.6)
        "invertir_direccion": False,
    },
    "velocidad": {
        "objetivo_recta": 80,
        "objetivo_recta_larga": 100,   # recta larga y despejada en el minimapa
        "recta_larga_px": 90,          # largo mínimo de ruta recta visible (minimapa de ~176 px)
        "recta_larga_giro_max": 8,     # grados máximos que puede girar la ruta para contar como recta
        "recta_larga_seg": 2.0,        # tiempo que debe seguir recta antes de subir a la velocidad larga
        "objetivo_curva": 60,          # curva normal (~40°)
        "objetivo_curva_cerrada": 40,  # curva cerrada / esquina (~75° o más)
        "objetivo_cerca_destino": 30,
        "objetivo_por_giro_total": [[20, 80], [35, 70], [55, 58], [80, 46]],  # curvas largas (grados -> km/h; v30 más rápido)
        "giro_total_extra_por_px": 0.25,
        "bajada_reduccion_kmh": 10,   # v28: en bajada (gana velocidad sin acelerar) curvas X km/h más despacio
        "bajada_seg": 4.0,
        "objetivo_bifurcacion": 55,   # la calle se abre en dos delante (separador, salida): 0 = no frenar
        "objetivo_bifurcacion_autopista": 70,
        "regla_antes_m": 80,          # v31: empezar a bajar X m antes de una regla con límite...
        "regla_antes_kmh_por_m": 0.5, # ...permitiendo límite + 0,5 km/h por cada metro que falta  # v30: lo mismo en autopista (calle "Autopista ..."/"... Fwy")
        "objetivo_desviado": 0,       # (0 = desactivado) límite si va desviado de la línea más de desviado_px
        "desviado_px": 5.0,
        "objetivo_ignorar_fotogramas": 2,  # ignora bajadas del objetivo que duran 1-2 fotogramas (ruido)
        "curva_suave_grados": 20,     # cambios de dirección menores no cuentan como curva
        "rumbo_que_cuenta_como_curva": 35,  # camión muy torcido respecto a la ruta: ir más despacio
        "desvio_para_ir_lento_px": 14,      # muy fuera de la ruta: bajar la velocidad para volver
        "desvio_para_ir_lento_seg": 1.5,    # ...solo si dura (el GPS a veces se sale de la calle)
        "objetivo_fuera_de_ruta": 30,
        "curva_ref_grados": 40,
        "curva_cerrada_grados": 75,
        "kmh_extra_por_px": 0.45,
        # curvas por lo CERRADAS que son: grados que gira la ruta en ~20 px -> km/h
        "objetivo_por_tasa_giro": [[10, 80], [18, 74], [28, 61], [40, 49], [60, 35]],     # una curva lejana permite ir más rápido (km/h por px de distancia)
        "memoria_curva_seg": 1.5,     # mantiene el objetivo bajo un rato (evita frena/acelera)
        "subida_objetivo_kmh_seg": 8, # cuánto puede subir el objetivo por segundo
        # --- control de velocidad (v6): el HUD se actualiza cada ~0.6 s y con retraso,
        #     por eso se predice la velocidad real y se prefiere soltar a frenar ---
        "retraso_hud_seg": 0.35,      # cuánto va atrasado el número del HUD
        # acelerador para mantener cada velocidad en llano: [km/h, acelerador]
        "acelerador_crucero_por_velocidad": [[15, 0.22], [45, 0.30], [80, 0.48], [100, 0.62]],
        "kp": 0.025,                  # (antiguo; ya no se usa)
        "kp_acelerador": 0.03,        # acelerador extra por km/h que falta (v25: control suave, sin tirones)
        "ki_acelerador": 0.012,       # aprende el acelerador que hace falta (carga, cuestas)
        "integral_acelerador_max": 0.4,
        "bajada_acelerador_por_seg": 1.5,  # el acelerador baja como mucho esto por segundo
        "tras_freno_seg": 0.8,        # tras frenar, no pasar del acelerador de crucero durante X s
        "acelerador_max_en_marcha": 1.0,
        "subida_acelerador_por_seg": 1.0,
        "soltar_antes_kmh": 4,        # suelta el acelerador X km/h antes de llegar al objetivo si sube rápido
        "acelerador_arranque": 1.0,
        "segundos_parado_para_arranque": 1.2,
        # a velocidades objetivo bajas no se pisa a fondo (el camión se pasaría): [km/h objetivo, acelerador máx]
        "acelerador_max_por_objetivo": [[10, 0.40], [20, 0.55], [35, 0.85], [50, 1.0]],
        "subida_refuerzo_por_seg": 0.35,  # si va lento sin llegar al objetivo (subida), el acelerador sube poco a poco
        "subida_refuerzo_max": 0.5,   # acelerador extra máximo en subida
        "margen_sin_frenar_lento_kmh": 9,  # a velocidades objetivo bajas (≤30) solo suelta hasta pasarse esto
        "soltar_progresivo_kmh": 8,   # (antiguo; ya no se usa)
        "amortiguacion_seg": 0.0,     # anticipa la velocidad X s (0 = no; la predicción del HUD ya lo hace)
        "sin_freno_bajo_kmh": 20,     # por debajo de esta velocidad solo frena si se pasa mucho
        "sin_freno_bajo_margen_kmh": 10,
        "margen_sin_frenar_kmh": 12,  # en recta: por encima del objetivo hasta aquí solo suelta
        "margen_sin_frenar_curva_kmh": 5,  # antes de una curva frena antes
        "margen_sin_frenar_curva_suave_kmh": 8,  # v30: en curvas largas/suaves solo suelta hasta pasarse esto
        "frenar_exceso_lectura_kmh": 3,  # v30: en tramos suaves, frenar solo si el HUD YA marca objetivo + X
                                         # (la predicción sola causaba frena-acelera en curvas)
        "freno_max": 0.35,
        "freno_pulso_seg": 0.3,       # frena a pulsos cortos (más largos si va muy pasado)...
        "freno_espera_seg": 0.8,      # ...y espera a ver el efecto en el HUD
        "sin_velocimetro_recta": 0.6,
        "sin_velocimetro_curva": 0.45,
    },
    "etapas": {
        "llegada_seg": 1.5,
        "ruta_estable_seg": 1.5,
        "tramos": ["Ir a cargar", "Ir al punto de entrega (A)", "Volver a la zona de trabajo (B)"],
    },
    "atasco": {
        "activo": True,
        "segundos": 3.0,              # acelerando a fondo sin moverse durante X s -> marcha atrás
        "kmh_max": 5,
        "choque_caida_kmh": 25,       # bajar X km/h de golpe sin frenar = choque
        "choque_ventana_seg": 1.0,
        "umbral_movimiento": 1.0,     # solo si no hay velocímetro
        "reversa_seg": 4.0,
        "cancelar_reversa_kmh": 20,   # v33: si en la marcha atrás sigue avanzando más rápido que esto, se cancela
        "reversa_kmh_max": 6,         # velocidad máxima marcha atrás al desatascarse
        "reversa_fuerza": 0.55,       # cuánto se pisa la marcha atrás (0-1)
        "reversa_extra_si_repite": 2.0,   # si vuelve a atascarse enseguida, más marcha atrás
        # tras chocar GIRANDO (p. ej. un poste al doblar): avanzar casi recto unos metros antes de volver a girar
        "recto_tras_choque_m": 5.0,
        "recto_tras_choque_extra_m": 3.0, # más metros si vuelve a chocar en el mismo sitio
        "recto_tras_choque_volante": 0.15,  # volante máximo hacia el lado del choque mientras tanto
    },
    "teclas": {
        "activar": "INSERT",
        "modo_lento": "PAGEUP",
        "modo_rapido": "F10",         # 2.6.0; fijo desde la 3.4.0
        "saltar_etapa": "PAGEDOWN",
        "salir": "END",
        "capturar": "F11",
        "carril": "DELETE",           # activar/desactivar la ayuda de carril
        "hito": "F9",                 # 2.3.0: marcar un momento para comentarlo en las observaciones
        "grabar": "F5",               # 3.5.0 (no F7: oculta el HUD): empezar / terminar de grabar un recorrido
        "panel": "F6",                # 3.1.0: prende o apaga el panel flotante (la interfaz lo lee)
        "tomar_control": ["S", "SPACE"],
    },
    "experimental": {                 # 2.3.2: funciones en prueba (pestaña Experimental)
        "velocidad_suave_curvas": True,
        "velocidad_sin_vaiven": True,  # 3.2.4: anticipar y no soltar del todo el acelerador por poco
        "trazados_comunes_vuelta": True,
        "rumbo_norte": True,          # 2.4.0: rumbo exacto con la N del minimapa (se guarda en el viaje)
        "yolo": True,                 # 3.6.0: YOLO en modo sombra (si está instalado)
        "yolo_frena": True,           # 3.7.0: YOLO frena a fondo y hace esperar de verdad (lo demás, en sombra)
        "usar_grabaciones": True,     # 2.4.1: apagar para hacer entradas/salidas a mano sin borrar nada
        "lado_suave_autopista": True  # 2.5.2: corrección de lado promediada a 70 km/h o más
    },
    "modo_rapido": {                  # 2.6.0 (fijo desde la 3.4.0): más velocidad y curvas más fluidas
        "factor_curvas": 1.15,        # curvas normales y cerradas (tabla por tasa de giro y por grados)
        "extra_esquina_kmh": 5,       # esquinas sin regla (las de las reglas no cambian)
        "velocidad": {                # valores que reemplaza mientras está activo
            "objetivo_recta": 90,
            "objetivo_recta_larga": 110,
            "recta_larga_giro_max": 14,
            "recta_larga_rumbo_max": 10,
            "recta_larga_desvio_max": 6,
            "recta_larga_seg": 1.0,
            "objetivo_por_giro_total": [[20, 90], [35, 78], [55, 64], [80, 50]],
            "objetivo_bifurcacion": 65,
            "objetivo_bifurcacion_autopista": 80,
            "margen_sin_frenar_kmh": 18,
            "objetivo_ignorar_fotogramas": 4,
            "memoria_curva_seg": 0.8,
            "subida_objetivo_kmh_seg": 12,
            "freno_max": 0.55,        # a más velocidad hace falta frenar más fuerte cuando sí hay que frenar
            "freno_espera_seg": 0.5
        }
    },
    "yolo": {                         # 3.6.0: detección de vehículos (modo sombra), ver vision_yolo.py
        "activo": True,
        "modelo": "yolo11n.pt",
        "hz": 10,
        "confianza": 0.35,
        "fov_horizontal_grados": 60,  # primera persona: escala de la distancia (el tiempo hasta chocar no depende)
        "mascara": []                 # rectángulos de la cabina a tapar (Calibración → Máscara de cabina)
    },
    "modo_lento": {                   # 3.5.0: el modo rápido al revés (tecla RE PÁG o reglas con "modo": "lento")
        "factor_curvas": 0.85,        # curvas normales, cerradas y largas
        "extra_esquina_kmh": -3,      # esquinas sin regla (las de las reglas no cambian)
        "velocidad": {
            "objetivo_recta": 60,
            "objetivo_recta_larga": 70,
            "objetivo_bifurcacion": 45,
            "objetivo_bifurcacion_autopista": 55
        }
    },
    "lado_suave": {                   # 2.5.2
        "kmh_desde": 70,
        "segundos": 0.5,
        "rumbo_max": 10,              # solo en recta: ruta junto al camión casi derecha...
        "giro_max": 25                # ...y sin curva fuerte por delante
    },
    "rumbo": {                        # 2.4.0: detección de la N
        "margen_px": 14,              # cuánto se mira por fuera del minimapa
        "umbral_n": 0.6,              # parecido mínimo con la plantilla de la N
        "peso_n": 0.35,               # cuánto corrige la N al rumbo de cada cuadro
        "esquina_px": 14              # en las esquinas la N es poco precisa
    },
    "salto_ruta": {                   # 2.4.2: saltos falsos de la línea del GPS (error de lectura de un instante)
        "activo": True,
        "kmh_min": 50,                # solo yendo rápido
        "desvio_px": 12,              # la línea se corre de lado más que esto...
        "giro_grados": 35,            # ...y la curva de adelante cambia más que esto, en un cuadro
        "max_seg": 1.5,               # si sigue así más tiempo, se acepta como ruta real
        "vuelta_desvio_px": 8,
        "vuelta_giro_grados": 25,
        "rumbo_real_grados": 8        # si el camión de verdad giró (rumbo exacto), se acepta
    },
    "capturas": {                     # 2.2.0: capturas de pantalla en los incidentes (se borran al cerrar)
        "activo": True,
        "cada_seg": 0.45,             # cada cuánto se guarda una pantalla en memoria
        "ancho": 1280,                # se achica a este ancho
        "calidad": 80                 # calidad JPG
    },
    "trazado": {                      # 2.1.0: trazados grabados (datos/trazados/)
        "cambio_px_seg": 6.0,         # qué tan rápido se corre de lado siguiendo el trazado
        "kmh_margen": 5,              # límite = velocidad a la que pasaste tú + esto...
        "kmh_minimo": 15              # ...pero nunca menos que esto
    },
    "grabacion": {                    # v38: repetición de recorridos grabados (carpeta grabaciones/)
        "volante_max": 0.7,           # tope del volante al repetir una tecla A/D grabada
        "volante_por_seg": 2.5,       # cuánto sube el volante por segundo (como el teclado del juego)
        "volante_vuelta_por_seg": 5.0,
        "acelerador_base": 0.45,      # acelerador con W grabada...
        "acelerador_por_kmh": 0.035,  # ...más esto por cada km/h que falte para la velocidad grabada
        "acelerador_mantener": 0.3,   # sin W grabada pero yendo más lento que tú: un poco de acelerador
        "mantener_kmh": 4,
        "freno": 0.6,
        "desvio_kmh_max": 15,         # se interrumpe si la velocidad difiere más que esto...
        "desvio_seg": 3.0,            # ...durante tantos segundos
        "quieto_seg": 3.0             # ...o si está parado tantos segundos cuando tú te movías
    },
    "etapas_pantalla": {
        "activo": True,               # reconocer menú de carga y barras "Cargando/Descargando" en pantalla
        "cada_seg": 0.4,
        "marcador_frenar_px": 70,     # frenar al acercarse al marcador de destino (círculo rojo)
        "aproximar_marcador": True,   # al final, ir directo al marcador hasta entrar en él
        "aproximar_px": 35,           # ir directo al marcador cuando la ruta se acaba y está a menos de X px
        "llegar_px": 4,               # dentro del marcador: parar y esperar al juego
        "objetivo_aproximar_kmh": 20,  # el juego frena el camión en seco al llegar
        "parado_es_llegada_seg": 2.5, # parado junto al marcador sin que el juego reaccione...
        "llegada_m": 8,
        "retroceso_tras_cargar_seg": 1.8,  # v30: tras cargar, un poco de marcha atrás para girar mejor (0 = no)
        "retroceso_tras_cargar_fuerza": 0.5,
        "retroceso_tras_cargar_volante": 0.5,  # v32: volante al retroceder para enderezar la trompa hacia la ruta
        "accion_inicio_max_m": 600,   # v31: "acción necesaria" solo inicia trabajo si el punto está a menos de X m
        "barra_max_kmh": 12,          # v29: por encima de esta velocidad no se hace caso a menú/barra
        "intentos_llegar": 3,
        "empuje_seg": 2.5,            # parado lejos del punto: primero acelera fuerte X s, luego marcha atrás
        "empuje_acelerador": 0.9,         # ...si no: marcha atrás y otro intento; después pide que lo lleves tú
        "confirmar_etapas": True,     # el tramo solo avanza tras ver el menú de carga o la barra
                                      # (o si la distancia del minimapa salta a un punto nuevo)
    },
    # lectura de textos del HUD: distancia al punto, punto cardinal, zona y calle (para el registro)
    "hud_texto": {
        "activo": True,
        "cada_seg": 1.0,
        "registrar_incidentes": True,   # viajes/incidentes.csv: choques, atascos, maniobras... con el lugar
        "destino_lejos_m": 150,
        "notificaciones": True,         # leer "cargado / descargado / trabajo completado" para fijar la etapa
        "condicion_aviso": 2,           # anotar incidente si la condición del camión baja X puntos o más
        "region_condicion": [6.55, 0.80, 7.2, 1.14],     # "97%" con el ícono del motor (relativo al minimapa)
        "region_notificacion": [-0.1, -1.1, 1.15, -0.02],         # si el punto está a más de X m, no frenar "por destino"
        "region_distancia": [-0.05, 0.62, 0.65, 1.12],   # relativo al minimapa (x0, y0, x1, y1)
        "region_zona": [1.02, 0.55, 3.4, 1.22],
        "filtrar_distancia": True,      # 2.7.2: ignorar/corregir lecturas de distancia imposibles (5540 -> 6640)
        "distancia_max_mps": 45,        # lo más rápido que puede bajar la distancia (m por segundo)
        "distancia_margen_m": 30,
        "salto_lecturas": 5,            # 2.7.3: lecturas seguidas que debe repetirse un salto para creerlo
        "aprender_numeros": True,       # 2.7.2: aprender cómo se ven los números en este PC (mi_equipo/plantillas_hud_usuario.npz)
        "aprender_baja_max_m": 40,      # solo aprende de lecturas que bajan como mucho esto desde la anterior
    },
    "ventana_juego": "Grand Theft Auto",   # v33: título de la ventana del juego (para saber si tiene el foco)
    "usuario": "",                # v33: quién hizo el viaje (se guarda al final de cada archivo de viaje)
    "fps": 30,
}

CALIBRACION = ("minimapa", "jugador", "color_ruta_hsv", "vision", "ventana_juego", "calibracion")


def _fusionar(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = v
    return out


def cargar(ruta=None, guardar_migracion=True):
    ruta = ruta or _config_defecto()
    cfg = _cargar(ruta, guardar_migracion)
    cfg["_ruta"] = ruta
    return cfg


def _config_defecto():
    try:
        import carpetas
        return carpetas.CONFIG
    except Exception:  # noqa
        return "config.json"


def _cargar(ruta="config.json", guardar_migracion=True):
    if not os.path.exists(ruta):
        cfg = copy.deepcopy(DEFAULTS)
        guardar(cfg, ruta)
        print(f"[i] Creado {ruta} con valores por defecto. Ejecuta calibrar.py.")
        return cfg
    with open(ruta, encoding="utf-8") as f:
        usuario = json.load(f)
    if usuario.get("version", 1) < VERSION:
        ver = usuario.get("version", 1)
        _resp = os.path.join(os.path.dirname(os.path.abspath(ruta)), "respaldos")
        os.makedirs(_resp, exist_ok=True)
        shutil.copy(ruta, os.path.join(_resp, f"config_v{ver}_respaldo.json"))
        conservar = {k: usuario[k] for k in CALIBRACION if k in usuario}
        if "velocimetro" in usuario:
            conservar["velocimetro"] = {k: usuario["velocimetro"][k]
                                        for k in ("activo", "region", "color_hsv") if k in usuario["velocimetro"]}
        if ver >= 20:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            if ver == 20:
                at_u = dict(usuario.get("atasco", {}))
                for k in ("reversa_seg", "reversa_extra_si_repite"):
                    at_u.pop(k, None)
                conservar["atasco"] = at_u
            # v22: ir un poco a la izquierda de la línea y crucero hasta 100 km/h (v23: 1,3 m)
            ct_u = dict(usuario.get("control", {}))
            if ver <= 21 or ct_u.get("desplazamiento_carril_px") == -2.0:
                ct_u.pop("desplazamiento_carril_px", None)
            conservar["control"] = ct_u
            ve_u = dict(usuario.get("velocidad", {}))
            ve_u.pop("acelerador_crucero_por_velocidad", None)
            conservar["velocidad"] = ve_u
            # v24: curvas más rápidas y pareja, llegada al punto sin frenar. Solo se cambian los
            # valores que el usuario no había tocado (siguen con el valor por defecto anterior).
            viejos = {("velocidad", "objetivo_curva"): 58, ("velocidad", "objetivo_curva_cerrada"): 38,
                      ("velocidad", "objetivo_por_tasa_giro"): [[10, 80], [18, 72], [28, 58], [40, 46], [60, 33]],
                      ("esquinas", "objetivo_esquina_kmh"): 18, ("esquinas", "objetivo_esquina_muy_cerrada_kmh"): 12,
                      ("velocidad", "objetivo_cerca_destino"): 20, ("etapas_pantalla", "objetivo_aproximar_kmh"): 10,
                      ("velocidad", "subida_acelerador_por_seg"): 2.0, ("velocidad", "amortiguacion_seg"): 0.25}
            if ver <= 31 and not usuario.get("ventana_juego"):
                conservar["ventana_juego"] = DEFAULTS["ventana_juego"]   # v33: detectar si el juego tiene el foco
            if ver == 29:
                # v31: desplazamiento general 0 y retroceso tras cargar más largo (si no los habías cambiado)
                viejos.update({("control", "desplazamiento_carril_px"): -2.2,
                               ("etapas_pantalla", "retroceso_tras_cargar_seg"): 0.9})
            if ver <= 28:
                # v30: más a la izquierda y curvas largas más rápidas (solo si no los habías cambiado)
                viejos.update({("control", "desplazamiento_carril_px"): -1.7,
                               ("velocidad", "objetivo_por_giro_total"): [[15, 80], [25, 65], [45, 50], [70, 40]],
                               ("velocidad", "giro_total_extra_por_px"): 0.2})
            for (sec, k), viejo in viejos.items():
                d = dict(conservar.get(sec, usuario.get(sec, {})))
                if d.get(k) == viejo:
                    d.pop(k, None)
                conservar[sec] = d
        elif ver >= 19:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            def quitar(sec, claves):
                d = dict(usuario.get(sec, {}))
                for k in claves:
                    d.pop(k, None)
                conservar[sec] = d
            quitar("velocidad", ("objetivo_curva", "objetivo_curva_cerrada", "objetivo_por_tasa_giro"))
            quitar("esquinas", ("objetivo_esquina_kmh", "objetivo_esquina_muy_cerrada_kmh",
                                "giro_tardio_px", "giro_tardio_ganancia"))
            quitar("atasco", ("reversa_seg",))
        elif ver >= 18:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            vel_u = dict(usuario.get("velocidad", {}))
            for k in ("objetivo_curva", "objetivo_curva_cerrada", "objetivo_por_tasa_giro"):
                vel_u.pop(k, None)                          # v20: curvas más rápidas
            conservar["velocidad"] = vel_u
            es_u = dict(usuario.get("esquinas", {}))
            for k in ("objetivo_esquina_kmh", "objetivo_esquina_muy_cerrada_kmh"):
                es_u.pop(k, None)
            conservar["esquinas"] = es_u
            at_u = dict(usuario.get("atasco", {}))
            at_u.pop("segundos", None)
            conservar["atasco"] = at_u
        elif ver >= 17:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            conservar["esquinas"] = dict(usuario.get("esquinas", {}), abrir_antes_px=0.0)   # v19: ir por el centro
        elif ver >= 16:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            conservar["calle"] = dict(usuario.get("calle", {}), activo=True)    # v18: calles reactivadas
            ctrl = dict(usuario.get("control", {}))
            ctrl.pop("persecucion_desvio_grados_px", None)
            conservar["control"] = ctrl
        elif ver >= 15:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            conservar["calle"] = dict(usuario.get("calle", {}), activo=False)
        elif ver >= 14:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            car = dict(usuario.get("carril", {}))
            for k in ("peso_grados", "tope_grados"):      # v16: corrección de carril más suave (zigzag)
                car.pop(k, None)
            conservar["carril"] = car
        elif ver >= 13:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
        elif ver >= 12:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
        elif ver >= 11:
            conservar = {k: v for k, v in usuario.items() if k not in ("version",)}
            vel_u = dict(usuario.get("velocidad", {}))
            for k in ("acelerador_arranque", "segundos_parado_para_arranque"):
                vel_u.pop(k, None)
            conservar["velocidad"] = vel_u
        elif ver >= 10:
            # v11: esquinas y detección de calles nueva; se conserva todo lo demás
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "calle", "version")}
            vel_u = usuario.get("velocidad", {})
            conservar["velocidad"] = {k: vel_u[k] for k in vel_u if k.startswith("objetivo_")}
        elif ver >= 9:
            # v10: calles grises, curvas por cerrazón; se conserva todo lo demás
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "version")}
            vel_u = usuario.get("velocidad", {})
            conservar["velocidad"] = {k: vel_u[k] for k in vel_u if k.startswith("objetivo_")}
        elif ver >= 8:
            # v9: nuevos parámetros de visión/velocidad; se conserva todo lo demás
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "version")}
            vel_u = usuario.get("velocidad", {})
            conservar["velocidad"] = {k: vel_u[k] for k in vel_u if k.startswith("objetivo_")}
        elif ver >= 7:
            # v8: volante más fuerte y nuevos parámetros de atasco/velocidad
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "atasco", "version")}
            ctrl = dict(usuario.get("control", {}))
            for k in ("kp", "kd", "ganancia_por_velocidad"):
                ctrl.pop(k, None)
            conservar["control"] = ctrl
            vel_u = usuario.get("velocidad", {})
            conservar["velocidad"] = {k: vel_u[k] for k in vel_u if k.startswith("objetivo_")}
            m = usuario.get("minimapa", DEFAULTS["minimapa"])
            conservar.setdefault("vision", {})["radio_anticipacion"] = round(min(m["w"], m["h"]) * 0.7, 1)
        elif ver >= 6:
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "version")}
        elif ver >= 5:
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "version")}
        elif ver >= 4:
            conservar = {k: v for k, v in usuario.items() if k not in ("velocidad", "version")}
            m = usuario.get("minimapa", DEFAULTS["minimapa"])
            base = min(m["w"], m["h"])
            conservar.setdefault("vision", {})
            conservar["vision"]["radio_inicio"] = round(base * 0.072, 1)
            conservar["vision"]["radio_ajuste"] = round(base * 0.17, 1)
        elif ver >= 3:
            ctrl = {k: v for k, v in usuario.get("control", {}).items()}
            conservar["control"] = ctrl            # la dirección v3 ya estaba afinada
            vis = usuario.get("vision", {})
            conservar.setdefault("vision", {}).update(vis)
        if ver >= 2:
            for k in ("teclas",):
                if k in usuario:
                    conservar[k] = usuario[k]
            if "backend" in usuario.get("control", {}) and "control" not in conservar:
                conservar["control"] = {"backend": usuario["control"]["backend"]}
        if ver < 34:
            # 3.0.0: flecha del jugador y radios de visión pasan a la unidad fija del minimapa (272 x 180)
            try:
                import geometria
                if geometria.convertir_unidades(conservar):
                    print("[i] Calibración: la flecha del jugador y los radios pasan a la unidad fija del minimapa.")
            except Exception as e:  # noqa
                print(f"[!] No se pudieron convertir las unidades de la calibración: {e}")
        cfg = _fusionar(DEFAULTS, conservar)
        cfg["version"] = VERSION
        if guardar_migracion:
            guardar(cfg, ruta)
            print(f"[i] config.json actualizado a la versión {VERSION} (se mantuvo tu calibración, "
                  f"teclas y backend; copia anterior en mi_equipo/respaldos/config_v{ver}_respaldo.json).")
        return cfg
    cfg = _fusionar(DEFAULTS, usuario)
    if cfg.get("esquinas", {}).get("frente_flecha_px") == 4.5:      # 3.2.2: el valor de la 3.2.1 pasa a 7
        cfg["esquinas"]["frente_flecha_px"] = 7.0
    return cfg


def guardar(cfg, ruta=None):
    ruta = ruta or _config_defecto()
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    m = cfg.get("minimapa")
    if isinstance(m, dict) and "w_real" in m:      # 3.0.0: en el disco va el tamaño real del minimapa
        cfg["minimapa"] = {"x": m["x"], "y": m["y"], "w": m["w_real"], "h": m["h_real"]}
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def interpolar(x, tabla):
    """tabla = [[x0, y0], [x1, y1], ...] ordenada por x."""
    if x <= tabla[0][0]:
        return tabla[0][1]
    for (x0, y0), (x1, y1) in zip(tabla, tabla[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tabla[-1][1]

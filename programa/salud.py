"""
Avisos de problemas de base (3.1.0).

Vigila, mientras el programa corre, las cosas que hacen que el autopiloto «ande raro» sin decir por qué
(sobre todo en el PC de otro jugador) y las devuelve como una lista corta para mostrar en la ventana:

  mando       el mando virtual no funciona y está manejando con el teclado
  distancia   el HUD no se lee: la distancia al punto no cambia aunque el camión va rápido
  millas      la distancia no coincide con la velocidad (el juego está en millas, o la lectura es mala)
  recorrido   en la ida, el recorrido no se reconoció: no hay reglas
  etapa       el camión ya está cargado pero el programa sigue en «ir a cargar» (se activó a mitad de camino)

No lee nada de la pantalla: solo mira lo que el autopiloto ya midió. `actualizar` se llama unas 4 veces
por segundo y devuelve (activos, nuevos); `nuevos` son los avisos que aparecen por primera vez.
"""

VENTANA_S = 15.0          # ventana para comparar distancia recorrida con velocidad
MIN_ESPERADO_M = 150.0    # una ventana solo cuenta si el camión debió recorrer al menos esto
SEGUIDAS = 2              # ventanas seguidas con el mismo problema para avisar
RATIO_BAJO, RATIO_ALTO = 0.45, 2.2


class Salud:
    def __init__(self, backend="teclado", nombre_control="teclado"):
        self.backend = backend
        self.nombre_control = nombre_control
        self.activos = {}                 # clave -> dict(nivel, titulo, texto)
        self._visto = set()               # claves ya avisadas (no repetir la notificación)
        self._w = None                    # ventana de comparación
        self._ult_t = None
        self._mal = 0                     # ventanas seguidas con la distancia que no cuadra con la velocidad
        self._quieta = 0                  # ventanas seguidas con la distancia sin cambiar
        self._t_cargado = None            # cuándo se vio «cargado pero en etapa 0»
        self._t_tramo1 = None             # cuándo empezó la ida
        self._m_inicio = None

    # ------------------------------------------------------------ interno
    def _poner(self, clave, nivel, titulo, texto):
        self.activos[clave] = {"clave": clave, "nivel": nivel, "titulo": titulo, "texto": texto}

    def _quitar(self, clave):
        self.activos.pop(clave, None)

    def reiniciar(self):
        """Al volver a iniciar el programa."""
        self.__init__(self.backend, self.nombre_control)

    # ------------------------------------------------------------ llamada periódica
    def actualizar(self, ahora, estado, tramo, metros, kmh, vel_ok, recorrido):
        """Devuelve (lista de avisos activos, lista de avisos nuevos)."""
        antes = set(self.activos)

        # --- mando virtual: pidió mando y se creó teclado
        if self.backend == "mando" and self.nombre_control != "mando":
            self._poner("mando", "problema", "El mando virtual no funciona",
                        "Está manejando con el teclado, que es mucho peor (el camión se congela al girar). "
                        "Reinicia el PC si instalaste ViGEmBus hace poco; si sigue igual, Ajustes → Comprobar "
                        "instalación.")
        else:
            self._quitar("mando")

        manejando = estado in ("CONDUCIENDO", "ARRANCANDO", "RECUPERANDO")

        # --- distancia vs velocidad
        self._distancia(ahora, manejando, metros, kmh, vel_ok)

        # --- etapa: ya cargado pero en la etapa 0
        if tramo == 0 and metros is not None and metros > 1500 and estado not in ("TERMINADO", "DETENIDO"):
            if self._t_cargado is None:
                self._t_cargado = ahora
            if ahora - self._t_cargado > 6:
                self._poner("etapa", "aviso", "Parece que ya cargaste y el programa sigue en «ir a cargar»",
                            f"Faltan {metros / 1000:.1f} km, mucho para el punto de carga. Pasa a la ida con "
                            "«Saltar etapa» (AV PÁG) para que reconozca el recorrido y use sus reglas. Para la "
                            "próxima vez, activa el programa antes de cargar.")
        else:
            self._t_cargado = None
            self._quitar("etapa")

        # --- recorrido sin reconocer en la ida
        if tramo == 1 and manejando:
            if self._t_tramo1 is None:
                self._t_tramo1 = ahora
                self._m_inicio = metros
            sin = (not recorrido) or ("desconocido" in str(recorrido).lower())
            if sin and ahora - self._t_tramo1 > 14:
                ini = f" (empezó a {self._m_inicio / 1000:.2f} km)".replace(".", ",") if self._m_inicio else ""
                self._poner("recorrido", "aviso", "No reconozco el recorrido: no hay reglas en la ida",
                            "Va solo con el GPS y la visión" + ini + ". Es normal si activaste a mitad de camino "
                            "o si es un recorrido nuevo: elígelo en «Recorrido» (junto a «Empezar en») o activa antes de cargar.")
            elif not sin:
                self._quitar("recorrido")
        else:
            if tramo != 1:
                self._t_tramo1 = None
                self._quitar("recorrido")

        nuevos = [self.activos[c] for c in self.activos if c not in antes and c not in self._visto]
        for c in self.activos:
            self._visto.add(c)
        return list(self.activos.values()), nuevos

    def _distancia(self, ahora, manejando, metros, kmh, vel_ok):
        """Compara lo que el camión debió recorrer (velocidad × tiempo) con lo que bajó la distancia."""
        t_ant, self._ult_t = self._ult_t, ahora
        if not manejando or metros is None or not vel_ok or t_ant is None or ahora - t_ant > 1.5:
            self._w = None
            return
        w = self._w
        if w is None:
            self._w = {"t0": ahora, "d0": float(metros), "esp": 0.0}
            return
        w["esp"] += max(0.0, kmh) / 3.6 * (ahora - t_ant)
        if ahora - w["t0"] < VENTANA_S:
            return
        esp, obs = w["esp"], w["d0"] - float(metros)
        self._w = {"t0": ahora, "d0": float(metros), "esp": 0.0}
        if esp < MIN_ESPERADO_M:
            return
        if obs < -50 or abs(obs) > 1500:
            return                                       # la ruta cambió (punto nuevo, GPS recalculando): no cuenta
        ratio = obs / esp
        if abs(obs) < 0.1 * esp:
            self._quieta += 1
            self._mal = 0
        elif ratio < RATIO_BAJO or ratio > RATIO_ALTO:
            self._mal += 1
            self._quieta = 0
        else:
            self._quieta = self._mal = 0
        if self._quieta >= SEGUIDAS and float(metros) < 30:
            # «0.9m»: la distancia en millas («0.9mi») leída como metros
            self._poner("millas", "problema", "El juego está en millas: la distancia no se lee bien",
                        "El HUD muestra la distancia en millas y el programa la lee como metros. Pon el sistema "
                        "métrico en el juego (Configuración → Pantalla → Sistema de medida) y vuelve a iniciar.")
            self._quitar("distancia")
        elif self._quieta >= SEGUIDAS:
            self._poner("distancia", "problema", "No se lee la distancia del HUD",
                        "La distancia al punto no cambia aunque el camión va rápido. Sin ella no hay reglas ni "
                        "reconocimiento del recorrido. Revisa Calibración → Calibrar todo y que el minimapa del "
                        "juego muestre la distancia («↑ 925m»).")
            self._quitar("millas")
        elif self._mal >= SEGUIDAS:
            self._poner("millas", "problema", "La distancia no coincide con la velocidad",
                        "Casi seguro el juego está en millas: pon el sistema métrico (Configuración → Pantalla → "
                        "Sistema de medida). Si ya está en métrico, la lectura del HUD es mala: recalibra.")
            self._quitar("distancia")
        elif self._quieta == 0 and self._mal == 0:
            self._quitar("distancia")
            self._quitar("millas")

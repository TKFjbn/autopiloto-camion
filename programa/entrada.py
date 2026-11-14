"""
Entrada al juego (teclado por scancodes / mando virtual) y lectura de teclas globales.

- Teclado: usa SendInput con *scancodes* (DirectInput), que es lo que GTA V lee.
  pyautogui/pynput normales suelen NO funcionar dentro del juego.
- Mando: usa 'vgamepad' (requiere el driver ViGEmBus). Da dirección y acelerador
  ANALÓGICOS, que es muchísimo más suave para un camión que el teclado on/off.

Nada de esto toca archivos del juego ni del launcher: solo simula pulsaciones,
igual que si las hicieras tú.
"""
import sys
import time
import threading

ES_WINDOWS = sys.platform.startswith("win")

# ---------------------------------------------------------------- Win32 / ctypes
if ES_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _INPUTunion(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

    def _enviar_scan(scan, soltar):
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if soltar else 0)
        inp = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, flags, 0, 0))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def tecla_pulsada(vk):
        """True si la tecla virtual vk está físicamente abajo (lectura global)."""
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def titulo_ventana_activa():
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
else:  # Permite probar la visión en Linux/Mac con --simular
    def _enviar_scan(scan, soltar):
        pass

    def tecla_pulsada(vk):
        return False

    def titulo_ventana_activa():
        return ""

# Scancodes (teclado US/ES, posición física)
SCAN = {"W": 0x11, "A": 0x1E, "S": 0x1F, "D": 0x20, "SPACE": 0x39,
        "Y": 0x15, "E": 0x12, "ENTER": 0x1C}

# Códigos de tecla virtual para leer hotkeys (nombres válidos en config.json)
VK = {f"F{i}": 0x6F + i for i in range(1, 13)}                 # F1..F12
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})  # A..Z
VK.update({str(i): 0x30 + i for i in range(10)})               # 0..9
VK.update({f"NUMPAD{i}": 0x60 + i for i in range(10)})         # NUMPAD0..9
VK.update({
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "BACKSPACE": 0x08,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "UP": 0x26, "DOWN": 0x28,
    "LEFT": 0x25, "RIGHT": 0x27, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
    "NUMPAD_MAS": 0x6B, "NUMPAD_MENOS": 0x6D, "NUMPAD_POR": 0x6A,
    "NUMPAD_DIV": 0x6F, "LSHIFT": 0xA0, "RSHIFT": 0xA1,
    "LCTRL": 0xA2, "RCTRL": 0xA3, "LALT": 0xA4, "RALT": 0xA5,
})
# Nombres alternativos en español
VK.update({"ESPACIO": VK["SPACE"], "INSERTAR": VK["INSERT"], "SUPR": VK["DELETE"],
           "INICIO": VK["HOME"], "FIN": VK["END"], "REPAG": VK["PAGEUP"],
           "AVPAG": VK["PAGEDOWN"], "PAUSA": VK["PAUSE"]})


def validar_tecla(nombre, campo):
    n = str(nombre).upper().strip()
    if n not in VK:
        raise SystemExit(
            f"\n[config.json] La tecla '{nombre}' de \"{campo}\" no existe.\n"
            f"Nombres válidos: F1-F12, A-Z, 0-9, NUMPAD0-NUMPAD9, "
            + ", ".join(k for k in VK if len(k) > 3 and not k.startswith(("NUMPAD", "F"))) + "\n")
    return n


def pulsar_tecla(nombre, duracion=0.08):
    """Pulsación corta (p. ej. 'Y' para iniciar el trabajo)."""
    _enviar_scan(SCAN[nombre], False)
    time.sleep(duracion)
    _enviar_scan(SCAN[nombre], True)


class Hotkeys:
    """Detecta flancos de pulsación (se pulsó una vez) sin bloquear."""

    def __init__(self, nombres):
        self.nombres = nombres
        self.antes = {n: False for n in nombres}

    def leer(self):
        pulsadas = []
        for n in self.nombres:
            ahora = tecla_pulsada(VK[n])
            if ahora and not self.antes[n]:
                pulsadas.append(n)
            self.antes[n] = ahora
        return pulsadas


# ---------------------------------------------------------------- Backends
class ControlTeclado:
    """
    Convierte valores analógicos (dirección -1..1, acelerador 0..1, freno 0..1)
    en pulsaciones PWM: dentro de cada periodo la tecla se mantiene apretada
    una fracción del tiempo. Corre en su propio hilo.
    """
    nombre = "teclado"

    def __init__(self, periodo=0.10, minimo_on=0.025):
        self.periodo = periodo
        self.minimo_on = minimo_on
        self._valores = {"A": 0.0, "D": 0.0, "W": 0.0, "S": 0.0}
        self._abajo = set()
        self._lock = threading.Lock()
        self._vivo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def teclas_propias(self):
        with self._lock:
            return set(self._abajo)

    def set(self, direccion, acelerador, freno=0.0):
        direccion = max(-1.0, min(1.0, direccion))
        with self._lock:
            self._valores["A"] = -direccion if direccion < 0 else 0.0
            self._valores["D"] = direccion if direccion > 0 else 0.0
            self._valores["W"] = max(0.0, min(1.0, acelerador))
            self._valores["S"] = max(0.0, min(1.0, freno))

    def _press(self, k):
        if k not in self._abajo:
            _enviar_scan(SCAN[k], False)
            self._abajo.add(k)

    def _release(self, k):
        if k in self._abajo:
            _enviar_scan(SCAN[k], True)
            self._abajo.discard(k)

    def _bucle(self):
        while self._vivo:
            t0 = time.perf_counter()
            with self._lock:
                duty = dict(self._valores)
            fin = {}
            for k, d in duty.items():
                on = d * self.periodo
                if d >= 0.95:
                    self._press(k); fin[k] = None          # mantener
                elif on < self.minimo_on:
                    self._release(k)
                else:
                    self._press(k); fin[k] = t0 + on
            while True:
                ahora = time.perf_counter()
                for k, t in list(fin.items()):
                    if t is not None and ahora >= t:
                        self._release(k); del fin[k]
                if ahora - t0 >= self.periodo:
                    break
                time.sleep(0.003)

    def soltar_todo(self):
        self.set(0, 0, 0)
        with self._lock:
            for k in list(self._abajo):
                self._release(k)

    def cerrar(self):
        self._vivo = False
        self._hilo.join(timeout=1)
        for k in list(self._abajo):
            self._release(k)


class ControlMando:
    """Mando Xbox 360 virtual (pip install vgamepad + driver ViGEmBus)."""
    nombre = "mando"

    def __init__(self, zona_muerta=0.0):
        import vgamepad as vg  # se importa aquí para que sea opcional
        self.pad = vg.VX360Gamepad()
        self.zona_muerta = zona_muerta     # GTA ignora los movimientos pequeños del stick: se compensan

    def teclas_propias(self):
        return set()

    def set(self, direccion, acelerador, freno=0.0):
        d = max(-1.0, min(1.0, direccion))
        zm = self.zona_muerta
        if zm > 0 and abs(d) > 0.01:
            d = (1 if d > 0 else -1) * (zm + (1 - zm) * abs(d))
        elif abs(d) <= 0.01:
            d = 0.0
        self.pad.left_joystick_float(x_value_float=d, y_value_float=0.0)
        self.pad.right_trigger_float(value_float=max(0.0, min(1.0, acelerador)))
        self.pad.left_trigger_float(value_float=max(0.0, min(1.0, freno)))
        self.pad.update()

    def soltar_todo(self):
        self.set(0, 0, 0)

    def cerrar(self):
        self.soltar_todo()


def crear_control(backend, periodo_pwm=0.10, zona_muerta=0.0):
    if backend == "mando":
        try:
            return ControlMando(zona_muerta)
        except Exception as e:  # noqa
            print(f"[!] No se pudo crear el mando virtual ({e}). Uso teclado.")
    return ControlTeclado(periodo=periodo_pwm)

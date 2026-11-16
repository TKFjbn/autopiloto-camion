"""
Ventanas de la 2.2.0 que salen desde Ajustes y Calibración:
  - cambiar teclas
  - comprobar instalación
  - tutorial para usuarios nuevos
  - copiar el prompt de calibración para otro asistente de IA (+ archivos listos para adjuntar)
"""
import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import carpetas
import configuracion
import diagnostico
import entrada

# ---------------------------------------------------------------- teclas
# keysym de Tk -> nombre de tecla del programa (los de entrada.VK)
_TK_A_VK = {
    "Insert": "INSERT", "Delete": "DELETE", "Home": "HOME", "End": "END", "Prior": "PAGEUP", "Next": "PAGEDOWN",
    "Up": "UP", "Down": "DOWN", "Left": "LEFT", "Right": "RIGHT", "Pause": "PAUSE", "Scroll_Lock": "SCROLLLOCK",
    "space": "SPACE", "Return": "ENTER", "Tab": "TAB", "BackSpace": "BACKSPACE",
    "KP_Add": "NUMPAD_MAS", "KP_Subtract": "NUMPAD_MENOS", "KP_Multiply": "NUMPAD_POR", "KP_Divide": "NUMPAD_DIV",
    "Shift_L": "LSHIFT", "Shift_R": "RSHIFT", "Control_L": "LCTRL", "Control_R": "RCTRL",
    "Alt_L": "LALT", "Alt_R": "RALT",
    "KP_Insert": "NUMPAD0", "KP_End": "NUMPAD1", "KP_Down": "NUMPAD2", "KP_Next": "NUMPAD3", "KP_Left": "NUMPAD4",
    "KP_Begin": "NUMPAD5", "KP_Right": "NUMPAD6", "KP_Home": "NUMPAD7", "KP_Up": "NUMPAD8", "KP_Prior": "NUMPAD9",
}
_TK_A_VK.update({f"KP_{i}": f"NUMPAD{i}" for i in range(10)})

CAMPOS_TECLAS = (
    ("activar", "Activar / desactivar el autopiloto", "También termina una grabación."),
    ("saltar_etapa", "Saltar a la siguiente etapa", "Si el programa se desfasó de la etapa del trabajo."),
    ("salir", "Detener el programa", "Cierra el autopiloto (no la ventana)."),
    ("capturar", "Captura para calibrar", "Toma la captura de pantalla durante la calibración."),
    ("carril", "Ayuda de carril", "Activa o desactiva la ayuda de carril con la cámara."),
    ("panel", "Panel flotante", "Prende o apaga el panel flotante (la tira chica arriba al centro del juego)."),
    ("hito", "Marcar hito", "Marca un momento del viaje (con 3 capturas) para explicarlo en las observaciones."),
    ("grabar", "Grabar recorrido", "Empieza a grabar lo que haces (conduce tú); vuelve a pulsarla para terminar y ponerle nombre."),   # 3.5.0
    ("tomar_control:0", "Tomar el control (1)", "Al pulsarla en el juego, el autopiloto se desactiva y manejas tú."),
    ("tomar_control:1", "Tomar el control (2)", "Segunda tecla para tomar el control (opcional)."),
    ("---", "Modos de velocidad", ""),                     # 3.4.0: ya no son experimentales
    ("modo_lento", "Modo lento", "Menos velocidad en todo (rectas 60, curvas y esquinas más lentas). Las reglas mandan igual."),
    ("modo_rapido", "Modo rápido", "Más velocidad y curvas más fluidas (puede chocar más). Las reglas mandan igual."),
)
# teclas que usa el juego (no conviene que activen funciones del programa)
TECLAS_JUEGO = {"W", "A", "S", "D", "SPACE", "E", "Y", "ENTER", "F", "H", "G"}
EVITAR = {"F7": "oculta el HUD y con él el minimapa", "F8": "es la captura del juego",
          "HOME": "abre el overlay de Social Club", "TAB": "abre la rueda de armas en GTA",
          "LALT": "se usa con ALT+TAB"}


def nombre_tecla(evento):
    k = evento.keysym
    if k in _TK_A_VK:
        return _TK_A_VK[k]
    if len(k) == 1 and k.isalnum():
        return k.upper()
    if k.upper() in entrada.VK:
        return k.upper()
    return None


def _leer_teclas():
    """Teclas actuales de mi_equipo/config.json (o las de fábrica si aún no existe)."""
    t = dict(configuracion.DEFAULTS["teclas"])
    if os.path.exists(carpetas.CONFIG):
        guardadas = (carpetas.leer_json(carpetas.CONFIG, {}) or {}).get("teclas") or {}
        t.update(guardadas)
    t["tomar_control"] = list(t.get("tomar_control") or [])
    backend = ((carpetas.leer_json(carpetas.CONFIG, {}) or {}).get("control") or {}).get("backend", "teclado") \
        if os.path.exists(carpetas.CONFIG) else configuracion.DEFAULTS["control"].get("backend", "teclado")
    return t, backend


def _guardar_teclas(teclas, backend):
    if os.path.exists(carpetas.CONFIG):
        crudo = carpetas.leer_json(carpetas.CONFIG, {})
        if not crudo:
            raise ValueError("mi_equipo/config.json no se puede leer (formato roto)")
        crudo["teclas"] = teclas
        crudo.setdefault("control", {})["backend"] = backend
        carpetas.guardar_json(carpetas.CONFIG, crudo)
    else:
        cfg = configuracion.cargar(carpetas.CONFIG, guardar_migracion=False)
        cfg["teclas"] = teclas
        cfg["control"]["backend"] = backend
        os.makedirs(carpetas.EQUIPO, exist_ok=True)
        configuracion.guardar(cfg, carpetas.CONFIG)


def ventana_teclas(app):
    T = app.T
    teclas, backend = _leer_teclas()
    trabajo = {k: v for k, v in teclas.items() if k != "tomar_control"}
    tc = list(teclas["tomar_control"]) + ["", ""]
    trabajo["tomar_control:0"], trabajo["tomar_control:1"] = tc[0], tc[1]

    win = tk.Toplevel(app.root)
    win.configure(bg=T["bg"])
    win.title("Cambiar teclas")
    win.transient(app.root)
    cab = ttk.Frame(win, padding=10)
    cab.pack(fill="x")
    ttk.Label(cab, text="Teclas del programa", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(cab, text="Pulsa «Cambiar» y después la tecla nueva (ESC cancela). Las teclas con que el camión "
                        "maneja en el juego (W/A/S/D) no se cambian aquí: dependen de los controles del juego.",
              wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))
    cuerpo = ttk.Frame(win, padding=(10, 0, 10, 0))
    cuerpo.pack(fill="both", expand=True)
    etiquetas = {}
    estado = {"esperando": None}
    aviso = tk.Label(win, text="", fg=T["aviso"], bg=T["bg"], wraplength=520, justify="left")

    def texto(clave):
        v = trabajo.get(clave) or ""
        return v if v else "(ninguna)"

    def refrescar():
        for clave, lbl in etiquetas.items():
            lbl.config(text=texto(clave), fg=T["morado"] if estado["esperando"] == clave else T["texto"])

    def empezar(clave):
        estado["esperando"] = clave
        etiquetas[clave].config(text="pulsa una tecla…")
        aviso.config(text="")
        win.focus_force()

    def tecla(evento):
        clave = estado["esperando"]
        if clave is None:
            return
        if evento.keysym == "Escape":
            estado["esperando"] = None
            refrescar()
            return "break"
        n = nombre_tecla(evento)
        if n is None:
            aviso.config(text=f"La tecla «{evento.keysym}» no se puede usar. Prueba con otra.")
            return "break"
        for otra, v in trabajo.items():
            if otra != clave and v == n:
                nombre_otra = next((e for c, e, _a in CAMPOS_TECLAS if c == otra), otra)
                aviso.config(text=f"{n} ya se usa para «{nombre_otra}». Cámbiala primero allí o elige otra.")
                return "break"
        es_tomar = clave.startswith("tomar_control")
        problemas = []
        if n in EVITAR:
            problemas.append(f"{n} {EVITAR[n]}")
        if n in TECLAS_JUEGO and not es_tomar:
            problemas.append(f"{n} es una tecla del juego: cada vez que la uses para manejar también activarías "
                             "esta función")
        if problemas and not messagebox.askyesno("Cambiar teclas", "Ojo: " + "; ".join(problemas) +
                                                 ".\n\n¿Usarla igual?", parent=win):
            estado["esperando"] = None
            refrescar()
            return "break"
        trabajo[clave] = n
        estado["esperando"] = None
        refrescar()
        return "break"

    win.bind("<KeyPress>", tecla)
    for fila, (clave, etiqueta, ayuda) in enumerate(CAMPOS_TECLAS):
        if clave == "---":
            ttk.Separator(cuerpo).grid(row=fila, column=0, columnspan=4, sticky="ew", pady=(8, 0))
            ttk.Label(cuerpo, text=etiqueta, style="Tenue.TLabel").grid(row=fila, column=0, sticky="w",
                                                                         pady=(14, 2))
            continue
        ttk.Label(cuerpo, text=etiqueta + ":").grid(row=fila, column=0, sticky="w", pady=2)
        lbl = tk.Label(cuerpo, text=texto(clave), width=14, anchor="w", bg=T["campo"], fg=T["texto"],
                       relief="flat", padx=6)
        lbl.grid(row=fila, column=1, sticky="w", padx=6, pady=2)
        etiquetas[clave] = lbl
        b = ttk.Button(cuerpo, text="Cambiar", command=lambda c=clave: empezar(c))
        b.grid(row=fila, column=2, padx=2, pady=2)
        app._ayuda(b, ayuda)
        if clave == "tomar_control:1":
            q = ttk.Button(cuerpo, text="Quitar", command=lambda: (trabajo.__setitem__("tomar_control:1", ""),
                                                                   refrescar()))
            q.grid(row=fila, column=3, padx=2, pady=2)
    fila = len(CAMPOS_TECLAS)
    ttk.Separator(cuerpo).grid(row=fila, column=0, columnspan=4, sticky="ew", pady=8)
    ttk.Label(cuerpo, text="Controlar el camión con:").grid(row=fila + 1, column=0, sticky="w")
    var_b = tk.StringVar(value="mando" if backend == "mando" else "teclado")
    for i, (v, t, a) in enumerate((("teclado", "Teclado", "Simula W/A/S/D. Funciona siempre, pero el volante "
                                    "es todo o nada."),
                                   ("mando", "Mando virtual (recomendado)", "Volante y acelerador suaves. Necesita "
                                    "vgamepad y el driver ViGEmBus: revísalo en «Comprobar instalación»."))):
        r = ttk.Radiobutton(cuerpo, text=t, value=v, variable=var_b)
        r.grid(row=fila + 1 + i, column=1, columnspan=3, sticky="w", padx=6)
        app._ayuda(r, a)
    aviso.pack(fill="x", padx=10, pady=(6, 0))

    def restaurar():
        d = configuracion.DEFAULTS["teclas"]
        for k in trabajo:
            if k.startswith("tomar_control:"):
                lista = list(d["tomar_control"]) + ["", ""]
                trabajo[k] = lista[int(k.split(":")[1])]
            else:
                trabajo[k] = d.get(k, trabajo[k])
        aviso.config(text="Teclas de fábrica puestas. Pulsa Guardar para aplicarlas.")
        refrescar()

    def guardar():
        nuevas = {k: v for k, v in trabajo.items() if not k.startswith("tomar_control:")}
        nuevas["tomar_control"] = [v for v in (trabajo["tomar_control:0"], trabajo["tomar_control:1"]) if v]
        if not nuevas["tomar_control"]:
            aviso.config(text="Deja al menos una tecla para tomar el control.")
            return
        try:
            _guardar_teclas(nuevas, var_b.get())
        except Exception as e:  # noqa
            messagebox.showerror("Cambiar teclas", f"No se pudieron guardar:\n{e}", parent=win)
            return
        print("[OK] Teclas guardadas en mi_equipo/config.json.")
        app._cargar_teclas()
        if app._ocupado():
            messagebox.showinfo("Cambiar teclas", "Guardado. Las teclas nuevas valen la próxima vez que inicies "
                                                  "el programa (Detener → Iniciar).", parent=win)
        win.destroy()

    pie = ttk.Frame(win, padding=10)
    pie.pack(fill="x")
    ttk.Button(pie, text="Guardar", style="Grande.TButton", command=guardar).pack(side="right")
    ttk.Button(pie, text="Cancelar", command=win.destroy).pack(side="right", padx=6)
    ttk.Button(pie, text="Restaurar por defecto", command=restaurar).pack(side="left")
    win.focus_force()


# ---------------------------------------------------------------- comprobar instalación
def ventana_diagnostico(app):
    T = app.T
    win = tk.Toplevel(app.root)
    win.configure(bg=T["bg"])
    win.title("Comprobar instalación")
    win.geometry("760x560")
    win.transient(app.root)
    cab = ttk.Frame(win, padding=10)
    cab.pack(fill="x")
    ttk.Label(cab, text="Comprobar instalación", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(cab, text="Revisa las librerías y herramientas que usa el programa. No instala nada: si falta algo, "
                        "te dice qué hacer. Los comandos «pip» se escriben en una consola (cmd) dentro de la carpeta "
                        "programa/.", wraplength=720, justify="left").pack(anchor="w", pady=(4, 0))
    marco = ttk.Frame(win)
    marco.pack(fill="both", expand=True, padx=10)
    lienzo = tk.Canvas(marco, highlightthickness=0, bg=T["bg"])
    barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
    interior = ttk.Frame(lienzo)
    interior.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.create_window((0, 0), window=interior, anchor="nw")
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    resumen = tk.Label(win, text="Comprobando…", bg=T["bg"], fg=T["texto2"], anchor="w")
    resumen.pack(fill="x", padx=10, pady=(6, 0))
    estado = {"res": []}
    color = {"ok": T["ok"], "aviso": T["aviso"], "error": T["error"]}
    icono = {"ok": "✓", "aviso": "!", "error": "✗"}

    def copiar(txt):
        app.root.clipboard_clear()
        app.root.clipboard_append(txt)

    def mostrar(res):
        if not win.winfo_exists():
            return
        for w in interior.winfo_children():
            w.destroy()
        estado["res"] = res
        for r in res:
            fila = ttk.Frame(interior)
            fila.pack(fill="x", pady=3)
            tk.Label(fila, text=icono[r["estado"]], fg=color[r["estado"]], bg=T["bg"], width=2,
                     font=("Segoe UI", 12, "bold")).pack(side="left", anchor="n")
            txt = ttk.Frame(fila)
            txt.pack(side="left", fill="x", expand=True)
            ttk.Label(txt, text=f"{r['nombre']}: {r['detalle']}", wraplength=640, justify="left").pack(anchor="w")
            if r["solucion"] and r["estado"] != "ok":
                sol = ttk.Frame(txt)
                sol.pack(anchor="w", fill="x")
                tk.Label(sol, text="→ " + r["solucion"], fg=color[r["estado"]], bg=T["bg"], wraplength=560,
                         justify="left").pack(side="left", anchor="w")
                if r["solucion"].startswith("pip "):
                    comando = r["solucion"].split("   ")[0]
                    ttk.Button(sol, text="Copiar", command=lambda c=comando: copiar(c)).pack(side="left", padx=6)
        n_err = sum(r["estado"] == "error" for r in res)
        n_av = sum(r["estado"] == "aviso" for r in res)
        if n_err:
            resumen.config(text=f"{n_err} problema(s) que impiden usar el programa y {n_av} aviso(s).",
                           fg=T["error"])
        elif n_av:
            resumen.config(text=f"Todo lo necesario está bien. {n_av} aviso(s) (opcionales o por revisar).",
                           fg=T["aviso"])
        else:
            resumen.config(text="Todo está bien.", fg=T["ok"])

    def comprobar():
        resumen.config(text="Comprobando…", fg=T["texto2"])

        def trabajo():
            try:
                res = diagnostico.comprobar()
            except Exception as e:  # noqa
                res = [diagnostico._r("Comprobación", "error", f"falló: {e}")]
            app.root.after(0, lambda: mostrar(res))
        threading.Thread(target=trabajo, daemon=True).start()

    def probar_mando():
        if app._ocupado():
            messagebox.showinfo("Probar mando", "Detén el programa antes de probar el mando.", parent=win)
            return
        resumen.config(text="Moviendo el volante del mando virtual…", fg=T["texto2"])

        def trabajo():
            ok, msg = diagnostico.probar_mando()
            app.root.after(0, lambda: resumen.config(text=msg, fg=T["ok"] if ok else T["error"]))
        threading.Thread(target=trabajo, daemon=True).start()

    pie = ttk.Frame(win, padding=10)
    pie.pack(fill="x")
    ttk.Button(pie, text="Cerrar", command=win.destroy).pack(side="right")
    ttk.Button(pie, text="Copiar informe",
               command=lambda: copiar(diagnostico.informe(estado["res"]))).pack(side="right", padx=6)
    b = ttk.Button(pie, text="Probar mando (1 s)", command=probar_mando)
    b.pack(side="left")
    app._ayuda(b, "Mueve el volante del mando virtual a la derecha y a la izquierda. Si el juego está abierto "
                  "con el camión, este puede girar un poco.")
    ttk.Button(pie, text="Comprobar de nuevo", command=comprobar).pack(side="left", padx=6)
    comprobar()
    return win


# ---------------------------------------------------------------- tutorial
def _pasos(app):
    t, backend = _leer_teclas()
    tc = " o ".join(t["tomar_control"]) or "S"
    return [
        ("¡Bienvenido!",
         "Este programa maneja el camión en el trabajo de camionero de GTA V RP. Sigue la ruta roja del GPS en el "
         "minimapa, frena en las curvas y espera en las paradas.\n\n"
         "No toca el juego ni su carpeta, ni lee la memoria: solo mira la pantalla y simula el teclado o un mando.\n\n"
         "Primero, ¿cómo te llamas? Tu nombre se anota en cada viaje y en las observaciones.", "nombre"),
        ("1. Comprobar la instalación",
         "Revisa que estén las librerías que necesita el programa (OpenCV, mss, el mando virtual, el OCR de "
         "Windows…). Si falta algo, te dice qué comando escribir.\n\n"
         "Lo que sale en rojo hay que arreglarlo; lo amarillo es opcional o para revisar.\n\n"
         "Siempre puedes volver a comprobarlo en Ajustes → Comprobar instalación.", "diagnostico"),
        ("2. Preparar el juego",
         "• Pon GTA en «Ventana sin bordes» (o en ventana). En pantalla completa exclusiva la captura sale negra y "
         "las notificaciones no se ven.\n"
         "• Dentro del camión, usa la cámara en primera persona y no muevas el ratón: si mueves la cámara, el "
         "minimapa gira.\n"
         "• Si el juego corre como administrador, abre el programa con «Autopiloto (administrador).bat». Si no, "
         "Windows bloquea las teclas simuladas.\n"
         "• Desde la 3.0.0 la calibración sigue a la ventana del juego: puedes moverla o cambiar la resolución "
         "sin recalibrar (si cambia mucho la proporción, recalibra la cámara de carril).", None),
        ("3. Calibrar la pantalla",
         "Una vez, en la pestaña Calibración → «Calibrar todo» (con GTA abierto):\n\n"
         f"1. Entra al juego, súbete al camión con la ruta del GPS visible, EN MOVIMIENTO, y pulsa {t.get('capturar', 'F11')}.\n"
         "2. Vuelve al programa (ALT+TAB) y pulsa «Continuar ▶».\n"
         "3. El programa encuentra solo el minimapa, la flecha, el velocímetro y los textos, y los muestra con "
         "recuadros junto a lo que leyó (distancia, velocidad, condición).\n"
         "4. Si todo calza, pulsa ENTER. Si no: M = marcar el minimapa a mano, F = clic en la flecha, "
         "V = marcar el velocímetro, C = color de la ruta.\n"
         "5. (Opcional) 4 clics en las líneas del carril para la cámara de carril.\n\n"
         "La calibración queda en mi_equipo/ y es solo para tu PC. Se guarda relativa a la ventana del juego.", None),
        ("4. Teclas y control",
         f"• {t.get('activar')}: activa o desactiva el autopiloto.\n"
         f"• {tc}: tomas el control al instante (el autopiloto se desactiva solo).\n"
         f"• {t.get('modo_lento')}: modo lento · {t.get('saltar_etapa')}: siguiente etapa · "
         f"{t.get('salir')}: detener · {t.get('hito', 'F9')}: marcar un hito.\n\n"
         f"Ahora controlas el camión con: {'mando virtual' if backend == 'mando' else 'teclado'}. El mando virtual "
         "es mucho más suave para el camión (necesita vgamepad y el driver ViGEmBus).\n\n"
         "Todo esto se cambia en Ajustes → Cambiar teclas.", "teclas"),
        ("5. Tu primer viaje",
         "1. En la pestaña Conducir pulsa «▶ Iniciar programa».\n"
         "2. En el juego, contrata el trabajo (Y junto al punto). Cuando aparece la ruta, pulsa "
         f"{t.get('activar')}.\n"
         "3. El autopiloto va a cargar, se detiene y espera: tú eliges la mercancía en el menú.\n"
         "4. Al aparecer la nueva ruta arranca solo hacia el punto A, espera la descarga y vuelve a B.\n"
         "5. Si algo se ve peligroso, toma el control y después vuelve a activarlo.\n\n"
         "Si abres el programa a mitad de un trabajo, elige el tramo en «Empezar en».", None),
        ("6. Grabaciones y trazados",
         "Para los lugares difíciles puedes enseñarle al programa:\n\n"
         "• Grabación (repetir teclas): donde no hay GPS útil, como la entrada a una granja. Pulsa «● Grabar "
         "recorrido», maneja tú el tramo, vuelve a pulsar Grabar y elige cuándo repetirla.\n"
         "• Trazado: calles con GPS pero llenas de obstáculos (farolas, postes). Graba igual y elige «Trazado»: el "
         "autopiloto irá por tu mismo lado de la calle.\n\n"
         "Se guardan en datos/ y se pueden pasar a otros jugadores.", None),
        ("7. Al terminar: observaciones",
         "Cuando termina un trabajo o detienes el programa, te pregunta si quieres hacer observaciones. Verás los "
         "puntos críticos (choques, atascos, cuando tomaste el control) con la causa probable y 3 capturas de "
         "pantalla de cada uno. Escribe qué pasó de verdad: así se pueden corregir las reglas. Lo que más sirve: "
         "qué tocó o qué hizo mal, de qué lado, desde dónde empezó y si fue por tráfico.\n\n"
         f"Si durante el viaje ves algo raro (por ejemplo, que va muy lento), pulsa {t.get('hito', 'F9')} para marcar "
         "un hito. Aparece en las observaciones con sus capturas: explica por qué lo marcaste (si lo dejas en blanco, "
         "no se guarda).\n\n"
         "Las capturas se borran al cerrar el programa, salvo las que guardes con «Guardar esta captura».\n\n"
         "Para calibrar con un asistente de IA, usa Calibración → «Copiar prompt + archivos»: pega el prompt y "
         "adjunta solo «para_ia.txt».\n\n"
         "Puedes volver a ver este tutorial en Ajustes → Ver tutorial. ¡Buen viaje!", None),
    ]


def ventana_tutorial(app, al_terminar=None):
    T = app.T
    win = tk.Toplevel(app.root)
    win.configure(bg=T["bg"])
    win.title("Tutorial · Autopiloto de camión")
    win.geometry("700x580")
    win.transient(app.root)
    pasos = _pasos(app)
    pos = {"i": 0}
    arriba = ttk.Frame(win, padding=(14, 12, 14, 0))
    arriba.pack(fill="x")
    lbl_paso = ttk.Label(arriba, text="", style="Tenue.TLabel")
    lbl_paso.pack(anchor="w")
    lbl_tit = ttk.Label(arriba, text="", style="Titulo.TLabel")
    lbl_tit.pack(anchor="w", pady=(2, 0))
    cuerpo = ttk.Frame(win, padding=(14, 8, 14, 0))
    cuerpo.pack(fill="both", expand=True)
    lbl_txt = tk.Label(cuerpo, text="", bg=T["bg"], fg=T["texto"], wraplength=660, justify="left", anchor="nw",
                       font=("Segoe UI", 10))
    lbl_txt.pack(fill="x", anchor="w")
    extra = ttk.Frame(cuerpo)
    extra.pack(fill="x", pady=(12, 0))
    var_nombre = tk.StringVar(value=app.var_usuario.get())

    def guardar_nombre():
        n = var_nombre.get().strip()
        if n and n != app.var_usuario.get().strip():
            app.var_usuario.set(n)
            app._guardar_usuario()

    def mostrar():
        i = pos["i"]
        tit, txt, widget = pasos[i]
        lbl_paso.config(text=f"Paso {i + 1} de {len(pasos)}")
        lbl_tit.config(text=tit)
        lbl_txt.config(text=txt)
        for w in extra.winfo_children():
            w.destroy()
        if widget == "nombre":
            ttk.Label(extra, text="Tu nombre:").pack(side="left")
            e = ttk.Entry(extra, textvariable=var_nombre, width=30)
            e.pack(side="left", padx=6)
            e.focus_set()
        elif widget == "diagnostico":
            ttk.Button(extra, text="Comprobar instalación ahora", style="Acento.TButton",
                       command=lambda: ventana_diagnostico(app)).pack(side="left")
        elif widget == "teclas":
            ttk.Button(extra, text="Cambiar teclas…", command=lambda: ventana_teclas(app)).pack(side="left")
        b_atras.config(state="normal" if i > 0 else "disabled")
        b_sig.config(text="Terminar" if i == len(pasos) - 1 else "Siguiente ▶")

    def mover(d):
        if pasos[pos["i"]][2] == "nombre":
            guardar_nombre()
        if pos["i"] + d >= len(pasos):
            cerrar()
            return
        pos["i"] = max(0, pos["i"] + d)
        if d > 0:
            pasos[:] = _pasos(app)          # por si cambió las teclas o el nombre
        mostrar()

    def cerrar():
        guardar_nombre()
        app.prefs["tutorial_visto"] = True
        app.guardar_prefs()
        win.destroy()
        if al_terminar:
            al_terminar()

    pie = ttk.Frame(win, padding=14)
    pie.pack(fill="x", side="bottom")
    b_sig = ttk.Button(pie, text="Siguiente ▶", style="Acento.TButton", command=lambda: mover(1))
    b_sig.pack(side="right")
    b_atras = ttk.Button(pie, text="◀ Atrás", command=lambda: mover(-1))
    b_atras.pack(side="right", padx=6)
    ttk.Button(pie, text="Saltar tutorial", command=cerrar).pack(side="left")
    win.protocol("WM_DELETE_WINDOW", cerrar)
    mostrar()
    return win


# ---------------------------------------------------------------- prompt para otro asistente de IA
ARCHIVO_PROMPT = os.path.join(carpetas.RAIZ, "PROMPT_CALIBRACION.md")


def texto_prompt():
    with open(ARCHIVO_PROMPT, encoding="utf-8") as fh:
        s = fh.read()
    ini, fin = s.find("---------------- INICIO DEL PROMPT"), s.find("---------------- FIN DEL PROMPT")
    if ini >= 0 and fin > ini:
        s = s[s.index("\n", ini) + 1:fin].rstrip("-\n ")
    return s.strip() + "\n"


def _ultimo_viaje():
    try:
        v = sorted(f for f in os.listdir(carpetas.VIAJES) if f.startswith("viaje_") and f.endswith(".csv"))
    except Exception:  # noqa
        return None
    return os.path.join(carpetas.VIAJES, v[-1]) if v else None


def _seleccion_llm(datos, recorrido):
    """(rutas de los JSON, [(archivo, trazado)]) que necesita la IA para ese recorrido."""
    import grabaciones
    import rutas
    jsons = []

    def agregar(r):
        if r not in jsons and os.path.exists(r):
            jsons.append(r)

    ruta = next((r for r in datos["rutas"] if rutas.nombre_recorrido(r) == recorrido), None)
    if ruta is not None:
        agregar(os.path.join(carpetas.RUTAS, ruta["_archivo"]))
    else:                                    # recorrido desconocido: todas las rutas
        for r in datos["rutas"]:
            agregar(os.path.join(carpetas.RUTAS, r["_archivo"]))
    agregar(os.path.join(carpetas.RUTAS, "_comunes.json"))
    if ruta is not None and datos.get("compartidos"):             # 2.5.0: tramos compartidos y sus recorridos
        agregar(os.path.join(carpetas.DATOS, "compartidos.json"))
        tramos = rutas.tramos_compartidos(datos, ruta, 1) + rutas.tramos_compartidos(datos, ruta, 2)
        for _otro, _lo, _hi, _c, g in tramos:
            for r in datos["rutas"]:
                if os.path.splitext(r["_archivo"])[0] in (g.get("a"), g.get("b")) and r is not ruta:
                    agregar(os.path.join(carpetas.RUTAS, r["_archivo"]))
    trazados = []
    try:                                     # 2.5.1: trazados del recorrido (mandan sobre el lado de las reglas)
        for t in grabaciones.cargar_trazados():
            if (ruta is None or not t.get("recorrido") or t.get("recorrido") == recorrido or t.get("comun")) \
                    and t.get("_archivo"):
                trazados.append((t["_archivo"], t))
    except Exception as e:  # noqa
        print(f"[i] No se leyeron los trazados: {e}")
    return jsons, trazados


def preparar_archivos_llm(viaje, recorrido):
    """Copia a mi_equipo/para_llm/ el CSV del viaje, el JSON de su ruta, _comunes.json, los trazados del recorrido
    y sus capturas guardadas; arma para_ia.txt (todo junto) y, si hay varios trabajos, uno por trabajo."""
    import rutas
    shutil.rmtree(carpetas.PARA_LLM, ignore_errors=True)
    os.makedirs(carpetas.PARA_LLM, exist_ok=True)
    copiados = []

    def copiar(origen):
        if origen and os.path.exists(origen) and os.path.basename(origen) not in copiados:
            shutil.copy2(origen, os.path.join(carpetas.PARA_LLM, os.path.basename(origen)))
            copiados.append(os.path.basename(origen))

    copiar(viaje)
    datos = rutas.cargar()
    trabajos = []
    try:
        import paquete_ia
        if viaje:
            trabajos = [rec for rec, _tr in paquete_ia.trabajos_del_viaje(viaje)[1]]
    except Exception as e:  # noqa
        print(f"[i] No se separaron los trabajos del viaje: {e}")
    recs = [r for r in dict.fromkeys(trabajos) if r and r != "-"] or [recorrido]
    jsons, trazados = [], []
    for rec in recs:                          # todo lo que usa el viaje (todos sus recorridos)
        j, t = _seleccion_llm(datos, rec)
        jsons += [x for x in j if x not in jsons]
        trazados += [x for x in t if x[0] not in {a for a, _ in trazados}]
    for j in jsons:
        copiar(j)
    for a, _t in trazados:
        copiar(os.path.join(carpetas.TRAZADOS, a))
    try:                                     # 2.5.3: todo en un solo archivo chico (planes gratis de las IA)
        import paquete_ia
        try:
            prompt = texto_prompt()
        except Exception:  # noqa
            prompt = None
        nombres = lambda js: [(os.path.basename(x), x) for x in js]  # noqa: E731
        paquete_ia.armar(os.path.join(carpetas.PARA_LLM, "para_ia.txt"), viaje, nombres(jsons), trazados, prompt)
        extra = ["para_ia.txt"]
        if len(trabajos) > 1:                # 2.5.5: uno por trabajo (más chicos: Gemini corta cerca de 200 KB)
            for n, rec in enumerate(trabajos, 1):
                j, t = _seleccion_llm(datos, rec if rec != "-" else None)
                nombre = f"para_ia_trabajo{n}.txt"
                paquete_ia.armar(os.path.join(carpetas.PARA_LLM, nombre), viaje, nombres(j), t, prompt, indice=n)
                extra.append(nombre)
        copiados[:0] = extra
    except Exception as e:  # noqa
        print(f"[!] No se pudo armar para_ia.txt: {e}")
    if viaje:
        base = os.path.splitext(os.path.basename(viaje))[0]
        caps = os.path.join(os.path.dirname(viaje), "capturas")
        if os.path.isdir(caps):
            for f in sorted(os.listdir(caps)):
                if f.startswith(base + "_"):
                    copiar(os.path.join(caps, f))
    return copiados


def copiar_prompt_llm(app, viaje=None, recorrido=None):
    try:
        txt = texto_prompt()
    except Exception as e:  # noqa
        messagebox.showerror("Prompt de calibración", f"No encuentro PROMPT_CALIBRACION.md:\n{e}", parent=app.root)
        return
    viaje = viaje or _ultimo_viaje()
    if recorrido is None and viaje:
        recorrido = app._resumen_viaje(viaje).get("recorrido")
    try:
        copiados = preparar_archivos_llm(viaje, recorrido)
    except Exception as e:  # noqa
        copiados = []
        print(f"[!] No se pudieron preparar los archivos para el asistente: {e}")
    app.root.clipboard_clear()
    app.root.clipboard_append(txt)
    print(f"[OK] Prompt de calibración copiado. Archivos en mi_equipo/para_llm/: {', '.join(copiados) or '(ninguno)'}")
    if copiados:
        app.abrir_carpeta(carpetas.PARA_LLM)
    tam = os.path.getsize(viaje) / 1e6 if viaje and os.path.exists(viaje) else 0
    nota = (f"\n\nOjo: el CSV pesa {tam:.0f} MB; algunos asistentes no aceptan archivos tan grandes."
            if tam > 15 else "")
    messagebox.showinfo(
        "Prompt de calibración",
        "El prompt quedó copiado: pégalo (Ctrl+V) en el chat del asistente de IA.\n\n"
        + ("Después adjunta SOLO «para_ia.txt» (de la carpeta que se abrió): trae las instrucciones, el viaje "
           "resumido, las reglas, los tramos compartidos y los trazados en un solo archivo chico. Si se te olvida "
           "pegar el prompt, basta con adjuntarlo y escribir «analiza y pregunta»."
           + (f"\n\nEl viaje tiene {sum(1 for c in copiados if c.startswith('para_ia_trabajo'))} trabajos: si el "
              "asistente no lee el archivo entero (Gemini), usa uno a la vez: «para_ia_trabajo1.txt», "
              "«para_ia_trabajo2.txt»…" if any(c.startswith("para_ia_trabajo") for c in copiados) else "")
           + "\n\nSi el asistente acepta muchos archivos grandes, también puedes adjuntar los sueltos:\n  • "
           + "\n  • ".join(c for c in copiados if not c.startswith("para_ia"))
           if copiados and copiados[0] == "para_ia.txt" else
           (f"Después adjunta los archivos de la carpeta que se abrió ({len(copiados)}):\n  • "
            + "\n  • ".join(copiados) if copiados else "No encontré viajes: haz un viaje primero."))
        + f"{nota}\n\nViaje: {os.path.basename(viaje) if viaje else '-'} · Recorrido: {recorrido or '-'}\n\n"
          "Cuando el asistente te entregue el JSON corregido, guárdalo en datos/rutas/ (reemplazando el "
          "anterior) y reinicia el programa.", parent=app.root)

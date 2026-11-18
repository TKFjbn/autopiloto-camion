"""
Menú de trabajos al abrir el programa (3.9.0).

Una cuadrícula de botones grandes, siempre centrada y con 3 por fila como máximo: con 1 trabajo, uno al centro;
con 2, dos lado a lado al centro; con 4, tres arriba y el cuarto abajo al centro; y así. Para agregar un trabajo
basta con sumarlo a TRABAJOS (y que el resto del programa sepa qué hacer en ese modo).

Lo elegido se recuerda en mi_equipo/modo.json; con «Abrir siempre en este modo» el menú no vuelve a salir
(se cambia con el botón del trabajo, arriba en la ventana principal).
Solo usa la biblioteca estándar (lo abre arranque.py antes que todo lo demás).
"""
import json
import os

PROGRAMA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(os.path.dirname(PROGRAMA), "mi_equipo", "modo.json")

# (clave, nombre, ícono, descripción)
TRABAJOS = [
    ("camionero", "Camionero", "🚚", "El trabajo de camionero: etapas (cargar, ir, volver), rutas reconocidas, "
                                     "reglas por lugar, mapa de la ruta y grabaciones."),
    ("libre", "Libre (prueba)", "🧭", "Marca un punto en el mapa (ruta morada) y el autopiloto te lleva. "
                                      "Sin etapas ni rutas: solo reglas generales del modo."),
]
NOMBRES = {k: n for k, n, _i, _d in TRABAJOS}

FONDO, PANEL, BORDE, TEXTO, TENUE, ACENTO = "#1e1f22", "#2b2d31", "#3f4147", "#f2f3f5", "#949ba4", "#5865f2"


def leer():
    try:
        with open(ARCHIVO, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa
        return {}


def guardar(modo, siempre):
    try:
        os.makedirs(os.path.dirname(ARCHIVO), exist_ok=True)
        with open(ARCHIVO, "w", encoding="utf-8") as fh:
            json.dump({"modo": modo, "siempre": bool(siempre)}, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def posiciones(n, por_fila=3):
    """[(fila, columna_en_fila, cuántos_en_esa_fila)] para n botones: filas de 3, la última centrada."""
    out = []
    for i in range(n):
        fila = i // por_fila
        en_fila = min(por_fila, n - fila * por_fila)
        out.append((fila, i % por_fila, en_fila))
    return out


def elegir(forzar_menu=False):
    """Devuelve la clave del trabajo elegido, o None si se cerró el menú."""
    pref = leer()
    if not forzar_menu and pref.get("siempre") and pref.get("modo") in NOMBRES:
        return pref["modo"]
    if len(TRABAJOS) == 1:
        return TRABAJOS[0][0]
    import tkinter as tk
    root = tk.Tk()
    root.title("Autopiloto · elige el trabajo")
    root.configure(bg=FONDO)
    elegido = {"modo": None}
    var_siempre = tk.BooleanVar(value=bool(pref.get("siempre")))

    cab = tk.Frame(root, bg=PANEL, padx=20, pady=16)
    cab.pack(fill="x", padx=8, pady=(8, 4))
    tk.Label(cab, text="¿Qué trabajo vas a hacer?", font=("Segoe UI", 16, "bold"), bg=PANEL, fg=TEXTO).pack()
    tk.Label(cab, text="Puedes cambiarlo después con el botón del trabajo, arriba en la ventana.",
             font=("Segoe UI", 9), bg=PANEL, fg=TENUE).pack(pady=(4, 0))

    cuerpo = tk.Frame(root, bg=PANEL, padx=30, pady=24)
    cuerpo.pack(fill="both", expand=True, padx=8, pady=4)
    filas = {}
    for (clave, nombre, icono, desc), (fila, _col, _n) in zip(TRABAJOS, posiciones(len(TRABAJOS))):
        if fila not in filas:
            filas[fila] = tk.Frame(cuerpo, bg=PANEL)
            filas[fila].pack(pady=8)                       # cada fila se centra sola

        def elegir_este(c=clave):
            elegido["modo"] = c
            elegido["siempre"] = bool(var_siempre.get())      # antes de cerrar la ventana
            root.destroy()
        marcado = pref.get("modo") == clave
        b = tk.Frame(filas[fila], bg=ACENTO if marcado else BORDE, padx=2, pady=2, cursor="hand2")
        b.pack(side="left", padx=8)
        dentro = tk.Frame(b, bg="#383a40", width=240, height=150, cursor="hand2")
        dentro.pack()
        dentro.pack_propagate(False)
        for w, txt, fnt, col in ((None, icono, ("Segoe UI Emoji", 26), TEXTO),
                                 (None, nombre, ("Segoe UI", 13, "bold"), TEXTO),
                                 (None, desc, ("Segoe UI", 8), TENUE)):
            lbl = tk.Label(dentro, text=txt, font=fnt, bg="#383a40", fg=col, wraplength=220, justify="center",
                           cursor="hand2")
            lbl.pack(pady=(10, 0) if txt == icono else (2, 0))
            lbl.bind("<Button-1>", lambda _e, f=elegir_este: f())
        for w in (b, dentro):
            w.bind("<Button-1>", lambda _e, f=elegir_este: f())

        def resaltar(_e, w=dentro, on=True):
            col = "#404249" if on else "#383a40"
            w.configure(bg=col)
            for h in w.winfo_children():
                h.configure(bg=col)
        dentro.bind("<Enter>", lambda e, w=dentro: resaltar(e, w, True))
        dentro.bind("<Leave>", lambda e, w=dentro: resaltar(e, w, False))

    pie = tk.Frame(root, bg=FONDO, pady=6)
    pie.pack(fill="x", padx=8, pady=(0, 8))
    tk.Checkbutton(pie, text="Abrir siempre en el trabajo que elija (sin este menú)", variable=var_siempre,
                   bg=FONDO, fg=TENUE, selectcolor=PANEL, activebackground=FONDO, activeforeground=TEXTO,
                   font=("Segoe UI", 9)).pack()
    root.update_idletasks()
    w, h = max(560, root.winfo_reqwidth()), max(380, root.winfo_reqheight())
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.mainloop()
    if elegido["modo"]:
        guardar(elegido["modo"], elegido.get("siempre", False))
    return elegido["modo"]

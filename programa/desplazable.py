"""
Zona con barra de desplazamiento vertical (3.4.1) para pestañas y paneles que no caben en la pantalla.

    marco, interior, lienzo = desplazable.crear(padre, bg="#2b2d31", estilo="Panel.TFrame", padding=8)
    marco.pack(fill="both", expand=True)
    ... poner el contenido en «interior» ...

- La barra aparece solo cuando el contenido no cabe.
- La rueda del mouse mueve la zona mientras el mouse está encima, salvo sobre listas, textos o lienzos que tienen
  su propia barra (Treeview, Text, Canvas, Listbox).
- El contenido toma el ancho de la zona (no hay barra horizontal).
"""
import tkinter as tk
from tkinter import ttk

PROPIOS = ("Text", "Treeview", "Canvas", "Listbox", "TCombobox")


def _dentro(w, marco):
    a, b = str(w), str(marco)
    return a == b or a.startswith(b + ".")


def crear(padre, bg, estilo="Panel.TFrame", padding=0, horizontal=False):
    """horizontal=True (3.6.1): si el contenido es más ancho que la zona, aparece también una barra abajo
    (Shift + rueda la mueve)."""
    marco = tk.Frame(padre, bg=bg, highlightthickness=0, borderwidth=0)
    marco.rowconfigure(0, weight=1)
    marco.columnconfigure(0, weight=1)
    lienzo = tk.Canvas(marco, highlightthickness=0, borderwidth=0, bg=bg)
    barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
    barra_h = ttk.Scrollbar(marco, orient="horizontal", command=lienzo.xview)
    interior = ttk.Frame(lienzo, style=estilo, padding=padding)
    item = lienzo.create_window((0, 0), window=interior, anchor="nw")
    lienzo.configure(yscrollcommand=barra.set, xscrollcommand=barra_h.set)
    lienzo.grid(row=0, column=0, sticky="nsew")
    estado = {"barra": False, "barra_h": False}

    def revisar(_e=None):
        alto_c, ancho_c = lienzo.winfo_height(), lienzo.winfo_width()
        ancho = max(ancho_c, interior.winfo_reqwidth()) if horizontal else ancho_c
        lienzo.itemconfigure(item, width=ancho)
        alto_i = interior.winfo_reqheight()
        lienzo.itemconfigure(item, height=max(alto_i, alto_c))       # rellena si sobra (los fill="both" se ven)
        lienzo.configure(scrollregion=(0, 0, ancho, max(alto_i, alto_c)))
        if horizontal:
            falta_h = ancho > ancho_c + 2
            if falta_h and not estado["barra_h"]:
                barra_h.grid(row=1, column=0, sticky="ew")
                estado["barra_h"] = True
            elif not falta_h and estado["barra_h"]:
                barra_h.grid_remove()
                estado["barra_h"] = False
                lienzo.xview_moveto(0)
        falta = alto_i > alto_c + 2
        if falta and not estado["barra"]:
            barra.grid(row=0, column=1, sticky="ns")
            estado["barra"] = True
        elif not falta and estado["barra"]:
            barra.grid_remove()
            estado["barra"] = False
            lienzo.yview_moveto(0)

    def rueda(e, delta=None, lado=False):
        if not estado["barra_h" if lado else "barra"]:
            return None
        w = e.widget
        try:
            if w is not lienzo and w.winfo_class() in PROPIOS:
                return None
            if not _dentro(w, marco):
                return None
        except (tk.TclError, AttributeError):
            return None
        d = delta if delta is not None else (-1 if e.delta > 0 else 1)
        if lado:
            lienzo.xview_scroll(d * 3, "units")
        else:
            lienzo.yview_scroll(d * 3, "units")
        return "break"

    def entrar(_e):
        marco.bind_all("<MouseWheel>", rueda)
        marco.bind_all("<Button-4>", lambda e: rueda(e, -1))
        marco.bind_all("<Button-5>", lambda e: rueda(e, 1))
        if horizontal:
            marco.bind_all("<Shift-MouseWheel>", lambda e: rueda(e, None, True))

    def salir(e):
        try:                                     # al pasar a un hijo también llega <Leave>: solo si sale del todo
            x, y = marco.winfo_pointerxy()
            dentro = marco.winfo_containing(x, y)
            if dentro is not None and _dentro(dentro, marco):
                return
        except (tk.TclError, KeyError):
            pass
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>"):
            marco.unbind_all(ev)

    interior.bind("<Configure>", revisar, add="+")
    lienzo.bind("<Configure>", revisar, add="+")
    marco.bind("<Enter>", entrar, add="+")
    marco.bind("<Leave>", salir, add="+")
    return marco, interior, lienzo

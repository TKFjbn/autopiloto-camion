"""
Ventanas de actualización (3.1.0): aviso de versión nueva, instalación desde GitHub y desde un .zip.

La lógica está en actualizar.py; aquí solo está lo que se ve. Todo lo lento (internet, copiar archivos) va
en un hilo aparte y la ventana lo consulta cada 200 ms: tkinter no se toca desde otros hilos.
"""
import os
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, filedialog, messagebox

import actualizar
import version


class Tarea:
    """Corre `fn(estado)` en un hilo. `estado` es un dict compartido: {"texto", "pct", "ok", "error", "fin"}."""

    def __init__(self, fn):
        self.estado = {"texto": "", "pct": None, "ok": None, "error": None, "fin": False}
        self.hilo = threading.Thread(target=self._correr, args=(fn,), daemon=True)
        self.hilo.start()

    def _correr(self, fn):
        try:
            self.estado["ok"] = fn(self.estado)
        except actualizar.ErrorActualizar as e:
            self.estado["error"] = str(e)
        except Exception as e:  # noqa
            self.estado["error"] = f"Error inesperado: {e}"
        finally:
            self.estado["fin"] = True


def _esperar(app, tarea, al_pasar, al_fin, ms=200):
    """Consulta la tarea desde el hilo de la ventana hasta que termina."""
    def paso():
        try:
            al_pasar(tarea.estado)
            if tarea.estado["fin"]:
                al_fin(tarea.estado)
                return
            app.root.after(ms, paso)
        except tk.TclError:
            pass                                          # la ventana se cerró
    app.root.after(ms, paso)


# ------------------------------------------------------------------ buscar
def revisar(app, manual=False):
    """Pregunta a GitHub por la última versión. Al abrir el programa es silencioso si no hay nada nuevo."""
    if getattr(app, "_buscando_act", False):
        return
    app._buscando_act = True

    def trabajo(est):
        est["texto"] = "Buscando…"
        return actualizar.consultar()

    def fin(est):
        app._buscando_act = False
        if est["error"]:
            if manual:
                messagebox.showinfo("Actualizaciones", est["error"], parent=app.root)
            else:
                print(f"[i] No se pudo buscar actualizaciones: {est['error']}")
            return
        info = est["ok"]
        app._ultima_version = info
        if not actualizar.hay_nueva(info["version"]):
            app.btn_nueva.pack_forget()
            if manual:
                messagebox.showinfo("Actualizaciones", f"Estás al día: tienes la versión {version.VERSION}.",
                                    parent=app.root)
            return
        app.btn_nueva.config(text=f"⬆ Versión {info['version']}")
        app.btn_nueva.pack(side="right", padx=(0, 8))
        print(f"[i] Hay una versión nueva del programa: {info['version']} (tienes {version.VERSION}).")
        ignorada = app.prefs["actualizaciones"].get("ignorar") == info["version"]
        corriendo = app.hilo is not None and app.hilo.is_alive()
        if manual or (not ignorada and not corriendo):
            mostrar(app, info)

    _esperar(app, Tarea(trabajo), lambda e: None, fin)


def mostrar_ultima(app):
    info = getattr(app, "_ultima_version", None)
    if info:
        mostrar(app, info)
    else:
        revisar(app, manual=True)


# ------------------------------------------------------------------ ventana de la versión nueva
def mostrar(app, info):
    """Ventana con lo que cambia y los botones para actualizar."""
    prev = getattr(app, "_win_act", None)
    try:
        if prev is not None and prev.winfo_exists():
            prev.lift()
            return
    except tk.TclError:
        pass
    T = app.T
    win = app._win_act = tk.Toplevel(app.root)
    win.title("Actualizar el autopiloto")
    win.configure(bg=T["bg"])
    win.transient(app.root)
    win.geometry("640x540")
    cab = ttk.Frame(win, padding=(12, 10, 12, 0))
    cab.pack(fill="x")
    ttk.Label(cab, text=f"Versión {info['version']} disponible", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(cab, text=f"Tienes la {version.VERSION}. Esto es lo que cambia:").pack(anchor="w", pady=(2, 0))
    cuerpo = ttk.Frame(win, padding=12)
    cuerpo.pack(fill="both", expand=True)
    txt = tk.Text(cuerpo, wrap="word", height=14, bg=T["log_bg"], fg=T["log_fg"], relief="flat", padx=8, pady=6,
                  font=("Segoe UI", 10))
    sb = ttk.Scrollbar(cuerpo, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", actualizar.notas_cortas(info.get("notas")) or "(Esta versión no trae descripción.)")
    txt.config(state="disabled")
    pie = ttk.Frame(win, padding=(12, 0, 12, 12))
    pie.pack(fill="x")
    var_datos = tk.BooleanVar(value=True)
    ttk.Checkbutton(pie, text="Actualizar también los datos (rutas, grabaciones y trazados)",
                    variable=var_datos).pack(anchor="w")
    ttk.Label(pie, text="Antes de cambiar nada se guarda una copia en mi_equipo/respaldos/. Tu calibración, tus "
                        "preferencias y tus viajes no se tocan.", style="Tenue.TLabel", wraplength=600,
              justify="left").pack(anchor="w", pady=(2, 6))
    estado = ttk.Label(pie, text="", style="Tenue.TLabel")
    estado.pack(anchor="w", pady=(0, 6))
    barra = ttk.Progressbar(pie, mode="determinate", maximum=100)
    botones = ttk.Frame(pie)
    botones.pack(fill="x")
    b_ahora = ttk.Button(botones, text="Actualizar ahora", style="Acento.TButton")
    b_ahora.pack(side="left")
    b_luego = ttk.Button(botones, text="Más tarde", command=win.destroy)
    b_luego.pack(side="left", padx=6)

    def no_avisar():
        app.prefs["actualizaciones"]["ignorar"] = info["version"]
        app.guardar_prefs()
        win.destroy()
    b_ign = ttk.Button(botones, text="No avisar de esta versión", command=no_avisar)
    b_ign.pack(side="left")
    ttk.Button(botones, text="Ver en GitHub", command=lambda: webbrowser.open(info.get("url") or "")).pack(
        side="right")

    def actualizar_ahora():
        if app.hilo is not None and app.hilo.is_alive():
            messagebox.showinfo("Actualizar", "Detén el programa antes de actualizar (botón «Detener»).", parent=win)
            return
        for b in (b_ahora, b_luego, b_ign):
            b.config(state="disabled")
        barra.pack(fill="x", pady=(0, 6), before=botones)
        con_datos = var_datos.get()

        def trabajo(est):
            est["texto"] = "Descargando…"
            carpeta = tempfile.mkdtemp(prefix="autopiloto_dl_")
            ruta = os.path.join(carpeta, "autopiloto_camion.zip")

            def prog(hecho, total):
                est["pct"] = (100.0 * hecho / total) if total else None
                est["texto"] = f"Descargando… {hecho / 1e6:.1f} MB" + (f" de {total / 1e6:.1f}" if total else "")
            actualizar.descargar(info.get("zip"), ruta, prog)
            est["texto"], est["pct"] = "Instalando…", None
            try:
                return actualizar.aplicar(ruta, con_datos=con_datos, log=print)
            finally:
                try:
                    os.remove(ruta)
                    os.rmdir(carpeta)
                except OSError:
                    pass
        _esperar(app, Tarea(trabajo), lambda e: _mostrar_avance(e, estado, barra),
                 lambda e: _terminar(app, win, e, estado, barra, botones, b_luego))

    b_ahora.config(command=actualizar_ahora)


def _mostrar_avance(est, etiqueta, barra):
    etiqueta.config(text=est["texto"])
    if est["pct"] is None:
        barra.config(mode="indeterminate")
        barra.step(4)
    else:
        barra.config(mode="determinate", value=est["pct"])


def _terminar(app, win, est, etiqueta, barra, botones, b_luego):
    barra.pack_forget()
    if est["error"]:
        etiqueta.config(text="No se pudo actualizar: " + est["error"], foreground=app.T["error"])
        b_luego.config(text="Cerrar", state="normal", command=win.destroy)
        return
    r = est["ok"]
    print(f"[OK] Actualizado: {r['antes']} → {r['despues']} ({r['archivos']} archivos"
          + (f", datos {r['datos']}" if r.get("datos") else "") + ").")
    app.btn_nueva.pack_forget()
    etiqueta.config(text=f"Listo: versión {r['despues']} instalada. Cierra el programa y vuelve a abrirlo "
                         "para usarla.", foreground=app.T["ok"])
    for w in botones.winfo_children():
        w.pack_forget()
    ttk.Button(botones, text="Cerrar el programa ahora", style="Acento.TButton", command=app.cerrar).pack(side="left")
    ttk.Button(botones, text="Seguir con esta versión", command=win.destroy).pack(side="left", padx=6)


# ------------------------------------------------------------------ desde un .zip
def desde_zip(app):
    """Instala una versión desde un .zip que te pasaron (sin internet)."""
    if app.hilo is not None and app.hilo.is_alive():
        messagebox.showinfo("Actualizar", "Detén el programa antes de actualizar (botón «Detener»).",
                            parent=app.root)
        return
    ruta = filedialog.askopenfilename(parent=app.root, title="Elige el .zip del autopiloto",
                                      filetypes=(("Autopiloto (zip)", "*.zip"), ("Todos", "*.*")))
    if not ruta:
        return
    try:
        info = actualizar.inspeccionar(ruta)
    except actualizar.ErrorActualizar as e:
        messagebox.showerror("Actualizar", str(e), parent=app.root)
        return
    nueva, actual = info["programa"], version.VERSION
    datos = info.get("datos")
    texto = (f"Programa: {actual} → {nueva}\n" + (f"Datos: {actualizar.version_datos_local() or '?'} → {datos}\n"
                                                     if datos else "") +
             "\nSe guarda antes una copia de lo que se reemplaza en mi_equipo/respaldos/.\nTu calibración, tus "
             "preferencias y tus viajes no se tocan.")
    if version.tupla(nueva) < version.tupla(actual):
        messagebox.showerror("Actualizar", f"Ese .zip es más viejo ({nueva}) que tu versión ({actual}).",
                             parent=app.root)
        return
    igual = version.tupla(nueva) == version.tupla(actual)
    if igual:
        texto = f"Ese .zip es la misma versión que tienes ({actual}); se reinstala encima.\n\n" + texto
    con_datos = True
    if datos:
        r = messagebox.askyesnocancel("Actualizar", texto + "\n\n¿Actualizar también los datos?\n"
                                      "Sí = programa y datos · No = solo el programa · Cancelar = no hacer nada",
                                      parent=app.root)
        if r is None:
            return
        con_datos = r
    elif not messagebox.askyesno("Actualizar", texto + "\n\n¿Instalar?", parent=app.root):
        return

    def trabajo(est):
        est["texto"] = "Instalando…"
        return actualizar.aplicar(ruta, con_datos=con_datos, permitir_igual=igual, log=print)

    def fin(est):
        if est["error"]:
            messagebox.showerror("Actualizar", est["error"], parent=app.root)
            return
        r = est["ok"]
        print(f"[OK] Actualizado: {r['antes']} → {r['despues']} ({r['archivos']} archivos).")
        if messagebox.askyesno("Actualizar", f"Listo: versión {r['despues']} instalada.\n\n¿Cerrar el programa ahora "
                               "para volver a abrirlo con la versión nueva?", parent=app.root):
            app.cerrar()
    _esperar(app, Tarea(trabajo), lambda e: None, fin)

"""
Íconos de la flecha que el HUD del juego muestra a la izquierda de la distancia (3.9.0).

hud_texto lee la flecha como ↑ ← → ↗ ↖; aquí se pasa a un ícono grande para la interfaz.
"?" = hay distancia pero no se reconoció la flecha. Por ahora solo se muestra: no se usa para conducir.
"""
ICONOS = {"↑": "⬆", "←": "⬅", "→": "➡", "↗": "⬈", "↖": "⬉"}
NOMBRES = {"↑": "sigue recto", "←": "gira a la izquierda", "→": "gira a la derecha",
           "↗": "mantente a la derecha", "↖": "mantente a la izquierda"}


def icono(flecha, metros=None):
    """Ícono para la flecha del HUD; "?" si hay distancia sin flecha reconocida; "" si no hay nada."""
    if flecha in ICONOS:
        return ICONOS[flecha]
    return "?" if metros is not None else ""


def con_distancia(texto_km, flecha, metros):
    """«⬈ 2,28 km» (o solo la distancia si no hay nada que mostrar)."""
    ic = icono(flecha, metros)
    return f"{ic} {texto_km}" if ic else texto_km

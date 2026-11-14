"""
Versión del programa (versionado semántico: MAYOR.MENOR.PARCHE).

  MAYOR  cambia el formato de datos o de reportes (lo viejo deja de ser compatible).
  MENOR  funciones nuevas, compatibles con lo anterior.
  PARCHE arreglos y ajustes sin funciones nuevas.

Los datos (carpeta datos/) llevan su propia versión en datos/datos.json, y cada archivo de datos dice
la versión mínima del programa que necesita ("programa_minimo").
"""
VERSION = "3.1.0"
FORMATO_DATOS = 1          # formato de los archivos de datos/ que este programa sabe leer


def tupla(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0, 0, 0)


def cumple(minimo):
    """True si este programa es igual o más nuevo que `minimo` (texto 'X.Y.Z')."""
    return not minimo or tupla(VERSION) >= tupla(minimo)


def cumple_minimo_de(actual, minimo):
    """True si la versión `actual` (texto) es >= `minimo`."""
    try:
        return tupla(actual or "0") >= tupla(minimo)
    except Exception:  # noqa
        return False

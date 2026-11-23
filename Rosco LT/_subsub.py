# SPDX-License-Identifier: GPL-3.0-or-later
"""Sub-submenús de los subroscos: un botón del submenú puede llevar más
órdenes detrás (una marca ▸ lo dice).

- Al pasar el ratón por ese botón, su sub-submenú sale solo, por fuera del
  rosco (o debajo del botón, en los submenús rectangulares).
- Clic en el botón: su orden de ahora. Clic en una del sub-submenú: esa
  orden pasa a ocupar el botón y la que estaba, al sub-submenú (se recuerda).

``SUBSUB`` dice qué hueco de qué submenú las lleva; ``cara`` y
``poner_cara`` leen y cambian la que está a la vista; ``geometria`` da los
gajos (o rectángulos) del sub-submenú abierto.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF

# (submenú, hueco) → las órdenes que comparten el hueco (la primera, de serie).
SUBSUB = {("move", "estirar"): ("estirar ventana", "prolongar a plano")}
# Solo los de las partes que lleva esta edición (``_edicion``).
from . import _edicion  # noqa: E402
SUBSUB = {k: v for k, v in SUBSUB.items() if _edicion.modo(*k)}
TEXTOS = {"estirar ventana": "estirar\nventana", "prolongar a plano": "prolongar\na plano",
          "borrar anotaciones": "borrar\nanotaciones"}
ICONOS = {"estirar ventana": "m_estirar", "prolongar a plano": "m_prolongar",
          "anotar": "m_anotar", "borrar anotaciones": "m_borrar_anot"}
TEXTOS, ICONOS = _edicion.limpiar(TEXTOS), _edicion.limpiar(ICONOS)
ANCHO_FLY = 50.0                       # el grueso de la banda del sub-submenú
PASO_FLY = 52.0                        # grados de cada gajo del sub-submenú


def _ajustes():
    from ._ajustes import ajustes
    return ajustes("subsub")


def tiene(clave, hueco) -> bool:
    return (clave, hueco) in SUBSUB


_CARAS: dict = {}                      # lo leído de los ajustes (la barra lo mira a menudo)


def cara(clave, hueco) -> str:
    """La orden que está a la vista en el hueco."""
    opciones = SUBSUB[(clave, hueco)]
    if (clave, hueco) not in _CARAS:
        try:
            v = _ajustes().value(f"{clave}/{hueco}")
        except Exception:  # noqa: BLE001
            v = None
        _CARAS[(clave, hueco)] = v
    v = _CARAS[(clave, hueco)]
    return v if v in opciones else opciones[0]


def poner_cara(clave, hueco, orden) -> None:
    if orden in SUBSUB.get((clave, hueco), ()):
        _CARAS[(clave, hueco)] = orden
        _ajustes().setValue(f"{clave}/{hueco}", orden)


def otras(clave, hueco) -> list:
    """Las del sub-submenú: todas menos la que está a la vista."""
    actual = cara(clave, hueco)
    return [o for o in SUBSUB[(clave, hueco)] if o != actual]


def texto(orden) -> str:
    return TEXTOS.get(orden, orden)


def icono(orden):
    return ICONOS.get(orden)


def geometria(g: dict, clave, hueco) -> list:
    """[(orden, forma)] del sub-submenú de ``hueco`` en el submenú ``g``
    (radial: gajos por fuera, centrados en el del hueco; rectangular:
    rectángulos debajo del suyo). Las formas responden a ``contains``."""
    claves = [k for k, _r in g.get("chips", ())]
    if hueco not in claves or not tiene(clave, hueco):
        return []
    i = claves.index(hueco)
    lista = otras(clave, hueco)
    if g.get("radial"):
        from ._rosco import ANCHO_MODOS, HUECO_PX, Gajo
        e = g.get("e", 1.0)
        c, rh = g["centro"], g["rh"]
        r1 = rh + HUECO_PX + ANCHO_MODOS * _f(g)
        if g.get("finales"):
            # Con «al terminar» (Línea…) por fuera: el sub-submenú, más allá,
            # para que no lo tape (2.49.2).
            from ._rosco import ANCHO_FINALES
            r1 += HUECO_PX + ANCHO_FINALES * _f(g)
        n = len(claves)
        paso = 360.0 / n
        medio = 90.0 + paso / 2.0 - (i + 1) * paso + paso / 2.0
        ancho = PASO_FLY * len(lista)
        a0 = medio - ancho / 2.0
        return [(o, Gajo(c, r1 + HUECO_PX, r1 + HUECO_PX + ANCHO_FLY * e, a0 + j * PASO_FLY, PASO_FLY))
                for j, o in enumerate(lista)]
    r = dict(g["chips"])[hueco]
    return [(o, QRectF(r.left(), r.bottom() + 4.0 + j * (r.height() + 4.0), r.width(), r.height()))
            for j, o in enumerate(lista)]


def _f(g) -> float:
    """El factor de tamaño con que se hizo el rosco (de su radio central)."""
    from ._rosco import RH, RH_LADOS
    rh = g["rh"]
    con_lados = "menos" in g
    return rh / (RH_LADOS if con_lados else RH)


def marca(g: dict, clave):
    """[(punto, ángulo)] para la marca ▸ de los huecos con sub-submenú
    (radial); en el rectangular, la esquina de abajo a la derecha."""
    salida = []
    claves = [k for k, _r in g.get("chips", ())]
    for i, k in enumerate(claves):
        if not tiene(clave, k):
            continue
        if g.get("radial"):
            from ._rosco import ANCHO_MODOS, HUECO_PX
            r1 = g["rh"] + HUECO_PX + ANCHO_MODOS * _f(g)
            paso = 360.0 / len(claves)
            a = 90.0 + paso / 2.0 - (i + 1) * paso + paso / 2.0
            c = g["centro"]
            ar = math.radians(a)
            salida.append((QPointF(c.x() + (r1 + 4.0) * math.cos(ar), c.y() - (r1 + 4.0) * math.sin(ar)), a))
        else:
            r = dict(g["chips"])[k]
            salida.append((QPointF(r.right() - 6.0, r.bottom() - 6.0), -45.0))
    return salida

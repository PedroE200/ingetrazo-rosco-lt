# SPDX-License-Identifier: GPL-3.0-or-later
"""Iconos de las Tareas: los PNG de ``imagenes`` (la libreta del botón, que
sale de ``icono_tareas.svg``, y los botones de borrar y recuperar tarea) y
los iconos de línea de la columna, el buscador y el micrófono, dibujados aquí."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

IMAGENES = Path(__file__).resolve().parent / "imagenes"


@lru_cache(maxsize=None)
def pixmap(nombre: str) -> QPixmap:
    return QPixmap(str(IMAGENES / nombre))


def icono(nombre: str) -> QIcon:
    return QIcon(pixmap(nombre))


def libreta() -> QIcon:
    """El icono de las Tareas (botón de la barra, ventana y pie): la libreta de
    espiral con casillas y bolígrafo (``icono_tareas.svg``)."""
    return icono("icono_tareas.png")


# ---- Iconos de línea (24×24, trazo redondeado) para la columna y el buscador -------------
# Los puntos son trazos de largo casi nulo: con la punta redonda salen círculos.

TRAZOS = {
    "nueva_arriba": ("M6 13h12a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1v-4a1 1 0 0 1 1 -1z",
                     "M12 3.5v6", "M9 6.5h6"),
    "nueva_abajo": ("M6 5h12a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1v-4a1 1 0 0 1 1 -1z",
                    "M12 14.5v6", "M9 17.5h6"),
    "borrar": ("M4.5 7h15", "M9.5 7v-2.5h5v2.5", "M6.5 7l1 13h9l1 -13",
               "M10.5 10.5v6", "M13.5 10.5v6"),
    "subir": ("M12 19.5v-15", "M6.5 10l5.5 -5.5l5.5 5.5"),
    "bajar": ("M12 4.5v15", "M6.5 14l5.5 5.5l5.5 -5.5"),
    "buscar": ("M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0 -13z", "M15.3 15.3l4.7 4.7"),
    "microfono": ("M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1 -6 0v-5a3 3 0 0 1 3 -3z",
                  "M6 11a6 6 0 0 0 12 0", "M12 17v3.5", "M8.5 20.5h7"),
    "plegado": ("M10 6.5l5.5 5.5l-5.5 5.5",),
    "desplegado": ("M6.5 10l5.5 5.5l5.5 -5.5",),
    "puntos": ("M9 6h.01", "M15 6h.01", "M9 12h.01", "M15 12h.01", "M9 18h.01", "M15 18h.01"),
    "reloj": ("M12 4a8 8 0 1 0 0 16a8 8 0 1 0 0 -16z", "M12 7.5v4.5l3 2"),
}
GROSOR_PUNTOS = 3.2


@lru_cache(maxsize=None)
def _pix_trazo(nombre: str, color: str, px: int, grosor: float) -> QPixmap:
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    if nombre == "puntos":
        grosor = max(grosor, GROSOR_PUNTOS)
    caminos = "".join(f'<path d="{d}"/>' for d in TRAZOS[nombre])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="{grosor}" stroke-linecap="round" '
           f'stroke-linejoin="round">{caminos}</svg>')
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return out


def trazo(nombre: str, color: str, px: int = 48, grosor: float = 2) -> QIcon:
    """Un icono de línea de ``TRAZOS`` en ``color`` (se dibuja grande y Qt lo reduce)."""
    return QIcon(_pix_trazo(nombre, color, px, grosor))


def ruta_imagen(nombre: str) -> str:
    """Ruta con barras normales, para las hojas de estilo (``image: url(...)``)."""
    return (IMAGENES / nombre).as_posix()

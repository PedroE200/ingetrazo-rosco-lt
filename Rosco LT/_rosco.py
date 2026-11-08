# SPDX-License-Identifier: GPL-3.0-or-later
"""Los submenús en rosco (Opciones ▸ Submenús ▸ Radiales): en vez del
rectángulo, una pequeña diana redonda.

- En el centro, el nombre de la orden, la flecha ‹ para volver y, en
  Polígono y Círculo, «− lados +».
- Alrededor, los modos: el primero arriba y los demás en el sentido de las
  agujas del reloj.
- Arriba, por fuera de los modos, el ojo azul.
- Por fuera, a la izquierda (el lado del puntero), «al terminar» en las
  órdenes que dibujan: de arriba abajo nada · grupo con nombre · grupo ·
  componente.

``geometria`` devuelve el mismo diccionario que el submenú rectangular
(``marco``, ``volver``, ``menos``, ``mas``…), con ``Gajo`` en lugar de
rectángulos para los modos (``chips``) y «al terminar» (``finales``): quien
la llama los empareja con sus claves, como en el rectangular. Responden a
``contains`` y ``center`` igual, así el clic se atiende con el mismo código.
"""
from __future__ import annotations

from ._idioma import _tr
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPen

from . import _flotante
from ._flotante import _pt, rayar, sector, sombra

HUECO_GRADOS = 2.0                      # entre gajo y gajo
HUECO_PX = 4.0                          # entre centro, modos y «al terminar»
RH, RH_LADOS = 34.0, 44.0               # el círculo del centro (más grande con lados)
ANCHO_MODOS, ANCHO_FINALES = 46.0, 40.0
# «Al terminar», en el orden de FINALES (nada, grupo, componente, con nombre):
# (ángulo de inicio, barrido). A la izquierda, seguidos, sin hueco en medio.
FIN_GAJOS = ((100.0, 40.0), (180.0, 40.0), (220.0, 40.0), (140.0, 40.0))
OJO_A = 90.0                            # el ojo azul, encima del centro
ANCHO_OJO = 30.0                        # sin «al terminar»: sitio para el ojo
ICONO = 15.0


class Gajo:
    """Un hueco del rosco: se usa como los rectángulos del submenú
    rectangular (``contains``, ``center``) y sabe su forma para dibujarse."""

    def __init__(self, c: QPointF, r0: float, r1: float, a0: float, barrido: float) -> None:
        self.path = sector(c, r0, r1, a0 + HUECO_GRADOS / 2.0, barrido - HUECO_GRADOS, 5.0)
        self._centro = _pt(c, (r0 + r1) / 2.0, a0 + barrido / 2.0)

    def contains(self, p) -> bool:
        return self.path.contains(QPointF(p))

    def center(self) -> QPointF:
        return QPointF(self._centro)


def radios(con_lados: bool, con_final: bool, f: float = 1.0) -> tuple:
    """(centro, modos fuera, finales fuera, del centro al borde izquierdo de
    la caja, alto de la caja). El ancho es ``izquierda + modos fuera``."""
    rh = (RH_LADOS if con_lados else RH) * f
    r1 = rh + HUECO_PX + ANCHO_MODOS * f
    r3 = r1 + HUECO_PX + ANCHO_FINALES * f if con_final else r1
    arriba = max(r3, r1 + HUECO_PX + ANCHO_OJO * f)       # hasta encima del ojo
    return rh, r1, r3, r3, arriba + r3


def geometria(x0: float, y0: float, n: int, con_lados: bool, con_final: bool,
              f: float = 1.0) -> dict:
    """El rosco con su caja arriba a la izquierda en ``(x0, y0)``."""
    rh, r1, r3, izquierda, alto = radios(con_lados, con_final, f)
    c = QPointF(x0 + izquierda, y0 + alto - r3)           # el ojo queda encima
    r0 = rh + HUECO_PX
    paso = 360.0 / max(1, n)
    # El ojo: en medio de «al terminar» o, sin él, pegado a los modos.
    r_ojo = (r1 + HUECO_PX + r3) / 2.0 if con_final else r1 + HUECO_PX + ANCHO_OJO * f / 2.0
    g = {"radial": True, "centro": c, "rh": rh, "ojo": _pt(c, r_ojo, OJO_A),
         "marco": QRectF(x0, y0, izquierda + r1, alto),
         # Nombre arriba, flecha de volver abajo (y los lados en medio).
         "titulo": QRectF(c.x() - rh + 5.0, c.y() - rh + 6.0 * f, 2.0 * rh - 10.0,
                          (22.0 if con_lados else 26.0) * f),
         "volver": QRectF(c.x() - 9.0, c.y() + rh - 25.0 * f, 18.0, 18.0),
         # Lo mismo que el rectangular: (clave, hueco); aquí solo los huecos.
         "chips": [Gajo(c, r0, r1, 90.0 + paso / 2.0 - (i + 1) * paso, paso)
                   for i in range(n)]}
    if con_lados:
        lado = 18.0
        g["menos"] = QRectF(c.x() - 30.0 * f - lado / 2.0, c.y() - lado / 2.0 + 2.0, lado, lado)
        g["mas"] = QRectF(c.x() + 30.0 * f - lado / 2.0, c.y() - lado / 2.0 + 2.0, lado, lado)
    if con_final:
        r2 = r1 + HUECO_PX
        g["finales"] = [Gajo(c, r2, r3, a0, b) for a0, b in FIN_GAJOS]
    return g


# ---- Dibujo ------------------------------------------------------------------------

def _gajo(painter, gajo: Gajo, texto: str, activo: bool, color, icono, relieve: bool,
          e: float = 1.0) -> None:
    """Un gajo; ``e`` es el tamaño (iconos y textos crecen con él). Un
    texto con salto de línea va en dos renglones, con el icono más arriba."""
    from . import _iconos
    color = QColor(color) if color is not None else QColor(_flotante.ROJO)
    path = gajo.path
    if relieve:
        sombra(painter, path, 1.5, 2.0)
        caja = path.boundingRect()
        degradado = QLinearGradient(caja.topLeft(), caja.bottomLeft())
        degradado.setColorAt(0.0, QColor(255, 255, 255))
        degradado.setColorAt(1.0, QColor(196, 196, 189))
        # El activo, sin rayas (tapaban icono y texto): rosa liso y borde
        # rojo grueso.
        if activo:
            painter.setPen(QPen(color, 2.4))
            painter.setBrush(QBrush(QColor(252, 222, 222)))
        else:
            painter.setPen(QPen(QColor(150, 148, 140), 1.0))
            painter.setBrush(QBrush(degradado))
        painter.drawPath(path)
    else:
        fondo = QColor(color)
        fondo.setAlpha(45)
        painter.setPen(QPen(color if activo else QColor(180, 178, 169), 1.2 if activo else 1.0))
        painter.setBrush(QBrush(fondo if activo else QColor(255, 255, 255, 230)))
        painter.drawPath(path)
    q = gajo.center()
    renglones = texto.count("\n") + 1
    alto = 14.0 * e * renglones
    sube = 5.0 * e * (renglones - 1)
    painter.setPen(color.darker(140) if activo else QColor(68, 68, 65))
    negrita = relieve and activo
    if negrita:
        painter.setPen(QColor(140, 20, 20))
        fuente = QFont(painter.font())
        fuente.setBold(True)
        painter.setFont(fuente)
    if icono is not None and _iconos.tiene(icono):
        if relieve:                          # iconos más grandes (Relieve 3D)
            ic = QPointF(q.x(), q.y() - 9.0 * e - sube)
            _iconos.pintar(painter, icono, ic, ICONO * e * 1.35)
            caja = QRectF(q.x() - 40.0 * e, q.y() + 3.0 * e - sube, 80.0 * e, alto)
        else:
            ic = QPointF(q.x(), q.y() - 7.0 * e - sube)
            _iconos.pintar(painter, icono, ic, ICONO * e)
            caja = QRectF(q.x() - 40.0 * e, q.y() + 2.0 * e - sube, 80.0 * e, alto)
        painter.drawText(caja, Qt.AlignCenter, _tr(texto))
    else:
        painter.drawText(QRectF(q.x() - 40.0 * e, q.y() - alto / 2.0, 80.0 * e, alto),
                         Qt.AlignCenter, _tr(texto))
    if negrita:
        fuente = QFont(painter.font())
        fuente.setBold(False)
        painter.setFont(fuente)


def pintar(painter, g: dict, titulo: str, modos, finales, lados, relieve: bool,
           tinta: QColor, volver) -> None:
    """``modos`` y ``finales``: [(texto, activo, color, icono)] en el orden
    de los gajos; ``lados``: el número (o None); ``volver(painter, centro)``
    dibuja la flecha de volver."""
    c, rh = g["centro"], g["rh"]
    e = g.get("e", 1.0)                 # el tamaño del rosco (Opciones)
    f = QFont(painter.font())
    f.setPointSizeF(8.0 * e)
    f.setBold(False)
    painter.setFont(f)
    for (_k, gajo), (texto, activo, color, icono) in zip(g["chips"], modos):
        _gajo(painter, gajo, texto, activo, color, icono, relieve, e)
    for (_k, gajo), (texto, activo, color, icono) in zip(g.get("finales", ()), finales):
        _gajo(painter, gajo, texto, activo, color, icono, relieve, e)
    # El centro: un disco blanco con el contorno de la barra.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
    painter.drawEllipse(c, rh, rh)
    for color, ancho in ((_flotante.HALO, 3.4), (_flotante.ROJO, 1.6)):
        painter.setPen(QPen(color, ancho))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(c, rh, rh)
    f.setBold(True)
    painter.setFont(f)
    painter.setPen(tinta)
    painter.drawText(g["titulo"], Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap, _tr(titulo))
    f.setBold(False)
    painter.setFont(f)
    if lados is not None and "menos" in g:
        for clave, signo in (("menos", "−"), ("mas", "+")):
            r = g[clave]
            painter.setPen(QPen(QColor(150, 148, 140), 1.0))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(r)
            painter.setPen(QColor(68, 68, 65))
            painter.drawText(r, Qt.AlignCenter, _tr(signo))
        valor = QRectF(g["menos"].right(), g["menos"].top(),
                       g["mas"].left() - g["menos"].right(), g["menos"].height())
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(tinta)
        painter.drawText(valor, Qt.AlignCenter, _tr(str(lados)))
        f.setBold(False)
        painter.setFont(f)
    volver(painter, g["volver"].center())

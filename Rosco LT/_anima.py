# SPDX-License-Identifier: GPL-3.0-or-later
"""La pantallita animada de la ayuda: una escena por gesto del ratón.

``pintar(painter, caja, escena, k)`` dibuja la escena en ``caja`` en el instante
``k`` (de 0 a 1). Todo va en una rejilla de ANCHO × ALTO, escalada a la caja.
"""
from __future__ import annotations


import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF

from ._idioma import _tr

ANCHO, ALTO = 410.0, 130.0
DURACION_S = 2.6
_FONDO = QColor(228, 228, 224)
_TINTA = QColor(91, 91, 214)
_OSCURA = QColor(75, 58, 168)
_ROJO = QColor(214, 34, 34)
_VERDE = QColor(46, 155, 62)
_NEGRO = QColor(17, 17, 17)
_LINEA = ((50.0, 95.0), (120.0, 50.0), (190.0, 85.0), (250.0, 45.0))
_OBJETO = QRectF(255.0, 35.0, 90.0, 60.0)


def _mover(k, a, b, hasta):
    u = min(1.0, max(0.0, k / hasta))
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u


def _objeto(p, marcado: bool = False) -> None:
    p.setPen(QPen(_OSCURA if marcado else QColor(85, 85, 85), 2.0 if marcado else 1.2))
    p.setBrush(QBrush(QColor(183, 178, 238) if marcado else QColor(207, 211, 220)))
    p.drawRect(_OBJETO)


def _rosco(p, x, y, opaco: float = 1.0, escala: float = 1.0) -> None:
    p.save()
    p.setOpacity(opaco)
    p.translate(x, y)
    p.scale(escala, escala)
    p.setPen(QPen(_TINTA, 1.5))
    p.setBrush(QBrush(QColor(255, 255, 255)))
    p.drawEllipse(QPointF(0.0, 0.0), 42.0, 42.0)
    p.setPen(QPen(QColor(199, 195, 234), 1.0))
    for a in range(8):
        r = a * math.pi / 4.0
        p.drawLine(QPointF(15.0 * math.cos(r), 15.0 * math.sin(r)),
                   QPointF(42.0 * math.cos(r), 42.0 * math.sin(r)))
    p.setPen(QPen(_TINTA, 1.0))
    p.setBrush(QBrush(_FONDO))
    p.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
    p.restore()


def _cursor(p, x, y, lapiz: bool = False) -> None:
    p.save()
    p.translate(x, y)
    if lapiz:
        p.rotate(-45.0)
        p.setPen(QPen(_NEGRO, 1.2))
        p.setBrush(QBrush(QColor(245, 197, 24)))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(8, -5), QPointF(28, -5), QPointF(28, 5), QPointF(8, 5)]))
        p.setBrush(QBrush(QColor(228, 190, 138)))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(8, -5), QPointF(8, 5)]))
    else:
        p.setPen(QPen(QColor(255, 255, 255), 1.0))
        p.setBrush(QBrush(_NEGRO))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(0, 15), QPointF(4, 11), QPointF(7, 18),
                                 QPointF(10, 17), QPointF(7, 10), QPointF(12, 10)]))
    p.restore()


def _pulso(p, x, y, u, color) -> None:
    if not 0.0 < u < 1.0:
        return
    p.save()
    p.setOpacity(1.0 - u)
    p.setPen(QPen(color, 2.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(x, y), 4.0 + 16.0 * u, 4.0 + 16.0 * u)
    p.restore()


def _clic(p, k, x, y, t0, color, doble: bool = False) -> None:
    _pulso(p, x, y, (k - t0) / 0.14, color)
    if doble:
        _pulso(p, x, y, (k - t0 - 0.1) / 0.14, color)


def _linea(p, n: int, goma=None) -> None:
    p.setPen(QPen(QColor(34, 34, 34), 2.0))
    for a in range(n):
        p.drawLine(QPointF(*_LINEA[a]), QPointF(*_LINEA[a + 1]))
    if goma is not None:
        lapiz = QPen(_OSCURA, 1.2, Qt.DashLine)
        p.setPen(lapiz)
        p.drawLine(QPointF(*_LINEA[n]), QPointF(*goma))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_OSCURA))
    for a in range(n + 1):
        p.drawEllipse(QPointF(*_LINEA[a]), 3.0, 3.0)


def _rotulo(p, texto, color=_OSCURA) -> None:
    p.setPen(color)
    p.drawText(QRectF(14.0, 112.0, ANCHO - 28.0, 16.0), Qt.AlignLeft | Qt.AlignVCenter, texto)


# ---- Las escenas ---------------------------------------------------------------------
def vacio(p, k):
    x, y = _mover(k, (20.0, 20.0), (120.0, 70.0), 0.3)
    _objeto(p)
    if k > 0.45:
        _rosco(p, 120.0, 70.0, min(1.0, (k - 0.45) / 0.1))
    _clic(p, k, 120.0, 70.0, 0.35, _TINTA)
    _cursor(p, x, y)


def objeto(p, k):
    x, y = _mover(k, (150.0, 110.0), (300.0, 65.0), 0.3)
    _objeto(p, k > 0.4)
    if k > 0.4:
        _rosco(p, 300.0, 65.0, 0.25)
    _clic(p, k, 300.0, 65.0, 0.35, _TINTA)
    _cursor(p, x, y)


def repite(p, k):
    x, y = _mover(k, (20.0, 20.0), (120.0, 90.0), 0.3)
    _objeto(p)
    if k > 0.5:
        _rotulo(p, _tr("Línea (última orden)"))
    _clic(p, k, 120.0, 90.0, 0.35, _TINTA, doble=True)
    _cursor(p, x, y, k > 0.5)


def alterna(p, k):
    _objeto(p)
    if k < 0.3 or k > 0.72:
        _rosco(p, 120.0, 65.0)
    _clic(p, k, 120.0, 65.0, 0.26, _ROJO)
    _clic(p, k, 120.0, 65.0, 0.68, _ROJO)
    _cursor(p, 120.0, 65.0)


def menu(p, k):
    x, y = _mover(k, (150.0, 110.0), (300.0, 60.0), 0.3)
    _objeto(p)
    _clic(p, k, 300.0, 60.0, 0.35, _ROJO)
    if k > 0.45:
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(43, 43, 43)))
        p.drawRoundedRect(QRectF(308.0, 66.0, 94.0, 58.0), 4.0, 4.0)
        p.setPen(QColor(238, 238, 238))
        for i, t in enumerate(("Info de entidad", "Ocultar", "Bloquear")):
            p.drawText(QRectF(314.0, 69.0 + i * 17.0, 86.0, 16.0), Qt.AlignLeft | Qt.AlignVCenter, _tr(t))
    _cursor(p, x, y)


def deshace(p, k):
    if k < 0.45:
        _objeto(p)
    _clic(p, k, 120.0, 65.0, 0.35, _ROJO, doble=True)
    if k > 0.5:
        _rotulo(p, _tr("Deshecho"))
    _cursor(p, 120.0, 65.0)


def boton(p, k):
    x, y = _mover(k, (120.0, 70.0), (150.0, 48.0), 0.3)
    _objeto(p)
    if k < 0.45:
        _rosco(p, 120.0, 70.0)
    else:
        _rosco(p, 120.0, 70.0, min(1.0, (k - 0.45) / 0.1), 0.8)
        p.setPen(QColor(45, 36, 112))
        p.drawText(QRectF(70.0, 106.0, 100.0, 16.0), Qt.AlignCenter, _tr("Línea"))
    _clic(p, k, 150.0, 48.0, 0.35, _TINTA)
    _cursor(p, x, y)


def pulsado(p, k):
    pulsa = 0.25 < k < 0.72
    x, y = (150.0, 48.0) if k < 0.25 else _mover(k - 0.25, (150.0, 48.0), (300.0, 80.0), 0.4)
    _objeto(p)
    if k < 0.72:
        _rosco(p, 120.0, 70.0, 0.12 if pulsa else 1.0)
    else:
        _rosco(p, 300.0, 80.0)
    if pulsa:
        p.setPen(QPen(_TINTA, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, y), 9.0, 9.0)
    _cursor(p, x, y)


def punto(p, k):
    if k < 0.45:
        n = 1
        x, y = _mover(k, (150.0, 100.0), (190.0, 85.0), 0.35)
    else:
        n = 2
        x, y = _mover(k - 0.5, (190.0, 85.0), (230.0, 60.0), 0.3)
    _linea(p, n, (x, y))
    _clic(p, k, 190.0, 85.0, 0.4, _TINTA)
    _cursor(p, x, y, True)


def cancela(p, k):
    if k < 0.5:
        _linea(p, 2, (240.0, 60.0))
    _clic(p, k, 240.0, 60.0, 0.42, _TINTA, doble=True)
    if k > 0.55:
        _rotulo(p, _tr("Cancelado: se descarta lo que estaba a medias"), _ROJO)
    _cursor(p, 240.0, 60.0, k < 0.5)


def termina(p, k):
    _linea(p, 2, (240.0, 60.0) if k < 0.45 else None)
    _clic(p, k, 240.0, 60.0, 0.38, _ROJO)
    if k > 0.5:
        _rotulo(p, _tr("Terminada: se conserva"), _VERDE)
    _cursor(p, 240.0, 60.0, k < 0.5)


def atras(p, k):
    _linea(p, 2 if k < 0.45 else 1, (240.0, 60.0))
    _clic(p, k, 240.0, 60.0, 0.38, _ROJO, doble=True)
    if k > 0.5:
        _rotulo(p, _tr("Un paso atrás: la orden sigue"))
    _cursor(p, 240.0, 60.0, True)


ESCENAS = {"vacio": vacio, "objeto": objeto, "repite": repite, "alterna": alterna, "menu": menu,
           "deshace": deshace, "boton": boton, "pulsado": pulsado, "punto": punto,
           "cancela": cancela, "termina": termina, "atras": atras}


def pintar(painter, caja: QRectF, escena: str, k: float) -> None:
    """La escena en ``caja``, en el instante ``k`` (0–1), con su marco."""
    p = painter
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(189, 186, 179), 1.0))
    p.setBrush(QBrush(_FONDO))
    p.drawRoundedRect(caja, 5.0, 5.0)
    p.setClipRect(caja.adjusted(1.0, 1.0, -1.0, -1.0))
    p.translate(caja.left(), caja.top())
    p.scale(caja.width() / ANCHO, caja.height() / ALTO)
    f = QFont(p.font())
    f.setPointSizeF(7.5)
    f.setBold(False)
    p.setFont(f)
    fn = ESCENAS.get(escena)
    if fn is not None:
        fn(p, k)
    p.restore()

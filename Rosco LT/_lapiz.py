# SPDX-License-Identifier: GPL-3.0-or-later
"""El cursor de Rosco LT: un lápiz amarillo con la forma de la herramienta
junto a la punta (rectángulo, polígono, arco, círculo, línea, seleccionar,
medir, altura). Borrar no lleva lápiz sino una goma. La punta es el punto
activo del cursor.

Contorno negro grueso y halo blanco: se lee sobre cualquier fondo. Sin
píxeles semitransparentes (en Windows saldrían oscuros).
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)

NEGRO = QColor(17, 17, 17)
BLANCO = QColor(255, 255, 255)
AMARILLO = QColor(245, 197, 24)
MADERA = QColor(228, 190, 138)
MINA = QColor(42, 94, 168)
GOMA = QColor(229, 57, 53)
ROJO = QColor(214, 34, 34)

ANCHO, ALTO = 52, 54
PUNTA = QPointF(12.0, 30.0)          # el punto activo (hay sitio a su izquierda para la línea)

_CACHE: dict = {}

# Sin ninguna orden del rosco activa (en espera), el lápiz va en grises.
GRISES = {"negro": QColor(85, 85, 85), "amarillo": QColor(185, 185, 185),
          "madera": QColor(214, 214, 214), "mina": QColor(119, 119, 119),
          "goma": QColor(154, 154, 154)}


def _lapiz(p: QPainter, gris: bool = False) -> None:
    """El lápiz en zigzag, con la punta en (0, 0) y el cuerpo hacia arriba a
    la derecha (como el de la imagen de referencia). ``gris``: en grises."""
    negro = GRISES["negro"] if gris else NEGRO
    p.save()
    p.rotate(-45.0)
    p.scale(0.62, 0.62)
    lapiz = QPen(negro, 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(lapiz)
    p.setBrush(QBrush(GRISES["madera"] if gris else MADERA))
    p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(9, -7), QPointF(9, 7)]))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(GRISES["mina"] if gris else MINA))
    p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(3.4, -2.6), QPointF(3.4, 2.6)]))
    p.setPen(lapiz)
    p.setBrush(QBrush(GRISES["amarillo"] if gris else AMARILLO))
    cuerpo = [(9, -7), (24, -7), (20, -12), (36, -12), (32, -7), (47, -7), (47, 7),
              (32, 7), (36, 12), (20, 12), (24, 7), (9, 7)]
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in cuerpo]))
    p.setPen(QPen(negro, 1.3))
    for y in (-3.0, 1.0):
        p.drawLine(QPointF(12, y), QPointF(44, y))
    p.setPen(QPen(negro, 2.4))
    p.setBrush(QBrush(GRISES["madera"] if gris else MADERA))
    p.drawRect(QRectF(47, -7, 6, 14))
    p.setPen(QPen(negro, 2.6))
    p.setBrush(QBrush(GRISES["goma"] if gris else GOMA))
    p.drawRoundedRect(QRectF(53, -7, 9, 14), 2.5, 2.5)
    p.restore()


def _goma(p: QPainter) -> None:
    """La goma de borrar inclinada, con la esquina que borra en (0, 0): la
    punta roja, la funda azul y el cuerpo blanco, y una raya de lo borrado."""
    p.save()
    p.setPen(QPen(ROJO, 2.2, Qt.DashLine))
    p.drawLine(QPointF(-10.0, 4.0), QPointF(0.0, 4.0))
    p.rotate(-45.0)
    contorno = QPen(NEGRO, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    halo = QPen(BLANCO, 5.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    cuerpo = QRectF(0.0, -7.0, 30.0, 14.0)
    p.setPen(halo)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(cuerpo, 3.0, 3.0)
    p.setPen(contorno)
    p.setBrush(QBrush(BLANCO))
    p.drawRoundedRect(cuerpo, 3.0, 3.0)
    p.setBrush(QBrush(GOMA))
    p.drawRoundedRect(QRectF(0.0, -7.0, 11.0, 14.0), 3.0, 3.0)
    p.setBrush(QBrush(MINA))
    p.drawRect(QRectF(11.0, -7.0, 8.0, 14.0))
    p.restore()


def _estrella(c: QPointF, r_ext: float, r_int: float) -> QPainterPath:
    """Estrella de cinco puntas centrada en ``c``, con una punta arriba."""
    puntos = []
    for i in range(10):
        r = r_ext if i % 2 == 0 else r_int
        a = math.radians(90.0 + i * 36.0)
        puntos.append(QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(puntos))
    path.closeSubpath()
    return path


def _forma(p: QPainter, forma: str) -> None:
    """La forma de la herramienta, junto a la punta (en (0, 0)), con halo."""
    trazo = QPainterPath()
    relleno = QPainterPath()
    if forma == "rect":
        trazo.addRect(QRectF(-2, 4, 20, 13))
    elif forma == "poly":
        trazo.addPolygon(QPolygonF([QPointF(6, 4), QPointF(16, 4), QPointF(21, 12),
                                    QPointF(16, 20), QPointF(6, 20), QPointF(1, 12)]))
        trazo.closeSubpath()
    elif forma == "arco":
        trazo.arcMoveTo(QRectF(-1, 7, 22, 22), 180.0)
        trazo.arcTo(QRectF(-1, 7, 22, 22), 180.0, -180.0)
    elif forma == "circulo":
        trazo.addEllipse(QPointF(10, 12), 8.5, 8.5)
    elif forma == "linea":
        # Una estrellita roja pegada a la punta, sin halo.
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(ROJO))
        p.drawPath(_estrella(QPointF(-3.3, 3.3), 4.8, 2.0))
        p.restore()
        return
    elif forma == "borrar":
        trazo.moveTo(2, 14)
        trazo.lineTo(20, 14)
    elif forma == "seleccionar":
        for x0, y0, x1, y1 in ((-2, 4, 18, 4), (18, 4, 18, 18), (18, 18, -2, 18), (-2, 18, -2, 4)):
            for k in range(3):
                t0, t1 = k / 3.0, k / 3.0 + 0.2
                trazo.moveTo(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0)
                trazo.lineTo(x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)
    elif forma == "medir":
        trazo.moveTo(2, 18)
        trazo.lineTo(20, 18)
        for x in (2, 8, 14, 20):
            trazo.moveTo(x, 18)
            trazo.lineTo(x, 12 if x in (2, 14) else 14)
    elif forma == "altura":
        trazo.moveTo(10, 22)
        trazo.lineTo(10, 8)
        relleno.addPolygon(QPolygonF([QPointF(5, 10), QPointF(10, 3), QPointF(15, 10)]))
        relleno.closeSubpath()
    else:
        return
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(BLANCO, 4.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(trazo)
    p.setPen(QPen(NEGRO, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(trazo)
    if not relleno.isEmpty():
        p.setPen(QPen(BLANCO, 1.5))
        p.setBrush(QBrush(NEGRO))
        p.drawPath(relleno)
    if forma == "borrar":
        p.setPen(QPen(ROJO, 2.2, Qt.DashLine))
        p.drawLine(QPointF(6, 18), QPointF(18, 6))
    p.restore()


def pixmap(forma: str, dpr: float = 1.0) -> QPixmap:
    pm = QPixmap(int(math.ceil(ANCHO * dpr)), int(math.ceil(ALTO * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(PUNTA)
        if forma == "borrar":
            _goma(p)
        else:
            _forma(p, forma)
            _lapiz(p, gris=not forma)    # sin forma: ninguna orden del rosco activa
    finally:
        p.end()
    return pm


def cursor(forma: str, dpr: float = 1.0) -> QCursor:
    """El cursor lápiz de ``forma`` (o el lápiz solo), con el punto activo en
    la punta."""
    clave = (forma, round(dpr, 2))
    cur = _CACHE.get(clave)
    if cur is None:
        cur = _CACHE[clave] = QCursor(pixmap(forma, dpr), int(PUNTA.x()), int(PUNTA.y()))
    return cur

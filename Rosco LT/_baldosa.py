# SPDX-License-Identifier: GPL-3.0-or-later
"""Los botones de la barra «Rosco LT» en baldosa: cuadrado de esquinas
redondeadas con un degradado de abajo arriba (turquesa → azul → azul
marino casi negro), borde azul noche, bisel claro arriba y oscuro abajo y
brillo en la mitad de arriba. Encima, el dibujo del botón pasado a azules:
lo oscuro (las líneas) en casi blanco y lo de color en azul traslúcido, con
un halo azul claro. Solo esos botones: ni los de IngeTrazo ni los del anillo.

``icono(dibujo, detalles)`` da el QIcon con todos los tamaños: Normal (y
On) en azul, Active (ratón encima) más claro, Disabled (y Off) en gris.
``dibujo(px)`` y ``detalles(px)`` devuelven una QImage cuadrada de ``px``
con el dibujo en tinta negra; los ``detalles`` van encima tal cual, sin
recolorear (los ojos y la boca del arquitecto, en negro)."""
from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)

TAMANOS = (16, 20, 24, 28, 32, 36, 40, 48, 64, 96)

# El degradado de la baldosa, de abajo (0) arriba (1).
FONDO = ((0.0, "#24b8cc"), (0.10, "#0898b4"), (0.21, "#0666ae"), (0.35, "#020c40"),
         (1.0, "#000312"))
FONDO_BAJO = ((0.0, "#48cede"), (0.10, "#18b0ca"), (0.21, "#0c7cc4"), (0.35, "#031654"),
              (1.0, "#010520"))
FONDO_GRIS = ((0.0, "#5f7882"), (1.0, "#34454d"))
BORDE = "#010c26"
# El dibujo: (relleno, tinta arriba, tinta abajo).
AZULES = ("#3fb0f5", "#f2fbff", "#8fd3ff")
GRISES = ("#7d8f99", "#c9d3d9", "#93a3ad")
HALO = QColor(143, 227, 255)
LADO_DIBUJO = 36.5 / 48.0              # el dibujo ocupa el 76 % de la baldosa


def svg(texto: str, px: int) -> QImage:
    """Un SVG a una QImage de ``px`` (transparente si falla)."""
    from PySide6.QtSvg import QSvgRenderer
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    render = QSvgRenderer(QByteArray(texto.encode("utf-8")))
    if render.isValid():
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        render.render(p, QRectF(0, 0, px, px))
        p.end()
    return img


def _mezcla(a: QColor, b: QColor, t: float) -> tuple:
    return (a.red() + (b.red() - a.red()) * t, a.green() + (b.green() - a.green()) * t,
            a.blue() + (b.blue() - a.blue()) * t)


def _recolorear(img: QImage, gris: bool) -> QImage:
    """Lo oscuro pasa a la tinta clara (degradada de arriba abajo) y lo de
    color al azul de relleno, algo traslúcido."""
    relleno, arriba, abajo = (QColor(c) for c in (GRISES if gris else AZULES))
    img = img.convertToFormat(QImage.Format_ARGB32)
    h, w = img.height(), img.width()
    for y in range(h):
        tinta = QColor.fromRgbF(*(v / 255.0 for v in _mezcla(arriba, abajo, y / max(1, h - 1))))
        for x in range(w):
            c = img.pixelColor(x, y)
            a = c.alpha()
            if not a:
                continue
            luz = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0
            t = max(0.0, min(1.0, (1.0 - luz) * 1.25))
            r, g, b = _mezcla(relleno, tinta, t)
            img.setPixelColor(x, y, QColor(round(r), round(g), round(b), round(a * (0.6 + 0.4 * t))))
    return img


def _redondo(x, y, lado, radio) -> QPainterPath:
    camino = QPainterPath()
    camino.addRoundedRect(QRectF(x, y, lado, lado), radio, radio)
    return camino


def _baldosa(p: QPainter, n: int, paradas) -> None:
    u = n / 48.0
    caja = _redondo(1 * u, 1 * u, 46 * u, 10.5 * u)
    fondo = QLinearGradient(QPointF(0, 47 * u), QPointF(0, 1 * u))
    for o, c in paradas:
        fondo.setColorAt(o, QColor(c))
    p.fillPath(caja, QBrush(fondo))
    p.strokePath(caja, QPen(QColor(BORDE), 1.2 * u))
    bisel = QLinearGradient(QPointF(0, 2.2 * u), QPointF(0, 45.8 * u))
    bisel.setColorAt(0.0, QColor(127, 227, 240, 217))
    bisel.setColorAt(0.5, QColor(127, 227, 240, 0))
    bisel.setColorAt(0.5001, QColor(0, 8, 20, 0))
    bisel.setColorAt(1.0, QColor(0, 8, 20, 140))
    p.strokePath(_redondo(2.2 * u, 2.2 * u, 43.6 * u, 9.5 * u), QPen(QBrush(bisel), 1.4 * u))
    brillo = QPainterPath()
    brillo.moveTo(2.6 * u, 12 * u)
    brillo.quadTo(2.6 * u, 2.6 * u, 12 * u, 2.6 * u)
    brillo.lineTo(36 * u, 2.6 * u)
    brillo.quadTo(45.4 * u, 2.6 * u, 45.4 * u, 12 * u)
    brillo.lineTo(45.4 * u, 20 * u)
    brillo.quadTo(24 * u, 27 * u, 2.6 * u, 20 * u)
    brillo.closeSubpath()
    luz = QLinearGradient(QPointF(0, 2.6 * u), QPointF(0, 24 * u))
    luz.setColorAt(0.0, QColor(255, 255, 255, 56))
    luz.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(brillo, QBrush(luz))


def _halo(p: QPainter, dibujo: QImage, x: float, y: float, radio: float) -> None:
    """Un brillo azul claro alrededor del dibujo (copias de su silueta en
    corro, muy tenues)."""
    silueta = QImage(dibujo.convertToFormat(QImage.Format_ARGB32_Premultiplied))
    q = QPainter(silueta)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(silueta.rect(), HALO)
    q.end()
    p.save()
    for anillo, opacidad in ((radio, 0.16), (radio * 0.5, 0.22)):
        p.setOpacity(opacidad)
        for k in range(12):
            a = k / 12.0 * 2.0 * math.pi
            p.drawImage(QPointF(x + anillo * math.cos(a), y + anillo * math.sin(a)), silueta)
    p.restore()


def _pixmap(n: int, paradas, dibujo: QImage, detalles: QImage | None, gris: bool) -> QPixmap:
    img = QImage(n, n, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    _baldosa(p, n, paradas)
    o = (n - dibujo.width()) / 2.0
    if not gris:
        _halo(p, dibujo, o, o, max(0.6, 1.1 * n / 48.0))
    p.drawImage(QPointF(o, o), dibujo)
    if detalles is not None:
        p.drawImage(QPointF(o, o), detalles)
    p.end()
    return QPixmap.fromImage(img)


def icono(dibujo, detalles=None, off_gris: bool = False, colores: bool = False) -> QIcon:
    """El QIcon en baldosa (ver el principio del archivo). ``off_gris``:
    un botón de casilla (el interruptor) sin marcar va en gris. ``colores``:
    el dibujo va con sus colores, sin pasarlo a azules (la diana del rosco)."""
    resultado = QIcon()
    for n in TAMANOS:
        lado = max(4, round(n * LADO_DIBUJO))
        fuente = dibujo(lado)
        encima = detalles(lado) if detalles is not None else None
        azul = fuente.convertToFormat(QImage.Format_ARGB32) if colores else _recolorear(fuente, False)
        gris = _recolorear(fuente, True)
        normal = _pixmap(n, FONDO, azul, encima, False)
        bajo = _pixmap(n, FONDO_BAJO, azul, encima, False)
        apagado = _pixmap(n, FONDO_GRIS, gris, encima, True)
        for estado in (QIcon.State.On, QIcon.State.Off):
            gris_aqui = off_gris and estado == QIcon.State.Off
            resultado.addPixmap(apagado if gris_aqui else normal, QIcon.Mode.Normal, estado)
            resultado.addPixmap(apagado if gris_aqui else bajo, QIcon.Mode.Active, estado)
            resultado.addPixmap(apagado, QIcon.Mode.Disabled, estado)
            resultado.addPixmap(apagado if gris_aqui else normal, QIcon.Mode.Selected, estado)
    return resultado

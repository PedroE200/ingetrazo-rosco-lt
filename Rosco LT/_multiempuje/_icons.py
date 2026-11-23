# SPDX-License-Identifier: GPL-3.0-or-later
"""Iconos de Multiempuje dibujados con QPainter: un cubo isométrico al que se le empuja una
cara (resultado naranja, bordes nuevos azules). Un icono «principal» para el cursor, el menú y
la pestaña, y una variante por modo para la barra y el panel. También el cursor único de la
herramienta, con una pequeña marca de estado arriba a la derecha."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

LINE = QColor(28, 30, 36)
TOP = QColor(214, 216, 222)
LEFT = QColor(150, 154, 164)
RIGHT = QColor(108, 112, 124)
ACC = QColor(232, 140, 48)
ACC_FILL = QColor(232, 140, 48, 120)
ACC_SOFT = QColor(232, 140, 48, 60)
NEW = QColor(110, 190, 255)
VERDE = QColor(80, 200, 110)
AZUL = QColor(90, 150, 255)
ROJO = QColor(230, 70, 60)
AMAR = QColor(240, 200, 80)
BLANCO = QColor(250, 250, 250)

# cubo isométrico en un espacio de diseño de 100 × 100
T, UR, LR, B, LL, UL, C = (50, 12), (84, 31), (84, 69), (50, 88), (16, 69), (16, 31), (50, 50)
D = 16.0                      # desplazamiento del empuje
NR = (0.87, 0.5)              # normal (en el dibujo) de la cara derecha
NT = (0.0, -1.0)              # normal de la cara superior
CARA_TOP = [T, UR, C, UL]
CARA_DER = [C, UR, LR, B]
CARA_IZQ = [UL, C, B, LL]


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


class _Dib:
    def __init__(self, p: QPainter, ox: float, oy: float, k: float, w: float):
        self.p, self.ox, self.oy, self.k, self.w = p, ox, oy, k, w

    def t(self, q):
        return QPointF(self.ox + q[0] * self.k, self.oy + q[1] * self.k)

    def poly(self, pts, fill=None, pen=None, dash=False):
        if pen is None:
            pen = QPen(LINE, self.w, Qt.DashLine if dash else Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.p.setPen(pen)
        self.p.setBrush(QBrush(fill) if fill is not None else Qt.NoBrush)
        self.p.drawPolygon(QPolygonF([self.t(q) for q in pts]))

    def line(self, a, b, color, w=None, dash=False):
        self.p.setPen(QPen(color, w or self.w, Qt.DashLine if dash else Qt.SolidLine, Qt.RoundCap))
        self.p.drawLine(self.t(a), self.t(b))

    def arrow(self, a, b, color, w=None):
        self.line(a, b, color, w)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        for d in (ang + 2.5, ang - 2.5):
            self.line(b, (b[0] + 9.0 * math.cos(d), b[1] + 9.0 * math.sin(d)), color, w)

    def cubo(self, dash_top=False):
        self.poly(CARA_IZQ, LEFT)
        self.poly(CARA_DER, RIGHT)
        self.poly(CARA_TOP, TOP, dash=dash_top)

    def losa(self, cara, n, d=D):
        """Cara desplazada según n·d con sus tiras laterales (bordes nuevos en azul)."""
        nueva = [_add(q, n, d) for q in cara]
        m = len(cara)
        for i in range(m):
            self.poly([cara[i], cara[(i + 1) % m], nueva[(i + 1) % m], nueva[i]], ACC_SOFT, QPen(NEW, self.w * 0.8))
        self.poly(nueva, ACC_FILL, QPen(ACC, self.w * 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        return nueva


def draw_cube(p: QPainter, key: str, ox: float, oy: float, k: float, w: float):
    """Dibuja el icono ``key`` («principal» o un modo) con origen (ox, oy) y escala k."""
    d = _Dib(p, ox, oy, k, w)
    if key == "principal":
        d.cubo(dash_top=True)
        nueva = d.losa(CARA_TOP, NT, D * 1.3)
        cen = ((nueva[0][0] + nueva[2][0]) / 2, (nueva[0][1] + nueva[2][1]) / 2)
        d.arrow(_add(cen, (0, 10)), _add(cen, (0, -26)), LINE, w * 1.3)
    elif key == "engrosar":
        d.cubo()
        d.losa(CARA_TOP, NT)
    elif key == "conjunto":
        d.cubo(dash_top=True)
        m = _add(NT, NR)                                  # inglete: la arista común se mueve por ambas
        nt = [_add(T, NT, D), _add(UR, m, D), _add(C, m, D), _add(UL, NT, D)]
        nr = [_add(C, m, D), _add(UR, m, D), _add(LR, NR, D), _add(B, NR, D)]
        for q, nq in zip(CARA_TOP, nt):
            d.line(q, nq, NEW, w * 0.8)
        for q, nq in zip(CARA_DER, nr):
            d.line(q, nq, NEW, w * 0.8)
        d.poly(nr, ACC_FILL, QPen(ACC, w * 1.1))
        d.poly(nt, ACC_FILL, QPen(ACC, w * 1.1))
    elif key == "redondeo":
        d.cubo()
        m = _add(NT, NR)
        nt = [_add(T, NT, D), _add(UR, NT, D), _add(C, m, D), _add(UL, NT, D)]
        nr = [_add(C, m, D), _add(UR, NR, D), _add(LR, NR, D), _add(B, NR, D)]
        path = QPainterPath(d.t(nt[3]))
        path.lineTo(d.t(nt[0]))
        path.lineTo(d.t(nt[1]))
        path.quadTo(d.t(_add(UR, m, D)), d.t(nr[1]))
        path.lineTo(d.t(nr[2]))
        path.lineTo(d.t(nr[3]))
        path.lineTo(d.t(nr[0]))
        path.closeSubpath()
        p.setPen(QPen(ACC, w * 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(ACC_FILL))
        p.drawPath(path)
        d.line(nt[3], UL, NEW, w * 0.8)
        d.line(nt[0], T, NEW, w * 0.8)
        d.line(nr[2], LR, NEW, w * 0.8)
        d.line(nr[3], B, NEW, w * 0.8)
    elif key == "vector":
        d.cubo(dash_top=True)
        v = (0.5, -0.85)
        d.losa(CARA_TOP, v, D * 1.2)
        d.arrow((88, 62), _add((88, 62), v, 34), AZUL, w * 1.4)
    elif key == "normal":
        d.cubo(dash_top=True)
        d.losa(CARA_DER, NR, D * 0.9)
        d.losa(CARA_TOP, NT, D * 0.9)
    elif key == "extruir":
        d.cubo(dash_top=True)
        v = (0.6, -0.55)
        nr = [_add(q, v, D) for q in CARA_DER]
        nt = [_add(q, v, D) for q in CARA_TOP]
        for q, nq in zip(CARA_TOP, nt):
            d.line(q, nq, NEW, w * 0.8)
        for q, nq in zip(CARA_DER, nr):
            d.line(q, nq, NEW, w * 0.8)
        d.poly(nr, ACC_FILL, QPen(ACC, w * 1.1))
        d.poly(nt, ACC_FILL, QPen(ACC, w * 1.1))
    elif key == "seguir":
        # paredes inclinadas (tronco de pirámide): la tapa sube siguiendo las paredes
        UL2, UR2, T2, C2 = (24, 36), (76, 36), (50, 21), (50, 51)
        d.poly([UL2, C2, B, LL], LEFT)
        d.poly([C2, UR2, LR, B], RIGHT)
        d.poly([T2, UR2, C2, UL2], TOP, dash=True)
        nt = [(50, 4), (68, 14), (50, 24), (32, 14)]
        for q, nq in zip([T2, UR2, C2, UL2], nt):
            d.line(q, nq, NEW, w * 0.8)
        d.poly(nt, ACC_FILL, QPen(ACC, w * 1.1))
    else:
        d.cubo()


def icon_pixmap(key: str, size: int = 64, pad: float = 0.06) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    k = size * (1 - 2 * pad) / 100.0
    draw_cube(p, key, size * pad, size * pad, k, max(1.0, 2.2 * size / 64))
    p.end()
    return pm


_ICONS = {}


def mode_icon(key: str, size: int = 64) -> QIcon:
    ck = (key, size)
    if ck not in _ICONS:
        _ICONS[ck] = QIcon(icon_pixmap(key, size))
    return _ICONS[ck]


# ------------------------------------------------------------------ cursor único
MARCAS = {"mas": VERDE, "ok": VERDE, "grupo": AMAR, "plano": AZUL, "direccion": ROJO}


def _marca(p: QPainter, marca: str, r: QRectF, k: float):
    p.setPen(QPen(LINE, 1.0 * k))
    p.setBrush(QBrush(MARCAS[marca]))
    p.drawEllipse(r)
    cx, cy, h = r.center().x(), r.center().y(), r.width() * 0.27
    pen = QPen(LINE, 1.4 * k, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if marca == "mas":
        p.drawLine(QPointF(cx - h, cy), QPointF(cx + h, cy))
        p.drawLine(QPointF(cx, cy - h), QPointF(cx, cy + h))
    elif marca == "ok":
        p.drawPolyline(QPolygonF([QPointF(cx - h, cy), QPointF(cx - h * 0.3, cy + h * 0.8), QPointF(cx + h, cy - h * 0.8)]))
    elif marca == "grupo":
        s = h * 1.1
        p.drawRect(QRectF(cx - s, cy - s * 0.4, s * 1.3, s * 1.3))
        p.drawRect(QRectF(cx - s * 0.3, cy - s, s * 1.3, s * 1.3))
    elif marca == "plano":
        s = h * 1.2
        p.drawPolygon(QPolygonF([QPointF(cx - s, cy + s * 0.5), QPointF(cx - s * 0.3, cy - s * 0.5),
                                 QPointF(cx + s, cy - s * 0.5), QPointF(cx + s * 0.3, cy + s * 0.5)]))
    elif marca == "direccion":
        p.drawLine(QPointF(cx - h, cy + h), QPointF(cx + h, cy - h))
        p.drawLine(QPointF(cx + h, cy - h), QPointF(cx + h * 0.1, cy - h))
        p.drawLine(QPointF(cx + h, cy - h), QPointF(cx + h, cy - h * 0.1))


def cursor_pixmap(marca: str | None = None, size: int = 32) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    k = size / 32
    p.drawPixmap(int(4 * k), int(4 * k), icon_pixmap("principal", int(28 * k)))
    # punto activo (arriba a la izquierda)
    p.setPen(QPen(LINE, 1.2 * k))
    p.setBrush(QBrush(BLANCO))
    p.drawEllipse(QRectF(0.5 * k, 0.5 * k, 5 * k, 5 * k))
    if marca in MARCAS:
        _marca(p, marca, QRectF(21 * k, 1 * k, 10 * k, 10 * k), k)
    p.end()
    return pm


_CURSORS = {}


def tool_cursor(marca: str | None = None) -> QCursor:
    """Cursor de la herramienta (punto activo en el círculo blanco de la esquina)."""
    if marca not in _CURSORS:
        _CURSORS[marca] = QCursor(cursor_pixmap(marca, 32), 3, 3)
    return _CURSORS[marca]

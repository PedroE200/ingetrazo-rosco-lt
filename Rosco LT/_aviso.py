# SPDX-License-Identifier: GPL-3.0-or-later
"""Un aviso pequeño, oscuro y sin botones (p. ej. «3 elementos → capa
«Muros»»): sale un momento junto al cajetín o al cursor y se va solo. No
coge el ratón ni el foco."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ._flotante import mover_a

DURA_MS = 2000
ALTO = 30
MUESTRA = 12                           # el cuadradito del color


class Aviso(QWidget):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._texto = ""
        self._color = None
        self._fuente = QFont(self.font())
        self._fuente.setPixelSize(12)
        self._reloj = QTimer(self)
        self._reloj.setSingleShot(True)
        self._reloj.timeout.connect(self.hide)

    def mostrar(self, texto: str, global_pos: QPoint, color=None, ms: int = DURA_MS) -> None:
        """``color``: ``(r, g, b)`` de 0 a 1 para el cuadradito, o None."""
        self._texto = texto
        self._color = color
        ancho = QFontMetrics(self._fuente).horizontalAdvance(texto) + (44 if color else 24)
        self.setFixedSize(ancho, ALTO)
        mover_a(self, global_pos)
        self.show()
        self.raise_()
        self.update()
        self._reloj.start(ms)

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(40, 40, 48, 235))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            x = 12.0
            if self._color is not None:
                r, g, b = (max(0, min(255, int(v * 255))) for v in self._color[:3])
                p.setBrush(QColor(r, g, b))
                p.setPen(QColor(255, 255, 255, 160))
                p.drawRect(QRectF(x, (ALTO - MUESTRA) / 2.0, MUESTRA, MUESTRA))
                x += MUESTRA + 8.0
            p.setPen(QColor(255, 255, 255))
            p.setFont(self._fuente)
            p.drawText(QRectF(x, 0, self.width() - x - 8.0, ALTO), Qt.AlignVCenter | Qt.AlignLeft, self._texto)
        finally:
            p.end()

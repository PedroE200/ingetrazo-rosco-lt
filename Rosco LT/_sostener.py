# SPDX-License-Identifier: GPL-3.0-or-later
"""El aro del clic derecho sostenido: rodea la punta del cursor y se va
llenando de rojo; lleno (``SOSTENER_MS``), al soltar sale el menú de IngeTrazo. Es una
ventanita transparente que no coge el ratón."""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ._flotante import mover_a

SOSTENER_MS = 500                      # lo que hay que sostener el derecho para el menú
R = 13.0                               # radio del aro
GRUESO = 3.5
LADO = 40


class AroSostener(QWidget):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(LADO, LADO)
        self._t0 = 0.0
        self._reloj = QTimer(self)
        self._reloj.setInterval(30)
        self._reloj.timeout.connect(self.update)

    def empezar(self, global_pos: QPoint) -> None:
        mover_a(self, global_pos.x() - LADO // 2, global_pos.y() - LADO // 2)
        self._t0 = time.monotonic()
        self.show()
        self.raise_()
        self._reloj.start()

    def lleno(self) -> None:
        """Lleno del todo y quieto, hasta que se suelte el botón."""
        self._t0 = time.monotonic() - SOSTENER_MS / 1000.0
        self._reloj.stop()
        self.update()

    def parar(self) -> None:
        self._reloj.stop()
        self.hide()

    def paintEvent(self, ev) -> None:  # noqa: N802
        frac = min(1.0, (time.monotonic() - self._t0) * 1000.0 / SOSTENER_MS)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            c = self.rect().center()
            caja = QRectF(c.x() - R + 0.5, c.y() - R + 0.5, 2 * R, 2 * R)
            p.setPen(QPen(QColor(255, 255, 255, 220), GRUESO + 3.0))
            p.drawEllipse(caja)
            p.setPen(QPen(QColor(205, 30, 40, 70), GRUESO))
            p.drawEllipse(caja)
            if frac > 0.0:
                p.setPen(QPen(QColor(205, 30, 40), GRUESO, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(caja, 90 * 16, int(-360 * 16 * frac))
        finally:
            p.end()

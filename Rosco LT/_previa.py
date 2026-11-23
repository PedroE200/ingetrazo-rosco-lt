# SPDX-License-Identifier: GPL-3.0-or-later
"""La vista previa del subrosco: al pararse sobre un botón del rosco que lo
tiene, su subrosco a tamaño real, en gris y pegado al botón. No se pulsa:
es una ventanita transparente al ratón, así que los clics llegan a los
botones de debajo, y al ir hacia otro botón desaparece."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ._flotante import mover_a

ESPERA_MS = 300                        # parado este tiempo sobre el botón: sale


def en_gris(img: QImage) -> QImage:
    """La imagen en grises, con su misma transparencia."""
    img = img.convertToFormat(QImage.Format_ARGB32)      # sin premultiplicar: las sombras no se ennegrecen
    alfa = img.convertToFormat(QImage.Format_Alpha8)
    gris = img.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_ARGB32)
    gris.setAlphaChannel(alfa)
    return gris


class VentanaPrevia(QWidget):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._pm = QPixmap()

    def mostrar(self, img: QImage, arriba_izq: QPoint) -> None:
        self._pm = QPixmap.fromImage(img)
        dpr = img.devicePixelRatio() or 1.0
        self.resize(int(img.width() / dpr) + 1, int(img.height() / dpr) + 1)
        mover_a(self, arriba_izq)
        self.show()
        self.raise_()
        self.update()

    def ocultar(self) -> None:
        if self.isVisible():
            self.hide()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.drawPixmap(0, 0, self._pm)
        finally:
            p.end()

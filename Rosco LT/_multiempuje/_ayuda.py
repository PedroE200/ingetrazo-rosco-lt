# SPDX-License-Identifier: GPL-3.0-or-later
"""Popups de ayuda con ilustración 3D: al dejar el ratón medio segundo sobre una opción del
panel aparece una tarjeta (título, imagen «antes → después» y una frase); con los desplegables
salen todas sus opciones en columna. Se cierra al salir o al hacer clic."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from . import _ilustra as IL

RETARDO_MS = 500
SEPARACION = 8


class Popup(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._labels = []

    def mostrar(self, claves, ancla: QRect, ancho=350):
        for lab in self._labels:
            lab.hide()
            self.layout().removeWidget(lab)
            lab.setParent(None)
            lab.deleteLater()
        self._labels = []
        if not claves:
            return
        compacto = len(claves) > 1
        for k in claves:
            lab = QLabel()
            lab.setPixmap(IL.tarjeta(k, ancho, 120 if compacto else 160))
            self.layout().addWidget(lab)
            self._labels.append(lab)
        self.adjustSize()
        self.move(self._posicion(ancla))
        self.show()

    def _posicion(self, ancla: QRect) -> QPoint:
        pantalla = QGuiApplication.screenAt(ancla.center()) or QGuiApplication.primaryScreen()
        area = pantalla.availableGeometry()
        w, h = self.sizeHint().width(), self.sizeHint().height()
        x = ancla.left() - w - SEPARACION
        if x < area.left():
            x = ancla.right() + SEPARACION
        if x + w > area.right():
            x = max(area.left(), area.right() - w)
        y = ancla.center().y() - h // 2
        y = max(area.top(), min(y, area.bottom() - h))
        return QPoint(x, y)


class Ayudas(QObject):
    """Filtro de eventos: ``registrar(widget, claves)`` asocia una o varias ilustraciones a un
    widget del panel. ``activas`` permite apagarlas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activas = True
        self._claves = {}
        self._popup = None
        self._pendiente = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(RETARDO_MS)
        self._timer.timeout.connect(self._abrir)

    def registrar(self, widget, claves):
        if isinstance(claves, str):
            claves = [claves]
        self._claves[widget] = list(claves)
        widget.installEventFilter(self)
        widget.destroyed.connect(lambda *_a, w=widget: self._claves.pop(w, None))

    def eventFilter(self, obj, ev):  # noqa: N802
        t = ev.type()
        if t == QEvent.Enter and self.activas and obj in self._claves:
            self._pendiente = obj
            self._timer.start()
        elif t in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Hide, QEvent.FocusOut, QEvent.Wheel):
            if obj is self._pendiente:
                self._pendiente = None
            self._timer.stop()
            self.cerrar()
        return False

    def _abrir(self):
        w = self._pendiente
        if w is None or not self.activas or not w.isVisible() or not w.underMouse():
            return
        if self._popup is None:
            self._popup = Popup()
        ancla = QRect(w.mapToGlobal(QPoint(0, 0)), w.size())
        # el ancla abarca el ancho de la pestaña: así el popup sale a su izquierda, no encima
        sa = w
        while sa is not None and not isinstance(sa, QScrollArea):
            sa = sa.parentWidget()
        if sa is not None:
            r = QRect(sa.mapToGlobal(QPoint(0, 0)), sa.size())
            ancla = QRect(r.left(), ancla.top(), r.width(), ancla.height())
        try:
            self._popup.mostrar(self._claves.get(w, []), ancla)
        except Exception:  # noqa: BLE001
            self.cerrar()

    def cerrar(self):
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()

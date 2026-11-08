# SPDX-License-Identifier: GPL-3.0-or-later
"""El desplegable Navegador: un espejo del panel Navegador de IngeTrazo.

Es otra copia del mismo panel (``views.outliner.OutlinerPanel``), en una
ventanita desplegable bajo la pastilla: el árbol de grupos y componentes a
cualquier profundidad, el filtro, el ojo, el candado, los planos de sección y
su menú contextual. Un clic selecciona en el modelo, un doble clic (o Enter)
abre el grupo para editarlo. Mientras está abierto se pone al día con cada
cambio del modelo. Se cierra al pinchar fuera, como cualquier desplegable.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QVBoxLayout

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

ANCHO, ALTO = 460, 420
ROJO = "#d62222"


class Navegador:
    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.ventana = None
        self.panel = None
        self._reloj = None
        self._version = None

    def _crear(self) -> None:
        from views.outliner import OutlinerPanel                # interno de 0.5.8
        win = self.cadena.app.window
        self.ventana = QFrame(win, Qt.Popup)
        self.ventana.setObjectName("rosco_lt_navegador")
        self.ventana.setStyleSheet(
            f"QFrame#rosco_lt_navegador {{ border: 1.5px solid {ROJO}; border-radius: 6px; }}")
        lay = QVBoxLayout(self.ventana)
        lay.setContentsMargins(2, 2, 2, 2)
        self.panel = OutlinerPanel(win)
        lay.addWidget(self.panel)
        self.ventana.resize(ANCHO, ALTO)
        self._reloj = QTimer(self.ventana)
        self._reloj.setInterval(300)
        self._reloj.timeout.connect(self._seguir)
        self.ventana.installEventFilter(self._Cierre(self.ventana, self.cadena))

    class _Cierre(QObject):
        """Al cerrarse (clic fuera, Esc), el clic que lo cerró no debe
        llegar al modelo: Windows lo entrega también al visor."""

        def __init__(self, parent, cadena) -> None:
            super().__init__(parent)
            self.cadena = cadena

        def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
            if ev.type() == QEvent.Type.Hide:
                self.cadena.tragar_clic()
            return False

    def abrir(self, viewport, global_pos: QPoint) -> None:
        """Lo despliega con su esquina superior izquierda en ``global_pos``
        (sin salirse de la pantalla)."""
        if self.ventana is None:
            self._crear()
        self.panel.refresh()
        self._version = self._clave(viewport)
        pantalla = (QGuiApplication.screenAt(global_pos)
                    or QGuiApplication.primaryScreen()).availableGeometry()
        r = QRect(global_pos, self.ventana.size())
        if r.bottom() > pantalla.bottom():
            r.moveBottom(global_pos.y() - 30)          # mejor encima de la pastilla
        r.moveLeft(max(pantalla.left(), min(r.left(), pantalla.right() - r.width())))
        r.moveTop(max(pantalla.top(), r.top()))
        self.ventana.move(r.topLeft())
        self.ventana.show()
        self.panel.tree.setFocus()
        self._reloj.start()

    @staticmethod
    def _clave(viewport):
        scene = viewport.scene
        return (id(scene), getattr(scene, "version", None),
                len(getattr(scene, "selection", ()) or ()),
                id(getattr(scene, "edit_group", None)))

    def _seguir(self) -> None:
        """Mientras está abierto, al día con el modelo (como el panel)."""
        if self.ventana is None or not self.ventana.isVisible():
            if self._reloj is not None:
                self._reloj.stop()
            return
        vp = self.cadena.app.viewport
        clave = self._clave(vp)
        if clave != self._version:
            self._version = clave
            try:
                self.panel.refresh()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo poner al día el navegador")

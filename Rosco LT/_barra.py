# SPDX-License-Identifier: GPL-3.0-or-later
"""La barra de herramientas «Rosco LT», común a todas las piezas (la barra de dibujo,
Reiniciar…): se crea una vez y cada pieza le añade su botón."""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QToolBar

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

TOOLBAR = "rosco_lt_toolbar"
TITULO = "Rosco LT"
ESPERA_MS = 1500        # tras el arranque (IngeTrazo restaura entonces las barras)


def _colocar_primera_vez(win, tb) -> None:
    """La primera vez, IngeTrazo restaura sus barras después de los plugins y
    deja oculta la que no conoce. Entonces se coloca al final de la última
    fila de arriba y se muestra; desde ahí, manda la posición que guarde
    IngeTrazo (si se mueve u oculta, se respeta)."""
    from ._ajustes import ajustes as generales
    ajustes = generales()
    if str(ajustes.value("barra/colocada", "")).lower() in ("1", "true"):
        return

    def colocar() -> None:
        try:
            win.removeToolBar(tb)
            win.addToolBar(Qt.TopToolBarArea, tb)
            tb.show()
            ajustes.setValue("barra/colocada", True)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo colocar la barra Rosco LT")

    QTimer.singleShot(ESPERA_MS, colocar)


def barra(app) -> QToolBar:
    """La barra «Rosco LT», creada como las propias de IngeTrazo (Dibujo,
    Modificar…): movible, flotante, con el tamaño de icono de las
    preferencias y su entrada en el menú de barras."""
    win = app.window
    tb = win.findChild(QToolBar, TOOLBAR)
    if tb is not None:
        return tb
    nueva = getattr(win, "_new_toolbar", None)            # interno de 0.5.8
    if callable(nueva):
        try:
            tb = nueva(TITULO, TOOLBAR)
        except Exception:  # noqa: BLE001 — se crea a mano abajo
            log.exception("_new_toolbar falló; barra propia")
            tb = None
    if tb is None:
        tb = QToolBar(TITULO, win)
        tb.setObjectName(TOOLBAR)          # Qt recuerda su posición por el nombre
        tb.setMovable(True)
        tb.setFloatable(True)
        tb.setAllowedAreas(Qt.AllToolBarAreas)
        try:
            from views.icons import toolbar_icon_px
            px = toolbar_icon_px()
        except Exception:  # noqa: BLE001
            px = 24
        tb.setIconSize(QSize(px, px))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        win.addToolBar(Qt.TopToolBarArea, tb)
    tb._rosco_lt_refs = []                 # las acciones viven lo que la barra
    _colocar_primera_vez(win, tb)
    return tb


def anadir(app, accion) -> None:
    tb = barra(app)
    tb.addAction(_tr(accion))
    tb._rosco_lt_refs.append(accion)

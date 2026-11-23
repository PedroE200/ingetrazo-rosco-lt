# SPDX-License-Identifier: GPL-3.0-or-later
"""Entrada por voz en las cajas de texto de Multiempuje.

``con_microfono(campo)`` pone un micrófono dentro del campo, a la derecha, con la ayuda
«Dictar por voz». Al pulsarlo, el foco va al campo (al final de lo que haya) y se abre el
dictado del sistema (Win+H) en el sitio que el sistema decida (esa ventanita no se puede mover;
si se arrastra, el sistema recuerda dónde se dejó)."""
from __future__ import annotations

import ctypes
import logging
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit

log = logging.getLogger("ingetrazo.plugins.multiempuje.voz")

AYUDA = "Dictar por voz"


def icono_microfono(color: str = "#8a8a92") -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(11.0, 3.0, 10.0, 17.0), 5.0, 5.0)
    p.setBrush(Qt.NoBrush)
    arco = QPainterPath()
    arco.moveTo(7.0, 14.0)
    arco.cubicTo(7.0, 27.0, 25.0, 27.0, 25.0, 14.0)
    p.drawPath(arco)
    p.drawLine(QPointF(16.0, 24.0), QPointF(16.0, 29.0))
    p.drawLine(QPointF(11.0, 29.0), QPointF(21.0, 29.0))
    p.end()
    return QIcon(pm)


_u32 = ctypes.windll.user32 if os.name == "nt" else None
VK_LWIN, VK_H, KEYUP = 0x5B, 0x48, 0x0002


def _win_h() -> None:
    if _u32 is None:
        return
    for vk, sube in ((VK_LWIN, 0), (VK_H, 0), (VK_H, KEYUP), (VK_LWIN, KEYUP)):
        _u32.keybd_event(vk, 0, sube, 0)


def dictar(campo) -> None:
    try:
        w = campo.window()
        w.activateWindow()
        w.raise_()
        campo.setFocus(Qt.OtherFocusReason)
        campo.end(False)
        QTimer.singleShot(80, _win_h)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo abrir el dictado del sistema")


def con_microfono(campo: QLineEdit, ayuda: str = AYUDA) -> QLineEdit:
    accion = QAction(icono_microfono(), ayuda, campo)
    accion.setToolTip(ayuda)
    accion.triggered.connect(lambda: dictar(campo))
    campo.addAction(accion, QLineEdit.TrailingPosition)
    return campo

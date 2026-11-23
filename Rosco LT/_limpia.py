# SPDX-License-Identifier: GPL-3.0-or-later
"""Pantalla limpia por partes (el botoncito de la diana): quitar y volver a
poner los menús, todas las barras de herramientas, la barra de estado y los
paneles laterales de IngeTrazo, cada cosa por separado o todo de golpe. La
diana no se toca: va dibujada en el visor, y desde ella se vuelve a mostrar.

Al volver a poner algo sale solo lo que estaba a la vista al quitarlo. Antes
de cerrar IngeTrazo se pone todo como estaba, para que guarde su disposición
de siempre."""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QDockWidget, QToolBar

from ._ajustes import registro

log = registro("anillo")
PARTES = (("menus", "Quitar menús"),
          ("barras", "Quitar barras de herramientas"),
          ("estado", "Quitar barra de estado (abajo)"),
          ("paneles", "Quitar paneles laterales"))
_SIN_TOPE = 16777215                    # la altura máxima de serie de Qt


def icono_interruptor(encendido: bool) -> QIcon:
    """Un interruptor pequeño: rojo con la bola a la derecha si está
    encendido (todo quitado), gris con la bola a la izquierda si no."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(214, 34, 34) if encendido else QColor(201, 198, 191))
    p.drawRoundedRect(QRectF(1, 8, 30, 16), 8, 8)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QRectF(17 if encendido else 3, 10, 12, 12))
    p.end()
    return QIcon(pm)


class Limpieza(QObject):
    def __init__(self, win) -> None:
        super().__init__(win)
        self.win = win
        self.quitado: dict[str, list] = {}    # parte → lo que se escondió
        win.installEventFilter(self)

    def esta_quitado(self, parte) -> bool:
        return parte in self.quitado

    def todo_quitado(self) -> bool:
        return all(parte in self.quitado for parte, _t in PARTES)

    def poner(self, parte, quitar: bool) -> None:
        if quitar == (parte in self.quitado):
            return
        try:
            if quitar:
                self.quitado[parte] = self._quitar(parte)
            else:
                self._mostrar(parte, self.quitado.pop(parte))
        except Exception:  # noqa: BLE001
            log.exception("Pantalla limpia: fallo con %s", parte)

    def todo(self, quitar: bool) -> None:
        for parte, _t in PARTES:
            self.poner(parte, quitar)

    def _quitar(self, parte) -> list:
        win = self.win
        if parte == "menus":
            mb = win.menuBar()
            if mb is None or not mb.isVisible() or mb.maximumHeight() == 0:
                return []
            # Aplastada en vez de oculta: así siguen valiendo los atajos de
            # teclado de sus órdenes.
            mb.setMaximumHeight(0)
            return [mb]
        if parte == "barras":
            ws = [tb for tb in win.findChildren(QToolBar)
                  if tb.isVisible() and win.toolBarArea(tb) != Qt.NoToolBarArea]
        elif parte == "estado":
            sb = win.statusBar()
            ws = [sb] if sb is not None and sb.isVisible() else []
        else:
            ws = [d for d in win.findChildren(QDockWidget) if d.isVisible() and not d.isFloating()]
        for w in ws:
            w.hide()
        return ws

    @staticmethod
    def _mostrar(parte, ws) -> None:
        for w in ws:
            try:
                if parte == "menus":
                    w.setMaximumHeight(_SIN_TOPE)
                else:
                    w.show()
            except RuntimeError:                # ya no existe
                pass

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        if obj is self.win and ev.type() == QEvent.Type.Close and self.quitado:
            self.todo(False)
        return False

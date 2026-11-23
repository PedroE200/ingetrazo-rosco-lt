# SPDX-License-Identifier: GPL-3.0-or-later
"""Deshacer y rehacer varios pasos: mantener pulsado su botoncito del rosco.

El historial de IngeTrazo no pone nombre a sus pasos, así que Rosco anota con
qué orden se hizo cada uno según van entrando (``Pasos.anotar``, desde el
reloj de la barra). Lo que ya estaba al abrir el dibujo, o lo hecho sin una
orden conocida, toma el nombre del tipo de paso («Línea», «Agrupar»,
«Cambio»…).

``ListaPasos``: la ventanita con los 10 últimos; al pasar por uno se marcan
él y los de encima, y clic (o soltar el botón encima) = deshacer o rehacer
hasta ahí.
"""
from __future__ import annotations

from ._flotante import mover_a
from ._idioma import _tr
import logging

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ._ajustes import registro

log = registro("pasos")
CUANTOS = 10
FILA = 22.0
ANCHO = 214.0
ROJO = QColor(205, 30, 40)
TINTA = QColor(40, 40, 40)
GRIS = QColor(140, 140, 140)

# Tipo de paso del historial → nombre, cuando no se sabe con qué orden se hizo.
POR_TIPO = {
    "AddEdgeCommand": "Línea",
    "AddFaceCommand": "Cara",
    "MakeGroupCommand": "Agrupar",
    "MakeComponentCommand": "Componente",
    "InsertGroupCommand": "Insertar",
    "DeleteGroupCommand": "Borrar",
    "DeleteCommand": "Borrar",
    "EraseCommand": "Borrar",
    "AssignLayerCommand": "Pasar a capa",
    "DeleteLayerCommand": "Borrar capa",
    "ExplodeCommand": "Descomponer",
    "PaintCommand": "Pintar",
    "MoveCommand": "Mover",
    "TransformCommand": "Mover",
    "CompoundCommand": "Varios cambios",
    "SnapshotCompound": "Cambio",
    "SnapshotMutation": "Cambio",
}


class Pasos:
    """Los nombres de los pasos del historial, por paso."""

    def __init__(self) -> None:
        self._nombres: dict = {}               # id(paso) → nombre (None: no se sabe)
        self._escena = None

    def anotar(self, viewport, nombre_orden) -> None:
        """Mira si han entrado pasos nuevos y les pone ``nombre_orden()``."""
        hist = viewport.history
        pila = getattr(hist, "undo_stack", None)
        if pila is None:
            return
        if viewport.scene is not self._escena:
            # Otro dibujo: lo que hay no se hizo ahora.
            self._escena = viewport.scene
            self._nombres = {id(c): None for c in pila}
            self._nombres.update({id(c): None for c in getattr(hist, "redo_stack", [])})
            return
        nuevos = [c for c in list(pila)[-CUANTOS:] if id(c) not in self._nombres]
        if not nuevos:
            return
        nombre = None
        try:
            nombre = nombre_orden()
        except Exception:  # noqa: BLE001
            log.exception("sin el nombre de la orden")
        for c in nuevos:
            self._nombres[id(c)] = nombre
        if len(self._nombres) > 400:
            vivos = {id(c) for c in pila} | {id(c) for c in getattr(hist, "redo_stack", [])}
            self._nombres = {k: v for k, v in self._nombres.items() if k in vivos}

    def nombre(self, paso) -> str:
        tipo = type(paso).__name__
        if tipo == "AssignLayerCommand":
            return _tr("Pasar a capa")
        n = self._nombres.get(id(paso))
        if n:
            return n
        return _tr(POR_TIPO.get(tipo, "Cambio"))

    def ultimos(self, viewport, cual: str) -> list:
        """Los nombres de los últimos pasos de deshacer o de rehacer, el
        siguiente primero."""
        hist = viewport.history
        pila = list(getattr(hist, "undo_stack" if cual == "deshacer" else "redo_stack", []) or [])
        return [self.nombre(c) for c in reversed(pila[-CUANTOS:])]


class ListaPasos(QWidget):
    """La ventanita: título, los pasos y, abajo, lo que hará el clic."""

    def __init__(self, padre, cual: str, pasos: list, al_elegir) -> None:
        super().__init__(padre, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.cual = cual
        self.pasos = pasos
        self.al_elegir = al_elegir
        self.bajo = -1
        self.setFixedSize(int(ANCHO), int(34 + len(pasos) * FILA + 32))

    def mostrar(self, global_pos: QPoint, a_la_izquierda: bool) -> None:
        x = global_pos.x() - (self.width() if a_la_izquierda else 0)
        pantalla = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        zona = pantalla.availableGeometry()
        x = max(zona.left(), min(x, zona.right() - self.width()))
        y = global_pos.y()
        if y + self.height() > zona.bottom():
            y = max(zona.top(), global_pos.y() - self.height() - 30)
        mover_a(self, x, y)
        self.show()

    def _fila_en(self, p: QPointF) -> int:
        i = int((p.y() - 32.0) // FILA)
        if 0 <= i < len(self.pasos) and 4 <= p.x() <= self.width() - 4:
            return i
        return -1

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        i = self._fila_en(ev.position())
        if i != self.bajo:
            self.bajo = i
            self.update()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        i = self._fila_en(ev.position())
        if i < 0:
            return                             # p. ej. el soltar del botón que la abrió
        self.close()
        try:
            self.al_elegir(i + 1)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo %s varios pasos", self.cual)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if not self.rect().contains(ev.position().toPoint()):
            self.close()

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:
            self.close()

    def leaveEvent(self, ev) -> None:  # noqa: N802
        if self.bajo != -1:
            self.bajo = -1
            self.update()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            p.setPen(QPen(ROJO, 1.4))
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.drawRoundedRect(r, 8, 8)
            f = QFont(self.font())
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            p.setPen(TINTA)
            p.drawText(QRectF(12, 6, r.width() - 20, 22), Qt.AlignVCenter | Qt.AlignLeft,
                       _tr("Deshacer hasta…") if self.cual == "deshacer" else _tr("Rehacer hasta…"))
            for i, nombre in enumerate(self.pasos):
                y = 32.0 + i * FILA
                if 0 <= self.bajo and i <= self.bajo:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(255, 205, 205) if i == self.bajo else QColor(255, 228, 228)))
                    p.drawRect(QRectF(4, y, r.width() - 6, FILA - 1))
                f.setBold(False)
                f.setPixelSize(11)
                p.setFont(f)
                p.setPen(GRIS)
                p.drawText(QRectF(10, y, 20, FILA), Qt.AlignVCenter | Qt.AlignRight, str(i + 1))
                f.setPixelSize(13)
                f.setBold(i == self.bajo)
                p.setFont(f)
                p.setPen(TINTA)
                caja = QRectF(38, y, r.width() - 46, FILA)
                p.drawText(caja, Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetricsF(f).elidedText(nombre, Qt.ElideRight, caja.width()))
            f.setBold(True)
            f.setPixelSize(12)
            p.setFont(f)
            y = 32.0 + len(self.pasos) * FILA + 4
            if self.bajo >= 0:
                n = self.bajo + 1
                p.setPen(ROJO)
                texto = (_tr("Clic: deshacer {0} pasos", n) if self.cual == "deshacer"
                         else _tr("Clic: rehacer {0} pasos", n)) if n > 1 else (
                    _tr("Clic: deshacer 1 paso") if self.cual == "deshacer" else _tr("Clic: rehacer 1 paso"))
            else:
                p.setPen(GRIS)
                f.setBold(False)
                p.setFont(f)
                texto = _tr("Pasa por un paso y haz clic")
            p.drawText(QRectF(12, y, r.width() - 20, 22), Qt.AlignVCenter | Qt.AlignLeft, texto)
        finally:
            p.end()

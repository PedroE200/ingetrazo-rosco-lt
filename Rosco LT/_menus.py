# SPDX-License-Identifier: GPL-3.0-or-later
"""El árbol de menús de IngeTrazo: todos los menús de la barra de menús
(Archivo, Edición, Cámara, Dibujo…) en un desplegable que se abre por
ramas, con un filtro para encontrar una acción tecleando.

Un clic en una rama la abre o la cierra; un clic (o Enter) en una acción la
ejecuta y cierra el desplegable. Con el filtro escrito solo quedan las
acciones que lo contienen (sin mirar mayúsculas ni tildes), con sus ramas
abiertas, y Enter ejecuta la primera. Se rehace cada vez que se abre, así
que muestra lo que haya entonces en los menús (también los que se rellenan
al abrirse, como Extensiones). Se cierra al pinchar fuera.
"""
from __future__ import annotations

from ._idioma import _tr
import logging
import unicodedata

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QFrame, QHeaderView, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

ANCHO, ALTO = 340, 460
ROJO = "#d62222"


def _limpio(texto: str) -> str:
    """El texto de una acción sin el «&» del atajo ni el tabulador."""
    return (texto.replace("&&", "\0").replace("&", "").replace("\0", "&")
            .split("\t")[0].strip())


def _plano(texto: str) -> str:
    """En minúsculas y sin tildes (para el filtro)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


class _Cierre(QObject):
    """Al cerrarse (clic fuera, Esc), el clic que lo cerró no debe llegar
    al modelo: Windows lo entrega también al visor."""

    def __init__(self, parent, cadena) -> None:
        super().__init__(parent)
        self.cadena = cadena

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        if ev.type() == QEvent.Type.Hide:
            self.cadena.tragar_clic()
        return False


class MenusArbol:
    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.ventana = None
        self.filtro = None
        self.arbol = None
        self._acciones: dict = {}             # id(item) -> QAction

    def _crear(self) -> None:
        win = self.cadena.app.window
        v = self.ventana = QFrame(win, Qt.Popup)
        v.setObjectName("rosco_lt_menus")
        v.setStyleSheet(
            f"QFrame#rosco_lt_menus {{ border: 1.5px solid {ROJO}; border-radius: 6px; }}")
        lay = QVBoxLayout(v)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)
        self.filtro = QLineEdit(v)
        self.filtro.setPlaceholderText(_tr("Filtrar acciones…"))
        self.filtro.setClearButtonEnabled(True)
        from ._voz import con_microfono
        con_microfono(self.filtro)
        self.arbol = QTreeWidget(v)
        self.arbol.setColumnCount(2)
        self.arbol.setHeaderHidden(True)
        self.arbol.setUniformRowHeights(True)
        self.arbol.setExpandsOnDoubleClick(False)
        cab = self.arbol.header()
        cab.setStretchLastSection(False)
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        cab.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lay.addWidget(self.filtro)
        lay.addWidget(self.arbol)
        v.resize(ANCHO, ALTO)
        self.filtro.textChanged.connect(self._filtrar)
        self.filtro.returnPressed.connect(self._primera)
        self.arbol.itemClicked.connect(self._clic)
        self.arbol.itemActivated.connect(self._clic)
        v.installEventFilter(_Cierre(v, self.cadena))

    # -- el árbol --
    def _llenar(self) -> None:
        self.arbol.clear()
        self._acciones.clear()
        for act in self.cadena.app.window.menuBar().actions():
            menu = act.menu()
            if menu is None or not act.isVisible():
                continue
            item = QTreeWidgetItem([_limpio(act.text()), ""])
            letra = item.font(0)
            letra.setBold(True)
            item.setFont(0, letra)
            self.arbol.addTopLevelItem(item)
            self._rama(item, menu, frozenset())

    def _rama(self, padre, menu, vistos) -> None:
        if id(menu) in vistos:
            return
        vistos = vistos | {id(menu)}
        try:
            menu.aboutToShow.emit()           # los que se rellenan al abrirse
        except Exception:  # noqa: BLE001
            log.exception("el menú %s no se dejó preparar", menu.title())
        for act in menu.actions():
            if act.isSeparator() or not act.isVisible():
                continue
            texto = _limpio(act.text())
            if not texto:
                continue
            sub = act.menu()
            if sub is not None:
                item = QTreeWidgetItem(padre, [texto, ""])
                self._rama(item, sub, vistos)
                if item.childCount() == 0:
                    padre.removeChild(item)
                continue
            if act.isCheckable():
                texto = ("✓ " if act.isChecked() else "    ") + texto
            atajo = act.shortcut().toString(QKeySequence.NativeText)
            item = QTreeWidgetItem(padre, [texto, atajo])
            if not act.icon().isNull():
                item.setIcon(0, act.icon())
            item.setDisabled(not act.isEnabled())
            self._acciones[id(item)] = act

    def _filtrar(self, texto: str) -> None:
        t = _plano(texto.strip())

        def ver(item) -> bool:
            if item.childCount():
                hijos = [ver(item.child(i)) for i in range(item.childCount())]
                visible = any(hijos) if t else True
                item.setHidden(not visible)
                item.setExpanded(bool(t) and visible)
                return visible
            visible = not t or t in _plano(item.text(0))
            item.setHidden(not visible)
            return visible

        for i in range(self.arbol.topLevelItemCount()):
            ver(self.arbol.topLevelItem(i))

    def _hojas_visibles(self, item=None):
        hijos = ([self.arbol.topLevelItem(i) for i in range(self.arbol.topLevelItemCount())]
                 if item is None else [item.child(i) for i in range(item.childCount())])
        for h in hijos:
            if h.isHidden():
                continue
            if id(h) in self._acciones:
                yield h
            else:
                yield from self._hojas_visibles(h)

    def _primera(self) -> None:
        """Enter en el filtro: la primera acción que queda (si se puede)."""
        for h in self._hojas_visibles():
            if not h.isDisabled():
                self._clic(h)
                return

    def _clic(self, item, _columna=0) -> None:
        act = self._acciones.get(id(item))
        if act is None:                      # una rama: se abre o se cierra
            item.setExpanded(not item.isExpanded())
            return
        if not act.isEnabled():
            return
        self.ventana.hide()
        QTimer.singleShot(0, act.trigger)

    # -- abrir --
    def abrir(self, global_pos: QPoint) -> None:
        """Lo despliega con su esquina superior izquierda en ``global_pos``
        (sin salirse de la pantalla)."""
        if self.ventana is None:
            self._crear()
        self._llenar()
        self.filtro.blockSignals(True)
        self.filtro.clear()
        self.filtro.blockSignals(False)
        pantalla = (QGuiApplication.screenAt(global_pos)
                    or QGuiApplication.primaryScreen()).availableGeometry()
        r = QRect(global_pos, self.ventana.size())
        r.moveLeft(max(pantalla.left(), min(r.left(), pantalla.right() - r.width())))
        r.moveTop(max(pantalla.top(), min(r.top(), pantalla.bottom() - r.height())))
        self.ventana.move(r.topLeft())
        self.ventana.show()
        self.filtro.setFocus()

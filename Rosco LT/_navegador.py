# SPDX-License-Identifier: GPL-3.0-or-later
"""El desplegable Navegador: un espejo del panel Navegador de IngeTrazo.

Es otra copia del mismo panel (``views.outliner.OutlinerPanel``), en una
ventanita desplegable bajo la pastilla: el árbol de grupos y componentes a
cualquier profundidad, el filtro, el ojo, el candado, los planos de sección y
su menú contextual. Un clic selecciona en el modelo, un doble clic (o Enter)
abre el grupo para editarlo. Se cierra al pinchar fuera, como cualquier
desplegable, o al salir con el ratón.

1.6.0: arriba, dentro del propio panel, una fila con la chincheta (fijado:
ni se cierra al salir ni al pinchar fuera, y se mueve arrastrando la fila),
«Actualizar» y la casilla «Automático» (se pone al día solo, como el
Navegador de IngeTrazo; si no, solo con «Actualizar»).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from ._flotante import mover_a
from ._idioma import _tr

from ._ajustes import registro

log = registro("anillo")
ANCHO, ALTO = 460, 420
ROJO = "#d62222"


def _icono(clave: str, lado: int = 18) -> QIcon:
    from . import _iconos
    pm = QPixmap(lado * 2, lado * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        _iconos.pintar(p, clave, QPointF(lado / 2.0, lado / 2.0), float(lado))
    finally:
        p.end()
    return QIcon(pm)


def _ajuste_auto() -> bool:
    try:
        from ._ajustes import ajustes
        return str(ajustes("navegador").value("automatico", True)).lower() in ("true", "1")
    except Exception:  # noqa: BLE001
        return True


def _guardar_auto(valor: bool) -> None:
    try:
        from ._ajustes import ajustes
        s = ajustes("navegador")
        s.setValue("automatico", bool(valor))
        s.sync()
    except Exception:  # noqa: BLE001
        log.exception("no se pudo guardar el ajuste del navegador")


class Navegador:
    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.ventana = None
        self.panel = None
        self._reloj = None
        self._version = None
        self._dentro = False                  # el ratón ya entró (salir lo cierra)
        self.fijado = False
        from . import _edicion
        self.con_cabeza = _edicion.con("navegador_chincheta")
        self.automatico = _ajuste_auto() if self.con_cabeza else True
        self._arrastre = None

    def _crear(self) -> None:
        from views.outliner import OutlinerPanel                # interno de 0.5.8
        win = self.cadena.app.window
        self.ventana = QFrame(win, Qt.Popup)
        self.ventana.setObjectName("rosco_navegador")
        lay = QVBoxLayout(self.ventana)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        self.panel = OutlinerPanel(win)
        # La fila de arriba, con el mismo fondo que el panel (sin huecos blancos).
        fondo = self.panel.palette().color(self.panel.backgroundRole()).name()
        texto = self.panel.palette().color(self.panel.foregroundRole()).name()
        self.ventana.setStyleSheet(
            f"QFrame#rosco_navegador {{ border: 1.5px solid {ROJO}; border-radius: 6px; background: {fondo}; }}"
            f"QWidget#nav_cabeza {{ background: {fondo}; }}"
            f"QWidget#nav_cabeza QToolButton {{ color: {texto}; background: transparent; border: 1px solid transparent;"
            f" border-radius: 4px; padding: 1px 4px; font-size: 11px; }}"
            f"QWidget#nav_cabeza QToolButton:hover {{ border-color: {ROJO}; }}"
            f"QWidget#nav_cabeza QToolButton:checked {{ background: rgba(214,34,34,70); border-color: {ROJO}; }}"
            f"QWidget#nav_cabeza QCheckBox {{ color: {texto}; font-size: 11px; }}")
        cabeza = QWidget()
        cabeza.setObjectName("nav_cabeza")
        cabeza.setCursor(Qt.SizeAllCursor)
        fila = QHBoxLayout(cabeza)
        fila.setContentsMargins(4, 2, 4, 2)
        fila.setSpacing(6)
        self.boton_fijar = QToolButton()
        self.boton_fijar.setCheckable(True)
        self.boton_fijar.setIcon(_icono("chincheta"))
        self.boton_fijar.setIconSize(QSize(16, 16))
        self.boton_fijar.setToolTip(_tr("Fijar: no se cierra al salir ni al pinchar fuera "
                                        "(se mueve arrastrando esta fila)"))
        self.boton_fijar.setCursor(Qt.ArrowCursor)
        self.boton_fijar.toggled.connect(lambda v: QTimer.singleShot(0, lambda: self._fijar(v)))
        fila.addWidget(self.boton_fijar)
        self.boton_actualizar = QToolButton()
        self.boton_actualizar.setText(_tr("⟳ Actualizar"))
        self.boton_actualizar.setToolTip(_tr("Poner el navegador al día ahora"))
        self.boton_actualizar.setCursor(Qt.ArrowCursor)
        self.boton_actualizar.clicked.connect(self.actualizar)
        fila.addWidget(self.boton_actualizar)
        self.casilla_auto = QCheckBox(_tr("Automático"))
        self.casilla_auto.setChecked(self.automatico)
        self.casilla_auto.setToolTip(_tr("Marcado: se pone al día solo, como el Navegador de IngeTrazo. "
                                         "Desmarcado: solo con «Actualizar»."))
        self.casilla_auto.setCursor(Qt.ArrowCursor)
        self.casilla_auto.setFocusPolicy(Qt.NoFocus)
        self.casilla_auto.toggled.connect(self._poner_auto)
        fila.addWidget(self.casilla_auto)
        fila.addStretch(1)
        cabeza.installEventFilter(self._Arrastre(cabeza, self))
        if self.con_cabeza:
            lay.addWidget(cabeza)
        else:
            cabeza.setParent(self.ventana)
            cabeza.hide()
        lay.addWidget(self.panel)
        self.ventana.resize(ANCHO, ALTO)
        self._reloj = QTimer(self.ventana)
        self._reloj.setInterval(300)
        self._reloj.timeout.connect(self._seguir)
        self.ventana.installEventFilter(self._Cierre(self.ventana, self.cadena))

    class _Cierre(QObject):
        """Al cerrarse (clic fuera, Esc), el clic que lo cerró no debe
        llegar al modelo: el sistema lo entrega también al visor."""

        def __init__(self, parent, cadena) -> None:
            super().__init__(parent)
            self.cadena = cadena

        def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
            if ev.type() == QEvent.Type.Hide:
                self.cadena.tragar_clic()
            return False

    class _Arrastre(QObject):
        """Arrastrar la fila de arriba mueve la ventanita."""

        def __init__(self, parent, nav) -> None:
            super().__init__(parent)
            self.nav = nav

        def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
            t = ev.type()
            v = self.nav.ventana
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.LeftButton:
                self.nav._arrastre = ev.globalPosition().toPoint() - v.pos()
                return True
            if t == QEvent.Type.MouseMove and self.nav._arrastre is not None and ev.buttons() & Qt.LeftButton:
                v.move(ev.globalPosition().toPoint() - self.nav._arrastre)
                return True
            if t == QEvent.Type.MouseButtonRelease:
                self.nav._arrastre = None
            return False

    def _fijar(self, puesto: bool) -> None:
        """Con la chincheta, ventana normal (no se cierra al pinchar fuera);
        sin ella, otra vez desplegable."""
        if self.ventana is None:
            return
        self.fijado = bool(puesto)
        pos, visible = self.ventana.pos(), self.ventana.isVisible()
        self.ventana.setWindowFlags((Qt.Tool | Qt.FramelessWindowHint) if self.fijado else Qt.Popup)
        mover_a(self.ventana, pos)
        if visible or self.fijado:
            self.ventana.show()
            self._reloj.start()
        self._dentro = False

    def _poner_auto(self, valor: bool) -> None:
        self.automatico = bool(valor)
        _guardar_auto(self.automatico)
        if self.automatico:
            self.actualizar()

    def actualizar(self) -> None:
        if self.panel is None:
            return
        self._version = self._clave(self.cadena.app.viewport)
        try:
            self.panel.refresh()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo poner al día el navegador")

    def abrir(self, viewport, global_pos: QPoint) -> None:
        """Lo despliega con su esquina superior izquierda en ``global_pos``
        (sin salirse de la pantalla). Fijado, solo se pone al día y delante."""
        if self.ventana is None:
            self._crear()
        self.actualizar()
        self._dentro = False
        if self.fijado and self.ventana.isVisible():
            self.ventana.raise_()
            return
        pantalla = (QGuiApplication.screenAt(global_pos)
                    or QGuiApplication.primaryScreen()).availableGeometry()
        r = QRect(global_pos, self.ventana.size())
        if r.bottom() > pantalla.bottom():
            r.moveBottom(global_pos.y() - 30)          # mejor encima de la pastilla
        r.moveLeft(max(pantalla.left(), min(r.left(), pantalla.right() - r.width())))
        r.moveTop(max(pantalla.top(), r.top()))
        mover_a(self.ventana, r.topLeft())
        self.ventana.show()
        self.panel.tree.setFocus()
        self._reloj.start()

    def _salio(self) -> bool:
        """El ratón ya estuvo dentro y ahora está fuera (sin un menú suyo
        abierto): se cierra el desplegable y el rosco, y queda Seleccionar.
        Fijado, no."""
        if self.fijado:
            return False
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication
        dentro = self.ventana.frameGeometry().adjusted(-10, -10, 10, 10).contains(QCursor.pos())
        if dentro:
            self._dentro = True
            return False
        if not self._dentro or QApplication.activePopupWidget() not in (None, self.ventana):
            return False
        self._dentro = False
        self.ventana.hide()
        try:
            self.cadena.cerrar_anillo()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo cerrar el rosco al salir del navegador")
        return True

    @staticmethod
    def _clave(viewport):
        """Lo que cambia el árbol: el modelo, lo seleccionado (qué, no
        cuántos), los grupos abiertos y lo oculto."""
        scene = viewport.scene
        try:
            sel = frozenset(id(x) for x in (getattr(scene, "selection", ()) or ()))
        except Exception:  # noqa: BLE001
            sel = None
        def largo(nombre):
            try:
                v = getattr(scene, nombre, None)
                return len(v) if v is not None and not callable(v) else None
            except Exception:  # noqa: BLE001
                return None
        version = getattr(scene, "content_version", None)
        return (id(scene), getattr(scene, "version", None), None if callable(version) else version,
                sel, id(getattr(scene, "edit_group", None)), largo("_edit_stack"), largo("_object_hidden"))

    def _seguir(self) -> None:
        """Mientras está abierto, al día con el modelo si es automático. Si el
        ratón entró y vuelve a salir (sin fijar), se cierra y queda
        Seleccionar."""
        if self.ventana is None or not self.ventana.isVisible():
            if self._reloj is not None:
                self._reloj.stop()
            return
        if self._salio():
            return
        if not self.automatico:
            return
        clave = self._clave(self.cadena.app.viewport)
        if clave != self._version:
            self.actualizar()

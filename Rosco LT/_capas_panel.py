# SPDX-License-Identifier: GPL-3.0-or-later
"""El mini panel de capas que abre el cajetín de capa (▾ o el nombre).

Lo del panel Capas de IngeTrazo en pequeño, con sus mismas funciones (así el
panel, la barra Capas y «Estado anterior» se enteran):

- arriba, el buscador (con micrófono y ayuda con imagen) y los botones de
  capa nueva y carpeta nueva;
- cada fila: ojo (mostrar u ocultar), candado (bloquear, verde abierto / rojo
  cerrado), diana (aislar, verde / roja), el color y el nombre, y el lápiz
  de la activa;
- clic en el nombre: sin selección, esa capa pasa a ser la activa; con algo
  seleccionado, pregunta y lo pasa a esa capa;
- botón derecho en una fila: el menú de esa capa del panel Capas (color,
  línea, grosor, transparencia, impresión, renombrar, fusionar…);
- abajo, los botones de la barra Capas y «⋯» (purgar, plantillas, abrir el
  panel).

Se cierra con Esc o con un clic fuera de él.
"""
from __future__ import annotations

from ._flotante import mover_a
from ._idioma import _tr
import fnmatch
import logging

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import _capas

from ._ajustes import registro

log = registro("capas")
ANCHO = 336
ROJO = QColor(205, 30, 40)
VERDE = QColor(30, 150, 60)
NEGRO = QColor(30, 30, 30)
GRIS = QColor(150, 150, 150)
NARANJA = QColor(240, 110, 40)
OSCURO = "#46484e"

C_OJO, C_CANDADO, C_AISLAR, C_NOMBRE, C_ACTIVA = range(5)
# Las columnas del panel Capas de IngeTrazo que hacen lo mismo.
NATIVA = {C_OJO: 2, C_CANDADO: 3, C_ACTIVA: 1}
BARRA = ("Hacer capa activa", "Aislar capa", "Bloquear capa", "Pasar a la capa activa",
         "Ocultar capa", "Mostrar todas las capas", "Estado anterior")


# ---- los iconos -------------------------------------------------------------------
def _icono(dibujar, tam=16) -> QIcon:
    dpr = 2.0
    pm = QPixmap(int(tam * dpr), int(tam * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        dibujar(p, tam / 2.0, tam / 2.0)
    finally:
        p.end()
    return QIcon(pm)


def pintar_ojo(p, cx, cy, abierto=True, col=NEGRO, s=1.0) -> None:
    p.setPen(QPen(col, 1.2))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(cx - 6 * s, cy))
    path.quadTo(QPointF(cx, cy - 6 * s), QPointF(cx + 6 * s, cy))
    path.quadTo(QPointF(cx, cy + 6 * s), QPointF(cx - 6 * s, cy))
    p.drawPath(path)
    p.setBrush(QBrush(col))
    p.drawEllipse(QPointF(cx, cy), 1.8 * s, 1.8 * s)
    if not abierto:
        p.setPen(QPen(ROJO, 1.6))
        p.drawLine(QPointF(cx - 6 * s, cy + 5 * s), QPointF(cx + 6 * s, cy - 5 * s))


def pintar_candado(p, cx, cy, cerrado=True, col=NEGRO, s=1.0) -> None:
    p.setPen(QPen(col, 1.2))
    p.setBrush(QBrush(col) if cerrado else Qt.NoBrush)
    p.drawRoundedRect(QRectF(cx - 4.5 * s, cy - 1 * s, 9 * s, 7 * s), 1.2, 1.2)
    p.setBrush(Qt.NoBrush)
    arco = QPainterPath()
    arco.moveTo(cx - 3 * s, cy - 1 * s)
    arco.lineTo(cx - 3 * s, cy - 3.5 * s)
    arco.arcTo(QRectF(cx - 3 * s, cy - 6.5 * s, 6 * s, 6 * s), 180, -180)
    arco.lineTo(cx + 3 * s, (cy - 1 * s) if cerrado else (cy - 3 * s))
    p.drawPath(arco)


def pintar_diana(p, cx, cy, llena=False, col=GRIS, s=1.0) -> None:
    p.setPen(QPen(col, 1.3))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), 6 * s, 6 * s)
    p.setBrush(QBrush(col) if llena else Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), 2.4 * s, 2.4 * s)


def pintar_lapiz(p, cx, cy, col=NARANJA, s=1.0) -> None:
    from PySide6.QtGui import QPolygonF
    p.setPen(QPen(col.darker(140), 0.9))
    p.setBrush(QBrush(col))
    p.drawPolygon(QPolygonF([QPointF(cx - 5 * s, cy + 5 * s), QPointF(cx - 5 * s, cy + 2 * s),
                             QPointF(cx + 3 * s, cy - 6 * s), QPointF(cx + 6 * s, cy - 3 * s),
                             QPointF(cx - 2 * s, cy + 5 * s)]))


def pintar_gotero(p, cx, cy, col, s=1.0) -> None:
    """Un cuentagotas inclinado (la punta abajo a la izquierda): perilla,
    collar, tubo y la gota."""
    from PySide6.QtGui import QPolygonF
    p.save()
    p.translate(cx, cy)
    p.rotate(45.0)
    p.scale(s, s)
    p.setPen(QPen(col.darker(150), 1.0))
    p.setBrush(QBrush(col))
    p.drawRoundedRect(QRectF(-2.6, -8.5, 5.2, 5.5), 2.2, 2.2)
    p.drawRect(QRectF(-3.6, -3.4, 7.2, 1.6))
    p.setBrush(QBrush(QColor(255, 255, 255)))
    p.drawPolygon(QPolygonF([QPointF(-1.8, -1.8), QPointF(1.8, -1.8), QPointF(0.7, 6.5), QPointF(-0.7, 6.5)]))
    p.setBrush(QBrush(col))
    p.drawEllipse(QPointF(0.0, 8.6), 1.1, 1.1)
    p.restore()


def cursor_gotero():
    """El cursor del cuentagotas (la punta es el sitio del clic)."""
    from PySide6.QtGui import QCursor
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        pintar_gotero(p, 17.0, 15.0, QColor(205, 30, 40), 1.55)
    finally:
        p.end()
    return QCursor(pm, 6, 26)


from ._capas import pintar_aplicar  # noqa: E402,F401 — el de Aplicar capa, común


def _muestra(rgb) -> QIcon:
    col = QColor.fromRgbF(*rgb)

    def d(p, cx, cy):
        p.setPen(QPen(QColor(90, 90, 90), 1))
        p.setBrush(QBrush(col))
        p.drawRect(QRectF(cx - 5, cy - 5, 10, 10))
    return _icono(d)


def _carpeta() -> QIcon:
    def d(p, cx, cy):
        p.setPen(QPen(QColor(150, 120, 40), 1))
        p.setBrush(QBrush(QColor(240, 205, 110)))
        p.drawRect(QRectF(cx - 6.5, cy - 4, 13, 10))
        p.drawRect(QRectF(cx - 6.5, cy - 6, 6, 2.5))
    return _icono(d)


# ---- la ayuda con imagen del buscador ----------------------------------------------
def _registrar_ayuda() -> None:
    from . import _ayuda_texto as A
    if "filtro_capas" in A.AYUDAS:
        return
    A.AYUDAS["filtro_capas"] = (
        "Filtrar capas", "Escribe parte del nombre. Con * y ? es un patrón para el nombre "
        "entero: «MUR*», «*cota*». Vacío: todas.")

    def dibujo(p):
        f = QFont("Segoe UI")
        f.setPointSizeF(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(NEGRO)
        p.drawText(QPointF(12, 34), "MUR*")
        p.setPen(GRIS)
        p.drawText(QPointF(64, 34), "→")
        f.setBold(False)
        p.setFont(f)
        for i, (n, col) in enumerate((("Muros", QColor(219, 107, 92)),
                                      ("Muros interiores", QColor(186, 90, 80)))):
            p.setPen(QPen(QColor(90, 90, 90), 1))
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(88, 24 + i * 24, 10, 10))
            p.setPen(NEGRO)
            p.drawText(QPointF(104, 34 + i * 24), n)
        p.setPen(GRIS)
        p.drawText(QPointF(12, 82), _tr("«Cotas» no sale"))
    A.DIBUJOS["filtro_capas"] = dibujo


# ---- el mini panel ------------------------------------------------------------------
class _Arbol(QTreeWidget):
    """La lista: la rueda solo la desplaza."""

    def __init__(self, padre) -> None:
        super().__init__(padre)
        self.al_derecho = None

    def contextMenuEvent(self, ev) -> None:  # noqa: N802
        if callable(self.al_derecho):
            self.al_derecho(self.itemAt(ev.pos()), ev.globalPos())


class MiniCapas(QFrame):
    def __init__(self, cadena) -> None:
        super().__init__(cadena.app.window, Qt.Tool | Qt.FramelessWindowHint)
        self.cadena = cadena
        self.vp = None
        self._ocupado = False                 # un aviso o un menú abierto desde aquí
        self._firma = None
        self._plegadas: set = set()
        self.setObjectName("rosco_capas")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedWidth(ANCHO)
        self.setStyleSheet(
            "QFrame#rosco_capas { background: #ffffff; border: 1.5px solid #cd1e28; border-radius: 8px; }"
            "QLineEdit { border: 1px solid #bebec3; border-radius: 5px; padding: 3px 6px;"
            " background: #fafafc; color: #222; }"
            "QTreeWidget { border: none; background: #ffffff; color: #222; outline: none; }"
            "QTreeWidget::item { height: 24px; }"
            "QTreeWidget::item:hover { background: #e8eefc; }"
            "QTreeWidget::item:selected { background: #ffece4; color: #222; }"
            "QHeaderView::section { background: #ffffff; color: #888; border: none;"
            " border-bottom: 1px solid #e1e1e4; padding: 2px; font-weight: bold; }"
            "QFrame#rosco_capas_abajo { background: " + OSCURO + "; border-radius: 6px; }"
            "QToolButton#oscuro { background: " + OSCURO + "; border: none; border-radius: 5px; }"
            "QToolButton#oscuro:hover { background: #5d6068; }"
            "QToolButton#oscuro:disabled { background: #6a6c72; }"
            "QToolButton#claro { background: #f5f5f7; border: 1px solid #c8c8cd; border-radius: 5px;"
            " color: #222; font-weight: bold; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        arriba = QHBoxLayout()
        arriba.setSpacing(5)
        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText(_tr("Filtrar capas… (admite * y ?)"))
        self.filtro.textChanged.connect(lambda _t: self.rellenar(forzar=True))
        try:
            from ._voz import con_microfono
            con_microfono(self.filtro, self)
        except Exception:  # noqa: BLE001
            log.exception("sin micrófono en el buscador de capas")
        arriba.addWidget(self.filtro, 1)
        self.b_capa = self._boton_oscuro(_tr("Agregar capa"), self._nueva_capa)
        self.b_carpeta = self._boton_oscuro(_tr("Agregar carpeta"), self._nueva_carpeta)
        arriba.addWidget(self.b_capa)
        arriba.addWidget(self.b_carpeta)
        lay.addLayout(arriba)

        self.arbol = _Arbol(self)
        self.arbol.setColumnCount(5)
        self.arbol.setHeaderLabels(["", "", "", _tr("Nombre"), _tr("Activa")])
        h = self.arbol.header()
        h.setStretchLastSection(False)
        for col, ancho in ((C_OJO, 24), (C_CANDADO, 24), (C_AISLAR, 24), (C_ACTIVA, 46)):
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            self.arbol.setColumnWidth(col, ancho)
        h.setSectionResizeMode(C_NOMBRE, QHeaderView.Stretch)
        h.setSectionsClickable(False)
        cab = self.arbol.headerItem()
        cab.setIcon(C_OJO, _icono(lambda p, x, y: pintar_ojo(p, x, y, True, GRIS)))
        cab.setIcon(C_CANDADO, _icono(lambda p, x, y: pintar_candado(p, x, y, False, GRIS)))
        cab.setIcon(C_AISLAR, _icono(lambda p, x, y: pintar_diana(p, x, y, False, GRIS)))
        cab.setToolTip(C_OJO, _tr("Mostrar u ocultar"))
        cab.setToolTip(C_CANDADO, _tr("Bloquear o desbloquear"))
        cab.setToolTip(C_AISLAR, _tr("Aislar: ver solo esa capa"))
        # Sin sangría (la columna del ojo no se mueve): el nombre lleva la suya
        # y las carpetas, ▸ / ▾ delante.
        self.arbol.setIndentation(0)
        self.arbol.setRootIsDecorated(False)
        self.arbol.setItemsExpandable(False)
        self.arbol.setSelectionMode(QAbstractItemView.NoSelection)
        self.arbol.setFocusPolicy(Qt.NoFocus)
        self.arbol.setIconSize(QSize(16, 16))
        self.arbol.setMouseTracking(True)
        self.arbol.itemClicked.connect(self._clic)
        self.arbol.al_derecho = self._derecho
        lay.addWidget(self.arbol)

        abajo = QFrame()
        abajo.setObjectName("rosco_capas_abajo")
        fila = QHBoxLayout(abajo)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(3)
        self.botones = {}
        for texto in BARRA:
            b = QToolButton()
            b.setObjectName("oscuro")
            b.setIconSize(QSize(24, 24))
            b.setFixedSize(QSize(34, 30))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _c=False, t=texto: self._accion_barra(t))
            fila.addWidget(b)
            self.botones[texto] = b
        mas = QToolButton()
        mas.setObjectName("claro")
        mas.setText("⋯")
        mas.setFixedSize(QSize(30, 30))
        mas.setFocusPolicy(Qt.NoFocus)
        mas.setToolTip(_tr("Más: purgar, plantillas, abrir el panel Capas"))
        mas.clicked.connect(lambda: self._mas(mas))
        fila.addWidget(mas)
        fila.addStretch(1)
        lay.addWidget(abajo)

        try:
            _registrar_ayuda()
            from ._ayuda_texto import Ayudante
            self.ayuda = Ayudante(self)
            self.ayuda.poner(self.filtro, "filtro_capas")
        except Exception:  # noqa: BLE001
            log.exception("sin ayuda con imagen en el buscador de capas")
            self.ayuda = None

        self._reloj = QTimer(self)
        self._reloj.setInterval(400)
        self._reloj.timeout.connect(self.rellenar)

    # -- piezas --
    def _boton_oscuro(self, ayuda, accion) -> QToolButton:
        b = QToolButton()
        b.setObjectName("oscuro")
        b.setToolTip(ayuda)
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(QSize(36, 28))
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(accion)
        return b

    def _panel(self):
        return _capas.panel_nativo(self.cadena.app.window)

    def _barra_capas(self):
        for t in self.cadena.app.window.findChildren(QToolBar):
            if t.objectName() == "layers":
                return t
        return None

    def _accion(self, texto):
        tb = self._barra_capas()
        if tb is None:
            return None
        return next((a for a in tb.actions() if a.text() == texto), None)

    def _iconos_nativos(self) -> None:
        """Los iconos de la barra y del panel Capas, tal cual."""
        for texto, b in self.botones.items():
            a = self._accion(texto)
            if a is not None:
                b.setIcon(a.icon())
                b.setToolTip(a.toolTip())
                b.setEnabled(a.isEnabled())
            else:
                b.setEnabled(False)
        panel = self._panel()
        if panel is not None:
            for b in panel.findChildren(QToolButton):
                if b.toolTip() == _tr("Agregar capa") or b.toolTip() == "Agregar capa":
                    self.b_capa.setIcon(b.icon())
                elif b.toolTip() == _tr("Agregar carpeta") or b.toolTip() == "Agregar carpeta":
                    self.b_carpeta.setIcon(b.icon())
        if self.b_capa.icon().isNull():
            self.b_capa.setText("+")
        if self.b_carpeta.icon().isNull():
            self.b_carpeta.setText("+▭")

    # -- abrir y cerrar --
    def abrir(self, viewport, global_pos: QPoint) -> None:
        self.vp = viewport
        self.filtro.blockSignals(True)
        self.filtro.clear()
        self.filtro.blockSignals(False)
        self._iconos_nativos()
        self.rellenar(forzar=True)
        self.adjustSize()
        pantalla = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        zona = pantalla.availableGeometry()
        x = max(zona.left(), min(global_pos.x(), zona.right() - self.width()))
        y = global_pos.y()
        if y + self.height() > zona.bottom():
            y = max(zona.top(), y - self.height() - 34)
        mover_a(self, x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.instance().installEventFilter(self)
        self._reloj.start()

    def closeEvent(self, ev) -> None:  # noqa: N802
        self._reloj.stop()
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:  # noqa: BLE001
            pass
        if self.ayuda is not None:
            self.ayuda.tarjeta.hide()
        super().closeEvent(ev)
        if self.vp is not None:
            self.vp.setFocus()
        QTimer.singleShot(0, self.cadena._sincronizar)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        t = ev.type()
        if t == QEvent.Type.KeyPress and ev.key() == Qt.Key_Escape and not self._ocupado:
            self.close()
            return True
        if t == QEvent.Type.MouseButtonPress and not self._ocupado and self.isVisible():
            w = obj if isinstance(obj, QWidget) else None
            if w is not None and not self._es_mio(w):
                self.close()
                self.cadena.tragar_clic()
        return False

    def _es_mio(self, w) -> bool:
        while w is not None:
            if w is self:
                return True
            if isinstance(w, QMenu) or (self.ayuda is not None and w is self.ayuda.tarjeta):
                return True
            w = w.parentWidget()
        return False

    # -- la lista --
    def _filtra(self, nombre) -> bool:
        t = self.filtro.text().strip()
        if not t:
            return True
        if "*" in t or "?" in t:
            return fnmatch.fnmatch(nombre.lower(), t.lower())
        return t.lower() in nombre.lower()

    def _filas(self, scene):
        panel = self._panel()
        if panel is not None and callable(getattr(panel, "display_outline", None)):
            try:
                return list(panel.display_outline())
            except Exception:  # noqa: BLE001
                log.exception("sin el orden del panel Capas")
        return [("layer", n, 0) for n in _capas.nombres(scene)]

    def rellenar(self, forzar: bool = False) -> None:
        vp = self.vp
        if vp is None or (not forzar and not self.isVisible()):
            return
        scene = vp.scene
        filas = self._filas(scene)
        act = _capas.activa(scene)
        estado = tuple((k, n, d, _capas.oculta(scene, n), _capas.bloqueada(scene, n),
                        _capas.aislada(vp, n) if k == "layer" else False,
                        _capas.color_de(scene, n) if k == "layer" else None) for k, n, d in filas)
        firma = (id(scene), estado, act, self.filtro.text())
        if not forzar and firma == self._firma:
            return
        self._firma = firma
        self.arbol.clear()
        # Las capas que pasan el filtro, con las carpetas que llevan a ellas.
        visibles = set()
        pila = []
        for k, n, d in filas:
            del pila[d:]
            if k == "layer" and self._filtra(n):
                visibles.add(("layer", n))
                visibles.update(pila)
            if k == "folder":
                pila.append(("folder", n))
        padres = []                           # (item o None, nombre) de cada carpeta abierta
        for (k, n, d), (_k, _n, _d, oc, bl, ai, rgb) in zip(filas, estado):
            del padres[d:]
            plegada = any(q[1] in self._plegadas for q in padres)
            if (k, n) not in visibles or plegada:
                if k == "folder":
                    padres.append((None, n))
                continue
            padre = next((q[0] for q in reversed(padres) if q[0] is not None), None)
            it = QTreeWidgetItem(padre if padre is not None else self.arbol)
            it.setData(C_NOMBRE, Qt.UserRole, (k, n))
            sangria = "    " * d
            if k == "folder":
                it.setText(C_NOMBRE, sangria + ("▸ " if n in self._plegadas else "▾ ") + n)
            else:
                it.setText(C_NOMBRE, sangria + n)
            verde_rojo = ROJO if bl else VERDE
            it.setIcon(C_OJO, _icono(lambda p, x, y, oc=oc: pintar_ojo(p, x, y, not oc)))
            it.setIcon(C_CANDADO, _icono(lambda p, x, y, bl=bl, c=verde_rojo: pintar_candado(p, x, y, bl, c)))
            it.setToolTip(C_OJO, _tr("Mostrar") if oc else _tr("Ocultar"))
            it.setToolTip(C_CANDADO, _tr("Desbloquear") if bl else _tr("Bloquear"))
            if k == "folder":
                it.setIcon(C_NOMBRE, _carpeta())
                f = it.font(C_NOMBRE)
                f.setBold(True)
                it.setFont(C_NOMBRE, f)
                padres.append((it, n))
            else:
                it.setIcon(C_NOMBRE, _muestra(rgb))
                it.setIcon(C_AISLAR, _icono(lambda p, x, y, ai=ai: pintar_diana(
                    p, x, y, ai, ROJO if ai else VERDE)))
                it.setToolTip(C_AISLAR, _tr("Volver a ver todas") if ai else _tr("Aislar: ver solo esta capa"))
                it.setToolTip(C_NOMBRE, _tr("Clic: pasar lo seleccionado a «{0}»", n) if scene.selection
                              else _tr("Clic: hacer activa «{0}»", n))
                if oc:
                    it.setForeground(C_NOMBRE, QBrush(GRIS))
                if n == act:
                    it.setIcon(C_ACTIVA, _icono(lambda p, x, y: pintar_lapiz(p, x, y)))
                    f = it.font(C_NOMBRE)
                    f.setBold(True)
                    it.setFont(C_NOMBRE, f)
                    for c in range(5):
                        it.setBackground(c, QBrush(QColor(255, 236, 228)))
                else:
                    it.setToolTip(C_ACTIVA, _tr("Hacer activa"))
        self.arbol.expandAll()
        filas_vistas = max(3, min(14, self._contar()))
        self.arbol.setFixedHeight(28 + filas_vistas * 25)
        self.adjustSize()

    def _contar(self) -> int:
        n = 0
        def contar(it):
            nonlocal n
            n += 1
            if it.isExpanded():
                for i in range(it.childCount()):
                    contar(it.child(i))
        for i in range(self.arbol.topLevelItemCount()):
            contar(self.arbol.topLevelItem(i))
        return n

    def _hecho(self) -> None:
        self.rellenar(forzar=True)
        self._iconos_nativos()
        self.cadena._sincronizar()

    # -- clics --
    def _clic(self, it, col) -> None:
        clave = it.data(C_NOMBRE, Qt.UserRole)
        if not clave or self.vp is None:
            return
        kind, nombre = clave
        vp = self.vp
        panel = self._panel()
        try:
            if col == C_AISLAR and kind == "layer":
                _capas.aislar(vp, nombre)
            elif col in (C_OJO, C_CANDADO) or (col == C_ACTIVA and kind == "layer"):
                if panel is not None and callable(getattr(panel, "click_cell", None)):
                    panel.click_cell(clave, NATIVA[col])
                    _capas._avisar(vp)
                elif col == C_OJO:
                    from core.layers import set_visible
                    set_visible(vp.scene, [nombre], _capas.oculta(vp.scene, nombre))
                    _capas._avisar(vp)
                elif col == C_CANDADO:
                    _capas.bloquear(vp, nombre)
                else:
                    _capas.hacer_activa(vp, nombre)
                if col == C_ACTIVA:
                    vp.flash_status(_tr("Capa activa: «{0}».", nombre), 3000)
            elif kind == "folder":
                if nombre in self._plegadas:
                    self._plegadas.discard(nombre)
                else:
                    self._plegadas.add(nombre)
                self.rellenar(forzar=True)
                return
            elif col == C_NOMBRE:
                self._elegir(nombre)
                return
        except Exception:  # noqa: BLE001
            log.exception("fallo en el mini panel de capas")
        self._hecho()

    def _elegir(self, nombre) -> None:
        """Clic en el nombre de una capa: sin selección, la activa; con
        selección, pregunta y la pasa."""
        vp = self.vp
        scene = vp.scene
        seleccion = list(scene.selection)
        if not seleccion:
            _capas.hacer_activa(vp, nombre)
            vp.flash_status(_tr("Capa activa: «{0}». Lo que dibujes irá a ella.", nombre), 4000)
            self.close()
            return
        if self._confirmar(len(seleccion), nombre, _capas.activa(scene)):
            if _capas.asignar(vp, seleccion, nombre):
                vp.flash_status(_tr("Selección pasada a la capa «{0}».", nombre), 4000)
            else:
                vp.flash_status(_tr("Lo seleccionado ya estaba en «{0}».", nombre), 4000)
            self.close()
            return
        self._hecho()

    def _confirmar(self, n, nombre, act) -> bool:
        self._ocupado = True
        try:
            m = QMessageBox(self)
            m.setIcon(QMessageBox.Question)
            m.setWindowTitle(_tr("Pasar a otra capa"))
            m.setText(_tr("¿Pasar los {0} elementos seleccionados a la capa «{1}»?", n, nombre))
            m.setInformativeText(_tr("La capa activa sigue siendo «{0}».", act))
            si = m.addButton(_tr("Pasar"), QMessageBox.AcceptRole)
            m.addButton(_tr("Cancelar"), QMessageBox.RejectRole)
            m.setDefaultButton(si)
            m.exec()
            return m.clickedButton() is si
        finally:
            self._ocupado = False
            self.activateWindow()

    def _derecho(self, it, global_pos) -> None:
        """El menú de esa fila del panel Capas."""
        if it is None or self.vp is None:
            return
        kind, nombre = it.data(C_NOMBRE, Qt.UserRole)
        panel = self._panel()
        if panel is None or not callable(getattr(panel, "fill_menu", None)):
            return
        self._ocupado = True
        try:
            nativo = panel.item_for(nombre, kind)
            m = QMenu(self)
            panel.fill_menu(m, nativo)
            if not m.isEmpty():
                m.exec(global_pos)
        except Exception:  # noqa: BLE001
            log.exception("sin el menú de la capa %s", nombre)
        finally:
            self._ocupado = False
        _capas._avisar(self.vp)
        self._hecho()
        if self.isVisible():
            self.activateWindow()

    def _accion_barra(self, texto) -> None:
        a = self._accion(texto)
        if a is not None and a.isEnabled():
            a.trigger()
        if self.vp is not None:
            _capas._avisar(self.vp)
        self._hecho()

    def _mas(self, boton) -> None:
        panel = self._panel()
        m = QMenu(self)
        purgar = m.addAction(_tr("Purgar capas sin usar…"))
        m.addSeparator()
        exportar = m.addAction(_tr("Exportar plantilla de capas…"))
        importar = m.addAction(_tr("Importar plantilla de capas…"))
        m.addSeparator()
        abrir = m.addAction(_tr("Abrir el panel Capas"))
        for a in (purgar, exportar, importar):
            a.setEnabled(panel is not None)
        self._ocupado = True
        try:
            elegida = m.exec(boton.mapToGlobal(QPoint(0, boton.height())))
            if elegida is purgar:
                panel._on_purge()
            elif elegida is exportar:
                panel.export_template()
            elif elegida is importar:
                panel.import_template()
            elif elegida is abrir:
                a = self._accion("Panel de capas")
                self.close()
                if a is not None:
                    a.trigger()
                return
        except Exception:  # noqa: BLE001
            log.exception("fallo en «⋯» del mini panel de capas")
        finally:
            self._ocupado = False
        if self.vp is not None:
            _capas._avisar(self.vp)
        self._hecho()

    # -- nuevas --
    def _nueva_capa(self) -> None:
        vp = self.vp
        if vp is None:
            return
        scene = vp.scene
        nombre = self._pedir(_tr("Nueva capa"), _tr("Nombre de la capa:"), _tr("Capa {0}", len(scene.layers)))
        if not nombre:
            return
        try:
            from core.layers import Layer, unique_name
            nombre = unique_name({ly.name for ly in scene.layers}, nombre) \
                if scene.layer(nombre) is not None else nombre
            scene.layers.append(Layer(nombre))
            _capas.hacer_activa(vp, nombre)
            vp.flash_status(_tr("Capa «{0}» creada y activa.", nombre), 4000)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo crear la capa")
        self._hecho()

    def _nueva_carpeta(self) -> None:
        vp = self.vp
        if vp is None:
            return
        nombre = self._pedir(_tr("Nueva carpeta"), _tr("Nombre de la carpeta:"), _tr("Carpeta"))
        if not nombre:
            return
        try:
            from core.layers import add_folder
            add_folder(vp.scene, nombre)
            _capas._avisar(vp)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo crear la carpeta")
        self._hecho()

    def _pedir(self, titulo, rotulo, valor) -> str | None:
        """Un nombre, en una ventanita con micrófono."""
        self._ocupado = True
        try:
            d = QDialog(self)
            d.setWindowTitle(titulo)
            lay = QVBoxLayout(d)
            lay.addWidget(QLabel(rotulo))
            campo = QLineEdit(valor)
            campo.selectAll()
            try:
                from ._voz import con_microfono
                con_microfono(campo, d)
            except Exception:  # noqa: BLE001
                pass
            lay.addWidget(campo)
            fila = QHBoxLayout()
            fila.addStretch(1)
            ok = QPushButton(_tr("Aceptar"))
            no = QPushButton(_tr("Cancelar"))
            ok.setDefault(True)
            ok.clicked.connect(d.accept)
            no.clicked.connect(d.reject)
            fila.addWidget(ok)
            fila.addWidget(no)
            lay.addLayout(fila)
            d.setMinimumWidth(300)
            hecho = d.exec() == QDialog.Accepted
            texto = campo.text().strip()
            return texto if hecho and texto else None
        finally:
            self._ocupado = False
            if self.isVisible():
                self.activateWindow()

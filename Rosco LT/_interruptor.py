# SPDX-License-Identifier: GPL-3.0-or-later
"""El interruptor de Rosco LT: apagarla y encenderla sin reiniciar
IngeTrazo. Se apaga y se enciende con el botón de encendido del principio de
la barra «Rosco LT» (hundido y con disco naranja si está encendida; en gris
y, apagada, en la barra solo quedan él, Reiniciar y Tareas) o con la casilla Extensiones ▸
Rosco LT ▸ Rosco LT activado; también se apaga en Opciones ▸ Desactivar
Rosco LT (el botoncito bajo el anillo).

También pone el submenú Extensiones ▸ Rosco LT, donde van todas sus
órdenes (``entrada``): la barra de dibujo, la barra de modificar, Alinear, Reiniciar, las Tareas y la
casilla. Las Tareas (``_notas``) no se apagan: siguen a mano con ella apagada.

Apagada, las piezas siguen cargadas pero no hacen nada: sus filtros de
eventos, overlays y envoltorios de las herramientas nativas (selección
múltiple, clic en vacío, cursor lápiz) dejan pasar todo tal cual (miran
``ENCENDIDA``), los relojes se paran, las ventanitas se esconden y sus
entradas de menú y botones se ocultan. La elección se recuerda: si
IngeTrazo se cierra con ella apagada, arranca apagada.
"""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

TITULO_ACTIVAR = "Activar Rosco LT"
TIP_ACTIVAR = "Vuelve a poner en marcha Rosco LT (la barra, Alinear y Reiniciar)."
TITULO_CASILLA = "Rosco LT activado"
TIP_CASILLA = "Enciende o apaga Rosco LT al momento, sin reiniciar IngeTrazo."
TITULO_BOTON = "Interruptor de Rosco LT"
TIP_ENCENDIDA = "Rosco LT encendido. Clic para apagarlo (sin reiniciar)."
TIP_APAGADA = "Rosco LT apagado. Clic para encenderlo."
AVISO_APAGADA = ("Rosco LT desactivado. Para volver: el interruptor de la barra "
                 "«Rosco LT» o Extensiones ▸ Rosco LT.")
ACCENT = "#f37329"
# El orden de las órdenes en Extensiones ▸ Rosco LT (se cargan en otro).
ORDEN = ("barra_dibujo", "barra_modificar", "alinear", "reiniciar", "notas_modelo", "notas_global",
         "interruptor")

# Lo miran los filtros, overlays y envoltorios de todas las piezas.
ENCENDIDA = True


def _ajustes() -> QSettings:
    from ._ajustes import ajustes
    return ajustes()


def guardada() -> bool:
    """Cómo quedó la última vez (encendida, si nunca se tocó)."""
    valor = _ajustes().value("general/activa", True)
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true")
    return bool(valor)


def _limpio(texto: str) -> str:
    return texto.split("\t")[0].replace("&", "").strip()


def _buscar(win, texto: str, excluir=()):
    """La acción de menú más reciente con ese texto (por si
    ``add_menu_action`` no la devuelve)."""
    buscado = _limpio(texto)
    fuera = {id(a) for a in excluir}
    return next((a for a in reversed(win.findChildren(QAction))
                 if _limpio(a.text()) == buscado and id(a) not in fuera), None)


def _submenu(app):
    """Extensiones ▸ Rosco LT (None si esta IngeTrazo no tiene ``add_menu``)."""
    win = app.window
    if not hasattr(win, "_rosco_lt_submenu"):
        menu = None
        crear = getattr(app, "add_menu", None)
        if callable(crear):
            try:
                menu = crear("Rosco LT")
            except Exception:  # noqa: BLE001 — las órdenes van sueltas
                log.exception("no se pudo crear el submenú Rosco LT")
        win._rosco_lt_submenu = menu
    return win._rosco_lt_submenu


def entrada(app, clave: str, texto: str, funcion, tip: str, shortcut=None):
    """Una orden de Rosco LT en Extensiones ▸ Rosco LT, en su sitio según
    ``ORDEN``. Sin submenú, suelta en Extensiones (como antes)."""
    menu = _submenu(app)
    if menu is None:
        extra = {"shortcut": shortcut} if shortcut else {}
        return app.add_menu_action(_tr(texto), funcion, tip=_tr(tip), **extra)
    accion = QAction(_tr(texto), app.window)
    accion.setToolTip(_tr(tip))
    accion.setStatusTip(_tr(tip))
    if shortcut:
        accion.setShortcut(QKeySequence(shortcut))
    accion.triggered.connect(lambda _c=False: funcion())
    accion._rosco_lt_orden = ORDEN.index(clave)
    despues = next((a for a in menu.actions()
                    if getattr(a, "_rosco_lt_orden", -1) > accion._rosco_lt_orden), None)
    if despues is None:
        menu.addAction(_tr(accion))
    else:
        menu.insertAction(despues, accion)
    return accion


def apuntar(app, accion, texto: str) -> None:
    """Una entrada de menú de Rosco LT, para ocultarla al apagar."""
    win = app.window
    lista = getattr(win, "_rosco_lt_menu", None)
    if lista is None:
        lista = win._rosco_lt_menu = []
    if accion is None:
        accion = _buscar(win, _tr(texto), lista)
    if accion is None:
        log.warning("no encontré la entrada «%s»: seguirá a la vista apagada", texto)
        return
    lista.append(accion)


def apagada(app) -> bool:
    """Para las órdenes de Rosco LT que lleguen con ella apagada (el menú
    del botón derecho, un atajo): avisa y dice que no se haga nada."""
    if ENCENDIDA:
        return False
    app.viewport.flash_status(_tr(AVISO_APAGADA), 5000)
    return True


def _encendido(tinta) -> QPixmap:
    """El símbolo de encendido (viewBox 48 → 64 px): disco naranja, arco
    abierto arriba y la rayita que entra en él."""
    k = 64.0 / 48.0
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    disco = QColor(ACCENT)
    disco.setAlphaF(0.85)
    p.setBrush(QBrush(disco))
    p.drawEllipse(QPointF(24 * k, 26 * k), 11 * k, 11 * k)
    p.setPen(QPen(tinta, 3.4 * k, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    # Radio 15 alrededor del disco, abierto arriba (de 124° a 56°, en grados Qt).
    p.drawArc(QRectF(9 * k, 11 * k, 30 * k, 30 * k), 124 * 16, 292 * 16)
    p.drawLine(QPointF(24 * k, 6 * k), QPointF(24 * k, 24 * k))
    p.end()
    return pm


def _icono_interruptor(win) -> QIcon:
    """Marcado (encendida), en su baldosa azul; sin marcar, en la gris
    (``_baldosa``). Si la baldosa falla, el símbolo de siempre."""
    try:
        from . import _baldosa
        negro = _encendido(QColor(0, 0, 0)).toImage()
        return _baldosa.icono(
            lambda px: negro.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation),
            off_gris=True)
    except Exception:  # noqa: BLE001 — queda el símbolo de siempre
        log.exception("no se pudo hacer el interruptor en baldosa")
    color = QIcon(_encendido(win.palette().windowText().color()))
    icono = QIcon()
    for lado in (16, 24, 32, 48, 64):
        talla = QSize(lado, lado)
        icono.addPixmap(color.pixmap(talla), QIcon.Mode.Normal, QIcon.State.On)
        icono.addPixmap(color.pixmap(talla, QIcon.Mode.Disabled),
                        QIcon.Mode.Normal, QIcon.State.Off)
    return icono


def _parar(*relojes) -> None:
    for reloj in relojes:
        if reloj is not None:
            reloj.stop()


def _esconder(*ventanas) -> None:
    for w in ventanas:
        if w is not None and w.isVisible():
            w.hide()


class Interruptor:
    def __init__(self, app) -> None:
        self.app = app
        self.menu = None                      # la casilla (o «Activar Rosco LT»)
        self.boton = None                     # el interruptor de la barra
        self.raya = None                      # la raya que lo separa de los demás

    # -- instalación --
    def encendida(self) -> bool:
        return ENCENDIDA

    def _otros(self) -> list:
        """Los interruptores de las demás variantes instaladas: solo puede
        funcionar una a la vez (usan los mismos clics y atajos)."""
        return [o for o in getattr(self.app.window, "_roscos_interruptores", []) if o is not self]

    def instalar(self) -> None:
        app = self.app
        win = app.window
        if not hasattr(win, "_roscos_interruptores"):
            win._roscos_interruptores = []
        win._roscos_interruptores.append(self)
        submenu = _submenu(app)
        if submenu is not None:
            submenu.addSeparator()
            self.menu = QAction(_tr(TITULO_CASILLA), win)
            self.menu.setCheckable(True)
            self.menu.setToolTip(_tr(TIP_CASILLA))
            self.menu.setStatusTip(_tr(TIP_CASILLA))
            self.menu._rosco_lt_orden = ORDEN.index("interruptor")
            self.menu.triggered.connect(self._alternar)
            submenu.addAction(_tr(self.menu))
        else:
            accion = app.add_menu_action(_tr(TITULO_ACTIVAR), self.encender, tip=_tr(TIP_ACTIVAR))
            self.menu = accion if accion is not None else _buscar(win, _tr(TITULO_ACTIVAR))
        try:
            # El interruptor va el primero, a la izquierda de «Abrir la barra»,
            # con la raya detrás; las demás piezas ya pusieron sus botones.
            from ._barra import barra
            tb = barra(app)
            primera = next(iter(tb.actions()), None)
            self.boton = QAction(_icono_interruptor(win), _tr(TITULO_BOTON), win)
            self.boton.setCheckable(True)
            self.boton.triggered.connect(self._alternar)
            if primera is None:
                tb.addAction(_tr(self.boton))
                self.raya = tb.addSeparator()
            else:
                tb.insertAction(primera, self.boton)
                self.raya = tb.insertSeparator(primera)
            tb._rosco_lt_refs.append(self.boton)
        except Exception:  # noqa: BLE001 — queda el menú
            log.exception("no se pudo poner el interruptor en la barra")
            self.boton = None
        self._ver_acciones(ENCENDIDA)

    # -- las piezas --
    def _cadenas(self) -> list:
        return list((getattr(self.app.window, "_rosco_lt_barra_dibujo", None) or {}).values())

    def _barras_modificar(self) -> list:
        return list((getattr(self.app.window, "_rosco_lt_barra_modificar", None) or {}).values())

    def _de_rosco_lt(self, tool) -> bool:
        if tool is None:
            return False
        for c in self._cadenas():
            if c._es_base(tool) or tool is c.push:
                return True
        if any(tool is b.referencia for b in self._barras_modificar()):
            return True
        alinear = getattr(self.app.window, "_rosco_lt_alinear", None)
        return alinear is not None and tool is getattr(alinear, "tool", None)

    def _a_seleccionar(self) -> None:
        """Si la herramienta activa es de Rosco LT, el Seleccionar de
        IngeTrazo (la orden a medias se cancela, como con Esc)."""
        win, vp = self.app.window, self.app.viewport
        tool = vp.active_tool
        if not self._de_rosco_lt(tool):
            return
        cancelar = getattr(tool, "on_cancel", None)
        if callable(cancelar):
            try:
                cancelar(vp)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo cancelar la orden en curso")
        activar = getattr(win, "_activate_tool", None)          # interno de 0.5.8
        if callable(activar):
            try:
                activar("select")
                return
            except Exception:  # noqa: BLE001
                log.exception("_activate_tool('select') falló")
        nativo = (getattr(win, "_tools", None) or {}).get("select")
        if nativo is not None:
            vp.set_active_tool(nativo)

    def _ver_acciones(self, encendida: bool) -> None:
        """Encendida: sus entradas y botones; apagada, solo el interruptor,
        la casilla del submenú y los botones marcados ``_rosco_lt_siempre``
        (Reiniciar). Las Tareas no están en estas listas: no se tocan."""
        from PySide6.QtWidgets import QToolBar
        from ._barra import TOOLBAR
        win = self.app.window
        for a in getattr(win, "_rosco_lt_menu", None) or []:
            a.setVisible(encendida)
        tb = win.findChild(QToolBar, TOOLBAR)
        for a in getattr(tb, "_rosco_lt_refs", None) or []:
            if a is not self.boton and not getattr(a, "_rosco_lt_siempre", False):
                a.setVisible(encendida)
        if self.menu is not None:
            if self.menu.isCheckable():          # la casilla del submenú, siempre
                self.menu.setChecked(encendida)
            else:
                self.menu.setVisible(not encendida)
        if self.raya is not None:
            self.raya.setVisible(encendida)
        if self.boton is not None:
            self.boton.setChecked(encendida)
            tip = TIP_ENCENDIDA if encendida else TIP_APAGADA
            self.boton.setToolTip(_tr(tip))
            self.boton.setStatusTip(_tr(tip))

    def _alternar(self, marcada: bool) -> None:
        if marcada:
            self.encender()
        else:
            self.apagar()

    # -- apagar / encender --
    def apagar(self, arranque: bool = False) -> None:
        """``arranque``: al cargar, porque se cerró apagada (sin aviso)."""
        global ENCENDIDA
        if not ENCENDIDA:
            return
        vp = self.app.viewport
        if not arranque:
            _ajustes().setValue("general/activa", False)
            self._a_seleccionar()
        ENCENDIDA = False
        for c in self._cadenas():
            try:
                _parar(c._reloj, c._reposo, getattr(c.crono, "_tic", None))
                if c.cancelar is not None:
                    c.cancelar.esconder()
                if c.medidas is not None and c.medidas.isVisible():
                    c.medidas.hide()
                    c.medidas.clave = None
                _esconder(c.win, c.panel_tiempo, getattr(c, "calculadora", None),
                          getattr(c.navegador, "ventana", None),
                          getattr(c.menus_arbol, "ventana", None))
                # Sin la diana no habría desde dónde volver a mostrarlo.
                if getattr(c, "limpieza", None) is not None:
                    c.limpieza.todo(False)
                c._lazo = None
                c._quitar_cursor(vp)
                c._soltar()
            except Exception:  # noqa: BLE001 — las demás piezas se apagan igual
                log.exception("no se pudo apagar la barra de dibujo del todo")
        for b in self._barras_modificar():
            try:
                _parar(b._reloj, b._reposo)
                _esconder(b.win)
                b.submenu_visible = False
                b._quitar_cursor(vp)
                b._soltar()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo apagar la barra de modificar del todo")
        self._ver_acciones(False)
        vp.update()
        if not arranque:
            vp.flash_status(_tr(AVISO_APAGADA), 8000)
        log.info("Rosco LT desactivado")

    def encender(self) -> None:
        global ENCENDIDA
        if ENCENDIDA:
            return
        for otro in self._otros():               # solo una variante a la vez
            try:
                otro.apagar()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo apagar la otra variante")
        ENCENDIDA = True
        _ajustes().setValue("general/activa", True)
        vp = self.app.viewport
        for c in self._cadenas():
            try:
                c._reloj.start()
                if c.crono is not None:
                    c.crono._tic.start()
                c._sincronizar()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo encender la barra de dibujo")
        for b in self._barras_modificar():
            try:
                b._reloj.start()
                b._sincronizar()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo encender la barra de modificar")
        self._ver_acciones(True)
        vp.update()
        vp.flash_status(_tr("Rosco LT activado."), 4000)
        log.info("Rosco LT activado")

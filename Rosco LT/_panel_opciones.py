# SPDX-License-Identifier: GPL-3.0-or-later
"""El panel de Opciones del rosco: secciones a la izquierda y su contenido a
la derecha, con «Fijar la barra aquí» siempre arriba. Los cambios se aplican
al momento y se recuerdan (los mismos ajustes que el menú de antes)."""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QRadioButton, QSlider, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import _edicion, _seleccion
from ._idioma import _tr

from ._ajustes import registro

log = registro("opciones")
class ComboTemas(QComboBox):
    """El desplegable de temas: al pasar el ratón por cada uno, al lado de
    la lista sale la imagen del rosco con ese tema (como el menú de antes)."""

    def __init__(self, cadena) -> None:
        super().__init__()
        self.cadena = cadena
        self._imagenes: dict = {}
        self.vista = QLabel("", None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.vista.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.vista.setStyleSheet("QLabel { background: #fafaf8; border: 1.5px solid #d62222;"
                                 " border-radius: 6px; padding: 6px; }")
        self.highlighted.connect(self._mostrar)

    def _imagen(self, clave):
        pm = self._imagenes.get(clave)
        if pm is None:
            pm = self._imagenes[clave] = self.cadena.previsualizar(clave)
        return pm

    def _mostrar(self, i: int) -> None:
        clave = self.itemData(i)
        lista = self.view()
        if clave is None or not lista.isVisible():
            self.vista.hide()
            return
        try:
            self.vista.setPixmap(self._imagen(clave))
        except Exception:  # noqa: BLE001 — sin vista previa, el desplegable sigue
            log.exception("no se pudo previsualizar el tema %s", clave)
            self.vista.hide()
            return
        self.vista.adjustSize()
        caja = lista.window().frameGeometry()
        fila = lista.visualRect(self.model().index(i, 0))
        y = lista.viewport().mapToGlobal(fila.topLeft()).y() - 20
        pos = QPoint(caja.right() + 8, y)
        pantalla = lista.screen().availableGeometry()
        if pos.x() + self.vista.width() > pantalla.right():
            pos.setX(caja.left() - 8 - self.vista.width())
        pos.setY(max(pantalla.top(), min(pos.y(), pantalla.bottom() - self.vista.height())))
        self.vista.move(pos)
        self.vista.show()
        self.vista.raise_()

    def showPopup(self) -> None:  # noqa: N802
        super().showPopup()
        QTimer.singleShot(0, lambda: self._mostrar(self.currentIndex()))

    def hidePopup(self) -> None:  # noqa: N802
        self.vista.hide()
        super().hidePopup()

    def hideEvent(self, ev) -> None:  # noqa: N802
        self.vista.hide()
        super().hideEvent(ev)

ACENTO = "#5b5bd6"
ACENTO_OSCURO = "#3c3489"
ACENTO_CLARO = "#ecebfd"

_ESTILO = f"""
QWidget {{ color: #2b2b30; }}
QFrame#panel {{ background: #fbfbfa; border: 1px solid #c9c6e8; border-radius: 10px; }}
QRadioButton {{ color: #2b2b30; spacing: 6px; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border-radius: 7px; border: 1px solid #9e9ab8;
                          background: white; }}
QRadioButton::indicator:checked {{ border: 4px solid {ACENTO}; width: 6px; height: 6px; }}
QSlider::groove:horizontal {{ height: 4px; background: #dcdbe6; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACENTO}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
                             background: white; border: 1px solid {ACENTO}; }}
QComboBox QAbstractItemView {{ background: white; color: #2b2b30;
                              selection-background-color: {ACENTO_CLARO}; selection-color: {ACENTO_OSCURO}; }}
QWidget#cabecera {{ border-bottom: 1px solid #e3e1ee; }}
QLabel#titulo {{ font-weight: 600; color: #222; }}
QLabel#seccion {{ color: #6b6a75; margin-top: 6px; }}
QLabel#nota {{ color: #6b6a75; }}
QListWidget#secciones {{ border: none; border-right: 1px solid #e3e1ee; background: transparent;
                         outline: 0; }}
QListWidget#secciones::item {{ padding: 6px 10px; border-radius: 0; color: #333; }}
QListWidget#secciones::item:selected {{ background: {ACENTO_CLARO}; color: {ACENTO_OSCURO}; }}
QListWidget#secciones::item:hover:!selected {{ background: #f1f0f6; }}
QWidget#fijar {{ border-bottom: 1px solid #e3e1ee; }}
QLabel#fijar_texto {{ color: {ACENTO_OSCURO}; }}
QToolButton#cerrar {{ border: none; color: #666; font-size: 14px; padding: 0 4px; }}
QToolButton#cerrar:hover {{ color: #d62222; }}
QPushButton {{ border: 1px solid #c9c6e8; border-radius: 6px; padding: 5px 10px; background: white; }}
QPushButton:hover {{ background: {ACENTO_CLARO}; }}
QPushButton#apagar {{ color: #b42323; border-color: #efc2c2; }}
QPushButton#apagar:hover {{ background: #fcebeb; }}
QComboBox {{ border: 1px solid #c9c6e8; border-radius: 6px; padding: 3px 8px; background: white;
             color: #2b2b30; min-width: 120px; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QPushButton#pestana {{ color: #555; padding: 4px 12px; }}
QPushButton#pestana:checked {{ background: {ACENTO}; border-color: {ACENTO_OSCURO}; color: white;
                              font-weight: 600; }}
QScrollArea#zona_ayuda {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #c9c6e8; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACENTO}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


class Interruptor(QAbstractButton):
    """Un interruptor redondeado (sí/no)."""

    def __init__(self, activo: bool, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(activo))
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(34, 18)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACENTO) if self.isChecked() else QColor("#c9c8cf"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.right() - d - 2 if self.isChecked() else r.left() + 2
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 2, d, d))
        p.end()


def _panel_ayuda():
    """La ayuda (solo si la edición la lleva; sin ella no hay sección Ayuda
    ni ayuda junto a los clics)."""
    if not _edicion.con("panel_ayuda"):
        raise RuntimeError("esta edición no lleva la ayuda")
    from . import _panel_ayuda as ayuda
    return ayuda


class PanelOpciones(QWidget):
    SECCIONES = ("Clics", "Órdenes", "Dictado", "Aspecto", "Guardar", "Ayuda")
    if not _edicion.con("panel_ayuda"):
        SECCIONES = SECCIONES[:-1]
    TAMANO = (480, 400)
    TAMANOS = {"Ayuda": (640, 600)}        # la que necesita más sitio para leerse
    AYUDA_CLICS_W = 440                    # el panel lateral de la ayuda de los clics

    def __init__(self, cadena, pagina: int = 0) -> None:
        super().__init__(cadena.app.window, Qt.Tool | Qt.FramelessWindowHint)
        self.cadena = cadena
        self._arrastre = None
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(_ESTILO)
        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(0, 0, 0, 0)
        marco = QFrame(self)
        marco.setObjectName("panel")
        fuera.addWidget(marco)
        col = QVBoxLayout(marco)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._cabecera())
        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        self.lista = QListWidget()
        self.lista.setObjectName("secciones")
        self.lista.setFixedWidth(112)
        for s in self.SECCIONES:
            self.lista.addItem(_tr(s))
        cuerpo.addWidget(self.lista)
        derecha = QVBoxLayout()
        derecha.setContentsMargins(12, 6, 12, 10)
        derecha.setSpacing(4)
        derecha.addWidget(self._fila_fijar())
        self.paginas = QStackedWidget()
        for hacer in (self._p_clics, self._p_ordenes, self._p_dictado, self._p_aspecto,
                      self._p_guardar, self._p_ayuda)[:len(self.SECCIONES)]:
            self.paginas.addWidget(hacer())
        derecha.addWidget(self.paginas, 1)
        cuerpo.addLayout(derecha, 1)
        col.addLayout(cuerpo, 1)
        self.lista.currentRowChanged.connect(self.paginas.setCurrentIndex)
        self.lista.currentRowChanged.connect(self._ajustar_tamano)
        self.lista.setCurrentRow(max(0, min(pagina, len(self.SECCIONES) - 1)))
        self._ajustar_tamano(self.lista.currentRow())
        for campo in (*self.findChildren(QComboBox), *self.findChildren(QSlider)):
            campo.installEventFilter(self)

    # -- piezas --
    def _cabecera(self) -> QWidget:
        w = QWidget()
        w.setObjectName("cabecera")
        fila = QHBoxLayout(w)
        fila.setContentsMargins(12, 8, 8, 8)
        icono = QLabel("⚙")
        icono.setStyleSheet(f"color: {ACENTO}; font-size: 15px;")
        titulo = QLabel(_tr("Opciones del rosco"))
        titulo.setObjectName("titulo")
        cerrar = QToolButton()
        cerrar.setObjectName("cerrar")
        cerrar.setText("✕")
        cerrar.setToolTip(_tr("Cerrar (Esc)"))
        cerrar.clicked.connect(self.close)
        fila.addWidget(icono)
        fila.addWidget(titulo, 1)
        fila.addWidget(cerrar)
        w.mousePressEvent = self._empezar_arrastre
        w.mouseMoveEvent = self._arrastrar
        w.mouseReleaseEvent = lambda _e: setattr(self, "_arrastre", None)
        w.setCursor(Qt.SizeAllCursor)
        return w

    def _fila(self, texto: str, widget: QWidget, clase: str = "") -> QWidget:
        w = QWidget()
        if clase:
            w.setObjectName(clase)
        fila = QHBoxLayout(w)
        fila.setContentsMargins(0, 4, 0, 4)
        etiqueta = QLabel(texto)
        etiqueta.setWordWrap(True)
        if clase:
            etiqueta.setObjectName(clase + "_texto")
        fila.addWidget(etiqueta, 1)
        fila.addWidget(widget)
        return w

    def _seccion(self, texto: str) -> QLabel:
        e = QLabel(texto)
        e.setObjectName("seccion")
        return e

    def _interruptor_opcion(self, clave: str, texto: str) -> QWidget:
        sw = Interruptor(_seleccion.opcion(clave))

        def cambiar(valor) -> None:
            _seleccion.poner_opcion(clave, valor)
            self.cadena.app.viewport.flash_status(_tr("{0}: {1}.", texto, _tr("sí") if valor else _tr("no")), 2500)
        sw.toggled.connect(cambiar)
        return self._fila(texto, sw)

    def _fila_fijar(self) -> QWidget:
        self.sw_fijar = Interruptor(bool(self.cadena.anclada))

        def cambiar(valor) -> None:
            if bool(self.cadena.anclada) != bool(valor):
                self.cadena._pulsar_chincheta(self.cadena.app.viewport, "chincheta")
            self.sw_fijar.blockSignals(True)
            self.sw_fijar.setChecked(bool(self.cadena.anclada))
            self.sw_fijar.blockSignals(False)
        self.sw_fijar.toggled.connect(cambiar)
        return self._fila(_tr("Fijar la barra aquí (chincheta)"), self.sw_fijar, "fijar")

    def _pagina(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        return w, col

    def _deslizador(self, texto, minimo, maximo, valor, unidad, al_cambiar, paso=1) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 4, 0, 2)
        col.setSpacing(2)
        col.addWidget(QLabel(texto))
        fila = QHBoxLayout()
        barra = QSlider(Qt.Horizontal)
        barra.setRange(minimo, maximo)
        barra.setValue(valor)
        barra.setSingleStep(paso)
        lectura = QLabel(f"{valor} {unidad}")
        lectura.setMinimumWidth(48)

        def cambiar(v) -> None:
            v = int(round(v / paso)) * paso
            lectura.setText(f"{v} {unidad}")
            al_cambiar(v)
        barra.valueChanged.connect(cambiar)
        fila.addWidget(barra, 1)
        fila.addWidget(lectura)
        col.addLayout(fila)
        return w

    # -- páginas --
    def _p_clics(self) -> QWidget:
        """Las opciones de los clics y, al lado, su ayuda con la pantallita
        animada, entera y sin barra (el panel se ensancha para ella; sin la
        ayuda en esta edición, solo las opciones)."""
        w = QWidget()
        fila = QHBoxLayout(w)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        izq, col = self._pagina()
        col.addWidget(self._seccion(_tr("Botón izquierdo")))
        for clave, texto in _seleccion.OPCIONES:
            col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        col.addWidget(self._seccion(_tr("Botón derecho")))
        for clave, texto in _seleccion.DERECHO:
            col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        nota = QLabel(_tr("A la derecha, qué hace cada clic: pasa el ratón por una fila y la "
                          "pantallita enseña ese gesto."))
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        if not _edicion.con("panel_ayuda"):
            nota.setText(_tr("Izquierdo: hacer o elegir. Derecho: el rosco, terminar o volver atrás. "
                             "Doble: otra vez o cancelar."))
        col.addWidget(nota)
        col.addStretch(1)
        fila.addWidget(izq, 1)
        if not _edicion.con("panel_ayuda"):
            return w
        Lienzo = _panel_ayuda().Lienzo
        lado = QFrame()
        lado.setObjectName("ayuda_lado")
        lado.setStyleSheet("QFrame#ayuda_lado { background: #fbfbfa; border-left: 1px solid #e3e1ee; }")
        caja = QVBoxLayout(lado)
        caja.setContentsMargins(6, 2, 0, 0)
        caja.setSpacing(2)
        caja.addWidget(self._seccion(_tr("Ayuda de los clics")))
        self.puntos_ayuda = self._puntos_que_caben()
        self.ayuda_clics = Lienzo(puntos=self.puntos_ayuda)
        self.ayuda_clics.setFixedWidth(self.AYUDA_CLICS_W)
        caja.addWidget(self.ayuda_clics, 1)
        fila.addWidget(lado)
        return w

    def _puntos_que_caben(self) -> float:
        """La letra de la ayuda de los clics: la mayor (hasta 8,5) con la
        que cabe entera en la pantalla."""
        alto_para = _panel_ayuda().alto_para
        try:
            libre = self.cadena.app.window.screen().availableGeometry().height() - 120
        except Exception:  # noqa: BLE001
            libre = 900
        for puntos in (8.5, 8.0, 7.5, 7.0, 6.5):
            if alto_para(self.AYUDA_CLICS_W, puntos) <= libre:
                return puntos
        return 6.5

    def _tamano_clics(self) -> tuple:
        alto_para = _panel_ayuda().alto_para
        alto = alto_para(self.AYUDA_CLICS_W, getattr(self, "puntos_ayuda", 8.5))
        return (self.TAMANO[0] + self.AYUDA_CLICS_W + 20, max(self.TAMANO[1], alto + 100))

    def _p_ordenes(self) -> QWidget:
        w, col = self._pagina()
        col.addWidget(self._seccion(_tr("Al terminar una orden")))
        for clave, texto in _seleccion.TRAS_ORDEN:
            col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        col.addWidget(self._seccion(_tr("Mantener pulsado un botón")))
        for clave, texto in _seleccion.PULSACION:
            col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        for titulo, lista in (("Teclado", _seleccion.TECLADO), ("Vista previa", _seleccion.VISTA)):
            if not lista:                    # sin casillas en esta edición
                continue
            col.addWidget(self._seccion(_tr(titulo)))
            for clave, texto in lista:
                col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        col.addStretch(1)
        return w

    def _p_dictado(self) -> QWidget:
        w, col = self._pagina()
        col.addWidget(self._seccion(_tr("Dictado de medidas")))
        for clave, texto in _seleccion.DICTADO:
            col.addWidget(self._interruptor_opcion(clave, _tr(texto)))
        col.addStretch(1)
        return w

    def _p_aspecto(self) -> QWidget:
        from . import _idioma, _temas
        c = self.cadena
        w, col = self._pagina()
        temas = ComboTemas(c)
        claves = list(_temas.TEMAS)
        for t in _temas.TEMAS.values():
            temas.addItem(_tr(t.nombre), t.clave)
            temas.setItemData(temas.count() - 1, _tr(t.descripcion), Qt.ToolTipRole)
        temas.setCurrentIndex(claves.index(c.tema.clave) if c.tema.clave in claves else 0)
        temas.currentIndexChanged.connect(lambda i: c.poner_tema(temas.itemData(i)))
        col.addWidget(self._fila(_tr("Tema de la barra"), temas))
        col.addWidget(self._deslizador(_tr("Tamaño de la barra"), round(_temas.ESCALA_MIN * 100),
                                       round(_temas.ESCALA_MAX * 100), round(c.escala * 100), "%",
                                       lambda v: c.poner_escala(v / 100.0), 5))
        col.addWidget(self._seccion(_tr("Submenús de las órdenes")))
        formas = QWidget()
        fila = QHBoxLayout(formas)
        fila.setContentsMargins(0, 0, 0, 0)
        grupo = QButtonGroup(formas)
        actual = "radial" if getattr(c, "submenus_radiales", False) else "rect"
        for clave, texto in _seleccion.SUBMENUS:
            b = QRadioButton(_tr(texto))
            b.setChecked(clave == actual)
            b.toggled.connect(lambda si, k=clave: si and self._poner_submenus(k))
            grupo.addButton(b)
            fila.addWidget(b)
        fila.addStretch(1)
        col.addWidget(formas)
        # Dónde sale: a la derecha del cursor o centrado bajo él.
        sitios = QWidget()
        fila = QHBoxLayout(sitios)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(QLabel(_tr("Sitio:")))
        grupo_sitio = QButtonGroup(sitios)
        for clave, texto in _seleccion.SITIOS_SUBMENU:
            b = QRadioButton(_tr(texto))
            b.setChecked(clave == c.sitio_submenu)
            b.toggled.connect(lambda si, k=clave: si and self._poner_sitio(k))
            grupo_sitio.addButton(b)
            fila.addWidget(b)
        fila.addStretch(1)
        col.addWidget(sitios)
        self.distancia = self._deslizador(_tr("Distancia del cursor al submenú"), _seleccion.DISTANCIA_MIN,
                                          _seleccion.DISTANCIA_MAX, c.distancia_submenu, "px",
                                          c.poner_distancia_submenu, 2)
        self.distancia.setEnabled(c.sitio_submenu != "centro")   # solo vale «a la derecha»
        col.addWidget(self.distancia)
        self.escala_rosco = self._deslizador(_tr("Tamaño del rosco de submenús"), _seleccion.ESCALA_ROSCO_MIN,
                                             _seleccion.ESCALA_ROSCO_MAX, c.escala_rosco, "%",
                                             c.poner_escala_rosco, 5)
        self.escala_rosco.setEnabled(actual == "radial")
        col.addWidget(self.escala_rosco)
        lenguas = QComboBox()
        for codigo, nombre in _idioma.IDIOMAS:
            lenguas.addItem(nombre, codigo)
        codigos = [k for k, _n in _idioma.IDIOMAS]
        lenguas.setCurrentIndex(codigos.index(_idioma.actual()) if _idioma.actual() in codigos else 0)
        lenguas.currentIndexChanged.connect(lambda i: self._poner_idioma(lenguas.itemData(i)))
        col.addWidget(self._fila(_tr("Idioma"), lenguas))
        col.addStretch(1)
        return w

    def _p_guardar(self) -> QWidget:
        w, col = self._pagina()
        col.addWidget(self._seccion(_tr("Configuración")))
        nota = QLabel(_tr("Guarda en un archivo todos los ajustes del rosco (tema, huecos, opciones, "
                          "idioma…) para cargarlos después o en otro equipo."))
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        col.addWidget(nota)
        fila = QHBoxLayout()
        for texto, que in (("Exportar la configuración…", "exportar"), ("Importar una configuración…", "importar")):
            b = QPushButton(_tr(texto))
            b.clicked.connect(lambda _c=False, q=que: QTimer.singleShot(
                0, lambda: _seleccion._configuracion(self.cadena, q)))
            fila.addWidget(b)
        col.addLayout(fila)
        col.addStretch(1)
        return w

    def _p_ayuda(self) -> QWidget:
        PaginaAyuda = _panel_ayuda().PaginaAyuda
        return PaginaAyuda()

    # -- acciones --
    def _poner_submenus(self, clave: str) -> None:
        c = self.cadena
        _seleccion.poner_forma_submenus(clave)
        c.submenus_radiales = clave == "radial"
        self.escala_rosco.setEnabled(c.submenus_radiales)
        c._sincronizar()

    def _poner_sitio(self, clave: str) -> None:
        self.cadena.poner_sitio_submenu(clave)
        self.distancia.setEnabled(clave != "centro")

    def _poner_idioma(self, codigo: str) -> None:
        from . import _idioma
        _idioma.poner(codigo)
        self.cadena.idioma_cambiado()
        # El panel se rehace en el idioma nuevo, en el mismo sitio y la misma sección.
        pos, pagina = self.pos(), self.lista.currentRow()
        QTimer.singleShot(0, lambda: abrir(self.cadena, None, pos, pagina))
        self.close()

    # -- ventana --
    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        """La rueda del ratón no cambia los valores de los campos."""
        return ev.type() == QEvent.Type.Wheel or super().eventFilter(obj, ev)

    def _ajustar_tamano(self, fila: int) -> None:
        """Cada sección con su tamaño, sin salirse de la pantalla."""
        seccion = self.SECCIONES[fila] if 0 <= fila < len(self.SECCIONES) else None
        if seccion == "Clics" and _edicion.con("panel_ayuda"):
            self.resize(*self._tamano_clics())
        else:
            self.resize(*self.TAMANOS.get(seccion, self.TAMANO))
        if self.isVisible():
            self.dentro_de_pantalla()

    def dentro_de_pantalla(self) -> None:
        g = self.screen().availableGeometry()
        self.move(max(g.left(), min(self.x(), g.right() + 1 - self.width())),
                  max(g.top(), min(self.y(), g.bottom() + 1 - self.height())))

    def _empezar_arrastre(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._arrastre = ev.globalPosition().toPoint() - self.pos()

    def _arrastrar(self, ev) -> None:
        if self._arrastre is not None:
            self.move(ev.globalPosition().toPoint() - self._arrastre)

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(ev)

    def closeEvent(self, ev) -> None:  # noqa: N802
        if getattr(self.cadena, "_panel_opciones", None) is self:
            self.cadena._panel_opciones = None
        super().closeEvent(ev)


def abrir(cadena, global_pos, pos_exacta: QPoint | None = None, pagina: int = 0) -> None:
    """Abre (o trae delante) el panel de opciones cerca de ``global_pos``."""
    viejo = getattr(cadena, "_panel_opciones", None)
    if viejo is not None:
        try:
            viejo.raise_()
            viejo.activateWindow()
            return
        except RuntimeError:
            cadena._panel_opciones = None
    panel = PanelOpciones(cadena, pagina)
    cadena._panel_opciones = panel
    if pos_exacta is not None:
        panel.move(pos_exacta)
    elif global_pos is not None:
        pantalla = cadena.app.window.screen().availableGeometry()
        x = min(max(pantalla.left(), global_pos.x() - panel.width() // 2), pantalla.right() - panel.width())
        y = min(max(pantalla.top(), global_pos.y()), pantalla.bottom() - panel.height())
        panel.move(x, y)
    panel.show()
    panel.dentro_de_pantalla()
    panel.raise_()
    panel.activateWindow()

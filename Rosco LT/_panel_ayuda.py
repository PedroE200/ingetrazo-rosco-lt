# SPDX-License-Identifier: GPL-3.0-or-later
"""La ayuda de Rosco, en la sección «Ayuda» del panel de Opciones: dos
pestañas (los clics, con su pantallita animada, y todo lo demás) con el texto
desplazable. Al pasar el ratón por una fila de clics, la pantallita se queda
en sus gestos."""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QTextDocument
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import _anima, _edicion
from ._cadena import OJOS, ojo_de
from ._flotante import ROJO, ROJO_OSCURO
from ._idioma import _tr

AYUDA_RATON = 30.0                     # sitio para el ratoncito de cada fila
# La primera pestaña: los clics. Cada fila: (botón, veces, texto); botón «i»
# izquierdo o «d» derecho; veces 1, 2, 3 o 0 si es mantener pulsado.
AYUDA_PESTANAS = ("Los clics", "Todo lo demás")
AYUDA_CLICS = (
    ("Sin orden (Seleccionar)",
     (("i", 1, "<b>Clic izquierdo</b> en vacío: quita la selección, como en IngeTrazo. En un objeto: lo "
               "selecciona y sale el anillo de selección. Con un grupo abierto, fuera de su caja: cierra el grupo.",
       ("objeto",)),
      ("i", 2, "<b>Doble clic izquierdo</b> en vacío: repite la última orden. En un grupo: entra a editarlo.", ("repite",)),
      ("d", 1, "<b>Clic derecho</b> en vacío: muestra u oculta el rosco. Con un submenú o la rueda a la vista: "
               "un paso atrás (al rosco; del rosco, Seleccionar y se esconde).", ("alterna",)),
      ("d", 1, "<b>Clic derecho</b> sobre un objeto: el menú de IngeTrazo de ese objeto.", ("menu",)),
      ("d", 2, "<b>Doble clic derecho</b>: deshace el último cambio.", ("deshace",)),
      ("d", 3, "<b>Triple clic derecho</b> rápido: apaga Rosco; con Rosco apagado, lo enciende.", ("alterna",)),
      )),
    ("Sobre el rosco",
     (("i", 1, "<b>Clic en un botón</b>: su orden, directa (la última que elegiste en ese botón); "
               "el rosco se quita hasta acabarla.", ("boton",)),
      ("d", 1, "<b>Clic derecho en un botón</b>: su subrosco, con las demás órdenes. La que eliges pasa "
               "al botón y se recuerda; la que tenía, al subrosco. En la rueda, sobre Plano de sección: "
               "mostrar planos, cortes y relleno.", ("boton",)),
      ("i", 2, "<b>Doble clic en el centro</b>: repite la última orden.", ("repite",)),
      ("d", 1, "<b>Clic derecho</b> fuera de los botones: un paso atrás. En un submenú o en la rueda de "
               "vistas vuelve al rosco principal; en el rosco principal, Seleccionar y el rosco se "
               "esconde.", ("boton",)),
      ("i", 0, "<b>Mantener pulsado</b>: el rosco se vuelve transparente para ver el modelo y, al soltar, vuelve "
               "donde esté el cursor. Sobre un botón, además escucha una orden de voz.", ("pulsado",)))),
    ("Con una orden en marcha",
     (("i", 1, "<b>Clic izquierdo</b>, en vacío o en un objeto: pone el siguiente punto. Nunca abre nada. "
               "Al acabar, la orden sigue activa para otra vez.", ("punto",)),
      ("i", 2, "<b>Doble clic izquierdo</b>: cancela la orden. Descarta lo que estaba a medias; "
               "lo terminado se queda.", ("cancela",)),
      ("d", 1, "<b>Clic derecho</b>: termina la orden, conserva lo hecho (lo que cuelga del ratón "
               "se suelta) y abre el rosco con el submenú de esa orden. Otro clic derecho: al rosco "
               "principal; otro más: Seleccionar.", ("termina",)),
      ("d", 2, "<b>Doble clic derecho</b>: un paso atrás. Quita lo último y sigues en la orden.", ("atras",)))),
)
# Sin las filas ni las frases de las partes que esta edición no lleva.
AYUDA_CLICS = _edicion.limpiar(AYUDA_CLICS)
AYUDA_ESCENAS = tuple(dict.fromkeys(e for _t, filas in AYUDA_CLICS for fila in filas for e in fila[3]))
# La segunda pestaña: apartados (título, texto) o (título, [(ojo, texto)]).
AYUDA = (
    ("Moverse y parar",
     "Al mover el ratón, el anillo va con el cursor. Al pararte se queda fijo y ya puedes "
     "hacer clic en sus botones. Si te alejas, vuelve a seguirte."),
    ("Arriba: dibujar",
     "Fuera: línea, rectángulo, círculo, polígono y arco. Dentro: medir, seleccionar y "
     "pintar. Un clic elige la herramienta y abre sus opciones a la derecha del cursor "
     "(lados, modo, «al terminar»…)."),
    ("Abajo: modificar lo seleccionado",
     "Dentro: suprimir, simetría, escalar y rotar. Fuera: borrar, copiar, cortar, pegar, "
     "pegar en su sitio, crear grupo, bloquear, ocultar e invertir cara."),
    # Cada ojo por lo que hace («@función»): el punto de color sale del ojo que
    # la lleva de verdad (de serie o como lo dejó el usuario en el gestor).
    ('Los ojos (la rueda y el historial se abren al pasar el ratón; los demás, con un clic)',
     [("@rueda", 'La rueda de vistas (zoom, vistas estándar, cónica/paralela, plano de sección, cámara, ocultar…).'),
      ("@historial", "Los 10 últimos comandos (se abren al pasar el ratón)."),
      ("@texturas", 'La biblioteca de texturas, con un clic.'),
      ("@ocultar_resto", 'Ocultar el resto del modelo (otro clic lo vuelve a mostrar).')]),
    ("Los botoncitos del borde",
     "Deshacer y rehacer, opciones, pantalla limpia, buscar (con la barra quieta, teclea para "
     "buscar una orden; con un clic, los menús de IngeTrazo en árbol), preferencias, gestor de "
     "barras, extensiones, apagar y calculadora. A la izquierda: texto, empujar/tirar y notas "
     "(con el reloj en «Tareas del modelo»); a la derecha: guardar, desplazar y copia "
     "con nombre y comentario. Todos los huecos se cambian en el gestor de barras ▸ "
     "Barra Rosco."),
    ("La casilla de medidas",
     "Sale junto al lápiz tras cada punto. Teclea la medida (admite cuentas, como 120/2) o díctala "
     "con el micrófono: rojo mientras escucha. La V acepta, el retroceso borra una cifra y el aspa "
     "toda la casilla."),
    ("Con el teclado",
     "Esc cancela la orden o cierra el panel abierto. Ctrl+Alt+R reinicia IngeTrazo. "
     "Doble toque rápido en Bloq Mayús: enciende o apaga Rosco."),
    ("Ajustes",
     "En Opciones: idioma, tema de la barra, tamaño, distancia del cursor al submenú, tamaño del "
     "rosco de submenús, dictado de medidas tras el primer punto, qué hacer al terminar una orden "
     "y fijar la barra con la chincheta. Rosco se apaga con el botón Apagar: doble clic, o clic y «Apagar Rosco»."),
)


if not _edicion.con("texturas"):
    # Sin biblioteca de texturas, su ojo es la Ayuda rápida.
    AYUDA = tuple((t, [("@ayuda", "La ayuda rápida, al pasar el ratón; con un clic, Opciones ▸ Ayuda.")
                       if o == "@texturas" else (o, x) for o, x in c] if isinstance(c, list) else c)
                  for t, c in AYUDA)
AYUDA = _edicion.limpiar(AYUDA)
# Dónde va cada ojo de serie (si aún no hay barra a la que preguntar).
DE_SERIE = {"rueda": "arriba", "historial": "derecha", "texturas": "izquierda", "ayuda": "izquierda",
            "ocultar_resto": "abajo"}


def _ojo_real(ojo):
    """El ojo de una fila de la ayuda («@función»: el que la lleva de verdad;
    None si no está en ningún ojo: la fila no sale)."""
    if isinstance(ojo, str) and ojo.startswith("@"):
        from . import _cadena
        if _cadena._ULTIMA:
            return ojo_de(ojo[1:])
        return DE_SERIE.get(ojo[1:])
    return ojo


def _ratoncito(painter, x, y, boton, veces) -> None:
    """El ratón pequeño de cada fila, con el botón que toca en rojo."""
    painter.save()
    cuerpo = QRectF(x, y + 1.0, 13.0, 19.0)
    painter.setPen(QPen(QColor(40, 40, 38), 1.1))
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawRoundedRect(cuerpo, 5.0, 5.0)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(ROJO))
    painter.drawRoundedRect(QRectF(x + (1.5 if boton == "i" else 7.0), y + 2.5, 4.5, 7.5), 2.0, 2.0)
    painter.setPen(QColor(40, 40, 38))
    marca = {2: "×2", 3: "×3", 0: "…"}.get(veces)
    if marca:
        f = QFont(painter.font())
        f.setPointSizeF(7.0)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(x + 12.0, y + 9.0, 16.0, 12.0), Qt.AlignLeft | Qt.AlignVCenter, marca)
    painter.restore()


class Lienzo(QWidget):
    """El contenido de la pestaña abierta: su alto depende del ancho."""

    def __init__(self, parent=None, puntos: float = 8.5) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pagina = 0
        self._ancho = -1
        self._piezas: list = []
        self._caja = QRectF()
        self._escena = AYUDA_ESCENAS[0]
        self._t = time.monotonic()
        self._fila = None                  # la fila de clics bajo el ratón
        self._fuente = QFont(self.font())
        self._fuente.setPointSizeF(puntos)
        self._fuente.setBold(False)
        self._reloj = QTimer(self)
        self._reloj.setInterval(40)
        self._reloj.timeout.connect(self._paso)

    def poner_pagina(self, pagina: int) -> None:
        if pagina == self.pagina:
            return
        self.pagina = pagina
        self._ancho = -1
        self._maquetar()
        self.update()
        self._vigilar()

    def _maquetar(self) -> None:
        """Reparte la pestaña abierta en el ancho que hay."""
        w = self.width()
        if w == self._ancho:
            return
        self._ancho = w
        f = self._fuente
        negrita = QFont(f)
        negrita.setBold(True)
        fm, alto_titulo = QFontMetricsF(f), QFontMetricsF(negrita).height()
        ancho = max(60.0, w - 20.0)
        y = 4.0
        piezas: list = []
        if self.pagina == 0:
            alto = ancho * _anima.ALTO / _anima.ANCHO
            self._caja = QRectF(10.0, y, ancho, alto)
            y += alto + 8.0
            for titulo, filas in AYUDA_CLICS:
                piezas.append(("titulo", QRectF(10.0, y, ancho, alto_titulo), _tr(titulo), None))
                y += alto_titulo + 3.0
                for boton, veces, html, escenas in filas:
                    doc = QTextDocument()
                    doc.setDefaultFont(f)
                    doc.setDocumentMargin(0.0)
                    doc.setTextWidth(ancho - AYUDA_RATON)
                    doc.setHtml("<div style='color:#30302e'>" + _tr(html) + "</div>")
                    alto = max(doc.size().height(), 22.0)
                    piezas.append(("clic", QRectF(10.0, y, ancho, alto), doc, (boton, veces, escenas)))
                    y += alto + 4.0
                y += 3.0
        else:
            for titulo, cuerpo in AYUDA:
                piezas.append(("titulo", QRectF(10.0, y, ancho, alto_titulo), _tr(titulo), None))
                y += alto_titulo + 1.0
                for ojo, texto in (cuerpo if isinstance(cuerpo, list) else [(None, cuerpo)]):
                    if ojo is not None:
                        ojo = _ojo_real(ojo)
                        if ojo is None:
                            continue         # esa función no está en ningún ojo
                    x = 10.0 + (14.0 if ojo else 0.0)
                    texto = _tr(texto)
                    r = fm.boundingRect(QRectF(x, y, 10.0 + ancho - x, 4000.0),
                                        Qt.AlignLeft | Qt.TextWordWrap, texto)
                    piezas.append(("texto", QRectF(x, y, 10.0 + ancho - x, r.height()), texto, ojo))
                    y += r.height()
                y += 5.0
        self._piezas = piezas
        self._fila = None
        self.setMinimumHeight(int(y + 6.0))

    # -- la pantallita animada --
    def _vigilar(self) -> None:
        """El reloj solo anda con la pestaña de los clics a la vista."""
        if self.pagina == 0 and self.isVisible():
            if not self._reloj.isActive():
                self._t = time.monotonic()
                self._reloj.start()
        else:
            self._reloj.stop()

    def _paso(self) -> None:
        if self.pagina != 0 or not self.isVisible():
            self._reloj.stop()
            return
        if time.monotonic() - self._t >= _anima.DURACION_S:
            lista = self._fila[3][2] if self._fila is not None else AYUDA_ESCENAS
            i = lista.index(self._escena) if self._escena in lista else -1
            self._escena = lista[(i + 1) % len(lista)]
            self._t = time.monotonic()
            self.update()                  # cambia también la fila resaltada
            return
        self.update(self._caja.adjusted(-1.0, -1.0, 1.0, 1.0).toAlignedRect())

    def _poner_fila(self, fila) -> None:
        if fila is self._fila:
            return
        self._fila = fila
        if fila is not None and self._escena not in fila[3][2]:
            self._escena = fila[3][2][0]
            self._t = time.monotonic()
        self.update()

    def _fila_marcada(self):
        """La fila resaltada: la del ratón o, si no, la primera de la escena."""
        if self._fila is not None:
            return self._fila
        return next((x for x in self._piezas if x[0] == "clic" and self._escena in x[3][2]), None)

    # -- eventos --
    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        self._vigilar()

    def hideEvent(self, ev) -> None:  # noqa: N802
        self._vigilar()
        super().hideEvent(ev)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._maquetar()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        fila = None
        if self.pagina == 0:
            p = ev.position()
            fila = next((x for x in self._piezas if x[0] == "clic" and x[1].contains(p)), None)
        self._poner_fila(fila)

    def leaveEvent(self, ev) -> None:  # noqa: N802
        self._poner_fila(None)             # la pantallita vuelve a su bucle
        super().leaveEvent(ev)

    def paintEvent(self, ev) -> None:  # noqa: N802
        f = self._fuente
        negrita = QFont(f)
        negrita.setBold(True)
        alto_linea = QFontMetricsF(f).height()
        zona = QRectF(ev.rect())
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.fillRect(ev.rect(), QColor("#fbfbfa"))   # el del panel, sea cual sea el tema de la app
            if self.pagina == 0:
                k = min(1.0, max(0.0, (time.monotonic() - self._t) / _anima.DURACION_S))
                _anima.pintar(painter, self._caja, self._escena, k)
            marcada = self._fila_marcada() if self.pagina == 0 else None
            for pieza in self._piezas:
                tipo, r, texto, extra = pieza
                if not r.adjusted(-8.0, -2.0, 4.0, 2.0).intersects(zona):
                    continue
                if tipo == "titulo":
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(ROJO))
                    painter.drawEllipse(QPointF(r.left() + 4.0, r.center().y()), 3.5, 3.5)
                    painter.setFont(negrita)
                    painter.setPen(ROJO_OSCURO)
                    painter.drawText(r.adjusted(12.0, 0.0, 0.0, 0.0), Qt.AlignLeft | Qt.AlignVCenter, texto)
                elif tipo == "clic":
                    if pieza is marcada:
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QBrush(QColor(91, 91, 214, 38)))
                        painter.drawRoundedRect(r.adjusted(-4.0, -1.0, 4.0, 1.0), 4.0, 4.0)
                    _ratoncito(painter, r.left(), r.top(), extra[0], extra[1])
                    painter.save()
                    painter.translate(r.left() + AYUDA_RATON, r.top())
                    texto.drawContents(painter)
                    painter.restore()
                else:
                    if extra is not None:
                        painter.setPen(QPen(QColor(60, 60, 58), 0.8))
                        painter.setBrush(QBrush(OJOS[extra][2]))
                        painter.drawEllipse(QPointF(r.left() - 7.0, r.top() + alto_linea / 2.0), 4.0, 4.0)
                    painter.setFont(f)
                    painter.setPen(QColor(48, 48, 46))
                    painter.drawText(r, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, texto)
        finally:
            painter.end()


def alto_para(ancho: int, puntos: float) -> int:
    """El alto que necesita la ayuda de los clics con ``ancho`` px y letra de
    ``puntos``: para que el panel la enseñe entera, sin barra."""
    lienzo = Lienzo(puntos=puntos)
    lienzo.resize(ancho, 10)
    lienzo._maquetar()
    alto = lienzo.minimumHeight()
    lienzo.deleteLater()
    return alto


class PaginaAyuda(QWidget):
    """Las dos pestañas (cambian de color al elegirlas) y su contenido."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(5)
        # 2.49.2: los clics tienen su ayuda en Opciones ▸ Clics; aquí, lo demás.
        self.lienzo = Lienzo()
        self.lienzo.poner_pagina(1)
        self.zona = QScrollArea()
        self.zona.setObjectName("zona_ayuda")
        self.zona.setFrameShape(QFrame.NoFrame)
        self.zona.setWidgetResizable(True)
        self.zona.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.zona.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)   # el ancho no baila entre pestañas
        self.zona.viewport().setAutoFillBackground(False)
        self.zona.setWidget(self.lienzo)
        self.lienzo.setAutoFillBackground(False)   # setWidget lo enciende; el lienzo pinta su fondo
        col.addWidget(self.zona, 1)


    def _elegir(self, pagina: int) -> None:
        self.lienzo.poner_pagina(pagina)
        self.zona.verticalScrollBar().setValue(0)

# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventana de las listas de tareas (pieza de Rosco):

- Pestañas arriba (Tareas del modelo · Tareas de IngeTrazo) para pasar a
  la otra lista, banda degradada y tarjeta blanca con el nombre en grande,
  el contador y, en la del modelo, la ruta del archivo.
- Columna de cuadros degradados: nueva arriba, nueva abajo y, con selección,
  borrar, subir y bajar.
- «Tareas abiertas» con el buscador, que deja ver solo las que contienen
  lo escrito.
- Una fila por tarea, sobre una hoja cuadriculada: casilla de hecha,
  ✕ borrar (↺ recuperar), el texto editable en el sitio (de una o varias
  líneas) y los puntos para seleccionar o arrastrar. Intro = tarea nueva
  debajo; Mayús+Intro = otra línea; ↑/↓ pasan de una tarea a otra.
- «N tareas hechas», que pliega o despliega las hechas.
- Las borradas siguen a la vista (rojo tachado) hasta «Guardar cambios».
- Pie: Imprimir, Exportar (Texto / CSV), Ayuda y Hecho, o Cancelar y
  Guardar cambios si hay cambios. Guardar cierra la ventana.

Las dos listas van en una sola ventana: las pestañas cambian de lista (y
de degradado: azul marino a turquesa el modelo; naranja IngeTrazo) sin perder los cambios de la otra, y Guardar / Cancelar valen
para las dos.
"""
from __future__ import annotations

from .._idioma import _tr
import csv
import itertools
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import (
    QByteArray, QEvent, QMimeData, QSize, QStandardPaths, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QDrag, QFont, QInputMethodEvent, QPainter, QPalette, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QStyleFactory, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from . import _datos, _iconos

from .._ajustes import CLAVE, atributo, registro

log = registro("tareas")
MIME = f"application/x-{CLAVE.replace('_', '-')}-tarea"
FUENTE = "Segoe UI"
FONDO = "#F0F0F0"              # ventana y pie
LATERAL = "#E9E9E9"            # columna de botones
BORDE = "#CFCFCF"
GRIS = "#888888"
EDITANDO = "#FFFBE3"           # texto que se está escribiendo
HECHA = "#FAFAFA"              # fondo de las filas hechas
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct",
         "nov", "dic")

# Pestaña de la otra lista (inactiva): gris casi negro.
PESTANA = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4a4a4a,stop:1 #151515)"
GRIS_APAGADO = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e4e4e4,stop:1 #c8c8c8)"


def _vertical(*paradas: str) -> str:
    n = len(paradas) - 1
    pasos = ",".join(f"stop:{i / n:g} {c}" for i, c in enumerate(paradas))
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,{pasos})"


def _horizontal(*paradas: str) -> str:
    n = len(paradas) - 1
    pasos = ",".join(f"stop:{i / n:g} {c}" for i, c in enumerate(paradas))
    return f"qlineargradient(x1:0,y1:0,x2:1,y2:0,{pasos})"


@dataclass(frozen=True)
class Tema:
    """Los colores de una lista y sus degradados."""
    color: str                 # acento: casillas, foco, flecha de plegar
    oscuro: str                # borde de la pestaña y de los cuadros
    claro: str                 # fila seleccionada
    v: str                     # degradado vertical: pestaña y cuadros
    v_encima: str
    v_hundido: str
    h: str                     # degradado horizontal: banda y raya de hechas
    texto: tuple               # paradas del degradado de los títulos


TEMAS = {
    # azul marino a turquesa
    "modelo": Tema("#1db4b0", "#0d2f66", "#c9efee",
                   _vertical("#0d2f66", "#17739a", "#2cc4bd"),
                   _vertical("#154080", "#1d86ad", "#3fd6cf"),
                   _vertical("#081d42", "#0d2f66"),
                   _horizontal("#0d2f66", "#1a7fa0", "#2cc4bd"),
                   ("#0d2f66", "#1a7fa0", "#22bcb6")),
    # naranja degradado
    "global": Tema("#E07A1F", "#7a2e04", "#FBE3CB",
                   _vertical("#7a2e04", "#d9661c", "#f7a64a"),
                   _vertical("#8f3a08", "#e8772a", "#ffb862"),
                   _vertical("#4f1d02", "#7a2e04"),
                   _horizontal("#7a2e04", "#d9661c", "#f7a64a"),
                   ("#7a2e04", "#d9661c", "#f29a3c")),
}
NOMBRES = {"modelo": "Tareas del modelo", "global": "Tareas de IngeTrazo"}

AYUDA = ("Tarea nueva: los dos primeros cuadros de la columna (arriba o abajo de la lista) "
         "o Intro en una tarea.\n"
         "Mayús + Intro: otra línea dentro de la misma tarea.\n"
         "↑ / ↓: pasar de una tarea a otra.\n"
         "Casilla: dar la tarea por hecha o volver a abrirla.\n"
         "✕: borrar la tarea (↺ la recupera hasta que guardes).\n"
         "Puntos de la derecha: pulsa para seleccionar (Ctrl o Mayús: varias) "
         "o arrastra para cambiarla de sitio.\n"
         "Con una tarea seleccionada, la columna la borra, la sube o la baja.\n"
         "«N tareas hechas»: pliega o despliega las hechas.\n"
         "Buscador: deja ver solo las tareas que contienen lo escrito.\n"
         "Micrófono: dictado del sistema. Escribiendo una tarea, sigue la frase en ella; "
         "si no, crea una tarea nueva arriba de la lista.\n"
         "Pestañas de arriba: pasan a la otra lista.")

_BARRA = ("QScrollBar:vertical{width:12px;background:#F4F4F4;border:none;margin:0;}"
          "QScrollBar::handle:vertical{background:#C1C1C1;border-radius:4px;min-height:24px;"
          "margin:2px;}"
          "QScrollBar::handle:vertical:hover{background:#A8A8A8;}"
          "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
          "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:none;}")

_ids = itertools.count(1)


def _fuente(pt: float, negrita=False, cursiva=False, tachada=False) -> QFont:
    f = QFont(FUENTE)
    f.setPointSizeF(pt)
    f.setBold(negrita)
    f.setItalic(cursiva)
    f.setStrikeOut(tachada)
    return f


def _boton_icono(nombre, lado: int, tip: str, fn) -> QToolButton:
    """``nombre``: un PNG de ``imagenes`` o un QIcon ya hecho."""
    b = QToolButton()
    b.setIcon(_iconos.icono(nombre) if isinstance(nombre, str) else nombre)
    b.setIconSize(_qsize(lado))
    b.setAutoRaise(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setToolTip(_tr(tip))
    b.setStyleSheet("QToolButton{border:none;background:transparent;padding:0;}")
    b.clicked.connect(lambda _c=False: fn())
    return b


def _qsize(lado: int) -> QSize:
    return QSize(lado, lado)


def _boton_pie(texto: str, fn, principal: bool = False) -> QPushButton:
    """Botón grande del pie; el principal
    lleva el borde azul grueso."""
    b = QPushButton(_tr(texto))
    b.setAutoDefault(False)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumSize(140, 36)
    borde = "2px solid #0078d7" if principal else "1px solid #adadad"
    b.setStyleSheet(
        f"QPushButton{{border:{borde};border-radius:3px;font-family:{FUENTE};font-size:14px;"
        "color:#222;padding:0 16px;"
        "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fdfdfd,stop:1 #e8e8e8);}"
        "QPushButton:hover{background:#e5f1fb;border-color:#0078d7;}"
        "QPushButton:pressed{background:#cce4f7;}"
        "QPushButton:focus{outline:none;}")
    b.clicked.connect(lambda _c=False: fn())
    return b


def _boton_claro(texto: str, fn, tema: Tema) -> QPushButton:
    """Botón pequeño de las herramientas del panel (Imprimir, Exportar)."""
    b = QPushButton(_tr(texto))
    b.setAutoDefault(False)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(27)
    b.setStyleSheet(
        "QPushButton{border:1px solid #adadad;background:#fafafa;border-radius:3px;"
        f"padding:0 10px;font-family:{FUENTE};font-size:12px;color:#222;}}"
        f"QPushButton:hover{{background:{_translucido(tema.claro, 0.6)};"
        f"border-color:{tema.color};}}"
        "QPushButton:focus{outline:none;}")
    b.clicked.connect(lambda _c=False: fn())
    return b


class _Degradado(QLabel):
    """Texto relleno con el degradado horizontal de la lista, como los
    títulos."""

    def __init__(self, texto: str, paradas, px: int, peso=QFont.Bold) -> None:
        super().__init__(texto)
        self._paradas = paradas
        f = QFont(FUENTE)
        f.setPixelSize(px)
        f.setWeight(peso)
        self.setFont(f)
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, ev) -> None:
        from PySide6.QtGui import QLinearGradient, QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = self.fontMetrics()
        ancho = fm.horizontalAdvance(_tr(self.text()))
        y = (self.height() + fm.ascent() - fm.descent()) / 2
        camino = QPainterPath()
        camino.addText(0, y, self.font(), self.text())
        grad = QLinearGradient(0, 0, max(1, ancho), 0)
        n = len(self._paradas) - 1
        for i, c in enumerate(self._paradas):
            grad.setColorAt(i / n, QColor(c))
        p.fillPath(camino, grad)
        p.end()


def _translucido(color: str, alfa: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{round(alfa * 255)})"


class _Cuadricula(QWidget):
    """El fondo de la lista: una hoja cuadriculada (se mueve con las tareas)."""

    PASO = 16
    LINEA = QColor("#DCE4EF")

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(ev.rect(), QColor("#FFFFFF"))
        p.setPen(self.LINEA)
        r = ev.rect()
        x = r.left() - r.left() % self.PASO
        while x <= r.right():
            p.drawLine(x, r.top(), x, r.bottom())
            x += self.PASO
        y = r.top() - r.top() % self.PASO
        while y <= r.bottom():
            p.drawLine(r.left(), y, r.right(), y)
            y += self.PASO
        p.end()


def _fecha_archivo() -> str:
    d = datetime.now()
    return f"{d.day:02d} {_tr(MESES[d.month - 1])} {d:%y} {d:%H}h{d:%M}"


# ---- Filas ------------------------------------------------------------------------------

class _Texto(QTextEdit):
    """El texto de una tarea, de una o varias líneas: Mayús+Intro parte la
    línea, Intro crea otra tarea debajo y ↑/↓ cambian siempre de tarea.
    Crece con sus líneas; nunca enseña barras."""

    TECLAS = (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Up, Qt.Key_Down)

    def __init__(self, fila: "_Fila") -> None:
        super().__init__()
        self.fila = fila
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(2)
        self.document().contentsChanged.connect(self._ajustar)
        self._ultima_tecla = 0.0         # para saber dónde empieza cada trozo dictado

    def texto(self) -> str:
        return self.toPlainText()

    def poner(self, texto: str) -> None:
        self.setPlainText(texto)
        self.moveCursor(QTextCursor.Start)       # un texto largo se ve por el principio
        self._ajustar()

    def al_final(self) -> None:
        self.moveCursor(QTextCursor.End)

    def _ajustar(self) -> None:
        self.document().setTextWidth(max(10, self.viewport().width()))
        alto = int(self.document().size().height() + 0.99)
        alto = max(alto, self.fontMetrics().lineSpacing() + 6)
        if alto != self.height():
            self.setFixedHeight(alto)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._ajustar()

    def wheelEvent(self, ev) -> None:
        ev.ignore()                      # la rueda mueve la lista, no la tarea

    # -- dictado del sistema: en Qt llega sin ver el texto de alrededor, así que
    #    no separa con espacio ni sabe si va en mitad de una frase.
    def _dictando(self) -> bool:
        return self.fila.ventana._dictando == self.fila.id

    def _con_contexto(self, texto: str) -> str:
        """Pone el espacio que falta delante de lo dictado y la mayúscula (o
        minúscula, si sigue una frase) según lo que hay antes del cursor."""
        if not texto or not texto[0].isalnum():
            return texto                 # «.», «,»… van pegados
        antes = self.toPlainText()[:self.textCursor().selectionStart()]
        previo = antes.rstrip(" ")
        palabra = texto.split(" ", 1)[0]
        if not previo or previo[-1] in ".!?¡¿\n":
            texto = texto[0].upper() + texto[1:]
        elif not (len(palabra) > 1 and palabra.isupper()):      # siglas, tal cual
            texto = texto[0].lower() + texto[1:]
        if antes and not antes[-1].isspace() and antes[-1] not in "¿¡(«\"'":
            texto = " " + texto
        return texto

    def inputMethodEvent(self, ev) -> None:
        if ev.commitString() and self._dictando():
            arreglado = self._con_contexto(ev.commitString())
            if arreglado != ev.commitString():
                nuevo = QInputMethodEvent(ev.preeditString(), ev.attributes())
                nuevo.setCommitString(arreglado, ev.replacementStart(),
                                      ev.replacementLength())
                ev = nuevo
        super().inputMethodEvent(ev)

    def event(self, ev) -> bool:
        # Que los atajos de IngeTrazo (Intro, flechas) no se queden con la tecla.
        if ev.type() == QEvent.ShortcutOverride and ev.key() in self.TECLAS:
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev) -> None:
        if self.fila.ventana.filas.get(self.fila.id) is not self.fila:
            return                       # fila ya sustituida (pendiente de borrar)
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            if ev.modifiers() & Qt.ShiftModifier:
                if not self.isReadOnly():
                    self.textCursor().insertText("\n")     # nueva línea en la tarea
                return
            self.fila.ventana._intro(self.fila.id)
            return
        if ev.key() in (Qt.Key_Up, Qt.Key_Down):
            self.fila.ventana._saltar(self.fila.id, -1 if ev.key() == Qt.Key_Up else 1)
            return
        # Si el dictado escribe como teclas: cada trozo llega de golpe, así que
        # la primera letra tras una pausa es el principio de lo dictado.
        if (self._dictando() and ev.text().isprintable() and ev.text()
                and not ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            ahora = time.monotonic()
            nuevo, self._ultima_tecla = ahora - self._ultima_tecla > 0.4, ahora
            if nuevo and not self.isReadOnly():
                arreglado = self._con_contexto(ev.text())
                if arreglado != ev.text():
                    self.textCursor().insertText(arreglado)
                    return
        super().keyPressEvent(ev)


class _Puntos(QToolButton):
    """Los puntos de la derecha: clic selecciona, arrastrar mueve la tarea."""

    def __init__(self, fila: "_Fila") -> None:
        super().__init__()
        self.fila = fila
        self._inicio = None
        self.setIcon(_iconos.trazo("puntos", "#9A9A9A"))
        self.setIconSize(_qsize(16))
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(_tr("Pulsa para seleccionar la tarea (Ctrl o Mayús: varias).\n"
                        "Arrástrala para cambiarla de sitio."))
        self.setStyleSheet("QToolButton{border:none;background:transparent;padding:0;}")

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._inicio = ev.position().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if (self._inicio is not None and ev.buttons() & Qt.LeftButton
                and (ev.position().toPoint() - self._inicio).manhattanLength()
                >= QApplication.startDragDistance()):
            self._inicio = None
            self.setDown(False)
            mime = QMimeData()
            mime.setData(MIME, QByteArray(str(self.fila.id).encode()))
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(self.fila.grab())
            drag.setHotSpot(ev.position().toPoint() + self.pos())
            drag.exec(Qt.MoveAction)
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        clic = self._inicio is not None and ev.button() == Qt.LeftButton
        self._inicio = None
        super().mouseReleaseEvent(ev)
        if clic and self.rect().contains(ev.position().toPoint()):
            varias = bool(ev.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            self.fila.ventana._seleccionar(self.fila.id, varias)


class _Fila(QFrame):

    def __init__(self, ventana: "VentanaTareas", tarea: dict,
                 numero: int | None = None) -> None:
        super().__init__()
        self.ventana = ventana
        self.id = tarea["_id"]
        self.hecha = tarea["hecha"] or tarea["_borrada"]
        self.setObjectName("fila")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 6, 2)
        lay.setSpacing(6)

        self.casilla = QCheckBox()
        # Fusion respeta la paleta clara; uno por casilla, porque con hojas de
        # estilo Qt lo envuelve en un proxy que se queda con él y lo borra.
        estilo = QStyleFactory.create("Fusion")
        estilo.setParent(self.casilla)          # dueño en C++, no en Python
        self.casilla.setStyle(estilo)
        self.casilla.setPalette(ventana._paleta)
        self.casilla.setFocusPolicy(Qt.NoFocus)
        self.casilla.setCursor(Qt.PointingHandCursor)
        self.casilla.setChecked(self.hecha)
        self.casilla.setFixedWidth(18)
        if tarea["_borrada"]:
            self.casilla.setEnabled(False)
        else:
            self.casilla.setToolTip(_tr("Pulsa para volver a abrir la tarea" if tarea["hecha"]
                                    else "Pulsa para dar la tarea por hecha"))
            self.casilla.toggled.connect(lambda v: ventana._marcar(self.id, v))
        lay.addWidget(self.casilla)

        if tarea["_borrada"]:
            self.borrar = _boton_icono("recuperar.png", 18,
                                       "Pulsa para recuperar la tarea",
                                       lambda: ventana._recuperar(self.id))
        else:
            self.borrar = _boton_icono("borrar.png", 18, "Pulsa para borrar la tarea",
                                       lambda: ventana._borrar([self.id]))
        lay.addWidget(self.borrar)

        # Número de la tarea (las borradas no llevan): azul de la lista, o
        # gris en las hechas.
        self.numero = QLabel("{0}.".format(numero) if numero else "")
        self.numero.setAlignment(Qt.AlignRight | Qt.AlignTop)
        tinta = "#AAAAAA" if self.hecha else ventana.tema.oscuro
        self.numero.setStyleSheet(f"font-family:{FUENTE};font-size:10pt;font-weight:bold;"
                                  f"color:{tinta};background:transparent;padding-top:2px;")
        # Ancho fijo para «999.»: los textos quedan alineados con 1, 10 o 100 tareas.
        self.numero.setFixedWidth(self.numero.fontMetrics().horizontalAdvance("999.") + 2)
        lay.addWidget(self.numero)

        self.texto = _Texto(self)
        letra = _fuente(10, cursiva=tarea["_borrada"], tachada=self.hecha)
        # Seminegrita para que se lea bien sobre la cuadrícula; algo menos en las hechas.
        letra.setWeight(QFont.Medium if self.hecha else QFont.DemiBold)
        self.texto.setFont(letra)
        self.texto.poner(tarea["texto"])
        self.texto.setReadOnly(tarea["_borrada"])
        # Después de poner el texto: solo avisan los cambios del usuario.
        self.texto.textChanged.connect(lambda: ventana._editado(self.id, self.texto.texto()))
        lay.addWidget(self.texto, 1)

        self.puntos = _Puntos(self)
        lay.addWidget(self.puntos)
        # Casilla, ✕ y puntos, arriba, a la altura de la primera línea.
        for w in (self.casilla, self.borrar, self.numero, self.puntos):
            lay.setAlignment(w, Qt.AlignTop)
        self.pintar(tarea, False)

    def pintar(self, tarea: dict, seleccionada: bool) -> None:
        tema = self.ventana.tema
        # Fondos con transparencia, para que se vea la cuadrícula de la hoja.
        if seleccionada:
            fondo = _translucido(tema.claro, 0.85)
        else:
            fondo = _translucido(HECHA, 0.75) if self.hecha else "transparent"
        if tarea["_borrada"]:
            tinta = "#D32F2F"
        elif tarea["hecha"]:
            tinta = "#555555"
        else:
            tinta = "#000000"
        foco = "" if tarea["_borrada"] else (
            f"QTextEdit:focus{{background:{_translucido(EDITANDO, 0.92)};"
            f"border-bottom:2px solid {tema.color};}}")
        marca = _iconos.ruta_imagen("marca_blanca.png")
        # Raya fina entre tareas, del color de la pestaña (turquesa o naranja claro).
        raya = _translucido(tema.color, 0.45)
        self.setStyleSheet(
            f"#fila{{background:{fondo};border:none;border-bottom:1px solid {raya};}}"
            f"QTextEdit{{background:transparent;color:{tinta};border:none;"
            "border-bottom:2px solid transparent;padding:0;"
            "selection-background-color:#3399FF;selection-color:#FFFFFF;}" + foco +
            "QCheckBox{background:transparent;}"
            "QCheckBox::indicator{width:14px;height:14px;border:1px solid #8A8A8A;"
            "border-radius:3px;background:#FFFFFF;}"
            f"QCheckBox::indicator:hover{{border-color:{tema.color};}}"
            f"QCheckBox::indicator:checked{{background:{tema.color};border-color:{tema.color};"
            f"image:url({marca});}}"
            "QCheckBox::indicator:disabled{background:#EEEEEE;border-color:#C4C4C4;}"
            "QCheckBox::indicator:checked:disabled{background:#C4C4C4;}")

    # -- soltar una tarea arrastrada encima de esta
    def _origen(self, ev):
        if not ev.mimeData().hasFormat(MIME):
            return None
        try:
            return int(bytes(ev.mimeData().data(MIME)).decode())
        except ValueError:
            return None

    def dragEnterEvent(self, ev) -> None:
        origen = self._origen(ev)
        if origen is not None and self.ventana._misma_seccion(origen, self.id):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:
        self.dragEnterEvent(ev)

    def dropEvent(self, ev) -> None:
        origen = self._origen(ev)
        if origen is None:
            return
        despues = ev.position().y() > self.height() / 2
        ev.acceptProposedAction()
        QTimer.singleShot(0, lambda: self.ventana._mover_junto(origen, self.id, despues))


class _Separador(QFrame):
    """«N tareas hechas» con la flecha de plegar, como un título de sección."""

    def __init__(self, ventana: "VentanaTareas", hechas: int, plegado: bool) -> None:
        super().__init__()
        tema = ventana.tema
        color = tema.color
        self.setObjectName("separador")
        self.setStyleSheet("#separador{background:transparent;border:none;}")
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 14, 0, 0)
        caja.setSpacing(3)
        lay = QHBoxLayout()
        lay.setContentsMargins(2, 0, 4, 0)
        lay.setSpacing(6)
        caja.addLayout(lay)
        raya = QFrame()                  # raya con el degradado de la banda
        raya.setObjectName("raya")
        raya.setFixedHeight(2)
        raya.setStyleSheet(f"#raya{{background:{tema.h};border:none;}}")
        caja.addWidget(raya)
        if plegado:
            b = _boton_icono(_iconos.trazo("plegado", color, grosor=2.4), 16,
                             "Pulsa para desplegar la lista de hechas", ventana._plegar)
        else:
            b = _boton_icono(_iconos.trazo("desplegado", color, grosor=2.4), 16,
                             "Pulsa para plegar la lista de hechas", ventana._plegar)
        b.setVisible(hechas > 0)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hueco = b.sizePolicy()
        hueco.setRetainSizeWhenHidden(True)
        b.setSizePolicy(hueco)
        lay.addWidget(b)
        self.etiqueta = _Degradado(_tareas_hechas(hechas), tema.texto, 15)
        lay.addWidget(self.etiqueta, 1)


def _tareas_hechas(n: int) -> str:
    return _tr("1 tarea hecha") if n == 1 else _tr("{0} tareas hechas", n)


class _Ruta(QLabel):
    """La ruta del modelo en la cabecera, recortada por el medio si no cabe."""

    def __init__(self) -> None:
        super().__init__()
        self._texto = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def poner(self, texto: str) -> None:
        self._texto = texto
        self.setToolTip(_tr(texto))
        self.setVisible(bool(texto))
        self._recortar()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._recortar()

    def _recortar(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._texto, Qt.ElideMiddle,
                                                      max(0, self.width())))


# ---- Ventana ------------------------------------------------------------------------------

def _del_estado(nombre: str):
    """Atributo de la lista de la pestaña visible (cada lista guarda el suyo)."""
    return property(lambda self: self._estados[self.clave][nombre],
                    lambda self, v: self._estados[self.clave].__setitem__(nombre, v))


class VentanaTareas(QDialog):
    """Una sola ventana para las dos listas: las pestañas cambian de lista
    sin perder los cambios de la otra; Guardar y Cancelar valen para las dos."""

    guardada = Signal()

    tareas = _del_estado("tareas")
    original = _del_estado("original")
    seleccion = _del_estado("seleccion")
    _ruta_cargada = _del_estado("ruta")
    _plegado = _del_estado("plegado")

    def __init__(self, app, almacen) -> None:
        super().__init__(app.window)
        self.app = app
        self.almacen = almacen
        clave = almacen.opcion("pestana", "global")
        self.clave = clave if clave in NOMBRES else "global"
        self.tema = TEMAS[self.clave]
        self._estados = {k: {"tareas": [], "original": [], "seleccion": set(), "ruta": None,
                             "plegado": bool(almacen.opcion(f"plegadas_{k}", False)),
                             "cargada": False}
                         for k in NOMBRES}
        self.filas: dict[int, _Fila] = {}
        self.filtro = ""
        self._dictando = None              # id de la tarea en la que se está dictando
        self._raiz = None
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.setWindowIcon(_iconos.libreta())

        self._paleta = QPalette()
        for rol, color in ((QPalette.Window, FONDO), (QPalette.Base, "#FFFFFF"),
                           (QPalette.Text, "#222222"), (QPalette.WindowText, "#222222"),
                           (QPalette.Button, "#FAFAFA"), (QPalette.ButtonText, "#222222"),
                           (QPalette.PlaceholderText, "#999999")):
            self._paleta.setColor(rol, QColor(color))
        self.setPalette(self._paleta)
        self.setAutoFillBackground(True)
        self.setObjectName(f"{CLAVE}_tareas")      # colores fijos, aunque IngeTrazo vaya en oscuro
        self.setStyleSheet(f"#{CLAVE}_tareas{{background:{FONDO};}}"
                           "QToolTip{color:#222;background:#FFFFE8;border:1px solid #BBB;}")
        self._marco = QVBoxLayout(self)
        self._marco.setContentsMargins(0, 0, 0, 0)
        self._construir()
        geom = almacen.opcion("geometria") or almacen.opcion(f"geometria_{self.clave}")
        self.setMinimumWidth(520)
        if not (geom and self.restoreGeometry(QByteArray.fromBase64(geom.encode()))):
            self.resize(640, 760)        # el tamaño de partida

    # ---- Construcción ---------------------------------------------------------------------
    def _construir(self) -> None:
        """Todo lo de dentro, con los colores de la pestaña visible; al cambiar
        de pestaña se tira y se vuelve a hacer."""
        tema = self.tema
        viejo, self._raiz = self._raiz, QWidget()
        self._raiz.setObjectName("raiz")
        self._raiz.setStyleSheet(f"#raiz{{background:{FONDO};}}")
        if viejo is not None:
            self._marco.removeWidget(viejo)
            viejo.hide()
            viejo.deleteLater()
        self._marco.addWidget(self._raiz)
        lay = QVBoxLayout(self._raiz)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # -- pestañas, a la derecha: la visible, con su degradado; la otra, oscura
        pestanas = QHBoxLayout()
        pestanas.setContentsMargins(22, 10, 22, 0)
        pestanas.setSpacing(4)
        pestanas.addStretch(1)
        self._pestanas = {}
        for clave in NOMBRES:
            self._pestanas[clave] = self._pestana(clave)
            pestanas.addWidget(self._pestanas[clave], 0, Qt.AlignBottom)
        lay.addLayout(pestanas)

        tarjeta = QVBoxLayout()            # banda + panel: una tarjeta redondeada
        tarjeta.setContentsMargins(14, 0, 14, 0)
        tarjeta.setSpacing(0)
        banda = QFrame()
        banda.setObjectName("banda")
        banda.setFixedHeight(8)
        banda.setStyleSheet(f"#banda{{background:{tema.h};border-top-left-radius:8px;"
                            "border-top-right-radius:8px;}")
        tarjeta.addWidget(banda)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(f"#panel{{background:#FFFFFF;border:1px solid {BORDE};"
                            "border-top:none;border-bottom-left-radius:10px;"
                            "border-bottom-right-radius:10px;}")
        lp = QVBoxLayout(panel)
        lp.setContentsMargins(1, 0, 1, 1)
        lp.setSpacing(0)

        # -- cabecera: nombre en grande, contador y ruta del modelo
        cab = QWidget()
        cab.setObjectName("cab")
        cab.setFixedHeight(54)
        cab.setStyleSheet("#cab{background:#FFFFFF;border-bottom:1px solid #EEEEEE;}")
        fila = QHBoxLayout(cab)
        fila.setContentsMargins(22, 0, 22, 0)
        fila.setSpacing(14)
        nombre = QLabel(_tr(NOMBRES[self.clave]).upper())
        nombre.setStyleSheet(f"font-family:{FUENTE};font-size:21px;font-weight:bold;"
                             "color:#222222;background:transparent;")
        fila.addWidget(nombre)
        self.contador = QLabel()
        self.contador.setStyleSheet(f"font-family:{FUENTE};font-size:12px;color:{GRIS};"
                                    "background:transparent;")
        fila.addWidget(self.contador)
        self.ruta = _Ruta()
        self.ruta.setStyleSheet(f"font-family:{FUENTE};font-size:12px;color:{GRIS};"
                                "background:transparent;")
        self.ruta.setVisible(False)
        fila.addWidget(self.ruta, 1)
        lp.addWidget(cab)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        # -- columna de cuadros con el degradado de la lista
        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(64)
        lateral.setStyleSheet(f"#lateral{{background:{LATERAL};border:none;"
                              f"border-right:1px solid {BORDE};}}")
        lc = QVBoxLayout(lateral)
        lc.setContentsMargins(0, 12, 0, 10)
        lc.setSpacing(10)
        lc.addWidget(self._baldosa("nueva_arriba", "Insertar una tarea nueva arriba de la lista",
                                   lambda: self._nueva(arriba=True)), 0, Qt.AlignHCenter)
        lc.addWidget(self._baldosa("nueva_abajo", "Insertar una tarea nueva abajo de la lista",
                                   lambda: self._nueva(arriba=False)), 0, Qt.AlignHCenter)
        raya = QFrame()
        raya.setFixedSize(40, 1)
        raya.setStyleSheet("background:#D4D4D4;")
        lc.addWidget(raya, 0, Qt.AlignHCenter)
        self.b_borrar = self._baldosa("borrar", "Borrar las tareas seleccionadas",
                                      lambda: self._borrar(sorted(self.seleccion)))
        self.b_subir = self._baldosa("subir", "Subir la tarea seleccionada",
                                     lambda: self._mover(-1))
        self.b_bajar = self._baldosa("bajar", "Bajar la tarea seleccionada",
                                     lambda: self._mover(1))
        for b in (self.b_borrar, self.b_subir, self.b_bajar):
            lc.addWidget(b, 0, Qt.AlignHCenter)
        if self.clave == "modelo":
            # El Reloj (Control de tiempo) vive aquí desde la 2.39.2.
            raya2 = QFrame()
            raya2.setFixedSize(40, 1)
            raya2.setStyleSheet("background:#D4D4D4;")
            lc.addWidget(raya2, 0, Qt.AlignHCenter)
            lc.addWidget(self._baldosa("reloj", "Reloj: control de tiempo, alarma y recordatorio",
                                       self._reloj), 0, Qt.AlignHCenter)
            texto = QLabel(_tr("Reloj"))
            texto.setStyleSheet(f"font-family:{FUENTE};font-size:11px;color:#555555;"
                                "background:transparent;")
            lc.addWidget(texto, 0, Qt.AlignHCenter)
        lc.addStretch(1)
        cuerpo.addWidget(lateral)

        # -- «Tareas abiertas», buscador y lista
        centro = QWidget()
        centro.setObjectName("centro")
        centro.setStyleSheet("#centro{background:#FFFFFF;}")
        lv = QVBoxLayout(centro)
        lv.setContentsMargins(22, 12, 18, 6)
        lv.setSpacing(0)
        titulo = QHBoxLayout()
        titulo.setSpacing(8)
        titulo.addWidget(_Degradado(_tr("Tareas abiertas"), tema.texto, 19))
        ayuda = QLabel("?")
        ayuda.setFixedSize(20, 20)
        ayuda.setAlignment(Qt.AlignCenter)
        ayuda.setStyleSheet(f"font-family:{FUENTE};font-size:13px;font-weight:bold;"
                            "color:#FFFFFF;background:#C4C4C4;border-radius:3px;")
        ayuda.setToolTip(_tr(AYUDA))
        titulo.addWidget(ayuda)
        titulo.addStretch(1)
        titulo.addWidget(self._boton_voz())       # en medio, entre el título y el buscador
        titulo.addStretch(1)
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(_tr("Busca una tarea"))
        self.buscar.setClearButtonEnabled(True)
        self.buscar.setFixedSize(220, 30)
        self.buscar.setPalette(self._paleta)
        self.buscar.addAction(_iconos.trazo("buscar", "#888888"), _tr(QLineEdit.LeadingPosition))
        try:
            from .._voz import con_microfono
            con_microfono(self.buscar)
        except Exception:  # noqa: BLE001 — sin micrófono, el buscador sigue igual
            log.exception("no se pudo poner el micrófono al buscador")
        self.buscar.setStyleSheet(
            f"QLineEdit{{border:1px solid #BBBBBB;border-radius:3px;padding:0 6px;"
            f"font-family:{FUENTE};font-size:13px;background:#FFFFFF;color:#222;}}"
            f"QLineEdit:focus{{border-color:{tema.color};}}")
        self.buscar.textChanged.connect(self._buscar)
        titulo.addWidget(self.buscar)
        lv.addLayout(titulo)
        lv.addSpacing(6)
        linea = QFrame()
        linea.setFixedHeight(1)
        linea.setStyleSheet("background:#9A9A9A;")
        lv.addWidget(linea)
        lv.addSpacing(2)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setObjectName("lista")
        self.scroll.setStyleSheet("#lista{border:none;background:#FFFFFF;}" + _BARRA)
        self.contenido = _Cuadricula()
        self.contenido.setObjectName("contenido")
        self.lista = QVBoxLayout(self.contenido)
        self.lista.setContentsMargins(0, 0, 0, 0)
        self.lista.setSpacing(0)
        self.scroll.setWidget(self.contenido)
        lv.addWidget(self.scroll, 1)
        cuerpo.addWidget(centro, 1)
        lp.addLayout(cuerpo, 1)

        # -- herramientas dentro del panel
        herr = QWidget()
        herr.setObjectName("herr")
        herr.setStyleSheet("#herr{background:#FFFFFF;border-top:1px solid #EEEEEE;"
                           "border-bottom-left-radius:10px;border-bottom-right-radius:10px;}")
        lh = QHBoxLayout(herr)
        lh.setContentsMargins(22, 6, 26, 10)
        lh.setSpacing(12)
        lh.addWidget(_boton_claro("Imprimir", self._imprimir, tema))
        lh.addWidget(_boton_claro("Exportar", self._exportar, tema))
        self.formato = QComboBox()
        self.formato.addItem(_tr("Texto"), "txt")  # no-traducir: "txt" es el dato del formato
        self.formato.addItem("CSV", "csv")  # no-traducir: sigla del formato
        self.formato.setToolTip(_tr("Formato de la exportación"))
        self.formato.setFixedHeight(27)
        self.formato.setStyleSheet(
            f"QComboBox{{font-family:{FUENTE};font-size:12px;color:#222;background:#FAFAFA;"
            "border:1px solid #ADADAD;border-radius:3px;padding:0 8px;}"
            f"QComboBox:hover{{border-color:{tema.color};}}"
            "QComboBox QAbstractItemView{color:#222;background:#FFFFFF;"
            f"selection-background-color:{tema.claro};selection-color:#222;}}")
        self.formato.setCurrentIndex(max(0, self.formato.findData(
            self.almacen.opcion("formato_export", "txt"))))
        self.formato.currentIndexChanged.connect(
            lambda _i: self.almacen.poner_opcion("formato_export", self.formato.currentData()))
        lh.addWidget(self.formato)
        lh.addSpacing(6)
        enlace = QLabel(_tr('<a href="#" style="color:#1a0dab;text-decoration:none">'
                        'Ayuda en pantalla</a>'))
        enlace.setStyleSheet(f"font-family:{FUENTE};font-size:13px;background:transparent;")
        enlace.setCursor(Qt.PointingHandCursor)
        enlace.linkActivated.connect(lambda _l: self._ayuda())
        lh.addWidget(enlace)
        lh.addStretch(1)
        lp.addWidget(herr)
        tarjeta.addWidget(panel, 1)
        lay.addLayout(tarjeta, 1)

        # -- pie: icono y nombre en degradado, y los botones de cerrar
        pie = QHBoxLayout()
        pie.setContentsMargins(26, 12, 26, 14)
        pie.setSpacing(10)
        icono = QLabel()
        icono.setPixmap(_iconos.libreta().pixmap(30, 30))
        icono.setStyleSheet("background:transparent;")
        pie.addWidget(icono)
        pie.addWidget(_Degradado(_tr("Tareas"), tema.texto, 22, QFont.ExtraBold))
        pie.addStretch(1)
        self.b_cancelar = _boton_pie("Cancelar", self.reject)
        self.b_guardar = _boton_pie("Guardar cambios", self._guardar, principal=True)
        self.b_hecho = _boton_pie("Hecho", self.reject, principal=True)
        for b in (self.b_cancelar, self.b_guardar, self.b_hecho):
            pie.addWidget(b)
        lay.addLayout(pie)

    def _pestana(self, clave: str) -> QPushButton:
        activa = clave == self.clave
        b = QPushButton(_tr(NOMBRES[clave]))
        b.setAutoDefault(False)
        b.setFocusPolicy(Qt.NoFocus)
        b.setMinimumWidth(170)
        b.setFixedHeight(40 if activa else 36)        # la activa, un poco más alta
        if activa:
            estilo = (f"color:#FFFFFF;border:1px solid {self.tema.oscuro};"
                      f"background:{self.tema.v};")
        else:
            estilo = f"color:#BBBBBB;border:1px solid #000000;background:{PESTANA};"
        b.setStyleSheet(
            f"QPushButton{{{estilo}border-bottom:none;border-top-left-radius:9px;"
            "border-top-right-radius:9px;padding:0 18px;"
            f"font-family:{FUENTE};font-size:15px;font-weight:bold;}}"
            "QPushButton:hover{color:#FFFFFF;}")
        if activa:
            b.setToolTip(_tr("Estás en «{0}»", NOMBRES[clave]))
        else:
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(_tr("Pasar a «{0}»", NOMBRES[clave]))
            # Fuera de la señal: el botón se tira al rehacer la ventana.
            b.clicked.connect(lambda _c=False, k=clave: QTimer.singleShot(0, lambda: self._cambiar(k)))
        return b

    def _cambiar(self, clave: str) -> None:
        """Pasa a la otra lista en la misma ventana; la que se deja conserva
        sus cambios."""
        if clave == self.clave or clave not in NOMBRES:
            return
        self.clave = clave
        self.tema = TEMAS[clave]
        self.filtro = ""
        self._dictando = None
        self.almacen.poner_opcion("pestana", clave)
        self._construir()
        if not self._estados[clave]["cargada"] or not self.sucio():
            self.cargar()
        else:
            self._pintar()

    def _baldosa(self, nombre: str, tip: str, fn) -> QToolButton:
        """Un cuadro de la columna, con el degradado de la lista y el icono en
        blanco."""
        b = QToolButton()
        b.setIcon(_iconos.trazo(nombre, "#FFFFFF"))
        b.setIconSize(QSize(22, 22))
        b.setFixedSize(40, 40)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(_tr(tip))
        t = self.tema
        b.setStyleSheet(
            f"QToolButton{{background:{t.v};border:none;border-bottom:1px solid {t.oscuro};"
            "border-radius:7px;}"
            f"QToolButton:hover{{background:{t.v_encima};}}"
            f"QToolButton:pressed{{background:{t.v_hundido};}}"
            f"QToolButton:disabled{{background:{GRIS_APAGADO};border-bottom-color:#B5B5B5;}}")
        b.clicked.connect(lambda _c=False: fn())
        return b

    def _reloj(self) -> None:
        """Abre (o cierra) el panel del Reloj de la barra, junto a esta ventana."""
        cadena = (getattr(self.app.window, atributo("anillos"), None) or {}).get(CLAVE)
        abrir = getattr(cadena, "abrir_tiempo_junto", None)
        if callable(abrir):
            abrir(self)

    def _boton_voz(self) -> QToolButton:
        """Botón de dictado, con el estilo de los glifos de la columna."""
        t = self.tema
        b = QToolButton()
        b.setIcon(_iconos.trazo("microfono", "#FFFFFF"))
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(30, 30)
        b.setFocusPolicy(Qt.NoFocus)           # que no le quite el foco a la tarea
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(_tr("Entrada por voz (dictado del sistema)\n"
                     "Escribiendo una tarea: sigue la frase en esa tarea.\n"
                     "Si no: crea una tarea nueva arriba de la lista.\n"
                     "Mientras dictas, púlsalo otra vez para dar la tarea por escrita."))
        b.setCheckable(True)                   # hundido mientras se dicta
        b.setStyleSheet(
            f"QToolButton{{background:{t.v};border:none;border-bottom:1px solid {t.oscuro};"
            "border-radius:6px;}"
            f"QToolButton:hover{{background:{t.v_encima};}}"
            f"QToolButton:pressed,QToolButton:checked{{background:{t.v_hundido};"
            "border:2px solid #FFFFFF;}")
        b.clicked.connect(lambda _c=False: self._dictar())
        self.b_voz = b
        return b

    def _tarea_en_edicion(self) -> "_Fila | None":
        """La fila cuyo texto se está escribiendo (tiene el foco), si la hay."""
        w = QApplication.focusWidget()
        if isinstance(w, _Texto) and not w.isReadOnly() \
                and self.filas.get(w.fila.id) is w.fila:
            return w.fila
        return None

    def _dictar(self) -> None:
        """Una pulsación empieza a dictar y la siguiente termina:

        - Dictando en una tarea (y sin haber salido de ella): cierra el
          dictado y da la tarea por escrita, como un Intro; la siguiente
          pulsación ya crea otra tarea.
        - Escribiendo una tarea: el dictado sigue al final de su texto.
        - Si no: crea una tarea nueva arriba del todo y dicta en ella.
        """
        fila = self._tarea_en_edicion()
        if self._dictando is not None and fila is not None and fila.id == self._dictando:
            self._terminar_dictado(fila)
            return
        if fila is not None:
            self.activateWindow()
            fila.texto.setFocus(Qt.OtherFocusReason)
            fila.texto.al_final()
            self._dictando = fila.id
        else:
            self.buscar.clear()                # que la tarea nueva no quede oculta
            self._nueva(arriba=True)           # le da el foco en la siguiente vuelta
            self._dictando = self.tareas[0]["_id"]
        self.b_voz.setChecked(True)
        QTimer.singleShot(250, self._abrir_dictado)

    def _terminar_dictado(self, fila: "_Fila") -> None:
        self._dictando = None
        self.b_voz.setChecked(False)
        self._abrir_dictado()                  # Win+H otra vez: el dictado se cierra
        fila.texto.clearFocus()                # la tarea queda escrita
        t = self._tarea(fila.id)
        if t is not None and not t["texto"].strip():
            self.tareas.remove(t)              # sin nada dictado, la fila vacía sobra
            QTimer.singleShot(0, self._pintar)

    def _abrir_dictado(self) -> None:
        try:
            import ctypes
            u = ctypes.windll.user32
            win, h, suelta = 0x5B, 0x48, 0x0002            # VK_LWIN, «H», KEYEVENTF_KEYUP
            u.keybd_event(win, 0, 0, 0)
            u.keybd_event(h, 0, 0, 0)
            u.keybd_event(h, 0, suelta, 0)
            u.keybd_event(win, 0, suelta, 0)
        except Exception:  # noqa: BLE001 — fuera de este sistema o sin user32
            log.exception("Tareas: no se pudo abrir el dictado del sistema")
            QMessageBox.information(self, _tr("Tareas"),
                                    _tr("No se pudo abrir el dictado del sistema.\n"
                                    "Pulsa Win + H con el cursor en la tarea."))

    def _ayuda(self) -> None:
        QMessageBox.information(self, _tr("Tareas - Ayuda"), _tr(AYUDA))

    def _buscar(self, texto: str) -> None:
        self.filtro = texto.strip().casefold()
        self._pintar()

    def _visible(self, tarea: dict) -> bool:
        """Con el buscador, solo las que contienen lo escrito (y las vacías,
        que se están escribiendo)."""
        texto = tarea["texto"].strip()
        return not self.filtro or not texto or self.filtro in texto.casefold()

    # ---- Cargar / guardar -----------------------------------------------------------------
    def _leer(self, clave: str | None = None) -> list[dict]:
        if (clave or self.clave) == "modelo":
            return _datos.tareas_modelo(self.app)
        return _datos.limpias(self.almacen.tareas)

    def cargar(self, clave: str | None = None) -> None:
        """Vuelve a leer una lista (la visible si no se dice cuál)."""
        clave = clave or self.clave
        e = self._estados[clave]
        e["original"] = self._leer(clave)
        e["tareas"] = [{**t, "_id": next(_ids), "_borrada": False} for t in e["original"]]
        if not e["tareas"]:              # una fila en blanco para escribir
            e["tareas"].append(self._tarea_nueva())
        e["seleccion"] = set()
        e["ruta"] = _datos.ruta_actual(self.app)
        e["cargada"] = True
        if clave == self.clave:
            self._pintar()
        else:
            self._refrescar()

    def mostrar(self, clave: str | None = None) -> None:
        """Abre la ventana (en la pestaña ``clave`` si se da)."""
        if not self.isVisible():
            for e in self._estados.values():
                e["cargada"] = False     # al abrir, las dos listas tal como estén guardadas
        if clave and clave != self.clave:
            self._cambiar(clave)
        elif not self._estados[self.clave]["cargada"] or not self.sucio():
            self.cargar()
        self.show()
        self.raise_()
        self.activateWindow()

    def documento_cambiado(self) -> None:
        """Del modelo: tras Abrir/Nuevo/Deshacer su lista puede ser otra."""
        e = self._estados["modelo"]
        if not self.isVisible() or not e["cargada"]:
            return
        if not self.sucio("modelo"):
            if self._leer("modelo") != e["original"]:
                self.cargar("modelo")
            else:
                self._poner_titulo()
            return
        if _datos.ruta_actual(self.app) != e["ruta"]:
            self.cargar("modelo")
            self.app.viewport.flash_status(
                _tr("El modelo ha cambiado y se ha vuelto a leer su lista de tareas."), 5000)

    def _actuales(self, clave: str | None = None) -> list[dict]:
        tareas = self._estados[clave or self.clave]["tareas"]
        return _datos.limpias([t for t in tareas if not t["_borrada"]])

    def sucio(self, clave: str | None = None) -> bool:
        """Cambios sin guardar en una lista (la visible si no se dice cuál)."""
        e = self._estados[clave or self.clave]
        return e["cargada"] and self._actuales(clave) != e["original"]

    def sucia_alguna(self) -> bool:
        return any(self.sucio(k) for k in NOMBRES)

    def _escribir(self) -> None:
        for clave, e in self._estados.items():
            if not self.sucio(clave):
                continue
            lista = self._actuales(clave)
            e["original"] = lista          # antes: set_document_data avisa del cambio
            if clave == "modelo":
                _datos.poner_tareas_modelo(self.app, lista)
            else:
                self.almacen.poner_tareas(lista)
        self.guardada.emit()

    def _guardar(self) -> None:
        self._escribir()
        self.reject()

    def _preguntar_guardar(self) -> bool:
        """Si hay cambios en alguna lista, pregunta. False si el usuario cancela."""
        sucias = [k for k in NOMBRES if self.sucio(k)]
        if not sucias:
            return True
        donde = _tr(" y ").join("«{0}»".format(_tr(NOMBRES[k])) for k in sucias)
        caja = QMessageBox(QMessageBox.Question, _tr("Tareas"),
                           _tr("Se han hecho cambios en {0}.\n¿Quieres guardarlos?", donde),
                           QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, self)
        caja.button(QMessageBox.Yes).setText(_tr("Sí"))
        caja.button(QMessageBox.No).setText(_tr("No"))
        caja.button(QMessageBox.Cancel).setText(_tr("Cancelar"))
        respuesta = caja.exec()
        if respuesta == QMessageBox.Cancel:
            return False
        if respuesta == QMessageBox.Yes:
            self._escribir()
        else:
            for e in self._estados.values():
                e["tareas"] = [{**t, "_id": next(_ids), "_borrada": False}
                               for t in e["original"]]
        return True

    def reject(self) -> None:
        """Hecho, Cancelar, Esc y la ✕ de la ventana (QDialog.closeEvent llama
        aquí; si la ventana sigue visible, el cierre se anula)."""
        if not self._preguntar_guardar():
            return
        self.almacen.poner_opcion("geometria", self.saveGeometry().toBase64().data().decode())
        super().reject()

    # ---- Pintar ---------------------------------------------------------------------------
    def _abiertas(self) -> list[dict]:
        return [t for t in self.tareas if not t["hecha"] and not t["_borrada"]]

    def _hechas(self) -> list[dict]:
        return [t for t in self.tareas if t["hecha"] or t["_borrada"]]

    def _poner_titulo(self) -> None:
        if self.clave == "modelo":
            titulo = _tr("Tareas del modelo — {0}", _datos.nombre_modelo(self.app))
            ruta = _datos.ruta_actual(self.app)
            self.ruta.poner(str(ruta) if ruta else "")
        else:
            titulo = _tr("Tareas de IngeTrazo")
        self.setWindowTitle(titulo + (" *" if self.sucia_alguna() else ""))
        for clave, b in self._pestanas.items():   # «●»: esa lista tiene cambios sin guardar
            b.setText(_tr(NOMBRES[clave]) + ("  ●" if self.sucio(clave) else ""))

    def _pintar(self, foco: int | None = None) -> None:
        self.contenido.setUpdatesEnabled(False)
        while self.lista.count():
            item = self.lista.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.filas.clear()
        # El número sale de la posición: abiertas 1, 2, 3… y las hechas siguen
        # la cuenta; las borradas no cuentan. Se renumera cada vez que se pinta.
        cuenta = itertools.count(1)
        for t in self._abiertas():
            n = next(cuenta)
            if self._visible(t) or t["_id"] == foco:
                self._poner_fila(t, n)
        hechas = self._hechas()
        numeros = {t["_id"]: (None if t["_borrada"] else next(cuenta)) for t in hechas}
        self.lista.addWidget(_Separador(self, self._contar(hechas), self._plegado))
        if not self._plegado:
            for t in hechas:
                if self._visible(t) or t["_id"] == foco:
                    self._poner_fila(t, numeros[t["_id"]])
        self.lista.addStretch(1)
        self.contenido.setUpdatesEnabled(True)
        self._refrescar()
        if foco is not None and foco in self.filas:
            # Las filas nuevas aún no se ven: el foco, en la siguiente vuelta.
            QTimer.singleShot(0, lambda f=self.filas[foco]: self._enfocar(f))

    def _enfocar(self, fila: _Fila) -> None:
        if self.filas.get(fila.id) is not fila:
            return
        self.activateWindow()
        fila.texto.setFocus(Qt.OtherFocusReason)
        fila.texto.al_final()
        self.scroll.ensureWidgetVisible(fila)

    def _poner_fila(self, tarea: dict, numero: int | None = None) -> None:
        fila = _Fila(self, tarea, numero)
        fila.pintar(tarea, tarea["_id"] in self.seleccion)
        self.filas[tarea["_id"]] = fila
        self.lista.addWidget(fila)

    @staticmethod
    def _contar(lista) -> int:
        return sum(1 for t in lista if t["texto"].strip())

    def _refrescar(self) -> None:
        """Contadores, botones de la cabecera y del pie, sin rehacer las filas."""
        abiertas, hechas = self._contar(self._abiertas()), self._contar(self._hechas())
        self.contador.setText("{0} {1} · {2} {3}".format(abiertas, _tr('abierta' if abiertas == 1 else 'abiertas'), hechas, _tr('hecha' if hechas == 1 else 'hechas')))
        for i in range(self.lista.count()):
            w = self.lista.itemAt(i).widget()
            if isinstance(w, _Separador):
                w.etiqueta.setText(_tr(_tareas_hechas(hechas)))
        self.seleccion &= set(self.filas)
        sel = self._seccion_seleccionada()
        self.b_borrar.setEnabled(bool(self.seleccion))
        self.b_subir.setEnabled(sel is not None and sel.index(next(iter(self.seleccion))) > 0)
        self.b_bajar.setEnabled(sel is not None
                                and sel.index(next(iter(self.seleccion))) < len(sel) - 1)
        sucio = self.sucia_alguna()
        self.b_cancelar.setVisible(sucio)
        self.b_guardar.setVisible(sucio)
        self.b_hecho.setVisible(not sucio)
        self._poner_titulo()

    def _seccion_seleccionada(self) -> list[int] | None:
        """Ids de la sección de la única tarea seleccionada (para subir/bajar)."""
        if len(self.seleccion) != 1:
            return None
        tid = next(iter(self.seleccion))
        t = self._tarea(tid)
        if t is None or t["_borrada"]:
            return None
        seccion = self._hechas() if t["hecha"] else self._abiertas()
        return [x["_id"] for x in seccion if not x["_borrada"]]

    def _tarea(self, tid: int) -> dict | None:
        return next((t for t in self.tareas if t["_id"] == tid), None)

    def _indice(self, tid: int) -> int:
        return next(i for i, t in enumerate(self.tareas) if t["_id"] == tid)

    # ---- Acciones -------------------------------------------------------------------------
    def _tarea_nueva(self) -> dict:
        return {"texto": "", "hecha": False, "creada": _datos.ahora(), "hecha_en": None,
                "_id": next(_ids), "_borrada": False}

    def _nueva(self, arriba: bool) -> None:
        t = self._tarea_nueva()
        if arriba:
            self.tareas.insert(0, t)
        else:
            abiertas = self._abiertas()
            i = self._indice(abiertas[-1]["_id"]) + 1 if abiertas else 0
            self.tareas.insert(i, t)
        self.seleccion.clear()
        self._pintar(foco=t["_id"])

    def _intro(self, tid: int) -> None:
        """Intro en una tarea: otra nueva justo debajo."""
        actual = self._tarea(tid)
        if actual is None:
            return
        t = self._tarea_nueva()
        if actual["hecha"] or actual["_borrada"]:
            abiertas = self._abiertas()
            i = self._indice(abiertas[-1]["_id"]) + 1 if abiertas else 0
        else:
            i = self._indice(tid) + 1
        self.tareas.insert(i, t)
        self._pintar(foco=t["_id"])

    def _saltar(self, tid: int, paso: int) -> None:
        orden = list(self.filas)
        if tid not in orden:
            return
        j = orden.index(tid) + paso
        if 0 <= j < len(orden):
            fila = self.filas[orden[j]]
            fila.texto.setFocus()
            self.scroll.ensureWidgetVisible(fila)

    def _editado(self, tid: int, texto: str) -> None:
        t = self._tarea(tid)
        if t is not None:
            t["texto"] = texto
            self._refrescar()

    def _marcar(self, tid: int, hecha: bool) -> None:
        t = self._tarea(tid)
        if t is None:
            return
        t["hecha"] = hecha
        t["hecha_en"] = _datos.ahora() if hecha else None
        orig = next((o for o in self.original
                     if o["texto"] == t["texto"].strip() and o["hecha"] == hecha), None)
        if orig is not None:            # deshacer el cambio deja la tarea como estaba
            t["hecha_en"] = orig["hecha_en"]
        # Cambia de sección; fuera de la señal de la casilla, que aún existe.
        QTimer.singleShot(0, self._pintar)

    def _borrar(self, ids) -> None:
        for tid in ids:
            t = self._tarea(tid)
            if t is None:
                continue
            if not t["texto"].strip():
                self.tareas.remove(t)   # una vacía se quita sin más
            else:
                t["_borrada"] = True
        self.seleccion.clear()
        QTimer.singleShot(0, self._pintar)

    def _recuperar(self, tid: int) -> None:
        t = self._tarea(tid)
        if t is not None:
            t["_borrada"] = False
            QTimer.singleShot(0, self._pintar)

    def _seleccionar(self, tid: int, varias: bool) -> None:
        if varias:
            self.seleccion ^= {tid}
        else:
            self.seleccion = set() if self.seleccion == {tid} else {tid}
        for fid, fila in self.filas.items():
            t = self._tarea(fid)
            if t is not None:
                fila.pintar(t, fid in self.seleccion)
        self._refrescar()

    def _mover(self, paso: int) -> None:
        seccion = self._seccion_seleccionada()
        if seccion is None:
            return
        tid = next(iter(self.seleccion))
        j = seccion.index(tid) + paso
        if 0 <= j < len(seccion):
            self._mover_junto(tid, seccion[j], despues=paso > 0)

    def _misma_seccion(self, a: int, b: int) -> bool:
        ta, tb = self._tarea(a), self._tarea(b)
        if ta is None or tb is None or a == b or ta["_borrada"] or tb["_borrada"]:
            return False
        return ta["hecha"] == tb["hecha"]

    def _mover_junto(self, origen: int, destino: int, despues: bool) -> None:
        if not self._misma_seccion(origen, destino):
            return
        t = self.tareas.pop(self._indice(origen))
        i = self._indice(destino) + (1 if despues else 0)
        self.tareas.insert(i, t)
        self._pintar()

    def _plegar(self) -> None:
        self._plegado = not self._plegado
        self.almacen.poner_opcion(f"plegadas_{self.clave}", self._plegado)
        QTimer.singleShot(0, self._pintar)

    # ---- Imprimir y exportar --------------------------------------------------------------
    def _nombre_lista(self) -> str:
        if self.clave == "modelo":
            return f"Tareas - {Path(_datos.nombre_modelo(self.app)).stem}"
        return "Tareas - IngeTrazo"

    def _para_exportar(self) -> tuple[list[dict], list[dict]]:
        actuales = self._actuales()
        return ([t for t in actuales if not t["hecha"]], [t for t in actuales if t["hecha"]])

    def _imprimir(self) -> None:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

        abiertas, hechas = self._para_exportar()
        partes = [f"<h3 style='color:#000080;text-align:center'>{escape(self._nombre_lista())}</h3>",
                  "<p><b>" + _tr("Tareas abiertas: {0}", len(abiertas)) + "</b></p><table cellpadding='2'>"]
        partes += [f"<tr><td valign='top'>&#9744;</td><td valign='top' align='right'>"
                   f"<b>{n}.</b></td><td>{_html(t['texto'])}</td></tr>"
                   for n, t in enumerate(abiertas, 1)]
        partes.append("</table><p><b>" + _tr("Tareas hechas: {0}", len(hechas)) + "</b></p><table cellpadding='2'>")
        partes += [f"<tr><td valign='top'>&#9745;</td><td valign='top' align='right' "
                   f"style='color:#808080'>{n}.</td><td style='color:#808080'>"
                   f"<s>{_html(t['texto'])}</s></td></tr>"
                   for n, t in enumerate(hechas, len(abiertas) + 1)]
        partes.append("</table>")
        doc = QTextDocument()
        doc.setDefaultFont(_fuente(10))
        doc.setHtml("".join(partes))

        printer = QPrinter(QPrinter.HighResolution)
        vista = QPrintPreviewDialog(printer, self)
        vista.setWindowTitle(_tr("Tareas - Imprimir"))
        vista.paintRequested.connect(doc.print_)
        vista.resize(800, 700)
        vista.exec()

    def _exportar(self) -> None:
        formato = self.formato.currentData()
        carpeta = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) \
            or str(Path.home())
        inicio = str(Path(carpeta) / f"{self._nombre_lista()} - {_fecha_archivo()}.{formato}")
        filtro = "CSV (*.csv)" if formato == "csv" else _tr("Texto (*.txt)")
        ruta, _ = QFileDialog.getSaveFileName(
            self, _tr("Exportar CSV") if formato == "csv" else _tr("Exportar texto"), inicio, filtro)
        if not ruta:
            return
        abiertas, hechas = self._para_exportar()
        try:
            if formato == "csv":
                with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["N", _tr("Estado"), _tr("Tarea"), _tr("Creada"), _tr("Hecha")])
                    for n, t in enumerate(abiertas + hechas, 1):
                        w.writerow([n, _tr("hecha" if t["hecha"] else "abierta"), t["texto"],
                                    _corta(t.get("creada")), _corta(t.get("hecha_en"))])
            else:
                lineas = [self._nombre_lista(), "", _tr("TAREAS ABIERTAS: {0}", len(abiertas))]
                lineas += [_linea_txt(n, t["texto"]) for n, t in enumerate(abiertas, 1)]
                lineas += ["", _tr("TAREAS HECHAS: {0}", len(hechas))]
                lineas += [_linea_txt(n, t["texto"])
                           for n, t in enumerate(hechas, len(abiertas) + 1)]
                Path(ruta).write_text("\n".join(lineas) + "\n", encoding="utf-8")
        except OSError as err:
            log.exception("no se pudo exportar a %s", ruta)
            QMessageBox.critical(self, _tr("Tareas"),
                                 _tr("No se pudo crear el archivo de exportación:\n{0}", err))
            return
        caja = QMessageBox(QMessageBox.Question, _tr("Tareas"),
                           _tr("Archivo exportado:\n\n{0}\n\n¿Quieres abrirlo?", ruta),
                           QMessageBox.Yes | QMessageBox.No, self)
        caja.button(QMessageBox.Yes).setText(_tr("Sí"))
        caja.button(QMessageBox.No).setText(_tr("No"))
        if caja.exec() == QMessageBox.Yes:
            _datos.abrir_externo(ruta)


def _linea_txt(n: int, texto: str) -> str:
    """« 3 - primera línea», y las demás líneas de la tarea sangradas debajo."""
    cabeza = f" {n} - "
    primera, *resto = texto.split("\n")
    return "\n".join([cabeza + primera] + [" " * len(cabeza) + r for r in resto])


def _html(texto: str) -> str:
    return escape(texto).replace("\n", "<br>")


def _corta(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso)

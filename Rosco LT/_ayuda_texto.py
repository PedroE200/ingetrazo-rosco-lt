# SPDX-License-Identifier: GPL-3.0-or-later
"""La ayuda con imagen del panel de Texto.

Con el botón «?» de la cabecera encendido (se recuerda), al dejar el ratón
medio segundo sobre un campo (o sobre su rótulo) sale una tarjeta junto al
panel con un dibujo de lo que hace y una frase. Mientras está encendida, la
tarjeta sustituye a la ayuda emergente de siempre de esos campos.

``Ayudante(panel)``: ``poner(widget, clave)`` para cada campo; ``rotulos(rejilla)``
da a cada rótulo de una rejilla la ayuda del campo de su fila; ``encendida``.
"""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

log = logging.getLogger("ingetrazo.plugins.rosco_lt.texto")

W, H = 220, 96                                # el dibujo de la tarjeta
MORADO = QColor("#4b3aa8")
TINTA = QColor("#222222")
GRIS = QColor("#9a978f")
ROJO = QColor("#d62222")
ESPERA_MS = 500

# clave → (título, frase)
AYUDAS = {
    "texto": ("Texto", "Lo que se escribe. Intro hace otra línea."),
    "letra": ("Letra", "El tipo de letra con que se dibuja el texto."),
    "negrita": ("Negrita", "Letras más gruesas."),
    "cursiva": ("Cursiva", "Letras inclinadas."),
    "tamano": ("Tamaño", "La altura de la letra (con «altura de mayúsculas», la de la H)."),
    "contexto": ("Modelo o papel", "Modelo: el tamaño real en el dibujo. Papel: el tamaño impreso, "
                 "que se multiplica por la escala."),
    "escala": ("Escala", "Con «Papel»: 3 mm a 1/50 son 15 cm en el modelo."),
    "grosor": ("Grosor", "Hace las letras en volumen, con este fondo. Vacío o 0 = planas."),
    "alinear": ("Alinear", "Las líneas a la izquierda, centradas, a la derecha o justificadas."),
    "vertical": ("Alinear en vertical", "Arriba, en medio o abajo del contenedor (hace falta su alto)."),
    "interlineado": ("Interlineado", "Distancia entre una línea y la siguiente: 1 = normal, "
                     "1,5 = más separadas."),
    "ancho": ("Ancho de letra", "Estira o estrecha las letras: 1 = normal, 1,3 = más anchas."),
    "entre_letras": ("Entre letras", "Espacio extra entre cada letra (una medida)."),
    "entre_palabras": ("Entre palabras", "El hueco entre palabras: 1 = normal, 2 = el doble."),
    "insercion": ("Punto de inserción", "Qué punto del texto cae donde haces clic: una esquina, "
                  "el centro o la base de la primera o la última línea."),
    "desplazar": ("Desplazar XYZ", "Mueve el texto desde el punto de clic, en los ejes rojo, "
                  "verde y azul."),
    "ancho_max": ("Ancho máximo", "Las líneas se parten al llegar a este ancho. Vacío = sin límite."),
    "alto_cont": ("Alto del contenedor", "La altura de la caja donde va el texto, para alinearlo "
                  "en vertical."),
    "aristas": ("Aristas", "Dibuja el contorno de las letras con aristas."),
    "caras": ("Caras", "Rellena las letras con caras."),
    "etiqueta": ("Etiqueta", "En qué etiqueta (capa) van las aristas, las caras o el borde."),
    "color": ("Color", "El color de las caras de las letras."),
    "borde": ("Borde", "Un marco alrededor del texto."),
    "borde_tipo": ("Forma del borde", "Rectángulo, rectángulo redondeado, círculo, rombo o hexágono."),
    "borde_medida": ("Ajustado o a medida", "Ajustado: el borde sigue al texto. A medida: tiene "
                     "el ancho y el alto que le des."),
    "borde_caja": ("Caja del borde", "A qué se ajusta: la caja lógica de la letra, solo lo "
                   "dibujado o el contenedor."),
    "borde_valores": ("Medida del borde", "Ancho y alto del borde a medida (sin alto, la mitad del ancho)."),
    "borde_margen": ("Margen", "La separación entre el texto y el borde."),
    "margen_pct": ("Margen en %", "El margen como un tanto por ciento de la altura de la letra."),
    "borde_ocultar": ("Ocultar el borde", "Las aristas del borde, ocultas: no se ven, pero siguen ahí."),
}


# ---- los dibujos -------------------------------------------------------------------
def _fuente(tam: float, negrita=False, cursiva=False, familia="Segoe UI") -> QFont:
    f = QFont(familia)
    f.setPointSizeF(tam)
    f.setBold(negrita)
    f.setItalic(cursiva)
    return f


def _texto(p, x, y, s, tam=15.0, color=TINTA, **k) -> None:
    _dibujar(p, x, y, _tr(s), tam, color, **k)


def _dibujar(p, x, y, s, tam=15.0, color=TINTA, **k) -> None:
    p.setFont(_fuente(tam, **k))
    p.setPen(color)
    p.drawText(QPointF(x, y), s)


def _flecha(p, a: QPointF, b: QPointF, color=MORADO, puntas=2) -> None:
    p.setPen(QPen(color, 1.5))
    p.drawLine(a, b)
    d = b - a
    largo = max(1e-6, (d.x() ** 2 + d.y() ** 2) ** 0.5)
    u = QPointF(d.x() / largo, d.y() / largo)
    n = QPointF(-u.y(), u.x())
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    for punta, sentido in ((b, 1.0), (a, -1.0))[:puntas]:
        q = punta - u * 7.0 * sentido
        p.drawPolygon(QPolygonF([punta, q + n * 3.5, q - n * 3.5]))
    p.setBrush(Qt.NoBrush)


def _caja(p, r: QRectF, color=GRIS, rayas=True, ancho=1.2) -> None:
    pen = QPen(color, ancho)
    if rayas:
        pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(r)


def _rotulo(p, x, y, s, color=MORADO) -> None:
    _dibujar(p, x, y, s, 8.5, color)


def _d_texto(p):
    _texto(p, 14, 38, "Planta baja", 17)
    _texto(p, 14, 70, "cota +0,50", 17)
    p.setPen(QPen(MORADO, 1.5))
    p.drawLine(QPointF(118, 56), QPointF(118, 76))


def _d_letra(p):
    for i, fam in enumerate(("Segoe UI", "Georgia", "Consolas")):
        _texto(p, 14 + i * 70, 60, "Aa", 24, familia=fam)
        _rotulo(p, 14 + i * 70, 84, fam)


def _d_negrita(p):
    _texto(p, 18, 60, "Abc", 26)
    _texto(p, 120, 60, "Abc", 26, negrita=True)
    _rotulo(p, 18, 84, _tr("normal"))
    _rotulo(p, 120, 84, _tr("negrita"))


def _d_cursiva(p):
    _texto(p, 18, 60, "Abc", 26)
    _texto(p, 120, 60, "Abc", 26, cursiva=True)
    _rotulo(p, 18, 84, _tr("normal"))
    _rotulo(p, 120, 84, _tr("cursiva"))


def _d_tamano(p):
    _texto(p, 30, 74, "Hola", 34)
    _caja(p, QRectF(26, 34, 120, 0.1))
    _flecha(p, QPointF(170, 74), QPointF(170, 34))
    _rotulo(p, 178, 58, _tr("tamaño"))
    p.setPen(QPen(GRIS, 1, Qt.DashLine))
    p.drawLine(QPointF(26, 74), QPointF(176, 74))


def _d_contexto(p):
    p.setPen(QPen(GRIS, 1.2))
    p.drawRect(QRectF(14, 18, 70, 60))
    _texto(p, 22, 52, "Abc", 9)
    _rotulo(p, 18, 90, _tr("papel: 3 mm"))
    _flecha(p, QPointF(92, 48), QPointF(124, 48), puntas=1)
    _rotulo(p, 96, 40, "×50")
    _texto(p, 130, 60, "Abc", 26)
    _rotulo(p, 132, 90, _tr("modelo: 15 cm"))


def _d_escala(p):
    p.setPen(QPen(GRIS, 1.2))
    p.drawRect(QRectF(14, 14, 76, 68))
    _texto(p, 22, 44, "1/50", 13, MORADO, negrita=True)
    _texto(p, 22, 68, "Abc", 9)
    _flecha(p, QPointF(98, 48), QPointF(128, 48), puntas=1)
    _texto(p, 134, 62, "Abc", 24)


def _d_grosor(p):
    letra = QPainterPath()
    letra.addText(QPointF(30, 74), _fuente(46, negrita=True), "T")
    atras = letra.translated(22, -14)
    p.setPen(QPen(GRIS, 1.2))
    p.setBrush(QColor(220, 218, 210))
    p.drawPath(atras)
    caja, caja2 = letra.boundingRect(), atras.boundingRect()
    for a, b in ((caja.topLeft(), caja2.topLeft()), (caja.topRight(), caja2.topRight()),
                 (caja.bottomRight(), caja2.bottomRight())):
        p.drawLine(a, b)
    p.setPen(QPen(TINTA, 1.4))
    p.setBrush(QColor(255, 255, 255))
    p.drawPath(letra)
    _flecha(p, QPointF(caja.right() + 6, caja.bottom() + 4), QPointF(caja2.right() + 6, caja2.bottom() + 4))
    _rotulo(p, 150, 80, _tr("grosor"))


def _lineas(p, x0, x1, alinear: int, y0=24.0) -> None:
    largos = (1.0, 0.72, 0.88)
    p.setPen(QPen(TINTA, 5, Qt.SolidLine, Qt.RoundCap))
    for i, f in enumerate(largos):
        ancho = (x1 - x0) * (1.0 if alinear == 3 else f)
        x = x0 if alinear in (0, 3) else (x1 - ancho if alinear == 2 else (x0 + x1 - ancho) / 2)
        p.drawLine(QPointF(x, y0 + i * 14), QPointF(x + ancho, y0 + i * 14))


def _d_alinear(p):
    for i, nombre in enumerate(("izq.", "centro", "der.", "justif.")):
        x0 = 8 + i * 53
        _lineas(p, x0, x0 + 44, i)
        _rotulo(p, x0, 86, _tr(nombre))


def _d_vertical(p):
    for i, nombre in enumerate(("arriba", "medio", "abajo")):
        x0 = 12 + i * 70
        r = QRectF(x0, 10, 58, 64)
        _caja(p, r)
        y = (18, 38, 58)[i]
        p.setPen(QPen(TINTA, 5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x0 + 8, y), QPointF(x0 + 50, y))
        p.drawLine(QPointF(x0 + 8, y + 10), QPointF(x0 + 38, y + 10))
        _rotulo(p, x0 + 6, 88, _tr(nombre))


def _d_interlineado(p):
    _texto(p, 14, 34, "Planta baja", 17)
    _texto(p, 14, 76, "cota +0,50", 17)
    _flecha(p, QPointF(186, 20), QPointF(186, 62))
    p.setPen(QPen(MORADO, 1, Qt.DashLine))
    p.drawLine(QPointF(176, 20), QPointF(204, 20))
    p.drawLine(QPointF(176, 62), QPointF(204, 62))
    _rotulo(p, 192, 44, "×1")


def _d_ancho(p):
    _texto(p, 16, 60, "Abc", 26)
    p.save()
    p.translate(108, 0)
    p.scale(1.45, 1.0)
    _texto(p, 0, 60, "Abc", 26)
    p.restore()
    _rotulo(p, 16, 86, "1")
    _rotulo(p, 108, 86, "1,45")


def _d_entre_letras(p):
    for i, c in enumerate("ABCD"):
        _texto(p, 22 + i * 46, 60, c, 26)
    for i in range(3):
        _flecha(p, QPointF(46 + i * 46, 74), QPointF(66 + i * 46, 74))
    _rotulo(p, 22, 90, _tr("espacio extra entre cada letra"))


def _d_entre_palabras(p):
    _texto(p, 12, 56, "muro", 20)
    _texto(p, 128, 56, "de carga", 20)
    _flecha(p, QPointF(70, 68), QPointF(124, 68))
    _rotulo(p, 74, 86, _tr("hueco ×2"))


def _d_insercion(p):
    r = QRectF(40, 20, 140, 52)
    _caja(p, r)
    _texto(p, 54, 54, "Texto", 22)
    p.setPen(Qt.NoPen)
    for i in range(3):
        for j in range(3):
            q = QPointF(r.left() + i * r.width() / 2, r.bottom() - j * r.height() / 2)
            p.setBrush(ROJO if (i, j) == (0, 0) else GRIS)
            p.drawEllipse(q, 4.5 if (i, j) == (0, 0) else 3, 4.5 if (i, j) == (0, 0) else 3)
    _rotulo(p, 8, 90, _tr("el punto rojo cae donde haces clic"))


def _d_desplazar(p):
    o = QPointF(36, 74)
    p.setPen(QPen(QColor(214, 40, 40), 2))
    p.drawLine(o, o + QPointF(40, 0))
    p.setPen(QPen(QColor(40, 160, 60), 2))
    p.drawLine(o, o + QPointF(-20, -14))
    p.setPen(QPen(QColor(40, 90, 214), 2))
    p.drawLine(o, o + QPointF(0, -40))
    p.setBrush(ROJO)
    p.setPen(Qt.NoPen)
    p.drawEllipse(o, 3.5, 3.5)
    _texto(p, 110, 44, "Texto", 20)
    _flecha(p, o, QPointF(108, 48), puntas=1)
    _rotulo(p, 58, 90, _tr("desde el clic, en X, Y y Z"))


def _d_ancho_max(p):
    p.setPen(QPen(MORADO, 1, Qt.DashLine))
    p.drawLine(QPointF(20, 10), QPointF(20, 78))
    p.drawLine(QPointF(150, 10), QPointF(150, 78))
    _texto(p, 24, 30, "Las líneas se", 12)
    _texto(p, 24, 50, "parten al llegar", 12)
    _texto(p, 24, 70, "a este ancho", 12)
    _flecha(p, QPointF(20, 88), QPointF(150, 88))
    _rotulo(p, 156, 92, _tr("ancho máx."))


def _d_alto_cont(p):
    r = QRectF(30, 8, 110, 80)
    _caja(p, r)
    p.setPen(QPen(TINTA, 5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(42, 42), QPointF(126, 42))
    p.drawLine(QPointF(42, 54), QPointF(108, 54))
    _flecha(p, QPointF(154, 8), QPointF(154, 88))
    _rotulo(p, 162, 52, _tr("alto"))


def _letras(p, relleno: QColor | None, borde=True, x=24, y=70, tam=40) -> None:
    camino = QPainterPath()
    camino.addText(QPointF(x, y), _fuente(tam, negrita=True), "AB")
    p.setPen(QPen(TINTA, 1.4) if borde else Qt.NoPen)
    p.setBrush(relleno if relleno is not None else Qt.NoBrush)
    p.drawPath(camino)


def _d_aristas(p):
    _letras(p, None)
    _rotulo(p, 130, 52, _tr("solo el contorno"))


def _d_caras(p):
    _letras(p, QColor(200, 198, 190), borde=False)
    _rotulo(p, 130, 52, _tr("rellenas"))


def _d_etiqueta(p):
    _letras(p, QColor(230, 228, 222), x=14, tam=30, y=56)
    for i, (t, c) in enumerate((("Textos", "#e4ddfb"), ("Bordes", "#fadede"))):
        r = QRectF(110, 18 + i * 30, 96, 22)
        p.setPen(QPen(GRIS, 1))
        p.setBrush(QColor(c))
        p.drawRoundedRect(r, 5, 5)
        _texto(p, r.left() + 8, r.top() + 16, t, 10)
    _rotulo(p, 14, 88, _tr("cada parte en su etiqueta"))


def _d_color(p):
    for i, c in enumerate(("#1e90ff", "#ff8c00", "#c71585")):
        camino = QPainterPath()
        camino.addText(QPointF(18 + i * 66, 66), _fuente(34, negrita=True), "A")
        p.setPen(QPen(TINTA, 1))
        p.setBrush(QColor(c))
        p.drawPath(camino)


def _d_borde(p):
    _texto(p, 54, 58, "Texto", 22)
    p.setPen(QPen(TINTA, 1.6))
    p.drawRect(QRectF(40, 24, 130, 46))


def _d_borde_tipo(p):
    p.setPen(QPen(TINTA, 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(8, 30, 36, 26))
    p.drawRoundedRect(QRectF(52, 30, 36, 26), 8, 8)
    p.drawEllipse(QPointF(114, 43), 17, 17)
    p.drawPolygon(QPolygonF([QPointF(158, 26), QPointF(176, 43), QPointF(158, 60), QPointF(140, 43)]))
    p.drawPolygon(QPolygonF([QPointF(188, 43), QPointF(196, 29), QPointF(210, 29), QPointF(218, 43),
                             QPointF(210, 57), QPointF(196, 57)]))


def _d_borde_medida(p):
    _texto(p, 18, 54, "Abc", 16)
    p.setPen(QPen(TINTA, 1.4))
    p.drawRect(QRectF(12, 34, 52, 28))
    _rotulo(p, 12, 86, _tr("ajustado"))
    _texto(p, 128, 54, "Abc", 16)
    p.drawRect(QRectF(100, 16, 108, 60))
    _rotulo(p, 120, 90, _tr("a medida"))


def _d_borde_caja(p):
    _texto(p, 22, 58, "gp", 26)
    _caja(p, QRectF(18, 22, 40, 48), MORADO)
    _rotulo(p, 14, 88, _tr("lógica"))
    _texto(p, 92, 58, "gp", 26)
    _caja(p, QRectF(90, 36, 36, 32), MORADO)
    _rotulo(p, 84, 88, _tr("contenido"))
    _caja(p, QRectF(150, 10, 62, 64))
    _texto(p, 162, 50, "gp", 22)
    _caja(p, QRectF(150, 10, 62, 64), MORADO, rayas=False, ancho=1.0)
    _rotulo(p, 148, 88, _tr("contenedor"))


def _d_borde_valores(p):
    r = QRectF(40, 16, 120, 52)
    p.setPen(QPen(TINTA, 1.4))
    p.drawRect(r)
    _texto(p, 70, 48, "Texto", 14)
    _flecha(p, QPointF(r.left(), 80), QPointF(r.right(), 80))
    _rotulo(p, 86, 94, _tr("ancho"))
    _flecha(p, QPointF(176, r.top()), QPointF(176, r.bottom()))
    _rotulo(p, 182, 46, _tr("alto"))


def _d_borde_margen(p):
    p.setPen(QPen(TINTA, 1.4))
    p.drawRect(QRectF(20, 14, 160, 62))
    _texto(p, 66, 54, "Texto", 18)
    _caja(p, QRectF(62, 34, 72, 26), GRIS)
    _flecha(p, QPointF(20, 46), QPointF(62, 46))
    _rotulo(p, 26, 40, _tr("margen"))


def _d_margen_pct(p):
    p.setPen(QPen(TINTA, 1.4))
    p.drawRect(QRectF(20, 14, 160, 62))
    _texto(p, 66, 58, "Hola", 22)
    _flecha(p, QPointF(56, 30), QPointF(56, 60))
    _rotulo(p, 24, 90, _tr("10 % de la altura de la letra"))


def _d_borde_ocultar(p):
    _texto(p, 56, 56, "Texto", 22)
    p.setPen(QPen(GRIS, 1.2, Qt.DashLine))
    p.drawRect(QRectF(40, 22, 130, 46))
    _rotulo(p, 40, 88, _tr("aristas ocultas (siguen ahí)"))


DIBUJOS = {k: globals().get("_d_" + k) for k in AYUDAS}


def dibujo(clave: str) -> QPixmap:
    dpr = 2.0
    pm = QPixmap(int(W * dpr), int(H * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QColor(255, 255, 255))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    try:
        f = DIBUJOS.get(clave)
        if f is not None:
            f(p)
    except Exception:  # noqa: BLE001 — sin dibujo, queda la frase
        log.exception("no se pudo dibujar la ayuda de %s", clave)
    p.setPen(QPen(QColor(221, 221, 221), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, W - 1, H - 1))
    p.end()
    return pm


# ---- la tarjeta y quien la saca --------------------------------------------------
class Tarjeta(QFrame):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("ayuda_texto")
        self.setStyleSheet("QFrame#ayuda_texto { background: #ffffe8; border: 1px solid #b9b6ae;"
                           " border-radius: 6px; }"
                           "QLabel { color: #222; background: transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        self.titulo = QLabel()
        f = self.titulo.font()
        f.setBold(True)
        self.titulo.setFont(f)
        self.imagen = QLabel()
        self.frase = QLabel()
        self.frase.setWordWrap(True)
        self.frase.setFixedWidth(W)
        for w in (self.titulo, self.imagen, self.frase):
            lay.addWidget(w)

    def poner(self, clave: str) -> None:
        titulo, frase = AYUDAS.get(clave, (clave, ""))
        self.titulo.setText(_tr(titulo))
        self.imagen.setPixmap(dibujo(clave))
        self.frase.setText(_tr(frase))
        self.adjustSize()


class Ayudante(QObject):
    def __init__(self, panel: QWidget, encendida: bool = True) -> None:
        super().__init__(panel)
        self.panel = panel
        self.encendida = encendida
        self.claves: dict = {}                 # id(widget) → clave
        self.tarjeta = Tarjeta(panel)
        self._sobre = None
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(ESPERA_MS)
        self._espera.timeout.connect(self._mostrar)

    def poner(self, widget: QWidget, clave: str) -> None:
        if widget is None:
            return
        self.claves[id(widget)] = clave
        widget.installEventFilter(self)
        widget.setAttribute(Qt.WA_Hover, True)

    def rotulos(self, rejilla) -> None:
        """Cada rótulo (columna 0) toma la ayuda del primer campo con ayuda de su fila."""
        for fila in range(rejilla.rowCount()):
            item = rejilla.itemAtPosition(fila, 0)
            rotulo = item.widget() if item is not None else None
            if not isinstance(rotulo, QLabel):
                continue
            otro = rejilla.itemAtPosition(fila, 1)
            clave = self._clave_en(otro)
            if clave:
                self.poner(rotulo, clave)

    def _clave_en(self, item):
        if item is None:
            return None
        w = item.widget()
        if w is not None and id(w) in self.claves:
            return self.claves[id(w)]
        lay = item.layout()
        if lay is not None:
            for i in range(lay.count()):
                c = self._clave_en(lay.itemAt(i))
                if c:
                    return c
        return None

    def encender(self, si: bool) -> None:
        self.encendida = bool(si)
        if not si:
            self._espera.stop()
            self.tarjeta.hide()

    def _mostrar(self) -> None:
        w = self._sobre
        if w is None or not self.encendida or not w.isVisible() or not self.panel.isVisible():
            return
        self.tarjeta.poner(self.claves.get(id(w), ""))
        # Junto al panel (a su derecha; si no cabe, a la izquierda), a la altura del campo.
        marco = self.panel.frameGeometry()
        y = w.mapToGlobal(w.rect().topLeft()).y() - 6
        pantalla = QGuiApplication.screenAt(marco.center()) or QGuiApplication.primaryScreen()
        zona = pantalla.availableGeometry()
        x = marco.right() + 8
        if x + self.tarjeta.width() > zona.right():
            x = marco.left() - 8 - self.tarjeta.width()
        y = max(zona.top(), min(y, zona.bottom() - self.tarjeta.height()))
        self.tarjeta.move(x, y)
        self.tarjeta.show()
        self.tarjeta.raise_()

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        t = ev.type()
        if t in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            if self.encendida and id(obj) in self.claves:
                self._sobre = obj
                self._espera.start()
        elif t in (QEvent.Type.Leave, QEvent.Type.HoverLeave, QEvent.Type.MouseButtonPress,
                   QEvent.Type.Hide):
            if obj is self._sobre:
                self._sobre = None
                self._espera.stop()
                self.tarjeta.hide()
        elif t == QEvent.Type.ToolTip and self.encendida and id(obj) in self.claves:
            return True                        # la tarjeta hace de ayuda emergente
        return False

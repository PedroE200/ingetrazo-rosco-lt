# SPDX-License-Identifier: GPL-3.0-or-later
"""La línea de órdenes del rosco: un recuadro que va indicando el paso a paso
de la orden en curso. Sale debajo del submenú y, cuando este se oculta (al
empezar a poner puntos), va centrado y pegado al borde de abajo del visor. No
coge el ratón ni el teclado.

``PASOS``: lo que se pide en cada clic, por (orden, modo). ``ABIERTAS``: las
que no tienen un número fijo de pasos (el último se repite y no se cuentan).
"""
from __future__ import annotations

from ._flotante import mover_a
from . import _edicion
from ._idioma import _tr
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

ANCHO = 290
ALTO_RESERVA = 56.0                     # lo que se le guarda debajo del submenú
_ESTILO = """
QFrame#linea_orden { background: #fbfaf6; border: 1px solid #bdbab3; border-radius: 6px; }
QLabel { background: transparent; color: #222222; font-size: 8.5pt; }
QLabel#titulo { color: #4b3aa8; font-weight: bold; }
QFrame#linea_orden[pegada="true"] { border-bottom: none; border-bottom-left-radius: 0;
                                    border-bottom-right-radius: 0; }
"""

PASOS = {
    ("rect", "esquina"): ("Clic en una esquina.",
                          "Clic en la esquina opuesta (o teclea ancho;alto + Enter)."),
    ("rect", "centro"): ("Clic en el centro.", "Clic en una esquina (o teclea ancho;alto + Enter)."),
    ("rect", "lado"): ("Clic en el inicio del lado.", "Clic en el final del lado (va por los ejes).",
                       "Clic para el fondo (o teclea la medida + Enter)."),
    ("rect", "girado"): ("Clic en el inicio del lado.", "Clic en el final del lado, en cualquier dirección.",
                         "Clic para el fondo (o teclea la medida + Enter)."),
    ("poly", "centro"): ("Clic en el centro.", "Clic en un vértice (o teclea el radio + Enter)."),
    ("poly", "lado"): ("Clic en un extremo de la arista.",
                       "Clic en el otro extremo (o teclea su longitud + Enter)."),
    ("circle", "centro"): ("Clic en el centro.", "Clic en el borde (o teclea el radio + Enter)."),
    ("circle", "diámetro"): ("Clic en un punto.", "Clic en el punto opuesto (o teclea el diámetro + Enter)."),
    ("arco", "arco"): ("Clic en un extremo.", "Clic en el otro extremo.", "Clic en la flecha (o tecléala + Enter)."),
    ("arco", "3 puntos"): ("Clic en el inicio.", "Clic en un punto del arco.", "Clic en el final."),
    ("arco", "centro"): ("Clic en el centro.", "Clic en el inicio del arco.", "Clic en el ángulo final."),
    ("arco", "porción"): ("Clic en el centro.", "Clic en el inicio.", "Clic en el ángulo final."),
    ("linea", "guía"): ("Clic en el primer punto de la guía.", "Clic en el segundo punto."),
    ("linea", "equidist."): ("Clic en una cara o una polilínea.", "Arrastra o teclea la distancia + Enter."),
    ("linea", "paralela"): ("Clic en un segmento o una línea abierta.",
                            "Lleva el ratón al lado y haz clic, o teclea la distancia + Enter."),
    ("empujar", "redondear 3D"): ("Clic en una arista (o usa las seleccionadas).",
                             "Aleja el ratón o teclea el radio + Enter."),
    ("medir", "cota"): ("Clic en el primer punto.", "Clic en el segundo punto.",
                        "Clic en la posición de la línea de cota."),
    ("medir", "medir"): ("Clic en el primer punto.", "Clic en el segundo punto."),
    ("move", "mover"): ("Clic en el punto base.", "Clic en el destino (o teclea la distancia + Enter)."),
    ("move", "copia"): ("Clic en el punto base.", "Clic donde quieras la copia (o teclea la distancia + Enter)."),
    ("move", "empujar/tirar"): ("Clic en una cara.", "Mueve el ratón y haz clic, o teclea la altura + Enter."),
    ("move", "estirar ventana"): ("Clic en una esquina de la ventana.", "Clic en la esquina opuesta.",
                                  "Clic en el punto base.", "Clic en el destino (o teclea la distancia + Enter)."),
    ("move", "prolongar a plano"): ("Clic en el elemento, cerca del extremo que se alarga.",
                                    "Clic en la cara que hace de plano."),
    ("linea", "contorno 3D"): ("Elige las aristas del perímetro (las seleccionadas, o clic en ellas).",
                               "Ratón sobre una cara del lado y clic, o teclea la distancia + Enter."),
    ("move", "vértices"): ("Pasa por un vértice y arrastra su cuadradito verde.",
                           "Clic en el destino (o teclea la distancia + Enter)."),
    ("scale", "libre"): ("Clic en un tirador de la caja.", "Mueve el ratón y haz clic, o teclea la escala + Enter."),
    ("rotate", "sin copia"): ("Clic en el centro de giro.", "Clic en el inicio del ángulo.",
                              "Clic en el ángulo final (o teclea los grados + Enter)."),
    ("rotate", "con copia"): ("Clic en el centro de giro.", "Clic en el inicio del ángulo.",
                              "Clic en el ángulo final (o teclea los grados + Enter)."),
}
PASOS = _edicion.limpiar(PASOS)
ABIERTAS = {
    ("move", "alinear"): ("Selecciona primero lo que quieras alinear.",),
    ("linea", "línea"): ("Clic en el primer punto.",
                         "Clic en el siguiente punto; si cierras un contorno, pasa a la altura. Esc termina."),
    ("borrar", "borrar"): ("Clic o arrastra sobre aristas u objetos para borrarlos.",),
    ("borrar", "ocultar"): ("Clic o arrastra sobre aristas u objetos para ocultarlos.",),
    ("pintar", "pintar"): ("Clic en las caras que quieras pintar.",),
    ("pintar", "muestrear material"): ("Clic en una cara para coger su material.",),
    ("seleccionar", "ventana"): ("Clic, o arrastra una ventana (izq.→der.) o captura (der.→izq.).",),
    ("seleccionar", "lazo"): ("Arrastra rodeando lo que quieras (Ctrl añade, Mayús alterna).",),
    ("scale", "por referencia"): ("Sigue los puntos que te pide la barra de estado. Esc cancela.",),
}


def paso(clave: str, modo, clics: int, nombre: str) -> tuple | None:
    """``(título, texto)`` de la orden tras ``clics`` clics, o None si no está en la tabla."""
    fijos = PASOS.get((clave, modo))
    if fijos is not None:
        n = min(clics, len(fijos) - 1)
        return _tr("{0} · paso {1} de {2}", _tr(nombre), n + 1, len(fijos)), fijos[n]
    abiertos = ABIERTAS.get((clave, modo))
    if abiertos is not None:
        return nombre, abiertos[min(clics, len(abiertos) - 1)]
    return None


class LineaOrden(QFrame):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
                         | Qt.WindowTransparentForInput)
        self.setObjectName("linea_orden")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_ESTILO)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 5, 9, 6)
        lay.setSpacing(1)
        self.titulo = QLabel()
        self.titulo.setObjectName("titulo")
        self.texto = QLabel()
        self.texto.setWordWrap(True)
        lay.addWidget(self.titulo)
        lay.addWidget(self.texto)
        self.setFixedWidth(ANCHO)
        self._puesto = None

    def poner(self, titulo: str, texto: str, pos: QPoint, pegada: bool = False) -> None:
        """Con este texto y centrado en ``pos`` (global): con su borde de
        arriba en ``pos`` o, ``pegada``, con el de abajo apoyado en ``pos``."""
        if (titulo, texto) != self._puesto:
            self._puesto = (titulo, texto)
            self.titulo.setText(_tr(titulo))
            self.texto.setText(_tr(texto))
            self.adjustSize()
        if bool(self.property("pegada")) != pegada:
            self.setProperty("pegada", pegada)
            self.style().unpolish(self)
            self.style().polish(self)
        destino = QPoint(pos.x() - self.width() // 2, pos.y() - self.height() if pegada else pos.y())
        if self.pos() != destino:
            mover_a(self, destino)
        if not self.isVisible():
            self.show()

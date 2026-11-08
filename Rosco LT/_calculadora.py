# SPDX-License-Identifier: GPL-3.0-or-later
"""La calculadora suelta (botoncito de la diana, debajo de Apagar): + − × ÷ y
paréntesis, también tecleando; Enter o «=» calcula y «Copiar» lo
deja en el portapapeles. Sale al lado de la diana, se arrastra por cualquier
hueco libre y Esc o ✕ la cierran. Las cuentas, como las de la ventanita de
medidas (``_medidas.calcular``)."""
from __future__ import annotations

from ._idioma import _tr
from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout,
)

from ._medidas import _formatear, botones_casilla, calcular, unidad_doc
from ._tiempo import _ESTILO_BOTONES, _Arrastrable

TECLAS = (("7", 0, 0), ("8", 0, 1), ("9", 0, 2), ("÷", 0, 3),
          ("4", 1, 0), ("5", 1, 1), ("6", 1, 2), ("×", 1, 3),
          ("1", 2, 0), ("2", 2, 1), ("3", 2, 2), ("−", 2, 3),
          ("0", 3, 0), (",", 3, 1), ("C", 3, 2), ("+", 3, 3),
          ("(", 4, 0), (")", 4, 1), ("←", 4, 2), ("=", 4, 3))
OPERACIONES = "÷×−+"


class Calculadora(_Arrastrable, QFrame):
    def __init__(self, padre) -> None:
        super().__init__(padre, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("diana_calc")
        # Fuera del marco redondeado, transparente (sin banda negra).
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Colores fijos, como el Control de tiempo (el tema oscuro de
        # IngeTrazo pondría el texto blanco sobre blanco).
        self.setStyleSheet(
            "QFrame#diana_calc { background: #ffffff; border: 1.5px solid #d62222; "
            "border-radius: 8px; }"
            "QFrame#diana_calc QLabel { color: #111; background: transparent; }"
            "QLineEdit { background: #fff; color: #111; border: 1px solid #cfccc5; "
            "border-radius: 4px; padding: 3px 6px; font-size: 13pt; }"
            + _ESTILO_BOTONES
            + "QPushButton#op { background: #fadede; }"
            + "QPushButton { padding: 1px 2px; min-height: 18px; }")   # compacta: la letra, igual
        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 2, 5, 5)
        lay.setSpacing(3)
        cabeza = QHBoxLayout()
        asa = QLabel("⠿⠿")
        asa.setStyleSheet("color: #b9b6ae;")
        asa.setCursor(Qt.SizeAllCursor)
        cabeza.addWidget(asa)
        titulo = QLabel(_tr("Calculadora"))
        titulo.setCursor(Qt.SizeAllCursor)
        f = titulo.font()
        f.setBold(True)
        titulo.setFont(f)
        cabeza.addWidget(titulo, 1)
        cerrar = QToolButton()
        cerrar.setText("✕")
        cerrar.setToolTip(_tr("Cerrar (Esc)"))
        cerrar.setAutoRaise(True)
        cerrar.setFixedSize(QSize(22, 22))
        cerrar.setStyleSheet("QToolButton { color: #111; border: none; border-radius: 4px; }"
                             "QToolButton:hover { background: #fadede; }")
        cerrar.clicked.connect(self.hide)
        cabeza.addWidget(cerrar)
        lay.addLayout(cabeza)
        self.pantalla = QLineEdit()
        self.pantalla.setAlignment(Qt.AlignRight)
        self.pantalla.setPlaceholderText("120/2+30")
        self.pantalla.returnPressed.connect(self._igual)
        botones_casilla(self.pantalla, lambda _c=False: self._igual(),
                        lambda _c=False: (self.pantalla.clear(), self.pantalla.setFocus()), unidad_doc())
        lay.addWidget(self.pantalla)
        g = QGridLayout()
        g.setSpacing(2)
        for texto, fila, col in TECLAS:
            b = QPushButton(_tr(texto))
            b.setFocusPolicy(Qt.NoFocus)
            if texto in OPERACIONES:
                b.setObjectName("op")
            elif texto == "=":
                b.setObjectName("prim")
            b.clicked.connect(lambda _c=False, t=texto: self._tecla(t))
            g.addWidget(b, fila, col)
        lay.addLayout(g)
        self.copiar = QPushButton(_tr("Copiar"))
        self.copiar.setFocusPolicy(Qt.NoFocus)
        self.copiar.setToolTip(_tr("Calcula y deja el resultado en el portapapeles"))
        self.copiar.clicked.connect(self._copiar)
        lay.addWidget(self.copiar)
        self.setFixedWidth(246)                # caben 10 cifras, la unidad y los botones
        self.adjustSize()

    def mostrar(self, pos: QPoint) -> None:
        self.pantalla._unidad.poner(unidad_doc())   # la del dibujo abierto
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.pantalla.setFocus()
        self.pantalla.selectAll()

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(ev)

    def _tecla(self, t: str) -> None:
        if t == "C":
            self.pantalla.clear()
        elif t == "←":
            self.pantalla.backspace()
        elif t == "=":
            self._igual()
        else:
            self.pantalla.insert(t)
        self.pantalla.setFocus()

    def _igual(self) -> bool:
        if not self.pantalla.text().strip():
            return False
        try:
            self.pantalla.setText(_formatear(calcular(self.pantalla.text())))
            return True
        except Exception:  # noqa: BLE001 — una cuenta mal escrita
            self.pantalla.selectAll()
            return False

    def _copiar(self) -> None:
        if not self._igual():
            return
        QApplication.clipboard().setText(self.pantalla.text())
        self.copiar.setText(_tr("¡Copiado!"))
        QTimer.singleShot(1200, lambda: self.copiar.setText(_tr("Copiar")))

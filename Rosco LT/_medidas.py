# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventanita de medidas de Rosco LT: un renglón por medida y una calculadora.

Aparece sola junto al cursor en cada punto (cada segmento de la línea, cada
fase del rectángulo, la altura…) y lo sigue, con la medida actual en gris.
No le quita el teclado al visor: lo que se teclea va a su renglón y las
teclas de IngeTrazo (flechas, Ctrl…) siguen funcionando. Cada medida va en su
renglón (p. ej. Ancho / Alto); Enter pasa al siguiente y, en el último,
aplica. Tab o «;» cambian de renglón; Esc borra lo tecleado. Un clic en ella
le da el teclado (para la calculadora). Las medidas aceptan las mismas
unidades que IngeTrazo («2,5», «30cm», «1500mm»). El botón de la calculadora
abre una calculadora sencilla (+ − × ÷); «Usar» copia el resultado al
renglón activo, «Enter» además lo aplica y «Esc» la cierra sin usarlo.
"""
from __future__ import annotations

from ._idioma import _tr
import ast
import logging
import operator
import time

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QCursor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ._voz import con_microfono, icono_microfono, medida_dictada, vigia

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

ROJO = "#d62222"
QUIETA_S = 0.3                         # ratón parado este tiempo: la ventanita se para
ANCHO = 258                            # caben 10 cifras, la unidad y los botones
PISTA = "Enter aplica · Esc borra"
DERECHA_DEL_LAPIZ = 38                 # el cuerpo del lápiz acaba antes
DEBAJO_DEL_LAPIZ = 22                  # si no cabe arriba o a la derecha
ESPERA_CIERRE_MS = 200                 # que Win+H llegue con el foco aún en la casilla

_ESTILO = f"""
QFrame#marco {{ background: #ffffff; border: 1.5px solid {ROJO}; border-radius: 7px; }}
QLabel#titulo {{ color: #505050; font-size: 8.5pt; }}
QLabel#pista {{ color: #6e6e6e; font-size: 7.5pt; }}
QLabel {{ color: #444441; font-size: 8.5pt; }}
QLineEdit {{ border: 1px solid #b9b8b2; padding: 0px 2px; font-size: 10pt;
             background: #ffffff; color: #111111; }}
QLineEdit:focus, QLineEdit[activo="true"] {{ border: 1.5px solid {ROJO}; }}QLineEdit[malo="true"] {{ border: 1.5px solid #b00020; background: #fdecee; }}
QPushButton {{ border: 1px solid #b4b2a9; border-radius: 4px; background: #ffffff;
               padding: 0px 1px; min-width: 14px; min-height: 16px; color: #111111; }}
QPushButton:hover {{ background: #fadede; }}
QPushButton#enter {{ background: {ROJO}; color: #ffffff; border: none; font-weight: bold; }}
QPushButton#usar {{ border: 1px solid {ROJO}; color: {ROJO}; }}
QPushButton#esc {{ background: #f1efe8; color: #444441; }}
QToolButton {{ border: 1px solid {ROJO}; border-radius: 4px; background: #fadede; }}
"""

# ---- Calculadora: solo números y + − × ÷ ( ) ------------------------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv}


def calcular(expresion: str) -> float:
    """Evalúa ``expresion`` con números y + − × ÷ ( ). Coma = decimal."""
    texto = (expresion.replace("×", "*").replace("÷", "/").replace("−", "-")
             .replace(",", ".").strip())
    if not texto:
        raise ValueError("vacío")
    arbol = ast.parse(texto, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ValueError("expresión no válida")

    return ev(arbol)


def _formatear(v: float) -> str:
    texto = f"{v:.6f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") if texto else "0"


def _icono_calculadora() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(17, 17, 17))
    p.drawRoundedRect(QRectF(7, 3, 18, 26), 3, 3)
    p.setBrush(QColor(255, 255, 255))
    p.drawRect(QRectF(10, 6, 12, 6))
    for fila in range(3):
        for col in range(3):
            p.drawRect(QRectF(10 + col * 4.5, 15 + fila * 4.5, 3, 3))
    p.end()
    return QIcon(pm)


VERDE = "#2e9b3e"


def icono_check() -> QIcon:
    """La V verde de aplicar, como hecha a mano (rotulador)."""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2.0, 2.0)
    v = QPainterPath()
    v.moveTo(2.6, 13.2)
    v.cubicTo(4.2, 12.4, 5.4, 13.6, 6.6, 15.2)
    v.cubicTo(7.6, 16.5, 8.4, 17.8, 9.1, 18.6)
    v.cubicTo(11.6, 13.6, 15.4, 8.2, 21.4, 3.1)
    v.cubicTo(21.9, 2.7, 22.6, 3.3, 22.1, 3.8)
    v.cubicTo(16.8, 9.4, 13.3, 14.8, 10.6, 20.6)
    v.cubicTo(10.1, 21.6, 8.9, 21.7, 8.2, 20.8)
    v.cubicTo(6.7, 18.6, 5.3, 16.4, 3.4, 14.6)
    v.cubicTo(2.9, 14.1, 2.3, 13.6, 2.6, 13.2)
    v.closeSubpath()
    p.fillPath(v, QColor(VERDE))
    p.end()
    return QIcon(pm)


def icono_aspa() -> QIcon:
    """El aspa roja de borrar, como un tachón a rotulador (con su segunda
    pasada fina)."""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2.0, 2.0)
    rojo = QColor(ROJO)
    for (puntos, ancho, opaco) in (
            (((3, 3.5), (7, 7, 10, 11.5, 13.5, 14), (16, 16, 18.5, 18.5, 21, 21)), 3.2, 1.0),
            (((4.5, 3), (8, 7, 11, 10.5, 14, 13.5)), 1.2, 0.7),
            (((21, 3), (17.5, 6.5, 15, 10, 12, 12.5), (9, 15.5, 6, 18, 3, 21.5)), 3.0, 1.0),
            (((20, 4.6), (16.6, 8, 13, 11.6, 10, 14.2)), 1.0, 0.7)):
        c = QColor(rojo)
        c.setAlphaF(opaco)
        p.setPen(QPen(c, ancho, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        t = QPainterPath()
        t.moveTo(*puntos[0])
        for tramo in puntos[1:]:
            t.cubicTo(*tramo)
        p.drawPath(t)
    p.end()
    return QIcon(pm)


def icono_retroceso() -> QIcon:
    """La tecla de retroceso: una flecha gruesa hacia la izquierda con un aspa."""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2.0, 2.0)
    gris = QColor(68, 68, 65)
    p.setPen(QPen(gris, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    t = QPainterPath()
    t.moveTo(9.0, 5.0)
    t.lineTo(21.5, 5.0)
    t.lineTo(21.5, 19.0)
    t.lineTo(9.0, 19.0)
    t.lineTo(2.0, 12.0)
    t.closeSubpath()
    p.drawPath(t)
    p.setPen(QPen(gris, 1.8, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(11.5, 9.0), QPointF(17.5, 15.0))
    p.drawLine(QPointF(17.5, 9.0), QPointF(11.5, 15.0))
    p.end()
    return QIcon(pm)


def unidad_doc() -> str:
    """La unidad de longitud del dibujo («cm», «m», «mm»…)."""
    try:
        from core.units import length_suffix, model_unit
        return str(length_suffix(model_unit())).strip()
    except Exception:  # noqa: BLE001
        return ""


def unidad_de(rotulo: str) -> str:
    """La unidad que se enseña junto a la casilla ``rotulo``."""
    r = (rotulo or "").lower()
    if "°" in r or "ngulo" in r or "grado" in r or "angle" in r:
        return "°"
    if "lados" in r or "segmentos" in r or "escala" in r or "factor" in r or "scale" in r:
        return ""                          # una cantidad, sin unidad
    return unidad_doc()


class _Unidad(QObject):
    """La unidad en gris, dentro de la casilla, justo antes de sus botones."""

    def __init__(self, campo: QLineEdit, texto: str) -> None:
        super().__init__(campo)
        self.campo = campo
        self.rotulo = QLabel(_tr(texto), campo)
        self.rotulo.setStyleSheet("color: #8a8a8a; background: transparent; border: none;")
        self.rotulo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.rotulo.adjustSize()
        campo.setTextMargins(0, 0, self.rotulo.width() + 3 if texto else 0, 0)
        campo.installEventFilter(self)
        self.rotulo.setVisible(bool(texto))
        QTimer.singleShot(0, self.colocar)

    def poner(self, texto: str) -> None:
        self.rotulo.setText(texto)
        self.rotulo.adjustSize()
        self.campo.setTextMargins(0, 0, self.rotulo.width() + 3 if texto else 0, 0)
        self.rotulo.setVisible(bool(texto))
        self.colocar()

    def colocar(self) -> None:
        botones = [b for b in self.campo.findChildren(QToolButton) if b.isVisible()]
        tope = min((b.x() for b in botones), default=self.campo.width() - 2)
        r = self.rotulo
        r.move(tope - r.width() - 2, (self.campo.height() - r.height()) // 2)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            QTimer.singleShot(0, self.colocar)
        return False


def botones_casilla(campo: QLineEdit, aplicar, borrar, unidad: str = "", al_micro=None) -> None:
    """Dentro de ``campo``, a la derecha: la unidad en gris, el micrófono, el
    retroceso, la V verde (``aplicar``) y el aspa (``borrar``). ``al_micro``:
    lo que hace el micrófono, si no es dictar sin más."""
    campo._unidad = _Unidad(campo, unidad)
    # Qt pone cada acción nueva más cerca del texto: se añaden de fuera adentro
    # para que queden micrófono · retroceso · V · aspa.
    for icono, ayuda, accion in ((icono_aspa(), "Borrar la casilla", borrar),
                                 (icono_check(), "Aplicar (Enter)", aplicar),
                                 (icono_retroceso(), "Borrar la última cifra",
                                  lambda _c=False: campo.backspace())):
        a = QAction(icono, _tr(ayuda), campo)
        a.setToolTip(_tr(ayuda))
        a.triggered.connect(accion)
        campo.addAction(a, _tr(QLineEdit.TrailingPosition))
    campo._accion_micro = con_microfono(campo, al_pulsar=al_micro)
    for b in campo.findChildren(QToolButton):
        b.setCursor(Qt.PointingHandCursor)


class _Renglon(QLineEdit):
    """Un renglón de medida: Enter/Tab/Esc los maneja la ventanita."""

    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        # Lo dictado llega en palabras («dos coma cinco»): al poco se ve en cifras.
        self._reloj = QTimer(self)
        self._reloj.setSingleShot(True)
        self._reloj.setInterval(600)
        self._reloj.timeout.connect(self.poner_en_cifras)
        self._componiendo = False             # Windows aún está escribiendo la frase
        self.textChanged.connect(self._quiza_dictado)

    def inputMethodEvent(self, ev) -> None:  # noqa: N802 — nombre de Qt
        self._componiendo = bool(ev.preeditString())
        super().inputMethodEvent(ev)
        if self._componiendo:
            self._reloj.stop()
        else:
            self._quiza_dictado(self.text())

    def _quiza_dictado(self, texto: str) -> None:
        # Más que una unidad, o los espacios que el dictado mete con el ruido.
        if (sum(c.isalpha() for c in texto) > 2 or texto[:1].isspace()) and not self._componiendo:
            self._reloj.start()

    def poner_en_cifras(self) -> None:
        if self._componiendo:
            return                            # no se le cambia el texto en mitad de una frase
        if self.text() and not self.text().strip():
            self.clear()
            return
        cifras = medida_dictada(self.text(), miles=self.ventana.dictando)
        if cifras and cifras != self.text():
            self.setText(cifras)

    def keyPressEvent(self, ev) -> None:  # noqa: N802 — nombre de Qt
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.ventana.enter(self)
            return
        if ev.key() == Qt.Key_Escape:
            self.ventana.esc()
            return
        if ev.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.ventana.saltar(self, -1 if ev.key() == Qt.Key_Backtab else 1)
            return
        self.setProperty("malo", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().keyPressEvent(ev)


class Medidas(QWidget):
    """La ventanita. ``abrir(titulo, campos, texto, aplicar)``: ``campos`` es
    una lista de etiquetas; ``aplicar(textos)`` recibe los textos de los
    renglones y devuelve True si los aceptó."""

    def __init__(self, ventana_principal, viewport, parsear) -> None:
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        super().__init__(ventana_principal, flags)
        # Se muestra sin quitarle el teclado al visor (ver ``abrir``).
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # Lo que la ventana mida de más que el marco, transparente (sin la
        # banda negra a la derecha).
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.vp = viewport
        self.parsear = parsear                  # texto → float, o None
        self.aplicadas = 0                      # medidas aplicadas (la siguiente, otra vez a dictar)
        self.al_aplicar = None
        self.dictado_auto = False               # lo abrió la opción, no el micrófono
        self._aplicar = None
        self.clave = None                       # (título, renglones) mostrados
        self._junto_a = None
        self._quieta = False                    # parada para llegar con el ratón
        self._ultimo_p = None
        self._t_mov = 0.0
        self.setStyleSheet(_ESTILO)
        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(0, 0, 0, 0)
        fuera.setSizeConstraint(QLayout.SetFixedSize)   # la ventana, del ancho del marco
        marco = QFrame(self)
        marco.setObjectName("marco")
        marco.setFixedWidth(ANCHO)
        fuera.addWidget(marco)
        lay = QVBoxLayout(marco)
        lay.setContentsMargins(4, 2, 4, 3)    # compacta: la letra, igual
        lay.setSpacing(2)
        cabeza = QHBoxLayout()
        self.titulo = QLabel("")
        self.titulo.setObjectName("titulo")
        self.titulo.setWordWrap(True)
        cabeza.addWidget(self.titulo, 1)
        self.boton_calc = QToolButton()
        self.boton_calc.setIcon(_icono_calculadora())
        self.boton_calc.setIconSize(QSize(18, 18))
        self.boton_calc.setToolTip(_tr("Calculadora"))
        self.boton_calc.setFocusPolicy(Qt.NoFocus)
        self.boton_calc.clicked.connect(self._alternar_calculadora)
        cabeza.addWidget(self.boton_calc)
        lay.addLayout(cabeza)
        self.rejilla = QGridLayout()
        self.rejilla.setHorizontalSpacing(4)
        self.rejilla.setVerticalSpacing(2)
        lay.addLayout(self.rejilla)
        self.renglones: list[_Renglon] = []
        self.etiquetas: list[QLabel] = []
        self.pista = QLabel(_tr(PISTA))
        self.pista.setToolTip(_tr("Medida o cuenta (120+30) · Enter aplica · Esc borra"))
        self.pista.setObjectName("pista")
        self.pista.setWordWrap(True)
        lay.addWidget(self.pista)
        self.calc = self._crear_calculadora()
        self.calc.hide()
        lay.addWidget(self.calc)
        self._activo: _Renglon | None = None

    # -- calculadora --
    def _crear_calculadora(self) -> QWidget:
        caja = QWidget()
        g = QGridLayout(caja)
        g.setContentsMargins(0, 2, 0, 0)
        g.setSpacing(2)
        self.pantalla = QLineEdit()
        self.pantalla.setAlignment(Qt.AlignRight)
        self.pantalla.returnPressed.connect(self._igual)
        botones_casilla(self.pantalla, lambda _c=False: self._igual(),
                        lambda _c=False: (self.pantalla.clear(), self.pantalla.setFocus()), unidad_doc())
        g.addWidget(self.pantalla, 0, 0, 1, 4)
        teclas = [("7", 1, 0), ("8", 1, 1), ("9", 1, 2), ("÷", 1, 3),
                  ("4", 2, 0), ("5", 2, 1), ("6", 2, 2), ("×", 2, 3),
                  ("1", 3, 0), ("2", 3, 1), ("3", 3, 2), ("−", 3, 3),
                  ("0", 4, 0), (",", 4, 1), ("C", 4, 2), ("+", 4, 3),
                  ("(", 5, 0), (")", 5, 1), ("←", 5, 2), ("=", 5, 3)]
        for texto, fila, col in teclas:
            b = QPushButton(_tr(texto))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _c=False, t=texto: self._tecla(t))
            g.addWidget(b, fila, col)
        # Última fila: Esc · Usar · Enter.
        for texto, nombre, accion, col, ancho, ayuda in (
                ("Esc", "esc", self._esc_calc, 0, 1,
                 "Cierra la calculadora sin usar el resultado"),
                ("Usar", "usar", self._usar, 1, 2,
                 "Copia el resultado a la medida (sin aplicarla)"),
                ("Enter", "enter", self._enter_calc, 3, 1,
                 "Copia el resultado a la medida y la aplica")):
            b = QPushButton(_tr(texto))
            b.setObjectName(nombre)
            b.setToolTip(_tr(ayuda))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(accion)
            g.addWidget(b, 6, col, 1, ancho)
        return caja

    def _colocar(self) -> None:
        """A la derecha del cursor, con la esquina de abajo a la altura de la
        punta del lápiz y sin pisar su cuerpo; si no cabe en la pantalla (p. ej.
        al abrir la calculadora), al otro lado. Nunca debajo de la barra de
        tareas."""
        p = getattr(self, "_junto_a", None) or QCursor.pos()
        pantalla = QGuiApplication.screenAt(p) or QGuiApplication.primaryScreen()
        zona = pantalla.availableGeometry()
        w, h = self.width(), self.height()
        x = p.x() + DERECHA_DEL_LAPIZ
        if x + w > zona.right():
            x = p.x() - DEBAJO_DEL_LAPIZ - w
        y = p.y() - h
        if y < zona.top():
            y = p.y() + DEBAJO_DEL_LAPIZ
        x = max(zona.left(), min(x, zona.right() - w))
        y = max(zona.top(), min(y, zona.bottom() - h))
        self.move(x, y)

    def _ajustar(self) -> None:
        """Al tamaño justo y junto al cursor. Qt rehace la disposición una
        vuelta después de ocultar o quitar algo (la calculadora, renglones):
        se repite entonces para que no quede grande y vacía."""
        self.adjustSize()
        self._colocar()
        QTimer.singleShot(0, self._reajustar)

    def _reajustar(self) -> None:
        if self.isVisible() and self.size() != self.sizeHint():
            self.adjustSize()
            self._colocar()

    def _alternar_calculadora(self) -> None:
        ver = not self.calc.isVisible()
        self.calc.setVisible(ver)
        if ver:
            fila = self._activo or (self.renglones[0] if self.renglones else None)
            self.pantalla.setText(fila.text() if fila is not None else "")
            self.pantalla.setFocus()
            self.pantalla.selectAll()
        elif self._activo is not None:
            self._activo.setFocus()
        self._ajustar()

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
        try:
            self.pantalla.setText(_formatear(calcular(self.pantalla.text())))
            return True
        except Exception:  # noqa: BLE001 — una expresión mal escrita
            self.pantalla.selectAll()
            return False

    def _usar(self) -> None:
        if not self._igual():
            return
        fila = self._activo or (self.renglones[0] if self.renglones else None)
        if fila is not None:
            fila.setText(self.pantalla.text())
            fila.setFocus()
        self.calc.hide()
        self._ajustar()

    def _enter_calc(self) -> None:
        """Usar + Enter: el resultado pasa a la medida y se aplica (o salta al
        renglón siguiente, como Enter en él)."""
        fila = self._activo or (self.renglones[0] if self.renglones else None)
        if fila is None or not self._igual():
            return
        fila.setText(self.pantalla.text())
        self.calc.hide()
        self._ajustar()
        self.enter(fila)

    def _esc_calc(self) -> None:
        """Cierra la calculadora; la medida queda como estaba."""
        self.calc.hide()
        if self._activo is not None:
            self._activo.setFocus()
        self._ajustar()

    # -- renglones --
    def abrir(self, titulo: str, campos: list, texto: str, aplicar,
              activar: bool = False) -> None:
        """Muestra la ventanita con un renglón por ``campos``. Sin
        ``activar`` no toma el teclado: lo tecleado en el visor le llega por
        ``recibir_tecla`` y las teclas de IngeTrazo (flechas, Ctrl…) siguen
        siendo del visor."""
        self._aplicar = aplicar
        self.clave = (titulo, tuple(campos))
        self.titulo.setText(_tr(titulo))
        for w in self.renglones + self.etiquetas:
            self.rejilla.removeWidget(w)
            w.hide()                        # que no asome hasta que se borre
            w.deleteLater()
        self.renglones, self.etiquetas = [], []
        for i, nombre in enumerate(campos):
            et = QLabel(_tr(nombre))
            r = _Renglon(self)
            r.setMinimumWidth(176)
            r.installEventFilter(self)
            botones_casilla(r, lambda _c=False, r=r: self.enter(r),
                            lambda _c=False, r=r: self._borrar(r), unidad_de(nombre),
                            al_micro=lambda _c=False, r=r: self._al_micro(r))
            self.rejilla.addWidget(et, i, 0)
            self.rejilla.addWidget(r, i, 1)
            self.etiquetas.append(et)
            self.renglones.append(r)
        self.calc.hide()
        self.pantalla._unidad.poner(unidad_doc())   # la del dibujo abierto
        self.adjustSize()
        self._junto_a = QCursor.pos()
        self._ultimo_p, self._t_mov, self._quieta = self._junto_a, time.monotonic(), False
        self._colocar()
        self.show()
        self.raise_()
        QTimer.singleShot(0, self._reajustar)     # sin hueco de la calculadora
        primero = self.renglones[0]
        primero.setText(texto)
        self._poner_activo(primero)
        if activar:
            self.activateWindow()
            primero.setFocus()

    def seguir(self) -> None:
        """Acompaña al cursor mientras se mueve. Si el ratón se para un
        momento (QUIETA_S), se queda quieta para poder llegar a ella con el
        ratón: mientras el cursor va hacia ella (zona entre el punto donde se
        paró y la ventanita) no se aparta; si se aleja, vuelve a seguirlo."""
        if not self.isVisible() or self.isActiveWindow():
            return
        p = QCursor.pos()
        ahora = time.monotonic()
        if self._quieta:
            if self._zona().contains(p):
                return
            self._quieta = False
        if p != self._ultimo_p:
            self._ultimo_p, self._t_mov = p, ahora
            self._junto_a = p
            self._colocar()
        elif ahora - self._t_mov >= QUIETA_S:
            self._quieta = True

    def _zona(self) -> QRect:
        """Rectángulo que abarca el punto donde se paró el ratón y la
        ventanita, con margen: el camino del cursor hacia ella."""
        a = self._junto_a or QCursor.pos()
        g = self.frameGeometry()
        return QRect(QPoint(min(a.x(), g.left()), min(a.y(), g.top())),
                     QPoint(max(a.x(), g.right()), max(a.y(), g.bottom()))
                     ).adjusted(-18, -18, 18, 18)

    def poner_actuales(self, valores) -> None:
        """La medida que se está dibujando, en gris en cada renglón vacío."""
        for r, v in zip(self.renglones, valores or ()):
            if r.placeholderText() != (v or ""):
                r.setPlaceholderText(_tr(v or ""))

    def hay_texto(self) -> bool:
        return any(r.text().strip() for r in self.renglones)

    def _poner_activo(self, renglon) -> None:
        self._activo = renglon
        for r in self.renglones:
            r.setProperty("activo", r is renglon)
            r.style().unpolish(r)
            r.style().polish(r)
        self._pintar_micro(vigia.oyendo and self.dictando)

    # -- el dictado --
    @property
    def dictando(self) -> bool:
        """El vigía está pendiente de una casilla de esta ventanita."""
        return vigia.activo and vigia.al_cambiar == self._pintar_micro

    def _pintar_micro(self, oyendo: bool) -> None:
        """Micrófono rojo en la casilla que está escuchando; abajo, cómo va."""
        for r in self.renglones:
            a = getattr(r, "_accion_micro", None)
            if a is not None:
                rojo = oyendo and r is self._activo
                a.setIcon(icono_microfono(ROJO) if rojo else icono_microfono())
                a.setToolTip(_tr("Escuchando" if rojo else "Dictar por voz"))
        if not self.dictando:
            texto = PISTA
        elif oyendo:
            texto = "Escuchando · V acepta · aspa o retroceso corrigen"
        else:
            texto = "Micrófono parado: púlsalo para seguir dictando"
        if self.pista.text() != _tr(texto):
            self.pista.setText(_tr(texto))

    def _foco_a_casilla(self, fila) -> None:
        self.activateWindow()
        self.raise_()
        self._poner_activo(fila)
        fila.setFocus(Qt.OtherFocusReason)
        fila.end(False)

    def _al_micro(self, fila) -> None:
        """El micrófono de una casilla: a escuchar en ella, pase lo que pase antes."""
        self._foco_a_casilla(fila)
        vigia.pedir(fila, seguir=True, al_cambiar=self._pintar_micro)

    def a_dictado(self, vaciar: bool = False) -> None:
        """El teclado a la casilla y el dictado de Windows escuchando.
        ``vaciar``: un punto nuevo, lo escrito para el anterior ya no vale."""
        if not self.isVisible() or not self.renglones:
            return
        if vaciar:
            for r in self.renglones:
                r.clear()
            self._poner_activo(self.renglones[0])
        fila = self._activo or self.renglones[0]
        self.dictado_auto = True
        self._foco_a_casilla(fila)
        vigia.pedir(fila, seguir=True, al_cambiar=self._pintar_micro)

    def terminar_dictado(self) -> None:
        """Se acabó: el dictado se cierra antes de que la casilla pierda el foco
        (después Win+H ya no lo cierra) y luego se cierra la ventanita."""
        if not self.dictando:
            self.cerrar()
            return
        self.dictado_auto = False
        cerrando = vigia.parar()
        self._pintar_micro(False)
        self.clave = None
        self._aplicar = None
        if cerrando:
            QTimer.singleShot(ESPERA_CIERRE_MS, self.cerrar)
        else:
            self.cerrar()

    def esc(self) -> None:
        """Esc en una casilla: se cierra y deja de escuchar."""
        self.terminar_dictado()

    def recibir_tecla(self, ev) -> bool:
        """Una tecla que llegó al visor con la ventanita abierta. Números,
        separadores y unidades van al renglón activo; Enter/Esc/Tab/«;» la
        manejan; el resto (flechas, Ctrl, atajos) sigue siendo del visor."""
        fila = self._activo or (self.renglones[0] if self.renglones else None)
        if fila is None:
            return False
        k, t = ev.key(), ev.text()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if not self.hay_texto():
                return False
            self.enter(fila)
            return True
        if k == Qt.Key_Escape:
            if not self.hay_texto():
                return False                 # Esc del visor: cancela la orden
            for r in self.renglones:
                r.clear()
            self._poner_activo(self.renglones[0])
            return True
        if k == Qt.Key_Backspace:
            if not fila.text():
                return False
            fila.backspace()
            return True
        if k in (Qt.Key_Tab, Qt.Key_Backtab) or t == ";":
            self.saltar(fila, -1 if k == Qt.Key_Backtab else 1)
            return True
        if ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            return False
        if self.dictando and t and t.isprintable():
            fila.insert(t)                   # lo oído no va al visor como atajos
            return True
        if t and (t.isdigit() or t in ",.-+*/()\"' "):
            if t == " " and not fila.text():
                return False                 # Espacio solo: Seleccionar
            fila.insert(t)
            self._limpiar_malo(fila)
            return True
        if t and t.lower() in "mcinft" and fila.text():
            fila.insert(t)                   # unidades tras un número: cm, mm…
            return True
        return False

    def _limpiar_malo(self, renglon) -> None:
        if renglon.property("malo"):
            renglon.setProperty("malo", False)
            renglon.style().unpolish(renglon)
            renglon.style().polish(renglon)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if ev.type() == ev.Type.FocusIn and obj in self.renglones:
            self._poner_activo(obj)
            if self.dictando:
                vigia.cambiar_campo(obj)
        return False

    def saltar(self, renglon, paso: int) -> None:
        i = self.renglones.index(renglon)
        destino = self.renglones[(i + paso) % len(self.renglones)]
        self._poner_activo(destino)
        if self.isActiveWindow():
            destino.setFocus()
            destino.selectAll()

    def enter(self, renglon) -> None:
        for r in self.renglones:
            r.poner_en_cifras()
        i = self.renglones.index(renglon)
        if renglon.text().strip() and self.parsear(renglon.text()) is None:
            self._marcar(renglon)
            return
        if i < len(self.renglones) - 1:
            self.saltar(renglon, 1)
            return
        textos = [r.text().strip() for r in self.renglones]
        for r in self.renglones:
            if r.text().strip() and self.parsear(r.text()) is None:
                self._marcar(r)
                return
        try:
            ok = self._aplicar(textos) if self._aplicar is not None else False
        except Exception:  # noqa: BLE001
            log.exception("no se pudo aplicar la medida")
            ok = False
        if ok:
            self.aplicadas += 1
            self.cerrar()
            if callable(self.al_aplicar):
                QTimer.singleShot(0, self.al_aplicar)   # la medida siguiente o el final
        else:
            self._marcar(renglon)

    def _borrar(self, renglon) -> None:
        """El aspa: vacía la casilla y la deja lista para escribir."""
        renglon.clear()
        self._limpiar_malo(renglon)
        self._poner_activo(renglon)
        if self.isActiveWindow():
            renglon.setFocus()

    def _marcar(self, renglon) -> None:
        renglon.setProperty("malo", True)
        renglon.style().unpolish(renglon)
        renglon.style().polish(renglon)
        self._poner_activo(renglon)
        if self.isActiveWindow():
            renglon.setFocus()
            renglon.selectAll()

    def cerrar(self) -> None:
        """Se oculta; la cadena la vuelve a abrir, vacía, para la medida
        siguiente (el próximo segmento, la altura…)."""
        self._aplicar = None
        self.clave = None
        self.hide()
        self.vp.window().activateWindow()
        self.vp.setFocus()

    def changeEvent(self, ev) -> None:  # noqa: N802
        # Si se estaba escribiendo en ella y se pincha fuera (en el modelo),
        # devuelve el teclado al visor y vuelve a seguir al cursor.
        if (ev.type() == ev.Type.ActivationChange and not self.isActiveWindow()
                and self.isVisible()):
            self.calc.hide()
            self._ajustar()
        super().changeEvent(ev)

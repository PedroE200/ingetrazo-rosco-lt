# SPDX-License-Identifier: GPL-3.0-or-later
"""Entrada por voz en las cajas de texto de Rosco LT.

- ``con_microfono(campo, ventana)``: pone un micrófono dentro del campo, a la
  derecha (QLineEdit: como acción; QPlainTextEdit / QTextEdit: un botoncito
  encima, con margen para que no tape el texto). Ayuda: «Dictar por voz».
- Al pulsarlo: el foco va al campo (al final de lo que haya) y se abre el
  dictado de Windows (Win+H), en el sitio que Windows decida.

(La ventanita de Win+H no se puede mover: Windows la dibuja dentro de una
ventana invisible del tamaño de la pantalla. Desde un programa de escritorio
el reconocimiento en línea no responde y el de escritorio entiende mal, así
que se usa el dictado de Windows tal cual; si se arrastra, Windows recuerda
dónde se dejó.)
"""
from __future__ import annotations

from ._idioma import _tr
import ctypes
import logging
import os
import re
import time
import unicodedata

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit, QToolButton

log = logging.getLogger("ingetrazo.plugins.rosco_lt.voz")

AYUDA = "Dictar por voz"


def icono_microfono(color: str = "#6b6b6b") -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(11.0, 3.0, 10.0, 17.0), 5.0, 5.0)
    p.setBrush(Qt.NoBrush)
    arco = QPainterPath()
    arco.moveTo(7.0, 14.0)
    arco.cubicTo(7.0, 27.0, 25.0, 27.0, 25.0, 14.0)
    p.drawPath(arco)
    p.drawLine(QPointF(16.0, 24.0), QPointF(16.0, 29.0))
    p.drawLine(QPointF(11.0, 29.0), QPointF(21.0, 29.0))
    p.end()
    return QIcon(pm)


# ---- Windows: Win+H ---------------------------------------------------------
_u32 = ctypes.windll.user32 if os.name == "nt" else None
VK_LWIN, VK_H, KEYUP = 0x5B, 0x48, 0x0002


def _win_h() -> None:
    if _u32 is None:
        return
    for vk, sube in ((VK_LWIN, 0), (VK_H, 0), (VK_H, KEYUP), (VK_LWIN, KEYUP)):
        _u32.keybd_event(vk, 0, sube, 0)


def dictar(campo, ventana=None) -> None:
    """Foco al campo (al final de lo que haya) y el dictado de Windows."""
    try:
        w = campo.window()
        w.activateWindow()
        w.raise_()
        campo.setFocus(Qt.OtherFocusReason)
        if isinstance(campo, QLineEdit):
            campo.end(False)
        else:
            c = campo.textCursor()
            c.movePosition(c.MoveOperation.End)
            campo.setTextCursor(c)
        vigia.pedir(campo, seguir=False)       # también si Windows paró el micrófono
    except Exception:  # noqa: BLE001 — sin dictado, el campo sigue funcionando
        log.exception("no se pudo abrir el dictado de Windows")


# ---- El dictado tras cada punto (Opciones ▸ Dictado de medidas) ---------------
_CLAVE_MICRO = (r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
                r"\ConsentStore\microphone\MicrosoftWindows.Client.CBS_cw5n1h2txyewy")


def escuchando() -> bool:
    """Si el dictado de Windows tiene el micrófono abierto: Windows lo apunta
    en el registro (sin hora de parada mientras escucha). Win+H abre y cierra,
    y hay que saberlo para no cerrarlo sin querer."""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CLAVE_MICRO) as k:
            return winreg.QueryValueEx(k, "LastUsedTimeStop")[0] == 0
    except OSError:
        return False


def _en_primer_plano() -> bool:
    """IngeTrazo es el programa de delante: si no, Win+H dictaría en otro."""
    if _u32 is None:
        return False
    try:
        pid = ctypes.c_ulong(0)
        _u32.GetWindowThreadProcessId(_u32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value == os.getpid()
    except OSError:
        return False


def _teclas_libres() -> bool:
    """Sin Ctrl, Mayús, Alt ni Windows pulsadas: con ellas, Win+H sería otra cosa."""
    return _u32 is not None and not any(_u32.GetAsyncKeyState(vk) & 0x8000
                                        for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


class Vigia(QObject):
    """Quien pulsa Win+H. Lo medido en Windows 11 (06-11-2026):

    - El micrófono se abre en menos de medio segundo.
    - Si el foco sale de la casilla, Windows lo para unos 100 ms después y no
      lo reanuda al volver. Win+H lo vuelve a abrir.
    - En silencio lo para solo a los 30 s.
    - Con el micrófono abierto y el foco en una casilla, Win+H lo cierra; sin
      casilla con foco no lo cierra.

    Por eso no basta con mirarlo una vez: con ``seguir`` se vigila mientras
    dure la medida. Solo hay un vigía, y así nunca se pulsa dos veces seguidas
    (la segunda cerraría lo que abrió la primera)."""

    INTERVALO_MS = 100
    TRAS_FOCO_S = 0.15                  # que el foco se asiente antes de pulsar
    ENTRE_PULSOS_S = 1.0                # lo que se le da al micrófono para abrirse
    MAX_PULSOS = 3                      # impar: si todo falla, no se queda a medias
    PERDIDA_FOCO_S = 0.8                # parado tan cerca de un cambio de foco: fue por eso
    SILENCIO_S = 28.0                   # parado tras esto: fue el silencio
    MAX_REANUDAR = 4                    # unos dos minutos sin hablar y deja de insistir

    def __init__(self) -> None:
        super().__init__()
        self.campo = None
        self.seguir = False
        self.al_cambiar = None
        self.activo = False
        self.oyendo = False
        self._estado = "quieto"         # arrancando · escucha · quieto
        self._ult_pulso = 0.0
        self._pulsos = 0
        self._desde = 0.0
        self._sin_foco = 0.0
        self._reanudadas = 0
        self._reloj = QTimer(self)
        self._reloj.setInterval(self.INTERVALO_MS)
        self._reloj.timeout.connect(self._mirar)

    def pedir(self, campo, seguir: bool = True, al_cambiar=None) -> None:
        """El dictado escuchando en ``campo`` (ya con el foco o a punto de tenerlo)."""
        self.campo, self.seguir, self.al_cambiar = campo, seguir, al_cambiar
        self.activo = True
        self._estado = "arrancando"
        self._pulsos = self._reanudadas = 0
        self._sin_foco = time.monotonic()
        self._reloj.start()
        self._avisar()

    def cambiar_campo(self, campo) -> None:
        """El foco pasa a otra casilla de la misma medida."""
        if self.activo:
            self.campo = campo
            self._sin_foco = time.monotonic()

    def _enfocado(self) -> bool:
        c = self.campo
        return (c.isVisible() and c.hasFocus() and c.window().isActiveWindow()
                and _en_primer_plano())

    def parar(self) -> bool:
        """Deja de vigilar. Cierra el dictado si puede (con el foco en la casilla);
        sin foco, Windows ya lo está parando. True si ha pulsado Win+H."""
        pulsado = False
        if self.activo:
            try:
                if escuchando() and self._enfocado() and _teclas_libres():
                    _win_h()
                    pulsado = True
            except RuntimeError:         # la casilla ya no existe
                pass
        self._soltar()
        return pulsado

    def _soltar(self) -> None:
        self._reloj.stop()
        self.activo = False
        self._estado = "quieto"
        self.campo = None
        self.oyendo = False
        self._avisar()
        self.al_cambiar = None

    def _avisar(self) -> None:
        if callable(self.al_cambiar):
            try:
                self.al_cambiar(self.oyendo)
            except RuntimeError:         # la ventanita ya no existe
                self.al_cambiar = None

    def _mirar(self) -> None:
        try:
            enfocado = self._enfocado()
        except (RuntimeError, AttributeError):   # la casilla se ha borrado
            self._soltar()
            return
        ahora = time.monotonic()
        mic = escuchando()
        oye = mic and enfocado
        if oye != self.oyendo:
            self.oyendo = oye
            self._avisar()
        if not enfocado:
            self._sin_foco = ahora
            return
        if mic:
            if self._estado != "escucha":
                self._estado, self._desde, self._pulsos = "escucha", ahora, 0
            if not self.seguir:
                self._reloj.stop()
                self.activo = False
                self._estado = "quieto"
            return
        if self._estado == "escucha":
            # Se ha parado. Por el foco o por el silencio se reanuda; si no,
            # lo ha parado el usuario (la ✕ o el micrófono de Windows).
            por_foco = ahora - self._sin_foco < self.PERDIDA_FOCO_S
            por_silencio = ahora - self._desde >= self.SILENCIO_S
            if por_silencio and not por_foco:
                self._reanudadas += 1
            if (por_foco or por_silencio) and self._reanudadas <= self.MAX_REANUDAR:
                self._estado, self._pulsos = "arrancando", 0
            else:
                self._estado = "quieto"
        if self._estado != "arrancando":
            return
        if (ahora - self._sin_foco < self.TRAS_FOCO_S
                or ahora - self._ult_pulso < self.ENTRE_PULSOS_S or not _teclas_libres()):
            return
        if self._pulsos >= self.MAX_PULSOS:
            log.warning("el dictado de Windows no abre el micrófono")
            self._estado = "quieto"
            if not self.seguir:
                self._soltar()
            return
        _win_h()
        self._ult_pulso = ahora
        self._pulsos += 1


vigia = Vigia()


# Lo que Windows escribe al dictar puede venir en palabras y con punto final.
_UNIDADES_VOZ = {"metro": "m", "metros": "m", "centimetro": "cm", "centimetros": "cm",
                 "milimetro": "mm", "milimetros": "mm", "pulgada": "in", "pulgadas": "in",
                 "pie": "ft", "pies": "ft", "m": "m", "cm": "cm", "mm": "mm", "grado": "",
                 "grados": ""}
_NUMEROS_VOZ = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
                "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
                "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
                "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
                "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28,
                "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
                "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
                "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
                "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
                "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700,
                "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900}
_DECIMAL_VOZ = ("coma", "punto", "con")


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _valor_palabras(palabras: list) -> str | None:
    """«mil quinientos veinte» → «1520»; «120» → «120». None si no se entiende."""
    if not palabras:
        return None
    if len(palabras) == 1 and re.fullmatch(r"\d+", palabras[0]):
        return palabras[0]
    total, parte = 0, 0
    for p in palabras:
        if p == "y":
            continue
        if p == "mil":
            total += (parte or 1) * 1000
            parte = 0
        elif p in _NUMEROS_VOZ:
            parte += _NUMEROS_VOZ[p]
        elif re.fullmatch(r"\d+", p):
            parte += int(p)
        else:
            return None
    return str(total + parte)


def _decimales_palabras(palabras: list) -> str | None:
    """Tras la coma: «cinco» → 5, «cero cinco» → 05, «veinticinco» → 25."""
    ceros = ""
    while palabras and palabras[0] in ("cero", "0"):
        ceros += "0"
        palabras = palabras[1:]
    if not palabras:
        return ceros or None
    resto = _valor_palabras(palabras)
    return None if resto is None else ceros + resto


def medida_dictada(texto: str, miles: bool = False) -> str | None:
    """La medida en cifras («dos coma cinco metros» → «2,5m»; «2,5.» → «2,5»),
    o None si no es una medida dicha y hay que dejarla como está. ``miles``:
    está dictado, así que «1.500» es mil quinientos (tecleado serían decimales)."""
    limpio = _sin_acentos((texto or "").strip().lower()).rstrip(".;:!?¡¿ ").lstrip("¡¿ ")
    if not limpio:
        return None
    if miles:
        limpio = re.sub(r"\b(\d{1,3})((?:\.\d{3})+)\b", lambda m: m[1] + m[2].replace(".", ""), limpio)
    if re.fullmatch(r"[\d.,\s+\-*/()]+(mm|cm|m|in|ft|\"|')?", limpio):
        return re.sub(r"\s+(?=(mm|cm|m|in|ft)$)", "", limpio)
    # «2,5 metros» o «dos coma cinco metros»: separa también la cifra de la coma
    # y de la unidad (Windows va escribiendo a trozos: «2m» y luego «cincuenta»).
    palabras = re.sub(r"(\d)(mm|cm|m|in|ft)\b", r"\1 \2", limpio)
    palabras = re.sub(r"(\d)[,.](\d)", r"\1 coma \2", palabras).replace(",", " ").split()
    unidad, tras_unidad = "", []
    for i, p in enumerate(palabras):
        if p in _UNIDADES_VOZ:
            unidad, tras_unidad, palabras = _UNIDADES_VOZ[p], palabras[i + 1:], palabras[:i]
            break
    if tras_unidad and tras_unidad[0] == "con":          # «dos metros con cincuenta»
        tras_unidad = tras_unidad[1:]
    corte = next((i for i, p in enumerate(palabras) if p in _DECIMAL_VOZ), None)
    if corte is None:
        entero, decimales = palabras, tras_unidad            # «dos metros cincuenta»
    else:
        entero, decimales = palabras[:corte], palabras[corte + 1:]
    if len(entero) > 2 and entero[-2:] == ["y", "medio"] and not decimales:
        entero, decimales = entero[:-2], ["cinco"]            # «dos y medio»
    n = _valor_palabras(entero)
    if n is None:
        return None
    if decimales:
        d = _decimales_palabras(decimales)
        if d is None:
            return None
        n = f"{n},{d}"
    return n + unidad


def con_microfono(campo, ventana=None, al_pulsar=None):
    """Pone el micrófono dentro de ``campo`` (a la derecha). ``al_pulsar``: en
    vez de dictar sin más. En una línea devuelve su acción (para cambiarle el color)."""
    icono = icono_microfono()
    if isinstance(campo, QLineEdit):
        accion = QAction(icono, _tr(AYUDA), campo)
        accion.setToolTip(_tr(AYUDA))
        accion.triggered.connect(al_pulsar if callable(al_pulsar) else lambda: dictar(campo, ventana))
        campo.addAction(accion, _tr(QLineEdit.TrailingPosition))
        return accion
    # Cajas de varias líneas: un botoncito arriba a la derecha y margen para él.
    boton = QToolButton(campo)
    boton.setIcon(icono)
    boton.setIconSize(QSize(14, 14))
    boton.setToolTip(_tr(AYUDA))
    boton.setCursor(Qt.PointingHandCursor)
    boton.setFocusPolicy(Qt.NoFocus)
    boton.setStyleSheet("QToolButton { border: none; background: transparent; }"
                        "QToolButton:hover { background: #fadede; border-radius: 3px; }")
    boton.setFixedSize(QSize(18, 18))
    boton.clicked.connect(lambda: dictar(campo, ventana))
    campo.setViewportMargins(0, 0, 20, 0)

    class _Pegado(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802
            if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                boton.move(campo.width() - boton.width() - 3, 3)
            return False
    pegado = _Pegado(campo)
    campo.installEventFilter(pegado)
    campo._microfono = (boton, pegado)       # que no se los lleve el recolector
    boton.move(campo.width() - boton.width() - 3, 3)

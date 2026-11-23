# SPDX-License-Identifier: GPL-3.0-or-later
"""Control de tiempo: cuánto llevas dibujando y cuánto lleva abierto el
archivo, y una alarma analógica para limitar la sesión de trabajo.

- Tiempo dibujando: solo cuenta mientras hay actividad en IngeTrazo (ratón o
  teclado); tras 2 minutos sin tocar nada deja de contar. Lo explica el
  globo del botoncito «i».
- Tiempo con el archivo abierto: desde que se abrió (o se creó) el documento.
  Los dos vuelven a cero al abrir o crear otro documento.
- Alarma: una esfera de 60 minutos; se arrastra la aguja (y se suman horas
  con «+1 h»), «Iniciar» la pone en marcha y el sector rojo va menguando.
  Al llegar a cero suena el sonido elegido y sale el aviso, centrado sobre
  IngeTrazo, con el recordatorio escrito.
- El panel se despliega al lado de la diana (``junto_a``), sin salirse de la
  zona de dibujo, y se cierra al pinchar fuera; se arrastra por cualquier
  hueco libre. Con la chincheta queda clavado:
  siempre a la vista, por encima, y se recuerda dónde estaba.
- Cada parte (tiempos, alarma, recordatorio, sonido) va en su recuadro.
"""
from __future__ import annotations

from ._idioma import _tr
import logging
import math
import os
import time

from PySide6.QtCore import (
    QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSettings, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ._ajustes import registro

log = registro("anillo")
ROJO = QColor(214, 34, 34)
INACTIVO_S = 120.0                      # sin actividad este tiempo: no cuenta
POSPONER_S = 300.0                      # «Posponer 5 min» del aviso

AYUDA_DIBUJANDO = (
    "<b style='color:#d62222'>¿Qué cuenta «Tiempo dibujando»?</b><br>"
    "Solo el rato que <b>usas IngeTrazo</b> (ratón o teclado). Si pasas "
    "<b>2 min sin tocar nada</b> o cambias a otro programa, se para. Vuelve a "
    "cero al abrir o crear otro archivo.")

# Colores fijos: con el tema oscuro de IngeTrazo el texto saldría blanco
# sobre el fondo blanco de las ventanas.
_ESTILO_BOTONES = (
    "QPushButton { background: #f4f3f0; color: #111; border: 1px solid #bdbab3; "
    "border-radius: 4px; padding: 2px 8px; }"
    "QPushButton:hover { background: #fadede; }"
    "QPushButton#prim { background: #d62222; color: #fff; border-color: #b01b1b; }"
    "QPushButton#prim:hover { background: #e23a3a; }")


def _icono_chincheta(clavada: bool) -> QIcon:
    """Una chincheta: inclinada si está suelta, vertical y roja si está
    clavada (panel anclado)."""
    pm = QPixmap(36, 36)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(18, 18)
    if not clavada:
        p.rotate(40.0)
    tinta = ROJO if clavada else QColor(17, 17, 17)
    p.setPen(QPen(QColor(17, 17, 17), 1.6))
    p.setBrush(QBrush(tinta))
    p.drawRoundedRect(QRectF(-6, -14, 12, 5), 1.5, 1.5)          # cabeza
    p.drawPolygon(QPolygonF([QPointF(-4, -9), QPointF(4, -9), QPointF(6, 2), QPointF(-6, 2)]))
    p.setPen(QPen(QColor(17, 17, 17), 2.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(0, 2), QPointF(0, 15))                      # punta
    p.end()
    return QIcon(pm)


def _hms(segundos: float) -> str:
    s = int(max(0, segundos))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _duracion(minutos: int) -> str:
    h, m = divmod(int(minutos), 60)
    return _tr("{0} h {1:02d} min", h, m) if h else _tr("{0} min", m)


def junto_a(centro: QPoint, radio: float, tam: QSize, zona: QRect) -> QPoint:
    """Dónde poner una ventana de tamaño ``tam`` al lado de la diana (centro
    y radio, en coordenadas de pantalla): a la derecha y a media altura; si
    no cabe, a la izquierda. Siempre dentro de ``zona`` (la de dibujo)."""
    w, h = tam.width(), tam.height()
    x = round(centro.x() + radio)
    if x + w > zona.right() and centro.x() - radio - w >= zona.left():
        x = round(centro.x() - radio - w)
    y = centro.y() - h // 2
    x = max(zona.left(), min(x, zona.right() - w + 1))
    y = max(zona.top(), min(y, zona.bottom() - h + 1))
    return QPoint(x, y)


# ---- El reloj (cuenta aunque el panel esté cerrado) ----------------------------

class Cronometro(QObject):
    def __init__(self, app) -> None:
        super().__init__(app.window)
        self.app = app
        self.dibujando = 0.0
        self.abierto_desde = time.monotonic()
        self._ultima_actividad = time.monotonic()
        self._doc = self._clave_doc()
        self.alarma_fin: float | None = None      # monotonic en que suena
        self.alarma_total = 0.0
        self.avisos = []                          # funciones a llamar al sonar
        self._tic = QTimer(self)
        self._tic.setInterval(1000)
        self._tic.timeout.connect(self._latido)
        self._tic.start()
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.installEventFilter(self)

    def _clave_doc(self):
        win = self.app.window
        return (id(self.app.viewport.scene), str(getattr(win, "_current_path", None)))

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        if ev.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                         QEvent.Type.KeyPress, QEvent.Type.Wheel):
            self._ultima_actividad = time.monotonic()
        return False

    def _latido(self) -> None:
        ahora = time.monotonic()
        doc = self._clave_doc()
        if doc != self._doc:                   # otro documento: de cero
            self._doc = doc
            self.dibujando = 0.0
            self.abierto_desde = ahora
        activa = QApplication.applicationState() == Qt.ApplicationActive
        if activa and ahora - self._ultima_actividad < INACTIVO_S:
            self.dibujando += 1.0
        if self.alarma_fin is not None and ahora >= self.alarma_fin:
            self.alarma_fin = None
            self._sonar()

    @property
    def abierto(self) -> float:
        return time.monotonic() - self.abierto_desde

    def restante(self) -> float | None:
        if self.alarma_fin is None:
            return None
        return max(0.0, self.alarma_fin - time.monotonic())

    def iniciar_alarma(self, segundos: float) -> None:
        if segundos <= 0:
            return
        self.alarma_total = segundos
        self.alarma_fin = time.monotonic() + segundos

    def parar_alarma(self) -> None:
        self.alarma_fin = None

    def _sonar(self) -> None:
        if not self.avisos:                    # sin panel: al menos un pitido
            QApplication.beep()
        self.app.viewport.flash_status(_tr("Control de tiempo: ¡se acabó el tiempo de trabajo!"), 15000)
        for aviso in list(self.avisos):
            try:
                aviso()
            except Exception:  # noqa: BLE001
                log.exception("fallo al avisar de la alarma")


# ---- El sonido de la alarma ------------------------------------------------------

# IngeTrazo no trae el módulo de sonido de Qt: se usa el del sistema (winmm),
# PlaySound para los .wav y MCI para los .mp3.
_SND_ASYNC, _SND_NODEFAULT, _SND_LOOP, _SND_FILENAME = 0x1, 0x2, 0x8, 0x20000
_ALIAS = "diana_alarma"


def _winmm():
    import ctypes
    return ctypes.windll.winmm


def sonidos_sistema() -> list[tuple[str, str]]:
    """(nombre, ruta) de los sonidos del sistema: alarmas y timbres primero."""
    carpeta = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Media")  # nombre técnico
    try:
        nombres = [n for n in os.listdir(carpeta) if n.lower().endswith(".wav")]
    except OSError:
        return []

    def orden(n):
        b = n.lower()
        return (0 if b.startswith("alarm") else 1 if b.startswith("ring") else
                3 if b.startswith("windows") or b.startswith("speech") else 2, b)
    return [(os.path.splitext(n)[0], os.path.join(carpeta, n)) for n in sorted(nombres, key=orden)]


class Sonido(QObject):
    """Toca un .wav o .mp3; «» o un archivo que no está: el pitido del sistema."""

    def __init__(self, padre) -> None:
        super().__init__(padre)
        self._mci = False
        self._pitidos = QTimer(self)
        self._pitidos.setInterval(1200)
        self._pitidos.timeout.connect(QApplication.beep)

    def tocar(self, ruta: str, repetir: bool = False) -> None:
        self.parar()
        if not ruta or not os.path.isfile(ruta):
            QApplication.beep()
            if repetir:
                self._pitidos.start()
            return
        try:
            mm = _winmm()
            if ruta.lower().endswith(".wav"):
                mm.PlaySoundW(ruta, None, _SND_FILENAME | _SND_ASYNC | _SND_NODEFAULT
                              | (_SND_LOOP if repetir else 0))
                return
            if mm.mciSendStringW(f'open "{ruta}" type mpegvideo alias {_ALIAS}', None, 0, None):
                raise OSError(f"no se pudo abrir {ruta}")
            self._mci = True
            if not (repetir and mm.mciSendStringW(f"play {_ALIAS} repeat", None, 0, None) == 0):
                mm.mciSendStringW(f"play {_ALIAS}", None, 0, None)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo tocar %s", ruta)
            QApplication.beep()

    def parar(self) -> None:
        self._pitidos.stop()
        try:
            mm = _winmm()
            mm.PlaySoundW(None, None, 0)
            if self._mci:
                mm.mciSendStringW(f"close {_ALIAS}", None, 0, None)
        except Exception:  # noqa: BLE001
            pass
        self._mci = False


# ---- Ventanas que se arrastran (sin barra de título) ---------------------------

class _Arrastrable:
    """Se arrastra pinchando en cualquier hueco libre (los botones, la esfera
    y las cajas de texto se quedan su clic)."""
    _agarre = None

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._agarre = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._agarre is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._agarre)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._agarre is not None:
            self._agarre = None
            self.movido()
        super().mouseReleaseEvent(ev)

    def movido(self) -> None:
        pass


# ---- La esfera de la alarma ------------------------------------------------------

class Esfera(QWidget):
    """Esfera de 60 minutos. Se arrastra la aguja para elegir los minutos;
    con la alarma en marcha, un sector rojo muestra lo que queda."""

    def __init__(self, panel) -> None:
        super().__init__()
        self.panel = panel
        self.minutos = 25
        self.setFixedSize(104, 104)
        self.setCursor(Qt.PointingHandCursor)

    def _centro_radio(self):
        lado = min(self.width(), self.height()) - 12
        return QPointF(self.width() / 2.0, self.height() / 2.0), lado / 2.0

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, r = self._centro_radio()
        p.setPen(QPen(QColor(44, 44, 42), 2.0))
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(c, r, r)
        crono = self.panel.crono
        restante = crono.restante()
        if restante is not None:
            minutos = (restante / 60.0) % 60.0 if restante < 3600 else 59.999
        else:
            minutos = float(self.minutos % 60 or (60 if self.minutos else 0))
        if minutos > 0:
            caja = QRectF(c.x() - r + 4, c.y() - r + 4, 2 * r - 8, 2 * r - 8)
            p.setPen(Qt.NoPen)
            rojo = QColor(ROJO)
            if restante is None:
                rojo.setAlpha(120)
            p.setBrush(QBrush(rojo))
            p.drawPie(caja, 90 * 16, int(-minutos / 60.0 * 360.0 * 16))
        p.setPen(QPen(QColor(44, 44, 42), 1.6))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        for m in range(0, 60, 5):
            a = math.radians(90.0 - m * 6.0)
            largo = 8.0 if m % 15 == 0 else 4.0
            p.drawLine(QPointF(c.x() + (r - largo) * math.cos(a), c.y() - (r - largo) * math.sin(a)),
                       QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a)))
            if m % 15 == 0:
                t = QPointF(c.x() + (r - 17) * math.cos(a), c.y() - (r - 17) * math.sin(a))
                p.drawText(QRectF(t.x() - 10, t.y() - 7, 20, 14), Qt.AlignCenter, _tr(str(m)))
        p.setBrush(QBrush(QColor(44, 44, 42)))
        p.drawEllipse(c, 4.0, 4.0)
        p.end()

    def _minutos_en(self, pos) -> int:
        c, _r = self._centro_radio()
        ang = math.degrees(math.atan2(c.y() - pos.y(), pos.x() - c.x()))
        m = int(round(((90.0 - ang) % 360.0) / 6.0)) % 60
        return m or 60

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self._elegir(ev.position())

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if ev.buttons() & Qt.LeftButton:
            self._elegir(ev.position())

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        ev.accept()                              # que no lo tome por arrastre

    def _elegir(self, pos) -> None:
        if self.panel.crono.restante() is not None:
            return                               # en marcha: no se cambia
        horas = self.minutos // 60 if self.minutos % 60 else max(0, self.minutos // 60 - 1)
        self.minutos = horas * 60 + self._minutos_en(pos)
        self.panel.refrescar()


# ---- El globo de ayuda («i») ---------------------------------------------------

class BotonInfo(QToolButton):
    """Botoncito rojo «i»: al pasar el ratón (o al pincharlo) sale un globo
    con la explicación; al salir se va."""

    def __init__(self, texto: str) -> None:
        super().__init__()
        self.setText("i")
        self.setFixedSize(QSize(16, 16))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QToolButton { background: #d62222; color: #fff; border: none; "
                           "border-radius: 8px; font: bold 9pt 'Georgia'; padding: 0; }")
        self.globo = QLabel(_tr(texto), None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.globo.setTextFormat(Qt.RichText)
        self.globo.setWordWrap(True)
        self.globo.setFixedWidth(240)
        self.globo.setStyleSheet("QLabel { background: #fffdf5; color: #333; font-size: 9pt; "
                                 "border: 1.2px solid #d62222; border-radius: 6px; padding: 7px 9px; }")
        self.clicked.connect(lambda: self._ver(True))

    def _ver(self, si: bool) -> None:
        if si:
            self.globo.adjustSize()
            self.globo.move(self.mapToGlobal(QPoint(-6, self.height() + 5)))
            self.globo.show()
            self.globo.raise_()
        else:
            self.globo.hide()

    def enterEvent(self, ev) -> None:  # noqa: N802
        self._ver(True)
        super().enterEvent(ev)

    def leaveEvent(self, ev) -> None:  # noqa: N802
        self._ver(False)
        super().leaveEvent(ev)

    def hideEvent(self, ev) -> None:  # noqa: N802
        self.globo.hide()
        super().hideEvent(ev)


# ---- El panel ------------------------------------------------------------------

class PanelTiempo(_Arrastrable, QFrame):
    def __init__(self, app, crono: Cronometro, alcerrar=None) -> None:
        super().__init__(app.window, Qt.Popup)
        self.app = app
        self.crono = crono
        self.anclado = False
        self.alcerrar = alcerrar
        self.aviso = None
        self.sonido = Sonido(self)
        self._cargando = True
        self.setObjectName("rosco_tiempo")
        self.setStyleSheet(
            "QFrame#rosco_tiempo { background: #ffffff; "
            "border: 1.5px solid #d62222; border-radius: 8px; }"
            "QFrame#rosco_tiempo QLabel, QFrame#rosco_tiempo QCheckBox "
            "{ color: #111111; background: transparent; }"
            # Los recercados: borde rosado y el título en rojo.
            "QFrame#rosco_tiempo QGroupBox { border: 1.2px solid #e6a9a9; border-radius: 7px; "
            "margin-top: 8px; padding: 7px 4px 3px 4px; color: #d62222; font-weight: bold; }"
            "QFrame#rosco_tiempo QGroupBox::title { subcontrol-origin: margin; left: 8px; "
            "padding: 0 3px; }"
            "QFrame#rosco_tiempo QGroupBox QWidget { font-weight: normal; }"
            # Con dos # para ganar a las reglas de arriba.
            "QFrame#rosco_tiempo QLabel#cifra { font-size: 15pt; font-weight: bold; color: #111; }"
            "QFrame#rosco_tiempo QLabel#rotulo { color: #5f5e5a; }"
            "QPlainTextEdit, QComboBox { background: #fff; color: #111; border: 1px solid #cfccc5; "
            "border-radius: 4px; padding: 2px 5px; }"
            "QComboBox QAbstractItemView { background: #fff; color: #111; "
            "selection-background-color: #fadede; selection-color: #111; }"
            + _ESTILO_BOTONES)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(3)
        # Sin barra de título: el asa, el nombre, la chincheta y cerrar.
        cabeza = QHBoxLayout()
        asa = QLabel("⠿⠿")
        asa.setStyleSheet("color: #b9b6ae;")
        asa.setToolTip(_tr("Arrastra para moverlo"))
        asa.setCursor(Qt.SizeAllCursor)
        cabeza.addWidget(asa)
        titulo = QLabel(_tr("Control de tiempo"))
        titulo.setCursor(Qt.SizeAllCursor)
        f = titulo.font()
        f.setBold(True)
        titulo.setFont(f)
        cabeza.addWidget(titulo, 1)
        self.chincheta = self._boton_icono(_icono_chincheta(False), "Clavar aquí: siempre a la "
                                           "vista, encima de todo, y vuelve a salir en este sitio")
        self.chincheta.setCheckable(True)
        self.chincheta.toggled.connect(self._anclar)
        cabeza.addWidget(self.chincheta)
        cerrar = self._boton_icono(None, "Cerrar")
        cerrar.setText("✕")
        cerrar.clicked.connect(self.hide)
        cabeza.addWidget(cerrar)
        lay.addLayout(cabeza)

        caja, sub = self._recuadro(lay, "Tiempos")
        self.dibujando = self._fila(sub, "Tiempo dibujando", BotonInfo(AYUDA_DIBUJANDO))
        self.abierto = self._fila(sub, "Archivo abierto")

        # La esfera a la izquierda; lo que queda y los botones, a su lado.
        caja, sub = self._recuadro(lay, "Alarma de trabajo")
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.esfera = Esfera(self)
        fila.addWidget(self.esfera)
        lado = QVBoxLayout()
        lado.setSpacing(4)
        self.lectura = QLabel("")
        self.lectura.setObjectName("rotulo")
        lado.addWidget(self.lectura)
        lado.addStretch(1)
        mas = QPushButton("+1 h")
        mas.clicked.connect(self._mas_hora)
        lado.addWidget(mas)
        self.boton = QPushButton(_tr("Iniciar"))
        self.boton.setObjectName("prim")
        self.boton.clicked.connect(self._alternar)
        lado.addWidget(self.boton)
        fila.addLayout(lado, 1)
        sub.addLayout(fila)

        caja, sub = self._recuadro(lay, "Recordatorio")
        self.recordatorio = QPlainTextEdit()
        self.recordatorio.setPlaceholderText(_tr("Escribe lo que quieres que te recuerde…"))
        self.recordatorio.setFixedHeight(40)
        from ._voz import con_microfono       # aquí: _voz no depende de esta pieza
        con_microfono(self.recordatorio)
        sub.addWidget(self.recordatorio)

        caja, sub = self._recuadro(lay, "Sonido de la alarma")
        fila = QHBoxLayout()
        self.lista = QComboBox()
        self.lista.addItem(_tr("Pitido del sistema"), "")
        for nombre, ruta in sonidos_sistema():
            self.lista.addItem(nombre, ruta)
        fila.addWidget(self.lista, 1)
        probar = QPushButton("▶")
        probar.setToolTip(_tr("Probar el sonido"))
        probar.setFixedWidth(28)
        probar.clicked.connect(lambda: self.sonido.tocar(self.lista.currentData() or ""))
        fila.addWidget(probar)
        elegir = QPushButton("…")
        elegir.setFixedWidth(28)
        elegir.setToolTip(_tr("Elegir un sonido tuyo (.wav o .mp3)"))
        elegir.clicked.connect(self._elegir_sonido)
        fila.addWidget(elegir)
        sub.addLayout(fila)
        self.repetir = QCheckBox(_tr("Repetir hasta cerrar el aviso"))
        sub.addWidget(self.repetir)

        self.setFixedWidth(236)
        self._reloj = QTimer(self)
        self._reloj.setInterval(500)
        self._reloj.timeout.connect(self.refrescar)
        crono.avisos.append(self._al_sonar)
        self._cargar()
        self.recordatorio.textChanged.connect(self._guardar)
        self.lista.currentIndexChanged.connect(self._al_cambiar_sonido)
        self.repetir.toggled.connect(self._guardar)
        self.adjustSize()
        self.refrescar()

    @staticmethod
    def _recuadro(lay, titulo):
        caja = QGroupBox(_tr(titulo))
        sub = QVBoxLayout(caja)
        sub.setContentsMargins(4, 4, 4, 2)
        sub.setSpacing(3)
        lay.addWidget(caja)
        return caja, sub

    @staticmethod
    def _boton_icono(icono, consejo) -> QToolButton:
        b = QToolButton()
        b.setAutoRaise(True)
        b.setToolTip(_tr(consejo))
        b.setFixedSize(QSize(24, 24))
        b.setStyleSheet("QToolButton { color: #111; border: none; border-radius: 4px; }"
                        "QToolButton:hover { background: #fadede; }"
                        "QToolButton:checked { background: #f5b9b9; }")
        if icono is not None:
            b.setIcon(icono)
            b.setIconSize(QSize(18, 18))
        return b

    @staticmethod
    def _fila(lay, texto, info=None) -> QLabel:
        fila = QHBoxLayout()
        fila.setSpacing(4)
        rot = QLabel(_tr(texto))
        rot.setObjectName("rotulo")
        fila.addWidget(rot)
        if info is not None:
            fila.addWidget(info)
        fila.addStretch(1)
        cifra = QLabel("0:00:00")
        cifra.setObjectName("cifra")
        fila.addWidget(cifra)
        lay.addLayout(fila)
        return cifra

    # -- lo que se recuerda --
    def _cargar(self) -> None:
        s = ajustes()
        self.recordatorio.setPlainText(str(s.value("recordatorio", "") or ""))
        ruta = s.value("sonido", None)
        if ruta is None:                         # la primera vez: Alarm01
            i = self.lista.findText("Alarm01")
        else:
            ruta = str(ruta or "")
            if ruta and self.lista.findData(ruta) < 0 and os.path.isfile(ruta):
                self._poner_propio(ruta)
            i = self.lista.findData(ruta)
        self.lista.setCurrentIndex(i if i >= 0 else 0)
        self.repetir.setChecked(str(s.value("repetir", "true")).lower() == "true")
        self._pos_guardada = s.value("pos", None)
        self._cargando = False
        if str(s.value("anclado", "false")).lower() == "true":
            self._anclar_al_mostrar = True

    def _guardar(self, *_args) -> None:
        if self._cargando:
            return
        s = ajustes()
        s.setValue("recordatorio", self.recordatorio.toPlainText())
        s.setValue("sonido", self.lista.currentData() or "")
        s.setValue("repetir", "true" if self.repetir.isChecked() else "false")
        s.setValue("anclado", "true" if self.anclado else "false")
        if self.anclado:
            s.setValue("pos", self.pos())

    def movido(self) -> None:
        if self.anclado:
            self._guardar()

    # -- el sonido --
    def _poner_propio(self, ruta: str) -> int:
        nombre = os.path.splitext(os.path.basename(ruta))[0] + _tr(" (tuyo)")
        self.lista.insertItem(1, nombre, ruta)
        return 1

    def _al_cambiar_sonido(self, _i) -> None:
        self.sonido.parar()
        self._guardar()

    def _elegir_sonido(self) -> None:
        # Un desplegable se cierra al abrir otra ventana: se reabre después.
        pos, volver = self.pos(), not self.anclado
        if volver:
            self.hide()
        ruta, _f = QFileDialog.getOpenFileName(self.app.window, _tr("Elegir el sonido de la alarma"),
                                               os.path.expanduser("~"),
                                               _tr("Sonidos (*.wav *.mp3);;Todos los archivos (*)"))
        if ruta:
            ruta = os.path.normpath(ruta)
            i = self.lista.findData(ruta)
            self.lista.setCurrentIndex(i if i >= 0 else self._poner_propio(ruta))
        if volver:
            self.mostrar(pos)

    # -- mostrar, anclar --
    def mostrar(self, global_pos: QPoint) -> None:
        if getattr(self, "_anclar_al_mostrar", False):
            self._anclar_al_mostrar = False
            guardada = self._pos_guardada
            if isinstance(guardada, QPoint) and QGuiApplication.screenAt(guardada) is not None:
                global_pos = guardada
            self.move(global_pos)
            self.chincheta.setChecked(True)      # lo muestra ya clavado
            return
        if not self.anclado:
            self.move(global_pos)
        self.show()
        self.raise_()
        self._reloj.start()
        self.refrescar()

    def showEvent(self, ev) -> None:  # noqa: N802
        # También al anclar: cambiar las banderas de la ventana la oculta y
        # la vuelve a mostrar, y el reloj debe seguir.
        super().showEvent(ev)
        self._reloj.start()
        self.refrescar()

    def hideEvent(self, ev) -> None:  # noqa: N802
        super().hideEvent(ev)
        self._reloj.stop()
        # El botón del reloj es un interruptor: el clic en él que cierra el
        # desplegable no debe volver a abrirlo (ver ``recien_cerrado``).
        self._cerrado_en = time.monotonic()
        if callable(self.alcerrar) and not self.anclado:
            self.alcerrar()

    def recien_cerrado(self) -> bool:
        return time.monotonic() - getattr(self, "_cerrado_en", 0.0) < 0.5

    def _anclar(self, si: bool) -> None:
        """Anclado: ventana de herramientas por encima, movible y que no se
        cierra al pinchar fuera. Sin anclar: desplegable."""
        pos = self.pos()
        self.anclado = si
        visible = self.isVisible()
        flags = ((Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) if si
                 else Qt.Popup)
        self.setWindowFlags(flags)
        self.chincheta.setIcon(_icono_chincheta(si))
        self.move(pos)
        if visible or si:
            self.show()
        self.raise_()
        self._guardar()

    # -- la alarma --
    def _mas_hora(self) -> None:
        if self.crono.restante() is None:
            self.esfera.minutos += 60
            self.refrescar()

    def _alternar(self) -> None:
        self._cumplido_hasta = 0.0
        if self.crono.restante() is not None:
            self.crono.parar_alarma()
        else:
            self.crono.iniciar_alarma(self.esfera.minutos * 60.0)
        self.refrescar()

    def posponer(self) -> None:
        self.sonido.parar()
        self._cumplido_hasta = 0.0
        self.crono.iniciar_alarma(POSPONER_S)
        self.refrescar()

    def _al_sonar(self) -> None:
        self._cumplido_hasta = time.monotonic() + 60.0      # el rótulo se queda un minuto
        self.refrescar()
        self.sonido.tocar(self.lista.currentData() or "", self.repetir.isChecked())
        if self.aviso is None:
            self.aviso = Aviso(self.app, self)
        detalle = (_tr("Alarma de {0}", _duracion(round(self.crono.alarma_total / 60.0))) + " · "
                   + time.strftime('%H:%M'))
        self.aviso.mostrar(self.recordatorio.toPlainText().strip(), detalle,
                           self.lista.currentText())

    def refrescar(self) -> None:
        self.dibujando.setText(_hms(self.crono.dibujando))
        self.abierto.setText(_hms(self.crono.abierto))
        restante = self.crono.restante()
        if restante is None and time.monotonic() < getattr(self, "_cumplido_hasta", 0.0):
            self.lectura.setText(_tr("¡Tiempo\ncumplido!"))
            self.boton.setText(_tr("Iniciar"))
        elif restante is not None:
            self.lectura.setText(_tr("Quedan\n{0}", _hms(restante)))
            self.boton.setText(_tr("Parar"))
        else:
            self.lectura.setText(_tr("Alarma:\n{0}", _duracion(self.esfera.minutos)))
            self.boton.setText(_tr("Iniciar"))
        self.esfera.update()


# ---- El aviso al sonar -----------------------------------------------------------

class Aviso(_Arrastrable, QFrame):
    """La ventana que sale centrada sobre IngeTrazo con el recordatorio; el
    sonido sigue hasta Cerrar o Posponer."""

    def __init__(self, app, panel: PanelTiempo) -> None:
        super().__init__(app.window, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.app = app
        self.panel = panel
        self.setObjectName("diana_aviso")
        self.setStyleSheet(
            "QFrame#diana_aviso { background: #ffffff; border: 2px solid #d62222; "
            "border-radius: 10px; }"
            "QFrame#diana_aviso QLabel { background: transparent; color: #6d6a63; }"
            "QLabel#titulo { color: #d62222; font-size: 14pt; font-weight: bold; }"
            "QLabel#texto { color: #111; font-size: 12pt; background: #fff7e6; "
            "border: 1px solid #f0d49a; border-radius: 6px; padding: 10px 12px; }"
            + _ESTILO_BOTONES)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        titulo = QLabel(_tr("⏰  ¡Se acabó el tiempo!"))
        titulo.setObjectName("titulo")
        lay.addWidget(titulo)
        self.detalle = QLabel("")
        lay.addWidget(self.detalle)
        self.texto = QLabel("")
        self.texto.setObjectName("texto")
        self.texto.setWordWrap(True)
        self.texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.texto)
        pie = QHBoxLayout()
        self.son = QLabel("")
        pie.addWidget(self.son, 1)
        posponer = QPushButton(_tr("Posponer 5 min"))
        posponer.clicked.connect(self._posponer)
        pie.addWidget(posponer)
        cerrar = QPushButton(_tr("Cerrar"))
        cerrar.setObjectName("prim")
        cerrar.clicked.connect(self.hide)
        pie.addWidget(cerrar)
        lay.addSpacing(6)
        lay.addLayout(pie)
        self.setFixedWidth(380)

    def mostrar(self, texto: str, detalle: str, sonido: str) -> None:
        self.texto.setText(_tr(texto))
        self.texto.setVisible(bool(texto))
        self.detalle.setText(_tr(detalle))
        self.son.setText("🔊 {0}".format(sonido))
        self.adjustSize()
        centro = self.app.window.frameGeometry().center()
        self.move(centro - QPoint(self.width() // 2, self.height() // 2))
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.alert(self.app.window)

    def _posponer(self) -> None:
        self.panel.posponer()
        self.hide()

    def hideEvent(self, ev) -> None:  # noqa: N802
        super().hideEvent(ev)
        self.panel.sonido.parar()


def ajustes() -> QSettings:
    from ._ajustes import ajustes as generales
    return generales("tiempo")

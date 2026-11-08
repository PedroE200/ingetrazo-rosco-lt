# SPDX-License-Identifier: GPL-3.0-or-later
"""El enlace con el gestor de barras: configurar desde su gestor qué va en cada
hueco de la barra.

Rosco LT se apunta en ``window._maestro_destinos`` (una lista que el gestor de barras lee
al abrir su gestor) con:

- ``secciones()``: los botones propios de la barra, para el árbol del gestor
  (claves «rosco_lt:<clave>», que solo valen para la barra);
- ``crear_panel(gestor, padre)``: el apartado «Barra Rosco LT» del lateral,
  el anillo en miniatura al que se arrastran los comandos del árbol (los de
  IngeTrazo, extensiones y comandos personales se guardan como «mh:<clave>»).
"""
from __future__ import annotations

from ._gestor import fijar_tipo, gestor_barras, tipo_arrastre
from ._idioma import _tr
import json
import logging
import math

from PySide6.QtCore import QByteArray, QMimeData, QPointF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QToolTip, QVBoxLayout, QWidget)

from . import _diana, _huecos, _iconos, _temas
from ._flotante import (BLANCO, CHINCHETA_R, NEGRO, ROJO, dibujar_banda, dibujar_boton_redondo,
                        glifo, relieve_redondo, sector)
from ._temas import CHICO_R

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

PREFIJO = "rosco_lt:"                  # botones propios en el árbol del gestor de barras
# Los botones propios de la barra, por apartados (en el árbol del gestor).
SECCIONES = (
    ("Dibujar", ("linea", "rect", "circle", "poly", "arco", "medir", "seleccionar",
                 "pintar", "borrar")),
    ("Modificar", ("move", "empujar", "scale", "flip", "rotate", "suprimir", "copiar", "cortar", "pegar",
                   "pegar_sitio", "agrupar", "bloquear", "ocultar", "invertir")),
    ("Botoncitos", ("deshacer", "rehacer", "opciones", "limpia", "apagar", "ext", "buscar",
                    "preferencias", "bar", "notas", "tiempo", "calc", "guardar", "copia",
                    "texto", "reiniciar", "cerrar_app")),
    ("Vistas", ("zoom_sel", "zoom_previo", "encuadre", "ocultar_resto", "centrar", "proyeccion",
                "sup_inf", "vista_frontal", "vista_posterior", "vista_derecha",
                "vista_izquierda", "vista_arriba", "vista_abajo", "ocultar_uno",
                "mostrar_ultimo", "mostrar_todo", "geometria_oculta", "objetos_ocultos", "ejes")),
    ("Ojos", ("rueda", "historial", "ayuda")),
)
NOMBRES_OJO = {"rueda": "Rueda de vistas (se abre al pasar por el ojo)",
               "historial": "Últimos comandos (se abren al pasar por el ojo)",
               "ayuda": "Ayuda de Rosco LT (se abre al pasar por el ojo)"}
COLOR_OJO = {"rueda": "arriba", "historial": "izquierda", "ayuda": "derecha"}
LADO = {"arriba": "de arriba", "derecha": "de la derecha", "abajo": "de abajo",
        "izquierda": "de la izquierda"}
R_TOTAL = 136.0                        # del centro del anillo a lo último (ojos, botoncitos)
R_RUEDA = _diana.RUEDA_R + 10.0


def _vivo(obj) -> bool:
    try:
        from shiboken6 import isValid
        return isValid(obj)
    except Exception:  # noqa: BLE001
        return obj is not None


class Enlace:
    """Lo que el gestor de barras necesita de la barra (ver arriba)."""

    prefijo = PREFIJO
    titulo = "Rosco LT"

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.paneles: list = []
        _iconos.ICONO_EXTERNO = self._icono_externo
        _iconos.NOMBRE_EXTERNO = cadena._nombre_externo
        win = cadena.app.window
        destinos = getattr(win, "_maestro_destinos", None)
        if not isinstance(destinos, list):
            destinos = win._maestro_destinos = []
        destinos[:] = [d for d in destinos if getattr(d, "prefijo", None) != PREFIJO]
        destinos.append(self)
        # el gestor de barras arma su catálogo un poco después de arrancar: los
        # iconos y nombres de sus comandos se vuelven a pedir entonces.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self._iconos_listos)

    def _iconos_listos(self) -> None:
        _iconos.olvidar_externos()
        self.cadena._etiqueta_w = None
        self.cadena._rehacer_dibujo()
        self.repintar()

    # ---- lo del gestor de barras ---------------------------------------------------------
    def _gestor(self):
        return gestor_barras(self.cadena.app.window)

    def _icono_externo(self, clave):
        gestor = self._gestor()
        if gestor is None:
            return None
        return gestor.icono(clave[len(_huecos.EXTERNO):])

    # ---- lo que pide el gestor de barras -----------------------------------------------------
    def secciones(self) -> list:
        return [(titulo, [PREFIJO + k for k in claves]) for titulo, claves in SECCIONES]

    def nombre(self, key: str) -> str:
        clave = key[len(PREFIJO):] if key.startswith(PREFIJO) else key
        return self.nombre_clave(clave)

    def nombre_clave(self, clave) -> str:
        if not clave:
            return "(vacío)"
        if clave in NOMBRES_OJO:
            return NOMBRES_OJO[clave]
        try:
            return self.cadena._texto_icono(clave)
        except Exception:  # noqa: BLE001
            return clave

    def descripcion(self, key: str) -> str:
        return "Botón de la barra Rosco LT: arrástralo a un hueco del apartado «Barra Rosco LT»."

    def icono(self, key: str) -> QIcon:
        clave = key[len(PREFIJO):] if key.startswith(PREFIJO) else key
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            if clave in _huecos.SOLO_OJOS:
                from ._cadena import OJOS
                p.scale(2.0, 2.0)
                self.cadena._pintar_ojo(p, QPointF(16.0, 16.0),
                                        OJOS[COLOR_OJO.get(clave, "izquierda")][2], False)
            else:
                glifo(p, clave, QPointF(32.0, 32.0), NEGRO, 56.0)
        finally:
            p.end()
        return QIcon(pm)

    def n_huecos(self) -> int:
        """Los huecos con algo puesto (el número de la cabecera)."""
        return len(self.cadena.huecos.todas())

    def ejecutar(self, key: str) -> None:
        self.cadena.app.viewport.flash_status(
            _tr("Los botones de Rosco LT se arrastran a un hueco del apartado «Barra Rosco LT»."), 4000)

    def crear_panel(self, gestor, padre=None) -> QWidget:
        fijar_tipo(gestor)
        panel = PanelHuecos(self, padre)
        self.paneles = [p for p in self.paneles if _vivo(p)] + [panel]
        return panel

    def repintar(self) -> None:
        vivos = []
        for p in self.paneles:
            if _vivo(p):
                try:
                    p.refrescar()
                    vivos.append(p)
                except RuntimeError:
                    pass
        self.paneles = vivos


# ---- El apartado «Barra Rosco LT»: el anillo en miniatura ---------------------------------

class PanelHuecos(QWidget):
    """El anillo, los botoncitos, los ojos y el aro de la rueda, en pequeño,
    con +/− por banda y «Por defecto»."""

    def __init__(self, enlace, padre=None) -> None:
        super().__init__(padre)
        self.enlace = enlace
        self.huecos = enlace.cadena.huecos
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)
        arriba = QHBoxLayout()
        pista = QLabel(_tr("Arrastra comandos del árbol a un hueco. Clic derecho: más opciones."))
        pista.setWordWrap(True)
        pista.setStyleSheet("color: #9aa4ae; font-size: 11px;")
        arriba.addWidget(pista, 1)
        defecto = QPushButton(_tr("Por defecto"))
        defecto.setAutoDefault(False)
        defecto.setToolTip(_tr("Vuelve a poner la barra como venía de serie"))
        defecto.clicked.connect(self._por_defecto)
        arriba.addWidget(defecto)
        v.addLayout(arriba)
        # El anillo, debajo los +/− de las bandas (centrados) y la rueda.
        self.anillo = _Lienzo(self, "anillo")
        v.addWidget(self.anillo)
        caja = QWidget()
        rejilla = QGridLayout(caja)
        rejilla.setContentsMargins(0, 2, 0, 4)
        rejilla.setHorizontalSpacing(4)
        rejilla.setVerticalSpacing(2)
        self._cuentas = {}
        for fila, g in enumerate(_huecos.BANDAS):
            nombre = QLabel(_tr(_huecos.NOMBRE_GRUPO[g]))
            nombre.setStyleSheet("color: #c9ced4; font-size: 11px;")
            menos, mas = QPushButton("−"), QPushButton("+")
            for b, fn, tip in ((menos, self.huecos.menos, "Un hueco menos"),
                               (mas, self.huecos.mas, "Un hueco más")):
                b.setFixedSize(QSize(24, 20))
                b.setAutoDefault(False)
                b.setToolTip(_tr(tip))
                b.clicked.connect(lambda _c=False, f=fn, gr=g: f(gr))
            cuenta = QLabel()
            cuenta.setAlignment(Qt.AlignCenter)
            cuenta.setMinimumWidth(22)
            cuenta.setStyleSheet("color: #e8eaed; font-size: 11px;")
            self._cuentas[g] = cuenta
            rejilla.addWidget(nombre, fila, 0)
            rejilla.addWidget(menos, fila, 1)
            rejilla.addWidget(cuenta, fila, 2)
            rejilla.addWidget(mas, fila, 3)
        centrada = QHBoxLayout()
        centrada.addStretch(1)
        centrada.addWidget(caja)
        centrada.addStretch(1)
        v.addLayout(centrada)
        self.rueda = _Lienzo(self, "rueda")
        v.addWidget(self.rueda)
        self.aviso = QLabel("")
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color: #F09595; font-size: 11px;")
        self.aviso.hide()
        v.addWidget(self.aviso)
        self.refrescar()

    def refrescar(self) -> None:
        for g, etiqueta in self._cuentas.items():
            lo, hi = _huecos.LIMITES[g]
            etiqueta.setText(_tr(str(len(self.huecos.banda(g)))))
            etiqueta.setToolTip(_tr("Entre {0} y {1} huecos", lo, hi))
        self.anillo.update()
        self.rueda.update()

    def avisar(self, texto: str) -> None:
        self.aviso.setText(_tr(texto))
        self.aviso.setVisible(bool(texto))

    def _por_defecto(self) -> None:
        r = QMessageBox.question(self, _tr("Barra Rosco LT"),
                                 _tr("¿Volver a poner la barra como venía de serie?\n"
                                 "Se pierde lo que hayas colocado en los huecos."))
        if r == QMessageBox.Yes:
            self.huecos.por_defecto()
            self.avisar("")


class _Lienzo(QWidget):
    """Un dibujo: el anillo con botoncitos y ojos (``parte="anillo"``) o la
    rueda con su aro (``"rueda"``). Acepta lo que se arrastra desde el árbol
    del gestor de barras (y entre huecos, para cambiarlos de sitio, también de
    un dibujo al otro)."""

    def __init__(self, panel, parte: str = "anillo") -> None:
        super().__init__(panel)
        self.panel = panel
        self.parte = parte
        self.cadena = panel.enlace.cadena
        self.huecos = panel.huecos
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumWidth(220)
        pol = self.sizePolicy()
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)
        self.setMinimumHeight(self.heightForWidth(220))
        self._encima = None                  # hueco bajo el ratón o bajo lo arrastrado
        self._pulsado = None                 # (hueco, posición) al pulsar

    # ---- geometría -------------------------------------------------------------------------
    def _tema(self):
        return _temas.tema(self.cadena.tema.clave)          # sin la escala del usuario

    def _escala(self) -> float:
        return max(0.4, min(1.0, (self.width() - 8.0) / (2.0 * R_TOTAL)))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(290, self.heightForWidth(290))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        s = max(0.4, min(1.0, (w - 8.0) / (2.0 * R_TOTAL)))
        radio = R_TOTAL * s if self.parte == "anillo" else R_RUEDA * s * 0.8
        return int(math.ceil(2.0 * radio + 4.0))

    def _centros(self):
        """Centro del anillo y de la rueda (px de su lienzo) y sus escalas."""
        s = self._escala()
        c = QPointF(self.width() / 2.0, R_TOTAL * s + 2.0)
        s2 = s * 0.8
        cr = QPointF(self.width() / 2.0, R_RUEDA * s2 + 2.0)
        return c, s, cr, s2

    @staticmethod
    def _pt(c, r, grados) -> QPointF:
        a = math.radians(grados)
        return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))

    def _centro_ojo(self, T, c, cual) -> QPointF:
        from ._cadena import OJO_R, OJOS
        angulo, donde, _color = OJOS[cual]
        r = T.r_ext + OJO_R + 2.0 if donde == "borde" else (T.r2[0] + T.r2[1]) / 2.0
        return self._pt(c, r, angulo)

    def hueco_en(self, pos):
        """``(grupo, índice u ojo)`` bajo ``pos`` (px del lienzo), o None."""
        from ._cadena import OJO_R, OJOS
        if self.parte == "rueda":
            return self._hueco_rueda(pos)
        T = self._tema()
        c, s, cr, s2 = self._centros()
        p = QPointF(c.x() + (pos.x() - c.x()) / s, c.y() + (pos.y() - c.y()) / s)
        for cual in OJOS:
            q = self._centro_ojo(T, c, cual)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= OJO_R + 3.0:
                return ("ojos", cual)
        r_chico = T.r_ext + CHICO_R + 3.0
        for j, angulo in enumerate(self.huecos.angulos_chicos):
            q = self._pt(c, r_chico, angulo)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHICO_R + 3.0:
                return ("chicos", j)
        lados = self.cadena.lados_de(T)
        for j, k, r_int, r_ext, a0, b, _tam in lados:
            if j == 6 and not k:
                q = self._mas_partir(c, r_int, r_ext, a0, b)
                if math.hypot(p.x() - q.x(), p.y() - q.y()) <= 6.0:
                    return ("lados", j)
        for j, k, r_int, r_ext, a0, b, _tam in lados:
            if j == 6 and not k:
                continue
            if sector(c, r_int, r_ext, a0, b).contains(p):
                return ("lados", j)
        dx, dy = p.x() - c.x(), c.y() - p.y()
        r = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        for g, claves, r_int, r_ext, a0, _tam in self.cadena.bandas_de(T):
            if not r_int - 2.0 <= r <= r_ext + 2.0:
                continue
            a = ang
            medio = a0 + T.barrido / 2.0
            while a - medio > 180.0:
                a -= 360.0
            while a - medio <= -180.0:
                a += 360.0
            if not a0 <= a <= a0 + T.barrido:
                continue
            n = len(claves)
            i = min(n - 1, max(0, int((a0 + T.barrido - a) // (T.barrido / n))))
            return (g, n - 1 - i if g in ("bi", "be") else i)
        return None

    def _mas_partir(self, c, r_int, r_ext, a0, b) -> QPointF:
        """Dónde va la crucecita del hueco de abajo vacío (en la parte baja
        del hueco de dentro de la izquierda, que entonces va entero)."""
        return self._pt(c, (r_int + r_ext) / 2.0, a0 + b * 0.82)

    def _hueco_rueda(self, pos):
        _c, _s, cr, s2 = self._centros()
        # El aro de la rueda.
        pr = QPointF(cr.x() + (pos.x() - cr.x()) / s2, cr.y() + (pos.y() - cr.y()) / s2)
        for j, angulo in enumerate(_huecos.ARO_ANGULOS):
            q = self._pt(cr, _diana.RUEDA_R * _diana.RUEDA_ARO, angulo)
            if math.hypot(pr.x() - q.x(), pr.y() - q.y()) <= _diana.ARO_BOTON_R + 3.0:
                return ("aro", j)
        # Dentro de la rueda: el centro (circulito y disco), los gajos y,
        # en el borde, los triángulos.
        R = _diana.RUEDA_R
        rb, rc, _ri, re = _diana._rueda_radios(R)
        dx, dy = pr.x() - cr.x(), cr.y() - pr.y()
        d = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx)) % 360.0
        if d <= rb + 1.5:
            return ("centro", 1)
        if d <= rc:
            return ("centro", 0)
        if d <= re + 2.0:
            paso = _diana.RUEDA_PASO
            i = int(((ang - (90.0 - paso / 2.0)) % 360.0) // paso)
            return ("gajos", min(i, _huecos.FIJOS["gajos"] - 1))
        if d <= R + 8.0:
            for j, g in enumerate(_diana.TRI_ANGULOS):
                if abs((ang - g + 180.0) % 360.0 - 180.0) <= 12.0:
                    return ("tri", j)
        return None

    # ---- dibujo ----------------------------------------------------------------------------
    def paintEvent(self, _ev) -> None:  # noqa: N802
        from ._cadena import OJO_R, OJOS
        T = self._tema()
        c, s, cr, s2 = self._centros()
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            if self.parte == "rueda":
                self._pintar_rueda(p, cr, s2)
                return
            p.save()
            p.translate(c)
            p.scale(s, s)
            p.translate(-c)
            for g, claves, r_int, r_ext, a0, tam in self.cadena.bandas_de(T):
                dibujar_banda(p, c, r_int, r_ext, claves, para_clic=True, a0=a0,
                              barrido=T.barrido, tam=tam, relieve=T.relieve)
                n, paso = len(claves), T.barrido / len(claves)
                for i, clave in enumerate(claves):
                    j = n - 1 - i if g in ("bi", "be") else i
                    trozo = sector(c, r_int, r_ext, a0 + T.barrido - paso * (i + 1), paso)
                    if not clave:
                        self._mas(p, self._pt(c, (r_int + r_ext) / 2.0,
                                              a0 + T.barrido - paso * (i + 0.5)))
                    if self._encima == (g, j):
                        self._tenir(p, trozo)
            # Los huecos de los lados (entre las dos mitades).
            for j, clave, r_int, r_ext, a0, b, tam in self.cadena.lados_de(T):
                if j == 6 and not clave:
                    # Vacío: Empujar va entero; solo una crucecita para partirlo.
                    q = self._mas_partir(c, r_int, r_ext, a0, b)
                    self._mas(p, q, 4.0)
                    if self._encima == ("lados", j):
                        camino = QPainterPath()
                        camino.addEllipse(q, 6.0, 6.0)
                        self._tenir(p, camino)
                    continue
                trozo = sector(c, r_int, r_ext, a0, b)
                dibujar_banda(p, c, r_int, r_ext, (clave,), para_clic=True, a0=a0,
                              barrido=b, tam=tam, relieve=T.relieve)
                if not clave:
                    self._mas(p, self._pt(c, (r_int + r_ext) / 2.0, a0 + b / 2.0), 4.0)
                if self._encima == ("lados", j):
                    self._tenir(p, trozo)
            r_chico = T.r_ext + CHICO_R + 3.0
            for j, (clave, angulo) in enumerate(zip(self.huecos.chicos(), self.huecos.angulos_chicos)):
                q = self._pt(c, r_chico, angulo)
                self._redondo(p, q, CHICO_R, clave, 0.6, ("chicos", j))
            for cual, (_a, _d, color) in OJOS.items():
                q = self._centro_ojo(T, c, cual)
                self.cadena._pintar_ojo(p, q, color, False)
                clave = self.huecos.ojos().get(cual, "")
                insignia = QPointF(q.x() + OJO_R * 0.85, q.y() + OJO_R * 0.55)
                if clave and clave not in _huecos.SOLO_OJOS:
                    self._redondo(p, insignia, 7.0, clave, 0.45, None)
                elif not clave:
                    self._mas(p, insignia, 4.0)
                if self._encima == ("ojos", cual):
                    camino = QPainterPath()
                    camino.addEllipse(q, OJO_R + 2.0, OJO_R + 2.0)
                    self._tenir(p, camino)
            p.restore()
        finally:
            p.end()

    def _pintar_rueda(self, p, cr, s2) -> None:
        """La rueda, más pequeña, con su interior y los seis huecos del aro."""
        p.save()
        p.translate(cr)
        p.scale(s2, s2)
        p.translate(-cr)
        _diana.rueda_pintar(p, cr, None, self.cadena.diana.proyeccion_actual())
        self._pintar_dentro(p, cr)
        for j, (clave, angulo) in enumerate(zip(self.huecos.aro(), _huecos.ARO_ANGULOS)):
            q = self._pt(cr, _diana.RUEDA_R * _diana.RUEDA_ARO, angulo)
            if clave:
                _diana._boton_aro_pintar(p, clave, q)
            else:
                p.setPen(QPen(BLANCO, 1.0))
                p.setBrush(QBrush(BLANCO))
                p.drawEllipse(q, _diana.ARO_BOTON_R, _diana.ARO_BOTON_R)
                self._mas(p, q)
            if self._encima == ("aro", j):
                camino = QPainterPath()
                camino.addEllipse(q, _diana.ARO_BOTON_R + 1.0, _diana.ARO_BOTON_R + 1.0)
                self._tenir(p, camino)
        p.restore()

    def _pintar_dentro(self, p, cr) -> None:
        """Lo de dentro de la rueda: cruces en lo vacío y el tinte del hueco
        bajo el ratón (gajos, triángulos, disco y circulito)."""
        R = _diana.RUEDA_R
        rb, rc, ri, re = _diana._rueda_radios(R)
        for i, clave in enumerate(self.huecos.lista("gajos")):
            if not clave:
                self._mas(p, self._pt(cr, (ri + re) / 2.0, 90.0 + _diana.RUEDA_PASO * i))
            if self._encima == ("gajos", i):
                self._tenir(p, _diana._rueda_gajo(cr, i, R))
        for j, (clave, grados) in enumerate(zip(self.huecos.lista("tri"), _diana.TRI_ANGULOS)):
            triangulo = _diana._rueda_triangulo(cr, grados, R)
            if not clave:
                p.save()
                p.setPen(QPen(QColor(150, 150, 150), 1.2, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawPath(triangulo)
                p.restore()
            if self._encima == ("tri", j):
                self._tenir(p, triangulo)
        disco, circulito = (self.huecos.lista("centro") + ["", ""])[:2]
        if not disco:
            self._mas(p, QPointF(cr.x(), cr.y() + rc * 0.58))
        if not circulito:
            self._mas(p, cr, 4.0)
        for j, radio in ((0, rc), (1, rb)):
            if self._encima == ("centro", j):
                camino = QPainterPath()
                camino.addEllipse(cr, radio, radio)
                if j == 0:
                    hueco = QPainterPath()
                    hueco.addEllipse(cr, rb, rb)
                    camino = camino.subtracted(hueco)
                self._tenir(p, camino)

    def _redondo(self, p, q, radio, clave, escala, hueco) -> None:
        """Un botoncito (o el hueco vacío, a trazos)."""
        p.save()
        if clave:
            p.setPen(QPen(ROJO, 1.4))
            p.setBrush(relieve_redondo(q, radio))
            p.drawEllipse(q, radio, radio)
            p.translate(q)
            p.scale(escala, escala)
            glifo(p, clave, QPointF(0.0, 0.0), NEGRO)
        else:
            pen = QPen(QColor(150, 150, 150), 1.2, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QBrush(QColor(255, 255, 255, 40)))
            p.drawEllipse(q, radio, radio)
        p.restore()
        if hueco is not None and self._encima == hueco:
            camino = QPainterPath()
            camino.addEllipse(q, radio + 1.5, radio + 1.5)
            self._tenir(p, camino)

    @staticmethod
    def _mas(p, q, brazo: float = 5.0) -> None:
        """La cruz de un hueco vacío."""
        p.save()
        p.setPen(QPen(QColor(160, 160, 160), 1.6))
        p.drawLine(QPointF(q.x() - brazo, q.y()), QPointF(q.x() + brazo, q.y()))
        p.drawLine(QPointF(q.x(), q.y() - brazo), QPointF(q.x(), q.y() + brazo))
        p.restore()

    @staticmethod
    def _tenir(p, camino) -> None:
        tinte = QColor(ROJO)
        tinte.setAlphaF(0.30)
        p.save()
        p.setPen(QPen(ROJO, 2.0, Qt.DashLine))
        p.setBrush(QBrush(tinte))
        p.drawPath(camino)
        p.restore()

    # ---- ratón: ayuda, menú y arrastrar entre huecos ---------------------------------------
    def _texto(self, hueco) -> str:
        g, i = hueco
        clave = self.huecos.clave(g, i)
        if g == "ojos":
            donde = _tr("ojo {0}", _tr(LADO[i]))
        elif g == "tri":
            donde = _tr(_huecos.NOMBRE_GRUPO[g]) + " · " + _tr(_huecos.NOMBRE_TRI[i])
        elif g == "centro":
            donde = _tr(_huecos.NOMBRE_GRUPO[g]) + " · " + _tr(_huecos.NOMBRE_CENTRO[i])
        elif g == "lados":
            donde = (_tr("Lado {0}", _tr("izquierdo" if i in (0, 1, 2, 6) else "derecho")) + " · "
                     + _tr({1: "dentro, arriba", 6: "dentro, abajo"}.get(
                         i, ("encima del ojo", "dentro", "debajo del ojo")[i % 3])))
        else:
            donde = _tr(_huecos.NOMBRE_GRUPO[g]) + f" · {i + 1}"
        return f"{donde}: {self.panel.enlace.nombre_clave(clave)}"

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        pos = ev.position()
        if self._pulsado is not None and ev.buttons() & Qt.LeftButton:
            hueco, inicio = self._pulsado
            if (pos - inicio).manhattanLength() >= 8 and self.huecos.clave(*hueco):
                self._pulsado = None
                self._arrastrar(hueco)
                return
        hueco = self.hueco_en(pos)
        if hueco != self._encima:
            self._encima = hueco
            self.update()
        if hueco is not None:
            QToolTip.showText(ev.globalPosition().toPoint(), self._texto(hueco), self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _ev) -> None:  # noqa: N802
        self._encima = None
        self.update()

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        hueco = self.hueco_en(ev.position())
        if hueco is None:
            return
        if ev.button() == Qt.LeftButton:
            self._pulsado = (hueco, ev.position())
        elif ev.button() == Qt.RightButton:
            self._menu(hueco, ev.globalPosition().toPoint())

    def mouseReleaseEvent(self, _ev) -> None:  # noqa: N802
        self._pulsado = None

    def _arrastrar(self, hueco) -> None:
        g, i = hueco
        clave = self.huecos.clave(g, i)
        key = clave[len(_huecos.EXTERNO):] if _huecos.externo(clave) else PREFIJO + clave
        md = QMimeData()
        md.setData(tipo_arrastre(), QByteArray(json.dumps({"key": key, "origen": f"rosco_lt:{g}:{i}",
                                                "indice": -1}).encode("utf-8")))
        md.setText(key)
        drag = QDrag(self)
        drag.setMimeData(md)
        icono = self.panel.enlace.icono(PREFIJO + clave) if not _huecos.externo(clave) else None
        if icono is None:
            gestor = self.panel.enlace._gestor()
            icono = gestor.icono(key) if gestor is not None else QIcon()
        if not icono.isNull():
            drag.setPixmap(icono.pixmap(28, 28))
        drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)

    def _menu(self, hueco, pos) -> None:
        g, i = hueco
        m = QMenu(self)
        m.addSection(_tr(self._texto(hueco)))
        vaciar = m.addAction(_tr("Vaciar este hueco"))
        vaciar.setEnabled(bool(self.huecos.clave(g, i)))
        izq = der = quitar = None
        if g in _huecos.BANDAS:
            lo, hi = _huecos.LIMITES[g]
            n = len(self.huecos.banda(g))
            izq = m.addAction(_tr("Añadir un hueco a la izquierda"))
            der = m.addAction(_tr("Añadir un hueco a la derecha"))
            izq.setEnabled(n < hi)
            der.setEnabled(n < hi)
            quitar = m.addAction(_tr("Quitar este hueco"))
            quitar.setEnabled(n > lo)
        m.addSeparator()
        defecto = m.addAction(_tr("Toda la barra por defecto…"))
        elegida = m.exec(pos)
        if elegida is None:
            return
        if elegida is vaciar:
            self.huecos.vaciar(g, i)
        elif elegida is izq:
            self.huecos.mas(g, i)
        elif elegida is der:
            self.huecos.mas(g, i + 1)
        elif elegida is quitar:
            self.huecos.menos(g, i)
        elif elegida is defecto:
            self.panel._por_defecto()

    # ---- soltar ----------------------------------------------------------------------------
    @staticmethod
    def _leer(md):
        if not md.hasFormat(tipo_arrastre()):
            return None
        try:
            info = json.loads(bytes(md.data(tipo_arrastre())).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        return info if isinstance(info, dict) and info.get("key") else None

    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        if self._leer(ev.mimeData()) is not None:
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:  # noqa: N802
        hueco = self.hueco_en(ev.position())
        if hueco != self._encima:
            self._encima = hueco
            self.update()
        if hueco is not None and self._leer(ev.mimeData()) is not None:
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragLeaveEvent(self, _ev) -> None:  # noqa: N802
        self._encima = None
        self.update()

    def dropEvent(self, ev) -> None:  # noqa: N802
        info = self._leer(ev.mimeData())
        hueco = self.hueco_en(ev.position())
        self._encima = None
        self.update()
        if info is None or hueco is None:
            return
        key, origen = str(info["key"]), str(info.get("origen") or "")
        if key == "|":
            self.panel.avisar("Los separadores no caben en la barra.")
            return
        g, i = hueco
        motivo = ""
        partes = origen.split(":")
        if len(partes) == 3 and partes[0] == "rosco_lt":
            # De otro hueco: se cambian de sitio.
            g0, i0 = partes[1], partes[2]
            if g0 != "ojos":
                i0 = int(i0)
            if (g0, i0) != (g, i):
                motivo = self.huecos.intercambiar(g0, i0, g, i)
        else:
            clave = key[len(PREFIJO):] if key.startswith(PREFIJO) else _huecos.EXTERNO + key
            motivo = self.huecos.poner(g, i, clave)
        self.panel.avisar(motivo)
        ev.acceptProposedAction()

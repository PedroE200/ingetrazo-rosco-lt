# SPDX-License-Identifier: GPL-3.0-or-later
"""El enlace con el gestor de barras: configurar desde su gestor qué va en cada
hueco de la barra.

Rosco se apunta en la lista de la ventana ``_gestor.DESTINOS_GESTOR`` (la que el
gestor de barras lee al abrir su gestor) con:

- ``secciones()``: los botones propios de la barra, para el árbol del gestor
  (claves «rosco:<clave>», que solo valen para la barra);
- ``crear_panel(gestor, padre)``: el apartado «Barra Rosco» del lateral,
  el anillo en miniatura al que se arrastran los comandos del árbol (los de
  IngeTrazo, extensiones y comandos personales se guardan con el prefijo
  ``_gestor.PREFIJO_EXTERNO``).
"""
from __future__ import annotations

from ._gestor import DESTINOS_GESTOR, fijar_tipo, gestor_barras, tipo_arrastre
from ._idioma import con_nombre, _tr
import json
import logging
import math

from PySide6.QtCore import QByteArray, QMimeData, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QToolTip, QVBoxLayout, QWidget)

from . import _diana, _huecos, _iconos, _temas
from ._voz import con_microfono
from ._flotante import BLANCO, NEGRO, ROJO, dibujar_banda, glifo, relieve_redondo, sector
from ._temas import CHICO_R

from ._ajustes import CLAVE, registro

log = registro()
PREFIJO = f"{CLAVE}:"                  # botones propios en el árbol del gestor de barras
# Los botones propios de la barra, por apartados (en el árbol del gestor).
SECCIONES = (
    ("Dibujar", ("linea", "rect", "circle", "poly", "arco", "medir", "seleccionar", "sel_rapida",
                 "pintar", "borrar")),
    ("Modificar", ("move", "empujar", "scale", "flip", "rotate", "suprimir", "portapapeles", "copiar", "cortar", "pegar",
                   "pegar_sitio", "agrupar", "bloquear", "ocultar", "invertir")),
    ("Botoncitos", ("deshacer", "rehacer", "opciones", "limpia", "apagar", "ext", "buscar",
                    "preferencias", "bar", "notas", "tiempo", "calc", "guardar", "copia",
                    "texto", "reiniciar", "cerrar_app")),
    ("Vistas", ("zoom_sel", "alinear_vista", "zoom_previo", "encuadre", "ocultar_resto", "centrar", "proyeccion",
                "sup_inf", "vista_frontal", "vista_posterior", "vista_derecha",
                "vista_izquierda", "vista_arriba", "vista_abajo", "ocultar_uno",
                "mostrar_ultimo", "mostrar_todo", "geometria_oculta", "objetos_ocultos", "ejes")),
    ("Ojos", ("rueda", "historial", "texturas", "ayuda")),
)
NOMBRES_OJO = {"rueda": "Rueda de vistas (se abre al pasar por el ojo)",
               "historial": "Últimos comandos (se abren al pasar por el ojo)",
               "texturas": "Biblioteca de texturas (un clic en el ojo abre su ventana)",
               "ayuda": "Ayuda rápida (se abre al pasar por el ojo; un clic abre Opciones ▸ Ayuda)"}
# El ojo de cada función de serie (el icono usa el ojo donde está de verdad).
COLOR_OJO = {"rueda": "arriba", "historial": "derecha", "texturas": "izquierda", "ayuda": "izquierda"}
# Solo los botones de esta edición; la ayuda va en un ojo solo si no hay
# texturas (es lo que el ojo verde abría antes).
from . import _edicion  # noqa: E402
NOMBRES_OJO = _edicion.limpiar(NOMBRES_OJO)
SECCIONES = tuple((titulo, tuple(k for k in claves if _edicion.clave(k)
                                 and (k != "ayuda" or (not _edicion.con("texturas") and _edicion.con("panel_ayuda")))))
                  for titulo, claves in SECCIONES)
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


def _parte_anillos2():
    """El módulo de los anillos personalizados (solo si la edición lo lleva:
    sin él, el gestor usa ``PanelHuecos`` y no llega aquí)."""
    if not _edicion.con("anillos2"):
        raise RuntimeError("esta edición no lleva los anillos personalizados")
    from . import _anillos2
    return _anillos2


class Enlace:
    """Lo que el gestor de barras necesita de la barra (ver arriba)."""

    prefijo = PREFIJO
    titulo = con_nombre("Rosco")

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.paneles: list = []
        _iconos.ICONO_EXTERNO = self._icono_externo
        _iconos.NOMBRE_EXTERNO = cadena._nombre_externo
        win = cadena.app.window
        destinos = getattr(win, DESTINOS_GESTOR, None)
        if not isinstance(destinos, list):
            destinos = []
            setattr(win, DESTINOS_GESTOR, destinos)
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
        return _tr("Botón de la barra Rosco: arrástralo a un hueco del apartado «Barra Rosco».")

    def icono(self, key: str) -> QIcon:
        clave = key[len(PREFIJO):] if key.startswith(PREFIJO) else key
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            if clave in _huecos.SOLO_EN_OJO:
                from ._cadena import OJOS
                p.scale(2.0, 2.0)
                cual = self.cadena.huecos.ojo_de(clave) or COLOR_OJO.get(clave, "izquierda")
                self.cadena._pintar_ojo(p, QPointF(16.0, 16.0), OJOS[cual][2], False)
            else:
                glifo(p, clave, QPointF(32.0, 32.0), NEGRO, 56.0)
        finally:
            p.end()
        return QIcon(pm)

    def n_huecos(self) -> int:
        """Los botones puestos en los dos anillos (el número de la cabecera)."""
        if not _edicion.con("anillos2"):
            from . import _cadena
            return sum(1 for k in _cadena.ANILLO_DENTRO + _cadena.ANILLO_FUERA if k)
        _anillos2 = _parte_anillos2()
        cfg = _anillos2.leer(self.cadena.huecos.id_activo)
        return sum(1 for k in cfg["dentro"] + cfg["fuera"] if k)

    def ejecutar(self, key: str) -> None:
        self.cadena.app.viewport.flash_status(
            _tr("Los botones de Rosco se arrastran a un hueco del apartado «Barra Rosco»."), 4000)

    def crear_panel(self, gestor, padre=None) -> QWidget:
        fijar_tipo(gestor)
        panel = (PanelAnillos2 if _edicion.con("anillos2") else PanelHuecos)(self, padre)
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


# ---- El apartado «Barra Rosco»: el anillo en miniatura ---------------------------------

class _SelectorSinRueda(QComboBox):
    """La rueda del ratón no cambia el grupo por descuido."""

    def wheelEvent(self, ev) -> None:  # noqa: N802
        ev.ignore()


class _DialogoNombre(QDialog):
    """Pide el nombre de un grupo. ``validar(texto)`` devuelve None o el
    motivo del rechazo; si lo hay, se enseña y el diálogo sigue abierto."""

    def __init__(self, padre, titulo: str, inicial: str, validar) -> None:
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.validar = validar
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_tr("Nombre del grupo")))
        self.campo = QLineEdit(inicial)
        self.campo.setMaxLength(_huecos.MAX_NOMBRE)
        con_microfono(self.campo)
        v.addWidget(self.campo)
        self.aviso = QLabel("")
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color: #F09595; font-size: 11px;")
        self.aviso.hide()
        v.addWidget(self.aviso)
        botones = QHBoxLayout()
        botones.addStretch(1)
        aceptar, cancelar = QPushButton(_tr("Aceptar")), QPushButton(_tr("Cancelar"))
        aceptar.setDefault(True)
        cancelar.setAutoDefault(False)
        aceptar.clicked.connect(self._aceptar)
        cancelar.clicked.connect(self.reject)
        botones.addWidget(aceptar)
        botones.addWidget(cancelar)
        v.addLayout(botones)
        self.campo.selectAll()

    def _aceptar(self) -> None:
        motivo = self.validar(self.texto())
        if motivo is None:
            self.accept()
            return
        self.aviso.setText(_tr(motivo[0], *motivo[1]))
        self.aviso.show()

    def texto(self) -> str:
        return self.campo.text()


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
        self.defecto = QPushButton(_tr("Por defecto"))
        self.defecto.setAutoDefault(False)
        self.defecto.clicked.connect(self._por_defecto)
        arriba.addWidget(self.defecto)
        v.addLayout(arriba)
        # El grupo que se ve y se edita, con sus botones.
        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.selector = _SelectorSinRueda()
        self.selector.setToolTip(_tr("Elige el grupo de huecos de la barra"))
        self.selector.currentIndexChanged.connect(self._elegir)
        fila.addWidget(self.selector, 1)
        self.b_nuevo, self.b_renombrar, self.b_eliminar = (
            QPushButton(_tr("Nuevo")), QPushButton(_tr("Renombrar")), QPushButton(_tr("Eliminar")))
        for b, fn in ((self.b_nuevo, self._nuevo), (self.b_renombrar, self._renombrar),
                      (self.b_eliminar, self._eliminar)):
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, f=fn: f())
            fila.addWidget(b)
        v.addLayout(fila)
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
        self.aviso = QLabel(_tr(""))
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color: #F09595; font-size: 11px;")
        self.aviso.hide()
        v.addWidget(self.aviso)
        self.refrescar()

    def refrescar(self) -> None:
        self._refrescar_grupos()
        for g, etiqueta in self._cuentas.items():
            lo, hi = _huecos.LIMITES[g]
            etiqueta.setText(_tr(str(len(self.huecos.banda(g)))))
            etiqueta.setToolTip(_tr("Entre {0} y {1} huecos", lo, hi))
        self.anillo.update()
        self.rueda.update()

    def avisar(self, texto: str) -> None:
        self.aviso.setText(_tr(texto))
        self.aviso.setVisible(bool(texto))

    def _refrescar_grupos(self) -> None:
        h = self.huecos
        juegos = h.juegos()
        self.selector.blockSignals(True)
        self.selector.clear()
        for id_juego, nombre, _color in juegos:
            self.selector.addItem(nombre, id_juego)
        self.selector.setCurrentIndex(max(0, self.selector.findData(h.id_activo)))
        self.selector.blockSignals(False)
        self.b_nuevo.setEnabled(len(juegos) < _huecos.MAX_JUEGOS)
        self.b_eliminar.setEnabled(h.id_activo != _huecos.ID_GENERAL)
        self.defecto.setToolTip(_tr("Vuelve a poner el grupo activo como venía de serie" if len(juegos) > 1
                                    else "Vuelve a poner la barra como venía de serie"))

    def _elegir(self, indice: int) -> None:
        id_juego = self.selector.itemData(indice)
        if id_juego is not None:
            # Al activar se rellena otra vez el selector: mejor fuera de su señal.
            QTimer.singleShot(0, lambda: self.huecos.activar(id_juego))

    def _mostrar_motivo(self, motivo) -> None:
        self.avisar(_tr(motivo[0], *motivo[1]) if motivo else "")

    def _nuevo(self) -> None:
        dialogo = _DialogoNombre(self, _tr("Nuevo grupo"), "", self.huecos.validar_nombre)
        if dialogo.exec() == QDialog.Accepted:
            self._mostrar_motivo(self.huecos.nuevo(dialogo.texto()))

    def _renombrar(self) -> None:
        h = self.huecos
        id_juego = h.id_activo
        dialogo = _DialogoNombre(self, _tr("Renombrar grupo"), h.nombre_visible(id_juego),
                                 lambda texto: h.validar_nombre(texto, id_juego))
        if dialogo.exec() == QDialog.Accepted:
            self._mostrar_motivo(h.renombrar(id_juego, dialogo.texto()))

    def _eliminar(self) -> None:
        h = self.huecos
        id_juego = h.id_activo
        r = QMessageBox.question(self, _tr("Eliminar grupo"),
                                 _tr("¿Eliminar el grupo «{0}»?\nNo se puede deshacer.",
                                     h.nombre_visible(id_juego)))
        if r == QMessageBox.Yes:
            h.borrar(id_juego)

    def _por_defecto(self) -> None:
        h = self.huecos
        if h.n_juegos() > 1:
            pregunta = _tr("¿Volver a poner el grupo «{0}» como venía de serie?\n"
                           "Se pierde lo que hayas colocado en sus huecos.",
                           h.nombre_visible(h.id_activo))
        else:
            pregunta = _tr("¿Volver a poner la barra como venía de serie?\n"
                           "Se pierde lo que hayas colocado en los huecos.")
        r = QMessageBox.question(self, _tr("Barra Rosco"), pregunta)
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
        md.setData(tipo_arrastre(), QByteArray(json.dumps({"key": key, "origen": f"{CLAVE}:{g}:{i}",
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
        defecto = m.addAction(_tr("Este grupo por defecto…" if self.huecos.n_juegos() > 1
                                  else "Toda la barra por defecto…"))
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
        if len(partes) == 3 and partes[0] == CLAVE:
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


# ---- Rosco 1.11.0: los dos anillos y la subbarra de cada botón ---------------------

_MIME_SUB = "application/x-rosco-subbarra"


def _a_clave(key: str) -> str:
    """La clave de hueco de lo que llega del árbol del gestor de barras."""
    return key[len(PREFIJO):] if key.startswith(PREFIJO) else _huecos.EXTERNO + key


class PanelAnillos2(PanelHuecos):
    """El apartado «Barra Rosco»: grupos, los dos anillos con sus ojos y
    botoncitos, la subbarra del botón elegido y la rueda."""

    def __init__(self, enlace, padre=None) -> None:
        QWidget.__init__(self, padre)
        self.enlace = enlace
        self.huecos = enlace.cadena.huecos
        self.elegido = None                  # ("dentro" | "fuera", índice) del botón elegido
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)
        arriba = QHBoxLayout()
        pista = QLabel(_tr("Arrastra comandos del árbol a un botón del anillo o a su subbarra. "
                           "Clic en un botón: su subbarra abajo."))
        pista.setWordWrap(True)
        pista.setStyleSheet("color: #9aa4ae; font-size: 11px;")
        arriba.addWidget(pista, 1)
        self.defecto = QPushButton(_tr("Por defecto"))
        self.defecto.setAutoDefault(False)
        self.defecto.clicked.connect(self._por_defecto)
        arriba.addWidget(self.defecto)
        v.addLayout(arriba)
        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.selector = _SelectorSinRueda()
        self.selector.setToolTip(_tr("Elige el grupo de huecos de la barra"))
        self.selector.currentIndexChanged.connect(self._elegir)
        fila.addWidget(self.selector, 1)
        self.b_nuevo, self.b_renombrar, self.b_eliminar = (
            QPushButton(_tr("Nuevo")), QPushButton(_tr("Renombrar")), QPushButton(_tr("Eliminar")))
        for b, fn in ((self.b_nuevo, self._nuevo), (self.b_renombrar, self._renombrar),
                      (self.b_eliminar, self._eliminar)):
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, f=fn: f())
            fila.addWidget(b)
        v.addLayout(fila)
        self.anillo = _LienzoAnillos(self)
        v.addWidget(self.anillo)
        nota = QLabel(_tr("Arrastra entre botones para cambiarlos de sitio · clic derecho: vaciar el hueco"))
        nota.setAlignment(Qt.AlignCenter)
        nota.setWordWrap(True)
        nota.setStyleSheet("color: #9aa4ae; font-size: 11px;")
        v.addWidget(nota)
        self.editor = _EditorSub(self)
        v.addWidget(self.editor)
        self.rueda = _Lienzo(self, "rueda")
        v.addWidget(self.rueda)
        self.aviso = QLabel(_tr(""))
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color: #F09595; font-size: 11px;")
        self.aviso.hide()
        v.addWidget(self.aviso)
        self.refrescar()

    # -- los datos del grupo activo --
    def cfg(self) -> dict:
        _anillos2 = _parte_anillos2()
        return _anillos2.leer(self.huecos.id_activo)

    def guardar(self, cfg) -> None:
        _anillos2 = _parte_anillos2()
        _anillos2.guardar(self.huecos.id_activo, cfg)
        self.enlace.cadena._huecos_cambiados()      # el rosco lo usa ya y repinta los paneles

    def clave_elegida(self) -> str:
        if self.elegido is None:
            return ""
        anillo, i = self.elegido
        lista = self.cfg()[anillo]
        return lista[i] if 0 <= i < len(lista) else ""

    def elegir_boton(self, hueco) -> None:
        self.elegido = hueco
        self.anillo.update()
        self.editor.refrescar()

    def refrescar(self) -> None:
        self._refrescar_grupos()
        self.anillo.update()
        self.editor.refrescar()
        self.rueda.update()

    def _nuevo(self) -> None:
        _anillos2 = _parte_anillos2()
        antes = {j[0] for j in self.huecos.juegos()}
        super()._nuevo()
        for id_juego, _n, _c in self.huecos.juegos():
            if id_juego not in antes:
                _anillos2.borrar(id_juego)     # el grupo nuevo empieza en blanco
                self.enlace.cadena._huecos_cambiados(soltar=False)

    def _eliminar(self) -> None:
        _anillos2 = _parte_anillos2()
        id_juego = self.huecos.id_activo
        antes = {j[0] for j in self.huecos.juegos()}
        super()._eliminar()
        if id_juego in antes and id_juego not in {j[0] for j in self.huecos.juegos()}:
            _anillos2.borrar(id_juego)

    def _por_defecto(self) -> None:
        _anillos2 = _parte_anillos2()
        h = self.huecos
        r = QMessageBox.question(self, _tr("Barra Rosco"),
                                 _tr("¿Poner en el grupo «{0}» los botones y las subbarras de serie?\n"
                                     "Se pierde lo que hayas colocado en los anillos.",
                                     h.nombre_visible(h.id_activo)))
        if r == QMessageBox.Yes:
            self.guardar(_anillos2.defecto())
            self.avisar("")


class _LienzoAnillos(_Lienzo):
    """Los dos anillos de Rosco con sus ojos y botoncitos, en pequeño."""

    def __init__(self, panel) -> None:
        super().__init__(panel, "anillos2")

    # ---- geometría --------------------------------------------------------------------------
    def _r_total(self) -> float:
        T = self._tema()
        return T.r_ext + 2.0 * CHICO_R + 10.0

    def _escala(self) -> float:
        return max(0.4, min(1.25, (self.width() - 8.0) / (2.0 * self._r_total())))

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        s = max(0.4, min(1.25, (w - 8.0) / (2.0 * self._r_total())))
        return int(math.ceil(2.0 * self._r_total() * s + 6.0))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, self.heightForWidth(320))

    def _centro(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _bandas(self, T):
        from . import _cadena as C
        p = C.PASO_FUERA
        arriba, abajo = C.ANILLO_FUERA[1:8], C.ANILLO_FUERA[9:]
        tam_d = min(T.tam1, 0.8 * (T.r1[0] + T.r1[1]) / 2.0 * math.radians(C.PASO_DENTRO))
        tam_f = min(T.tam2, 0.8 * (T.r2[0] + T.r2[1]) / 2.0 * math.radians(p))
        return ((C.ANILLO_DENTRO, T.r1[0], T.r1[1], 90.0 + C.PASO_DENTRO / 2.0 - 360.0, tam_d, 360.0),
                (arriba, T.r2[0], T.r2[1], C.OJO_DER_A + p / 2.0, tam_f, p * len(arriba)),
                (abajo, T.r2[0], T.r2[1], C.OJO_IZQ_A + p / 2.0 - 360.0, tam_f, p * len(abajo)))

    def _trozo(self, T, c, anillo, i):
        from . import _cadena as C
        if anillo == "dentro":
            a, paso, (r0, r1) = 90.0 - i * C.PASO_DENTRO, C.PASO_DENTRO, T.r1
        else:
            a, paso, (r0, r1) = C.OJO_IZQ_A - i * C.PASO_FUERA, C.PASO_FUERA, T.r2
        return sector(c, r0, r1, a - paso / 2.0, paso), self._pt(c, (r0 + r1) / 2.0, a)

    def hueco_en(self, pos):
        from . import _cadena as C
        from ._cadena import OJO_R, OJOS
        T = self._tema()
        c, s = self._centro(), self._escala()
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
        dx, dy = p.x() - c.x(), c.y() - p.y()
        r = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        for anillo, (r0, r1), a0, n, paso in (("dentro", T.r1, 90.0, len(C.ANILLO_DENTRO), C.PASO_DENTRO),
                                             ("fuera", T.r2, C.OJO_IZQ_A, len(C.ANILLO_FUERA), C.PASO_FUERA)):
            if r0 - 2.0 <= r <= r1 + 2.0:
                i = int(round((a0 - ang) / paso)) % n
                if anillo == "fuera" and i in C.OJOS_FUERA:
                    return None
                return (anillo, i)
        return None

    def _clave_en(self, hueco) -> str:
        g, i = hueco
        if g in ("dentro", "fuera"):
            lista = self.panel.cfg()[g]
            return lista[i] if 0 <= i < len(lista) else ""
        return self.huecos.clave(g, i)

    def _texto(self, hueco) -> str:
        g, i = hueco
        clave = self._clave_en(hueco)
        if g == "dentro":
            donde = _tr("Anillo de dentro · {0}", i + 1)
        elif g == "fuera":
            donde = _tr("Anillo de fuera · {0}", i + 1)
        elif g == "ojos":
            donde = _tr("ojo {0}", _tr(LADO[i]))
        else:
            donde = _tr(_huecos.NOMBRE_GRUPO[g]) + f" · {i + 1}"
        return f"{donde}: {self.panel.enlace.nombre_clave(clave)}"

    # ---- dibujo -----------------------------------------------------------------------------
    def paintEvent(self, _ev) -> None:  # noqa: N802
        from ._flotante import fijar_centro
        from ._cadena import OJO_R, OJOS
        T = self._tema()
        c, s = self._centro(), self._escala()
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.translate(c)
            p.scale(s, s)
            p.translate(-c)
            fijar_centro(p, c, T.abajo_anillo)
            for claves, r_int, r_ext, a0, tam, barrido in self._bandas(T):
                dibujar_banda(p, c, r_int, r_ext, claves, para_clic=True, a0=a0,
                              barrido=barrido, tam=tam, relieve=T.relieve)
            cfg = self.panel.cfg()
            for anillo in ("dentro", "fuera"):
                for i, clave in enumerate(cfg[anillo]):
                    if anillo == "fuera" and i in (0, 8):
                        continue
                    trozo, centro = self._trozo(T, c, anillo, i)
                    if not clave:
                        self._mas(p, centro, 6.0)
                    if self.panel.elegido == (anillo, i):
                        p.save()
                        p.setPen(QPen(ROJO, 3.2))
                        p.setBrush(Qt.NoBrush)
                        p.drawPath(trozo)
                        p.restore()
                    if self._encima == (anillo, i):
                        self._tenir(p, trozo)
            r_chico = T.r_ext + CHICO_R + 3.0
            for j, (clave, angulo) in enumerate(zip(self.huecos.chicos(), self.huecos.angulos_chicos)):
                self._redondo(p, self._pt(c, r_chico, angulo), CHICO_R, clave, 0.6, ("chicos", j))
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
        finally:
            p.end()

    # ---- ratón ------------------------------------------------------------------------------
    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        pos = ev.position()
        if self._pulsado is not None and ev.buttons() & Qt.LeftButton:
            hueco, inicio = self._pulsado
            if (pos - inicio).manhattanLength() >= 8 and self._clave_en(hueco):
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

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        pulsado, self._pulsado = self._pulsado, None
        if pulsado is not None and ev.button() == Qt.LeftButton and pulsado[0][0] in ("dentro", "fuera"):
            self.panel.elegir_boton(pulsado[0])

    def _arrastrar(self, hueco) -> None:
        g, i = hueco
        clave = self._clave_en(hueco)
        key = clave[len(_huecos.EXTERNO):] if _huecos.externo(clave) else PREFIJO + clave
        md = QMimeData()
        md.setData(tipo_arrastre(), QByteArray(json.dumps({"key": key, "origen": f"{CLAVE}:{g}:{i}",
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
        vaciar.setEnabled(bool(self._clave_en(hueco)))
        if m.exec(pos) is not vaciar:
            return
        if g in ("dentro", "fuera"):
            cfg = self.panel.cfg()
            cfg[g][i] = ""
            self.panel.guardar(cfg)
        else:
            self.huecos.vaciar(g, i)

    def dropEvent(self, ev) -> None:  # noqa: N802
        info = self._leer(ev.mimeData())
        hueco = self.hueco_en(ev.position())
        self._encima = None
        self.update()
        if info is None or hueco is None:
            return
        key, origen = str(info["key"]), str(info.get("origen") or "")
        if key == "|":
            self.panel.avisar(_tr("Los separadores no caben en la barra."))
            return
        g, i = hueco
        partes = origen.split(":")
        de_hueco = len(partes) == 3 and partes[0] == CLAVE
        motivo = ""
        if g in ("dentro", "fuera"):
            cfg = self.panel.cfg()
            if de_hueco and partes[1] in ("dentro", "fuera"):
                g0, i0 = partes[1], int(partes[2])
                cfg[g0][i0], cfg[g][i] = cfg[g][i], cfg[g0][i0]
            else:
                clave = _a_clave(key)
                if clave in _huecos.SOLO_EN_OJO:
                    self.panel.avisar(_tr("La rueda, el historial y las texturas solo pueden ir en un ojo."))
                    return
                for anillo in ("dentro", "fuera"):
                    cfg[anillo] = ["" if k == clave else k for k in cfg[anillo]]   # una vez: se mueve
                cfg[g][i] = clave
            self.panel.guardar(cfg)
            self.panel.elegir_boton((g, i))
        elif de_hueco and partes[1] not in ("dentro", "fuera"):
            g0, i0 = partes[1], partes[2]
            if g0 != "ojos":
                i0 = int(i0)
            if (g0, i0) != (g, i):
                motivo = self.huecos.intercambiar(g0, i0, g, i)
        elif not de_hueco:
            motivo = self.huecos.poner(g, i, _a_clave(key))
        else:
            motivo = "Los botones de los anillos no van en los ojos ni en los botoncitos."
        self.panel.avisar(_tr(motivo) if motivo else "")
        ev.acceptProposedAction()


class _EditorSub(QWidget):
    """La subbarra del botón elegido: título, «Por defecto (botón)» y sus
    dos filas (órdenes en rosa, complementos en verde)."""

    def __init__(self, panel) -> None:
        super().__init__(panel)
        self.panel = panel
        self.setObjectName("editor_sub")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#editor_sub { border: 1.5px solid #d62222; border-radius: 8px; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        cabeza = QHBoxLayout()
        self.titulo = QLabel("")
        self.titulo.setWordWrap(True)
        self.titulo.setStyleSheet("color: #e8eaed; font-size: 13px; font-weight: bold; border: none;")
        cabeza.addWidget(self.titulo, 1)
        self.defecto = QPushButton(_tr("Por defecto"))
        self.defecto.setAutoDefault(False)
        self.defecto.clicked.connect(self._por_defecto)
        cabeza.addWidget(self.defecto)
        v.addLayout(cabeza)
        self.filas = _FilasSub(self)
        v.addWidget(self.filas)
        self.nota = QLabel(_tr("Arrastra para ordenar o para pasar de rosa a verde · clic derecho: quitar"))
        self.nota.setWordWrap(True)
        self.nota.setStyleSheet("color: #9aa4ae; font-size: 11px; border: none;")
        v.addWidget(self.nota)

    def refrescar(self) -> None:
        clave = self.panel.clave_elegida()
        if not clave:
            self.titulo.setText(_tr("Haz clic en un botón del anillo para ver su subbarra."))
            self.defecto.hide()
            self.filas.hide()
            self.nota.hide()
            return
        nombre = self.panel.enlace.nombre_clave(clave).split(":")[0]
        self.titulo.setText(_tr("Subbarra de {0}", nombre))
        propia = clave in self.panel.cfg()["sub"]
        self.defecto.setText(_tr("Por defecto ({0})", nombre))
        self.defecto.setVisible(propia)
        self.filas.show()
        self.nota.show()
        self.filas.poner(clave)

    def _por_defecto(self) -> None:
        clave = self.panel.clave_elegida()
        cfg = self.panel.cfg()
        if clave in cfg["sub"]:
            del cfg["sub"][clave]
            self.panel.guardar(cfg)


class _FilasSub(QWidget):
    """Las dos filas de la subbarra, con fichas que se arrastran."""

    LADO, HUECO, TITULO = 62.0, 6.0, 20.0
    ROSA, VERDE = QColor(255, 196, 214), QColor(196, 238, 200)

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self.editor = editor
        self.panel = editor.panel
        self.clave = ""
        self.listas = {"o": [], "c": []}
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        pol = self.sizePolicy()
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)
        self._pulsado = None
        self._destino = None                 # (fila, posición) donde caería lo arrastrado

    # -- datos --
    def _base(self):
        from . import _cadena as C
        cadena = self.panel.enlace.cadena
        try:
            opciones = cadena._opciones_anillo_base(self.clave)
        except Exception:  # noqa: BLE001
            opciones = []
        return opciones, C

    def poner(self, clave) -> None:
        self.clave = clave
        sub = self.panel.cfg()["sub"].get(clave)
        if sub is not None:
            self.listas = {"o": [list(x) for x in sub["o"]], "c": [list(x) for x in sub["c"]]}
        else:
            opciones, C = self._base()
            self.listas = {"o": [], "c": []}
            for o in opciones:
                fila = "c" if C.es_complemento_base(clave, o[0], o[1]) else "o"
                self.listas[fila].append([o[0], o[1]])
        self.setMinimumHeight(self.heightForWidth(max(self.width(), 200)))
        self.updateGeometry()
        self.update()

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        alto = self.heightForWidth(self.width())
        if self.minimumHeight() != alto:
            self.setMinimumHeight(alto)

    def _guardar(self) -> None:
        cfg = self.panel.cfg()
        cfg["sub"][self.clave] = {"o": self.listas["o"], "c": self.listas["c"]}
        self.panel.guardar(cfg)

    def _ficha(self, tipo, valor):
        """(texto, icono, actual) de una opción."""
        opciones, _C = self._base()
        for o in opciones:
            if (o[0], o[1]) == (tipo, valor):
                return str(o[2]).replace("\n", " "), o[3], bool(o[4])
        return self.panel.enlace.nombre_clave(valor).split(":")[0], valor, False

    # -- geometría --
    def _por_fila(self, w) -> int:
        return max(1, int((w - 4.0 + self.HUECO) // (self.LADO + self.HUECO)))

    def _rects(self, w):
        """{(fila, i): rect} de las fichas y del hueco «+» (i = len) de cada
        fila, la y de los títulos y el alto total."""
        n = self._por_fila(w)
        rects, titulos, y = {}, {}, 0.0
        for fila in ("o", "c"):
            titulos[fila] = y
            y += self.TITULO
            total = len(self.listas[fila]) + 1
            for i in range(total):
                col, ren = i % n, i // n
                rects[(fila, i)] = QRectF(2.0 + col * (self.LADO + self.HUECO), y + ren * (self.LADO + self.HUECO),
                                          self.LADO, self.LADO)
            y += ((total - 1) // n + 1) * (self.LADO + self.HUECO) + 4.0
        return rects, titulos, y

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return int(math.ceil(self._rects(w)[2]))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(300, self.heightForWidth(300))

    def _en(self, pos):
        rects, _t, _y = self._rects(self.width())
        for (fila, i), r in rects.items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return fila, i
        return None

    def _destino_en(self, pos):
        """(fila, posición) donde se suelta: antes de la ficha bajo el ratón,
        o al final de la fila más cercana."""
        _rects, titulos, _y = self._rects(self.width())
        hit = self._en(pos)
        if hit is not None:
            return hit
        fila = "c" if pos.y() >= titulos["c"] else "o"
        return fila, len(self.listas[fila])

    # -- dibujo --
    def paintEvent(self, _ev) -> None:  # noqa: N802
        rects, titulos, _y = self._rects(self.width())
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            f = p.font()
            for fila, texto, color in (("o", "Órdenes (rosa)", self.ROSA), ("c", "Complementos (verde)", self.VERDE)):
                f.setPixelSize(12)
                f.setBold(True)
                p.setFont(f)
                p.setPen(color)
                p.drawText(QPointF(2.0, titulos[fila] + 14.0), _tr(texto))
                for i, (tipo, valor) in enumerate(self.listas[fila]):
                    r = rects[(fila, i)]
                    texto_f, icono, actual = self._ficha(tipo, valor)
                    p.setPen(QPen(ROJO if actual else QColor(120, 120, 120), 2.2 if actual else 1.0))
                    p.setBrush(color)
                    p.drawRoundedRect(r, 7, 7)
                    q = QPointF(r.center().x(), r.top() + 25.0)
                    if not (icono and _iconos.pintar(p, icono, q, 30.0)) and _huecos.externo(icono):
                        _iconos.letra(p, icono, q, 30.0)
                    f.setPixelSize(9)
                    f.setBold(False)
                    p.setFont(f)
                    p.setPen(QColor(40, 40, 40))
                    p.drawText(QRectF(r.left() + 1, r.bottom() - 18, r.width() - 2, 16), Qt.AlignCenter,
                               p.fontMetrics().elidedText(texto_f, Qt.ElideRight, int(r.width() - 4)))
                    if self._destino == (fila, i):
                        p.setPen(QPen(ROJO, 3.0))
                        p.drawLine(QPointF(r.left() - 4, r.top()), QPointF(r.left() - 4, r.bottom()))
                n = len(self.listas[fila])
                r = rects[(fila, n)]
                p.setPen(QPen(ROJO if self._destino == (fila, n) else QColor(150, 160, 170), 1.4, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, 7, 7)
                p.setPen(QColor(150, 160, 170))
                f.setPixelSize(20)
                p.setFont(f)
                p.drawText(QRectF(r.left(), r.top(), r.width(), r.height() - 16), Qt.AlignCenter, "+")
                f.setPixelSize(9)
                p.setFont(f)
                p.drawText(QRectF(r.left(), r.bottom() - 18, r.width(), 16), Qt.AlignCenter, _tr("arrastra aquí"))
        finally:
            p.end()

    # -- ratón --
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        hit = self._en(ev.position())
        if hit is None:
            return
        fila, i = hit
        if ev.button() == Qt.LeftButton and i < len(self.listas[fila]):
            self._pulsado = (hit, ev.position())
        elif ev.button() == Qt.RightButton:
            self._menu(fila, i, ev.globalPosition().toPoint())

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._pulsado is not None and ev.buttons() & Qt.LeftButton:
            (fila, i), inicio = self._pulsado
            if (ev.position() - inicio).manhattanLength() >= 8:
                self._pulsado = None
                md = QMimeData()
                md.setData(_MIME_SUB, QByteArray(f"{fila}:{i}".encode("utf-8")))
                drag = QDrag(self)
                drag.setMimeData(md)
                drag.exec(Qt.MoveAction)
                return
        hit = self._en(ev.position())
        if hit is not None and hit[1] < len(self.listas[hit[0]]):
            texto, _ic, _a = self._ficha(*self.listas[hit[0]][hit[1]])
            QToolTip.showText(ev.globalPosition().toPoint(), texto, self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, _ev) -> None:  # noqa: N802
        self._pulsado = None

    def _menu(self, fila, i, pos) -> None:
        m = QMenu(self)
        quitar = None
        if i < len(self.listas[fila]):
            quitar = m.addAction(_tr("Quitar «{0}» de la subbarra", self._ficha(*self.listas[fila][i])[0]))
        opciones, _C = self._base()
        puestas = {tuple(x) for x in self.listas["o"] + self.listas["c"]}
        faltan = [(o[0], o[1]) for o in opciones if (o[0], o[1]) not in puestas]
        volver = {}
        if faltan:
            m.addSeparator()
            sub = m.addMenu(_tr("Volver a poner"))
            for t, v in faltan:
                volver[sub.addAction(self._ficha(t, v)[0])] = [t, v]
        elegida = m.exec(pos)
        if elegida is None:
            return
        if elegida is quitar:
            del self.listas[fila][i]
        elif elegida in volver:
            self.listas[fila].insert(min(i, len(self.listas[fila])), volver[elegida])
        else:
            return
        self._guardar()

    # -- soltar --
    def _acepta(self, md) -> bool:
        return md.hasFormat(_MIME_SUB) or _Lienzo._leer(md) is not None

    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        if self._acepta(ev.mimeData()):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:  # noqa: N802
        if not self._acepta(ev.mimeData()):
            ev.ignore()
            return
        destino = self._destino_en(ev.position())
        if destino != self._destino:
            self._destino = destino
            self.update()
        ev.acceptProposedAction()

    def dragLeaveEvent(self, _ev) -> None:  # noqa: N802
        self._destino = None
        self.update()

    def dropEvent(self, ev) -> None:  # noqa: N802
        md = ev.mimeData()
        fila, pos = self._destino_en(ev.position())
        self._destino = None
        if md.hasFormat(_MIME_SUB):
            f0, i0 = bytes(md.data(_MIME_SUB)).decode("utf-8").split(":")
            i0 = int(i0)
            if f0 not in self.listas or not 0 <= i0 < len(self.listas[f0]):
                return
            entrada = self.listas[f0].pop(i0)
            if f0 == fila and i0 < pos:
                pos -= 1
            self.listas[fila].insert(min(pos, len(self.listas[fila])), entrada)
        else:
            info = _Lienzo._leer(md)
            key = str(info["key"])
            if key == "|":
                return
            clave = _a_clave(key)
            if clave in _huecos.SOLO_EN_OJO:
                self.panel.avisar(_tr("La rueda, el historial y las texturas solo pueden ir en un ojo."))
                return
            self.listas[fila].insert(min(pos, len(self.listas[fila])), ["accion", clave])
        ev.acceptProposedAction()
        self._guardar()

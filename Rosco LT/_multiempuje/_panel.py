# SPDX-License-Identifier: GPL-3.0-or-later
"""Panel lateral de Multiempuje (pestaña junto a Propiedades/BIM/Capas).

Una sola estructura: movimiento (Juntas, Una dirección, Cada cara), distancia y acabado; las
opciones del movimiento activo; «Más opciones» plegado (bordes nuevos, selección, plano destino,
grupo, rematado, desmoldeo, aleatorio) y el uso."""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QRadioButton, QScrollArea, QSizePolicy, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import _algo as A
from . import _settings as S
from ._ayuda import Ayudas
from ._i18n import _t, descripcion, uso
from ._icons import mode_icon
from ._voz import con_microfono

log = logging.getLogger("ingetrazo.plugins.multiempuje")

ICONO_MOV = {"juntas": "conjunto", "direccion": "vector", "cada_cara": "normal"}
NOMBRE_MOV = {"juntas": "Juntas", "direccion": "Una dirección", "cada_cara": "Cada cara"}


def _num(texto, defecto=None):
    try:
        return float(str(texto).replace(",", ".").replace("%", "").replace("°", "").strip())
    except (TypeError, ValueError):
        return defecto


def _fmt_num(v, suf=""):
    s = f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s} {suf}".strip()


def _fmt_len(m):
    try:
        from core.units import fmt_len
        return fmt_len(m)
    except Exception:  # noqa: BLE001
        return f"{m:.3f} m"


def _leer_len(texto):
    try:
        from core.units import parse_length_field
        v = parse_length_field(texto)
        if v is not None:
            return float(v)
    except Exception:  # noqa: BLE001
        pass
    return _num(texto)


class Seccion(QWidget):
    """Cabecera plegable («▾ Título») con su contenido debajo."""

    def __init__(self, titulo, parent=None, abierta=True):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.titulo = titulo
        self.boton = QToolButton()
        self.boton.setCheckable(True)
        self.boton.setChecked(abierta)
        self.boton.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.boton.setStyleSheet("QToolButton{font-weight:bold;padding:5px;border-radius:3px;}")
        self.boton.toggled.connect(self._plegar)
        lay.addWidget(self.boton)
        self.cuerpo = QWidget()
        self.lay = QVBoxLayout(self.cuerpo)
        self.lay.setContentsMargins(4, 0, 4, 4)
        self.lay.setSpacing(6)
        lay.addWidget(self.cuerpo)
        self._plegar(abierta)

    def set_titulo(self, titulo):
        self.titulo = titulo
        self._plegar(self.boton.isChecked())

    def _plegar(self, abierto):
        self.boton.setText(("▾  " if abierto else "▸  ") + self.titulo)
        self.cuerpo.setVisible(abierto)


def campo(texto="", ayuda=None):
    e = QLineEdit(texto)
    e.setMinimumHeight(28)
    con_microfono(e, _t("Dictar por voz"))
    if ayuda:
        e.setToolTip(ayuda)
    return e


def _boton(texto, color=None, ayuda=None):
    b = QToolButton()
    b.setText(texto)
    b.setCheckable(True)
    b.setMinimumHeight(28)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    if ayuda:
        b.setToolTip(ayuda)
    if color:
        b.setStyleSheet(f"QToolButton{{font-weight:bold;color:{color};}}")
    return b


class Panel(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self._cargando = False
        self.ayudas = Ayudas(self)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        # ---- las acciones, siempre a la vista
        fila = QHBoxLayout()
        fila.setContentsMargins(6, 6, 6, 2)
        fila.setSpacing(8)
        b = QPushButton(_t("Comenzar  (Enter)"))
        b.setToolTip("Empuja las caras elegidas la distancia indicada.")
        b.clicked.connect(self.ctrl.aplicar_panel)
        fila.addWidget(b, 1)
        b = QPushButton(_t("Deshacer el último  (Retroceso)"))
        b.setToolTip("Deshace el último empuje y deja otra vez elegidas las caras originales.")
        b.clicked.connect(self.ctrl.deshacer_ultimo)
        fila.addWidget(b, 1)
        self.b_plegar = QToolButton()
        self.b_plegar.setToolTip(_t("Pliega o despliega todas las secciones"))
        self.b_plegar.clicked.connect(self._plegar_todo)
        fila.addWidget(self.b_plegar)
        raiz.addLayout(fila)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        raiz.addWidget(scroll)
        self.scroll = scroll
        cont = QWidget()
        scroll.setWidget(cont)
        v = QVBoxLayout(cont)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(8)

        # ---- movimiento, distancia y acabado
        s = Seccion(_t("Multiempuje"))
        g = QGridLayout()
        g.setVerticalSpacing(8)
        g.addWidget(QLabel(_t("Movimiento:")), 0, 0)
        hb = QHBoxLayout()
        hb.setSpacing(4)
        self.grupo_mov = QButtonGroup(self)
        self.grupo_mov.setExclusive(True)
        self.botones = {}
        for i, m in enumerate(S.MOVIMIENTOS):
            b = QToolButton()
            b.setIcon(mode_icon(ICONO_MOV[m], 64))
            b.setIconSize(QSize(34, 34))
            b.setText(_t(NOMBRE_MOV[m]))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setMinimumSize(QSize(90, 62))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet("QToolButton{font-size:11px;}")
            b.setToolTip(f"{descripcion(m)}  ({_t('tecla')} {i + 1})")
            b.clicked.connect(lambda _c=False, mm=m: self.ctrl.set_movimiento(mm))
            self.grupo_mov.addButton(b)
            self.botones[m] = b
            hb.addWidget(b)
        g.addLayout(hb, 0, 1, 1, 2)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#c8c8cc")
        g.addWidget(self.desc, 1, 1, 1, 2)
        g.addWidget(QLabel(_t("Distancia:")), 2, 0)
        self.distancia = campo("", "Distancia para «Comenzar» y Enter (en las unidades del modelo). Negativa = hacia dentro.")
        self.distancia.editingFinished.connect(self._distancia)
        g.addWidget(self.distancia, 2, 1, 1, 2)
        g.addWidget(QLabel(_t("Acabado:")), 3, 0)
        self.r_push = QRadioButton(_t("Empujar (borra la original)"))
        self.r_thick = QRadioButton(_t("Engrosar (la conserva)"))
        self.r_push.setToolTip("Empujar/tirar clásico. Hacia dentro de un sólido recorta sus caras y puede abrir un hueco pasante.")
        self.r_thick.setToolTip("Da grosor: conserva la cara original (sólido cerrado). Ctrl mantenido invierte el acabado.")
        self.r_push.toggled.connect(lambda on: on and self._set("finishing", "push"))
        self.r_thick.toggled.connect(lambda on: on and self._set("finishing", "thicken"))
        g.addWidget(self.r_push, 3, 1)
        g.addWidget(self.r_thick, 3, 2)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        s.lay.addLayout(g)
        v.addWidget(s)

        # ---- opciones del movimiento activo
        self.s_mov = Seccion("")
        self.paginas = QStackedWidget()
        self.pag = {}
        for m in S.MOVIMIENTOS:
            w = QWidget()
            lay = QGridLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setVerticalSpacing(8)
            self._pagina(m, lay)
            self.paginas.addWidget(w)
            self.pag[m] = w
        self.s_mov.lay.addWidget(self.paginas)
        v.addWidget(self.s_mov)

        # ---- más opciones (plegado)
        self.s_mas = Seccion(_t("Más opciones"), abierta=False)
        g = QGridLayout()
        g.setVerticalSpacing(8)
        g.addWidget(QLabel(_t("Bordes nuevos:")), 0, 0)
        self.bordes = QComboBox()
        for k, t in (("contour", "Contorno (solo el perímetro)"), ("grid", "Cuadrícula (uno por cara)"), ("none", "Ninguno")):
            self.bordes.addItem(_t(t), k)
        self.bordes.setToolTip("Caras laterales nuevas: solo en el contorno, una por cada arista de cada cara, o ninguna.")
        self.bordes.currentIndexChanged.connect(lambda _i: self._set("borders", self.bordes.currentData()))
        g.addWidget(self.bordes, 0, 1, 1, 2)
        g.addWidget(QLabel(_t("Selección:")), 1, 0)
        self.selmodo = QComboBox()
        for k, t in (("surface", "Superficie (caras unidas por aristas suaves)"), ("single", "Individual"),
                     ("material", "Mismo material"), ("all", "Todas las unidas")):
            self.selmodo.addItem(_t(t), k)
        self.selmodo.setToolTip("Qué se elige al pasar el ratón por una cara (Tab lo cambia).")
        self.selmodo.currentIndexChanged.connect(lambda _i: self._set("sel_mode", self.selmodo.currentData(), rehacer=False))
        g.addWidget(self.selmodo, 1, 1, 1, 2)
        g.addWidget(QLabel(_t("Plano destino:")), 2, 0)
        hp = QHBoxLayout()
        self.plano_txt = QLabel(_t("ninguno"))
        hp.addWidget(self.plano_txt, 1)
        b = QPushButton(_t("Elegir en el dibujo…"))
        b.setToolTip("El siguiente clic en una cara (también de un grupo cerrado) o en un plano de sección fija el plano "
                     "hasta el que llegarán las caras empujadas.")
        b.clicked.connect(self.ctrl.pedir_plano)
        self.b_plano = b
        hp.addWidget(b)
        b = QPushButton(_t("Quitar"))
        b.clicked.connect(lambda: self.ctrl.set_plano(None))
        hp.addWidget(b)
        g.addLayout(hp, 2, 1, 1, 2)
        self.grupo = QCheckBox(_t("Crear el resultado en un grupo"))
        self.grupo.setToolTip("La geometría original no se toca; el resultado va a un grupo nuevo.")
        self.grupo.toggled.connect(lambda on: self._set("gen_group", bool(on)))
        g.addWidget(self.grupo, 3, 1, 1, 2)
        self.taper_on = QCheckBox(_t("Rematado (estrechar la cara superior)"))
        self.taper_on.setToolTip("Escala la cara superior respecto a su centro (Una dirección y Cada cara).")
        self.taper_on.toggled.connect(lambda on: self._set("taper_on", bool(on)))
        self.taper = campo("", "Tamaño de la cara superior, en % de la original")
        self.taper.editingFinished.connect(lambda: self._num_set(self.taper, "taper_pct", 1.0, 500.0, "%"))
        g.addWidget(self.taper_on, 4, 0, 1, 2)
        g.addWidget(self.taper, 4, 2)
        self.mold_on = QCheckBox(_t("Desmoldeo (inclinar los bordes)"))
        self.mold_on.setToolTip("Inclina los bordes respecto a la normal: la cara superior crece (ángulo +) o mengua (ángulo −). "
                                "No actúa con borde «siguiendo las vecinas» ni con redondeo.")
        self.mold_on.toggled.connect(lambda on: self._set("molding_on", bool(on)))
        self.mold = campo("", "Ángulo de desmoldeo en grados")
        self.mold.editingFinished.connect(lambda: self._num_set(self.mold, "molding_angle", -80.0, 80.0, "°"))
        g.addWidget(self.mold_on, 5, 0, 1, 2)
        g.addWidget(self.mold, 5, 2)
        self.rand_on = QCheckBox(_t("Aleatorio  mín / máx"))
        self.rand_on.setToolTip("Cada cara (Cada cara) o cada bloque de caras unidas (Juntas, Una dirección) se empuja la distancia "
                                "por un factor al azar entre mín y máx.")
        self.rand_on.toggled.connect(lambda on: self._set("random_on", bool(on)))
        hr = QHBoxLayout()
        self.rmin = campo("", "Factor mínimo")
        self.rmin.editingFinished.connect(lambda: self._num_set(self.rmin, "rmin", 0.0, 100.0))
        self.rmax = campo("", "Factor máximo")
        self.rmax.editingFinished.connect(lambda: self._num_set(self.rmax, "rmax", 0.0, 100.0))
        hr.addWidget(self.rmin)
        hr.addWidget(self.rmax)
        for sim, paso, ayuda in (("◀", -1, "Patrón aleatorio anterior"), ("▶", 1, "Patrón aleatorio siguiente")):
            bt = QPushButton(sim)
            bt.setFixedWidth(30)
            bt.setToolTip(_t(ayuda))
            bt.clicked.connect(lambda _c=False, p=paso: self._semilla(p))
            hr.addWidget(bt)
        g.addWidget(self.rand_on, 6, 0)
        g.addLayout(hr, 6, 1, 1, 2)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        self.s_mas.lay.addLayout(g)
        self.nota_mas = QLabel()
        self.nota_mas.setWordWrap(True)
        self.nota_mas.setStyleSheet("color:#8a8a92")
        self.s_mas.lay.addWidget(self.nota_mas)
        v.addWidget(self.s_mas)

        # ---- uso
        s = Seccion(_t("Uso"))
        ayuda = QLabel(uso())
        ayuda.setWordWrap(True)
        s.lay.addWidget(ayuda)
        self.chk_ayudas = QCheckBox(_t("Mostrar ayudas con imagen al pasar el ratón por las opciones"))
        self.chk_ayudas.toggled.connect(lambda on: self._set("ayudas", bool(on), rehacer=False))
        s.lay.addWidget(self.chk_ayudas)
        v.addWidget(s)
        v.addStretch(1)
        self.secciones = cont.findChildren(Seccion)
        for sec in self.secciones:
            sec.boton.toggled.connect(self._texto_plegar)
        self._texto_plegar()
        # La rueda desplaza el panel; nunca cambia un desplegable por descuido.
        for combo in self.findChildren(QComboBox):
            combo.installEventFilter(self)
        self._ayudas()
        self.refrescar()

    def eventFilter(self, obj, ev):  # noqa: N802 — nombre de Qt
        if ev.type() == QEvent.Wheel and isinstance(obj, QComboBox):
            QApplication.sendEvent(self.scroll.verticalScrollBar(), ev)
            return True
        return super().eventFilter(obj, ev)

    def _texto_plegar(self, _c=False):
        algo = any(sec.boton.isChecked() for sec in self.secciones)
        self.b_plegar.setText(_t("Plegar todo") if algo else _t("Desplegar todo"))

    def _plegar_todo(self):
        abrir = not any(sec.boton.isChecked() for sec in self.secciones)
        for sec in self.secciones:
            sec.boton.setChecked(abrir)

    def _ayudas(self):
        """Asocia a cada opción su ilustración (o las de todos sus valores)."""
        a = self.ayudas
        for m, b in self.botones.items():
            a.registrar(b, {"juntas": "mov_juntas", "direccion": "mov_direccion", "cada_cara": "mov_cada_cara"}[m])
        a.registrar(self.r_push, "acabado_push")
        a.registrar(self.r_thick, "acabado_thicken")
        a.registrar(self.borde, ["borde_inglete", "borde_seguir", "borde_promedio"])
        a.registrar(self.redondear, "redondear")
        for k, b in self.dir_btn.items():
            a.registrar(b, {"normal": "dir_normal", "media": "dir_media", "custom": "dir_custom"}.get(k, "dir_eje"))
        a.registrar(self.plana, "plana")
        a.registrar(self.coquad, "coquad")
        a.registrar(self.bordes, ["bordes_contorno", "bordes_cuadricula", "bordes_ninguno"])
        a.registrar(self.selmodo, ["sel_surface", "sel_single", "sel_material", "sel_all"])
        a.registrar(self.b_plano, "plano")
        a.registrar(self.grupo, "grupo")
        a.registrar(self.taper_on, "rematado")
        a.registrar(self.mold_on, "desmoldeo")
        a.registrar(self.rand_on, "aleatorio")

    # ---- páginas de opciones por movimiento
    def _pagina(self, m, lay):
        if m == "juntas":
            lay.addWidget(QLabel(_t("Borde exterior:")), 0, 0)
            self.borde = QComboBox()
            for k, t in (("inglete", "En inglete (cada cara a su distancia)"),
                         ("seguir", "Siguiendo las caras vecinas (p. ej. un tejado entre paredes)"),
                         ("promedio", "Promediado con las caras vecinas")):
                self.borde.addItem(_t(t), k)
            self._borde_tip = ("Cómo se mueven los vértices del contorno: en inglete con las caras elegidas, resbalando por las "
                               "aristas de las caras vecinas no elegidas, o promediando sus normales con las vecinas.")
            self.borde.setToolTip(self._borde_tip)
            self.borde.currentIndexChanged.connect(lambda _i: self._set("borde", self.borde.currentData()))
            lay.addWidget(self.borde, 0, 1, 1, 3)
            self.redondear = QCheckBox(_t("Redondear las aristas salientes"))
            self.redondear.setToolTip("Tiras cilíndricas en las aristas salientes y esquinas esféricas.")
            self.redondear.toggled.connect(lambda on: self._set("redondear", bool(on)))
            lay.addWidget(self.redondear, 1, 0, 1, 2)
            self.lab_ang = QLabel(_t("ángulo mín."))
            lay.addWidget(self.lab_ang, 1, 2)
            self.ang_round = campo("", "Ángulo mínimo entre dos caras para redondear su arista")
            self.ang_round.editingFinished.connect(lambda: self._num_set(self.ang_round, "angle_round", 0.5, 179.0, "°"))
            lay.addWidget(self.ang_round, 1, 3)
            self.lab_seg = QLabel(_t("segmentos por 90°"))
            lay.addWidget(self.lab_seg, 2, 2)
            self.seg_round = campo("", "Número de segmentos por cada 90° de redondeo")
            self.seg_round.editingFinished.connect(lambda: self._num_set(self.seg_round, "segment_round", 1, 64, entero=True))
            lay.addWidget(self.seg_round, 2, 3)
            lay.setColumnStretch(1, 1)
        elif m == "direccion":
            lay.addWidget(QLabel(_t("Dirección:")), 0, 0)
            self.dir_grupo = QButtonGroup(self)
            self.dir_grupo.setExclusive(True)
            self.dir_btn = {}
            filas = ((("normal", "Normal de la cara", None, "La normal de la cara en la que empiezas a arrastrar"),
                      ("media", "Media del conjunto", None, "La normal media (ponderada por áreas) de las caras elegidas: extrusión compacta"),
                      ("custom", "Personalizada", "#e88c30", "La dirección tomada del dibujo o tecleada")),
                     (("x", "X", "#e05050", "Eje X (rojo) · tecla →"),
                      ("y", "Y", "#4cc46a", "Eje Y (verde) · tecla ←"),
                      ("z", "Z", "#5a96ff", "Eje Z (azul) · tecla ↑")))
            for fila, defs in enumerate(filas):
                hb = QHBoxLayout()
                hb.setSpacing(3)
                for k, t, col, ayuda in defs:
                    b = _boton(_t(t), col, ayuda)
                    b.clicked.connect(lambda _c=False, kk=k: self.ctrl.set_direccion(kk))
                    self.dir_grupo.addButton(b)
                    self.dir_btn[k] = b
                    hb.addWidget(b)
                if fila == 1:
                    b = QPushButton(_t("Elegir en el dibujo…"))
                    b.setMinimumHeight(28)
                    b.setToolTip("Pasa el ratón por una arista, una cara, una guía o un eje del modelo (también de grupos cerrados) "
                                 "y haz clic para tomar su dirección.")
                    b.clicked.connect(self.ctrl.pedir_direccion)
                    hb.addWidget(b, 2)
                lay.addLayout(hb, fila, 1, 1, 3)
            self.vcustom_lab = QLabel("")
            self.vcustom_lab.setWordWrap(True)
            lay.addWidget(self.vcustom_lab, 2, 1, 1, 3)
            lay.addWidget(QLabel(_t("Teclear:")), 3, 0)
            self.vcustom = campo("", "Dirección personalizada: tres números separados por ; o , (por ejemplo 0 ; 0,71 ; 0,71)")
            self.vcustom.editingFinished.connect(self._vector_tecleado)
            lay.addWidget(self.vcustom, 3, 1, 1, 3)
            self.vlocal = QCheckBox(_t("Usar los ejes del grupo abierto (locales) para X, Y y Z"))
            self.vlocal.setToolTip("Dentro de un componente o grupo girado, X, Y y Z son sus propios ejes. Tab durante el arrastre lo cambia.")
            self.vlocal.toggled.connect(lambda on: self._set("vector_local", bool(on)))
            lay.addWidget(self.vlocal, 4, 0, 1, 4)
            self.plana = QCheckBox(_t("Cara superior plana (proyectada sobre un plano)"))
            self.plana.setToolTip("Las caras superiores quedan en un plano perpendicular a la dirección.")
            self.plana.toggled.connect(lambda on: self._set("plana", bool(on)))
            lay.addWidget(self.plana, 5, 0, 1, 4)
            ayuda = QLabel("<i>" + _t("Teclas: → X · ← Y · ↑ Z · ↓ normal (la misma flecha otra vez vuelve a Normal).") + "</i>")
            ayuda.setWordWrap(True)
            ayuda.setStyleSheet("color:#8a8a92")
            lay.addWidget(ayuda, 6, 0, 1, 4)
            lay.setColumnStretch(1, 1)
        else:
            self.coquad = QCheckBox(_t("Mantener unidos los triángulos que forman un cuadrilátero"))
            self.coquad.setToolTip("Dos triángulos casi coplanarios que forman un cuadrilátero se empujan como una sola cara.")
            self.coquad.toggled.connect(lambda on: self._set("coquad", bool(on)))
            lay.addWidget(self.coquad, 0, 0, 1, 4)
            lay.setColumnStretch(1, 1)

    # ---- cambios
    def _set(self, k, v, rehacer=True):
        if self._cargando:
            return
        self.ctrl.cambio(k, v, rehacer=rehacer)

    def _num_set(self, edit, k, lo, hi, suf="", entero=False):
        if self._cargando:
            return
        v = _num(edit.text())
        if v is None:
            self.refrescar()
            return
        v = max(lo, min(hi, v))
        if entero:
            v = int(round(v))
        if v == self.ctrl.opc.get(k):
            edit.setText(_fmt_num(v, suf))
            return
        edit.setText(_fmt_num(v, suf))
        self.ctrl.cambio(k, v)

    def _distancia(self):
        if self._cargando:
            return
        t = self.distancia.text().strip()
        if not t:
            return
        v = _leer_len(t)
        if v is None:
            self.refrescar()
            return
        if abs(v - float(self.ctrl.opc.get("distancia") or 0.0)) < 1e-12:
            return
        self.ctrl.cambio("distancia", v, rehacer=False)
        self.distancia.setText(_fmt_len(v))
        self.ctrl.distancia_tecleada(v)

    def _semilla(self, paso):
        s = int(self.ctrl.opc.get("seed") or 0) + paso
        self.ctrl.cambio("seed", s)

    def _vector_tecleado(self):
        if self._cargando:
            return
        t = self.vcustom.text().strip()
        if not t:
            return
        partes = [p for p in t.replace(";", " ").replace(",", ".").split() if p]
        try:
            v = tuple(float(p) for p in partes)
        except ValueError:
            v = ()
        if len(v) != 3:
            self.refrescar()
            try:
                self.ctrl.app.viewport.flash_status("Teclea tres números: x ; y ; z", 3000)
            except Exception:  # noqa: BLE001
                pass
            return
        actual = self.ctrl.opc.get("vector_custom")
        n = A.norm(v)
        if n and actual and all(abs(a - b) < 1e-6 for a, b in zip(n, actual)) and self.ctrl.opc.get("direccion") == "custom":
            return
        self.ctrl.set_vector_custom(v, _t("tecleada"))

    # ---- mostrar valores
    def refrescar(self):
        self._cargando = True
        try:
            o = self.ctrl.opc
            m = o.movimiento
            for k, b in self.botones.items():
                b.setChecked(k == m)
            self.desc.setText(descripcion(m))
            d = float(o.get("distancia") or 0.0)
            self.distancia.setText(_fmt_len(d) if abs(d) > 1e-12 else "")
            self.r_push.setChecked(o.get("finishing") == "push")
            self.r_thick.setChecked(o.get("finishing") == "thicken")
            # página del movimiento
            self.s_mov.set_titulo(_t("Opciones de «{m}»", m=_t(NOMBRE_MOV[m])))
            for k, w in self.pag.items():
                w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if k == m else QSizePolicy.Ignored)
            self.paginas.setCurrentWidget(self.pag[m])
            self.paginas.adjustSize()
            self.borde.setCurrentIndex(max(0, self.borde.findData(o.get("borde"))))
            red = bool(o.get("redondear"))
            self.redondear.setChecked(red)
            self.ang_round.setText(_fmt_num(float(o.get("angle_round")), "°"))
            self.seg_round.setText(str(int(o.get("segment_round"))))
            for w in (self.lab_ang, self.ang_round, self.lab_seg, self.seg_round):
                w.setEnabled(red)
            self.borde.setEnabled(not red)
            self.borde.setToolTip("Con redondeo, el borde va siempre en inglete." if red else self._borde_tip)
            dd = o.get("direccion")
            for k, b in self.dir_btn.items():
                b.setChecked(k == dd)
            vc = o.get("vector_custom")
            if vc:
                txt = " · ".join(f"{float(k):.2f}".replace(".", ",") for k in vc)
                ori = self.ctrl.custom_origen
                self.vcustom_lab.setText(f"{_t('Personalizada')}: <b>({txt})</b>" + (f" — {ori}" if ori else ""))
                self.vcustom.setText(" ; ".join(f"{float(k):.3f}".rstrip("0").rstrip(".").replace(".", ",") for k in vc))
            else:
                self.vcustom_lab.setText("<i>" + _t("Sin dirección personalizada: elígela en el dibujo o tecléala.") + "</i>")
                self.vcustom.setText("")
            self.vlocal.setChecked(bool(o.get("vector_local")))
            self.plana.setChecked(bool(o.get("plana")))
            self.coquad.setChecked(bool(o.get("coquad")))
            # más opciones
            self.bordes.setCurrentIndex(max(0, self.bordes.findData(o.get("borders"))))
            self.selmodo.setCurrentIndex(max(0, self.selmodo.findData(o.get("sel_mode"))))
            self.grupo.setChecked(bool(o.get("gen_group")))
            pl = self.ctrl.plano
            self.plano_txt.setText(_t("ninguno") if pl is None else
                                   f"z {_fmt_len(pl[0][2])} · normal ({pl[1][0]:.2f}, {pl[1][1]:.2f}, {pl[1][2]:.2f})")
            self.taper_on.setChecked(bool(o.get("taper_on")))
            self.taper.setText(_fmt_num(float(o.get("taper_pct")), "%"))
            self.mold_on.setChecked(bool(o.get("molding_on")))
            self.mold.setText(_fmt_num(float(o.get("molding_angle")), "°"))
            self.rand_on.setChecked(bool(o.get("random_on")))
            self.rmin.setText(_fmt_num(float(o.get("rmin"))))
            self.rmax.setText(_fmt_num(float(o.get("rmax"))))
            modo = o.modo
            taper_ok = modo in ("extruir", "vector", "normal")
            mold_ok = modo in ("conjunto", "extruir", "vector", "normal")
            for w in (self.taper_on, self.taper):
                w.setEnabled(taper_ok)
            for w in (self.mold_on, self.mold):
                w.setEnabled(mold_ok)
            notas = []
            if not taper_ok:
                notas.append(_t("el rematado solo actúa en «Una dirección» y «Cada cara»"))
            if not mold_ok:
                notas.append(_t("el desmoldeo no actúa con borde «siguiendo las vecinas» ni con redondeo"))
            notas.append(_t("los grupos y componentes se abren solos al hacer clic en sus caras"))
            self.nota_mas.setText("<i>" + " · ".join(notas) + "</i>")
            self.chk_ayudas.setChecked(bool(o.get("ayudas")))
            self.ayudas.activas = bool(o.get("ayudas"))
        finally:
            self._cargando = False

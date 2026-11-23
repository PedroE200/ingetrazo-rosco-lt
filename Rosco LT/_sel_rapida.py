# SPDX-License-Identifier: GPL-3.0-or-later
"""Selección rápida (3.1.0): seleccionar o quitar de la selección según
criterios, en una ventana con dos pestañas.

* «Por tipo»: tipos de objeto (guías, aristas, caras, grupos, componentes,
  cotas, textos, imágenes, planos de sección y curvas) y filtros por nombre
  de grupo o de componente, etiqueta y material.
* «Por medida»: un tipo de objeto, una propiedad (longitud, radio,
  diámetro, área, perímetro, volumen, etiqueta o material), una comparación
  y un valor (o dos, con «entre»).

Se busca en lo que se ve abierto: el modelo o, con un grupo abierto, dentro
de él (lo mismo que «Seleccionar todo» de IngeTrazo). Lo oculto, lo
bloqueado y lo de etiquetas ocultas o bloqueadas no cuenta."""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QAbstractSpinBox, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ._idioma import _tr

from ._ajustes import registro

log = registro()
ROJO = "#b01b1b"
AZUL_SEL = QColor(42, 127, 212)
CUALQUIERA = "Cualquiera"
POR_DEFECTO = "— Por defecto —"
MAX_LADOS_POLIGONO = 12             # una curva cerrada regular con 12 lados o menos: polígono

MODOS = (("nueva", "Nueva"), ("anadir", "Añadir a la actual"), ("quitar", "Quitar de la actual"))
TIPOS = (("punto_guia", "Punto guía"), ("linea_guia", "Línea guía"),
         ("arista", "Arista"), ("cara", "Cara"),
         ("grupo", "Grupo"), ("componente", "Componente"),
         ("cota", "Cota"), ("texto", "Texto"),
         ("imagen", "Imagen"), ("seccion", "Plano de sección"),
         ("curva", "Curva"))
TIPOS_MEDIDA = (("arista", "Arista"), ("arco", "Arco"), ("circulo", "Círculo"), ("poligono", "Polígono"),
                ("curva", "Curva"), ("cara", "Cara"), ("grupo", "Grupo"), ("componente", "Componente"))
PROPIEDADES = {"arista": ("longitud",), "arco": ("radio", "diametro", "longitud"),
               "circulo": ("radio", "diametro", "longitud"), "poligono": ("radio", "longitud"),
               "curva": ("longitud",), "cara": ("area", "perimetro"),
               "grupo": ("volumen",), "componente": ("volumen",)}
TEXTO_PROP = {"longitud": "Longitud", "radio": "Radio", "diametro": "Diámetro", "area": "Área",
              "perimetro": "Perímetro", "volumen": "Volumen", "etiqueta": "Etiqueta", "material": "Material"}
COMPARACIONES = (("<", "<"), ("<=", "≤"), (">", ">"), (">=", "≥"), ("==", "="), ("!=", "≠"), ("entre", "entre"))

ESTILO = f"""
QWidget#selrap {{ background: #f7f7f5; color: #2c2c2a; }}
QWidget#selrap QLabel, QWidget#selrap QCheckBox {{ color: #2c2c2a; background: transparent; }}
QWidget#selrap QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid #888;
    border-radius: 2px; background: white; }}
QWidget#selrap QCheckBox::indicator:checked {{ background: {ROJO}; border-color: {ROJO}; }}
QWidget#selrap QComboBox, QWidget#selrap QLineEdit {{ background: white; color: #2c2c2a;
    border: 1px solid #aaa; border-radius: 4px; padding: 2px 6px; min-height: 18px; }}
QWidget#selrap QComboBox:focus, QWidget#selrap QLineEdit:focus {{ border-color: {ROJO}; }}
QWidget#selrap QComboBox QAbstractItemView {{ background: white; color: #2c2c2a;
    selection-background-color: #fde2e2; selection-color: {ROJO}; }}
QPushButton#modo, QPushButton#boton {{ color: #2c2c2a; }}
QFrame#grupo {{ background: #ffffff; border: 1px solid #d6d6d0; border-radius: 6px; }}
QLabel#titulo {{ color: #77756e; font-size: 11px; font-weight: 600; }}
QPushButton#pestana {{ padding: 5px 16px; border: 1px solid #bbb; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; background: #e6e6e2; color: #555; }}
QPushButton#pestana:checked {{ background: {ROJO}; color: white; border-color: {ROJO}; }}
QPushButton#pestana:hover:!checked {{ background: #f3d9d9; }}
QPushButton#modo {{ padding: 3px 10px; border: 1px solid #bbb; background: white; }}
QPushButton#modo:checked {{ background: #fde2e2; color: {ROJO}; font-weight: 600; border-color: {ROJO}; }}
QPushButton#boton {{ padding: 3px 10px; border: 1px solid #bbb; border-radius: 5px; background: white; }}
QPushButton#boton:hover {{ background: #fadede; }}
QPushButton#aplicar {{ padding: 4px 14px; border: 1px solid {ROJO}; border-radius: 5px; background: {ROJO};
    color: white; font-weight: 600; }}
QFrame#raya {{ background: {ROJO}; max-height: 2px; min-height: 2px; }}
QWidget#selrap QLabel#ayuda {{ background: #dfe7f3; color: #2a5ea8; border-radius: 8px; font-weight: 700; }}
"""


# -- lo que hay en el contexto abierto --------------------------------------------------------
def _llamar(x):
    return x() if callable(x) else x


def _visible(scene, e) -> bool:
    try:
        return bool(scene.entity_selectable(e))
    except Exception:  # noqa: BLE001
        return True


def _lista(scene, nombre) -> list:
    try:
        return list(_llamar(getattr(scene, nombre, None)) or ())
    except Exception:  # noqa: BLE001
        return []


def universo(scene) -> dict:
    """Lo que se puede seleccionar en el contexto abierto, por tipo."""
    import core.select_ops as so
    oculta = not bool(getattr(scene, "show_hidden_geometry", False))
    aristas = [e for e in _lista(scene, "edges")
               if _visible(scene, e) and not (oculta and getattr(e, "hidden", False))]
    caras = [f for f in _lista(scene, "faces") if _visible(scene, f)]
    try:
        grupos = [g for g in so._context_groups(scene) if _visible(scene, g)]   # interno
    except Exception:  # noqa: BLE001
        grupos = []
    en_modelo = getattr(scene, "edit_group", None) is None
    u = {"arista": aristas, "cara": caras,
         "grupo": [g for g in grupos if not _es_componente(g)],
         "componente": [g for g in grupos if _es_componente(g)],
         "cota": [d for d in _lista(scene, "dimensions") if _visible(scene, d)],
         "texto": [t for t in _lista(scene, "text_labels") if _visible(scene, t)],
         "imagen": [i for i in _lista(scene, "image_planes") if _visible(scene, i)],
         "seccion": [s for s in _lista(scene, "section_planes") if _visible(scene, s)],
         "punto_guia": [], "linea_guia": []}
    if en_modelo:
        for g in _lista(scene, "guides"):
            if not _visible(scene, g):
                continue
            punto = type(g).__name__ == "Guide" and getattr(g, "direction", None) is None
            u["punto_guia" if punto else "linea_guia"].append(g)
    u["curva"] = [e for e in aristas if getattr(e, "curve", None)]
    return u


def _es_componente(g) -> bool:
    try:
        return bool(_llamar(getattr(g, "is_component", False)))
    except Exception:  # noqa: BLE001
        return False


def etiqueta_de(e) -> str:
    try:
        import core.select_ops as so
        return str(so.layer_of(e))
    except Exception:  # noqa: BLE001
        return str(getattr(e, "layer", "") or "")


def material_de(e):
    """El nombre del material (o POR_DEFECTO), o None si no lleva material."""
    if hasattr(e, "attrs") and hasattr(e, "loop"):           # una cara
        attrs = getattr(e, "attrs", None) or {}
        mat = attrs.get("mat") if isinstance(attrs, dict) else None
        return str(mat) if mat else POR_DEFECTO
    if hasattr(e, "xform") and hasattr(e, "material"):        # un grupo o componente
        mat = getattr(e, "material", None)
        return str(mat) if mat else POR_DEFECTO
    return None


def _longitud(e) -> float:
    try:
        return float(_llamar(e.length))
    except Exception:  # noqa: BLE001
        try:
            return (e.v1.position - e.v0.position).length()
        except Exception:  # noqa: BLE001
            return 0.0


def _perimetro(cara) -> float:
    pts = [v.position for v in (getattr(cara, "loop", None) or ())]
    return sum((pts[(i + 1) % len(pts)] - pts[i]).length() for i in range(len(pts))) if len(pts) > 1 else 0.0


def curvas(scene, aristas) -> list:
    """``[(tipo, aristas, forma)]`` de las curvas entre ``aristas``: tipo
    «arco», «circulo», «poligono» o «curva» (a mano alzada o irregular)."""
    from core.curve_segments import read_curve
    mesh = _llamar(getattr(scene, "mesh", None))
    vistas, salida = set(), []
    for e in aristas:
        cid = getattr(e, "curve", None)
        if not cid or cid in vistas:
            continue
        vistas.add(cid)
        try:
            todas = list(mesh.curve_edges(e)) if mesh is not None else [e]
        except Exception:  # noqa: BLE001
            todas = [e]
        try:
            forma = read_curve(mesh, e) if mesh is not None else None
        except Exception:  # noqa: BLE001
            forma = None
        if forma is None:
            tipo = "curva"
        elif not forma.closed:
            tipo = "arco"
        elif len(forma.edges or todas) <= MAX_LADOS_POLIGONO:
            tipo = "poligono"
        else:
            tipo = "circulo"
        salida.append((tipo, todas, forma))
    return salida


def _cumple(valor, comp, a, b) -> bool:
    if valor is None or a is None:
        return False
    tol = 1e-6 * max(1.0, abs(a)) + 1e-9
    if comp == "<":
        return valor < a - tol
    if comp == "<=":
        return valor <= a + tol
    if comp == ">":
        return valor > a + tol
    if comp == ">=":
        return valor >= a - tol
    if comp == "==":
        return abs(valor - a) <= tol
    if comp == "!=":
        return abs(valor - a) > tol
    if comp == "entre":
        if b is None:
            return False
        lo, hi = min(a, b), max(a, b)
        return lo - tol <= valor <= hi + tol
    return False


# -- la ayuda con imagen de cada campo (regla de los paneles nuevos) --------------------------
AYUDAS = {
    "modo": ("Modo de selección", "Nueva: deja solo lo que cumple. Añadir: lo suma a lo que ya "
             "tienes. Quitar: lo saca de lo que tienes."),
    "tipos": ("Tipo de objeto", "Marca qué clases de objetos se buscan. Sin marcar ninguno no se "
              "selecciona nada."),
    "nombre_grupo": ("Nombre de grupo", "Solo los grupos con este nombre. «Cualquiera» no filtra."),
    "nombre_componente": ("Nombre de componente", "Solo los componentes con este nombre. "
                          "«Cualquiera» no filtra."),
    "etiqueta": ("Etiqueta", "Solo lo que está en esta etiqueta (capa). «Cualquiera» no filtra."),
    "material": ("Material", "Solo las caras, grupos y componentes pintados con este material."),
    "tipo_medida": ("Tipo de objeto", "La clase de objeto que se mide. Un polígono es una curva "
                    "cerrada de 12 lados o menos; con más, un círculo."),
    "propiedad": ("Propiedad", "Lo que se mide: longitud, radio, diámetro, área, perímetro o "
                  "volumen (solo grupos sólidos), o su etiqueta o material."),
    "comparacion": ("Comparación", "Cómo se compara la medida con el valor; «entre» pide dos "
                    "valores y vale lo que queda entre ellos (incluidos)."),
    "valor": ("Valor", "La medida con la que se compara. Longitudes en la unidad del dibujo "
              "(admite «30cm», «2m+35cm»); áreas en m² y volúmenes en m³."),
}


def _caja(p, r: QRectF, texto: str, sel: bool, color=QColor(214, 222, 236)) -> None:
    """Un objeto dibujado en perspectiva sencilla; seleccionado, en azul."""
    d = r.height() * 0.28
    frente = QRectF(r.left(), r.top() + d, r.width() - d, r.height() - d)
    p.setPen(QPen(AZUL_SEL if sel else QColor(60, 62, 80), 2.2 if sel else 1.3))
    p.setBrush(color.darker(115))
    p.drawPolygon(QPolygonF([QPointF(frente.right(), frente.top()), QPointF(r.right(), r.top()),
                             QPointF(r.right(), r.bottom() - d), QPointF(frente.right(), frente.bottom())]))
    p.setBrush(color.lighter(108))
    p.drawPolygon(QPolygonF([QPointF(frente.left(), frente.top()), QPointF(r.left() + d, r.top()),
                             QPointF(r.right(), r.top()), QPointF(frente.right(), frente.top())]))
    p.setBrush(color)
    p.drawRect(frente)
    if texto:
        f = QFont(p.font())
        f.setPixelSize(10)
        f.setBold(sel)
        p.setFont(f)
        p.setPen(AZUL_SEL.darker(130) if sel else QColor(50, 50, 50))
        p.drawText(frente, Qt.AlignCenter, texto)


def _texto(p, r, t, px=11, color=QColor(44, 44, 42), negrita=False, al=Qt.AlignCenter) -> None:
    f = QFont(p.font())
    f.setPixelSize(px)
    f.setBold(negrita)
    p.setFont(f)
    p.setPen(color)
    p.drawText(r, al, t)


def _dibujo(p, clave, r: QRectF) -> None:
    from . import _iconos
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if clave == "modo":
        for i, (titulo, antes, despues) in enumerate((("Nueva", (1, 0, 1), (0, 1, 0)),
                                                       ("Añadir", (1, 0, 0), (1, 1, 0)),
                                                       ("Quitar", (1, 1, 0), (1, 0, 0)))):
            cx = x + w * (i + 0.5) / 3.0
            _texto(p, QRectF(cx - 45, y, 90, 14), titulo, 11, negrita=True)
            for k in range(3):
                _caja(p, QRectF(cx - 38 + k * 26, y + 22, 22, 22), "", bool(antes[k]))
                _caja(p, QRectF(cx - 38 + k * 26, y + 66, 22, 22), "", bool(despues[k]))
            _texto(p, QRectF(cx - 45, y + 46, 90, 18), "↓", 14)
    elif clave in ("tipos", "tipo_medida"):
        iconos = ("linea", "rect", "circle", "arco", "agrupar", "medir", "texto")
        for i, ic in enumerate(iconos):
            q = QPointF(x + w * (i + 0.5) / len(iconos), y + h * 0.45)
            sel = i in (1, 4)
            p.setPen(QPen(AZUL_SEL if sel else QColor(190, 190, 190), 2.0))
            p.setBrush(QColor(234, 243, 252) if sel else QColor(255, 255, 255))
            p.drawRoundedRect(QRectF(q.x() - 18, q.y() - 18, 36, 36), 6, 6)
            _iconos.pintar(p, ic, q, 26.0)
            _texto(p, QRectF(q.x() - 18, q.y() + 20, 36, 14), "✔" if sel else "", 12, AZUL_SEL)
    elif clave in ("nombre_grupo", "nombre_componente"):
        nombres = ("Mesa", "Silla", "Mesa") if clave == "nombre_grupo" else ("Puerta", "Ventana", "Puerta")
        for i, n in enumerate(nombres):
            _caja(p, QRectF(x + 12 + i * (w - 24) / 3.0, y + 16, (w - 24) / 3.0 - 12, h - 30), n, n == nombres[0])
    elif clave == "etiqueta":
        for i, (n, sel, col) in enumerate((("Muros", True, QColor(236, 214, 200)),
                                            ("Mobiliario", False, QColor(214, 230, 210)),
                                            ("Muros", True, QColor(236, 214, 200)))):
            rr = QRectF(x + 12 + i * (w - 24) / 3.0, y + 22, (w - 24) / 3.0 - 12, h - 36)
            _caja(p, rr, "", sel, col)
            p.setPen(QPen(QColor(120, 90, 30), 1.0))
            p.setBrush(QColor(246, 197, 74))
            p.drawRoundedRect(QRectF(rr.left(), y, rr.width(), 16), 4, 4)
            _texto(p, QRectF(rr.left(), y, rr.width(), 16), n, 10)
    elif clave == "material":
        for i, (sel, col) in enumerate(((True, QColor(196, 92, 60)), (False, QColor(196, 160, 110)),
                                        (True, QColor(196, 92, 60)), (False, QColor(170, 190, 210)))):
            rr = QRectF(x + 10 + i * (w - 20) / 4.0, y + 12, (w - 20) / 4.0 - 10, h - 24)
            _caja(p, rr, "", sel, col)
        _texto(p, QRectF(x, y + h - 14, w, 14), "ladrillo", 10, AZUL_SEL, True)
    elif clave == "propiedad":
        p.setPen(QPen(QColor(60, 62, 80), 2.0))
        p.setBrush(QColor(214, 222, 236))
        p.drawRect(QRectF(x + 30, y + 30, w - 60, h - 60))
        p.setPen(QPen(AZUL_SEL, 1.6))
        p.drawLine(QPointF(x + 30, y + 18), QPointF(x + w - 30, y + 18))
        _texto(p, QRectF(x, y + 2, w, 14), "longitud 2,40 m", 10, AZUL_SEL, True)
        _texto(p, QRectF(x + 30, y + 30, w - 60, h - 60), "área 3,60 m²", 11, QColor(40, 40, 40), True)
    elif clave == "comparacion":
        y0 = y + h * 0.55
        p.setPen(QPen(QColor(80, 80, 80), 1.6))
        p.drawLine(QPointF(x + 12, y0), QPointF(x + w - 12, y0))
        a, b = x + w * 0.35, x + w * 0.65
        p.setPen(QPen(AZUL_SEL, 6.0))
        p.drawLine(QPointF(a, y0), QPointF(b, y0))
        for xx, t in ((a, "1,20"), (b, "2,50")):
            p.setPen(QPen(QColor(60, 60, 60), 1.4))
            p.drawLine(QPointF(xx, y0 - 8), QPointF(xx, y0 + 8))
            _texto(p, QRectF(xx - 30, y0 + 10, 60, 14), t, 10)
        _texto(p, QRectF(x, y, w, 16), "entre 1,20 y 2,50: vale lo azul", 11, AZUL_SEL, True)
    elif clave == "valor":
        caja = QRectF(x + w * 0.2, y + h * 0.3, w * 0.6, 28)
        p.setPen(QPen(QColor(150, 150, 150), 1.2))
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(caja, 4, 4)
        _texto(p, caja.adjusted(8, 0, -24, 0), "1,20 m", 13, QColor(30, 30, 30), True, Qt.AlignVCenter | Qt.AlignLeft)
        _texto(p, QRectF(caja.right() - 24, caja.top(), 22, caja.height()), "🎤", 13)
        _texto(p, QRectF(x, caja.bottom() + 6, w, 16), "también «120cm» o «2m-80cm»", 10)


def tarjeta(clave, ancho=320, alto_dibujo=110) -> QPixmap:
    titulo, frase = AYUDAS[clave]
    titulo, frase = _tr(titulo), _tr(frase)
    f = QFont()
    f.setPixelSize(11)
    fm = QFontMetricsF(f)
    caja_txt = fm.boundingRect(QRectF(0, 0, ancho - 20, 400), Qt.TextWordWrap, frase)
    alto = int(28 + alto_dibujo + 10 + caja_txt.height() + 12)
    pm = QPixmap(ancho, alto)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(176, 27, 27), 1.4))
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(QRectF(0.7, 0.7, ancho - 1.4, alto - 1.4), 8, 8)
    _texto(p, QRectF(10, 6, ancho - 20, 18), titulo, 13, QColor(176, 27, 27), True, Qt.AlignLeft | Qt.AlignVCenter)
    try:
        _dibujo(p, clave, QRectF(10, 28, ancho - 20, alto_dibujo))
    except Exception:  # noqa: BLE001
        log.exception("no se pudo dibujar la ayuda %s", clave)
    p.setFont(f)
    p.setPen(QColor(60, 60, 58))
    p.drawText(QRectF(10, 28 + alto_dibujo + 10, ancho - 20, caja_txt.height() + 4), Qt.TextWordWrap, frase)
    p.end()
    return pm


class _Globo(QLabel):
    def __init__(self) -> None:
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def mostrar(self, clave, ancla: QRect) -> None:
        self.setPixmap(tarjeta(clave))
        self.adjustSize()
        pantalla = QGuiApplication.screenAt(ancla.center()) or QGuiApplication.primaryScreen()
        area = pantalla.availableGeometry()
        w, h = self.width(), self.height()
        x = ancla.right() + 8
        if x + w > area.right():
            x = ancla.left() - w - 8
        y = max(area.top(), min(ancla.center().y() - h // 2, area.bottom() - h))
        self.move(QPoint(x, y))
        self.show()


class _Ayudas(QObject):
    """Al dejar el ratón sobre un «?», su tarjeta con imagen."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._claves = {}
        self._globo = None
        self._pendiente = None
        self._reloj = QTimer(self)
        self._reloj.setSingleShot(True)
        self._reloj.setInterval(350)
        self._reloj.timeout.connect(self._abrir)

    def marca(self, clave) -> QLabel:
        lab = QLabel("?")
        lab.setObjectName("ayuda")
        lab.setFixedSize(16, 16)
        lab.setAlignment(Qt.AlignCenter)
        lab.setCursor(Qt.WhatsThisCursor)
        self._claves[lab] = clave
        lab.installEventFilter(self)
        return lab

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        t = ev.type()
        if t == QEvent.Enter and obj in self._claves:
            self._pendiente = obj
            self._reloj.start()
        elif t in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Hide):
            self._pendiente = None
            self._reloj.stop()
            self.cerrar()
        return False

    def _abrir(self) -> None:
        w = self._pendiente
        if w is None or not w.isVisible():
            return
        if self._globo is None:
            self._globo = _Globo()
        try:
            self._globo.mostrar(self._claves[w], QRect(w.mapToGlobal(QPoint(0, 0)), w.size()))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo enseñar la ayuda")

    def cerrar(self) -> None:
        if self._globo is not None:
            self._globo.hide()


class _SinRueda(QObject):
    """La rueda del ratón no cambia los desplegables ni los valores."""

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if ev.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox, QLineEdit)):
            ev.ignore()
            return True
        return False


# -- la ventana --------------------------------------------------------------------------------
class SeleccionRapida(QWidget):
    def __init__(self, ventana, viewport, parsear) -> None:
        super().__init__(ventana, Qt.Tool)
        self.setObjectName("selrap")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle(_tr("Selección rápida"))
        self.setStyleSheet(ESTILO)
        self.vp = viewport
        self.parsear = parsear
        self.memoria = []
        self.modo = "nueva"
        self._ayudas = _Ayudas(self)
        self._sin_rueda = _SinRueda(self)
        self._botones_modo = []
        self._situada = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(10, 8, 10, 8)
        raiz.setSpacing(0)
        pestanas = QHBoxLayout()
        pestanas.setSpacing(4)
        self._grupo_pestanas = QButtonGroup(self)
        self.pila = QStackedWidget()
        for i, texto in enumerate(("Por tipo", "Por medida")):
            b = QPushButton(_tr(texto))
            b.setObjectName("pestana")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setCursor(Qt.PointingHandCursor)
            self._grupo_pestanas.addButton(b, i)
            pestanas.addWidget(b)
        pestanas.addStretch(1)
        self._grupo_pestanas.idClicked.connect(self._cambiar_pestana)
        raiz.addLayout(pestanas)
        raya = QFrame()
        raya.setObjectName("raya")
        raiz.addWidget(raya)
        raiz.addSpacing(8)
        self.pila.addWidget(self._pagina_tipo())
        self.pila.addWidget(self._pagina_medida())
        raiz.addWidget(self.pila)
        self._cambiar_pestana(0)

        pie = QHBoxLayout()
        pie.setContentsMargins(0, 8, 0, 0)
        self.cuenta = QLabel()
        pie.addWidget(self.cuenta)
        pie.addStretch(1)
        aplicar = QPushButton(_tr("Aplicar"))
        aplicar.setObjectName("aplicar")
        aplicar.setCursor(Qt.PointingHandCursor)
        aplicar.clicked.connect(self.aplicar)
        cerrar = QPushButton(_tr("Cerrar"))
        cerrar.setObjectName("boton")
        cerrar.setCursor(Qt.PointingHandCursor)
        cerrar.clicked.connect(self.close)
        pie.addWidget(aplicar)
        pie.addWidget(cerrar)
        raiz.addLayout(pie)

        for w in self.findChildren(QWidget):
            if isinstance(w, (QComboBox, QLineEdit)):
                w.setFocusPolicy(Qt.StrongFocus)
                w.installEventFilter(self._sin_rueda)
        self._reloj = QTimer(self)
        self._reloj.setInterval(600)
        self._reloj.timeout.connect(self._contar)
        self.setMinimumWidth(440)

    def _cambiar_pestana(self, i) -> None:
        """La ventana toma la altura de la pestaña que se ve (sin hueco)."""
        from PySide6.QtWidgets import QSizePolicy
        self.pila.setCurrentIndex(i)
        for k in range(self.pila.count()):
            pol = QSizePolicy.Preferred if k == i else QSizePolicy.Ignored
            self.pila.widget(k).setSizePolicy(pol, pol)
        self.pila.adjustSize()
        QTimer.singleShot(0, lambda: self.resize(self.width(), self.minimumSizeHint().height()))

    # -- piezas --
    def _grupo(self, titulo, ayuda=None):
        marco = QFrame()
        marco.setObjectName("grupo")
        lay = QVBoxLayout(marco)
        lay.setContentsMargins(9, 6, 9, 8)
        lay.setSpacing(4)
        cab = QHBoxLayout()
        t = QLabel(_tr(titulo))
        t.setObjectName("titulo")
        cab.addWidget(t)
        cab.addStretch(1)
        if ayuda:
            cab.addWidget(self._ayudas.marca(ayuda))
        lay.addLayout(cab)
        return marco, lay

    def _modos(self, lay, con_botones: bool) -> None:
        fila = QHBoxLayout()
        fila.setSpacing(0)
        grupo = QButtonGroup(self)
        for clave, texto in MODOS:
            b = QPushButton(_tr(texto))
            b.setObjectName("modo")
            b.setCheckable(True)
            b.setChecked(clave == self.modo)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=clave: self._poner_modo(k))
            grupo.addButton(b)
            fila.addWidget(b)
            self._botones_modo.append((clave, b))
        fila.addStretch(1)
        lay.addLayout(fila)
        if con_botones:
            fila2 = QHBoxLayout()
            for texto, fn in (("Invertir", self.invertir), ("Memorizar", self.memorizar),
                              ("Restaurar", self.restaurar)):
                b = QPushButton(_tr(texto))
                b.setObjectName("boton")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(fn)
                fila2.addWidget(b)
            fila2.addStretch(1)
            lay.addLayout(fila2)

    def _poner_modo(self, clave) -> None:
        self.modo = clave
        for k, b in self._botones_modo:
            b.setChecked(k == clave)

    def _campo(self, rejilla, fila, texto, widget, ayuda) -> None:
        rejilla.addWidget(QLabel(_tr(texto)), fila, 0)
        rejilla.addWidget(widget, fila, 1)
        rejilla.addWidget(self._ayudas.marca(ayuda), fila, 2)

    def _pagina_tipo(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        marco, l1 = self._grupo("Modo de selección", "modo")
        self._modos(l1, True)
        lay.addWidget(marco)
        marco, l2 = self._grupo("Tipo de objeto", "tipos")
        rej = QGridLayout()
        rej.setHorizontalSpacing(16)
        rej.setVerticalSpacing(2)
        self.casillas = {}
        for i, (clave, texto) in enumerate(TIPOS):
            c = QCheckBox(_tr(texto))
            c.setChecked(clave in ("arista", "cara"))
            self.casillas[clave] = c
            rej.addWidget(c, i // 2, i % 2)
        l2.addLayout(rej)
        lay.addWidget(marco)
        marco, l3 = self._grupo("Filtros")
        rej = QGridLayout()
        rej.setColumnStretch(1, 1)
        self.filtros = {}
        for fila, (clave, texto) in enumerate((("nombre_grupo", "Nombre de grupo"),
                                               ("nombre_componente", "Nombre de componente"),
                                               ("etiqueta", "Etiqueta"), ("material", "Material"))):
            combo = QComboBox()
            combo.setMinimumWidth(180)
            self.filtros[clave] = combo
            self._campo(rej, fila, texto, combo, clave)
        l3.addLayout(rej)
        lay.addWidget(marco)
        return w

    def _pagina_medida(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        marco, l1 = self._grupo("Modo de selección", "modo")
        self._modos(l1, False)
        lay.addWidget(marco)
        marco, l2 = self._grupo("Condición")
        rej = QGridLayout()
        rej.setColumnStretch(1, 1)
        self.tipo_medida = QComboBox()
        for clave, texto in TIPOS_MEDIDA:
            self.tipo_medida.addItem(_tr(texto), clave)
        self.propiedad = QComboBox()
        self.comparacion = QComboBox()
        for clave, texto in COMPARACIONES:
            self.comparacion.addItem(texto, clave)
        self.valor = QLineEdit()
        self.valor2 = QLineEdit()
        self.valor_lista = QComboBox()
        from ._voz import con_microfono
        for campo in (self.valor, self.valor2):
            try:
                con_microfono(campo, self)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo poner el micrófono")
        self.unidad = QLabel()
        self.unidad2 = QLabel()
        fila_valor = QHBoxLayout()
        fila_valor.setContentsMargins(0, 0, 0, 0)
        fila_valor.addWidget(self.valor, 1)
        fila_valor.addWidget(self.valor_lista, 1)
        fila_valor.addWidget(self.unidad)
        caja_valor = QWidget()
        caja_valor.setLayout(fila_valor)
        fila_valor2 = QHBoxLayout()
        fila_valor2.setContentsMargins(0, 0, 0, 0)
        fila_valor2.addWidget(self.valor2, 1)
        fila_valor2.addWidget(self.unidad2)
        self.caja_valor2 = QWidget()
        self.caja_valor2.setLayout(fila_valor2)
        self._campo(rej, 0, "Tipo de objeto", self.tipo_medida, "tipo_medida")
        self._campo(rej, 1, "Propiedad", self.propiedad, "propiedad")
        self._campo(rej, 2, "Comparación", self.comparacion, "comparacion")
        self._campo(rej, 3, "Valor", caja_valor, "valor")
        self.rotulo_y = QLabel(_tr("y"))
        rej.addWidget(self.rotulo_y, 4, 0)
        rej.addWidget(self.caja_valor2, 4, 1)
        l2.addLayout(rej)
        lay.addWidget(marco)
        lay.addStretch(1)
        self.tipo_medida.currentIndexChanged.connect(self._cambio_tipo)
        self.propiedad.currentIndexChanged.connect(self._cambio_propiedad)
        self.comparacion.currentIndexChanged.connect(self._cambio_comparacion)
        self._cambio_tipo()
        return w

    def _cambio_tipo(self) -> None:
        tipo = self.tipo_medida.currentData()
        antes = self.propiedad.currentData()
        self.propiedad.blockSignals(True)
        self.propiedad.clear()
        props = list(PROPIEDADES.get(tipo, ()))
        if tipo in ("cara", "grupo", "componente"):
            props += ["material"]
        props += ["etiqueta"]
        for k in props:
            self.propiedad.addItem(_tr(TEXTO_PROP[k]), k)
        i = self.propiedad.findData(antes)
        self.propiedad.setCurrentIndex(max(0, i))
        self.propiedad.blockSignals(False)
        self._cambio_propiedad()

    def _cambio_propiedad(self) -> None:
        prop = self.propiedad.currentData()
        lista = prop in ("etiqueta", "material")
        self.comparacion.blockSignals(True)
        actual = self.comparacion.currentData()
        self.comparacion.clear()
        for clave, texto in COMPARACIONES:
            if not lista or clave in ("==", "!="):
                self.comparacion.addItem(texto, clave)
        self.comparacion.setCurrentIndex(max(0, self.comparacion.findData(actual)))
        self.comparacion.blockSignals(False)
        self.valor.setVisible(not lista)
        self.unidad.setVisible(not lista)
        self.valor_lista.setVisible(lista)
        if lista:
            self._llenar(self.valor_lista, self._nombres(prop), con_cualquiera=False)
        unidad = {"area": "m²", "volumen": "m³"}.get(prop)
        if unidad is None and not lista:
            try:
                from ._medidas import unidad_doc
                unidad = unidad_doc()
            except Exception:  # noqa: BLE001
                unidad = ""
        self.unidad.setText(unidad or "")
        self.unidad2.setText(unidad or "")
        self._cambio_comparacion()

    def _cambio_comparacion(self) -> None:
        entre = self.comparacion.currentData() == "entre"
        self.rotulo_y.setVisible(entre)
        self.caja_valor2.setVisible(entre)

    # -- listas de nombres --
    def _nombres(self, que) -> list:
        sc = self.vp.scene
        try:
            u = universo(sc)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo leer el modelo")
            return []
        nombres = set()
        if que == "nombre_grupo":
            nombres = {str(g.name) for g in u["grupo"] if getattr(g, "name", None)}
        elif que == "nombre_componente":
            nombres = {str(g.name) for g in u["componente"] if getattr(g, "name", None)}
        elif que == "etiqueta":
            try:
                for capa in _lista(sc, "layers"):
                    n = getattr(capa, "name", None)
                    if n:
                        nombres.add(str(n))
            except Exception:  # noqa: BLE001
                pass
            for lista in u.values():
                for e in lista:
                    nombres.add(etiqueta_de(e))
        elif que == "material":
            nombres.add(POR_DEFECTO)
            for e in (*u["cara"], *u["grupo"], *u["componente"]):
                m = material_de(e)
                if m:
                    nombres.add(m)
        nombres.discard("")
        return sorted(nombres, key=lambda t: (t != POR_DEFECTO, t.casefold()))

    @staticmethod
    def _llenar(combo, nombres, con_cualquiera=True) -> None:
        antes = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        if con_cualquiera:
            combo.addItem(_tr(CUALQUIERA), None)
        for n in nombres:
            combo.addItem(_tr(n) if n == POR_DEFECTO else n, n)
        i = combo.findText(antes)
        combo.setCurrentIndex(max(0, i))
        combo.blockSignals(False)

    def refrescar(self) -> None:
        for clave, combo in self.filtros.items():
            self._llenar(combo, self._nombres(clave))
        if self.propiedad.currentData() in ("etiqueta", "material"):
            self._llenar(self.valor_lista, self._nombres(self.propiedad.currentData()), con_cualquiera=False)
        self._contar()

    def abrir(self) -> None:
        self.refrescar()
        if not self._situada:
            self.adjustSize()
            try:
                vp = self.vp
                g = QRect(vp.mapToGlobal(QPoint(0, 0)), vp.size())
                self.move(g.right() - self.width() - 40, g.top() + 60)
            except Exception:  # noqa: BLE001
                pass
            self._situada = True
        self.show()
        self.raise_()
        self.activateWindow()
        self._reloj.start()

    def closeEvent(self, ev) -> None:  # noqa: N802
        self._reloj.stop()
        self._ayudas.cerrar()
        super().closeEvent(ev)

    def _contar(self) -> None:
        try:
            n = len(self.vp.scene.selection)
        except Exception:  # noqa: BLE001
            n = 0
        self.cuenta.setText(_tr("Seleccionados: {0} objetos", n))

    # -- seleccionar --
    def _seleccionar(self, entidades, modo=None) -> None:
        sc = self.vp.scene
        modo = modo or self.modo
        entidades = list(dict.fromkeys(entidades))
        if modo == "nueva":
            if entidades:
                sc.select(entidades, mode="replace")
            else:
                sc.clear_selection()
        elif entidades:
            sc.select(entidades, mode="add" if modo == "anadir" else "remove")
        try:
            self.vp.notify_scene_changed()
        except Exception:  # noqa: BLE001
            pass
        self.vp.update()
        self._contar()
        self.vp.flash_status(_tr("Selección rápida: {0} objetos cumplen.", len(entidades)), 3000)

    def aplicar(self) -> None:
        try:
            entidades = self._por_tipo() if self.pila.currentIndex() == 0 else self._por_medida()
        except Exception:  # noqa: BLE001
            log.exception("fallo en la Selección rápida")
            self.vp.flash_status(_tr("La Selección rápida no pudo terminar."), 4000)
            return
        if entidades is None:
            return
        self._seleccionar(entidades)

    def _filtro(self, clave):
        return self.filtros[clave].currentData()

    def _por_tipo(self) -> list:
        u = universo(self.vp.scene)
        n_grupo, n_comp = self._filtro("nombre_grupo"), self._filtro("nombre_componente")
        etiqueta, material = self._filtro("etiqueta"), self._filtro("material")
        salida = []
        for clave, _texto in TIPOS:
            if not self.casillas[clave].isChecked():
                continue
            for e in u[clave]:
                if clave == "grupo" and n_grupo is not None and str(getattr(e, "name", "")) != n_grupo:
                    continue
                if clave == "componente" and n_comp is not None and str(getattr(e, "name", "")) != n_comp:
                    continue
                if etiqueta is not None and etiqueta_de(e) != etiqueta:
                    continue
                if material is not None and material_de(e) != material:
                    continue
                if clave == "curva":
                    salida.extend(self._toda_la_curva(e))
                else:
                    salida.append(e)
        return salida

    def _toda_la_curva(self, e) -> list:
        try:
            mesh = _llamar(getattr(self.vp.scene, "mesh", None))
            return list(mesh.curve_edges(e))
        except Exception:  # noqa: BLE001
            return [e]

    def _leer_valor(self, campo, prop):
        t = campo.text().strip()
        if not t:
            return None
        if prop in ("area", "volumen"):
            try:
                return float(t.replace(",", ".").replace("m²", "").replace("m³", "").strip())
            except ValueError:
                return None
        try:
            return self.parsear(t)
        except Exception:  # noqa: BLE001
            return None

    def _por_medida(self):
        tipo, prop = self.tipo_medida.currentData(), self.propiedad.currentData()
        comp = self.comparacion.currentData()
        u = universo(self.vp.scene)
        if prop in ("etiqueta", "material"):
            buscado = self.valor_lista.currentData()

            def medida(e):
                return etiqueta_de(e) if prop == "etiqueta" else material_de(e)

            def vale(e):
                v = medida(e)
                return (v == buscado) if comp == "==" else (v is not None and v != buscado)
        else:
            a = self._leer_valor(self.valor, prop)
            b = self._leer_valor(self.valor2, prop) if comp == "entre" else None
            if a is None or (comp == "entre" and b is None):
                self.vp.flash_status(_tr("Selección rápida: escribe un valor válido."), 4000)
                self.valor.setFocus()
                return None
            vale = None
        salida = []
        if tipo in ("arco", "circulo", "poligono", "curva"):
            for t, aristas, forma in curvas(self.vp.scene, u["arista"]):
                if t != tipo and not (tipo == "curva"):
                    continue
                if prop in ("etiqueta", "material"):
                    ok = vale(aristas[0])
                else:
                    if prop == "longitud":
                        v = sum(_longitud(e) for e in aristas)
                    elif prop in ("radio", "diametro") and forma is not None:
                        v = float(forma.radius) * (2.0 if prop == "diametro" else 1.0)
                    else:
                        v = None
                    ok = _cumple(v, comp, a, b)
                if ok:
                    salida.extend(aristas)
            return salida
        for e in u[tipo]:
            if prop in ("etiqueta", "material"):
                ok = vale(e)
            else:
                if prop == "longitud":
                    v = _longitud(e)
                elif prop == "area":
                    v = float(_llamar(e.area))
                elif prop == "perimetro":
                    v = _perimetro(e)
                elif prop == "volumen":
                    try:
                        from core.solids import solid_volume
                        v = solid_volume(e)
                    except Exception:  # noqa: BLE001
                        v = None
                else:
                    v = None
                ok = _cumple(v, comp, a, b)
            if ok:
                salida.append(e)
        return salida

    # -- invertir, memorizar, restaurar --
    def invertir(self) -> None:
        sc = self.vp.scene
        try:
            sc.invert_selection()
            self.vp.notify_scene_changed()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo invertir la selección")
        self.vp.update()
        self._contar()

    def memorizar(self) -> None:
        self.memoria = list(self.vp.scene.selection)
        self.vp.flash_status(_tr("Selección rápida: {0} objetos memorizados.", len(self.memoria)), 3000)

    def restaurar(self) -> None:
        if not self.memoria:
            self.vp.flash_status(_tr("Selección rápida: no hay nada memorizado."), 3000)
            return
        u = universo(self.vp.scene)
        vivos = {id(e) for lista in u.values() for e in lista}
        self._seleccionar([e for e in self.memoria if id(e) in vivos], "nueva")

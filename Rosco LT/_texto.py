# SPDX-License-Identifier: GPL-3.0-or-later
"""El Texto de Rosco: bloques de texto (planos o con grosor) que se
apoyan en la cara bajo el ratón y se pueden volver a editar.

Opciones de un bloque (``DEFECTO``): texto; letra, negrita y cursiva; tamaño
(del modelo o del papel, con su escala de dibujo; con «altura de mayúsculas»
el tamaño es la altura de la X); interlineado, ancho de letra, espacio entre
letras y entre palabras; punto de inserción (3×3, primera o última línea);
alinear las líneas (izquierda, centro, derecha, justificar) y en vertical
(con alto de contenedor); desplazamiento X/Y/Z; ancho máximo (parte las
líneas) y alto del contenedor; aristas y caras (cada una con su etiqueta, y
las caras con su color); grosor (0 = plano); borde (rectángulo, redondeado,
círculo, rombo o hexágono; ajustado al texto —caja lógica, de contenido o del
contenedor— con su margen, fijo o en % de la altura, o a medida; ocultar sus
aristas; su etiqueta); segmentos por curva.

El bloque queda como un grupo «Texto: …» con sus parámetros en
``ext["rosco"]["texto"]`` (y su marco), así que se puede rehacer.
"""
from __future__ import annotations

from ._ajustes import ext_al_dia
from ._idioma import con_nombre, _tr
import json
import logging
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QMatrix4x4, QPainterPath, QPalette, QTransform, QVector3D,
)
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFontComboBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton,
    QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from tools.base import Tool, ToolContext

from ._ajustes import registro

log = registro("texto")
CLAVE = "rosco"
PT = 100.0                                    # tamaño de la letra al componer (unidades de fuente)
ESCALAS = ("1/10", "1/20", "1/50", "1/100", "1/200", "1/500")
BORDES = (("rectangulo", "Rectángulo"), ("redondeado", "Rectángulo redondeado"),
          ("circulo", "Círculo"), ("rombo", "Rombo"), ("hexagono", "Hexágono"))
CAJAS = (("logica", "Caja lógica"), ("contenido", "Caja del contenido"),
         ("contenedor", "Caja del contenedor"))
COLORES = ("#ff4500", "#ff8c00", "#ffd700", "#90ee90", "#00ced1", "#1e90ff",
           "#c71585", "#000000", "#ffffff")
# Estilo = todo menos el texto (copiar y pegar estilo, seleccionar similares).
DEFECTO = {
    "texto": "Texto",
    "fuente": "Segoe UI", "negrita": False, "cursiva": False,
    "tamano": 0.3, "contexto": "modelo", "escala": "1/50", "mayusculas": True,
    "interlineado": 1.0, "ancho": 1.0, "letra": 0.0, "palabras": 1.0,
    "insercion": 0, "alinear": 0, "vertical": 0,
    "dx": 0.0, "dy": 0.0, "dz": 0.0,
    "ancho_max": 0.0, "alto_cont": 0.0,
    "grosor": 0.0,
    "aristas": True, "capa_aristas": "", "caras": True, "capa_caras": "", "color": "",
    "borde": False, "borde_tipo": "rectangulo", "borde_medida": False, "borde_caja": "logica",
    "borde_ancho": 0.0, "borde_alto": 0.0, "borde_margen": 0.0, "margen_pct": False,
    "borde_ocultar": False, "capa_borde": "",
    "segmentos": 4,
}
SIMILAR = ("fuente", "negrita", "cursiva", "tamano", "contexto", "escala", "mayusculas")
_MIN = 1e-9


def completar(params: dict | None) -> dict:
    p = dict(DEFECTO)
    for k, v in (params or {}).items():
        if k in DEFECTO:
            p[k] = v
    return p


def estilo(params: dict) -> dict:
    return {k: v for k, v in completar(params).items() if k != "texto"}


def es_texto(g) -> dict | None:
    """Los parámetros si ``g`` es un bloque de texto de esta pieza."""
    datos = (ext_al_dia(getattr(g, "ext", None) or {}).get(CLAVE) or {})
    t = datos.get("texto")
    return t if isinstance(t, dict) else None


# ---- composición (unidades de fuente, y hacia arriba) --------------------------
def _fuente(p: dict) -> QFont:
    f = QFont(p["fuente"] or "Segoe UI")
    f.setPointSizeF(PT)
    f.setBold(bool(p["negrita"]))
    f.setItalic(bool(p["cursiva"]))
    f.setKerning(True)
    return f


def _denominador(escala: str) -> float:
    try:
        a, b = str(escala).split("/")
        return max(_MIN, float(b) / float(a))
    except Exception:  # noqa: BLE001
        return 1.0


def escala_m(p: dict, fm: QFontMetricsF) -> float:
    """Metros por unidad de fuente."""
    tam = max(_MIN, float(p["tamano"]))
    if p["contexto"] == "papel":
        tam *= _denominador(p["escala"])
    base = fm.capHeight() if p["mayusculas"] and fm.capHeight() > 0 else PT
    return tam / max(_MIN, base)


def _aplanar(path: QPainterPath, n: int) -> list:
    """Los contornos de ``path`` como polígonos, con ``n`` tramos por curva."""
    anillos, actual = [], []
    i, total = 0, path.elementCount()
    while i < total:
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            if len(actual) >= 3:
                anillos.append(actual)
            actual = [(e.x, e.y)]
            i += 1
        elif e.type == QPainterPath.ElementType.LineToElement:
            actual.append((e.x, e.y))
            i += 1
        elif e.type == QPainterPath.ElementType.CurveToElement and i + 2 < total:
            x0, y0 = actual[-1] if actual else (e.x, e.y)
            c1, c2, fin = e, path.elementAt(i + 1), path.elementAt(i + 2)
            for k in range(1, n + 1):
                t = k / n
                u = 1.0 - t
                actual.append((u * u * u * x0 + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * fin.x,
                               u * u * u * y0 + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * fin.y))
            i += 3
        else:
            i += 1
    if len(actual) >= 3:
        anillos.append(actual)
    salida = []
    for r in anillos:
        limpio = [r[0]]
        for q in r[1:]:
            if abs(q[0] - limpio[-1][0]) > 1e-6 or abs(q[1] - limpio[-1][1]) > 1e-6:
                limpio.append(q)
        if len(limpio) > 3 and abs(limpio[0][0] - limpio[-1][0]) < 1e-6 and abs(limpio[0][1] - limpio[-1][1]) < 1e-6:
            limpio.pop()
        if len(limpio) >= 3:
            salida.append(limpio)
    return salida


def _partir(texto: str, ancho_max: float, medir) -> list:
    """Las líneas del texto, partidas por palabras si pasan de ``ancho_max``."""
    lineas = []
    for parrafo in texto.split("\n"):
        if ancho_max <= 0:
            lineas.append(parrafo)
            continue
        palabras, actual = parrafo.split(" "), ""
        for w in palabras:
            prueba = w if not actual else actual + " " + w
            if actual and medir(prueba) > ancho_max:
                lineas.append(actual)
                actual = w
            else:
                actual = prueba
        lineas.append(actual)
    return lineas


def componer(params: dict) -> dict:
    """El bloque en unidades de fuente (y arriba, origen = punto de inserción):
    ``{"letras": [anillos], "borde": [anillos], "escala": m/u, "caja": QRectF}``."""
    p = completar(params)
    f = _fuente(p)
    fm = QFontMetricsF(f)
    esc = escala_m(p, fm)
    em = fm.horizontalAdvance("M") or PT
    letra = float(p["letra"]) / esc                 # espacio extra entre letras (m → u)
    ancho_f = max(0.05, float(p["ancho"]))
    palabras_f = max(0.0, float(p["palabras"]))

    def avance(ch: str) -> float:
        a = fm.horizontalAdvance(_tr(ch)) * ancho_f
        if ch == " ":
            a *= palabras_f
        return a + letra

    def medir(s: str) -> float:
        return sum(avance(c) for c in s) - (letra if s else 0.0)

    ancho_max = float(p["ancho_max"]) / esc if float(p["ancho_max"]) > 0 else 0.0
    lineas = _partir(str(p["texto"]), ancho_max, medir)
    alto_linea = fm.lineSpacing() * max(0.1, float(p["interlineado"]))
    anchos = [medir(l) for l in lineas]
    bloque_w = ancho_max if ancho_max > 0 else (max(anchos) if anchos else 0.0)
    n = max(1, int(p["segmentos"]))
    letras = []
    contenido = QRectF()
    for i, (linea, w) in enumerate(zip(lineas, anchos)):
        y = -i * alto_linea
        hueco = bloque_w - w
        x, extra = 0.0, 0.0
        if p["alinear"] == 1:
            x = hueco / 2.0
        elif p["alinear"] == 2:
            x = hueco
        elif p["alinear"] == 3 and i < len(lineas) - 1 and linea.count(" "):
            extra = hueco / linea.count(" ")
        for ch in linea:
            if ch.strip():
                glifo = QPainterPath()
                glifo.addText(0.0, 0.0, f, ch)
                t = QTransform(ancho_f, 0.0, 0.0, -1.0, x, y)
                glifo = t.map(glifo)
                contenido = contenido.united(glifo.boundingRect()) if not contenido.isNull() else glifo.boundingRect()
                letras.extend(_aplanar(glifo, n))
            x += avance(ch) + (extra if ch == " " else 0.0)
    arriba = fm.ascent()
    abajo = -(len(lineas) - 1) * alto_linea - fm.descent()
    logica = QRectF(QPointF(0.0, abajo), QPointF(bloque_w, arriba))
    caja = QRectF(logica)
    alto_cont = float(p["alto_cont"]) / esc if float(p["alto_cont"]) > 0 else 0.0
    bajar = 0.0
    if alto_cont > 0:
        sobra = alto_cont - logica.height()
        bajar = {1: sobra / 2.0, 2: sobra}.get(int(p["vertical"]), 0.0)
        caja = QRectF(QPointF(0.0, arriba - alto_cont), QPointF(bloque_w, arriba))
    if bajar:
        letras = [[(x, y - bajar) for x, y in r] for r in letras]
        logica.translate(0.0, -bajar)
        contenido.translate(0.0, -bajar)
    # El punto de inserción.
    ins = int(p["insercion"])
    if ins in (9, 10):
        ax = caja.left()
        ay = -bajar if ins == 9 else -(len(lineas) - 1) * alto_linea - bajar
    else:
        col, fila = ins % 3, ins // 3              # fila 0 = abajo, 2 = arriba
        ax = (caja.left(), caja.center().x(), caja.right())[col]
        bajo, alto = min(caja.top(), caja.bottom()), max(caja.top(), caja.bottom())   # y hacia arriba
        ay = (bajo, (bajo + alto) / 2.0, alto)[fila]
    def mover(r):
        return [(x - ax, y - ay) for x, y in r]
    letras = [mover(r) for r in letras]
    for rect in (logica, contenido, caja):
        rect.translate(-ax, -ay)
    borde = _borde(p, esc, {"logica": logica, "contenido": contenido, "contenedor": caja}, n) \
        if p["borde"] else []
    return {"letras": letras, "borde": borde, "escala": esc, "caja": caja, "logica": logica}


def _borde(p: dict, esc: float, cajas: dict, n: int) -> list:
    """El contorno del borde (unidades de fuente)."""
    base = cajas.get(p["borde_caja"], cajas["logica"])
    if base.isNull():
        return []
    c = base.center()
    if p["borde_medida"] and float(p["borde_ancho"]) > 0:
        w = float(p["borde_ancho"]) / esc
        h = (float(p["borde_alto"]) / esc) if float(p["borde_alto"]) > 0 else w / 2.0
    else:
        margen = float(p["borde_margen"])
        if p["margen_pct"]:
            margen = float(p["tamano"]) * margen / 100.0
        m = margen / esc
        w, h = abs(base.width()) + 2.0 * m, abs(base.height()) + 2.0 * m
    x0, x1, y0, y1 = c.x() - w / 2.0, c.x() + w / 2.0, c.y() - h / 2.0, c.y() + h / 2.0
    tipo = p["borde_tipo"]
    if tipo == "circulo":
        r = max(w, h) / 2.0 if not p["borde_medida"] else None
        rx, ry = (r, r) if r is not None else (w / 2.0, h / 2.0)
        k = max(12, 8 * n)
        return [[(c.x() + rx * math.cos(2 * math.pi * i / k), c.y() + ry * math.sin(2 * math.pi * i / k))
                 for i in range(k)]]
    if tipo == "rombo":
        return [[(c.x(), y0 - h / 2.0), (x1 + w / 2.0, c.y()), (c.x(), y1 + h / 2.0), (x0 - w / 2.0, c.y())]] \
            if not p["borde_medida"] else [[(c.x(), y0), (x1, c.y()), (c.x(), y1), (x0, c.y())]]
    if tipo == "hexagono":
        d = h / 2.0
        return [[(x0 - d, c.y()), (x0, y0), (x1, y0), (x1 + d, c.y()), (x1, y1), (x0, y1)]]
    if tipo == "redondeado":
        r = min(w, h) * 0.2
        puntos = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0),
                           (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0)):
            for k in range(n + 1):
                a = math.radians(a0 + 90.0 * k / n)
                puntos.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return [puntos]
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


# ---- geometría ------------------------------------------------------------------
# Las letras de IngeTrazo se hacen de pie (plano XZ, grosor hacia -Y); este
# giro las tumba al plano XY local del bloque (grosor hacia +Z, la cara de delante).
_TUMBAR = QMatrix4x4(1, 0, 0, 0,
                     0, 0, 1, 0,
                     0, -1, 0, 0,
                     0, 0, 0, 1)


def marco_en(origen: QVector3D, normal: QVector3D) -> tuple:
    """``(origen, x, y, n)``: x horizontal y y hacia arriba sobre el plano."""
    n = QVector3D(normal).normalized()
    if abs(n.z()) > 0.99:
        x = QVector3D(1, 0, 0)
        y = QVector3D.crossProduct(n, x).normalized()
    else:
        x = QVector3D.crossProduct(QVector3D(0, 0, 1), n).normalized()
        y = QVector3D.crossProduct(n, x).normalized()
    return QVector3D(origen), x, y, n


def matriz_marco(marco: tuple, p: dict) -> QMatrix4x4:
    o, x, y, n = marco
    o = o + x * float(p["dx"]) + y * float(p["dy"]) + n * float(p["dz"])
    return QMatrix4x4(x.x(), y.x(), n.x(), o.x(),
                      x.y(), y.y(), n.y(), o.y(),
                      x.z(), y.z(), n.z(), o.z(),
                      0, 0, 0, 1)


def _color(hexa: str):
    c = QColor(hexa)
    return (c.redF(), c.greenF(), c.blueF()) if hexa and c.isValid() else None


def _malla_aristas(anillos: list, esc: float, ocultas: bool):
    from core.mesh import Mesh
    m = Mesh()
    for r in anillos:
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            e = m.add_edge(QVector3D(a[0] * esc, 0.0, a[1] * esc), QVector3D(b[0] * esc, 0.0, b[1] * esc))
            if ocultas and e is not None:
                e.hidden = True
    return m


def construir(params: dict, marco: tuple):
    """El grupo «Texto: …» listo para insertar (o ``None`` si no hay nada)."""
    from core.group import Group
    from core import text3d
    p = completar(params)
    comp = componer(p)
    esc = comp["escala"]
    hijos = []

    def hijo(malla, nombre, capa):
        g = Group(malla, name=nombre)
        g.xform = QMatrix4x4(_TUMBAR)
        if capa:
            g.layer = capa
        hijos.append(g)
    letras = comp["letras"]
    if letras and p["caras"]:
        malla = text3d._solid_from_rings(letras, esc, 0.0, max(0.0, float(p["grosor"])))
        rgb = _color(p["color"])
        aparte = p["aristas"] and (p["capa_aristas"] or "") != (p["capa_caras"] or "")
        for f in malla.faces:
            if rgb is not None:
                f.attrs["color"] = rgb
        if not p["aristas"] or aparte:
            for e in malla.edges:
                e.hidden = True
        hijo(malla, "Caras", p["capa_caras"])
        if aparte:
            hijo(_malla_aristas(letras, esc, False), "Aristas", p["capa_aristas"])
    elif letras:
        hijo(_malla_aristas(letras, esc, False), "Aristas", p["capa_aristas"])
    if comp["borde"]:
        hijo(_malla_aristas(comp["borde"], esc, bool(p["borde_ocultar"])), "Borde", p["capa_borde"])
    if not hijos:
        return None
    texto = str(p["texto"]).replace("\n", " ").strip()
    grupo = Group(name="Texto: " + (texto[:40] + ("…" if len(texto) > 40 else "")))
    grupo.adopt(hijos)
    grupo.xform = matriz_marco(marco, p)
    o, x, y, n = marco
    grupo.ext = {CLAVE: {"texto": p, "marco": [[o.x(), o.y(), o.z()], [x.x(), x.y(), x.z()],
                                                [y.x(), y.y(), y.z()], [n.x(), n.y(), n.z()]]}}
    return grupo


def marco_de(g) -> tuple | None:
    datos = (ext_al_dia(getattr(g, "ext", None) or {}).get(CLAVE) or {}).get("marco")
    try:
        return tuple(QVector3D(*v) for v in datos)
    except Exception:  # noqa: BLE001
        return None


def contorno(params: dict, marco: tuple) -> list:
    """Las aristas de la vista previa, en el mundo."""
    p = completar(params)
    comp = componer(p)
    esc = comp["escala"]
    m = matriz_marco(marco, p) * _TUMBAR
    tramos = []
    for r in comp["letras"] + comp["borde"]:
        pts = [m.map(QVector3D(a * esc, 0.0, b * esc)) for a, b in r]
        tramos.extend((pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))
    return tramos


# ---- la herramienta ---------------------------------------------------------------
class Texto(Tool):
    name = con_nombre("Rosco · texto")
    icon = "text"
    description = "Text blocks that sit on the face under the cursor and can be edited later."
    uses_snap = True
    vcb_label = None

    def __init__(self, cadena=None) -> None:
        self.cadena = cadena
        self.panel = None
        self.marco = None
        self._vista = []
        self._vista_clave = None
        self.editando = []                    # los bloques que se editan
        self._estilo_copiado = None

    # -- parámetros (los del panel o los últimos usados) --
    def params(self) -> dict:
        return self.panel.leer() if self.panel is not None else completar(_ultimos())

    def on_activate(self, viewport) -> None:
        if viewport.active_tool is not self:
            viewport.set_active_tool(self)
            return
        if self.panel is None:
            self.panel = PanelTexto(self, self.cadena.app.window if self.cadena else viewport.window())
        self._mirar_seleccion(viewport)
        self.panel.mostrar(viewport)
        viewport.flash_status(_tr(self._ayuda()), 9000)

    def on_deactivate(self, viewport) -> None:
        if self.panel is not None:
            _guardar_ultimos(self.panel.leer())
            self.panel.hide()
        self.marco = None
        self._vista = []
        viewport.update()

    def on_cancel(self, viewport) -> None:
        self.marco = None
        if self.cadena is not None:
            self.cadena._a_seleccionar(viewport)

    def _ayuda(self) -> str:
        if self.editando:
            return "Texto: cambia las opciones y pulsa Redibujar (o Intro). Esc sale."
        return "Texto: clic donde quieras colocarlo (se apoya en la cara bajo el ratón). Esc sale."

    def _mirar_seleccion(self, viewport) -> None:
        textos = [g for g in viewport.scene.selection if es_texto(g) is not None]
        self.editando = textos
        if self.panel is not None:
            if textos:
                self.panel.poner(es_texto(textos[0]))
            self.panel.estado(textos)

    # -- ratón --
    def on_hover(self, ctx: ToolContext) -> None:
        if self.editando:
            return
        self.marco = self._marco_bajo(ctx)
        clave = (json.dumps(self.params(), sort_keys=True),
                 tuple(round(v, 5) for q in self.marco for v in (q.x(), q.y(), q.z())))
        if clave != self._vista_clave:
            try:
                self._vista = contorno(self.params(), self.marco)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo componer la vista previa")
                self._vista = []
            self._vista_clave = clave
        ctx.viewport.update()

    def _marco_bajo(self, ctx) -> tuple:
        vp = ctx.viewport
        normal = QVector3D(0, 0, 1)
        try:
            cara, donde = vp.pick_face_placement(ctx.screen.x(), ctx.screen.y())
            if cara is not None:
                n = cara.normal() if callable(cara.normal) else cara.normal
                n = QVector3D(n)
                m = None
                if donde is not None:
                    for g, mm in vp.scene.placements():
                        if g is donde:
                            m = mm
                            break
                if m is not None:
                    n = m.mapVector(n)
                if n.lengthSquared() > _MIN:
                    normal = n.normalized()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo leer la cara bajo el ratón")
        return marco_en(QVector3D(ctx.world), normal)

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        if self.editando:
            vp.flash_status(_tr("Texto: estás editando; Redibujar aplica los cambios. Esc sale."), 4000)
            return
        marco = self._marco_bajo(ctx)
        self.colocar(vp, marco)

    def on_double_click(self, ctx: ToolContext) -> None:
        self.editar_en(ctx.viewport, ctx.screen.x(), ctx.screen.y())

    def editar_en(self, vp, x, y) -> bool:
        """Si en ``(x, y)`` del visor hay un texto, lo selecciona para
        editarlo. True = había uno."""
        try:
            g = vp.pick_group(x, y)
        except Exception:  # noqa: BLE001
            g = None
        while g is not None and es_texto(g) is None:
            g = getattr(g, "owner", None)
        if g is None:
            return False
        vp.scene.select([g], mode="replace")
        self._mirar_seleccion(vp)
        vp.notify_scene_changed()
        vp.flash_status(_tr(self._ayuda()), 6000)
        return True

    def rubber_band_lines(self):
        return [] if self.editando else list(self._vista)

    def dibujar(self, viewport, painter) -> None:
        pass

    # -- hacer --
    def colocar(self, viewport, marco) -> None:
        from core.history import InsertGroupCommand
        p = self.params()
        if not str(p["texto"]).strip():
            viewport.flash_status(_tr("Texto: escribe algo primero."), 3000)
            return
        try:
            g = construir(p, marco)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo construir el texto")
            viewport.flash_status(_tr("Texto: no se pudo construir (mira la letra elegida)."), 5000)
            return
        if g is None:
            viewport.flash_status(_tr("Texto: esa letra no tiene dibujo para estos caracteres."), 4000)
            return
        viewport.history.execute(InsertGroupCommand(g))
        viewport.notify_scene_changed()
        _guardar_ultimos(p)
        viewport.flash_status(_tr("Texto colocado. Ctrl+Z lo deshace."), 3000)

    def rehacer(self, viewport, grupos, cambio) -> int:
        """Vuelve a hacer ``grupos`` con ``cambio(params_viejos) → nuevos``
        en el mismo sitio: un paso de deshacer."""
        from core.history import CompoundCommand, DeleteGroupCommand, InsertGroupCommand
        cmds, nuevos = [], []
        for g in grupos:
            viejos, marco = es_texto(g), marco_de(g)
            if viejos is None or marco is None:
                continue
            viejos = completar(viejos)
            nuevos_p = cambio(viejos)
            nuevo = construir(nuevos_p, marco)
            if nuevo is None:
                continue
            # Si se movió o giró el bloque, el nuevo sale en el mismo sitio.
            try:
                antes = matriz_marco(marco, viejos).inverted()[0]
                nuevo.xform = QMatrix4x4(g.xform) * antes * matriz_marco(marco, completar(nuevos_p))
            except Exception:  # noqa: BLE001
                log.exception("no se pudo conservar la posición del texto")
            # Lo demás que guarde el grupo (hotspots de la Simetría, etiqueta…).
            ext = dict(getattr(g, "ext", None) or {})
            datos = dict(ext_al_dia(ext).get(CLAVE) or {})
            datos.update(nuevo.ext[CLAVE])
            ext[CLAVE] = datos
            nuevo.ext = ext
            if getattr(g, "layer", None):
                nuevo.layer = g.layer
            cmds += [DeleteGroupCommand(g), InsertGroupCommand(nuevo)]
            nuevos.append(nuevo)
        if not cmds:
            return 0
        viewport.history.execute(CompoundCommand(cmds))
        viewport.scene.select(nuevos, mode="replace")
        viewport.notify_scene_changed()
        self.editando = nuevos
        return len(nuevos)

    def redibujar(self, viewport) -> None:
        if not self.editando:
            viewport.flash_status(_tr("Texto: no hay ningún texto seleccionado para redibujar."), 3500)
            return
        p = self.params()
        if len(self.editando) == 1:
            n = self.rehacer(viewport, self.editando, lambda _v: p)
        else:
            est = estilo(p)
            n = self.rehacer(viewport, self.editando, lambda v: {**v, **est})
        viewport.flash_status(_tr("Texto: {0} redibujado(s). Ctrl+Z lo deshace.", n), 3000)

    # -- el menú --
    def copiar_estilo(self, viewport) -> None:
        self._estilo_copiado = estilo(self.params())
        viewport.flash_status(_tr("Texto: estilo copiado."), 2500)

    def pegar_estilo(self, viewport) -> None:
        if not self._estilo_copiado:
            viewport.flash_status(_tr("Texto: no hay estilo copiado."), 2500)
            return
        textos = [g for g in viewport.scene.selection if es_texto(g) is not None]
        n = self.rehacer(viewport, textos, lambda v: {**v, **self._estilo_copiado})
        if n:
            self.panel.poner({**self.params(), **self._estilo_copiado})
        viewport.flash_status(_tr("Texto: estilo pegado en {0}.", n), 2500)

    def duplicar(self, viewport) -> None:
        p = self.params()
        viewport.scene.clear_selection()
        self.editando = []
        self.panel.poner(p)
        self.panel.estado([])
        viewport.notify_scene_changed()
        viewport.flash_status(_tr("Texto: clic donde quieras la copia."), 4000)

    def _todos(self, viewport, dentro=None) -> list:
        from core.group import Group
        salida, pila = [], list(dentro if dentro is not None else viewport.scene.groups)
        while pila:
            g = pila.pop()
            if not isinstance(g, Group):
                continue
            if es_texto(g) is not None:
                salida.append(g)
            else:
                pila.extend(getattr(g, "children", None) or [])
        return salida

    def seleccionar(self, viewport, como: str) -> None:
        if como == "similares":
            ref = {k: self.params()[k] for k in SIMILAR}
            grupos = [g for g in self._todos(viewport)
                      if all(completar(es_texto(g)).get(k) == v for k, v in ref.items())]
        elif como == "dentro":
            grupos = self._todos(viewport, [g for g in viewport.scene.selection])
        else:
            grupos = self._todos(viewport)
        viewport.scene.select(grupos, mode="replace")
        self._mirar_seleccion(viewport)
        viewport.notify_scene_changed()
        viewport.flash_status(_tr("Texto: {0} seleccionado(s).", len(grupos)), 2500)


def _ultimos() -> dict:
    try:
        from ._ajustes import ajustes
        texto = ajustes().value("texto/ultimo", "")
        return json.loads(texto) if texto else {}
    except Exception:  # noqa: BLE001
        return {}


def _guardar_ultimos(p: dict) -> None:
    try:
        from ._ajustes import ajustes
        ajustes().setValue("texto/ultimo", json.dumps(completar(p), ensure_ascii=False))
    except Exception:  # noqa: BLE001
        log.exception("no se pudieron guardar las opciones del texto")


# ---- el panel ----------------------------------------------------------------------
_ESTILO = """
QFrame#rosco_texto { background: #ffffff; border: 1.5px solid #4b3aa8; border-radius: 8px; }
QFrame#rosco_texto QLabel { color: #222; background: transparent; font-size: 8.5pt; }
QLabel#titulo { font-weight: bold; color: #4b3aa8; }
QLabel#seccion { color: #777; font-size: 7.5pt; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QFontComboBox {
  background: #fff; color: #111; border: 1px solid #c9c6bf; border-radius: 3px; padding: 0px 2px;
  font-size: 8.5pt; }
QToolButton { color: #222; border: 1px solid #c9c6bf; border-radius: 3px; background: #f6f5f2;
  padding: 0px 3px; font-size: 8.5pt; }
QToolButton:checked { background: #e4ddfb; border-color: #4b3aa8; }
QToolButton:hover { background: #fadede; }
QPushButton { color: #111; background: #f4f3f0; border: 1px solid #bdbab3; border-radius: 4px;
  padding: 2px 8px; font-size: 8.5pt; }
QPushButton#prim { background: #4b3aa8; color: #fff; border-color: #3a2c88; }
QCheckBox { color: #222; font-size: 8.5pt; }
QCheckBox::indicator { width: 12px; height: 12px; border: 1px solid #8f8c85; border-radius: 2px;
  background: #fff; }
QCheckBox::indicator:checked { background: #4b3aa8; border-color: #3a2c88; }
QAbstractItemView { background: #fff; color: #111; selection-background-color: #e4ddfb;
  selection-color: #111; }
QMenu { background: #fff; color: #111; border: 1px solid #c9c6bf; }
QMenu::item:selected { background: #e4ddfb; }
"""


class PanelTexto(QFrame):
    """La ventanita del Texto: todas las opciones, compacta."""

    def __init__(self, tool: Texto, ventana) -> None:
        super().__init__(ventana, Qt.Tool | Qt.FramelessWindowHint)
        # Fondo opaco y colores propios: con el tema oscuro de IngeTrazo, la
        # ventana transparente salía negra y las letras no se veían.
        self.setObjectName("rosco_texto")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        claro = QPalette()
        for rol, color in ((QPalette.Window, "#ffffff"), (QPalette.Base, "#ffffff"),
                           (QPalette.AlternateBase, "#f6f5f2"), (QPalette.Button, "#f6f5f2"),
                           (QPalette.WindowText, "#222222"), (QPalette.Text, "#111111"),
                           (QPalette.ButtonText, "#222222"), (QPalette.PlaceholderText, "#999999"),
                           (QPalette.Highlight, "#e4ddfb"), (QPalette.HighlightedText, "#111111"),
                           (QPalette.ToolTipBase, "#ffffe8"), (QPalette.ToolTipText, "#111111")):
            claro.setColor(rol, QColor(color))
        self.setPalette(claro)
        self.setStyleSheet(_ESTILO)
        self.tool, self.ventana = tool, ventana
        self._cargando = False
        self._arrastre = None
        self._vista_previa = QTimer(self)
        self._vista_previa.setSingleShot(True)
        self._vista_previa.setInterval(150)
        self._vista_previa.timeout.connect(self._cambio)
        from ._voz import con_microfono
        self._mic = lambda campo: con_microfono(campo, ventana)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(3)
        # Cabecera: título, estado, detalles, menú y cerrar.
        cab = QHBoxLayout()
        self.titulo = QLabel(_tr("Texto"))
        self.titulo.setObjectName("titulo")
        self.titulo.setCursor(Qt.SizeAllCursor)
        cab.addWidget(self.titulo, 1)
        self.b_ayuda = QToolButton(text="?")
        self.b_ayuda.setCheckable(True)
        self.b_ayuda.setToolTip(_tr("Ayuda con imágenes al pasar por encima de cada campo"))
        cab.addWidget(self.b_ayuda)
        self.b_detalles = QToolButton(text=_tr("Detalles"))
        self.b_detalles.setCheckable(True)
        self.b_detalles.toggled.connect(self._ver_detalles)
        cab.addWidget(self.b_detalles)
        self.b_menu = QToolButton(text="☰")
        self.b_menu.setPopupMode(QToolButton.InstantPopup)
        self.b_menu.setMenu(self._menu())
        cab.addWidget(self.b_menu)
        cerrar = QToolButton(text="✕")
        cerrar.setToolTip(_tr("Salir del Texto (Esc)"))
        cerrar.clicked.connect(lambda: self.tool.on_cancel(self.tool.cadena.app.viewport))
        cab.addWidget(cerrar)
        lay.addLayout(cab)
        # El texto.
        self.texto = QPlainTextEdit()
        self.texto.setFixedHeight(48)
        self.texto.setPlaceholderText(_tr("Escribe el texto (Intro = otra línea)"))
        self._mic(self.texto)
        self.texto.textChanged.connect(self._tocar)
        lay.addWidget(self.texto)
        g = QGridLayout()
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(2)
        fila = 0
        # Letra.
        self.fuente = QFontComboBox()
        self.fuente.currentFontChanged.connect(self._tocar)
        self.negrita = self._boton("N", "Negrita", True)
        self.cursiva = self._boton("C", "Cursiva", True)
        caja = QHBoxLayout()
        caja.addWidget(self.fuente, 1)
        caja.addWidget(self.negrita)
        caja.addWidget(self.cursiva)
        g.addWidget(QLabel(_tr("Letra")), fila, 0)
        g.addLayout(caja, fila, 1)
        fila += 1
        # Tamaño, contexto y escala.
        self.tamano = self._medida("Tamaño de la letra (con «altura de mayúsculas», la de la X)")
        self.contexto = QComboBox()
        self.contexto.addItems([_tr("Modelo"), _tr("Papel")])
        self.contexto.setToolTip(_tr("Papel: el tamaño se multiplica por la escala del dibujo"))
        self.contexto.currentIndexChanged.connect(self._tocar)
        self.escala = QComboBox()
        self.escala.setEditable(True)
        self.escala.addItems(list(ESCALAS))
        self.escala.setToolTip(_tr("Escala del dibujo (también una propia, p. ej. 1/75)"))
        self._mic(self.escala.lineEdit())
        self.escala.currentTextChanged.connect(self._tocar)
        self.escala.setMinimumWidth(96)        # que el micrófono no tape la escala
        self.escala.setVisible(False)          # solo cuenta con «Papel»
        self.contexto.currentIndexChanged.connect(lambda i: self.escala.setVisible(i == 1))
        caja = QHBoxLayout()
        caja.addWidget(self.tamano, 1)
        caja.addWidget(self.contexto)
        caja.addWidget(self.escala)
        g.addWidget(QLabel(_tr("Tamaño")), fila, 0)
        g.addLayout(caja, fila, 1)
        fila += 1
        self.grosor = self._medida("Grosor de las letras (0 = planas)")
        g.addWidget(QLabel(_tr("Grosor")), fila, 0)
        g.addWidget(self.grosor, fila, 1)
        fila += 1
        # Alinear.
        self.alinear = self._grupo([("⯇", "Alinear a la izquierda"), ("≡", "Centrar"),
                                     ("⯈", "Alinear a la derecha"), ("☰", "Justificar")])
        self.vertical = self._grupo([("⤒", "Arriba (con alto de contenedor)"),
                                     ("⇕", "Centro (con alto de contenedor)"),
                                     ("⤓", "Abajo (con alto de contenedor)")])
        caja = QHBoxLayout()
        for b in self.alinear[1] + self.vertical[1]:
            caja.addWidget(b)
        caja.addStretch(1)
        g.addWidget(QLabel(_tr("Alinear")), fila, 0)
        g.addLayout(caja, fila, 1)
        fila += 1
        lay.addLayout(g)
        # Detalles (se pliegan).
        self.detalles = QWidget()
        d = QGridLayout(self.detalles)
        d.setContentsMargins(0, 0, 0, 0)
        d.setHorizontalSpacing(4)
        d.setVerticalSpacing(2)
        f = 0
        self.interlineado = self._factor("Interlineado (espacio entre líneas)")
        self.ancho = self._factor("Ancho de las letras")
        self.letra = self._medida("Espacio extra entre letras")
        self.palabras = self._factor("Espacio entre palabras")
        for etiqueta, w in (("Interlineado", self.interlineado), ("Ancho letra", self.ancho),
                            ("Entre letras", self.letra), ("Entre palabras", self.palabras)):
            d.addWidget(QLabel(_tr(etiqueta)), f, 0)
            d.addWidget(w, f, 1)
            f += 1
        # Punto de inserción 3×3 + primera / última línea.
        rejilla = QGridLayout()
        rejilla.setSpacing(1)
        self.insercion = []
        for i in range(9):
            b = QToolButton(text="·")
            b.setCheckable(True)
            b.setFixedSize(QSize(16, 14))
            b.setToolTip(_tr("Punto de inserción"))
            b.clicked.connect(lambda _c=False, k=i: self._poner_insercion(k))
            rejilla.addWidget(b, 2 - i // 3, i % 3)
            self.insercion.append(b)
        for k, (txt, ayuda) in ((9, ("1.ª", "Primera línea (su base)")), (10, ("Últ.", "Última línea (su base)"))):
            b = QToolButton(text=txt)
            b.setCheckable(True)
            b.setToolTip(_tr(ayuda))
            b.clicked.connect(lambda _c=False, kk=k: self._poner_insercion(kk))
            rejilla.addWidget(b, 0 if k == 9 else 2, 3)
            self.insercion.append(b)
        d.addWidget(QLabel(_tr("Inserción")), f, 0)
        d.addLayout(rejilla, f, 1)
        f += 1
        self.dx, self.dy, self.dz = (self._medida(_tr("Desplazar en {0}", e)) for e in "XYZ")
        caja = QHBoxLayout()
        for w in (self.dx, self.dy, self.dz):
            caja.addWidget(w)
        d.addWidget(QLabel(_tr("Desplazar XYZ")), f, 0)
        d.addLayout(caja, f, 1)
        f += 1
        self.ancho_max = self._medida("Ancho máximo: las líneas se parten al pasarlo (vacío = sin límite)")
        self.alto_cont = self._medida("Alto del contenedor (para alinear en vertical; vacío = ninguno)")
        d.addWidget(QLabel(_tr("Ancho máx.")), f, 0)
        d.addWidget(self.ancho_max, f, 1)
        f += 1
        d.addWidget(QLabel(_tr("Alto contenedor")), f, 0)
        d.addWidget(self.alto_cont, f, 1)
        f += 1
        # Aristas y caras.
        self.aristas = QCheckBox(_tr("Aristas"))
        self.capa_aristas = self._capas()
        self.caras = QCheckBox(_tr("Caras"))
        self.capa_caras = self._capas()
        self.b_color = QToolButton(text=_tr("Color"))
        self.b_color.setToolTip(_tr("Color de las caras (vacío = el de siempre)"))
        self.b_color.clicked.connect(self._elegir_color)
        self._color = ""
        for w in (self.aristas, self.caras):
            w.toggled.connect(self._uno_al_menos)
        caja = QHBoxLayout()
        caja.addWidget(self.aristas)
        caja.addWidget(self.capa_aristas, 1)
        d.addWidget(QLabel(_tr("Salida")), f, 0)
        d.addLayout(caja, f, 1)
        f += 1
        caja = QHBoxLayout()
        caja.addWidget(self.caras)
        caja.addWidget(self.capa_caras, 1)
        caja.addWidget(self.b_color)
        d.addLayout(caja, f, 1)
        f += 1
        # Borde.
        self.borde = QCheckBox(_tr("Borde"))
        self.borde.toggled.connect(self._tocar)
        self.borde_tipo = QComboBox()
        for k, t in BORDES:
            self.borde_tipo.addItem(_tr(t), k)
        self.borde_tipo.currentIndexChanged.connect(self._tocar)
        caja = QHBoxLayout()
        caja.addWidget(self.borde)
        caja.addWidget(self.borde_tipo, 1)
        d.addWidget(QLabel(_tr("Borde")), f, 0)
        d.addLayout(caja, f, 1)
        f += 1
        self.borde_medida = QComboBox()
        self.borde_medida.addItems([_tr("Ajustado al texto"), _tr("A medida")])
        self.borde_medida.currentIndexChanged.connect(self._tocar)
        self.borde_caja = QComboBox()
        for k, t in CAJAS:
            self.borde_caja.addItem(_tr(t), k)
        self.borde_caja.currentIndexChanged.connect(self._tocar)
        caja = QHBoxLayout()
        caja.addWidget(self.borde_medida)
        caja.addWidget(self.borde_caja, 1)
        d.addLayout(caja, f, 1)
        f += 1
        self.borde_ancho = self._medida("Ancho del borde (a medida)")
        self.borde_alto = self._medida("Alto del borde (a medida; vacío = la mitad del ancho)")
        caja = QHBoxLayout()
        caja.addWidget(self.borde_ancho)
        caja.addWidget(self.borde_alto)
        d.addWidget(QLabel(_tr("Medida")), f, 0)
        d.addLayout(caja, f, 1)
        f += 1
        self.borde_margen = QLineEdit()
        self.borde_margen.setToolTip(_tr("Margen entre el texto y el borde"))
        self._mic(self.borde_margen)
        self.borde_margen.textChanged.connect(self._tocar)
        self.margen_pct = QCheckBox(_tr("% de la altura"))
        self.margen_pct.toggled.connect(self._tocar)
        caja = QHBoxLayout()
        caja.addWidget(self.borde_margen, 1)
        caja.addWidget(self.margen_pct)
        d.addWidget(QLabel(_tr("Margen")), f, 0)
        d.addLayout(caja, f, 1)
        f += 1
        self.borde_ocultar = QCheckBox(_tr("Ocultar sus aristas"))
        self.borde_ocultar.toggled.connect(self._tocar)
        self.capa_borde = self._capas()
        caja = QHBoxLayout()
        caja.addWidget(self.borde_ocultar)
        caja.addWidget(self.capa_borde, 1)
        d.addLayout(caja, f, 1)
        f += 1
        lay.addWidget(self.detalles)
        # Pie.
        pie = QHBoxLayout()
        self.b_colocar = QPushButton(_tr("+ Colocar texto"))
        self.b_colocar.setObjectName("prim")
        self.b_colocar.setToolTip(_tr("Coloca el texto donde hagas clic"))
        self.b_colocar.clicked.connect(self._a_colocar)
        self.b_redibujar = QPushButton(_tr("Redibujar"))
        self.b_redibujar.setToolTip(_tr("Aplica las opciones al texto seleccionado (Intro)"))
        self.b_redibujar.clicked.connect(lambda: self.tool.redibujar(self.tool.cadena.app.viewport))
        pie.addWidget(self.b_colocar)
        pie.addWidget(self.b_redibujar)
        lay.addLayout(pie)
        self.setFixedWidth(300)
        self.detalles.setVisible(False)
        self._segmentos = 4
        self._mayusculas = True
        self._poner_ayuda(g, d)
        self.poner(completar(_ultimos()))

    def _poner_ayuda(self, g, d) -> None:
        """La ayuda con imagen de cada campo (``_ayuda_texto``), con el «?»."""
        from ._ayuda_texto import Ayudante
        try:
            from ._ajustes import ajustes
            encendida = str(ajustes().value("texto/ayuda", "true")).lower() in ("1", "true")
        except Exception:  # noqa: BLE001
            encendida = True
        self.ayuda = Ayudante(self, encendida)
        self.b_ayuda.setChecked(encendida)

        def cambiar(si):
            self.ayuda.encender(si)
            try:
                from ._ajustes import ajustes
                ajustes().setValue("texto/ayuda", bool(si))
            except Exception:  # noqa: BLE001
                pass
        self.b_ayuda.toggled.connect(cambiar)
        a = self.ayuda.poner
        a(self.texto, "texto")
        a(self.fuente, "letra")
        a(self.negrita, "negrita")
        a(self.cursiva, "cursiva")
        a(self.tamano, "tamano")
        a(self.contexto, "contexto")
        a(self.escala, "escala")
        a(self.grosor, "grosor")
        for b in self.alinear[1]:
            a(b, "alinear")
        for b in self.vertical[1]:
            a(b, "vertical")
        a(self.interlineado, "interlineado")
        a(self.ancho, "ancho")
        a(self.letra, "entre_letras")
        a(self.palabras, "entre_palabras")
        for b in self.insercion:
            a(b, "insercion")
        for w in (self.dx, self.dy, self.dz):
            a(w, "desplazar")
        a(self.ancho_max, "ancho_max")
        a(self.alto_cont, "alto_cont")
        a(self.aristas, "aristas")
        a(self.caras, "caras")
        for w in (self.capa_aristas, self.capa_caras, self.capa_borde):
            a(w, "etiqueta")
        a(self.b_color, "color")
        a(self.borde, "borde")
        a(self.borde_tipo, "borde_tipo")
        a(self.borde_medida, "borde_medida")
        a(self.borde_caja, "borde_caja")
        for w in (self.borde_ancho, self.borde_alto):
            a(w, "borde_valores")
        a(self.borde_margen, "borde_margen")
        a(self.margen_pct, "margen_pct")
        a(self.borde_ocultar, "borde_ocultar")
        self.ayuda.rotulos(g)
        self.ayuda.rotulos(d)

    # -- piezas --
    def _boton(self, texto, ayuda, marcable=False):
        b = QToolButton(text=texto)
        b.setToolTip(_tr(ayuda))
        b.setCheckable(marcable)
        if marcable:
            b.toggled.connect(self._tocar)
        return b

    def _grupo(self, piezas):
        botones = []
        for texto, ayuda in piezas:
            b = QToolButton(text=texto)
            b.setToolTip(_tr(ayuda))
            b.setCheckable(True)
            botones.append(b)
        def marcar(i):
            for j, b in enumerate(botones):
                b.setChecked(j == i)
            self._tocar()
        for i, b in enumerate(botones):
            b.clicked.connect(lambda _c=False, k=i: marcar(k))
        return marcar, botones

    def _medida(self, ayuda):
        e = QLineEdit()
        e.setToolTip(_tr(ayuda))
        self._mic(e)
        e.textChanged.connect(self._tocar)
        e.returnPressed.connect(self._intro)
        return e

    def _factor(self, ayuda):
        s = QDoubleSpinBox()
        s.setRange(0.05, 10.0)
        s.setSingleStep(0.05)
        s.setDecimals(2)
        s.setToolTip(_tr(ayuda))
        s.valueChanged.connect(self._tocar)
        return s

    def _capas(self):
        c = QComboBox()
        c.setToolTip(_tr("Etiqueta (capa)"))
        c.currentIndexChanged.connect(self._tocar)
        return c

    def _menu(self) -> QMenu:
        m = QMenu(self)
        vp = lambda: self.tool.cadena.app.viewport  # noqa: E731
        m.addAction(_tr("Copiar estilo"), lambda: self.tool.copiar_estilo(vp()))
        m.addAction(_tr("Pegar estilo"), lambda: self.tool.pegar_estilo(vp()))
        m.addAction(_tr("Duplicar"), lambda: self.tool.duplicar(vp()))
        m.addSeparator()
        m.addAction(_tr("Seleccionar similares"), lambda: self.tool.seleccionar(vp(), "similares"))
        m.addAction(_tr("Seleccionar todos"), lambda: self.tool.seleccionar(vp(), "todos"))
        m.addAction(_tr("Seleccionar todos en lo seleccionado"), lambda: self.tool.seleccionar(vp(), "dentro"))
        m.addSeparator()
        m.addAction(_tr("Ajustes…"), self._ajustes)
        return m

    # -- leer y poner --
    def _len(self, e: QLineEdit, defecto=0.0) -> float:
        t = e.text().strip()
        if not t:
            return defecto
        v = None
        try:                                   # lo que escribe el propio panel («60.00 cm»)
            from core.units import parse
            r = parse(t)
            if r.value is not None and not r.error:
                v = r.value
        except Exception:  # noqa: BLE001
            v = None
        try:                                   # cuentas: «2m+35cm», «(3-0,2)/2»…
            if v is None and self.tool.cadena is not None:
                v = self.tool.cadena._parsear(t)
        except Exception:  # noqa: BLE001
            v = None
        if v is None:
            try:
                v = float(t.replace(",", "."))
            except ValueError:
                return defecto
        return float(v)

    def leer(self) -> dict:
        def marcado(botones):
            return next((i for i, b in enumerate(botones) if b.isChecked()), 0)
        try:
            margen = float(self.borde_margen.text().replace(",", ".")) if self.margen_pct.isChecked() \
                else self._len(self.borde_margen)
        except ValueError:
            margen = 0.0
        return completar({
            "texto": self.texto.toPlainText(),
            "fuente": self.fuente.currentFont().family(), "negrita": self.negrita.isChecked(),
            "cursiva": self.cursiva.isChecked(),
            "tamano": self._len(self.tamano, 0.3), "contexto": ("modelo", "papel")[self.contexto.currentIndex()],
            "escala": self.escala.currentText().strip() or "1/50", "mayusculas": self._mayusculas,
            "interlineado": self.interlineado.value(), "ancho": self.ancho.value(),
            "letra": self._len(self.letra), "palabras": self.palabras.value(),
            "insercion": next((i for i, b in enumerate(self.insercion) if b.isChecked()), 0),
            "alinear": marcado(self.alinear[1]), "vertical": marcado(self.vertical[1]),
            "dx": self._len(self.dx), "dy": self._len(self.dy), "dz": self._len(self.dz),
            "ancho_max": self._len(self.ancho_max), "alto_cont": self._len(self.alto_cont),
            "grosor": self._len(self.grosor),
            "aristas": self.aristas.isChecked(), "capa_aristas": self.capa_aristas.currentData() or "",
            "caras": self.caras.isChecked(), "capa_caras": self.capa_caras.currentData() or "",
            "color": self._color,
            "borde": self.borde.isChecked(), "borde_tipo": self.borde_tipo.currentData(),
            "borde_medida": self.borde_medida.currentIndex() == 1, "borde_caja": self.borde_caja.currentData(),
            "borde_ancho": self._len(self.borde_ancho), "borde_alto": self._len(self.borde_alto),
            "borde_margen": margen, "margen_pct": self.margen_pct.isChecked(),
            "borde_ocultar": self.borde_ocultar.isChecked(), "capa_borde": self.capa_borde.currentData() or "",
            "segmentos": self._segmentos,
        })

    def _fmt(self, v: float) -> str:
        if not v:
            return ""
        try:
            from core.units import fmt_len
            return fmt_len(float(v))
        except Exception:  # noqa: BLE001
            return f"{float(v):g}"

    def poner(self, params: dict) -> None:
        p = completar(params)
        self._cargando = True
        try:
            self._rellenar_capas()
            self.texto.setPlainText(str(p["texto"]))
            self.fuente.setCurrentFont(QFont(p["fuente"] or "Segoe UI"))
            self.negrita.setChecked(bool(p["negrita"]))
            self.cursiva.setChecked(bool(p["cursiva"]))
            self.tamano.setText(self._fmt(p["tamano"]))
            self.contexto.setCurrentIndex(1 if p["contexto"] == "papel" else 0)
            self.escala.setCurrentText(str(p["escala"]))
            self._mayusculas = bool(p["mayusculas"])
            self.interlineado.setValue(float(p["interlineado"]))
            self.ancho.setValue(float(p["ancho"]))
            self.letra.setText(self._fmt(p["letra"]))
            self.palabras.setValue(float(p["palabras"]))
            for i, b in enumerate(self.insercion):
                b.setChecked(i == int(p["insercion"]))
            for i, b in enumerate(self.alinear[1]):
                b.setChecked(i == int(p["alinear"]))
            for i, b in enumerate(self.vertical[1]):
                b.setChecked(i == int(p["vertical"]))
            for e, k in ((self.dx, "dx"), (self.dy, "dy"), (self.dz, "dz"), (self.ancho_max, "ancho_max"),
                         (self.alto_cont, "alto_cont"), (self.grosor, "grosor"),
                         (self.borde_ancho, "borde_ancho"), (self.borde_alto, "borde_alto")):
                e.setText(self._fmt(p[k]))
            self.aristas.setChecked(bool(p["aristas"]))
            self.caras.setChecked(bool(p["caras"]))
            for c, k in ((self.capa_aristas, "capa_aristas"), (self.capa_caras, "capa_caras"),
                         (self.capa_borde, "capa_borde")):
                i = c.findData(p[k] or "")
                c.setCurrentIndex(max(0, i))
            self._color = p["color"] or ""
            self._pintar_color()
            self.borde.setChecked(bool(p["borde"]))
            self.borde_tipo.setCurrentIndex(max(0, self.borde_tipo.findData(p["borde_tipo"])))
            self.borde_medida.setCurrentIndex(1 if p["borde_medida"] else 0)
            self.borde_caja.setCurrentIndex(max(0, self.borde_caja.findData(p["borde_caja"])))
            self.margen_pct.setChecked(bool(p["margen_pct"]))
            self.borde_margen.setText(f"{float(p['borde_margen']):g}" if p["margen_pct"]
                                      else self._fmt(p["borde_margen"]))
            self.borde_ocultar.setChecked(bool(p["borde_ocultar"]))
            self._segmentos = int(p["segmentos"])
        finally:
            self._cargando = False

    def _rellenar_capas(self) -> None:
        try:
            nombres = [getattr(l, "name", str(l)) for l in self.tool.cadena.app.viewport.scene.layers]
        except Exception:  # noqa: BLE001
            nombres = []
        for c in (self.capa_aristas, self.capa_caras, self.capa_borde):
            actual = c.currentData()
            c.blockSignals(True)
            c.clear()
            c.addItem(_tr("Sin etiqueta"), "")
            for n in nombres:
                c.addItem(n, n)
            i = c.findData(actual or "")
            c.setCurrentIndex(max(0, i))
            c.blockSignals(False)

    def estado(self, textos) -> None:
        n = len(textos)
        self.titulo.setText(_tr("Texto · nuevo" if n == 0 else
                            ("Texto · editando" if n == 1 else _tr("Texto · {0} seleccionados", n))))
        self.b_redibujar.setEnabled(n > 0)

    # -- cambios --
    def _tocar(self, *_a) -> None:
        if not self._cargando:
            self._vista_previa.start()

    def _cambio(self) -> None:
        vp = self.tool.cadena.app.viewport
        self.tool._vista_clave = None
        vp.update()

    def _intro(self) -> None:
        if self.tool.editando:
            self.tool.redibujar(self.tool.cadena.app.viewport)

    def _uno_al_menos(self, _v) -> None:
        if not self.aristas.isChecked() and not self.caras.isChecked():
            otro = self.caras if self.sender() is self.aristas else self.aristas
            otro.setChecked(True)
        self._tocar()

    def _poner_insercion(self, k: int) -> None:
        for i, b in enumerate(self.insercion):
            b.setChecked(i == k)
        self._tocar()

    def _ver_detalles(self, ver: bool) -> None:
        self.detalles.setVisible(ver)
        self.adjustSize()

    def _elegir_color(self) -> None:
        d = QColorDialog(QColor(self._color) if self._color else QColor("#1e90ff"), self)
        for i, c in enumerate(COLORES):
            QColorDialog.setCustomColor(i, QColor(c))
        if d.exec():
            self._color = d.currentColor().name()
        else:
            self._color = ""
        self._pintar_color()
        self._tocar()

    def _pintar_color(self) -> None:
        c = self._color or "#f6f5f2"
        self.b_color.setStyleSheet(f"QToolButton {{ background: {c}; }}")
        self.b_color.setToolTip(_tr("Color de las caras: {0}", self._color or 'el de siempre'))

    def _a_colocar(self) -> None:
        vp = self.tool.cadena.app.viewport
        if self.tool.editando:
            vp.scene.clear_selection()
            self.tool.editando = []
            self.estado([])
            vp.notify_scene_changed()
        vp.setFocus()
        vp.flash_status(_tr("Texto: clic donde quieras colocarlo."), 4000)

    def _ajustes(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(_tr("Texto · ajustes"))
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(_tr("Segmentos por curva (más = letras más suaves)")))
        fila = QHBoxLayout()
        barra = QSlider(Qt.Horizontal)
        barra.setRange(1, 10)
        barra.setValue(self._segmentos)
        num = QSpinBox()
        num.setRange(1, 10)
        num.setValue(self._segmentos)
        barra.valueChanged.connect(num.setValue)
        num.valueChanged.connect(barra.setValue)
        fila.addWidget(barra, 1)
        fila.addWidget(num)
        lay.addLayout(fila)
        mayus = QCheckBox(_tr("Usar la altura de las mayúsculas (tamaño = altura de la X)"))
        mayus.setChecked(self._mayusculas)
        lay.addWidget(mayus)
        botones = QHBoxLayout()
        cancelar, aplicar = QPushButton(_tr("Cancelar")), QPushButton(_tr("Aplicar"))
        aplicar.setObjectName("prim")
        cancelar.clicked.connect(d.reject)
        aplicar.clicked.connect(d.accept)
        botones.addStretch(1)
        botones.addWidget(cancelar)
        botones.addWidget(aplicar)
        lay.addLayout(botones)
        if d.exec():
            self._segmentos = num.value()
            self._mayusculas = mayus.isChecked()
            self._tocar()

    # -- mostrar y arrastrar --
    def mostrar(self, viewport) -> None:
        self._rellenar_capas()
        self.adjustSize()
        if not self.isVisible():
            arriba = viewport.mapToGlobal(viewport.rect().topRight())
            self.move(arriba.x() - self.width() - 12, arriba.y() + 12)
        self.show()
        self.raise_()

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton and self.childAt(ev.position().toPoint()) in (None, self.titulo):
            self._arrastre = ev.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._arrastre is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._arrastre)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        self._arrastre = None
        super().mouseReleaseEvent(ev)

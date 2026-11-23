# SPDX-License-Identifier: GPL-3.0-or-later
"""Ilustraciones 3D de las opciones del panel («antes → después»).

Cada imagen se calcula con el propio motor (``_algo``) sobre una geometría de muestra y se
dibuja con un pequeño renderizador isométrico (QPainter, sombreado plano, orden por
profundidad). Así la imagen enseña exactamente lo que hace la opción."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF

from . import _algo as A

# ------------------------------------------------------------------ cámara isométrica
EYE = A.norm((1.0, -1.45, 0.95))                 # del modelo hacia el ojo
U = A.norm(A.cross((0.0, 0.0, 1.0), EYE))        # derecha en pantalla
W = A.norm(A.cross(EYE, U))                      # arriba en pantalla
LUZ = A.norm((0.35, -0.6, 0.72))

FONDO = QColor(30, 31, 35)
LINEA = QColor(24, 26, 32)
GRIS = (176, 180, 190)
PARED = (118, 122, 134)
SEL = (236, 196, 140)
RES = (232, 140, 48)
AZUL = QColor(100, 160, 255)
TEXTO = QColor(200, 200, 205)


def _sombra(rgb, n):
    f = 0.5 + 0.5 * max(0.0, A.dot(n, LUZ))
    return QColor(int(rgb[0] * f), int(rgb[1] * f), int(rgb[2] * f))


def _normal(pts):
    n = A.norm(A.newell(pts))
    if n is None:
        return (0.0, 0.0, 1.0)
    return n if A.dot(n, EYE) >= 0 else A.mul(n, -1.0)


class Escena:
    """Lista de caras 3D con estilo: ``solido`` (sombreada), ``alambre`` (contorno a trazos),
    ``plano`` (translúcida azul) y ``caja`` (contorno a trazos de un paralelepípedo)."""

    def __init__(self):
        self.caras = []

    def solido(self, pts, rgb=GRIS, borde=None):
        self.caras.append(("solido", list(pts), rgb, borde))

    def alambre(self, pts, color=(150, 150, 158)):
        self.caras.append(("alambre", list(pts), color, None))

    def plano(self, pts):
        self.caras.append(("plano", list(pts), None, None))

    def puntos(self):
        return [p for _k, pts, _c, _b in self.caras for p in pts]


def _proy(p):
    return A.dot(p, U), A.dot(p, W), A.dot(p, EYE)


def render(painter: QPainter, rect: QRectF, escena: Escena, marco=None):
    """Dibuja la escena dentro de ``rect``; ``marco`` = puntos que fijan la escala (para que
    «antes» y «después» salgan a la misma escala)."""
    pts = marco or escena.puntos()
    if not pts:
        return
    xs, ys = zip(*[_proy(p)[:2] for p in pts])
    dx, dy = max(xs) - min(xs) or 1.0, max(ys) - min(ys) or 1.0
    k = min(rect.width() / dx, rect.height() / dy) * 0.86
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def t(p):
        x, y, _z = _proy(p)
        return QPointF(rect.center().x() + (x - cx) * k, rect.center().y() - (y - cy) * k)

    orden = sorted(escena.caras, key=lambda c: sum(_proy(p)[2] for p in c[1]) / len(c[1]))
    for kind, poly, rgb, borde in orden:
        qp = QPolygonF([t(p) for p in poly])
        if kind == "solido":
            painter.setPen(QPen(borde or LINEA, 1.1))
            painter.setBrush(QBrush(_sombra(rgb, _normal(poly))))
            painter.drawPolygon(qp)
        elif kind == "alambre":
            painter.setPen(QPen(QColor(*rgb), 1.2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(qp)
        elif kind == "plano":
            painter.setPen(QPen(AZUL, 1.2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(100, 160, 255, 55)))
            painter.drawPolygon(qp)


# ------------------------------------------------------------------ geometrías de muestra
def _malla(polys, sel):
    pos, vid, faces, edges = {}, {}, {}, {}

    def V(p):
        k = A.pkey(p)
        if k not in vid:
            vid[k] = len(vid)
            pos[vid[k]] = tuple(map(float, p))
        return vid[k]
    for i, poly in enumerate(polys):
        loop = [V(p) for p in poly]
        pts = [pos[v] for v in loop]
        n = A.norm(A.newell(pts)) or (0.0, 0.0, 1.0)
        faces[i] = A.FaceIn(i, loop, [], n, A.length(A.newell(pts)) / 2, i in sel)
        for j in range(len(loop)):
            a, b = loop[j], loop[(j + 1) % len(loop)]
            k = (a, b) if a < b else (b, a)
            edges.setdefault(k, A.EdgeIn(k[0], k[1], []))
            edges[k].faces.append(i)
    return A.MeshIn(pos, faces, edges).finish()


def caja(x0=0.0, y0=0.0, s=1.0, h=None):
    h = s if h is None else h
    P = lambda x, y, z: (x0 + x * s, y0 + y * s, z * h)  # noqa: E731
    return [
        [P(0, 0, 1), P(1, 0, 1), P(1, 1, 1), P(0, 1, 1)],      # 0 arriba
        [P(0, 0, 0), P(0, 1, 0), P(1, 1, 0), P(1, 0, 0)],      # 1 abajo
        [P(0, 0, 0), P(1, 0, 0), P(1, 0, 1), P(0, 0, 1)],      # 2 frente (-y)
        [P(1, 0, 0), P(1, 1, 0), P(1, 1, 1), P(1, 0, 1)],      # 3 derecha (+x)
        [P(1, 1, 0), P(0, 1, 0), P(0, 1, 1), P(1, 1, 1)],      # 4 fondo (+y)
        [P(0, 1, 0), P(0, 0, 0), P(0, 0, 1), P(0, 1, 1)],      # 5 izquierda (-x)
    ]


def techo(ancho=1.0):
    """Superficie a dos aguas con tramo plano arriba (3 caras unidas por aristas suaves)."""
    prof = [(0.0, 0.0), (0.3, 0.3), (0.7, 0.3), (1.0, 0.0)]
    out = []
    for (x1, z1), (x2, z2) in zip(prof, prof[1:]):
        out.append([(x1, 0.0, z1), (x2, 0.0, z2), (x2, ancho, z2), (x1, ancho, z1)])
    return out


def techo_paredes():
    """Tejado a dos aguas entre dos paredes (las paredes no se eligen)."""
    return [
        [(0, 0, 1.0), (1.6, 0, 1.0), (1.6, 0.7, 1.4), (0, 0.7, 1.4)],
        [(0, 0.7, 1.4), (1.6, 0.7, 1.4), (1.6, 1.4, 1.0), (0, 1.4, 1.0)],
        [(0, 0, 0.3), (1.6, 0, 0.3), (1.6, 0, 1.0), (0, 0, 1.0)],       # pared frontal
        [(1.6, 1.4, 0.3), (0, 1.4, 0.3), (0, 1.4, 1.0), (1.6, 1.4, 1.0)],  # pared trasera
    ]


def rejilla(n=2, s=0.6):
    return [[(i * s, j * s, 0.0), ((i + 1) * s, j * s, 0.0), ((i + 1) * s, (j + 1) * s, 0.0), (i * s, (j + 1) * s, 0.0)]
            for i in range(n) for j in range(n)]


def losa():
    return [[(0, 0, 0), (1.2, 0, 0), (1.2, 0.9, 0), (0, 0.9, 0)]]


def inclinada():
    return [[(0, 0, 0), (1.1, 0, 0), (1.1, 0.9, 0.5), (0, 0.9, 0.5)]]


def ele():
    """Dos caras en ángulo recto (tapa y lateral de una caja)."""
    c = caja()
    return c, {0, 3}


def triangulos():
    return [[(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 0, 0), (1, 1, 0), (0, 1, 0)],
            [(1, 0, 0), (1.8, 0, 0), (1.8, 1, 0), (1, 1, 0)]]


# ------------------------------------------------------------------ catálogo de ilustraciones
def _p(**kw):
    base = dict(mode="conjunto", finishing="push", borders="contour")
    base.update(kw)
    return A.Params(**base)


def _antes_despues(polys, sel, params, offset, paredes=(), extra=None):
    """Devuelve (escena antes, escena después, puntos del marco)."""
    m = _malla(polys, sel)
    an = A.Analysis(m, sorted(sel), params)
    plan = A.build_plan(an, offset)
    antes, despues = Escena(), Escena()
    for i, poly in enumerate(polys):
        rgb = PARED if i in paredes else GRIS
        antes.solido(poly, SEL if i in sel else rgb, QColor(200, 120, 30) if i in sel else None)
        if i in plan.remove:
            despues.alambre(poly)
        else:
            despues.solido(poly, rgb)
    for nf in plan.faces:
        despues.solido(nf.pts, RES, QColor(120, 60, 10))
    if extra:
        extra(antes, despues)
    marco = antes.puntos() + despues.puntos()
    return antes, despues, marco


def _solo(polys, sel, paredes=()):
    e = Escena()
    for i, poly in enumerate(polys):
        e.solido(poly, SEL if i in sel else (PARED if i in paredes else GRIS), QColor(200, 120, 30) if i in sel else None)
    return e


def escenas(key):
    """Escenas de la ilustración ``key``: (antes, después, marco) o (sola, None, marco)."""
    if key == "mov_juntas":
        return _antes_despues(techo(), {0, 1, 2}, _p(mode="conjunto", finishing="thicken"), 0.16)
    if key == "mov_direccion":
        return _antes_despues(techo(), {0, 1, 2}, _p(mode="vector", vector=(0.0, 0.0, 1.0)), 0.3)
    if key == "mov_cada_cara":
        return _antes_despues(techo(), {0, 1, 2}, _p(mode="normal", borders="grid"), 0.16)
    if key == "acabado_push":
        return _antes_despues(caja(), {0}, _p(), 0.5)
    if key == "acabado_thicken":
        return _antes_despues(losa(), {0}, _p(finishing="thicken"), 0.22)
    if key in ("borde_inglete", "borde_seguir", "borde_promedio"):
        modo = {"borde_inglete": "conjunto", "borde_seguir": "seguir", "borde_promedio": "conjunto"}[key]
        return _antes_despues(techo_paredes(), {0, 1}, _p(mode=modo, influence=(key == "borde_promedio")), 0.28, paredes=(2, 3))
    if key == "redondear":
        return _antes_despues(caja(), {0, 2, 3, 4, 5}, _p(mode="redondeo", finishing="thicken", segment_round=4), 0.18)
    if key == "dir_normal":
        return _antes_despues(inclinada(), {0}, _p(mode="vector", vector=A.norm(A.newell(inclinada()[0]))), 0.3)
    if key == "dir_media":
        polys, sel = ele()
        return _antes_despues(polys, sel, _p(mode="extruir"), 0.4)
    if key == "dir_eje":
        return _antes_despues(inclinada(), {0}, _p(mode="vector", vector=(0.0, 0.0, 1.0)), 0.35)
    if key == "dir_custom":
        return _antes_despues(inclinada(), {0}, _p(mode="vector", vector=A.norm((0.6, 0.0, 0.8))), 0.35)
    if key == "plana":
        return _antes_despues(techo(), {0, 1, 2}, _p(mode="vector", vector=(0.0, 0.0, 1.0), vector_projected=True), 0.3)
    if key == "coquad":
        return _antes_despues(triangulos(), {0, 1, 2}, _p(mode="normal", borders="grid", coquad=True), 0.3)
    if key in ("bordes_contorno", "bordes_cuadricula", "bordes_ninguno"):
        b = {"bordes_contorno": "contour", "bordes_cuadricula": "grid", "bordes_ninguno": "none"}[key]
        return _antes_despues(rejilla(), set(range(4)), _p(borders=b), 0.3)
    if key == "plano":
        def extra(antes, despues):
            for e in (antes, despues):
                e.plano([(-0.2, -0.2, 0.55), (1.4, -0.2, 0.55), (1.4, 1.1, 0.55), (-0.2, 1.1, 0.55)])
        return _antes_despues(losa(), {0}, _p(target_plane=((0.0, 0.0, 0.55), (0.0, 0.0, 1.0))), 0.1, extra=extra)
    if key == "grupo":
        def extra(antes, despues):
            for pts in ([(-0.1, -0.1, 1.0), (1.1, -0.1, 1.0), (1.1, 1.1, 1.0), (-0.1, 1.1, 1.0)],
                        [(-0.1, -0.1, 1.6), (1.1, -0.1, 1.6), (1.1, 1.1, 1.6), (-0.1, 1.1, 1.6)]):
                despues.alambre(pts, (100, 160, 255))
        return _antes_despues(caja(), {0}, _p(finishing="thicken"), 0.5, extra=extra)
    if key == "rematado":
        return _antes_despues(caja(), {0}, _p(mode="extruir", taper_on=True, taper=0.5), 0.5)
    if key == "desmoldeo":
        return _antes_despues(caja(), {0}, _p(molding_on=True, molding_angle=15.0), 0.5)
    if key == "aleatorio":
        return _antes_despues(rejilla(3, 0.5), set(range(9)), _p(mode="normal", borders="grid", random_on=True, rmin=0.3, rmax=2.0, seed=7), 0.25)
    if key.startswith("sel_"):
        polys = techo() + caja(1.5, 0.0, 0.7)
        sel = {"sel_single": {1}, "sel_surface": {0, 1, 2}, "sel_material": {0, 1, 2}, "sel_all": set(range(len(polys)))}[key]
        return _solo(polys, sel), None, None
    return _solo(caja(), {0}), None, None


TEXTOS = {
    "mov_juntas": ("Juntas", "La superficie sigue unida: las esquinas se cortan en inglete y cada cara queda a la distancia."),
    "mov_direccion": ("Una dirección", "Todas las caras se mueven en la misma dirección (eje, media, normal o la que elijas)."),
    "mov_cada_cara": ("Cada cara", "Cada cara se empuja por separado según su propia normal."),
    "acabado_push": ("Acabado · Empujar", "Empujar/tirar clásico: la cara original desaparece y el sólido crece (o se recorta)."),
    "acabado_thicken": ("Acabado · Engrosar", "Da grosor: la cara original se conserva y se forma un sólido cerrado."),
    "borde_inglete": ("Borde exterior · En inglete", "Los vértices del contorno siguen el inglete de las caras elegidas: el alero sobresale de las paredes."),
    "borde_seguir": ("Borde exterior · Siguiendo las caras vecinas", "Los vértices del contorno resbalan por las caras no elegidas: el tejado crece sin salirse de las paredes."),
    "borde_promedio": ("Borde exterior · Promediado con las vecinas", "La dirección del contorno promedia la de las caras elegidas con la de sus vecinas."),
    "redondear": ("Redondear las aristas salientes", "Las aristas convexas se convierten en un redondeo (segmentos por 90°) con esquinas esféricas."),
    "dir_normal": ("Dirección · Normal de la cara", "Se empuja según la normal de la cara en la que empiezas a arrastrar."),
    "dir_media": ("Dirección · Media del conjunto", "Se empuja según la normal media de las caras elegidas: extrusión compacta."),
    "dir_eje": ("Dirección · X, Y o Z", "Se empuja según el eje elegido, sea cual sea la inclinación de la cara."),
    "dir_custom": ("Dirección · Personalizada", "Se empuja según la dirección tomada del dibujo (arista, cara, guía o eje) o tecleada."),
    "plana": ("Cara superior plana", "Las caras superiores quedan en un mismo plano perpendicular a la dirección."),
    "coquad": ("Triángulos pareados", "Dos triángulos que forman un cuadrilátero se empujan como una sola cara."),
    "bordes_contorno": ("Bordes nuevos · Contorno", "Solo se crean caras laterales en el perímetro del conjunto."),
    "bordes_cuadricula": ("Bordes nuevos · Cuadrícula", "Se crea un borde por cada arista de cada cara, también entre ellas."),
    "bordes_ninguno": ("Bordes nuevos · Ninguno", "Solo se crean las caras desplazadas, sin laterales."),
    "sel_single": ("Selección · Individual", "Al pasar el ratón se elige solo esa cara."),
    "sel_surface": ("Selección · Superficie", "Se eligen las caras unidas por aristas suaves (una superficie curva o facetada)."),
    "sel_material": ("Selección · Mismo material", "Se eligen las caras unidas que tienen el mismo material."),
    "sel_all": ("Selección · Todas las unidas", "Se elige todo lo que esté conectado por aristas."),
    "plano": ("Plano destino", "Las caras llegan hasta el plano elegido, sea cual sea la distancia."),
    "grupo": ("Crear el resultado en un grupo", "La geometría original no se toca: el resultado va a un grupo nuevo."),
    "rematado": ("Rematado", "La cara superior se escala respecto a su centro al % indicado."),
    "desmoldeo": ("Desmoldeo", "Los bordes se inclinan el ángulo indicado (positivo crece, negativo mengua)."),
    "aleatorio": ("Aleatorio", "Cada cara (o cada bloque de caras unidas) se empuja una distancia al azar entre mín y máx."),
}

_CACHE = {}


def imagen(key, w=330, h=160):
    """Pixmap «antes → después» (o una sola vista) de la opción ``key``."""
    ck = (key, w, h)
    if ck in _CACHE:
        return _CACHE[ck]
    pm = QPixmap(w, h)
    pm.fill(FONDO)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        antes, despues, marco = escenas(key)
    except Exception:  # noqa: BLE001
        antes, despues, marco = Escena(), None, None
    if despues is None:
        render(p, QRectF(8, 8, w - 16, h - 16), antes)
    else:
        mitad = (w - 28) / 2
        render(p, QRectF(8, 20, mitad, h - 28), antes, marco)
        render(p, QRectF(20 + mitad, 20, mitad, h - 28), despues, marco)
        p.setPen(QPen(TEXTO, 2))
        cx, cy = w / 2, h / 2
        p.drawLine(QPointF(cx - 7, cy), QPointF(cx + 7, cy))
        p.drawLine(QPointF(cx + 7, cy), QPointF(cx + 2, cy - 4))
        p.drawLine(QPointF(cx + 7, cy), QPointF(cx + 2, cy + 4))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(150, 150, 158))
        p.drawText(QRectF(0, 3, w / 2, 14), Qt.AlignCenter, "antes")
        p.drawText(QRectF(w / 2, 3, w / 2, 14), Qt.AlignCenter, "después")
    p.end()
    _CACHE[ck] = pm
    return pm


def tarjeta(key, ancho=350, alto=160):
    """Tarjeta completa: título, imagen y explicación (lo que enseña el popup)."""
    tit, txt = TEXTOS.get(key, (key, ""))
    img = imagen(key, ancho - 20, alto)
    h = 30 + img.height() + 52
    pm = QPixmap(ancho, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(232, 140, 48), 1.5))
    p.setBrush(QColor(44, 45, 50))
    p.drawRoundedRect(QRectF(1, 1, ancho - 2, h - 2), 7, 7)
    p.setPen(QColor(225, 225, 228))
    p.setFont(QFont("Segoe UI", 10, QFont.Bold))
    p.drawText(QRectF(10, 6, ancho - 20, 20), Qt.AlignLeft | Qt.AlignVCenter, tit)
    p.drawPixmap(10, 28, img)
    p.setPen(QColor(205, 205, 210))
    p.setFont(QFont("Segoe UI", 9))
    p.drawText(QRectF(10, 30 + img.height(), ancho - 20, 48), Qt.TextWordWrap, txt)
    p.end()
    return pm

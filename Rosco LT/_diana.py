# SPDX-License-Identifier: GPL-3.0-or-later
"""La diana de vistas (común al anillo y a la barra de selección).

    centro, mitad de arriba ... zoom extensión (centrar el modelo)
    centro, triángulo rojo .... interruptor vista frontal / posterior
    corona, arriba ............ zoom a la selección
    corona, derecha ........... zoom previo
    corona, izquierda ......... encuadre (mano)
    corona, abajo ............. ocultar / mostrar el resto del modelo
    triángulos de fuera ....... vista superior, inferior, derecha, izquierda
    dos botoncitos ............ deshacer / rehacer
    barra de encima ........... buscador de órdenes (solo con la barra fija)

El dueño da el centro de la diana (``cc``, px del visor) y decide qué hacer
con el encuadre (``al_encuadre``) y tras cada acción (``al_terminar``).
"""
from __future__ import annotations

from ._flotante import mover_a
from ._gestor import gestor_barras
from ._idioma import _tr
import logging
import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen,
    QPolygonF, QVector3D,
)

from . import _iconos
from ._flotante import BLANCO, HALO, NEGRO, ROJO, ROJO_OSCURO, SEPARADOR, glifo

log = logging.getLogger("ingetrazo.plugins.diana")

# ---- Geometría (px) ------------------------------------------------------------
R = 48.0                       # radio exterior
RC = 18.0                      # radio del centro
TRI_DENTRO, TRI_FUERA = 4.0, 15.0     # los triángulos: punta y base (desde el borde)
TRI_ANCHO = 7.5                # media base de cada triángulo
UR_R = 8.5                     # radio de los botoncitos
# Los botoncitos, por parejas (desde el centro): deshacer y rehacer a la
# izquierda; vista cónica y paralela, simétricos, a la derecha.
CHICOS = {"deshacer": QPointF(-86.0, -40.0), "rehacer": QPointF(-66.0, -40.0),
          "conica": QPointF(66.0, -40.0), "paralela": QPointF(86.0, -40.0)}
BUSCA_W, BUSCA_H = 200.0, 22.0
BUSCA_HUECO = 6.0              # entre el triángulo de arriba y el buscador
# El buscador va plegado en su lupa; a la misma altura, sueltos, los
# botones de reiniciar, del gestor de extensiones y del gestor de barras
# (x desde el centro de la diana): la lupa encima de deshacer y, a su lado
# encima de rehacer, los menús de IngeTrazo en árbol; los otros tres en el
# centro, al mismo paso que los de abajo.
FILA = {"buscar": -86.0, "menus": -66.0, "reiniciar": -20.0, "ext": 0.0, "bar": 20.0}
FILA_R = UR_R
# La chincheta y el cerrar de la barra van en esa fila, encima de cónica y
# paralela (los pone el dueño de la barra).
CHINCHETA_X = (66.0, 86.0)
TOLERANCIA = 2.0
ABAJO = R + TRI_FUERA          # del centro al pie del triángulo de abajo
ARRIBA = R + TRI_FUERA         # del centro a la punta de fuera del de arriba
ARRIBA_BUSCA = ARRIBA + BUSCA_HUECO + BUSCA_H    # del centro al tope del buscador
MEDIO = max(max(abs(q.x()) for q in CHICOS.values()) + UR_R,
            max(abs(x) for x in FILA.values()) + FILA_R)      # media anchura

QUIETA_CAMARA_S = 0.6          # vista quieta este tiempo: se guarda
MAX_VISTAS = 30

CORONA = {"arriba": "zoom_sel", "derecha": "zoom_previo",
          "izquierda": "encuadre", "abajo": "ocultar_resto"}
VISTAS = {"vista_arriba": "top", "vista_abajo": "bottom",
          "vista_derecha": "right", "vista_izquierda": "left"}
# La rueda (temas A y B): cinco gajos de 72° (el primero centrado arriba y los
# demás en sentido antihorario), el disco del centro (zoom extensión) con el
# circulito que alterna la vista superior e inferior, los cuatro triángulos
# de vistas y el ✕ en el aro de fuera, sobre la divisoria entre el gajo de
# arriba y el de la derecha.
RUEDA_R = 112.0
RUEDA_GAJOS = ["zoom_sel", "zoom_previo", "encuadre", "seccion", "proyeccion"]
RUEDA_PASO = 360.0 / len(RUEDA_GAJOS)
RUEDA_TRI = {"vista_posterior": 90.0, "vista_derecha": 0.0,
             "vista_frontal": 270.0, "vista_izquierda": 180.0}
# Lo de dentro de la rueda también se configura (``poner_rueda``): los cinco
# gajos, los cuatro triángulos (arriba, derecha, abajo, izquierda) y el centro
# (el disco y el circulito). Un hueco vacío («») no hace nada.
GAJOS_DEF = tuple(RUEDA_GAJOS)
TRI_ANGULOS = (90.0, 0.0, 270.0, 180.0)
TRI_DEF = tuple(RUEDA_TRI)
CENTRO_DEF = ("centrar", "sup_inf")
RUEDA_DISCO, RUEDA_CIRCULITO = CENTRO_DEF
NOMBRE_CORTO = None                    # callable(clave) -> nombre (lo pone la barra)
RUEDA_CERRAR = 90.0 - RUEDA_PASO / 2.0
# En el aro de fuera, con el ✕ y la flecha de volver: los ejes (30°), la
# cámara (150°, abre su abanico), geometría oculta, objetos ocultos, mostrar
# último y mostrar todo.
VOLVER_A = 126.0
RUEDA_BOTONES = {"ejes": 30.0, "camara": 150.0, "geometria_oculta": 210.0,
                 "objetos_ocultos": 234.0, "mostrar_ultimo": 306.0, "mostrar_todo": 330.0,
                 "volver": VOLVER_A}
# Lo que ``Diana._boton_aro`` sabe hacer, esté donde esté; los huecos del aro
# se configuran (``poner_aro``) y «volver» se queda siempre en su sitio.
ARO_PROPIAS = ("ocultar_uno", "mostrar_ultimo", "mostrar_todo", "geometria_oculta",
               "objetos_ocultos", "ejes", "camara")
ARO_DEF = ("ejes", "camara", "geometria_oculta", "objetos_ocultos", "mostrar_ultimo", "mostrar_todo")
RUEDA_ARO = 0.89                       # radio (de R) de los botones del aro
ARO_BOTON_R = 12.5                     # radio de los botones del aro (blancos, borde rojo)
ARO_ICONO = 19.0                       # tamaño de su icono
# El abanico de la cámara: cuatro botones por fuera de la rueda, junto a la
# cámara; las herramientas de cámara de IngeTrazo.
CAMARA_HERR = {"situar_camara": "position_camera", "caminar": "walk",
               "mirar_alrededor": "look_around"}
ABANICO_R = 1.20                       # radio (de R) del abanico
ABANICO_PASO = 18.0                    # grados entre sus botones
ABANICO = {"abierto": False}
RUEDA_TEXTOS = {"zoom_sel": "zoom sel.", "zoom_previo": "zoom previo",
                "encuadre": "encuadre", "ocultar_resto": "ocultar resto",
                "objetos_ocultos": "obj. ocultos", "seccion": "plano secc.",
                "alinear_vista": "alinear vista"}
# 3.1.0: gajos partidos en dos mitades, una al lado de la otra: la de la
# izquierda (más ángulo) es la orden del gajo y la de la derecha, la otra.
from . import _edicion  # noqa: E402
PARTIDOS = {"zoom_sel": "alinear_vista"} if _edicion.con("alinear_vista") else {}
RUEDA_PARTES = ("centrar", "modo2d", "sup_inf", "cerrar_rueda", *RUEDA_GAJOS, *RUEDA_TRI, *RUEDA_BOTONES,
                *ARO_PROPIAS, *CAMARA_HERR, "objetos_ocultos", "alinear_vista")
AMARILLO, MARRON = QColor(246, 197, 74), QColor(122, 74, 32)
# Las órdenes de IngeTrazo de los botones del aro (por su texto de menú).
MOSTRAR_ULTIMO = ("Mostrar último", "Unhide Last", "Último", "Last", "Mostrar lo último")
MOSTRAR_TODO = ("Mostrar todo", "Unhide All", "Todo", "All",
                "Mostrar todo lo oculto (todos los niveles)", "Show everything hidden (every level)")
GEOMETRIA_OCULTA = ("Geometría oculta", "Hidden Geometry")
OBJETOS_OCULTOS = ("Objetos ocultos", "Hidden Objects")
EJES = ("Ejes", "Axes")
PARTES = ("centrar", "frente_detras", *CORONA.values(), *VISTAS,
          *CHICOS, *FILA, *RUEDA_PARTES)
# Lo que ``Diana.usar`` sabe hacer (lo demás que se ponga en el aro lo hace
# la barra).
PROPIAS = frozenset(("centrar", "modo2d", "zoom_sel", "alinear_vista", "zoom_previo", "encuadre", "ocultar_resto",
                     "frente_detras", *VISTAS, "vista_frontal", "vista_posterior", "sup_inf",
                     "proyeccion", *ARO_PROPIAS, *CAMARA_HERR, "seccion",
                     "deshacer", "rehacer", "conica", "paralela",
                     "buscar", "ext", "reiniciar", "bar"))


def poner_aro(claves) -> None:
    """Lo que va en los seis huecos del aro de la rueda (los vacíos no se
    ven); «volver» sigue en el suyo."""
    from ._huecos import ARO_ANGULOS
    RUEDA_BOTONES.clear()
    for clave, angulo in zip(claves, ARO_ANGULOS):
        if clave and clave != "volver" and clave not in RUEDA_BOTONES:
            RUEDA_BOTONES[clave] = angulo
    RUEDA_BOTONES["volver"] = VOLVER_A


def poner_rueda(gajos, tri, centro) -> None:
    """Lo que va dentro de la rueda: los cinco gajos, los cuatro triángulos
    y el centro (disco, circulito)."""
    global RUEDA_DISCO, RUEDA_CIRCULITO
    RUEDA_GAJOS[:] = (list(gajos) + [""] * len(GAJOS_DEF))[:len(GAJOS_DEF)]
    RUEDA_TRI.clear()
    for clave, angulo in zip(tri, TRI_ANGULOS):
        if clave and clave not in RUEDA_TRI:
            RUEDA_TRI[clave] = angulo
    centro = (list(centro) + ["", ""])[:2]
    RUEDA_DISCO, RUEDA_CIRCULITO = centro[0], centro[1]


def texto_corto(clave) -> str:
    """La etiqueta de un gajo o del disco (corta: cabe en la rueda)."""
    if not clave:
        return ""
    if clave in RUEDA_TEXTOS:
        return _tr(RUEDA_TEXTOS[clave])
    if clave == "centrar":
        return _tr("zoom ext.")
    nombre = ""
    if callable(NOMBRE_CORTO):
        try:
            nombre = NOMBRE_CORTO(clave) or ""
        except Exception:  # noqa: BLE001
            nombre = ""
    nombre = _tr((nombre or NOMBRES.get(clave, clave)).split(":")[0].strip())
    return nombre if len(nombre) <= 13 else nombre[:12] + "…"


def disco_partido() -> bool:
    """El disco de la rueda con zoom extensión va partido: arriba zoom
    extensión y abajo el Modo 2D."""
    return RUEDA_DISCO == "centrar" and _edicion.con("modo2d")


def es_parte_rueda(parte) -> bool:
    if parte == "modo2d":
        return disco_partido()
    for gajo, otra in PARTIDOS.items():
        if parte == otra:
            return gajo in RUEDA_GAJOS
    return bool(parte) and (parte in (RUEDA_DISCO, RUEDA_CIRCULITO, "cerrar_rueda")
                            or parte in RUEDA_GAJOS or parte in RUEDA_TRI
                            or parte in RUEDA_BOTONES
                            or (ABANICO["abierto"] and parte in CAMARA_HERR))
NOMBRES = {"centrar": "Zoom extensión", "frente_detras": "Vista frontal / posterior",
           "modo2d": "Modo 2D: paralela, vista superior y zoom (a la selección si la hay)",
           "sup_inf": "Vista superior ⇄ inferior (amarillo: superior; marrón: inferior)",
           "proyeccion": "Cónica ⇄ paralela (muestra la vista actual)",
           "cerrar_rueda": "Cerrar la barra",
           "ocultar_uno": "Ocultar lo seleccionado", "mostrar_ultimo": "Mostrar lo último oculto",
           "mostrar_todo": "Mostrar todo lo oculto", "geometria_oculta": "Ver / esconder la geometría oculta",
           "objetos_ocultos": "Ver / esconder los objetos ocultos", "ejes": "Ejes del dibujo",
           "camara": "Cámara (situar, caminar, mirar alrededor)",
           "situar_camara": "Situar cámara", "caminar": "Caminar",
           "mirar_alrededor": "Mirar alrededor",
           "seccion": "Plano de sección",
           "volver": "Volver al anillo",
           "vista_frontal": "Vista frontal", "vista_posterior": "Vista posterior",
           "zoom_sel": "Zoom a la selección", "zoom_previo": "Zoom previo",
           "alinear_vista": "Alinear la vista: de frente a la cara seleccionada, en paralela",
           "encuadre": "Encuadre (mano)", "ocultar_resto": "Ocultar / mostrar el resto",
           "vista_arriba": "Vista superior", "vista_abajo": "Vista inferior",
           "vista_derecha": "Vista derecha", "vista_izquierda": "Vista izquierda",
           "deshacer": "Deshacer", "rehacer": "Rehacer",
           "conica": "Vista cónica (perspectiva)", "paralela": "Vista paralela",
           "buscar": "Teclea para buscar un comando · Clic: menús de IngeTrazo en árbol",
           "menus": "Menús de IngeTrazo (en árbol, con filtro)",
           "ext": "Gestor de extensiones",
           "bar": "Gestor de barras (si está instalado)",
           "reiniciar": "Reiniciar IngeTrazo"}
NOMBRES, RUEDA_TEXTOS = _edicion.limpiar(NOMBRES), _edicion.limpiar(RUEDA_TEXTOS)
# El ángulo (Qt: 0 = derecha, 90 = arriba) de cada lado.
_ANGULO = {"arriba": 90.0, "derecha": 0.0, "abajo": 270.0, "izquierda": 180.0}
_TRIANGULO = {"vista_arriba": 90.0, "vista_derecha": 0.0,
              "vista_abajo": 270.0, "vista_izquierda": 180.0}


def _pt(c, r, grados) -> QPointF:
    a = math.radians(grados)
    return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))


def _lado(dx, dy_arriba) -> str:
    """El cuarto (arriba, derecha, abajo, izquierda) de un vector."""
    if abs(dy_arriba) >= abs(dx):
        return "arriba" if dy_arriba > 0 else "abajo"
    return "derecha" if dx > 0 else "izquierda"


def _triangulo(cc, grados) -> QPainterPath:
    """El triángulo de fuera en ``grados``, con la punta hacia el centro."""
    punta = _pt(cc, R + TRI_DENTRO, grados)
    base = _pt(cc, R + TRI_FUERA, grados)
    a = math.radians(grados)
    nx, ny = math.sin(a), math.cos(a)            # perpendicular (px de pantalla)
    path = QPainterPath()
    path.addPolygon(QPolygonF([punta,
                               QPointF(base.x() + nx * TRI_ANCHO, base.y() + ny * TRI_ANCHO),
                               QPointF(base.x() - nx * TRI_ANCHO, base.y() - ny * TRI_ANCHO)]))
    path.closeSubpath()
    return path


def _toggle(cc) -> QPainterPath:
    """El interruptor frontal / posterior: triángulo rojo en el centro."""
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(cc.x() - 9.5, cc.y() + 2.0),
                               QPointF(cc.x() + 9.5, cc.y() + 2.0),
                               QPointF(cc.x(), cc.y() + 14.5)]))
    path.closeSubpath()
    return path


def _centro_ur(cc, cual) -> QPointF:
    return cc + CHICOS[cual]


def _proyeccion_glifo(cc, cual) -> QPainterPath:
    """Cónica: dos líneas que se juntan al fondo; paralela: un paralelogramo."""
    from ._flotante import _trazo
    x, y = cc.x(), cc.y()
    if cual == "conica":
        puntos = [(-4.6, 3.6), (4.6, 3.6), (1.6, -3.6), (-1.6, -3.6)]
    else:
        puntos = [(-4.8, 3.6), (2.4, 3.6), (4.8, -3.6), (-2.4, -3.6)]
    borde = QPainterPath()
    borde.addPolygon(QPolygonF([QPointF(x + a, y + b) for a, b in puntos]))
    borde.closeSubpath()
    return _trazo(borde, 1.5)


def proyeccion(viewport) -> str:
    """«perspective», «parallel» o «two_point»."""
    cam = viewport.camera
    modo = getattr(cam, "projection_mode", None)
    if callable(modo):
        try:
            return modo()
        except Exception:  # noqa: BLE001
            pass
    return "perspective" if getattr(cam, "perspective", True) else "parallel"


def rect_buscador(cc) -> QRectF:
    return QRectF(cc.x() - BUSCA_W / 2.0, cc.y() - ARRIBA_BUSCA, BUSCA_W, BUSCA_H)


def centro_fila(cc, cual) -> QPointF:
    """La lupa y los botones sueltos, a la altura del buscador plegado."""
    return QPointF(cc.x() + FILA[cual], rect_buscador(cc).center().y())


# ---- La rueda (temas A y B) -------------------------------------------------------------

def _rueda_radios(r):
    """(circulito, disco central, gajo interior, gajo exterior). El aro de
    fuera (del gajo exterior a R) lleva el ✕ y los botones."""
    return r * 0.11, r * 0.36, r * 0.40, r * 0.78


def rueda_centro_cerrar(cc, r: float = RUEDA_R) -> QPointF:
    return _pt(cc, r * RUEDA_ARO, RUEDA_CERRAR)


def rueda_centro_boton(cc, clave, r: float = RUEDA_R) -> QPointF:
    if clave in CAMARA_HERR:
        return rueda_centro_abanico(cc, clave, r)
    return _pt(cc, r * RUEDA_ARO, RUEDA_BOTONES[clave])


def abanico_abierto() -> bool:
    return ABANICO["abierto"] and "camara" in RUEDA_BOTONES


def cerrar_abanico() -> None:
    ABANICO["abierto"] = False


def rueda_centro_abanico(cc, clave, r: float = RUEDA_R) -> QPointF:
    """Los botones del abanico de la cámara: en arco por fuera de la rueda,
    centrados en el ángulo de la cámara."""
    base = RUEDA_BOTONES.get("camara", 150.0)
    i = list(CAMARA_HERR).index(clave)
    n = len(CAMARA_HERR)
    return _pt(cc, r * ABANICO_R, base + ((n - 1) / 2.0 - i) * ABANICO_PASO)


def en_zona_abanico(cc, p, r: float = RUEDA_R) -> bool:
    """``p`` está en la franja del abanico abierto (para no cerrar la rueda
    al ir de la cámara a sus botones)."""
    if not abanico_abierto() or p is None:
        return False
    dx, dy = p.x() - cc.x(), cc.y() - p.y()
    if math.hypot(dx, dy) > r * ABANICO_R + ARO_BOTON_R + 6.0:
        return False
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    base = RUEDA_BOTONES.get("camara", 150.0)
    media = (len(CAMARA_HERR) - 1) / 2.0 * ABANICO_PASO + 10.0
    return abs((ang - base + 180.0) % 360.0 - 180.0) <= media


def _boton_aro_pintar(painter, clave, q, icono=None, marcado: bool = False) -> None:
    """Un botón del aro (o del abanico): disco blanco con borde rojo grueso
    y el icono grande, para que se vea bien sobre cualquier fondo."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(176, 27, 27), 2.2))
    painter.setBrush(QBrush(QColor(255, 196, 214) if marcado else QColor(255, 255, 255)))
    painter.drawEllipse(q, ARO_BOTON_R, ARO_BOTON_R)
    from . import _iconos
    _iconos.pintar(painter, icono or clave, q, ARO_ICONO)
    painter.restore()


def _rueda_triangulo(cc, grados, r) -> QPainterPath:
    punta = _pt(cc, r * 0.90, grados)
    base = _pt(cc, r + 5.0, grados)
    a = math.radians(grados)
    nx, ny = math.sin(a), math.cos(a)
    path = QPainterPath()
    path.addPolygon(QPolygonF([punta, QPointF(base.x() + nx * 8.0, base.y() + ny * 8.0),
                               QPointF(base.x() - nx * 8.0, base.y() - ny * 8.0)]))
    path.closeSubpath()
    return path


def _rueda_gajo(cc, i, r) -> QPainterPath:
    from ._flotante import sector
    _rb, _rc, ri, re = _rueda_radios(r)
    return sector(cc, ri, re, 90.0 + RUEDA_PASO * i - RUEDA_PASO / 2.0, RUEDA_PASO, 3.0)


def rueda_mitades(cc, i, r) -> list:
    """Las dos mitades del gajo partido ``i``: ``[(parte, path, ángulo
    del medio)]``; la de la izquierda (más ángulo), la orden del gajo."""
    from ._flotante import sector
    _rb, _rc, ri, re = _rueda_radios(r)
    g = 90.0 + RUEDA_PASO * i
    medio = RUEDA_PASO / 2.0
    parte = RUEDA_GAJOS[i]
    return [(parte, sector(cc, ri, re, g, medio, 3.0), g + medio / 2.0),
            (PARTIDOS[parte], sector(cc, ri, re, g - medio, medio, 3.0), g - medio / 2.0)]


def _contenido_mitad(painter, cc, i, parte, bajo, r) -> None:
    """El icono y la etiqueta (en dos renglones) de una mitad de gajo."""
    _rb, _rc, ri, re = _rueda_radios(r)
    a = next(a for p, _path, a in rueda_mitades(cc, i, r) if p == parte)
    m = _pt(cc, (ri + re) / 2.0 - 1.5, a)
    f = QFont(painter.font())
    f.setPointSizeF(6.3)
    f.setBold(False)
    painter.setFont(f)
    glifo(painter, parte, QPointF(m.x(), m.y() - 10.0), ROJO_OSCURO if parte == bajo else NEGRO, 18.0)
    painter.setPen(QColor(44, 44, 42))
    painter.drawText(QRectF(m.x() - 24.0, m.y(), 48.0, 26.0), Qt.AlignHCenter | Qt.AlignTop,
                     texto_corto(parte).replace(" ", "\n", 1))


def rueda_parte_en(cc, p, r: float = RUEDA_R):
    """La parte de la rueda bajo ``p``, o None."""
    if cc is None or p is None:
        return None
    tope = ARO_BOTON_R + 1.5
    if abanico_abierto():
        for clave in CAMARA_HERR:
            q = rueda_centro_abanico(cc, clave, r)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= tope:
                return clave
    q = rueda_centro_cerrar(cc, r)
    if math.hypot(p.x() - q.x(), p.y() - q.y()) <= tope:
        return "cerrar_rueda"
    for clave in RUEDA_BOTONES:
        q = rueda_centro_boton(cc, clave, r)
        if math.hypot(p.x() - q.x(), p.y() - q.y()) <= tope:
            return clave
    dx, dy = p.x() - cc.x(), cc.y() - p.y()
    d = math.hypot(dx, dy)
    rb, rc, _ri, re = _rueda_radios(r)
    if d <= rb + 1.5:
        return RUEDA_CIRCULITO or None
    if d <= rc:
        if disco_partido() and dy < 0.0:
            return "modo2d"                  # la mitad de abajo del disco
        return RUEDA_DISCO or None
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    if d <= re + TOLERANCIA:
        i = min(int(((ang - (90.0 - RUEDA_PASO / 2.0)) % 360.0) // RUEDA_PASO), len(RUEDA_GAJOS) - 1)
        parte = RUEDA_GAJOS[i]
        if parte in PARTIDOS and (ang - (90.0 + RUEDA_PASO * i) + 180.0) % 360.0 - 180.0 < 0.0:
            return PARTIDOS[parte]           # la mitad de la derecha
        return parte or None
    if d <= r + 6.0:
        for parte, g in RUEDA_TRI.items():
            if abs((ang - g + 180.0) % 360.0 - 180.0) <= 9.0:
                return parte
    return None


def rueda_mascara(cc, r: float = RUEDA_R) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(cc, r + 8.0, r + 8.0)
    if abanico_abierto():
        for clave in CAMARA_HERR:
            path.addEllipse(rueda_centro_abanico(cc, clave, r), ARO_BOTON_R + 2.0, ARO_BOTON_R + 2.0)
    return path


def rueda_pintar(painter, cc, bajo=None, proyeccion: str = "perspective",
                 abajo: bool = False, r: float = RUEDA_R) -> None:
    """La rueda entera (sin el ratón): ``proyeccion`` es la actual (el gajo
    cónica ⇄ paralela la muestra) y ``abajo`` si la vista es la inferior
    (el circulito del centro va marrón; si no, amarillo)."""
    from ._flotante import dibujar_boton_redondo, hundido_banda, relieve_banda, sombra
    rb, rc, ri, re = _rueda_radios(r)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    disco = QPainterPath()
    disco.addEllipse(cc, r, r)
    sombra(painter, disco)
    painter.setPen(QPen(ROJO, 1.8))
    painter.setBrush(QBrush(BLANCO))
    painter.drawEllipse(cc, r, r)
    painter.setPen(QPen(ROJO, 1.2))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(cc, re, re)
    f = QFont(painter.font())
    f.setPointSizeF(7.5)
    f.setBold(False)
    painter.setFont(f)
    for i, parte in enumerate(RUEDA_GAJOS):
        if parte in PARTIDOS:
            for mitad, path, _a in rueda_mitades(cc, i, r):
                painter.setPen(Qt.NoPen)
                painter.setBrush(relieve_banda(cc, ri, re))
                painter.drawPath(path)
                painter.setPen(QPen(ROJO, 1.3))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
                _contenido_mitad(painter, cc, i, mitad, bajo, r)
            continue
        gajo = _rueda_gajo(cc, i, r)
        painter.setPen(Qt.NoPen)
        if parte == "proyeccion":
            # Un interruptor: hundido (sube al pasar el ratón) y dice en qué
            # vista estás.
            painter.setBrush(hundido_banda(cc, ri, re))
            painter.drawPath(gajo)
            painter.setPen(QPen(QColor(120, 120, 114), 1.3))
        else:
            painter.setBrush(relieve_banda(cc, ri, re))
            painter.drawPath(gajo)
            painter.setPen(QPen(ROJO, 1.3))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(gajo)
        _rueda_contenido(painter, cc, i, parte, proyeccion, bajo, r)
    # El disco del centro (de serie, zoom extensión) con el circulito dentro
    # (de serie, vista superior ⇄ inferior: amarillo o marrón).
    painter.setPen(QPen(ROJO, 2.0))
    painter.setBrush(relieve_banda(cc, 0.0, rc))
    painter.drawEllipse(cc, rc, rc)
    if disco_partido():
        # Partido por una raya: arriba zoom extensión, abajo el Modo 2D.
        painter.setPen(QPen(ROJO, 1.4))
        painter.drawLine(QPointF(cc.x() - rc + 1.0, cc.y()), QPointF(cc.x() - rb - 2.0, cc.y()))
        painter.drawLine(QPointF(cc.x() + rb + 2.0, cc.y()), QPointF(cc.x() + rc - 1.0, cc.y()))
        painter.setPen(QColor(44, 44, 42))
        painter.drawText(QRectF(cc.x() - 30.0, cc.y() - rc * 0.72, 60.0, 12.0), Qt.AlignCenter,
                         _tr(texto_corto(RUEDA_DISCO)))
        glifo(painter, RUEDA_DISCO, QPointF(cc.x() - rc * 0.55, cc.y() - rc * 0.28), NEGRO, 11.0)
        painter.drawText(QRectF(cc.x() - 30.0, cc.y() + rc * 0.42, 60.0, 12.0), Qt.AlignCenter,
                         _tr("modo 2D"))
        _plano(painter, QPointF(cc.x() - rc * 0.55, cc.y() + rc * 0.24), 0.62)
        negrita = QFont(f)
        negrita.setPointSizeF(8.5)
        negrita.setBold(True)
        painter.setFont(negrita)
        painter.setPen(ROJO)
        painter.drawText(QRectF(cc.x() + rc * 0.25, cc.y() + rc * 0.06, 22.0, 12.0), Qt.AlignCenter, "2D")
        painter.setFont(f)
    elif RUEDA_DISCO:
        glifo(painter, RUEDA_DISCO, QPointF(cc.x(), cc.y() + rc * 0.58), NEGRO, 15.0)
        painter.setPen(QColor(44, 44, 42))
        painter.drawText(QRectF(cc.x() - 30.0, cc.y() - rc * 0.72, 60.0, 12.0), Qt.AlignCenter,
                         _tr(texto_corto(RUEDA_DISCO)))
    if RUEDA_CIRCULITO == "sup_inf":
        painter.setPen(QPen(QColor(90, 60, 10), 1.4))
        painter.setBrush(QBrush(MARRON if abajo else AMARILLO))
        painter.drawEllipse(cc, rb, rb)
    elif RUEDA_CIRCULITO:
        painter.setPen(QPen(ROJO, 1.4))
        painter.setBrush(QBrush(BLANCO))
        painter.drawEllipse(cc, rb, rb)
        glifo(painter, RUEDA_CIRCULITO, cc, NEGRO, rb * 1.5)
    # Los triángulos (de serie, las vistas); con otra orden, su icono encima.
    for parte, grados in RUEDA_TRI.items():
        painter.setPen(QPen(ROJO, 1.3))
        painter.setBrush(QBrush(QColor(251, 227, 227)))
        painter.drawPath(_rueda_triangulo(cc, grados, r))
        if parte not in TRI_DEF:
            glifo(painter, parte, _pt(cc, r * 0.97, grados), NEGRO, 12.0)
    _boton_aro_pintar(painter, "cerrar_rueda", rueda_centro_cerrar(cc, r), icono="cerrar")
    abierto = abanico_abierto()
    for clave in RUEDA_BOTONES:
        _boton_aro_pintar(painter, clave, rueda_centro_boton(cc, clave, r),
                          marcado=abierto and clave == "camara")
    if abierto:
        # El abanico de la cámara, unido a ella con un arco discontinuo.
        q = rueda_centro_boton(cc, "camara", r)
        painter.setPen(QPen(QColor(176, 27, 27), 1.2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        for clave in CAMARA_HERR:
            d = rueda_centro_abanico(cc, clave, r)
            largo = math.hypot(d.x() - q.x(), d.y() - q.y()) or 1.0
            ux, uy = (d.x() - q.x()) / largo, (d.y() - q.y()) / largo
            painter.drawLine(QPointF(q.x() + ux * ARO_BOTON_R, q.y() + uy * ARO_BOTON_R),
                             QPointF(d.x() - ux * ARO_BOTON_R, d.y() - uy * ARO_BOTON_R))
        for clave in CAMARA_HERR:
            _boton_aro_pintar(painter, clave, rueda_centro_abanico(cc, clave, r))
    painter.restore()


def _plano(p, c, s=1.0) -> None:
    """El icono del Modo 2D: una planta vista desde arriba (tabique y puerta)."""
    p.save()
    p.setPen(QPen(QColor(30, 30, 30), 1.4 * s))
    p.setBrush(QBrush(QColor(142, 197, 232)))
    p.drawRect(QRectF(c.x() - 8 * s, c.y() - 5.5 * s, 16 * s, 11 * s))
    p.drawLine(QPointF(c.x() + 1 * s, c.y() - 5.5 * s), QPointF(c.x() + 1 * s, c.y() + 1 * s))
    p.setPen(QPen(ROJO, 1.2 * s))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(c.x() - 3 * s, c.y() - 2.5 * s, 8 * s, 8 * s), 0, 90 * 16)
    p.restore()


def _rueda_contenido(painter, cc, i, parte, proyeccion, bajo, r) -> None:
    """El icono y la etiqueta de un gajo (el de cónica ⇄ paralela enseña la
    vista actual)."""
    grados = 90.0 + RUEDA_PASO * i
    if not parte:
        return                               # un gajo vacío
    if parte == "proyeccion":
        icono, texto = (("paralela", "paralela") if proyeccion == "parallel"
                        else ("conica", "cónica"))
    else:
        icono, texto = parte, texto_corto(parte)
    # Icono arriba y texto debajo, centrados en el gajo (un poco hacia
    # dentro, para no rozar los botones del aro); en los gajos de los lados,
    # el texto en dos renglones para no pisar el disco del centro.
    _rb, _rc, ri, re = _rueda_radios(r)
    m = _pt(cc, (ri + re) / 2.0 - 1.5, grados)
    f = QFont(painter.font())
    f.setPointSizeF(7.5)
    f.setBold(False)
    painter.setFont(f)
    fm = QFontMetricsF(f)
    texto = _tr(texto)
    if (abs(math.cos(math.radians(grados))) > 0.7 and " " in texto
            and fm.horizontalAdvance(texto) > (re - ri) * 1.1):
        texto = texto.replace(" ", "\n", 1)
    alto = fm.height() * (texto.count("\n") + 1)
    ic = QPointF(m.x(), m.y() - alto / 2.0 - 6.0)
    glifo(painter, icono, ic, ROJO_OSCURO if parte == bajo else NEGRO, 22.0)
    painter.setPen(QColor(44, 44, 42))
    painter.drawText(QRectF(m.x() - 40.0, ic.y() + 12.0, 80.0, alto), Qt.AlignCenter, texto)


def rueda_pintar_bajo(painter, cc, bajo, proyeccion: str = "perspective",
                      r: float = RUEDA_R) -> None:
    """Solo lo que cambia con el ratón, encima de la rueda: el tinte de lo
    que tiene debajo; el interruptor, levantado al nivel de los demás."""
    from ._flotante import CHINCHETA_R, relieve_banda
    if bajo is None:
        return
    rb, rc, ri, re = _rueda_radios(r)
    tinte = QColor(ROJO)
    tinte.setAlphaF(0.14)
    fuerte = QColor(ROJO)
    fuerte.setAlphaF(0.30)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(fuerte))
    if bajo == "proyeccion" and bajo in RUEDA_GAJOS:
        i = RUEDA_GAJOS.index(bajo)
        gajo = _rueda_gajo(cc, i, r)
        painter.setBrush(relieve_banda(cc, ri, re))
        painter.drawPath(gajo)
        painter.setPen(QPen(ROJO, 1.3))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(gajo)
        _rueda_contenido(painter, cc, i, bajo, proyeccion, bajo, r)
    elif bajo in PARTIDOS.values() or (bajo in RUEDA_GAJOS and bajo in PARTIDOS):
        gajo = bajo if bajo in RUEDA_GAJOS else next((g for g, o in PARTIDOS.items() if o == bajo), None)
        if gajo in RUEDA_GAJOS:
            for parte, path, _a in rueda_mitades(cc, RUEDA_GAJOS.index(gajo), r):
                if parte == bajo:
                    painter.fillPath(path, QBrush(tinte))
    elif bajo in RUEDA_GAJOS:
        painter.fillPath(_rueda_gajo(cc, RUEDA_GAJOS.index(bajo), r), QBrush(tinte))
    elif bajo == RUEDA_DISCO or (bajo == "modo2d" and disco_partido()):
        disco = QPainterPath()
        disco.addEllipse(cc, rc, rc)
        hueco = QPainterPath()
        hueco.addEllipse(cc, rb, rb)
        if disco_partido():
            mitad = QPainterPath()
            mitad.addRect(QRectF(cc.x() - rc, cc.y() if bajo == "modo2d" else cc.y() - rc, 2.0 * rc, rc))
            disco = disco.intersected(mitad)
        painter.fillPath(disco.subtracted(hueco), QBrush(tinte))
    elif bajo == RUEDA_CIRCULITO:
        painter.drawEllipse(cc, rb, rb)
    elif bajo in RUEDA_TRI:
        painter.drawPath(_rueda_triangulo(cc, RUEDA_TRI[bajo], r))
    elif bajo == "cerrar_rueda":
        q = rueda_centro_cerrar(cc, r)
        painter.drawEllipse(q, ARO_BOTON_R, ARO_BOTON_R)
    elif bajo in RUEDA_BOTONES or (bajo in CAMARA_HERR and abanico_abierto()):
        q = rueda_centro_boton(cc, bajo, r)
        painter.drawEllipse(q, ARO_BOTON_R, ARO_BOTON_R)
    painter.restore()


def _flecha_giro(cc, cual) -> QPainterPath:
    """Flechita curva de deshacer (izquierda) o rehacer (derecha)."""
    from ._flotante import _punta, _trazo
    s = -1.0 if cual == "deshacer" else 1.0
    x, y = cc.x(), cc.y()
    arco = QPainterPath()
    caja = QRectF(x - 4.2, y - 3.6, 8.4, 8.4)
    if s < 0:
        arco.arcMoveTo(caja, -40.0)
        arco.arcTo(caja, -40.0, 220.0)
    else:
        arco.arcMoveTo(caja, 220.0)
        arco.arcTo(caja, 220.0, -220.0)
    negro = _trazo(arco, 1.7)
    return negro.united(_punta(x + s * 4.2, y + 3.4, 0.0, 1.0, 3.4, 2.8))


class Diana:
    def __init__(self, app, al_encuadre=None, al_terminar=None) -> None:
        self.app = app
        self.al_encuadre = al_encuadre
        self.al_terminar = al_terminar
        # Vistas en las que la cámara se quedó quieta (para el zoom previo).
        self._vistas: list = []
        self._cam_ultima = None
        self._cam_desde = 0.0
        self._cam_estable = None
        # Lo que «ocultar el resto» escondió fuera de un grupo abierto.
        self._aislado: list = []

    # -- dónde está cada cosa --
    @staticmethod
    def parte_en(cc, p, buscador: bool = True):
        if cc is None or p is None:
            return None
        dx, dy = p.x() - cc.x(), p.y() - cc.y()
        r = math.hypot(dx, dy)
        if r <= RC:
            return "frente_detras" if dy > 1.0 else "centrar"
        if r <= R + TOLERANCIA:
            return CORONA[_lado(dx, -dy)]
        if r <= R + TRI_FUERA + TOLERANCIA:
            lado = _lado(dx, -dy)
            ang = math.degrees(math.atan2(-dy, dx)) % 360.0
            if abs((ang - _ANGULO[lado] + 180.0) % 360.0 - 180.0) <= 22.0:
                return "vista_" + lado
        for cual in CHICOS:
            q = _centro_ur(cc, cual)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= UR_R + 1.0:
                return cual
        if buscador:
            for cual in FILA:
                q = centro_fila(cc, cual)
                if math.hypot(p.x() - q.x(), p.y() - q.y()) <= FILA_R + 1.5:
                    return cual
        return None

    @staticmethod
    def mascara(cc, buscador: bool = True) -> QPainterPath:
        """Lo que acepta clics (px del visor)."""
        path = QPainterPath()
        path.addEllipse(cc, R + 2.0, R + 2.0)
        for grados in _TRIANGULO.values():
            path.addPath(_triangulo(cc, grados))
        for cual in CHICOS:
            path.addEllipse(_centro_ur(cc, cual), UR_R + 1.0, UR_R + 1.0)
        if buscador:
            for cual in FILA:
                path.addEllipse(centro_fila(cc, cual), FILA_R + 1.0, FILA_R + 1.0)
        return path

    # -- dibujo --
    def pintar(self, painter, cc, bajo=None, para_clic: bool = False,
               buscador: bool = False) -> None:
        """La diana. ``para_clic`` (barra fija) añade un relleno casi
        invisible para que reciba el clic; en el cursor no va (el sistema lo
        pinta negro). ``buscador``: la barra de búsqueda encima."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        fuera = QPainterPath()
        fuera.addEllipse(cc, R, R)
        dentro = QPainterPath()
        dentro.addEllipse(cc, RC, RC)
        if para_clic:
            painter.fillPath(fuera, QBrush(QColor(255, 255, 255, 3)))
        tinte = QColor(ROJO)
        tinte.setAlphaF(0.14)
        # Lo que está bajo el ratón, teñido.
        if bajo in CORONA.values():
            lado = next(k for k, v in CORONA.items() if v == bajo)
            cuarto = QPainterPath()
            cuarto.moveTo(cc)
            cuarto.arcTo(QRectF(cc.x() - R, cc.y() - R, 2 * R, 2 * R),
                         _ANGULO[lado] - 45.0, 90.0)
            cuarto.closeSubpath()
            painter.fillPath(cuarto.subtracted(dentro), QBrush(tinte))
        elif bajo == "centrar":
            mitad = QPainterPath()
            mitad.moveTo(cc)
            mitad.arcTo(QRectF(cc.x() - RC, cc.y() - RC, 2 * RC, 2 * RC), 0.0, 180.0)
            mitad.closeSubpath()
            painter.fillPath(mitad, QBrush(tinte))
        # Las cuatro divisiones en aspa.
        painter.setPen(QPen(SEPARADOR, 1.0))
        for grados in (45.0, 135.0, 225.0, 315.0):
            painter.drawLine(_pt(cc, RC, grados), _pt(cc, R, grados))
        painter.setBrush(Qt.NoBrush)
        for color, ancho in ((HALO, 3.4), (ROJO, 1.6)):
            painter.setPen(QPen(color, ancho))
            painter.drawEllipse(cc, R, R)
            painter.drawEllipse(cc, RC, RC)
        # Glifos de la corona y del centro.
        medio = (R + RC) / 2.0
        for lado, parte in CORONA.items():
            glifo(painter, parte, _pt(cc, medio, _ANGULO[lado]),
                  ROJO_OSCURO if parte == bajo else NEGRO)
        glifo(painter, "centrar", QPointF(cc.x(), cc.y() - 6.5),
              ROJO_OSCURO if bajo == "centrar" else NEGRO, tam=14.0)
        toggle = _toggle(cc)
        painter.setPen(QPen(BLANCO, 1.2))
        painter.setBrush(QBrush(ROJO_OSCURO if bajo == "frente_detras" else ROJO))
        painter.drawPath(toggle)
        # Los triángulos de las vistas, apuntando al centro.
        for parte, grados in _TRIANGULO.items():
            tri = _triangulo(cc, grados)
            painter.setPen(QPen(HALO, 3.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(tri)
            painter.setPen(QPen(ROJO, 1.5))
            painter.setBrush(QBrush(QColor(245, 185, 185) if parte == bajo else BLANCO))
            painter.drawPath(tri)
        # Los botoncitos: deshacer · rehacer | cónica · paralela (la
        # proyección actual, marcada).
        actual = self.proyeccion_actual()
        for cual in CHICOS:
            q = _centro_ur(cc, cual)
            marcado = (cual == "conica" and actual != "parallel"
                       or cual == "paralela" and actual == "parallel")
            painter.setPen(QPen(ROJO, 2.0 if marcado else 1.2))
            painter.setBrush(QBrush(QColor(245, 185, 185) if cual == bajo
                                    else QColor(250, 222, 222) if marcado
                                    else QColor(255, 255, 255, 220)))
            painter.drawEllipse(q, UR_R, UR_R)
            if not _iconos.pintar(painter, cual, q, 13.0):
                forma = (_flecha_giro(q, cual) if cual in ("deshacer", "rehacer")
                         else _proyeccion_glifo(q, cual))
                painter.fillPath(forma, QBrush(ROJO_OSCURO if cual == bajo or marcado
                                               else NEGRO))
        if buscador:
            self._pintar_buscador(painter, cc, bajo)
        painter.restore()

    @staticmethod
    def pintar_bajo(painter, cc, bajo, buscador: bool = False) -> None:
        """Solo el tinte de lo que está bajo el ratón, encima de la diana ya
        pintada (sin ratón): así la barra fija no se repinta entera."""
        if bajo is None:
            return
        tinte = QColor(ROJO)
        tinte.setAlphaF(0.14)
        fuerte = QColor(ROJO)
        fuerte.setAlphaF(0.30)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fuerte))
        if bajo in CORONA.values():
            lado = next(k for k, v in CORONA.items() if v == bajo)
            cuarto = QPainterPath()
            cuarto.moveTo(cc)
            cuarto.arcTo(QRectF(cc.x() - R, cc.y() - R, 2 * R, 2 * R),
                         _ANGULO[lado] - 45.0, 90.0)
            cuarto.closeSubpath()
            dentro = QPainterPath()
            dentro.addEllipse(cc, RC, RC)
            painter.fillPath(cuarto.subtracted(dentro), QBrush(tinte))
        elif bajo == "centrar":
            mitad = QPainterPath()
            mitad.moveTo(cc)
            mitad.arcTo(QRectF(cc.x() - RC, cc.y() - RC, 2 * RC, 2 * RC), 0.0, 180.0)
            mitad.closeSubpath()
            painter.fillPath(mitad, QBrush(tinte))
        elif bajo == "frente_detras":
            painter.fillPath(_toggle(cc), QBrush(QColor(80, 0, 0, 70)))
        elif bajo in _TRIANGULO:
            painter.drawPath(_triangulo(cc, _TRIANGULO[bajo]))
        elif bajo in CHICOS:
            painter.drawEllipse(_centro_ur(cc, bajo), UR_R, UR_R)
        elif buscador and bajo in FILA:
            painter.drawEllipse(centro_fila(cc, bajo), FILA_R, FILA_R)
        painter.restore()

    @staticmethod
    def _pintar_buscador(painter, cc, bajo) -> None:
        """El buscador plegado en su lupa y, sueltos a su altura, el gestor
        de extensiones (cuatro piezas), el gestor de barras (tres barras) y
        Reiniciar (flecha en círculo). La lupa (o teclear) despliega el
        buscador encima de ellos."""
        for cual in FILA:
            c = centro_fila(cc, cual)
            encima = cual == bajo
            painter.setPen(QPen(ROJO, 1.3))
            painter.setBrush(QBrush(QColor(245, 185, 185) if encima
                                    else QColor(255, 255, 255, 235)))
            painter.drawEllipse(c, FILA_R, FILA_R)
            if _iconos.pintar(painter, cual, c, 13.0):
                continue
            tinta = ROJO_OSCURO if encima else NEGRO
            if cual in ("buscar", "reiniciar"):
                painter.save()
                painter.translate(c)
                painter.scale(0.62, 0.62)
                glifo(painter, "buscar" if cual == "buscar" else "rotate",
                      QPointF(0.0, 0.0), tinta)
                painter.restore()
                continue
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(tinta))
            if cual == "ext":
                for dx in (-3.6, 0.6):
                    for dy in (-3.6, 0.6):
                        painter.drawRect(QRectF(c.x() + dx, c.y() + dy, 3.0, 3.0))
            else:
                for dy in (-4.0, -0.75, 2.5):
                    painter.drawRect(QRectF(c.x() - 5.0, c.y() + dy, 10.0, 1.8))

    # -- acciones --
    def usar(self, viewport, parte, cc=None) -> None:
        win = self.app.window
        try:
            if parte == "centrar":
                self._llamar(win, "_on_zoom_extents")
            elif parte == "modo2d" and _edicion.con("modo2d"):
                self.modo_2d(viewport)
            elif parte == "zoom_sel":
                self._llamar(win, "_on_zoom_selection")
            elif parte == "alinear_vista" and _edicion.con("alinear_vista"):
                self.alinear_vista(viewport)
            elif parte == "zoom_previo":
                self.zoom_previo(viewport)
            elif parte == "encuadre":
                if callable(self.al_encuadre):
                    self.al_encuadre(viewport)
            elif parte == "ocultar_resto":
                self.ocultar_resto(viewport)
            elif parte == "frente_detras":
                self._vista(viewport, "back" if self._en_vista(viewport, "front")
                            else "front")
            elif parte in VISTAS:
                self._vista(viewport, VISTAS[parte])
            elif parte == "vista_frontal":
                self._vista(viewport, "front")
            elif parte == "vista_posterior":
                self._vista(viewport, "back")
            elif parte == "sup_inf":
                # El interruptor de la rueda: a la inferior si ya estás en
                # la superior; si no, a la superior.
                self._vista(viewport, "bottom" if self._en_vista(viewport, "top") else "top")
            elif parte == "proyeccion":
                self._proyectar(viewport, "perspective" if self.proyeccion_actual() == "parallel"
                                else "parallel")
            elif parte == "camara":
                # Abre o cierra su abanico; la rueda sigue abierta.
                ABANICO["abierto"] = not ABANICO["abierto"]
            elif parte in CAMARA_HERR:
                ABANICO["abierto"] = False
                self._herramienta(viewport, CAMARA_HERR[parte], NOMBRES[parte])
            elif parte == "seccion":
                self._herramienta(viewport, "section", NOMBRES[parte])
            elif parte in ARO_PROPIAS:
                self._boton_aro(viewport, parte)
            elif parte == "deshacer":
                self._llamar(win, "_on_undo")
            elif parte == "rehacer":
                self._llamar(win, "_on_redo")
            elif parte in ("conica", "paralela"):
                self._proyectar(viewport, "perspective" if parte == "conica"
                                else "parallel")
            elif parte == "buscar":
                self.buscar(viewport, "", cc)
            elif parte == "ext":
                self._llamar(win, "_on_manage_extensions")
            elif parte == "reiniciar":
                from ._reiniciar import reiniciar
                reiniciar(self.app)
            elif parte == "bar":
                gestor = gestor_barras(win)
                if gestor is not None and callable(getattr(gestor, "abrir_master", None)):
                    gestor.abrir_master()
                else:
                    viewport.flash_status(_tr("El gestor de barras no está instalado."), 4000)
        except Exception:  # noqa: BLE001 — la diana nunca rompe la barra
            log.exception("fallo en la diana (%s)", parte)
        viewport.update()
        if callable(self.al_terminar):
            self.al_terminar()

    def alinear_vista(self, viewport) -> None:
        """La cámara de frente a la cara seleccionada (también inclinada o
        dentro de un grupo abierto), en perpendicular, en vista paralela y
        con la cara encuadrada."""
        from PySide6.QtGui import QVector3D
        from core.mesh import Face
        sc = viewport.scene
        caras = [e for e in list(getattr(sc, "selection", None) or ()) if isinstance(e, Face)]
        if not caras:
            viewport.flash_status(_tr("Alinear vista: selecciona una cara."), 4000)
            return
        cara = max(caras, key=lambda f: f.area())     # con varias, la mayor
        n = QVector3D(cara.normal() if callable(cara.normal) else cara.normal)
        c = QVector3D(cara.centroid() if callable(cara.centroid) else cara.centroid)
        m = None
        try:
            m = self.app.window._edit_group_matrix()        # interno: el grupo abierto
        except Exception:  # noqa: BLE001
            m = None
        if m is not None:
            c = m.map(c)
            n = m.mapVector(n)
        if n.lengthSquared() < 1e-12:
            viewport.flash_status(_tr("Alinear vista: la cara no tiene una dirección clara."), 4000)
            return
        n = n.normalized()
        cam = viewport.camera
        ojo = cam.eye() if callable(cam.eye) else cam.eye
        if QVector3D.dotProduct(QVector3D(ojo) - c, n) < 0.0:
            n = -n                               # se mira desde el lado en que estás
        d = cam.distance() if callable(cam.distance) else cam.distance
        d = max(float(d or 0.0), 1.0)
        self._proyectar(viewport, "parallel")
        if not cam.place(c + n * d, c):
            cam.look_from(c + n * d, -n)
        self._llamar(self.app.window, "_on_zoom_selection")
        viewport.update()
        viewport.flash_status(_tr("Vista alineada con la cara, en paralela."), 3000)

    def proyeccion_actual(self) -> str:
        try:
            return proyeccion(self.app.viewport)
        except Exception:  # noqa: BLE001
            return "perspective"

    @staticmethod
    def _proyectar(viewport, modo) -> None:
        poner = getattr(viewport, "set_projection", None)      # interno de 0.5.8
        if callable(poner):
            poner(modo)
        else:
            viewport.camera.perspective = modo != "parallel"
        viewport.flash_status(_tr("Vista cónica." if modo == "perspective"
                              else "Vista paralela."), 2000)

    @staticmethod
    def _llamar(win, nombre) -> None:
        fn = getattr(win, nombre, None)                  # interno de 0.5.8
        if callable(fn):
            fn()

    def _herramienta(self, viewport, nombre, texto) -> None:
        """Activa una herramienta propia de IngeTrazo (cámara, sección)."""
        win = self.app.window
        activar = getattr(win, "_activate_tool", None)          # interno de 0.5.8
        tools = getattr(win, "_tools", None) or {}
        if callable(activar) and nombre in tools:
            activar(nombre)
            viewport.flash_status(_tr(texto) + ".", 2000)
        else:
            viewport.flash_status(_tr("No encontré la orden «{0}» de IngeTrazo.", _tr(texto)), 4000)

    def _boton_aro(self, viewport, parte) -> None:
        """Los botones del aro de la rueda: primero el método interno de la
        ventana (0.5.8) y, si no, la orden de menú por su texto."""
        from ._seleccion import disparar_menu
        win = self.app.window
        metodos = {"ocultar_uno": "_on_hide", "mostrar_ultimo": "_on_unhide_last",
                   "mostrar_todo": "_on_unhide_all", "geometria_oculta": "_on_toggle_hidden_geometry",
                   "objetos_ocultos": "_on_toggle_hidden_objects", "ejes": "_on_axes"}
        textos = {"ocultar_uno": ("Ocultar", "Hide"), "mostrar_ultimo": MOSTRAR_ULTIMO,
                  "mostrar_todo": MOSTRAR_TODO, "geometria_oculta": GEOMETRIA_OCULTA,
                  "objetos_ocultos": OBJETOS_OCULTOS, "ejes": EJES}
        fn = getattr(win, metodos[parte], None)
        if callable(fn):
            fn()
            return
        if parte == "ejes":
            activar = getattr(win, "_activate_tool", None)
            tools = getattr(win, "_tools", None) or {}
            if callable(activar) and "axes" in tools:
                activar("axes")
                return
        if not disparar_menu(win, textos[parte]):
            viewport.flash_status(_tr("No encontré la orden «{0}» de IngeTrazo.", textos[parte][0]), 4000)

    def _vista(self, viewport, nombre) -> None:
        fn = getattr(self.app.window, "_on_standard_view", None)
        if callable(fn):
            fn(nombre)
        else:
            viewport.camera.set_view(nombre)
            viewport.update()
        texto = {"top": "superior", "bottom": "inferior", "right": "derecha",
                 "left": "izquierda", "front": "frontal", "back": "posterior"}
        viewport.flash_status(_tr("Vista {0}.", texto.get(nombre, nombre)), 2000)

    def modo_2d(self, viewport) -> None:
        """Modo 2D: proyección paralela, vista superior y zoom extensión (o,
        con algo seleccionado, zoom a la selección)."""
        win = self.app.window
        self._proyectar(viewport, "parallel")
        self._vista(viewport, "top")
        seleccion = bool(getattr(viewport.scene, "selection", None))
        self._llamar(win, "_on_zoom_selection" if seleccion else "_on_zoom_extents")
        viewport.update()
        viewport.flash_status(_tr("Modo 2D: vista superior en paralela, zoom a la selección.") if seleccion
                              else _tr("Modo 2D: vista superior en paralela, zoom extensión."), 3000)

    @staticmethod
    def _en_vista(viewport, nombre) -> bool:
        cam = viewport.camera
        preset = getattr(type(cam), "_STANDARD_VIEWS", {}).get(nombre)
        if preset is None:
            return False
        yaw, pitch = preset
        dy = (cam.yaw - yaw + math.pi) % (2.0 * math.pi) - math.pi
        return abs(dy) < 1e-3 and abs(cam.pitch - pitch) < 1e-3

    def ocultar_resto(self, viewport) -> None:
        """Dentro de un grupo abierto: «Ocultar el resto del modelo» de
        IngeTrazo (Alt+Q). Fuera: esconde todo menos la selección, y el
        siguiente clic lo vuelve a mostrar (un paso de deshacer cada vez)."""
        scene = viewport.scene
        win = self.app.window
        if getattr(scene, "edit_group", None) is not None:
            self._llamar(win, "_on_toggle_hide_rest")
            return
        from core.history import HideCommand
        # Lo último que se escondió sigue oculto (también tras deshacer el
        # «mostrar»): este clic lo vuelve a mostrar.
        vuelven = [e for e in self._aislado if self._oculta(e)]
        if vuelven:
            viewport.history.execute(HideCommand(vuelven, hidden=False))
            viewport.notify_scene_changed()
            viewport.flash_status(_tr("Resto del modelo visible."), 2500)
            return
        sel = list(scene.selection)
        if not sel:
            viewport.flash_status(_tr("Selecciona algo primero: se ocultará todo lo "
                                  "demás."), 4000)
            return
        elegidos = {id(e) for e in sel}
        vertices = set()
        for e in sel:
            for v in getattr(e, "vertices", None) or ():
                vertices.add((round(v.x(), 6), round(v.y(), 6), round(v.z(), 6)))

        def suyo(arista) -> bool:
            return all((round(q.x(), 6), round(q.y(), 6), round(q.z(), 6)) in vertices
                       for q in (arista.a, arista.b))

        esconder = [g for g in scene.groups if id(g) not in elegidos and not self._oculta(g)]
        esconder += [f for f in scene.mesh.faces
                     if id(f) not in elegidos and not self._oculta(f)]
        esconder += [a for a in scene.mesh.edges
                     if id(a) not in elegidos and not self._oculta(a) and not suyo(a)]
        if not esconder:
            viewport.flash_status(_tr("No hay nada más que ocultar."), 2500)
            return
        viewport.history.execute(HideCommand(esconder, hidden=True))
        viewport.notify_scene_changed()
        self._aislado = esconder
        viewport.flash_status(_tr("Resto del modelo oculto ({0}); vuelve a pulsar para mostrarlo.", len(esconder)), 4000)

    @staticmethod
    def _oculta(e) -> bool:
        if getattr(e, "hidden", False):
            return True
        attrs = getattr(e, "attrs", None)
        return bool(attrs and attrs.get("hidden"))

    def buscar(self, viewport, texto: str = "", cc=None) -> None:
        """El buscador de órdenes de IngeTrazo, con ``texto`` ya escrito y
        colocado sobre la barra de búsqueda de la diana."""
        from views.command_search import open_search      # interno de 0.5.8
        caja = open_search(self.app.window, texto)
        if caja is None or cc is None:
            return
        try:
            # Centrado sobre la barra de búsqueda, con la lista hacia abajo.
            r = rect_buscador(cc)
            mover_a(caja, viewport.mapToGlobal(QPoint(round(r.center().x() - caja.width() / 2.0),
                                                  round(r.top()))))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo colocar el buscador")

    # -- vistas anteriores (zoom previo) --
    def _clave_camara(self):
        cam = self.app.viewport.camera
        t = cam.target
        return (round(t.x(), 5), round(t.y(), 5), round(t.z(), 5),
                round(cam.distance, 5), round(cam.yaw, 6), round(cam.pitch, 6),
                bool(cam.perspective), bool(getattr(cam, "two_point", False)),
                round(float(getattr(cam, "fov_deg", 45.0)), 4))

    def vigilar(self) -> None:
        """Guarda cada vista en la que la cámara se queda quieta un momento:
        son las «vistas anteriores» del zoom previo."""
        try:
            k = self._clave_camara()
        except Exception:  # noqa: BLE001
            return
        ahora = time.monotonic()
        if k != self._cam_ultima:
            self._cam_ultima, self._cam_desde = k, ahora
            return
        if ahora - self._cam_desde < QUIETA_CAMARA_S or k == self._cam_estable:
            return
        if self._cam_estable is not None:
            self._vistas.append(self._cam_estable)
            del self._vistas[:-MAX_VISTAS]
        self._cam_estable = k

    def zoom_previo(self, viewport) -> None:
        if not self._vistas:
            viewport.flash_status(_tr("No hay una vista anterior."), 3000)
            return
        k = self._vistas.pop()
        cam = viewport.camera
        cam.target = QVector3D(k[0], k[1], k[2])
        cam.distance, cam.yaw, cam.pitch = k[3], k[4], k[5]
        cam.perspective = k[6]
        if hasattr(cam, "two_point"):
            cam.two_point = k[7]
        if hasattr(cam, "fov_deg"):
            cam.fov_deg = k[8]
        sincronizar = getattr(viewport, "_sync_projection", None)
        if callable(sincronizar):
            try:
                sincronizar()
            except Exception:  # noqa: BLE001
                log.exception("_sync_projection falló")
        # Esta vista vuelve a ser la actual: no se guarda otra vez.
        self._cam_estable = self._cam_ultima = k
        self._cam_desde = time.monotonic()
        viewport.update()
        viewport.flash_status(_tr("Vista anterior ({0} más).", len(self._vistas)), 2500)

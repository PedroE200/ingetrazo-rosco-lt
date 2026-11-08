# SPDX-License-Identifier: GPL-3.0-or-later
"""Piezas comunes de la barra de dibujo y la barra de modificar (el mismo archivo va en las dos).

- ``cursor_compuesto``: mientras el ratón se mueve, la barra es parte del
  propio cursor del sistema, con el puntero de la herramienta en su centro.
  La dibuja el sistema operativo, así que va exactamente con el ratón.
- ``Flotante``: cuando el ratón se para, la barra se queda fija en una
  ventanita propia, transparente y sin marco, para poder hacer clic en sus
  botones. Solo la banda, el rótulo y los paneles aceptan clics (máscara);
  el resto deja pasar el clic al modelo. No toma el foco: el teclado sigue en
  el visor.
- La banda semicircular transparente con contorno rojo.
- Los glifos: siluetas negras macizas con detalles en blanco y un halo
  blanco fino para leerse sobre cualquier fondo.

El dueño (la barra de cada plugin) implementa ``pintar(painter)`` en
coordenadas del visor y ``raton_movido(p)``, ``raton_clic(p)``,
``raton_fuera()`` con ``p`` en coordenadas del visor.
"""
from __future__ import annotations

from ._idioma import _tr
import logging
import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QFontMetricsF, QLinearGradient, QPainter,
    QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF, QRadialGradient,
    QRegion, QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

log = logging.getLogger("ingetrazo.plugins.flotante")


ROJO = QColor(214, 34, 34)
NEGRO = QColor(17, 17, 17)
GRIS = QColor(150, 150, 146)
PERFIL_SUPRIMIR = QColor(214, 34, 34)  # el glifo de Suprimir, con perfil rojo (fijo, sin paleta)
ROJO_OSCURO = QColor(150, 18, 18)
HALO = QColor(255, 255, 255, 235)
# Las divisiones, opacas: en el cursor de Windows lo semitransparente sale oscuro.
SEPARADOR = QColor(228, 130, 130)
BLANCO = QColor(255, 255, 255)
ROSA_CLARO = QColor(251, 228, 228)     # el fondo del botón activo rayado (relieve)
R_ESQUINA = 6.0
PULSACION_MS = 350                     # pulsación larga sobre un botón: ver el modelo
ARRASTRE_PX = 6.0                      # … o arrastrar más que esto con el botón pulsado


# ---- Los temas de color (C a N) -------------------------------------------------
# Todas las piezas importan ROJO, ROJO_OSCURO, SEPARADOR y ROSA_CLARO por
# nombre: ``poner_paleta`` los cambia en su sitio al color del tema (y los
# devuelve al rojo sin paleta). La paleta queda en PALETA para los glifos de
# líneas y sombreado y el contorno degradado de las mezclas y de N.
PALETA = None                          # _temas.Paleta o None
_DE_SERIE = [(q, QColor(q)) for q in (ROJO, ROJO_OSCURO, SEPARADOR, ROSA_CLARO)]
# El centro del anillo y su radio en píxeles del dispositivo (para N); lo
# pone la barra antes de pintarse (``fijar_centro``).
_CENTRO = None
CHICO_R_ANILLO = 9.5                   # = _temas.CHICO_R: los botoncitos del anillo


def mezcla(a, b, t: float) -> QColor:
    """De ``a`` (t = 0) a ``b`` (t = 1)."""
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def poner_paleta(paleta) -> None:
    global PALETA
    PALETA = paleta
    if paleta is None:
        for q, color in _DE_SERIE:
            q.setRgb(color.red(), color.green(), color.blue())
        return
    medio = (mezcla(paleta.borde, paleta.borde2, 0.5) if paleta.borde2
             else QColor(paleta.borde))
    for q, color in ((ROJO, medio), (ROJO_OSCURO, QColor(paleta.acento)),
                     (SEPARADOR, QColor(paleta.div)), (ROSA_CLARO, mezcla(BLANCO, medio, 0.12))):
        q.setRgb(color.red(), color.green(), color.blue())


def fijar_centro(painter, c, radio: float) -> None:
    """El anillo que se va a pintar: centro ``c`` y ``radio`` (hasta el
    borde de los botoncitos), en coordenadas del pintor."""
    global _CENTRO
    t = painter.transform()
    d = t.map(QPointF(c))
    _CENTRO = (d.x(), d.y(), radio * (math.hypot(t.m11(), t.m12()) or 1.0))


def _t_radial(painter, q) -> float:
    """N: 0 junto a la diana, 1 en el borde de los botoncitos."""
    if _CENTRO is None:
        return 1.0
    x, y, r = _CENTRO
    d = painter.transform().map(QPointF(q))
    return max(0.0, min(1.0, (math.hypot(d.x() - x, d.y() - y) - 0.2 * r) / (0.8 * r)))


def color_linea(painter, q) -> QColor:
    """El color de las líneas de un glifo en ``q`` (N: según su distancia a
    la diana, en ocho pasos)."""
    p = PALETA
    if p is None:
        return QColor(NEGRO)
    if p.radial:
        return mezcla(p.borde, p.borde2, round(_t_radial(painter, q) * 8.0) / 8.0)
    return QColor(p.linea)


def brocha_borde(painter, claro: bool = False) -> QBrush:
    """El contorno del anillo (``claro``: sus divisiones): el color del tema
    o, en las mezclas y en N, su degradado alrededor del centro fijado."""
    p = PALETA
    if p is None or not p.borde2 or _CENTRO is None:
        return QBrush(SEPARADOR if claro else ROJO)
    inversa, ok = painter.transform().inverted()
    x, y, r = _CENTRO
    c = inversa.map(QPointF(x, y)) if ok else QPointF(x, y)
    r = r / (math.hypot(painter.transform().m11(), painter.transform().m12()) or 1.0)
    a, b = QColor(p.borde), QColor(p.borde2)
    if claro:
        a, b = mezcla(a, BLANCO, 0.45), mezcla(b, BLANCO, 0.45)
    if p.radial:
        g = QRadialGradient(c, r)
        g.setColorAt(0.0, a)
        g.setColorAt(0.2, a)
    else:
        g = QLinearGradient(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        g.setColorAt(0.0, a)
    g.setColorAt(1.0, b)
    return QBrush(g)


def pluma_borde(painter, ancho: float, claro: bool = False) -> QPen:
    pen = QPen(brocha_borde(painter, claro), ancho)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def relleno_redondo(bajo: bool) -> QColor:
    """El fondo de un botoncito bajo el ratón (``bajo``) o marcado."""
    if PALETA is None:
        return QColor(245, 185, 185) if bajo else QColor(250, 222, 222)
    return mezcla(BLANCO, ROJO, 0.30 if bajo else 0.15)


# ---- La ventanita ---------------------------------------------------------------

class Flotante(QWidget):
    """Ventana de herramientas translúcida; su punto ``ancla_local`` se coloca
    sobre el ancla de la barra (en coordenadas del visor)."""

    def __init__(self, dueno, ventana, viewport, ancho: int, alto: int,
                 ancla_local: QPointF) -> None:
        flags = (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
                 | Qt.NoDropShadowWindowHint)
        super().__init__(ventana, flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.resize(int(ancho), int(alto))
        self.dueno = dueno
        self.vp = viewport
        self.ancla_local = QPointF(ancla_local)
        self.origen = QPointF(0.0, 0.0)          # esquina sup. izq. en px del visor
        self._mascara_clave = None
        # El clic se da al soltar: mantener pulsado (PULSACION_MS) sobre un
        # botón, o arrastrar con el botón pulsado, vuelve la ventanita
        # transparente para ver el modelo debajo, y al soltar no cuenta como
        # clic. Mientras dura, la barra no se entera del ratón: no se suelta
        # ni reaparece hasta soltar, aunque el ratón salga de ella.
        self._pulsando = None
        self._larga = False
        # Transparente = no se pinta (nada de ``setWindowOpacity``: con la
        # transparencia por píxel, al volver a 1 a veces no se repintaba y
        # la barra no reaparecía al soltar).
        self._transparente = False
        self._reloj_pulsacion = QTimer(self)
        self._reloj_pulsacion.setSingleShot(True)
        self._reloj_pulsacion.setInterval(PULSACION_MS)
        self._reloj_pulsacion.timeout.connect(self._pulsacion_larga)

    # -- posición --
    def colocar(self, ancla_vp: QPointF) -> None:
        self.origen = QPointF(ancla_vp.x() - self.ancla_local.x(),
                              ancla_vp.y() - self.ancla_local.y())
        destino = self.vp.mapToGlobal(QPoint(round(self.origen.x()),
                                             round(self.origen.y())))
        # La posición real, redondeada, para que lo pintado cuadre al píxel.
        local = self.vp.mapFromGlobal(destino)
        self.origen = QPointF(local.x(), local.y())
        if self.pos() != destino:
            self.move(destino)

    def a_visor(self, local) -> QPointF:
        return QPointF(local) + self.origen

    def fijar_mascara(self, path_visor: QPainterPath, clave=None) -> None:
        """Solo ``path_visor`` (en px del visor) acepta clics. ``clave``
        evita rehacer la región si no ha cambiado."""
        if clave is not None and clave == self._mascara_clave:
            return
        self._mascara_clave = clave
        trazo = QPainterPathStroker()
        trazo.setWidth(6.0)
        local = path_visor.translated(-self.origen.x(), -self.origen.y())
        # La forma y su contorno de 6 px (la tolerancia del clic) se suman
        # como regiones: unir los trazados (``united``) tardaba décimas de
        # segundo con el anillo entero.
        region = QRegion()
        for forma in (local, trazo.createStroke(local)):
            for poligono in forma.toFillPolygons():
                region = region.united(QRegion(poligono.toPolygon(), Qt.WindingFill))
        if region.isEmpty():
            region = QRegion(0, 0, 1, 1)
        self.setMask(region)

    # -- pintura --
    def paintEvent(self, ev) -> None:  # noqa: N802 — nombre de Qt
        p = QPainter(self)
        try:
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            if self._transparente:
                return                       # pulsación larga: se ve el modelo
            p.setRenderHint(QPainter.Antialiasing)
            p.translate(-self.origen.x(), -self.origen.y())
            self.dueno.pintar(p)
        except Exception:  # noqa: BLE001 — un fallo de dibujo no rompe nada
            log.exception("fallo al pintar la barra flotante")
        finally:
            p.end()

    # -- ratón --
    @property
    def pulsando(self) -> bool:
        """El botón izquierdo sigue pulsado sobre la barra."""
        return self._pulsando is not None

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        p = self.a_visor(ev.position())
        if self._pulsando is not None:
            if (not self._larga and self._con_pulsacion()
                    and math.hypot(p.x() - self._pulsando.x(),
                                   p.y() - self._pulsando.y()) > ARRASTRE_PX):
                self._reloj_pulsacion.stop()
                self._pulsacion_larga()      # arrastrar también es «ver el modelo»
            return
        self._seguro(self.dueno.raton_movido, p)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.RightButton and hasattr(self.dueno, "raton_derecho"):
            ev.accept()                      # sobre el rosco: un paso atrás
            self._seguro(self.dueno.raton_derecho, self.a_visor(ev.position()))
            return
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return
        ev.accept()
        self._pulsando = self.a_visor(ev.position())
        self._larga = False
        if self._con_pulsacion():
            self._reloj_pulsacion.start()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() != Qt.LeftButton or self._pulsando is None:
            ev.ignore()
            return
        ev.accept()
        p, self._pulsando = self._pulsando, None
        self._reloj_pulsacion.stop()
        if self._larga:
            # Fue una pulsación larga, no un clic: la barra vuelve.
            self._fin_pulsacion_larga()
            self._al_soltar(self.a_visor(ev.position()))
            return
        self._seguro(self.dueno.raton_clic, p)

    @staticmethod
    def _opcion(clave: str) -> bool:
        """Opciones ▸ Mantener pulsado un botón (encendidas de serie)."""
        try:
            from ._seleccion import opcion
            return opcion(clave)
        except Exception:  # noqa: BLE001
            return True

    def _con_pulsacion(self) -> bool:
        """Mantener pulsado hace algo: ver el modelo."""
        return self._opcion("pulsacion_ver")

    def _pulsacion_larga(self) -> None:
        if self._pulsando is None or not self._con_pulsacion():
            return
        self._larga = True
        self.grabMouse()                     # que el soltar llegue aunque se vea el modelo
        if self._opcion("pulsacion_ver"):
            self._transparente = True        # ver el modelo hasta soltar
            self.update()

    def _fin_pulsacion_larga(self) -> None:
        self._larga = False
        self._pulsando = None
        try:
            self.releaseMouse()
        except Exception:  # noqa: BLE001
            pass
        if self._transparente:
            self._transparente = False
            self.update()                    # vuelve a verse en cuanto se suelta

    def vigilar_pulsacion(self) -> None:
        """Del reloj del dueño: si el soltar se perdió (la ventana
        transparente a veces no lo recibe), con el botón ya suelto vuelve
        (sin clic)."""
        if self._pulsando is not None and not (QApplication.mouseButtons() & Qt.LeftButton):
            larga = self._larga
            self._reloj_pulsacion.stop()
            self._fin_pulsacion_larga()
            p = self.a_visor(QPointF(self.mapFromGlobal(QCursor.pos())))
            if larga:
                self._al_soltar(p)
            else:
                self._seguro(self.dueno.raton_movido, p)

    def _al_soltar(self, p: QPointF) -> None:
        """Fin de la pulsación larga: el dueño decide dónde vuelve (el rosco,
        centrado en el cursor); si no dice nada, mira dónde está el ratón."""
        soltada = getattr(self.dueno, "pulsacion_soltada", None)
        self._seguro(soltada if soltada is not None else self.dueno.raton_movido, p)

    def ver_modelo(self, si: bool) -> None:
        """La barra deja de pintarse (se ve el modelo) o vuelve a verse."""
        if self._transparente != bool(si):
            self._transparente = bool(si)
            self.update()

    def hideEvent(self, ev) -> None:  # noqa: N802
        self._transparente = False           # nunca se queda sin pintarse
        if self._larga or self._pulsando is not None:
            self._reloj_pulsacion.stop()
            self._fin_pulsacion_larga()      # nunca se queda transparente
        super().hideEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        doble = getattr(self.dueno, "raton_doble", None)
        if ev.button() == Qt.LeftButton and doble is not None:
            try:
                hecho = bool(doble(self.a_visor(ev.position())))
            except Exception:  # noqa: BLE001
                log.exception("fallo en el doble clic de la barra")
                hecho = False
            if hecho:
                ev.accept()
                return
        self.mousePressEvent(ev)            # dos clics rápidos = dos clics

    def leaveEvent(self, ev) -> None:  # noqa: N802
        if self._pulsando is None:           # con el botón pulsado, hasta soltar
            self._seguro(self.dueno.raton_fuera)

    def wheelEvent(self, ev) -> None:  # noqa: N802
        """La rueda sobre la barra sigue haciendo zoom en el visor (sobre la
        ayuda que no cabe entera, la desplaza)."""
        try:
            pos = self.vp.mapFromGlobal(ev.globalPosition().toPoint())
            desplazar = getattr(self.dueno, "raton_rueda", None)
            if callable(desplazar) and desplazar(QPointF(pos), ev.angleDelta().y()):
                return
            copia = QWheelEvent(QPointF(pos), ev.globalPosition(), ev.pixelDelta(),
                                ev.angleDelta(), ev.buttons(), ev.modifiers(),
                                ev.phase(), ev.inverted())
            QApplication.sendEvent(self.vp, copia)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo pasar la rueda al visor")

    @staticmethod
    def _seguro(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 — un fallo nunca bloquea el ratón
            log.exception("fallo en la barra flotante")


def app_activa() -> bool:
    return QApplication.applicationState() == Qt.ApplicationActive


# ---- El arco como cursor ---------------------------------------------------------------
# Mientras el ratón se mueve, la banda es parte del propio cursor: lo dibuja el
# sistema, así que va exactamente con el ratón (sin retraso) y el puntero
# queda siempre en el centro del arco.

def _cursor_herramienta(tool):
    """El cursor nativo de ``tool`` (lápiz, cubo…), o None."""
    icono = getattr(tool, "icon", None)
    if not icono:
        return None
    try:
        from views.icons import tool_cursor
        cur = tool_cursor(icono, bool(getattr(tool, "cursor_plus", False)))
    except Exception:  # noqa: BLE001
        return None
    if cur is None or cur.pixmap().isNull():
        return None
    return cur


def _flecha(painter, c: QPointF) -> None:
    """Una flecha de ratón con la punta en ``c``."""
    path = _poli([(c.x(), c.y()), (c.x(), c.y() + 17), (c.x() + 4.5, c.y() + 13),
                  (c.x() + 7.5, c.y() + 19.5), (c.x() + 10, c.y() + 18.5),
                  (c.x() + 7, c.y() + 12), (c.x() + 12.5, c.y() + 12)])
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(NEGRO, 1.1))
    painter.setBrush(QBrush(BLANCO))
    painter.drawPath(path)
    painter.restore()


def cursor_compuesto(viewport, tool, dibujar, medio: float, arriba: float,
                     abajo: float = 40.0, puntero=None) -> QCursor:
    """Un cursor con la barra dibujada por ``dibujar(painter, centro)`` y, en
    el centro (el punto activo), el cursor propio de ``tool`` (o
    ``puntero``, un QCursor, si se da)."""
    dpr = max(1.0, float(viewport.devicePixelRatioF()))
    w, h = 2.0 * medio, arriba + abajo
    pm = QPixmap(int(math.ceil(w * dpr)), int(math.ceil(h * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(medio, arriba)
        dibujar(p, c)
        base = puntero if puntero is not None else _cursor_herramienta(tool)
        if base is not None:
            punto = base.hotSpot()
            p.drawPixmap(QPointF(c.x() - punto.x(), c.y() - punto.y()), base.pixmap())
        else:
            _flecha(p, c)
    finally:
        p.end()
    return QCursor(pm, int(round(medio)), int(round(arriba)))


def restaurar_cursor(viewport) -> None:
    """Devuelve al visor el cursor de su herramienta activa."""
    aplicar = getattr(viewport, "_apply_tool_cursor", None)    # interno de 0.5.8
    if callable(aplicar):
        try:
            aplicar()
            return
        except Exception:  # noqa: BLE001
            log.exception("_apply_tool_cursor falló")
    viewport.unsetCursor()


# ---- La banda semicircular ----------------------------------------------------------

def _pt(c, r, grados) -> QPointF:
    a = math.radians(grados)
    return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))


def sector(c, r_int, r_ext, a0, barrido, esquina: float = R_ESQUINA) -> QPainterPath:
    """Trozo de corona circular entre ``a0`` y ``a0 + barrido`` grados
    (0 = derecha, 90 = arriba, como en Qt), con las esquinas redondeadas."""
    a1 = a0 + barrido
    fuera = QRectF(c.x() - r_ext, c.y() - r_ext, 2.0 * r_ext, 2.0 * r_ext)
    dentro = QRectF(c.x() - r_int, c.y() - r_int, 2.0 * r_int, 2.0 * r_int)
    rc = max(0.0, min(esquina, (r_ext - r_int) / 2.0 - 0.5,
                      r_int * math.sin(math.radians(barrido) / 2.0) - 0.5))
    path = QPainterPath()
    if rc < 0.5:
        path.arcMoveTo(fuera, a0)
        path.arcTo(fuera, a0, barrido)
        path.arcTo(dentro, a1, -barrido)
        path.closeSubpath()
        return path
    do = math.degrees(math.asin(rc / (r_ext - rc)))
    di = math.degrees(math.asin(rc / (r_int + rc)))
    lo = math.sqrt((r_ext - rc) ** 2 - rc ** 2)
    li = math.sqrt((r_int + rc) ** 2 - rc ** 2)
    path.moveTo(_pt(c, r_ext, a0 + do))
    path.arcTo(fuera, a0 + do, barrido - 2.0 * do)
    path.quadTo(_pt(c, r_ext, a1), _pt(c, lo, a1))
    path.lineTo(_pt(c, li, a1))
    path.quadTo(_pt(c, r_int, a1), _pt(c, r_int, a1 - di))
    path.arcTo(dentro, a1 - di, -(barrido - 2.0 * di))
    path.quadTo(_pt(c, r_int, a0), _pt(c, li, a0))
    path.lineTo(_pt(c, lo, a0))
    path.quadTo(_pt(c, r_ext, a0), _pt(c, r_ext, a0 + do))
    path.closeSubpath()
    return path


def centro_boton(c, r_int, r_ext, i, n, a0: float = 0.0, barrido: float = 180.0) -> QPointF:
    paso = barrido / n
    return _pt(c, (r_int + r_ext) / 2.0, a0 + barrido - paso * (i + 0.5))


def boton_en(c, p, r_int, r_ext, claves, tolerancia: float = 2.0,
             a0: float = 0.0, barrido: float = 180.0):
    """La clave del trozo de banda bajo ``p``, o None. La banda va de ``a0``
    a ``a0 + barrido`` grados (por defecto, el semicírculo de arriba)."""
    if c is None or p is None:
        return None
    dx, dy = p.x() - c.x(), c.y() - p.y()       # dy > 0 = por encima
    r = math.hypot(dx, dy)
    if r < r_int - tolerancia or r > r_ext + tolerancia:
        return None
    ang = math.degrees(math.atan2(dy, dx))      # 0 = der., 90 = arriba
    # A menos de media vuelta del centro de la banda (vale también para
    # las de la mitad de abajo, de 180 a 360 grados).
    medio = a0 + barrido / 2.0
    while ang - medio > 180.0:
        ang -= 360.0
    while ang - medio <= -180.0:
        ang += 360.0
    margen = math.degrees(tolerancia / max(r, 1.0))
    if ang < a0 - margen or ang > a0 + barrido + margen:
        return None
    i = int((a0 + barrido - ang) // (barrido / len(claves)))
    return claves[min(max(i, 0), len(claves) - 1)]


# ---- Relieve: volumen, sombra y rayado -------------------------------------------------

def relieve_redondo(q, r) -> QBrush:
    """El relleno con volumen de un botón redondo: luz arriba a la izquierda."""
    g = QRadialGradient(QPointF(q.x() - r * 0.35, q.y() - r * 0.35), r * 1.6)
    g.setColorAt(0.0, BLANCO)
    g.setColorAt(0.5, QColor(240, 240, 236))
    g.setColorAt(1.0, QColor(168, 168, 160))
    return QBrush(g)


def relieve_banda(c, r_int, r_ext) -> QBrush:
    """El relleno con volumen de una banda (o un gajo): clara por dentro y
    más oscura hacia fuera, como si fuera convexa."""
    g = QRadialGradient(c, r_ext)
    g.setColorAt(0.0, BLANCO)
    g.setColorAt(max(0.0, min(0.9, r_int / r_ext)), BLANCO)
    g.setColorAt(max(0.0, min(0.97, (r_int / r_ext + 1.0) / 2.0)), QColor(236, 236, 232))
    g.setColorAt(1.0, QColor(166, 166, 158))
    return QBrush(g)


def hundido_banda(c, r_int, r_ext) -> QBrush:
    """El relleno de un botón hundido (un interruptor): oscuro en los
    bordes y claro en medio, como una depresión."""
    g = QRadialGradient(c, r_ext)
    g.setColorAt(max(0.0, min(0.9, r_int / r_ext)), QColor(150, 150, 144))
    g.setColorAt(max(0.0, min(0.95, (r_int / r_ext + 1.0) / 2.0)), QColor(244, 244, 240))
    g.setColorAt(1.0, QColor(130, 130, 124))
    return QBrush(g)


def sombra(painter, path: QPainterPath, dx: float = 2.0, dy: float = 3.0) -> None:
    """Una sombra suave bajo ``path`` (solo en las ventanitas: en el cursor
    lo semitransparente sale negro)."""
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(0, 0, 0, 55)))
    painter.drawPath(path.translated(dx, dy))
    painter.restore()


def rayar(painter, path: QPainterPath, color=None, paso: float = 5.0, ancho: float = 2.0) -> None:
    """Raya ``path`` en diagonal (a 45°) con líneas de ``ancho`` px cada
    ``paso`` px: el botón activo."""
    r = path.boundingRect()
    painter.save()
    painter.setClipPath(path, Qt.IntersectClip)
    painter.setPen(QPen(color or ROJO, ancho))
    alto = r.height()
    x = r.left() - alto
    while x <= r.right():
        painter.drawLine(QPointF(x, r.bottom()), QPointF(x + alto, r.top()))
        x += paso
    painter.restore()


def dibujar_banda(painter, c, r_int, r_ext, claves, activa=None, bajo=None,
                  apagadas=(), para_clic: bool = True, colores=None,
                  a0: float = 0.0, barrido: float = 180.0, tam: float = 24.0,
                  relieve: bool = False) -> None:
    """Banda transparente con contorno rojo, sus divisiones y los glifos.
    ``para_clic`` (ventanita fija) añade un relleno casi invisible para que
    toda la banda reciba el clic; en el cursor NO va: Windows convierte esos
    píxeles casi transparentes en negro opaco. Ocupa de ``a0`` a ``a0 +
    barrido`` grados (por defecto, el semicírculo de arriba). ``relieve``:
    banda opaca con volumen, divisiones en bisel y el botón activo relleno y
    rayado (todo opaco: vale también en el cursor)."""
    n = len(claves)
    paso = barrido / n
    # ``activa``: una clave o varias (p. ej. la herramienta y «grupo»).
    activas = {activa} if isinstance(activa, str) else set(activa or ())
    painter.setRenderHint(QPainter.Antialiasing)
    if PALETA is not None:
        # El degradado del contorno va alrededor de este anillo (la barra de dibujo ya lo
        # ha fijado; la barra de modificar y las vistas previas, no).
        d = painter.transform().map(QPointF(c))
        if _CENTRO is None or math.hypot(d.x() - _CENTRO[0], d.y() - _CENTRO[1]) > 1.0:
            fijar_centro(painter, c, r_ext + 2.0 * CHICO_R_ANILLO + 3.0)
    entera = sector(c, r_int, r_ext, a0, barrido)
    painter.setPen(Qt.NoPen)
    if relieve:
        if para_clic:
            sombra(painter, entera)      # en la ventanita, no en el cursor
        painter.setBrush(relieve_banda(c, r_int, r_ext))
        painter.drawPath(entera)
    elif para_clic:
        painter.setBrush(QBrush(QColor(255, 255, 255, 3)))
        painter.drawPath(entera)
    for i, clave in enumerate(claves):
        if relieve and clave in activas:
            trozo = sector(c, r_int, r_ext, a0 + barrido - paso * (i + 1), paso)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(ROSA_CLARO))
            painter.drawPath(trozo)
            rayar(painter, trozo)
            # El rayado no pisa el icono: un círculo limpio debajo.
            painter.setBrush(QBrush(BLANCO))
            painter.drawEllipse(centro_boton(c, r_int, r_ext, i, n, a0, barrido),
                                tam * 0.62, tam * 0.62)
        if clave == bajo or (PALETA is not None and para_clic and clave in activas):
            # Temas de color: el activo lleva un velo (solo en la ventanita).
            tinte = QColor(ROJO)
            tinte.setAlphaF(0.14 if clave == bajo and PALETA is None
                            else 0.12 if clave == bajo and clave not in activas else 0.22)
            painter.setBrush(QBrush(tinte))
            painter.drawPath(sector(c, r_int, r_ext, a0 + barrido - paso * (i + 1), paso))
    painter.setBrush(Qt.NoBrush)
    for i in range(1, n):
        a = a0 + barrido - paso * i
        if relieve:
            # En bisel: una línea oscura y, pegada, otra clara.
            painter.setPen(QPen(QColor(120, 120, 114), 1.4))
            painter.drawLine(_pt(c, r_int, a), _pt(c, r_ext, a))
            painter.setPen(QPen(BLANCO, 1.4))
            painter.drawLine(_pt(c, r_int, a - 1.1), _pt(c, r_ext, a - 1.1))
        else:
            painter.setPen(pluma_borde(painter, 1.0, claro=True))
            painter.drawLine(_pt(c, r_int, a), _pt(c, r_ext, a))
    if relieve:
        # Biseles de los bordes: luz en el de dentro, sombra en el de fuera.
        painter.setBrush(Qt.NoBrush)
        for radio, color in ((r_int + 1.5, BLANCO), (r_ext - 1.5, QColor(112, 112, 106))):
            pen = QPen(color, 2.0)
            painter.setPen(pen)
            caja = QRectF(c.x() - radio, c.y() - radio, 2.0 * radio, 2.0 * radio)
            arco = QPainterPath()
            arco.arcMoveTo(caja, a0)
            arco.arcTo(caja, a0, barrido)
            painter.drawPath(arco)
    pen = QPen(HALO, 3.4)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(entera)
    painter.setPen(pluma_borde(painter, 1.6))
    painter.drawPath(entera)
    colores = colores or {}
    for i, clave in enumerate(claves):
        color = colores.get(clave)
        if color is not None and para_clic:
            # Un botón con estado de color (p. ej. Grupo: rojo / azul). En el
            # cursor no: Windows pinta oscuro lo semitransparente.
            tinte = QColor(color)
            tinte.setAlphaF(0.20)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(tinte))
            painter.drawPath(sector(c, r_int, r_ext, a0 + barrido - paso * (i + 1), paso))
            painter.setBrush(Qt.NoBrush)
        if clave in activas or color is not None:
            if color is not None:
                pen = QPen(color, 2.6)
                pen.setJoinStyle(Qt.RoundJoin)
            else:
                pen = pluma_borde(painter, 2.6)
            painter.setPen(pen)
            painter.drawPath(sector(c, r_int, r_ext, a0 + barrido - paso * (i + 1), paso, 4.0))
    for i, clave in enumerate(claves):
        if clave in apagadas:
            tinta = GRIS
        elif colores.get(clave) is not None:
            tinta = colores[clave]
        elif clave in activas or clave == bajo:
            tinta = ROJO_OSCURO
        else:
            tinta = NEGRO
        glifo(painter, clave, centro_boton(c, r_int, r_ext, i, n, a0, barrido), tinta, tam)


# ---- Chincheta y cerrar: anclar la barra ------------------------------------------------
# Dos botoncitos en lo alto de la barra fija: la chincheta la deja anclada
# (fija y visible, no sigue al ratón) y, a su lado, ✕ la cierra (y la
# desancla). La barra de dibujo pone ahí Pantalla limpia (``segundo="limpia"``) y lleva
# su ✕ junto al cursor.
CHINCHETA_R = 8.5
CHINCHETA_DX = 11.0                     # del centro de la barra a cada botón


def centros_chincheta(cx, y, dxs=None, segundo="cerrar") -> dict:
    """Los dos botones, a ``dxs`` (x desde ``cx``) o centrados."""
    a, b = dxs or (-CHINCHETA_DX, CHINCHETA_DX)
    return {"chincheta": QPointF(cx + a, y), segundo: QPointF(cx + b, y)}


def chincheta_en(cx, y, p, dxs=None, segundo="cerrar"):
    """«chincheta», ``segundo`` o None para el punto ``p``."""
    if p is None:
        return None
    for clave, q in centros_chincheta(cx, y, dxs, segundo).items():
        if math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHINCHETA_R + 1.5:
            return clave
    return None


def mascara_chincheta(path: QPainterPath, cx, y, dxs=None, segundo="cerrar") -> None:
    for q in centros_chincheta(cx, y, dxs, segundo).values():
        path.addEllipse(q, CHINCHETA_R + 1.0, CHINCHETA_R + 1.0)


def dibujar_boton_redondo(painter, clave, q, bajo=None, marcado: bool = False,
                          icono=None, relieve: bool = False) -> None:
    """Un botoncito redondo de la fila de la chincheta (o el ✕, las vistas y
    el cancelar de la barra de dibujo), con el icono ``icono`` (o el de ``clave``)."""
    from . import _iconos
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    if relieve:
        bola = QPainterPath()
        bola.addEllipse(q, CHINCHETA_R, CHINCHETA_R)
        sombra(painter, bola, 1.5, 2.0)
    painter.setPen(pluma_borde(painter, 2.0 if marcado else 1.3))
    if clave == bajo:
        painter.setBrush(QBrush(relleno_redondo(True)))
    elif marcado:
        painter.setBrush(QBrush(relleno_redondo(False)))
    elif relieve:
        painter.setBrush(relieve_redondo(q, CHINCHETA_R))
    else:
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
    painter.drawEllipse(q, CHINCHETA_R, CHINCHETA_R)
    _iconos.pintar(painter, icono or clave, q, 13.0)
    painter.restore()


def dibujar_chincheta(painter, cx, y, anclada: bool, bajo=None, dxs=None,
                      segundo="cerrar", relieve: bool = False) -> None:
    for clave, q in centros_chincheta(cx, y, dxs, segundo).items():
        marcado = clave == "chincheta" and anclada
        dibujar_boton_redondo(painter, clave, q, bajo, marcado,
                              "chincheta_clavada" if marcado else None, relieve)


def texto_chincheta(clave, anclada: bool) -> str:
    if clave == "cerrar":
        return "Cerrar la barra (se desprende la chincheta)"
    if clave == "limpia":
        return "Pantalla limpia"
    return ("Soltar la barra: vuelve a seguir al ratón" if anclada
            else "Anclar la barra aquí: se queda fija y visible")


def etiqueta(painter, texto, centro) -> QRectF:
    f = QFont(painter.font())
    f.setPointSizeF(8.5)
    f.setBold(False)
    painter.setFont(f)
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(_tr(texto)) + 12.0
    r = QRectF(centro.x() - w / 2.0, centro.y() - fm.height() / 2.0 - 2.0,
               w, fm.height() + 4.0)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(44, 44, 42, 215)))
    painter.drawRoundedRect(r, 4.0, 4.0)
    painter.setPen(BLANCO)
    painter.drawText(r, Qt.AlignCenter, _tr(texto))
    return r


def rect_etiqueta(painter_font, texto, centro) -> QRectF:
    """El rectángulo que ocuparía ``etiqueta`` (para la máscara)."""
    f = QFont(painter_font)
    f.setPointSizeF(8.5)
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(_tr(texto)) + 12.0
    return QRectF(centro.x() - w / 2.0, centro.y() - fm.height() / 2.0 - 2.0,
                  w, fm.height() + 4.0)


# ---- Los glifos: siluetas negras ------------------------------------------------------

def _trazo(path: QPainterPath, ancho: float) -> QPainterPath:
    s = QPainterPathStroker()
    s.setWidth(ancho)
    s.setCapStyle(Qt.RoundCap)
    s.setJoinStyle(Qt.RoundJoin)
    return s.createStroke(path)


def _linea(x0, y0, x1, y1) -> QPainterPath:
    p = QPainterPath()
    p.moveTo(x0, y0)
    p.lineTo(x1, y1)
    return p


def _poli(puntos, cerrar=True) -> QPainterPath:
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(x, y) for x, y in puntos]))
    if cerrar:
        p.closeSubpath()
    return p


def _circulo(x, y, r) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(QPointF(x, y), r, r)
    return p


def _punta(px, py, dx, dy, largo=4.6, ancho=3.6) -> QPainterPath:
    """Cabeza de flecha maciza con la punta en (px, py), apuntando a (dx, dy)."""
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    nx, ny = -uy, ux
    bx, by = px - ux * largo, py - uy * largo
    return _poli([(px, py), (bx + nx * ancho, by + ny * ancho),
                  (bx - nx * ancho, by - ny * ancho)])


def _hexagono(x, y, r) -> list:
    return [(x + r * math.cos(math.radians(90 + 60 * k)),
             y - r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]


def _formas(clave, x, y):
    """``(negro, blanco)``: la silueta maciza y sus detalles en blanco, de
    unos 18 px, centrados en (x, y)."""
    negro, blanco = QPainterPath(), None
    if clave == "rect":
        negro.addRect(QRectF(x - 8.5, y - 6.5, 17.0, 13.0))
        blanco = QPainterPath()
        blanco.addRect(QRectF(x - 5.0, y - 3.0, 10.0, 6.0))
    elif clave == "poly":
        negro = _poli(_hexagono(x, y, 9.0))
        blanco = _poli(_hexagono(x, y, 3.6))
    elif clave == "line":
        negro = _poli([(x - 8, y + 7), (x - 5.5, y - 6), (x + 1.5, y - 3.5),
                       (x + 8, y - 7.5), (x + 7, y + 7)])
        for vx, vy in ((x - 5.5, y - 6), (x + 8, y - 7.5), (x - 8, y + 7)):
            negro = negro.united(_circulo(vx, vy, 2.4))
        blanco = _circulo(x + 0.5, y + 1.5, 2.0)
    elif clave == "circle":
        negro = _circulo(x, y, 9.0)
        blanco = _circulo(x, y, 3.5)
    elif clave == "barra_modificar":
        fuera, dentro, base = 9.0, 4.0, y + 4.0
        negro = QPainterPath()
        negro.moveTo(x - fuera, base)
        negro.arcTo(QRectF(x - fuera, base - fuera, 2 * fuera, 2 * fuera), 180.0, -180.0)
        negro.lineTo(x + dentro, base)
        negro.arcTo(QRectF(x - dentro, base - dentro, 2 * dentro, 2 * dentro), 0.0, 180.0)
        negro.closeSubpath()
        blanco = QPainterPath()
        for g in (60.0, 120.0):
            a = math.radians(g)
            blanco.addPath(_trazo(_linea(x + dentro * math.cos(a), base - dentro * math.sin(a),
                                         x + fuera * math.cos(a), base - fuera * math.sin(a)), 1.4))
    elif clave == "barra_dibujo":
        negro = _poli([(x, y - 9), (x + 8, y - 4.5), (x + 8, y + 4.5), (x, y + 9),
                       (x - 8, y + 4.5), (x - 8, y - 4.5)])
        aristas = QPainterPath()
        aristas.moveTo(x - 8, y - 4.5)
        aristas.lineTo(x, y)
        aristas.lineTo(x + 8, y - 4.5)
        aristas.moveTo(x, y)
        aristas.lineTo(x, y + 9)
        blanco = _trazo(aristas, 1.4)
    elif clave == "move":
        negro = _trazo(_linea(x - 5.5, y, x + 5.5, y), 3.0).united(
            _trazo(_linea(x, y - 5.5, x, y + 5.5), 3.0))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            negro = negro.united(_punta(x + dx * 9.5, y + dy * 9.5, dx, dy))
    elif clave == "scale":
        negro = QPainterPath()
        negro.addRect(QRectF(x - 9.0, y + 0.5, 8.0, 8.0))
        borde = _poli([(x - 9, y - 3), (x - 9, y - 9), (x + 9, y - 9), (x + 9, y + 9),
                       (x + 3, y + 9)], cerrar=False)
        negro = negro.united(_trazo(borde, 2.2))
        negro = negro.united(_trazo(_linea(x - 1, y - 1, x + 3.5, y - 5.5), 2.6))
        negro = negro.united(_punta(x + 6.5, y - 6.5, 1, -1, 4.2, 3.2))
    elif clave == "rotate":
        r, inicio, barrido = 7.0, 70.0, 280.0
        arco = QPainterPath()
        caja = QRectF(x - r, y - r, 2 * r, 2 * r)
        arco.arcMoveTo(caja, inicio)
        arco.arcTo(caja, inicio, barrido)
        negro = _trazo(arco, 3.2)
        fin = math.radians(inicio + barrido)
        px, py = x + r * math.cos(fin), y - r * math.sin(fin)
        negro = negro.united(_punta(px - math.sin(fin) * 2.5, py - math.cos(fin) * 2.5,
                                    -math.sin(fin), -math.cos(fin)))
    elif clave == "arco":
        # Un arco con sus dos extremos.
        arco = QPainterPath()
        caja = QRectF(x - 8.5, y - 5.5, 17.0, 17.0)
        arco.arcMoveTo(caja, 180.0)
        arco.arcTo(caja, 180.0, -180.0)
        negro = _trazo(arco, 3.0)
        negro = negro.united(_circulo(x - 8.5, y + 3.0, 2.6)).united(_circulo(x + 8.5, y + 3.0, 2.6))
    elif clave == "medir":
        # Una regla inclinada con sus marcas.
        import math as _m
        ang = _m.radians(-30.0)
        ux, uy = _m.cos(ang), _m.sin(ang)
        vx, vy = -uy, ux

        def q(a, b):
            return (x + ux * a + vx * b, y + uy * a + vy * b)
        negro = _poli([q(-10, -4.5), q(10, -4.5), q(10, 4.5), q(-10, 4.5)])
        blanco = QPainterPath()
        for a, largo in ((-6, 3.0), (-2, 1.6), (2, 3.0), (6, 1.6)):
            blanco.addPath(_trazo(_linea(*q(a, -4.5), *q(a, -4.5 + largo)), 1.3))
    elif clave == "linea":
        negro = _trazo(_linea(x - 6.5, y + 6.5, x + 6.5, y - 6.5), 3.0)
        negro = negro.united(_circulo(x - 7, y + 7, 2.6)).united(_circulo(x + 7, y - 7, 2.6))
    elif clave == "borrar":
        # Una goma inclinada, con su franja, sobre la línea del suelo.
        negro = _poli([(x - 9, y + 2), (x + 0.5, y - 7.5), (x + 8, y - 0), (x - 1.5, y + 9.5)])
        negro = negro.united(_trazo(_linea(x - 9, y + 9.5, x + 9, y + 9.5), 1.6))
        blanco = _trazo(_linea(x - 4.5, y - 2.5, x + 3, y + 5), 1.6)
    elif clave == "seleccionar":
        negro = _poli([(x - 4.5, y - 9.5), (x - 4.5, y + 7), (x - 0.5, y + 3.5),
                       (x + 2.5, y + 9.5), (x + 5.3, y + 8.2), (x + 2.3, y + 2.3),
                       (x + 7.5, y + 2.3)])
    elif clave in ("grupo", "agrupar"):
        # Una caja pequeña dentro de cuatro esquinas: «agrupar».
        esquinas = QPainterPath()
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            esquinas.moveTo(x + sx * 9.0, y + sy * 4.5)
            esquinas.lineTo(x + sx * 9.0, y + sy * 9.0)
            esquinas.lineTo(x + sx * 4.5, y + sy * 9.0)
        negro = _trazo(esquinas, 2.2)
        negro = negro.united(_poli([(x, y - 5.5), (x + 5, y - 2.8), (x + 5, y + 2.8),
                                    (x, y + 5.5), (x - 5, y + 2.8), (x - 5, y - 2.8)]))
        aristas = QPainterPath()
        aristas.moveTo(x - 5, y - 2.8)
        aristas.lineTo(x, y)
        aristas.lineTo(x + 5, y - 2.8)
        aristas.moveTo(x, y)
        aristas.lineTo(x, y + 5.5)
        blanco = _trazo(aristas, 1.1)
    elif clave == "centrar":
        # Cuatro esquinas de encuadre y un punto: «centrar el modelo».
        esquinas = QPainterPath()
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            esquinas.moveTo(x + sx * 6.5, y + sy * 2.5)
            esquinas.lineTo(x + sx * 6.5, y + sy * 6.5)
            esquinas.lineTo(x + sx * 2.5, y + sy * 6.5)
        negro = _trazo(esquinas, 2.2).united(_circulo(x, y, 2.0))
    elif clave == "encuadre":
        # Una mano abierta: palma, cuatro dedos y el pulgar.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 5.0, y - 1.5, 10.0, 8.5), 3.0, 3.0)
        for i, alto in enumerate((5.5, 7.5, 7.0, 5.0)):
            dx = -3.75 + i * 2.5
            negro = negro.united(_trazo(_linea(x + dx, y, x + dx, y - alto), 2.2))
        negro = negro.united(_trazo(_linea(x - 4.5, y + 2.5, x - 7.5, y - 0.5), 2.2))
    elif clave == "zoom_previo":
        # Lupa con una flecha hacia atrás.
        aro = QPainterPath()
        aro.addEllipse(QPointF(x - 1.0, y - 1.0), 4.6, 4.6)
        negro = _trazo(aro, 2.2).united(_trazo(_linea(x + 2.6, y + 2.6, x + 6.5, y + 6.5), 2.8))
        negro = negro.united(_trazo(_linea(x - 3.5, y - 1.0, x + 1.5, y - 1.0), 1.6))
        negro = negro.united(_punta(x - 4.0, y - 1.0, -1.0, 0.0, 2.6, 2.2))
    elif clave in ("zoom_sel", "buscar"):
        # Lupa; la de la selección lleva un cuadradito dentro.
        aro = QPainterPath()
        aro.addEllipse(QPointF(x - 1.0, y - 1.0), 4.6, 4.6)
        negro = _trazo(aro, 2.2).united(_trazo(_linea(x + 2.6, y + 2.6, x + 6.5, y + 6.5), 2.8))
        if clave == "zoom_sel":
            cuadro = QPainterPath()
            cuadro.addRect(QRectF(x - 3.0, y - 3.0, 4.0, 4.0))
            negro = negro.united(cuadro)
    elif clave == "flip":
        # Simetría: un triángulo macizo, su reflejo hueco y el eje a trazos.
        negro = _poli([(x - 2.0, y - 8.0), (x - 2.0, y + 8.0), (x - 9.5, y + 8.0)])
        negro = negro.united(_trazo(_poli([(x + 2.0, y - 8.0), (x + 2.0, y + 8.0),
                                           (x + 9.5, y + 8.0)]), 1.6))
        for y0 in (-10.0, -5.0, 0.0, 5.0):
            negro = negro.united(_trazo(_linea(x, y + y0, x, y + y0 + 2.5), 1.3))
    elif clave == "notas":
        # Una libreta: hoja con renglones y la espiral arriba.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 7.0, y - 7.0, 14.0, 16.0), 2.0, 2.0)
        for dx in (-4.0, 0.0, 4.0):
            negro = negro.united(_circulo(x + dx, y - 8.0, 1.6))
        blanco = QPainterPath()
        for dy in (-2.0, 1.5, 5.0):
            blanco.addPath(_trazo(_linea(x - 4.5, y + dy, x + 4.5, y + dy), 1.3))
    elif clave == "tiempo":
        # Un cronómetro: esfera, botón arriba y aguja.
        aro = QPainterPath()
        aro.addEllipse(QPointF(x, y + 1.5), 7.5, 7.5)
        negro = _trazo(aro, 2.4).united(_trazo(_linea(x, y - 6.0, x, y - 9.0), 2.6))
        negro = negro.united(_trazo(_linea(x - 3.0, y - 9.5, x + 3.0, y - 9.5), 2.2))
        negro = negro.united(_trazo(_linea(x, y + 1.5, x + 3.5, y - 2.0), 2.0))
    elif clave in ("pegar", "pegar_sitio"):
        # Un portapapeles; «en su sitio» lleva una diana pequeña.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 7.0, y - 6.5, 14.0, 16.0), 2.0, 2.0)
        pinza = QPainterPath()
        pinza.addRoundedRect(QRectF(x - 3.5, y - 9.0, 7.0, 4.5), 1.5, 1.5)
        negro = negro.united(pinza)
        blanco = QPainterPath()
        blanco.addRect(QRectF(x - 4.5, y - 3.0, 9.0, 10.0))
        if clave == "pegar_sitio":
            marca = QPainterPath()
            marca.addEllipse(QPointF(x, y + 2.0), 3.0, 3.0)
            blanco = blanco.subtracted(_trazo(marca, 1.4)).subtracted(_circulo(x, y + 2.0, 0.9))
    elif clave == "opciones":
        # Un engranaje: rueda con ocho dientes y su agujero.
        negro = _circulo(x, y, 6.5)
        for k in range(8):
            a = math.radians(k * 45.0)
            negro = negro.united(_trazo(_linea(x + 6.0 * math.cos(a), y + 6.0 * math.sin(a),
                                               x + 9.0 * math.cos(a), y + 9.0 * math.sin(a)), 3.4))
        blanco = _circulo(x, y, 2.8)
    elif clave == "bloquear":
        # Un candado: el arco y el cuerpo con su ojo.
        arco = QPainterPath()
        caja = QRectF(x - 4.5, y - 9.0, 9.0, 10.0)
        arco.arcMoveTo(caja, 180.0)
        arco.arcTo(caja, 180.0, -180.0)
        arco.lineTo(x + 4.5, y - 1.0)
        arco.moveTo(x - 4.5, y - 4.0)
        arco.lineTo(x - 4.5, y - 1.0)
        negro = _trazo(arco, 2.4)
        cuerpo = QPainterPath()
        cuerpo.addRoundedRect(QRectF(x - 7.5, y - 1.5, 15.0, 10.5), 2.0, 2.0)
        negro = negro.united(cuerpo)
        blanco = _circulo(x, y + 3.0, 1.8)
    elif clave == "suprimir":
        negro = _trazo(_linea(x - 6.5, y - 6.5, x + 6.5, y + 6.5), 3.4).united(
            _trazo(_linea(x + 6.5, y - 6.5, x - 6.5, y + 6.5), 3.4))
    elif clave in ("orientar", "invertir"):
        # Una cara con su mitad oscura (el dorso) y una flecha que la gira.
        marco = QPainterPath()
        marco.addRect(QRectF(x - 8.0, y - 8.0, 16.0, 16.0))
        negro = _trazo(marco, 2.0).united(_poli([(x - 8, y + 8), (x + 8, y - 8), (x + 8, y + 8)]))
        giro = QPainterPath()
        caja = QRectF(x - 6.0, y - 6.0, 10.0, 10.0)
        giro.arcMoveTo(caja, 200.0)
        giro.arcTo(caja, 200.0, -110.0)
        negro = negro.united(_trazo(giro, 1.8)).united(_punta(x + 2.5, y - 5.6, 1.0, 0.1, 3.4, 2.8))
    elif clave == "cortar":
        # Unas tijeras: dos aros y dos hojas cruzadas.
        aros = QPainterPath()
        aros.addEllipse(QPointF(x - 4.0, y + 5.0), 3.2, 3.2)
        aros.addEllipse(QPointF(x + 4.0, y + 5.0), 3.2, 3.2)
        negro = _trazo(aros, 2.2).united(_trazo(_linea(x - 2.0, y + 2.5, x + 5.0, y - 8.5), 2.2))
        negro = negro.united(_trazo(_linea(x + 2.0, y + 2.5, x - 5.0, y - 8.5), 2.2))
    elif clave == "copiar":
        # Dos hojas: la de atrás maciza, la de delante blanca con borde.
        atras = QPainterPath()
        atras.addRoundedRect(QRectF(x - 8.0, y - 8.0, 11.0, 12.0), 1.5, 1.5)
        delante = QPainterPath()
        delante.addRoundedRect(QRectF(x - 3.0, y - 3.0, 11.0, 12.0), 1.5, 1.5)
        negro = atras.united(delante)
        blanco = QPainterPath()
        blanco.addRoundedRect(QRectF(x - 1.6, y - 1.6, 8.2, 9.2), 1.0, 1.0)
    elif clave in ("ocultar_resto", "ocultar", "ocultar_uno"):
        # Un ojo cerrado: el párpado con sus pestañas hacia abajo.
        parpado = QPainterPath()
        parpado.moveTo(x - 9.0, y - 3.5)
        parpado.quadTo(x, y + 5.5, x + 9.0, y - 3.5)
        negro = _trazo(parpado, 2.2)
        for x0, y0, x1, y1 in ((-7.0, -0.4, -9.2, 3.2), (-3.4, 1.4, -4.6, 5.6), (0.0, 1.9, 0.0, 6.6),
                               (3.4, 1.4, 4.6, 5.6), (7.0, -0.4, 9.2, 3.2)):
            negro = negro.united(_trazo(_linea(x + x0, y + y0, x + x1, y + y1), 1.8))
    elif clave == "pintar":
        # Un cubo de pintura inclinado, con su asa y una gota.
        negro = _poli([(x - 9, y), (x - 1, y - 8), (x + 7, y), (x - 1, y + 8)])
        asa = QPainterPath()
        asa.moveTo(x - 5, y - 4)
        asa.quadTo(x - 6, y - 11, x - 1, y - 11)
        asa.quadTo(x + 3, y - 11, x + 3, y - 4)
        gota = QPainterPath()
        gota.moveTo(x + 8, y + 2)
        gota.quadTo(x + 11, y + 7, x + 8, y + 9)
        gota.quadTo(x + 5, y + 7, x + 8, y + 2)
        gota.closeSubpath()
        negro = negro.united(_trazo(asa, 1.8)).united(gota)
        blanco = _poli([(x - 5, y), (x - 1, y - 4), (x + 3, y), (x - 1, y + 4)])
    elif clave in ("deshacer", "rehacer"):
        # Una flecha que vuelve: a la izquierda deshacer, a la derecha rehacer.
        s = 1.0 if clave == "deshacer" else -1.0
        giro = QPainterPath()
        giro.moveTo(x + s * 7, y + 8)
        giro.lineTo(x + s * 7, y + 2)
        giro.quadTo(x + s * 7, y - 4, x + s * 1, y - 4)
        giro.lineTo(x - s * 4, y - 4)
        negro = _trazo(giro, 3.0).united(
            _poli([(x - s * 10, y - 4), (x - s * 3, y - 9.5), (x - s * 3, y + 1.5)]))
    elif clave == "limpia":
        # Un monitor con la pantalla en blanco y un destello.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 9.5, y - 8.0, 19.0, 13.0), 2.0, 2.0)
        negro = negro.united(_trazo(_linea(x, y + 5, x, y + 8), 2.4))
        negro = negro.united(_trazo(_linea(x - 4.5, y + 9, x + 4.5, y + 9), 2.2))
        blanco = QPainterPath()
        blanco.addRect(QRectF(x - 7.5, y - 6.0, 15.0, 9.0))
        blanco = blanco.subtracted(_poli([(x + 2, y - 5), (x + 3, y - 2.5), (x + 5.5, y - 1.5),
                                          (x + 3, y - 0.5), (x + 2, y + 2), (x + 1, y - 0.5),
                                          (x - 1.5, y - 1.5), (x + 1, y - 2.5)]))
    elif clave in ("guardar", "copia"):
        # Un disquete; la copia lleva otro detrás, asomando.
        dx = 2.5 if clave == "copia" else 0.0
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 8.0 + dx, y - 8.0 + dx, 16.0, 16.0), 2.0, 2.0)
        if clave == "copia":
            detras = QPainterPath()
            detras.addRoundedRect(QRectF(x - 10.0, y - 10.0, 13.0, 13.0), 2.0, 2.0)
            negro = negro.united(_trazo(detras, 1.8))
        blanco = QPainterPath()
        blanco.addRect(QRectF(x - 4.5 + dx, y - 8.0 + dx, 9.0, 5.0))          # la chapa
        blanco.addRoundedRect(QRectF(x - 5.0 + dx, y + 1.0 + dx, 10.0, 5.5), 1.0, 1.0)  # la etiqueta
    elif clave == "texto":
        # Una T con remates.
        negro = _trazo(_linea(x - 8.0, y - 8.0, x + 8.0, y - 8.0), 3.2)
        negro = negro.united(_trazo(_linea(x, y - 8.0, x, y + 9.0), 3.4))
        negro = negro.united(_trazo(_linea(x - 3.5, y + 9.0, x + 3.5, y + 9.0), 2.4))
        negro = negro.united(_trazo(_linea(x - 8.0, y - 8.0, x - 8.0, y - 5.0), 2.4))
        negro = negro.united(_trazo(_linea(x + 8.0, y - 8.0, x + 8.0, y - 5.0), 2.4))
    elif clave == "calc":
        # Una calculadora: el cuerpo, la pantallita y seis teclas.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 7.0, y - 9.5, 14.0, 19.0), 2.5, 2.5)
        blanco = QPainterPath()
        blanco.addRect(QRectF(x - 4.5, y - 7.0, 9.0, 4.5))
        for fila in (0.0, 4.0):
            for col in (-4.5, -1.25, 2.0):
                blanco.addRect(QRectF(x + col, y + fila, 2.5, 2.5))
    elif clave in ("apagar", "cerrar_app"):
        # El símbolo de encendido: un aro abierto arriba y su palito.
        aro = QPainterPath()
        caja = QRectF(x - 7.5, y - 7.5, 15.0, 15.0)
        aro.arcMoveTo(caja, 50.0)
        aro.arcTo(caja, 50.0, -280.0)
        negro = _trazo(aro, 2.8).united(_trazo(_linea(x, y - 9.5, x, y - 1), 3.0))
    elif clave == "ext":
        # Una pieza de puzle.
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 8.0, y - 5.0, 13.0, 13.0), 1.5, 1.5)
        negro = negro.united(_circulo(x - 1.5, y - 6.5, 3.0)).united(_circulo(x + 6.5, y + 1.5, 3.0))
        blanco = _circulo(x - 4.0, y + 4.0, 1.5)
    elif clave == "preferencias":
        # Un marco con dos deslizadores.
        marco = QPainterPath()
        marco.addRoundedRect(QRectF(x - 8.5, y - 8.5, 17.0, 17.0), 2.5, 2.5)
        negro = _trazo(marco, 2.0)
        for dy, dx in ((-3.0, -2.0), (3.5, 2.5)):
            negro = negro.united(_trazo(_linea(x - 5, y + dy, x + 5, y + dy), 1.6))
            negro = negro.united(_circulo(x + dx, y + dy, 2.6))
    elif clave == "menus":
        # Tres rayas.
        negro = QPainterPath()
        for dy in (-6.0, 0.0, 6.0):
            negro = negro.united(_trazo(_linea(x - 8, y + dy, x + 8, y + dy), 3.0))
    elif clave == "bar":
        # Una barra de herramientas con tres botones (gestor de barras).
        negro = QPainterPath()
        negro.addRoundedRect(QRectF(x - 10.5, y - 5.0, 21.0, 10.0), 2.5, 2.5)
        blanco = QPainterPath()
        for x0 in (-8.0, -2.25, 3.5):
            blanco.addRoundedRect(QRectF(x + x0, y - 2.5, 4.5, 5.0), 1.0, 1.0)
    elif clave == "capas":
        # Una hoja en rombo y dos niveles debajo.
        negro = _poli([(x, y - 9), (x + 9, y - 4.5), (x, y), (x - 9, y - 4.5)])
        for dy in (-0.5, 4.0):
            negro = negro.united(_trazo(_poli([(x - 9, y + dy), (x, y + dy + 4.5),
                                               (x + 9, y + dy)], cerrar=False), 2.0))
    elif clave in ("arbol", "nav"):
        # Un árbol de cajitas (el Navegador).
        ramas = QPainterPath()
        ramas.moveTo(x - 6, y - 3)
        ramas.lineTo(x - 6, y + 7)
        ramas.lineTo(x, y + 7)
        ramas.moveTo(x - 6, y + 1)
        ramas.lineTo(x, y + 1)
        negro = _trazo(ramas, 1.8)
        for r in (QRectF(x - 9.5, y - 9.5, 7.5, 6.5), QRectF(x, y - 2.0, 9.0, 5.5),
                  QRectF(x, y + 4.5, 9.0, 5.5)):
            caja = QPainterPath()
            caja.addRoundedRect(r, 1.0, 1.0)
            negro = negro.united(caja)
    elif clave == "align":
        negro = _trazo(_linea(x - 8, y - 1, x - 1, y - 8), 3.0).united(
            _trazo(_linea(x - 8.5, y + 7.5, x + 8.5, y + 7.5), 3.0))
        negro = negro.united(_trazo(_linea(x + 1.5, y - 5.5, x + 4.5, y - 0.5), 2.2))
        negro = negro.united(_punta(x + 6.5, y + 3.0, 0.6, 1.0, 4.2, 3.2))
    return negro, blanco


def glifo(painter, clave, c: QPointF, tinta: QColor = NEGRO, tam: float = 24.0) -> None:
    """Dibuja el icono de colores ``clave`` centrado en ``c`` (``tam`` px; en
    gris si ``tinta`` es GRIS). Si no hay icono, o con el tema B
    (``_iconos.SILUETAS``): la silueta, con halo blanco, relleno ``tinta``
    y detalles en blanco."""
    from . import _iconos
    if not clave:
        return                               # un hueco vacío
    if _iconos.pintar(painter, clave, c, tam, apagado=tinta == GRIS, tinta=tinta):
        return
    if _iconos.externo(clave):
        _iconos.letra(painter, clave, c, tam, tinta)   # un comando sin icono
        return
    silueta(painter, clave, c, tinta)


def silueta(painter, clave, c: QPointF, tinta: QColor = NEGRO, escala: float = 1.0) -> bool:
    """La silueta ``clave`` (unos 18 px por ``escala``) centrada en ``c``,
    con halo blanco, relleno ``tinta`` y detalles en blanco. False si no
    hay silueta para esa clave. Con un tema de color (``PALETA``), en
    líneas del color con el interior sombreado (``tinta`` distinta de NEGRO,
    p. ej. el botón activo: las líneas de ese color)."""
    negro, blanco = _formas(clave, 0.0, 0.0)
    if negro.isEmpty():
        return False
    p = PALETA
    color = p is not None and QColor(tinta) != GRIS
    if color:
        if p.radial:
            t = _t_radial(painter, c)
            col, col2 = mezcla(p.borde, p.borde2, t), mezcla(p.borde, p.borde2, t + 0.4)
            claro, fuerte = mezcla(BLANCO, col2, 0.15), mezcla(col, col2, 0.5)
        else:
            col = col2 = QColor(p.linea)
            claro, fuerte = QColor(p.claro), QColor(p.fuerte)
        if QColor(tinta) != NEGRO:
            col = col2 = QColor(tinta)
        elif clave == "suprimir":
            col = col2 = QColor(PERFIL_SUPRIMIR)   # perfil rojo: no se confunde con Desplazar
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(c)
    painter.scale(escala, escala)
    halo = QPen(QColor(PERFIL_SUPRIMIR) if clave == "suprimir" and not color else HALO, 2.4)
    halo.setJoinStyle(Qt.RoundJoin)
    painter.strokePath(negro, halo)
    if not color:
        painter.fillPath(negro, QBrush(tinta))
        if blanco is not None:
            painter.fillPath(blanco, QBrush(BLANCO))
        painter.restore()
        return True
    # Sombra opaca (va también en el cursor), relleno sombreado de arriba a
    # la izquierda a abajo a la derecha y las líneas encima, de 1,2 px.
    painter.fillPath(negro.translated(0.9, 1.1), QBrush(mezcla(col, BLANCO, 0.55)))
    sombreado = QLinearGradient(QPointF(-9.0, -9.0), QPointF(9.0, 9.0))
    sombreado.setColorAt(0.0, claro)
    sombreado.setColorAt(0.45, claro)
    sombreado.setColorAt(1.0, fuerte)
    painter.fillPath(negro, QBrush(sombreado))
    if col != col2:
        trazo = QLinearGradient(QPointF(-9.0, -9.0), QPointF(9.0, 9.0))
        trazo.setColorAt(0.0, col)
        trazo.setColorAt(1.0, col2)
        brocha = QBrush(trazo)
    else:
        brocha = QBrush(col)
    ancho = 1.2 / (math.hypot(painter.transform().m11(), painter.transform().m12()) or 1.0)
    pen = QPen(brocha, ancho)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.strokePath(negro, pen)
    if blanco is not None:
        painter.fillPath(blanco, QBrush(BLANCO))
        pen.setWidthF(ancho * 0.8)
        painter.strokePath(blanco, pen)
    painter.restore()
    return True

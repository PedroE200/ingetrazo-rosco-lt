# SPDX-License-Identifier: GPL-3.0-or-later
"""Editor de vértices (Desplazar ▸ vértices): mover cualquier vértice del
modelo, también los de dentro de un grupo o componente cerrado, sin abrirlo.

- Al pasar el ratón por encima de un vértice visible sale un cuadradito
  verde (``pick_vertex`` del visor ya descarta los tapados). Clic sostenido
  sobre él, arrastrar y soltar (``on_click`` / ``on_release``): el vértice
  queda donde se suelta, con el snap y el bloqueo de ejes de IngeTrazo. Un
  clic y soltar sin mover también vale: el siguiente clic pone el destino.
- Mientras se arrastra, las aristas que llegan al vértice se ven a trazos
  hacia su sitio nuevo; se puede teclear la distancia + Enter; Esc lo deja
  como estaba.
- Solo se cogen los vértices que se ven: los que tapa una cara no reaccionan.
- En un componente, el cambio sale en todas sus copias (comparten la malla).
- Soltar encima de otro vértice de la misma malla los une, si no rompe caras.
- Cada movimiento es un paso de deshacer (``MoverVertice``).

Vive fuera de ``__init__.py`` a propósito: IngeTrazo crearía una entrada de
menú por cada Tool definida allí.
"""
from __future__ import annotations

from ._idioma import con_nombre, _tr
import logging
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QVector3D

from core.history import Command
from core.units import fmt_len
from tools.base import Tool, ToolContext

from ._ajustes import registro

log = registro("modificar")
VERDE, VERDE_OSCURO = QColor(48, 215, 91), QColor(13, 70, 28)
AZUL = QColor(34, 102, 204)
LADO_PX = 11.0                          # el cuadradito verde
ARRASTRE_PX = 4.0                       # menos que esto, es un clic (no un arrastre)
TOLERANCIA_M = 1e-5                     # el sitio del visor y el del vértice coinciden
_MINIMO = 1e-9
MENSAJE = ("Vértices: pasa por un vértice y arrastra el cuadradito verde (también "
           "dentro de grupos cerrados) · flechas: bloquear eje · teclea la distancia "
           "+ Enter · Esc cancela.")


# ---- Dónde hay vértices ------------------------------------------------------------

def _oculto(g) -> bool:
    if getattr(g, "hidden", False):
        return True
    attrs = getattr(g, "attrs", None)
    return bool(attrs and attrs.get("hidden"))


def _matriz_de(scene, grupo):
    """La matriz que coloca ``grupo`` en el mundo, esté donde esté anidado."""
    from core.group import iter_placements
    for top in scene.groups:
        for g, m in iter_placements(top):
            if g is grupo:
                return m
    return getattr(grupo, "xform", None)


def _mallas(scene) -> list:
    """(malla, matriz o None, grupo o None) de todo lo que tiene vértices: la
    geometría suelta, el grupo abierto y cada grupo cerrado (también los
    anidados), una vez por copia colocada."""
    from core.group import iter_placements
    abierto = getattr(scene, "edit_group", None)
    suelta = getattr(scene, "loose_mesh", None)
    if suelta is None or abierto is None:
        suelta = scene.mesh
    salida = [(suelta, None, None)]
    if abierto is not None:
        salida.append((scene.mesh, _matriz_de(scene, abierto), abierto))
    for top in scene.groups:
        if _oculto(top):
            continue
        for g, m in iter_placements(top):
            if g is abierto or _oculto(g) or getattr(g, "billboard", False):
                continue
            salida.append((g.mesh, m, g))
    return salida


class Punto:
    """Un vértice concreto en una copia concreta: su malla, el vértice y la
    matriz de esa copia (None = ya en coordenadas del mundo)."""
    __slots__ = ("malla", "vertice", "matriz", "grupo", "mundo")

    def __init__(self, malla, vertice, matriz, grupo, mundo: QVector3D) -> None:
        self.malla, self.vertice, self.matriz, self.grupo = malla, vertice, matriz, grupo
        self.mundo = QVector3D(mundo)

    def a_mundo(self, local: QVector3D) -> QVector3D:
        return self.matriz.map(local) if self.matriz is not None else QVector3D(local)

    def a_local(self, mundo: QVector3D) -> QVector3D:
        if self.matriz is None:
            return QVector3D(mundo)
        inversa, ok = self.matriz.inverted()
        return inversa.map(mundo) if ok else QVector3D(mundo)

    def vecinos(self) -> list:
        """Los otros extremos (en el mundo) de las aristas del vértice."""
        v = self.vertice
        otros = []
        for e in getattr(v, "edges", None) or ():
            o = e.v1 if e.v0 is v else e.v0
            otros.append(self.a_mundo(o.position))
        return otros


# ---- El paso de deshacer -----------------------------------------------------------

def _tocar(scene) -> None:
    """Tras cambiar una malla: fuera de la selección lo que ya no existe y a
    redibujar (también los grupos cerrados)."""
    vivos = set(scene.mesh.edges) | set(scene.mesh.faces)
    for s in [s for s in scene.selection
              if (hasattr(s, "v0") or hasattr(s, "loop")) and s not in vivos]:
        scene.selection.discard(s)
    try:
        from core.history import _dirty_group_chunks        # interno de 0.5.8
        _dirty_group_chunks(scene)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo marcar los grupos para redibujar")
    scene.version += 1


class MoverVertice(Command):
    """Mueve un vértice de una malla (en sus coordenadas) y, si cae sobre
    otro, los une. Deshacer devuelve la malla entera como estaba."""

    def __init__(self, malla, origen: QVector3D, destino: QVector3D, unir: bool) -> None:
        self.malla = malla
        self.origen, self.destino = QVector3D(origen), QVector3D(destino)
        self.unir = unir
        self.antes = None
        self.despues = None

    def do(self, scene) -> None:
        if self.despues is not None:            # rehacer
            self.malla.restore_state(self.despues)
            _tocar(scene)
            return
        m = self.malla
        v = m.vertex_at(self.origen)
        if v is None:
            raise RuntimeError("el vértice ya no está en su sitio")
        self.antes = m.capture_state()
        m.place_vertex(v, self.destino)
        if self.unir:
            m.weld_coincident()
            m.prune_orphan_vertices()
            if any(len(set(lazo)) != len(lazo)
                   for f in m.faces for lazo in (f.loop, *getattr(f, "hole_loops", ()))):
                m.restore_state(self.antes)
                raise ValueError("unir esos vértices dejaría una cara rota")
        self.despues = m.capture_state()
        _tocar(scene)

    def undo(self, scene) -> None:
        if self.antes is not None:
            self.malla.restore_state(self.antes)
            _tocar(scene)


# ---- La herramienta ------------------------------------------------------------------

class EditorVertices(Tool):
    name = con_nombre("Rosco · editor de vértices")
    icon = "move"
    description = ("Move any vertex, inside closed groups too: hover it and drag "
                   "its green square.")
    uses_snap = True
    vcb_label = "Distancia"

    def __init__(self, barra=None) -> None:
        self.barra = barra
        self._cache_clave = None
        self._cache = ([], None)               # (puntos, array de posiciones)
        self._reset()

    def _reset(self) -> None:
        self.bajo: Punto | None = None          # el vértice bajo el ratón
        self.cogido: Punto | None = None        # el que se está moviendo
        self.start_point: QVector3D | None = None   # su sitio (el visor lo usa para los ejes)
        self.hover_point: QVector3D | None = None   # el destino que marca el ratón
        self._pulsado_en: QPointF | None = None
        self._arrastrado = False

    # -- ciclo de vida --
    def on_activate(self, viewport) -> None:
        if viewport.active_tool is not self:   # desde un menú: primero se activa
            viewport.set_active_tool(self)
            return
        self._reset()
        viewport.flash_status(_tr(MENSAJE), 9000)

    def on_deactivate(self, viewport) -> None:
        self._reset()
        viewport.update()

    def on_cancel(self, viewport) -> None:
        if self.cogido is not None:
            viewport.flash_status(_tr("Vértices: movimiento cancelado."), 2500)
        self._reset()
        viewport.update()

    # -- buscar el vértice bajo el ratón --
    def _puntos(self, scene) -> list:
        """Todos los vértices colocados en el mundo; se rehace solo cuando
        cambia el modelo."""
        clave = (id(scene), getattr(scene, "version", None), id(scene.mesh),
                 len(scene.groups))
        if clave != self._cache_clave:
            puntos = []
            for malla, m, g in _mallas(scene):
                for v in malla.vertices:
                    puntos.append(Punto(malla, v, m, g,
                                        m.map(v.position) if m is not None else v.position))
            self._cache, self._cache_clave = puntos, clave
        return self._cache

    def _buscar(self, ctx) -> Punto | None:
        """El vértice visible bajo el ratón. El visor ya sabe cuál es (el más
        cercano que no tapa ninguna cara, también dentro de grupos cerrados)
        y da su sitio en el mundo; aquí se busca de qué malla y copia es."""
        vp = ctx.viewport
        try:
            sitio = vp.pick_vertex(ctx.screen.x(), ctx.screen.y())
        except Exception:  # noqa: BLE001
            log.exception("pick_vertex falló")
            return None
        if sitio is None:
            return None
        sitio = QVector3D(sitio)
        mejor, mejor_d = None, TOLERANCIA_M
        for p in self._puntos(vp.scene):
            d = (p.mundo - sitio).length()
            if d <= mejor_d:
                mejor, mejor_d = p, d
        return mejor

    # -- ratón: pulsar coge, arrastrar mueve, soltar deja --
    def on_hover(self, ctx: ToolContext) -> None:
        if self.cogido is not None:
            self.hover_point = QVector3D(ctx.world)
            if (self._pulsado_en is not None
                    and math.hypot(ctx.screen.x() - self._pulsado_en.x(),
                                   ctx.screen.y() - self._pulsado_en.y()) > ARRASTRE_PX):
                self._arrastrado = True
        else:
            self.bajo = self._buscar(ctx)
        ctx.viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        """El visor lo llama al pulsar: coge el vértice bajo el ratón o, si
        ya hay uno cogido (clic sin arrastrar), es el destino."""
        vp = ctx.viewport
        if self.cogido is not None:
            self._mover(vp, QVector3D(ctx.world))
            return
        punto = self.bajo or self._buscar(ctx)
        if punto is None:
            return
        self.cogido = punto
        self.start_point = QVector3D(punto.mundo)
        self.hover_point = QVector3D(punto.mundo)
        self._pulsado_en = QPointF(ctx.screen.x(), ctx.screen.y())
        self._arrastrado = False
        vp.update()

    def on_release(self, viewport) -> None:
        if self.cogido is None or self._pulsado_en is None:
            return
        if self._arrastrado and self.hover_point is not None:
            self._mover(viewport, self.hover_point)
            return
        self._pulsado_en = None                # clic sin arrastrar: espera el destino
        viewport.flash_status(_tr("Vértices: clic en el destino (o teclea la distancia "
                              "+ Enter). Esc cancela."), 6000)

    # -- medidas tecleadas --
    def on_value(self, viewport, value) -> bool:
        if self.cogido is None:
            return False
        if isinstance(value, tuple):
            if len(value) != 3:
                return False
            delta = QVector3D(*value)
        else:
            try:
                largo = float(value)
            except (TypeError, ValueError):
                return False
            direccion = (self.hover_point - self.start_point
                         if self.hover_point is not None else QVector3D())
            if direccion.lengthSquared() < _MINIMO:
                eje = getattr(viewport, "axis_lock", None)
                direccion = {"x": QVector3D(1, 0, 0), "y": QVector3D(0, 1, 0),
                             "z": QVector3D(0, 0, 1)}.get(eje, QVector3D())
            if direccion.lengthSquared() < _MINIMO:
                viewport.flash_status(_tr("Vértices: marca la dirección con el ratón antes "
                                      "de teclear."), 4000)
                return False
            delta = direccion.normalized() * largo
        self._mover(viewport, self.start_point + delta)
        return True

    # -- el movimiento --
    def _mover(self, viewport, destino: QVector3D) -> None:
        p = self.cogido
        if p is None:
            return
        if (destino - p.mundo).length() < _MINIMO:
            self._reset()
            viewport.update()
            return
        origen_local = QVector3D(p.vertice.position)
        destino_local = p.a_local(destino)
        otro = p.malla.vertex_at(destino_local)
        unir = otro is not None and otro is not p.vertice
        if unir:
            destino_local = QVector3D(otro.position)     # exacto, para que se unan
        viewport.history.execute(MoverVertice(p.malla, origen_local, destino_local, unir))
        error = getattr(viewport.history, "last_error", None)
        self._reset()
        self._cache_clave = None
        viewport.notify_scene_changed()
        if error:
            viewport.flash_status(_tr("Vértices: no se movió ({0}).", error), 7000)
        elif unir:
            viewport.flash_status(_tr("Vértices unidos. Ctrl+Z lo deshace."), 4000)
        else:
            donde = f" en «{p.grupo.name}»" if p.grupo is not None and getattr(
                p.grupo, "name", "") else ""
            viewport.flash_status(_tr("Vértice movido{0} ({1}). Ctrl+Z lo deshace.", donde, fmt_len((destino - p.mundo).length())), 4000)
        viewport.update()

    # -- lo que dibuja el visor --
    def snap_excluded(self):
        if self.cogido is None:
            return None
        return {id(e) for e in getattr(self.cogido.vertice, "edges", None) or ()}, set()

    def rubber_band_lines(self):
        if self.cogido is None or self.hover_point is None:
            return []
        return [(self.start_point, self.hover_point)]

    def value_label(self):
        if self.cogido is None or self.hover_point is None:
            return None
        return (fmt_len((self.hover_point - self.start_point).length()),
                (self.start_point + self.hover_point) * 0.5)

    def dibujar(self, viewport, painter) -> None:
        """Overlay: el cuadradito verde y, al mover, las aristas a trazos
        hacia el sitio nuevo."""
        if viewport.active_tool is not self:
            return
        punto = self.cogido or self.bajo
        if punto is None:
            return
        w2p = viewport._world_to_pixel
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        donde = punto.mundo
        if self.cogido is not None and self.hover_point is not None:
            donde = self.hover_point
            fin = w2p(donde)
            if fin is not None:
                pluma = QPen(AZUL, 1.6, Qt.DashLine)
                painter.setPen(pluma)
                for otro in punto.vecinos():
                    a = w2p(otro)
                    if a is not None:
                        painter.drawLine(QPointF(*a), QPointF(*fin))
            ini = w2p(punto.mundo)
            if ini is not None:
                painter.setPen(QPen(AZUL, 1.4))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawEllipse(QPointF(*ini), 3.5, 3.5)
        q = w2p(donde)
        if q is not None:
            painter.setPen(QPen(VERDE_OSCURO, 1.6))
            painter.setBrush(QBrush(VERDE))
            painter.drawRect(QRectF(q[0] - LADO_PX / 2.0, q[1] - LADO_PX / 2.0, LADO_PX, LADO_PX))
        painter.restore()

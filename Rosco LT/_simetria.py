# SPDX-License-Identifier: GPL-3.0-or-later
"""La Simetría de Rosco: refleja la selección en un plano, viendo
antes el plano y el resultado en fantasma.

Cómo se elige el plano (Tab pasa de un modo a otro):

- «Bajo el cursor»: la cara que hay bajo el ratón (su plano), una arista (el
  plano que la contiene, de pie) o, en el vacío, el plano por el cursor de
  cara a la vista (rojo o verde, el que se vea mejor).
- «Por el centro»: lo mismo, pero el plano pasa por el centro de la caja de
  la selección (refleja en el sitio).
- «Dos puntos»: clic en A y en B: el plano es el de en medio y A va a B.

Además:

- Hotspots: flechitas en las seis caras de la caja de la selección (y los
  puntos propios que se le hayan puesto a un grupo con el editor); un clic en
  una refleja hacia ese lado.
- Flechas: → rojo, ← verde, ↑ azul fijan la normal del plano; otra vez la
  misma, o ↓, la sueltan.
- Ctrl (un toque): copia / el original.
- H: el editor de hotspots del grupo seleccionado: un clic pone uno en el
  punto (con la normal fijada con las flechas o la de la cara bajo el ratón)
  y un clic sobre uno lo quita. Se guardan en el grupo (``ext``).
- Sin nada seleccionado, el primer clic elige el objeto bajo el ratón.
- Esc: suelta el punto A, sale del editor o vuelve a Seleccionar.

Cada reflejo es un solo paso de deshacer (las mismas órdenes que la Simetría
de IngeTrazo, con cualquier plano).
"""
from __future__ import annotations

from ._ajustes import ext_al_dia
from ._idioma import con_nombre, _tr
import logging
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPen, QPolygonF, QVector3D

from core.history import Command
from tools.base import Tool, ToolContext

from ._ajustes import registro

log = registro("simetria")
CLAVE = "rosco"                       # group.ext[CLAVE]["hotspots"]
EJES = {"x": QVector3D(1, 0, 0), "y": QVector3D(0, 1, 0), "z": QVector3D(0, 0, 1)}
COLOR_EJE = {"x": QColor(214, 40, 40), "y": QColor(40, 160, 60), "z": QColor(40, 90, 214)}
NOMBRE_EJE = {"x": "rojo", "y": "verde", "z": "azul"}
ROSA = QColor(230, 60, 150)
GRIS = QColor(120, 120, 120)
MODOS = ("cursor", "centro", "puntos")
NOMBRE_MODO = {"cursor": "bajo el cursor", "centro": "por el centro de la selección",
               "puntos": "dos puntos (A → B)"}
HOT_PX = 11.0                                  # radio para atinar a un hotspot
MAX_FANTASMA = 6000                            # aristas como mucho en la vista previa
_MIN = 1e-9


def _v(p) -> QVector3D:
    return QVector3D(p) if isinstance(p, QVector3D) else QVector3D(float(p[0]), float(p[1]), float(p[2]))


def _lista(v: QVector3D) -> list:
    return [round(float(v.x()), 6), round(float(v.y()), 6), round(float(v.z()), 6)]


def _en_plano(n: QVector3D):
    """Dos ejes ``(u, v)`` unitarios del plano de normal ``n``."""
    ref = QVector3D(0, 0, 1) if abs(n.z()) < 0.9 else QVector3D(1, 0, 0)
    u = QVector3D.crossProduct(n, ref).normalized()
    return u, QVector3D.crossProduct(n, u).normalized()


class _Hotspots(Command):
    """Cambia los hotspots propios de un grupo (deshacer los devuelve)."""

    def __init__(self, grupo, nuevos: list) -> None:
        self.grupo = grupo
        self.nuevos = [dict(h) for h in nuevos]
        datos = ext_al_dia(getattr(grupo, "ext", None) or {}).get(CLAVE) or {}
        self.viejos = [dict(h) for h in datos.get("hotspots", [])]

    def _poner(self, scene, lista) -> None:
        ext = dict(getattr(self.grupo, "ext", None) or {})
        datos = dict(ext_al_dia(ext).get(CLAVE) or {})
        if lista:
            datos["hotspots"] = [dict(h) for h in lista]
        else:
            datos.pop("hotspots", None)
        if datos:
            ext[CLAVE] = datos
        else:
            ext.pop(CLAVE, None)
        self.grupo.ext = ext
        scene.version += 1

    def do(self, scene) -> None:
        self._poner(scene, self.nuevos)

    def undo(self, scene) -> None:
        self._poner(scene, self.viejos)


class Simetria(Tool):
    name = con_nombre("Rosco · simetría")
    icon = "flip"
    description = "Mirror the selection across a face, an edge, an axis, two points or a hotspot."
    uses_snap = True
    vcb_label = None

    def __init__(self, cadena=None) -> None:
        self.cadena = cadena
        self.copia = False
        self.eje: str | None = None              # normal fijada con las flechas
        self.modo = "cursor"
        self.editor = False
        self.copiando = False                    # con Copia: ya hay copias hechas (rosco oculto)
        self._mallas_clave = None
        self._mallas = []
        self._mundo_clave = None
        self._mundo = {}
        self._reset()

    def _reset(self) -> None:
        self.plano = None                        # (centro, normal, color)
        self.a: QVector3D | None = None          # «dos puntos»: el primero
        self.cursor: QVector3D | None = None
        self.pantalla: QPointF | None = None
        self.hot = None                          # el hotspot bajo el ratón: (punto, normal, propio)
        self._fantasma = []

    # -- ciclo de vida --
    def on_activate(self, viewport) -> None:
        if viewport.active_tool is not self:     # desde la barra: primero se activa
            viewport.set_active_tool(self)
            return
        self._reset()
        viewport.flash_status(_tr(self._ayuda(viewport)), 9000)

    def on_deactivate(self, viewport) -> None:
        self._reset()
        self.editor = False
        self.copiando = False
        viewport.update()

    def on_cancel(self, viewport) -> None:
        if self.a is not None:
            self.a = None
            viewport.flash_status(_tr("Simetría: punto A soltado."), 2500)
        elif self.copiando:
            # Fin de las copias: vuelve el rosco y la orden sigue.
            self.copiando = False
            viewport.flash_status(_tr("Simetría: copias terminadas."), 2500)
            if self.cadena is not None:
                self.cadena._sincronizar()
        elif self.editor:
            self.editor = False
            viewport.flash_status(_tr("Simetría: fuera del editor de hotspots."), 2500)
        else:
            self._reset()
            if self.cadena is not None:
                self.cadena._a_seleccionar(viewport)
            return
        self._sondear(viewport)
        viewport.update()

    def _ayuda(self, viewport) -> str:
        if not viewport.scene.selection:
            return "Simetría: clic en lo que quieras reflejar (o selecciónalo antes)."
        if self.editor:
            return ("Simetría · hotspots: clic pone uno (normal: flechas o la cara) · clic "
                    "sobre uno lo quita · H sale.")
        if self.modo == "puntos":
            return ("Simetría · dos puntos: clic en A y luego en B (el plano queda en medio). "
                    "Tab cambia de modo.")
        return ("Simetría: mueve el ratón y clic para reflejar · Ctrl copia · flechas fijan el "
                "eje · Tab cambia de modo · H edita hotspots.")

    def status_clause(self) -> str:
        copia = "[copia] / original" if self.copia else "copia / [original]"
        return _tr("Ctrl = {0} · Tab = {1} · flechas = eje · H = hotspots", _tr(copia), _tr(NOMBRE_MODO[self.modo]))

    # -- el submenú del rosco --
    def marcado(self, k: str) -> bool:
        """Lo que sale marcado en el submenú: el modo, el editor, la copia y el eje."""
        if k in MODOS:
            return self.modo == k and not self.editor
        if k == "hotspots":
            return self.editor
        if k == "copia":
            return self.copia
        return self.eje == k

    def elegir(self, viewport, k: str) -> None:
        """Una opción del submenú (como su tecla)."""
        if k in MODOS:
            self.modo, self.a, self.editor = k, None, False
            viewport.flash_status(_tr("Simetría: {0}.", NOMBRE_MODO[k]), 2500)
        elif k == "hotspots":
            if self._grupo_unico(viewport) is None and not self.editor:
                viewport.flash_status(_tr("Simetría: para editar hotspots, selecciona un grupo."), 3500)
                return
            self.editor = not self.editor
            viewport.flash_status(_tr(self._ayuda(viewport)), 6000)
        elif k == "copia":
            self.copia = not self.copia
            viewport.flash_status(_tr("Simetría: crea una copia reflejada."
                                  if self.copia else "Simetría: refleja el original."), 2500)
        elif k in EJES:
            self.eje = None if self.eje == k else k
            viewport.flash_status(_tr("Simetría: plano de normal {0}", _tr(NOMBRE_EJE[self.eje]))
                                  if self.eje else _tr("Simetría: plano libre"), 2000)
        self.refresh_hint(viewport)
        self._sondear(viewport)
        viewport.update()

    # -- teclado --
    def claims_key(self, *a) -> bool:
        """El visor pregunta antes de usar la tecla para sí (ejes, foco…):
        Tab, las flechas y H son de la Simetría."""
        key = a[0].key() if a and hasattr(a[0], "key") else (a[0] if a else 0)
        return key in (Qt.Key_Tab, Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_H)

    def on_key(self, viewport, key: int, modifiers=None) -> bool:
        if key in (Qt.Key_Right, Qt.Key_Left, Qt.Key_Up):
            eje = {Qt.Key_Right: "x", Qt.Key_Left: "y", Qt.Key_Up: "z"}[key]
            self.eje = None if self.eje == eje else eje
            viewport.flash_status(_tr("Simetría: plano de normal {0}", _tr(NOMBRE_EJE[self.eje]))
                                  if self.eje else _tr("Simetría: plano libre"), 2000)
        elif key == Qt.Key_Down:
            self.eje = None
            viewport.flash_status(_tr("Simetría: plano libre."), 2000)
        elif key == Qt.Key_Tab:
            self.modo = MODOS[(MODOS.index(self.modo) + 1) % len(MODOS)]
            self.a = None
            viewport.flash_status(_tr("Simetría: {0}.", NOMBRE_MODO[self.modo]), 2500)
        elif key == Qt.Key_H:
            grupo = self._grupo_unico(viewport)
            if grupo is None and not self.editor:
                viewport.flash_status(_tr("Simetría: para editar hotspots, selecciona un grupo."), 3500)
                return True
            self.editor = not self.editor
            viewport.flash_status(_tr(self._ayuda(viewport)), 6000)
        else:
            return False
        self.refresh_hint(viewport)
        self._sondear(viewport)
        viewport.update()
        return True

    def on_key_release(self, viewport, key: int, modifiers=None) -> bool:
        if key == Qt.Key_Control and self.ctrl_tapped(viewport):
            self.copia = not self.copia
            viewport.flash_status(_tr("Simetría: crea una copia reflejada."
                                  if self.copia else "Simetría: refleja el original."), 2500)
            self.refresh_hint(viewport)
            self._sondear(viewport)
            viewport.update()
            return True
        return False

    # -- lo seleccionado --
    def _nativa(self, viewport):
        return (getattr(viewport.window(), "_tools", None) or {}).get("flip")

    def _objetivos(self, viewport):
        """``(ok, grupos, posiciones, caras, aristas, centro)`` de la
        selección, como los lee la Simetría de IngeTrazo."""
        nativa = self._nativa(viewport)
        if nativa is None:
            return False, [], [], [], [], None
        try:
            return nativa._targets(viewport, full=True)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo leer la selección")
            return False, [], [], [], [], None

    @staticmethod
    def _caja(viewport):
        lo, hi = viewport.scene.selection_bounds()
        if lo is None or hi is None:
            return None
        return QVector3D(lo), QVector3D(hi)

    @staticmethod
    def _grupo_unico(viewport):
        from core.group import Group
        sel = [e for e in viewport.scene.selection if isinstance(e, Group)]
        return sel[0] if len(sel) == 1 and len(viewport.scene.selection) == 1 else None

    def _matrices(self, viewport) -> dict:
        """``id(grupo) → matriz al mundo`` de cada colocación (se rehace al
        cambiar el modelo)."""
        scene = viewport.scene
        clave = (id(scene), getattr(scene, "version", None))
        if clave != self._mundo_clave:
            mapa = {}
            try:
                for g, m in scene.placements():
                    mapa[id(g)] = m
            except Exception:  # noqa: BLE001
                log.exception("no se pudieron leer las colocaciones")
            self._mundo, self._mundo_clave = mapa, clave
        return self._mundo

    # -- los hotspots --
    def _hotspots(self, viewport) -> list:
        """``[(punto, normal, propio)]``: el centro de cada cara de la caja de
        la selección (su normal hacia fuera) y los propios de los grupos."""
        caja = self._caja(viewport)
        if caja is None:
            return []
        lo, hi = caja
        c = (lo + hi) * 0.5
        hot = []
        for eje, n in EJES.items():
            for lado in (lo, hi):
                p = QVector3D(c)
                if eje == "x":
                    p.setX(lado.x())
                elif eje == "y":
                    p.setY(lado.y())
                else:
                    p.setZ(lado.z())
                if (p - c).lengthSquared() < _MIN:
                    continue                     # caja plana en ese eje
                hot.append((p, n * (1.0 if lado is hi else -1.0), False))
        from core.group import Group
        for g in viewport.scene.selection:
            if not isinstance(g, Group):
                continue
            m = getattr(g, "xform", None)
            for h in (ext_al_dia(getattr(g, "ext", None) or {}).get(CLAVE) or {}).get("hotspots", []):
                try:
                    p, n = _v(h["p"]), _v(h["n"])
                    if m is not None:
                        p, n = m.map(p), m.mapVector(n)
                    if n.lengthSquared() > _MIN:
                        hot.append((p, n.normalized(), True))
                except Exception:  # noqa: BLE001
                    continue
        return hot

    def _hot_en(self, viewport, sx: float, sy: float):
        mejor, mejor_d = None, HOT_PX
        for h in self._hotspots(viewport):
            q = viewport._world_to_pixel(h[0])
            if q is None:
                continue
            d = math.hypot(q[0] - sx, q[1] - sy)
            if d <= mejor_d:
                mejor, mejor_d = h, d
        return mejor

    # -- el plano bajo el ratón --
    def _normal_vista(self, viewport, c: QVector3D) -> QVector3D:
        """En el vacío: el plano de pie que mejor se ve (normal roja o verde)."""
        q0 = viewport._world_to_pixel(c)
        mejor, largo = EJES["x"], -1.0
        for eje in ("x", "y"):
            q1 = viewport._world_to_pixel(c + EJES[eje])
            if q0 is None or q1 is None:
                continue
            dx = abs(q1[0] - q0[0])
            if dx > largo:
                mejor, largo = EJES[eje], dx
        return QVector3D(mejor)

    def _plano_en(self, viewport, sx: float, sy: float, mundo: QVector3D):
        """``(centro, normal, color)`` del plano para el ratón en ``(sx, sy)``."""
        caja = self._caja(viewport)
        centro_sel = (caja[0] + caja[1]) * 0.5 if caja is not None else None
        por = centro_sel if (self.modo == "centro" and centro_sel is not None) else mundo
        if self.eje is not None:
            return QVector3D(por), QVector3D(EJES[self.eje]), COLOR_EJE[self.eje]
        try:
            cara, donde = viewport.pick_face_placement(sx, sy)
        except Exception:  # noqa: BLE001
            cara, donde = None, None
        if cara is not None:
            n = cara.normal() if callable(cara.normal) else cara.normal
            n = QVector3D(n)
            m = self._matrices(viewport).get(id(donde)) if donde is not None else None
            if m is not None:
                n = m.mapVector(n)
            if n.lengthSquared() > _MIN:
                return QVector3D(por), n.normalized(), ROSA
        try:
            arista = viewport.pick_edge_any(sx, sy)
        except Exception:  # noqa: BLE001
            arista = None
        if arista is not None:
            a, b = _v(arista.a), _v(arista.b)
            d = b - a
            if d.lengthSquared() > _MIN:
                d.normalize()
                n = QVector3D.crossProduct(d, QVector3D(0, 0, 1))
                if n.lengthSquared() < 1e-6:
                    n = QVector3D.crossProduct(d, QVector3D(1, 0, 0))
                centro = (a + b) * 0.5 if self.modo != "centro" or centro_sel is None else centro_sel
                return centro, n.normalized(), ROSA
        return QVector3D(por), self._normal_vista(viewport, por), GRIS

    def _sondear(self, viewport, ctx: ToolContext | None = None) -> None:
        """Rehace el plano y el fantasma con el último sitio del ratón."""
        if ctx is not None:
            self.cursor = QVector3D(ctx.world)
            self.pantalla = QPointF(ctx.screen)
        if self.cursor is None or self.pantalla is None:
            return
        sx, sy = self.pantalla.x(), self.pantalla.y()
        self.hot = None
        self.plano = None
        if not viewport.scene.selection:
            self._fantasma = []
            return
        if self.editor:
            self.hot = self._hot_en(viewport, sx, sy)
            self._fantasma = []
            return
        if self.modo == "puntos":
            if self.a is not None and (self.cursor - self.a).lengthSquared() > _MIN:
                self.plano = ((self.a + self.cursor) * 0.5, (self.cursor - self.a).normalized(), ROSA)
        else:
            self.hot = self._hot_en(viewport, sx, sy)
            if self.hot is not None:
                self.plano = (QVector3D(self.hot[0]), QVector3D(self.hot[1]), ROSA)
            else:
                self.plano = self._plano_en(viewport, sx, sy, self.cursor)
        self._fantasma = self._reflejo_aristas(viewport) if self.plano is not None else []

    # -- ratón --
    def on_hover(self, ctx: ToolContext) -> None:
        self._sondear(ctx.viewport, ctx)
        ctx.viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        self._sondear(vp, ctx)
        if not vp.scene.selection:
            self._elegir(vp, ctx)
            return
        if self.editor:
            self._editar_hotspot(vp, ctx)
            return
        if self.modo == "puntos" and self.a is None:
            self.a = QVector3D(ctx.world)
            vp.flash_status(_tr("Simetría: ahora clic en B (A irá a B)."), 4000)
            vp.update()
            return
        if self.plano is None:
            return
        centro, normal, _color = self.plano
        if self._aplicar(vp, centro, normal):
            self.a = None
            if self.copia:
                self.copiando = True             # copias seguidas, cada clic una, hasta Esc
            if self.cadena is not None and self.cadena.panel == "flip":
                self.cadena.panel = None         # hecha: el submenú se cierra, como en las demás
            vp.flash_status(_tr("Simetría hecha (copia). Ctrl+Z la deshace." if self.copia
                            else "Simetría hecha. Ctrl+Z la deshace."), 3500)
        self._sondear(vp)
        vp.update()

    def _elegir(self, viewport, ctx) -> None:
        """Sin selección: el objeto bajo el ratón pasa a ser lo que se refleja."""
        sx, sy = ctx.screen.x(), ctx.screen.y()
        elegido = None
        try:
            elegido = viewport.pick_group(sx, sy)
            if elegido is None:
                cara, _g = viewport.pick_face_any(sx, sy)
                elegido = cara
        except Exception:  # noqa: BLE001
            log.exception("no se pudo elegir bajo el ratón")
        if elegido is None:
            viewport.flash_status(_tr("Simetría: no hay nada bajo el ratón."), 2500)
            return
        viewport.scene.select([elegido], mode="replace")
        viewport.notify_scene_changed()
        viewport.flash_status(_tr(self._ayuda(viewport)), 6000)
        self._sondear(viewport, ctx)
        viewport.update()

    # -- reflejar --
    def _aplicar(self, viewport, centro: QVector3D, normal: QVector3D) -> bool:
        """Refleja (o copia reflejada) la selección en el plano por
        ``centro`` de normal ``normal``: un paso de deshacer."""
        from core.group import copy_group, transformed_attrs
        from core.history import (
            AddEdgeCommand, AddFaceCommand, CompoundCommand, FlipGroupsCommand,
            FlipVerticesCommand, InsertGroupCommand, mirror_matrix,
        )
        from core.mesh import Mesh
        ok, grupos, posiciones, caras, aristas, _c = self._objetivos(viewport)
        if not ok:
            viewport.flash_status(_tr("Simetría: selecciona antes lo que quieres reflejar."), 3500)
            return False
        n = QVector3D(normal).normalized()
        cmds = []
        if self.copia:
            m = mirror_matrix(centro, n)
            for g in grupos:
                copia = copy_group(g)
                cmds.append(InsertGroupCommand(copia))
                cmds.append(FlipGroupsCommand([copia], centro, n))
            curvas = {}
            for f in caras:
                lazo = [m.map(QVector3D(v)) for v in f.vertices][::-1]
                huecos = [[m.map(QVector3D(v)) for v in h][::-1] for h in f.holes] or None
                cmds.append(AddFaceCommand(lazo, holes=huecos, auto=False,
                                           attrs=transformed_attrs(f.attrs, m)))
            for e in aristas:
                curva = getattr(e, "curve", None)
                if curva is not None and curva not in curvas:
                    curvas[curva] = Mesh.next_curve_id()
                cmds.append(AddEdgeCommand(m.map(QVector3D(e.a)), m.map(QVector3D(e.b)),
                                           soft=getattr(e, "soft", False) or None,
                                           curve=curvas.get(curva)))
        else:
            if grupos:
                cmds.append(FlipGroupsCommand(grupos, centro, n))
            if posiciones:
                cmds.append(FlipVerticesCommand(posiciones, centro, n, faces=caras))
        if not cmds:
            return False
        viewport.history.execute(cmds[0] if len(cmds) == 1 else CompoundCommand(cmds))
        error = getattr(viewport.history, "last_error", None)
        viewport.notify_scene_changed()
        if error:
            viewport.flash_status(_tr("Simetría: no se pudo ({0}).", error), 6000)
            return False
        return True

    # -- el editor de hotspots --
    def _editar_hotspot(self, viewport, ctx) -> None:
        grupo = self._grupo_unico(viewport)
        if grupo is None:
            viewport.flash_status(_tr("Simetría: el editor de hotspots necesita un grupo seleccionado."), 3500)
            return
        datos = (ext_al_dia(getattr(grupo, "ext", None) or {}).get(CLAVE) or {}).get("hotspots", [])
        lista = [dict(h) for h in datos]
        m = getattr(grupo, "xform", None)
        inversa = m.inverted()[0] if m is not None else None
        if self.hot is not None and self.hot[2]:
            # Quitar el propio bajo el ratón (el más cercano en el grupo).
            p_local = inversa.map(self.hot[0]) if inversa is not None else self.hot[0]
            lista.sort(key=lambda h: (_v(h["p"]) - p_local).lengthSquared())
            lista = lista[1:]
            texto = "Hotspot quitado."
        else:
            if self.eje is not None:
                n = QVector3D(EJES[self.eje])
            else:
                plano = self._plano_en(viewport, ctx.screen.x(), ctx.screen.y(), QVector3D(ctx.world))
                n = plano[1]
            p = QVector3D(ctx.world)
            if inversa is not None:
                p, n = inversa.map(p), inversa.mapVector(n)
            lista.append({"p": _lista(p), "n": _lista(n.normalized())})
            texto = "Hotspot puesto."
        viewport.history.execute(_Hotspots(grupo, lista))
        viewport.notify_scene_changed()
        viewport.flash_status(_tr("Simetría: {0} Ctrl+Z lo deshace.", texto), 3000)
        self._sondear(viewport)
        viewport.update()

    # -- la vista previa --
    def _aristas_mundo(self, viewport) -> list:
        """Las aristas de la selección en el mundo (se rehace al cambiar la
        selección o el modelo)."""
        from core.group import Group, iter_placements
        scene = viewport.scene
        clave = (id(scene), getattr(scene, "version", None), frozenset(id(e) for e in scene.selection))
        if clave == self._mallas_clave:
            return self._mallas
        tramos = []
        try:
            for e in scene.selection:
                if len(tramos) > MAX_FANTASMA:
                    break
                if isinstance(e, Group):
                    for g, m in iter_placements(e):
                        for a in g.mesh.edges:
                            pa, pb = QVector3D(a.a), QVector3D(a.b)
                            tramos.append((m.map(pa), m.map(pb)) if m is not None else (pa, pb))
                            if len(tramos) > MAX_FANTASMA:
                                break
                elif hasattr(e, "vertices") and hasattr(e, "normal"):     # una cara suelta
                    vs = [QVector3D(v) for v in e.vertices]
                    tramos.extend((vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs)))
                elif hasattr(e, "a") and hasattr(e, "b"):                  # una arista suelta
                    tramos.append((QVector3D(e.a), QVector3D(e.b)))
        except Exception:  # noqa: BLE001
            log.exception("no se pudieron leer las aristas de la selección")
        self._mallas, self._mallas_clave = tramos, clave
        return tramos

    def _reflejo_aristas(self, viewport) -> list:
        from core.history import mirror_matrix
        centro, normal, _c = self.plano
        m = mirror_matrix(centro, normal)
        return [(m.map(a), m.map(b)) for a, b in self._aristas_mundo(viewport)]

    def rubber_band_lines(self):
        return list(self._fantasma)

    def dibujar(self, viewport, painter) -> None:
        """Overlay (lo llama la barra con la orden activa): el plano
        translúcido, los hotspots, el punto A y el cuadrito de ayuda."""
        w2p = viewport._world_to_pixel
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        try:
            caja = self._caja(viewport)
            if self.plano is not None and caja is not None:
                centro, n, color = self.plano
                u, v = _en_plano(n)
                lado = max(0.25, (caja[1] - caja[0]).length() * 0.65)
                puntos = [w2p(centro + u * su * lado + v * sv * lado)
                          for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                if all(q is not None for q in puntos):
                    relleno = QColor(color)
                    relleno.setAlpha(45)
                    painter.setPen(QPen(color, 1.4))
                    painter.setBrush(QBrush(relleno))
                    painter.drawPolygon(QPolygonF([QPointF(*q) for q in puntos]))
            for p, n, propio in self._hotspots(viewport):
                q = w2p(p)
                if q is None:
                    continue
                activo = self.hot is not None and (self.hot[0] - p).lengthSquared() < _MIN
                self._flecha(painter, viewport, p, n, q, activo, propio)
            if self.a is not None:
                q = w2p(self.a)
                if q is not None:
                    painter.setPen(QPen(QColor(255, 255, 255), 1.4))
                    painter.setBrush(QBrush(ROSA))
                    painter.drawEllipse(QPointF(*q), 5.0, 5.0)
                    if self.cursor is not None:
                        b = w2p(self.cursor)
                        if b is not None:
                            painter.setPen(QPen(ROSA, 1.4, Qt.DashLine))
                            painter.drawLine(QPointF(*q), QPointF(*b))
            self._cuadro(painter, viewport)
        finally:
            painter.restore()

    def _flecha(self, painter, viewport, p, n, q, activo: bool, propio: bool) -> None:
        """Un hotspot: triángulo rosa que apunta hacia fuera de la caja."""
        caja = self._caja(viewport)
        paso = max(0.05, (caja[1] - caja[0]).length() * 0.06) if caja is not None else 0.1
        r = viewport._world_to_pixel(p + n * paso)
        dx, dy = (r[0] - q[0], r[1] - q[1]) if r is not None else (0.0, -1.0)
        largo = math.hypot(dx, dy) or 1.0
        dx, dy = dx / largo, dy / largo
        t = 9.0 if activo else 7.0
        punta = QPointF(q[0] + dx * t * 1.4, q[1] + dy * t * 1.4)
        base1 = QPointF(q[0] - dy * t * 0.8, q[1] + dx * t * 0.8)
        base2 = QPointF(q[0] + dy * t * 0.8, q[1] - dx * t * 0.8)
        color = QColor(160, 30, 110) if propio else ROSA
        painter.setPen(QPen(QColor(255, 255, 255), 1.6))
        painter.setBrush(QBrush(color.darker(120) if activo else color))
        painter.drawPolygon(QPolygonF([punta, base1, base2]))

    def _cuadro(self, painter, viewport) -> None:
        """El cuadrito de ayuda junto al cursor: modo, copia y eje."""
        if self.pantalla is None:
            return
        if self.editor:
            lineas = ["Hotspots del grupo", "clic: pone · clic encima: quita", "H: salir"]
        else:
            lineas = [_tr("Simetría · {0}", _tr(NOMBRE_MODO[self.modo])),
                      _tr("Copia: {0}  (Ctrl)", _tr("sí" if self.copia else "no")),
                      _tr("Eje: {0}  (flechas)", _tr(NOMBRE_EJE[self.eje] if self.eje else "libre")),
                      "Tab: modo · H: hotspots"]
            if not viewport.scene.selection:
                lineas = ["Simetría", "clic en lo que quieras reflejar"]
        f = QFont(painter.font())
        f.setPointSizeF(8.0)
        painter.setFont(f)
        fm = QFontMetricsF(f)
        ancho = max(fm.horizontalAdvance(_tr(t)) for t in lineas) + 12.0
        alto = fm.height() * len(lineas) + 8.0
        x, y = self.pantalla.x() + 22.0, self.pantalla.y() + 20.0
        rect = QRectF(x, y, ancho, alto)
        painter.setPen(QPen(QColor(75, 58, 168), 1.2))
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
        painter.drawRoundedRect(rect, 5.0, 5.0)
        painter.setPen(QColor(34, 34, 34))
        for i, t in enumerate(lineas):
            painter.drawText(QPointF(x + 6.0, y + 4.0 + fm.ascent() + i * fm.height()), _tr(t))

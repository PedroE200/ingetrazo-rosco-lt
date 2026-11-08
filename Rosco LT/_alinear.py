# SPDX-License-Identifier: GPL-3.0-or-later
"""Alinear: la herramienta de cuatro puntos y su panel de opciones.

La transformación lleva dos pares de puntos origen → destino:

    T  traslada origen 1 → destino 1
    R  gira alrededor de destino 1, por el eje ``u × v`` (el giro mínimo
       que lleva u = origen 2 − origen 1 sobre v = destino 2 − destino 1;
       con las dos parejas en planta, es un giro alrededor de Z)
    S  (opcional) escala desde destino 1 por |v| / |u|

    M = S · R · T

Se aplica con los comandos nativos de IngeTrazo 0.5.8 dentro de un
``CompoundCommand`` (un paso de deshacer): ``MoveGroupCommand``,
``RotateGroupCommand`` y ``ScaleGroupCommand`` para grupos y componentes, y
un comando propio que lleva los vértices sueltos por M de una vez (con el
plegado de caras no planas que hacen Mover/Rotar). En modo copia: copias de
los grupos (``copy_group`` + ``InsertGroupCommand``) y de las caras/aristas
sueltas, ya transformadas — lo mismo que hace Rotar con Ctrl.
"""
from __future__ import annotations

from ._idioma import _tr
import logging
import math

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QMatrix4x4, QPainter, QPen, QVector3D,
)

from tools.base import Tool, ToolContext

log = logging.getLogger("ingetrazo.plugins.alinear")

ROJO = QColor(214, 34, 34)
TINTA = QColor(44, 44, 42)
_EPS = 1e-7
_MAX_SEGMENTOS = 4000                   # más que esto: se previsualizan cajas

PASOS = ("1er punto de origen", "1er punto de destino",
         "2º punto de origen", "2º punto de destino")
TIP = ("Alinear: 1er punto origen → 1er destino, 2º origen → "
       "2º destino; mover o copiar y, si quieres, escalar al segmento.")


def _ajustes() -> QSettings:
    from ._ajustes import ajustes
    return ajustes("alinear")


def _leer_bool(valor, por_defecto: bool) -> bool:
    if valor is None:
        return por_defecto
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "yes", "si", "sí")
    return bool(valor)


# ---- La transformación -----------------------------------------------------------

def alineacion(o1, d1, o2, d2, escalar: bool):
    """``(delta, eje, grados, factor, M)`` de ALINEAR con dos pares. Si un
    segmento es nulo solo se traslada."""
    delta = d1 - o1
    t = QMatrix4x4()
    t.translate(delta)
    u, v = o2 - o1, d2 - d1
    lu, lv = u.length(), v.length()
    eje, grados, factor = QVector3D(0.0, 0.0, 1.0), 0.0, 1.0
    if lu > _EPS and lv > _EPS:
        un, vn = u / lu, v / lv
        cruz = QVector3D.crossProduct(un, vn)
        seno = cruz.length()
        coseno = max(-1.0, min(1.0, QVector3D.dotProduct(un, vn)))
        if seno > 1e-9:
            eje = cruz / seno
            grados = math.degrees(math.atan2(seno, coseno))
        elif coseno < 0.0:
            # Opuestos: media vuelta por el eje perpendicular a u más cercano
            # a Z (Z exacto si u es horizontal: el giro de 180° en planta).
            ref = QVector3D(0.0, 0.0, 1.0)
            if abs(QVector3D.dotProduct(un, ref)) > 0.9:     # u casi vertical
                ref = QVector3D(1.0, 0.0, 0.0)
            eje = (ref - un * QVector3D.dotProduct(ref, un)).normalized()
            grados = 180.0
        if escalar:
            factor = lv / lu
    from core.history import rotation_matrix, scale_matrix
    r = rotation_matrix(d1, eje, grados) if grados else QMatrix4x4()
    s = scale_matrix(d1, factor) if abs(factor - 1.0) > 1e-12 else QMatrix4x4()
    return delta, eje, grados, factor, s * r * t


def _comando_vertices_cls():
    """``Command`` que lleva unos vértices sueltos por una matriz (definido
    tarde: ``core.history`` es interno)."""
    from core.history import Command
    from core.topology import _key

    class TransformarVertices(Command):
        """Como Rotate/ScaleVerticesCommand pero con una matriz cualquiera:
        cada vértice compartido en esas posiciones va a ``m.map(p)``; luego
        se juntan los que caen sobre otro y se pliegan las caras que quedaran
        no planas. Deshacer/rehacer con instantáneas de la malla."""

        def __init__(self, posiciones, m) -> None:
            self.src = [QVector3D(p) for p in posiciones]
            self.m = QMatrix4x4(m)
            self._antes = None
            self._despues = None

        def do(self, scene) -> None:
            mesh = scene.mesh
            if self._despues is not None:            # rehacer
                mesh.restore_state(self._despues)
                scene.version += 1
                return
            self._antes = mesh.capture_state()
            claves = {_key(p) for p in self.src}
            mueven = [v for v in mesh.vertices if _key(v.position) in claves]
            for vtx in mueven:
                mesh.move_vertex(vtx, self.m.map(vtx.position) - vtx.position)
            try:
                from core.history import _weld_landed
                _weld_landed(mesh, {id(vtx) for vtx in mueven})
            except Exception:  # noqa: BLE001 — sin soldar también vale
                log.debug("sin _weld_landed", exc_info=True)
            try:
                from core.topology import fold_nonplanar_faces
                fold_nonplanar_faces(mesh)
            except Exception:  # noqa: BLE001
                log.debug("sin fold_nonplanar_faces", exc_info=True)
            self._despues = mesh.capture_state()
            scene.version += 1

        def undo(self, scene) -> None:
            if self._antes is not None:
                scene.mesh.restore_state(self._antes)
                scene.version += 1

    return TransformarVertices


# ---- La herramienta ----------------------------------------------------------------

class AlinearTool(Tool):
    name = "Alinear"
    icon = "move"                       # el cursor de Mover
    shortcut = None
    description = TIP
    vcb_label = "Distancia"
    uses_snap = True

    def __init__(self, ctl) -> None:
        self.ctl = ctl
        self.start_point: QVector3D | None = None
        self.chain_first_point = None   # sin snap «cerrar»
        self.puntos: list[QVector3D] = []
        self.hover: QVector3D | None = None
        self._grupos: list = []
        self._posiciones: list[QVector3D] = []
        self._caras: list = []
        self._aristas: list = []
        self._alambre: list = []        # segmentos de la selección (previa)

    # -- ciclo de vida --
    def on_activate(self, viewport) -> None:
        self.puntos = []
        self.start_point = None
        self.hover = None
        if not self._reunir(viewport):
            viewport.flash_status(
                _tr("Alinear: selecciona primero grupos, componentes, caras o "
                "aristas."), 6000)
            self.ctl.volver_a_seleccionar()
            return
        self.ctl.avisar_paso(viewport)

    def on_deactivate(self, viewport) -> None:
        self.puntos = []
        self.start_point = None
        self.hover = None
        self._alambre = []
        viewport.update()

    def on_cancel(self, viewport) -> None:
        if self.puntos:
            self.puntos = []
            self.start_point = None
            viewport.flash_status(_tr("Alinear: puntos borrados. ")
                                  + self.ctl.texto_paso(), 5000)
            viewport.update()
        else:
            self.ctl.volver_a_seleccionar()

    # -- entrada --
    def on_hover(self, ctx: ToolContext) -> None:
        self.hover = QVector3D(ctx.world)
        self.ctl.cursor = QPointF(ctx.screen)
        ctx.viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        if self.ctl.clic_panel(ctx.viewport, ctx.screen):
            return
        self._punto(ctx.viewport, QVector3D(ctx.world))

    def on_value(self, viewport, value) -> bool:
        """Distancia tecleada desde el punto anterior hacia el cursor."""
        if isinstance(value, tuple) or not self.puntos or self.hover is None:
            return False
        base = self.puntos[0] if len(self.puntos) < 3 else self.puntos[2]
        d = self.hover - base
        if d.length() < _EPS or value <= 0.0:
            return False
        self._punto(viewport, base + d.normalized() * float(value))
        return True

    def on_key(self, viewport, key: int, modifiers) -> bool:
        if key == Qt.Key_Control:
            return True                 # se alterna al soltar (si fue un toque)
        if key == Qt.Key_Backspace and self.puntos:
            tecleado = getattr(viewport, "_value_buffer", "")
            if isinstance(tecleado, str) and tecleado:
                return False            # borra lo tecleado, no un punto
            self.puntos.pop()
            self._fijar_inicio()
            self.ctl.avisar_paso(viewport)
            viewport.update()
            return True
        return False

    def on_key_release(self, viewport, key: int) -> bool:
        if key != Qt.Key_Control:
            return False
        if self.ctrl_tapped(viewport):
            self.ctl.alternar("copiar", viewport)
        return True

    def status_clause(self) -> str:
        return _tr("Ctrl = {0} · Retroceso = quitar el último punto",
                   _tr("mover" if self.ctl.copiar else "copiar"))

    # -- pasos --
    def _fijar_inicio(self) -> None:
        """El punto desde el que el visor infiere (ejes, guías): el origen 1
        para elegir destino 1 y origen 2; destino 1 para elegir destino 2."""
        n = len(self.puntos)
        self.start_point = (None if n == 0 else
                            QVector3D(self.puntos[2] if n == 3 else self.puntos[0]))

    def _punto(self, viewport, p: QVector3D) -> None:
        n = len(self.puntos)
        if n == 2 and (p - self.puntos[0]).length() < _EPS:
            viewport.flash_status(_tr("El 2º punto de origen no puede coincidir "
                                  "con el 1º."), 5000)
            return
        if n == 3 and (p - self.puntos[1]).length() < _EPS:
            viewport.flash_status(_tr("El 2º punto de destino no puede coincidir "
                                  "con el 1º."), 5000)
            return
        self.puntos.append(QVector3D(p))
        if len(self.puntos) == 4:
            self._aplicar(viewport)
            return
        self._fijar_inicio()
        self.ctl.avisar_paso(viewport)
        viewport.update()

    # -- la selección --
    def _reunir(self, viewport) -> bool:
        from core.mesh import Edge, Face
        from core.topology import _key
        self._grupos, self._caras, self._aristas = [], [], []
        posiciones, vistas = [], set()
        for ent in list(viewport.scene.selection):
            if isinstance(ent, Edge):
                self._aristas.append(ent)
                pts = (ent.a, ent.b)
            elif isinstance(ent, Face):
                self._caras.append(ent)
                pts = list(ent.vertices)
                for h in getattr(ent, "holes", ()) or ():
                    pts.extend(h)
            elif hasattr(ent, "mesh") and hasattr(ent, "xform"):
                self._grupos.append(ent)
                continue
            else:
                continue                # cotas, textos, imágenes…: no
            for p in pts:
                k = _key(p)
                if k not in vistas:
                    vistas.add(k)
                    posiciones.append(QVector3D(p))
        self._posiciones = posiciones
        self._alambre = self._segmentos(viewport)
        return bool(self._grupos or self._posiciones)

    def _segmentos(self, viewport) -> list:
        """El alambre de la selección para la previsualización; si es enorme,
        la caja de cada grupo."""
        segs: list = []
        try:
            from core.group import iter_placements
            total = 0
            for g in self._grupos:
                for pg, _m in iter_placements(g):
                    total += len(pg.mesh.edges)
            if total <= _MAX_SEGMENTOS:
                for g in self._grupos:
                    for pg, m in iter_placements(g):
                        for e in pg.mesh.edges:
                            a, b = QVector3D(e.a), QVector3D(e.b)
                            if m is not None:
                                a, b = m.map(a), m.map(b)
                            segs.append((a, b))
            else:
                for g in self._grupos:
                    segs.extend(_caja(viewport, g))
        except Exception:  # noqa: BLE001 — sin previa de grupos
            log.debug("sin alambre de grupos", exc_info=True)
        sueltos: list = []
        for f in self._caras:
            for lp in (list(f.vertices), *[list(h) for h in (f.holes or [])]):
                for i in range(len(lp)):
                    sueltos.append((QVector3D(lp[i]), QVector3D(lp[(i + 1) % len(lp)])))
        for e in self._aristas:
            sueltos.append((QVector3D(e.a), QVector3D(e.b)))
        return segs + sueltos[:_MAX_SEGMENTOS]

    # -- previsualización --
    def _matriz_previa(self):
        """La transformación con el cursor como el punto que falta."""
        p, h = self.puntos, self.hover
        n = len(p)
        if n == 0 or h is None:
            return None
        if n == 1:
            m = QMatrix4x4()
            m.translate(h - p[0])
            return m
        if n == 2:
            m = QMatrix4x4()
            m.translate(p[1] - p[0])
            return m
        if (h - p[1]).length() < _EPS:
            return None
        return alineacion(p[0], p[1], p[2], h, self.ctl.escalar)[4]

    def rubber_band_lines(self):
        p, h = self.puntos, self.hover
        n = len(p)
        out: list = []
        if n >= 1 and h is not None and n in (1, 2):
            out.append((p[0], h))                       # origen 1 → cursor
        if n >= 2:
            out.append((p[0], p[1]))                    # el primer par
        if n == 3:
            out.append((p[0], p[2]))                    # segmento de origen
            if h is not None:
                out.append((p[1], h))                   # segmento de destino
        m = self._matriz_previa()
        if m is not None:
            out.extend((m.map(a), m.map(b)) for a, b in self._alambre)
        return out

    def value_label(self):
        p, h = self.puntos, self.hover
        if not p or h is None:
            return None
        base = p[0] if len(p) < 3 else p[2]
        from core.units import fmt_len
        texto = fmt_len((h - base).length())
        if len(p) == 3 and self.ctl.escalar:
            lu = (p[2] - p[0]).length()
            if lu > _EPS:
                texto += f"  (×{(h - p[1]).length() / lu:.4g})"
        return texto, (base + h) * 0.5

    def draw_overlay(self, viewport, painter) -> None:
        self.ctl.dibujar(viewport, painter)

    # -- aplicar --
    def _aplicar(self, viewport) -> None:
        o1, d1, o2, d2 = self.puntos
        delta, eje, grados, factor, m = alineacion(o1, d1, o2, d2, self.ctl.escalar)
        try:
            cmd = self._comando(delta, d1, eje, grados, factor, m)
        except Exception as exc:  # noqa: BLE001
            log.exception("no se pudo preparar Alinear")
            viewport.flash_status(_tr("Alinear: no se pudo preparar ({0}).", exc), 7000)
            cmd = None
        if cmd is not None:
            viewport.history.execute(cmd)
            viewport.notify_scene_changed()
            rechazo = getattr(viewport.history, "last_rejected", None)
            error = viewport.history.last_error
            if rechazo:
                viewport.flash_status(_tr("Alinear: {0}", rechazo), 8000)
            elif error:
                viewport.flash_status(_tr("Alinear: no se aplicó ({0}).", error), 8000)
            else:
                partes = [_tr("copiado") if self.ctl.copiar else _tr("alineado")]
                if grados:
                    partes.append(_tr("giro {0:.2f}°", grados))
                if abs(factor - 1.0) > 1e-9:
                    partes.append(_tr("escala ×{0:.4g}", factor))
                viewport.flash_status(_tr("Alinear: ") + ", ".join(partes)
                                      + _tr(". Ctrl+Z lo deshace."), 6000)
        self.puntos = []
        self.start_point = None
        viewport.update()
        self.ctl.volver_a_seleccionar()

    def _comando(self, delta, centro, eje, grados, factor, m):
        from core.history import (
            AddEdgeCommand, AddFaceCommand, CompoundCommand, InsertGroupCommand,
            MoveGroupCommand, RotateGroupCommand, ScaleGroupCommand,
        )
        cmds: list = []

        def a_grupo(g) -> None:
            if delta.length() > 1e-12:
                cmds.append(MoveGroupCommand(g, delta))
            if grados:
                cmds.append(RotateGroupCommand(g, centro, eje, grados))
            if abs(factor - 1.0) > 1e-12:
                cmds.append(ScaleGroupCommand(g, centro, factor))

        if self.ctl.copiar:
            from core.group import copy_group, transformed_attrs
            from core.mesh import Mesh
            for g in self._grupos:
                copia = copy_group(g)            # instancia → instancia hermana
                cmds.append(InsertGroupCommand(copia))
                a_grupo(copia)
            for f in self._caras:
                cmds.append(AddFaceCommand(
                    [m.map(v) for v in f.vertices],
                    holes=[[m.map(v) for v in h] for h in (f.holes or [])] or None,
                    auto=False,
                    attrs=transformed_attrs(f.attrs, m)))
            curvas: dict = {}
            for e in self._aristas:
                curva = getattr(e, "curve", None)
                if curva is not None and curva not in curvas:
                    curvas[curva] = Mesh.next_curve_id()
                cmds.append(AddEdgeCommand(
                    m.map(e.a), m.map(e.b),
                    soft=getattr(e, "soft", False) or None,
                    curve=curvas.get(curva)))
        else:
            for g in self._grupos:
                a_grupo(g)
            if self._posiciones:
                cmds.append(_comando_vertices_cls()(self._posiciones, m))
        if not cmds:
            return None
        return cmds[0] if len(cmds) == 1 else CompoundCommand(cmds)


def _caja(viewport, group) -> list:
    """Las 12 aristas de la caja orientada del grupo."""
    from core.group import oriented_box_corners
    c = oriented_box_corners(*viewport._group_obb(group))
    out = []
    for i in range(8):
        for bit in (1, 2, 4):
            if not i & bit:
                out.append((c[i], c[i | bit]))
    return out


# ---- El controlador: menú, opciones, panel ---------------------------------------

class Alinear:
    def __init__(self, app) -> None:
        self.app = app
        cfg = _ajustes()
        self.copiar = _leer_bool(cfg.value("copiar"), False)
        self.escalar = _leer_bool(cfg.value("escalar"), False)
        self.cursor: QPointF | None = None
        self.tool = AlinearTool(self)

    def instalar(self) -> None:
        from . import _interruptor
        _interruptor.apuntar(
            self.app, _interruptor.entrada(self.app, "alinear", "Alinear", self.activar, TIP),
            "Alinear")

    # -- activar / salir --
    def activar(self) -> None:
        from . import _interruptor
        if _interruptor.apagada(self.app):
            return
        vp = self.app.viewport
        if not vp.scene.selection:
            vp.flash_status(_tr("Alinear: selecciona primero lo que quieres "
                            "alinear."), 6000)
            return
        if vp.active_tool is self.tool:
            self.tool.on_activate(vp)    # empezar de nuevo
        else:
            vp.set_active_tool(self.tool)
        vp.setFocus()                    # lo tecleado (medidas) va al visor
        vp.update()

    def volver_a_seleccionar(self) -> None:
        QTimer.singleShot(0, self._seleccionar)

    def _seleccionar(self) -> None:
        win, vp = self.app.window, self.app.viewport
        if vp.active_tool is not self.tool:
            return
        activar = getattr(win, "_activate_tool", None)      # interno de 0.5.8
        if callable(activar):
            try:
                activar("select")
                return
            except Exception:  # noqa: BLE001
                log.exception("_activate_tool('select') falló")
        tools = getattr(win, "_tools", None) or {}
        if tools.get("select") is not None:
            vp.set_active_tool(tools["select"])

    # -- opciones --
    def alternar(self, opcion: str, viewport) -> None:
        setattr(self, opcion, not getattr(self, opcion))
        _ajustes().setValue(opcion, getattr(self, opcion))
        viewport.flash_status(
            _tr("Alinear: {0}, {1}.", _tr('copiar') if self.copiar else _tr('mover'), _tr('escalando') if self.escalar else _tr('sin escalar')), 3000)
        self.tool.refresh_hint(viewport)
        viewport.update()

    def texto_paso(self) -> str:
        n = len(self.tool.puntos)
        return _tr("Paso {0}/4: {1}.", n + 1, _tr(PASOS[min(n, 3)]))

    def avisar_paso(self, viewport) -> None:
        viewport.flash_status(_tr("Alinear · ") + self.texto_paso()
                              + _tr("  (Esc = borrar, Ctrl = mover/copiar)"), 8000)

    # -- panel de respaldo (esquina superior izquierda del visor) --
    # Con la barra de modificar, las opciones van en su submenú, encima del
    # semicírculo; este panel solo sale si no está (o está oculta).
    def _en_barra_modificar(self) -> bool:
        if getattr(self.app.window, "_rosco_lt_barra_dibujo", None):
            return True                  # las opciones van en el submenú del rosco
        barras = getattr(self.app.window, "_rosco_lt_barra_modificar", None) or {}
        return any(getattr(b, "submenu_visible", False) for b in barras.values())

    def _panel(self):
        x, y = 12.0, 12.0
        return {"marco": QRectF(x, y, 290.0, 62.0),
                "mover": QRectF(x + 10.0, y + 30.0, 62.0, 22.0),
                "copiar": QRectF(x + 76.0, y + 30.0, 62.0, 22.0),
                "escalar": QRectF(x + 150.0, y + 30.0, 130.0, 22.0)}

    def clic_panel(self, viewport, screen) -> bool:
        if self._en_barra_modificar():
            return False                 # sus clics los toma la barra de modificar
        g = self._panel()
        p = QPointF(screen)
        if not g["marco"].contains(p):
            return False
        if g["mover"].contains(p) and self.copiar:
            self.alternar("copiar", viewport)
        elif g["copiar"].contains(p) and not self.copiar:
            self.alternar("copiar", viewport)
        elif g["escalar"].contains(p):
            self.alternar("escalar", viewport)
        return True                      # el panel no es un punto

    def dibujar(self, viewport, painter) -> None:
        if self._en_barra_modificar():
            return                       # el submenú de la barra de modificar ya lo muestra
        painter.setRenderHint(QPainter.Antialiasing)
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        f.setBold(False)
        painter.setFont(f)
        g = self._panel()
        painter.setPen(QPen(ROJO, 1.4))
        painter.setBrush(QBrush(QColor(255, 255, 255, 225)))
        painter.drawRoundedRect(g["marco"], 7.0, 7.0)
        titulo = QRectF(g["marco"].left() + 10.0, g["marco"].top() + 6.0,
                        g["marco"].width() - 20.0, 18.0)
        painter.setPen(TINTA)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(titulo, Qt.AlignLeft | Qt.AlignVCenter,
                         _tr("Alinear · ") + self.texto_paso())
        f.setBold(False)
        painter.setFont(f)

        def boton(r, texto, activo) -> None:
            painter.setPen(QPen(ROJO if activo else QColor(180, 178, 169), 1.0))
            painter.setBrush(QBrush(QColor(250, 222, 222) if activo
                                    else QColor(255, 255, 255)))
            painter.drawRoundedRect(r, 4.0, 4.0)
            painter.setPen(QColor(130, 20, 20) if activo else QColor(68, 68, 65))
            painter.drawText(r, Qt.AlignCenter, _tr(texto))

        boton(g["mover"], "Mover", not self.copiar)
        boton(g["copiar"], "Copiar", self.copiar)
        boton(g["escalar"], ("☑" if self.escalar else "☐")
              + _tr(" Escalar al segmento"), self.escalar)

        # Rótulo del paso junto al cursor (no se puede pulsar: va con él).
        if self.cursor is not None and viewport.active_tool is self.tool:
            texto = PASOS[min(len(self.tool.puntos), 3)]
            fm = QFontMetricsF(f)
            w = fm.horizontalAdvance(_tr(texto)) + 12.0
            x, y = self.cursor.x() + 18.0, self.cursor.y() + 18.0
            if x + w > viewport.width() - 4:
                x = self.cursor.x() - 18.0 - w
            r = QRectF(x, y, w, fm.height() + 4.0)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(44, 44, 42, 215)))
            painter.drawRoundedRect(r, 4.0, 4.0)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(r, Qt.AlignCenter, _tr(texto))

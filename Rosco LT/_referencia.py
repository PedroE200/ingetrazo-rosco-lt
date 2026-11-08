# SPDX-License-Identifier: GPL-3.0-or-later
"""Escala por referencia: dos clics marcan un segmento de referencia; se
teclea la longitud que debe tener (o se hace un tercer clic a esa distancia
del primer punto) y la selección se escala por igual en todas las
direcciones desde el primer punto.

Ejemplo: una puerta dibujada de 80 que debe medir 90. Clic en un extremo del
ancho, clic en el otro, teclear 90 + Enter: todo crece 90/80 desde el primer
extremo, que no se mueve.

Vive fuera de ``__init__.py`` a propósito: IngeTrazo crearía una entrada de
menú por cada Tool definida allí.
"""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtGui import QVector3D

from core.units import fmt_len
from tools.base import Tool, ToolContext

log = logging.getLogger("ingetrazo.plugins.rosco_lt.modificar")

_MINIMO = 1e-9


class EscalaReferencia(Tool):
    name = "Rosco LT · escala por referencia"
    icon = "scale"
    description = ("Scale the selection uniformly from a point so a "
                   "reference segment gets the length you type.")
    uses_snap = True
    vcb_label = "Longitud nueva"

    def __init__(self, barra=None) -> None:
        self.barra = barra
        self._reset()

    def _reset(self) -> None:
        self.start_point: QVector3D | None = None      # el primer punto (fijo)
        self.second_point: QVector3D | None = None     # fin del segmento de referencia
        self.hover_point: QVector3D | None = None
        self._grupos: list = []
        self._posiciones: list = []

    # -- ciclo de vida --
    def on_activate(self, viewport) -> None:
        self._reset()
        viewport.flash_status(_tr("Escala por referencia: clic en el primer punto del "
                              "segmento de referencia (ese punto no se moverá)."), 8000)

    def on_deactivate(self, viewport) -> None:
        self._reset()

    def on_cancel(self, viewport) -> None:
        en_curso = self.start_point is not None
        self._reset()
        if en_curso:
            viewport.flash_status(_tr("Escala por referencia: cancelada."), 3000)
        viewport.update()

    # -- ratón --
    def on_hover(self, ctx: ToolContext) -> None:
        self.hover_point = QVector3D(ctx.world)

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        p = QVector3D(ctx.world)
        if self.start_point is None:
            grupos, posiciones = self._objetivos(ctx)
            if not grupos and not posiciones:
                vp.flash_status(_tr("Escala por referencia: selecciona primero lo que "
                                "quieres escalar."), 5000)
                return
            self._grupos, self._posiciones = grupos, posiciones
            self.start_point = p
            vp.flash_status(_tr("Clic en el otro extremo del segmento de referencia."), 8000)
        elif self.second_point is None:
            if (p - self.start_point).length() < _MINIMO:
                return
            self.second_point = p
            vp.flash_status(_tr("Referencia: {0}. Teclea la longitud nueva + Enter (o clic a esa distancia del primer punto).", fmt_len(self._referencia())), 10000)
        else:
            self._aplicar(vp, (p - self.start_point).length())
        vp.update()

    def on_value(self, viewport, value) -> bool:
        if self.second_point is None:
            return False
        try:
            nueva = float(value)
        except (TypeError, ValueError):
            return False
        self._aplicar(viewport, nueva)
        return True

    # -- el escalado --
    def _referencia(self) -> float:
        return (self.second_point - self.start_point).length()

    @staticmethod
    def _objetivos(ctx):
        """Lo que escalan Mover/Rotar/Escalar: la selección, o lo que haya
        bajo el cursor."""
        try:
            from tools.scale import gather_targets              # interno de 0.5.8
            grupos, posiciones = gather_targets(ctx)
        except Exception:  # noqa: BLE001
            log.exception("gather_targets falló")
            return [], []
        return list(grupos or []), [QVector3D(q) for q in (posiciones or [])]

    def _aplicar(self, viewport, nueva: float) -> None:
        ref = self._referencia()
        if nueva <= _MINIMO or ref <= _MINIMO:
            viewport.flash_status(_tr("Escala por referencia: la longitud debe ser "
                                  "mayor que cero."), 4000)
            return
        factor = nueva / ref
        from core.history import (                              # interno de 0.5.8
            CompoundCommand, ScaleGroupCommand, ScaleVerticesCommand,
        )
        centro = QVector3D(self.start_point)
        ordenes = [ScaleGroupCommand(g, centro, factor) for g in self._grupos]
        if self._posiciones:
            ordenes.append(ScaleVerticesCommand(self._posiciones, centro, factor))
        viewport.history.execute(ordenes[0] if len(ordenes) == 1
                                 else CompoundCommand(ordenes))
        error = getattr(viewport.history, "last_error", None)
        viewport.notify_scene_changed()
        if error:
            viewport.flash_status(_tr("Escala por referencia: no se pudo ({0}).", error), 6000)
        else:
            viewport.flash_status(_tr("Escalado ×{0:.4g}: {1} → {2}. Ctrl+Z lo deshace.", factor, fmt_len(ref), fmt_len(nueva)), 6000)
        self._reset()
        viewport.update()

    # -- dibujo --
    def rubber_band_lines(self):
        if self.start_point is None:
            return []
        if self.second_point is None:
            fin = self.hover_point
            return [(self.start_point, fin)] if fin is not None else []
        lineas = [(self.start_point, self.second_point)]
        if self.hover_point is not None:
            lineas.append((self.start_point, self.hover_point))
        return lineas

    def status_clause(self) -> str:
        if self.second_point is not None:
            return _tr("Referencia {0}", fmt_len(self._referencia()))
        return ""

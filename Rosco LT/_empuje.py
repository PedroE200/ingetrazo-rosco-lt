# SPDX-License-Identifier: GPL-3.0-or-later
"""Empujar/Tirar también en caras de grupos y componentes cerrados.

La orden nativa rechaza esas caras («ábrelo primero»). Aquí el clic abre lo que
haga falta (nivel a nivel si hay anidados), la orden trabaja como siempre con el
grupo abierto y, al acabar el empuje, se cierra solo lo que se abrió: lo que ya
tenías abierto sigue abierto. En un componente, IngeTrazo lleva el cambio a todas
sus copias al salir, con su aviso en la barra de estado.

Medida tecleada: va durante el empuje. Después, con el grupo ya cerrado, la orden
nativa la aplicaría fuera del grupo, así que esa corrección se desactiva.
"""
from __future__ import annotations

from ._ajustes import atributo

import logging

from PySide6.QtCore import QTimer

from . import _interruptor

log = logging.getLogger(__name__)

MAX_NIVELES = 8


class EmpujeEnGrupos:
    def __init__(self, tool) -> None:
        self.tool = tool
        self.abiertos: list = []             # lo que abrió este empuje, de fuera a dentro
        self._on_hover = tool.on_hover
        self._on_click = tool.on_click
        self._on_double_click = tool.on_double_click
        self._commit_nativo = tool._commit
        self._on_cancel = tool.on_cancel
        self._on_deactivate = tool.on_deactivate
        self._on_undo = tool.on_undo
        tool.on_hover = self.on_hover
        tool.on_click = self.on_click
        tool.on_double_click = self.on_double_click
        tool._commit = self._commit
        tool.on_cancel = self.on_cancel
        tool.on_deactivate = self.on_deactivate
        tool.on_undo = self.on_undo

    # -- entrar --
    def _entrar(self, ctx) -> bool:
        """Abre el grupo de la cara bajo el cursor, si la hay. Devuelve False si
        no se puede empujar (bloqueado, o sin cara al abrirlo)."""
        vp = ctx.viewport
        x, y = ctx.screen.x(), ctx.screen.y()
        cara, dueno = vp.pick_face_any(x, y)
        if dueno is None:
            return True                      # cara suelta: la orden de siempre
        while dueno is not None and len(self.abiertos) < MAX_NIVELES:
            vp.begin_group_edit(dueno)
            if vp.scene.edit_group is not dueno:
                self._salir(vp)              # bloqueado: IngeTrazo ya lo ha avisado
                return False
            self.abiertos.append(dueno)
            cara, dueno = vp.pick_face_any(x, y)
        if cara is None or dueno is not None:
            self._salir(vp)
            return False
        self.tool.hovered_face = cara
        self.tool._hover_group = None
        self.tool._selected_arm = False
        return True

    def _activa(self) -> bool:
        return _interruptor.ENCENDIDA and not self.tool.dragging

    def on_hover(self, ctx):
        r = self._on_hover(ctx)
        tool = self.tool
        if self._activa() and tool._hover_group is not None:
            # La nativa no resalta estas caras; con su colocación se ven en su sitio.
            cara, sitio = ctx.viewport.pick_face_placement(ctx.screen.x(), ctx.screen.y())
            ctx.viewport.set_hover(cara, sitio)
        return r

    def on_click(self, ctx):
        if self._activa() and not self._entrar(ctx):
            return None
        return self._on_click(ctx)

    def on_double_click(self, ctx):
        if self._activa() and not self._entrar(ctx):
            return None
        r = self._on_double_click(ctx)
        self._salir_si_acabo(ctx.viewport)
        return r

    # -- salir --
    def _salir(self, vp) -> None:
        abiertos, self.abiertos = self.abiertos, []
        if not abiertos:
            return
        for grupo in reversed(abiertos):
            if vp.scene.edit_group is not grupo:
                break                        # ya salió por su cuenta (Esc, otro documento)
            vp.end_one_group_edit()
        tool = self.tool
        tool._last = None                    # ver la nota de arriba
        tool.hovered_face = None
        tool._hover_group = None
        vp.set_hover(None)
        vp.update()

    def _salir_si_acabo(self, vp) -> None:
        if self.abiertos and not self.tool.dragging:
            # Después de que termine lo que esté haciendo la orden.
            QTimer.singleShot(0, lambda: self._salir_seguro(vp))

    def _salir_seguro(self, vp) -> None:
        if self.tool.dragging:
            return                           # ya empezó otro empuje dentro
        try:
            self._salir(vp)
        except Exception:  # noqa: BLE001 — no debe tumbar el bucle de eventos
            log.exception("no se pudo cerrar el grupo tras empujar")

    def _commit(self, viewport):
        r = self._commit_nativo(viewport)
        self._salir_si_acabo(viewport)
        return r

    def on_cancel(self, viewport):
        r = self._on_cancel(viewport)
        self._salir_si_acabo(viewport)
        return r

    def on_undo(self, *args, **kwargs):
        r = self._on_undo(*args, **kwargs)
        if args:
            self._salir_si_acabo(args[0])
        return r

    def on_deactivate(self, viewport):
        r = self._on_deactivate(viewport)
        self._salir_seguro(viewport)
        return r


def instalar(tool) -> None:
    if tool is None or getattr(tool, atributo("empuje"), None) is not None:
        return
    setattr(tool, atributo("empuje"), EmpujeEnGrupos(tool))

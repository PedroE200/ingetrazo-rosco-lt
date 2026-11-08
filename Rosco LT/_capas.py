# SPDX-License-Identifier: GPL-3.0-or-later
"""Capas en Rosco LT: la capa de dibujo y el desplegable que la elige.

IngeTrazo no tiene «capa activa»: una capa es una etiqueta que lleva cada
cara, arista o grupo, y lo nuevo nace en la capa por defecto. La barra de dibujo guarda su
propia capa de dibujo y, cuando una de sus herramientas termina algo (una
base, la altura, el grupo de la pieza), pasa lo nuevo a esa capa con el
comando nativo ``AssignLayerCommand`` (un paso de deshacer).

- Lo nuevo se reconoce por GEOMETRÍA (como para agrupar): Empujar/Tirar
  rehace los objetos de las caras al previsualizar.
- Con Grupo en «grupo» o «componente» se espera a que exista el grupo y se
  le pone la capa a él entero (lo de dentro sigue en la capa por defecto).
- Deshacer y rehacer no vuelven a asignar nada: solo cuenta lo que se hace
  por primera vez con una herramienta de la barra de dibujo.

En la barra de selección el mismo desplegable pasa lo seleccionado a otra
capa.
"""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QActionGroup, QCursor
from PySide6.QtWidgets import QInputDialog, QMenu

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

NUEVA = "Nueva capa…"


def capa_por_defecto() -> str:
    try:
        from core.layers import DEFAULT_LAYER                   # interno de 0.5.8
        return DEFAULT_LAYER
    except Exception:  # noqa: BLE001
        return "Layer 0"


def nombres(scene) -> list:
    """Las capas del dibujo, la de por defecto primero."""
    defecto = capa_por_defecto()
    otras = [ly.name for ly in getattr(scene, "layers", []) if ly.name != defecto]
    return [defecto] + otras


def capa_de(entidad) -> str:
    try:
        from core.layers import layer_of
        return layer_of(entidad)
    except Exception:  # noqa: BLE001
        return capa_por_defecto()


def capa_de_seleccion(scene) -> str | None:
    """La capa común de lo seleccionado, o None si hay varias."""
    capas = {capa_de(e) for e in scene.selection}
    return capas.pop() if len(capas) == 1 else None


def asignar(viewport, entidades, nombre) -> bool:
    entidades = [e for e in entidades if capa_de(e) != nombre]
    if not entidades:
        return False
    from core.history import AssignLayerCommand              # interno de 0.5.8
    viewport.history.execute(AssignLayerCommand(entidades, nombre))
    viewport.notify_scene_changed()
    return True


def _clave_punto(p):
    return (round(p.x(), 5), round(p.y(), 5), round(p.z(), 5))


def _clave_cara(f):
    return frozenset(_clave_punto(p) for p in f.vertices)


def _clave_arista(e):
    return frozenset((_clave_punto(e.a), _clave_punto(e.b)))


class Capas:
    """La capa de dibujo de la barra de dibujo y el vigilante que la aplica."""

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self.capa: str | None = None          # None = la capa por defecto
        self._escena = None
        self._pila = 0
        self._vistos: set = set()             # órdenes ya tratadas (rehacer)
        self._caras: set = set()
        self._aristas: set = set()
        self._grupos: set = set()
        self.agrupando = False                # La barra de dibujo está creando el grupo

    # -- la capa elegida --
    def actual(self, scene) -> str:
        """La capa de dibujo; si ya no existe (otro documento), la de por
        defecto."""
        if self.capa is not None and scene.layer(self.capa) is not None:
            return self.capa
        self.capa = None
        return capa_por_defecto()

    # -- el vigilante (lo llama el reloj de la cadena) --
    def _foto(self, scene) -> None:
        mesh = scene.mesh
        self._caras = {_clave_cara(f) for f in mesh.faces}
        self._aristas = {_clave_arista(e) for e in mesh.edges}
        self._grupos = {id(g) for g in scene.groups}

    def vigilar(self, viewport) -> None:
        scene = viewport.scene
        pila = viewport.history.undo_stack
        if scene is not self._escena:
            self._escena, self._pila, self._vistos = scene, len(pila), set()
            self._foto(scene)
            return
        if len(pila) == self._pila:
            return
        if len(pila) < self._pila:            # deshacer: solo se actualiza
            self._pila = len(pila)
            self._foto(scene)
            return
        # Una pieza que va a ser grupo: se espera al grupo.
        if self.agrupando or self.cadena._antes is not None:
            return
        nuevas = [c for c in pila[self._pila:] if id(c) not in self._vistos]
        self._pila = len(pila)
        self._vistos.update(id(c) for c in nuevas)
        tool = viewport.active_tool
        propia = self.cadena._es_base(tool) or tool is self.cadena.push
        destino = self.actual(scene)
        from core.history import AssignLayerCommand
        if (nuevas and propia and destino != capa_por_defecto()
                and not all(isinstance(c, AssignLayerCommand) for c in nuevas)):
            self._aplicar(viewport, destino)
        self._pila = len(viewport.history.undo_stack)
        self._vistos.update(id(c) for c in viewport.history.undo_stack[-1:])
        self._foto(scene)

    def _aplicar(self, viewport, destino) -> None:
        scene = viewport.scene
        defecto = capa_por_defecto()
        mesh = scene.mesh
        nuevas = [g for g in scene.groups if id(g) not in self._grupos]
        nuevas += [f for f in mesh.faces if _clave_cara(f) not in self._caras]
        nuevas += [e for e in mesh.edges if _clave_arista(e) not in self._aristas]
        # Solo lo que nació en la capa por defecto (lo partido de una cara de
        # otra capa conserva la suya).
        nuevas = [e for e in nuevas if capa_de(e) == defecto]
        if not nuevas:
            return
        try:
            asignar(viewport, nuevas, destino)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo pasar la pieza a la capa %s", destino)

    # -- el desplegable --
    def menu(self, viewport, global_pos, seleccion: bool) -> None:
        """La lista de capas bajo la pastilla. En la barra de dibujo elige la capa de
        dibujo; en la barra de selección pasa lo seleccionado a la capa."""
        scene = viewport.scene
        marcada = capa_de_seleccion(scene) if seleccion else self.actual(scene)
        m = QMenu(self.cadena.app.window)
        grupo = QActionGroup(m)
        for nombre in nombres(scene):
            ly = scene.layer(nombre)
            extra = ""
            if ly is not None and not getattr(ly, "visible", True):
                extra += _tr(" (oculta)")
            if ly is not None and getattr(ly, "locked", False):
                extra += _tr(" (bloqueada)")
            a = QAction(nombre + extra, _tr(m))
            a.setCheckable(True)
            a.setChecked(nombre == marcada)
            a.setData(nombre)
            grupo.addAction(_tr(a))
            m.addAction(_tr(a))
        m.addSeparator()
        nueva = m.addAction(_tr(NUEVA))
        elegida = m.exec(global_pos)
        # El clic que cerró la lista (dentro o fuera) no debe llegar al modelo.
        self.cadena.tragar_clic()
        if elegida is None:
            return
        if elegida is nueva:
            nombre = self._pedir_nombre(scene)
            if not nombre:
                return
        else:
            nombre = elegida.data()
        if seleccion:
            if asignar(viewport, list(scene.selection), nombre):
                viewport.flash_status(_tr("Selección pasada a la capa «{0}».", nombre), 4000)
            return
        if scene.layer(nombre) is None:
            from core.layers import Layer
            scene.layers.append(Layer(nombre))
            scene.version += 1
            viewport.notify_scene_changed()
        self.capa = None if nombre == capa_por_defecto() else nombre
        viewport.flash_status(_tr("Rosco LT: lo que dibujes irá a la capa «{0}».", nombre), 5000)

    def _pedir_nombre(self, scene) -> str | None:
        n = len(scene.layers)
        nombre, ok = QInputDialog.getText(self.cadena.app.window, _tr("Nueva capa"),
                                          _tr("Nombre de la capa:"), text=_tr("Capa {0}", n))
        nombre = nombre.strip() if ok else ""
        return nombre or None

# SPDX-License-Identifier: GPL-3.0-or-later
"""Capas en Rosco: la capa activa, el cajetín de la barra y su mini panel.

La capa del cajetín ES la capa activa de IngeTrazo (la de la barra Capas y la
columna «Activa» del panel): cambiarla aquí la cambia allí, y al revés.
IngeTrazo pasa a la activa los grupos, componentes, cotas y textos que se
crean; Rosco pasa además las caras y aristas sueltas que dibujan sus
herramientas, con el comando nativo ``AssignLayerCommand`` (un paso de
deshacer).

- Lo nuevo se reconoce por GEOMETRÍA (como para agrupar): Empujar/Tirar
  rehace los objetos de las caras al previsualizar.
- Con Grupo en «grupo» o «componente» se espera a que exista el grupo y se
  le pone la capa a él entero (lo de dentro sigue en la capa por defecto).
- Deshacer y rehacer no vuelven a asignar nada: solo cuenta lo que se hace
  por primera vez con una herramienta del anillo.

Los botones del cajetín (hacer activa, aislar, bloquear) actúan sobre la
capa de lo seleccionado; sin selección, sobre la activa. Para que el panel
Capas y su barra se enteren (y «Estado anterior» lo recuerde), se usan sus
propias funciones cuando están.
"""
from __future__ import annotations

from ._idioma import _tr
import logging

from PySide6.QtWidgets import QDockWidget

from ._ajustes import registro

log = registro("anillo")
def capa_por_defecto() -> str:
    try:
        from core.layers import DEFAULT_LAYER                   # interno de IngeTrazo
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
    """La capa común de lo seleccionado, o None si hay varias (o nada)."""
    capas = {capa_de(e) for e in scene.selection}
    return capas.pop() if len(capas) == 1 else None


def activa(scene) -> str:
    """La capa activa de IngeTrazo (donde va lo nuevo)."""
    try:
        from core.layers import active_layer
        return active_layer(scene)
    except Exception:  # noqa: BLE001
        return capa_por_defecto()


def color_de(scene, nombre) -> tuple:
    """``(r, g, b)`` de 0 a 1: el color con que el panel pinta la capa."""
    try:
        from core.layers import layer_color
        ly = scene.layer(nombre)
        if ly is not None:
            return tuple(layer_color(ly))[:3]
    except Exception:  # noqa: BLE001
        pass
    return (0.9, 0.9, 0.9)


def panel_nativo(win):
    """El panel Capas de IngeTrazo (su pestaña), o None."""
    for d in win.findChildren(QDockWidget):
        if d.objectName() == "tray_layers":
            return d.widget()
    return None


def asignar(viewport, entidades, nombre) -> bool:
    entidades = [e for e in entidades if capa_de(e) != nombre]
    if not entidades:
        return False
    from core.history import AssignLayerCommand              # interno de IngeTrazo
    viewport.history.execute(AssignLayerCommand(entidades, nombre))
    viewport.notify_scene_changed()
    return True


def _avisar(viewport) -> None:
    scene = viewport.scene
    try:
        scene.version += 1
    except Exception:  # noqa: BLE001
        pass
    viewport.notify_scene_changed()
    panel = panel_nativo(viewport.window())
    if panel is not None and callable(getattr(panel, "refresh", None)):
        try:
            panel.refresh()
        except Exception:  # noqa: BLE001
            log.exception("el panel Capas no se refrescó")


def hacer_activa(viewport, nombre) -> None:
    panel = panel_nativo(viewport.window())
    if panel is not None and callable(getattr(panel, "set_active", None)):
        panel.set_active(nombre)
    else:
        from core.layers import set_active
        set_active(viewport.scene, nombre)
    _avisar(viewport)


def aislada(viewport, nombre) -> bool:
    panel = panel_nativo(viewport.window())
    try:
        if panel is not None and callable(getattr(panel, "isolated_layers", None)):
            return nombre in panel.isolated_layers()
        from core.layers import is_isolated
        return bool(is_isolated(viewport.scene, nombre))
    except Exception:  # noqa: BLE001
        return False


def aislar(viewport, nombre) -> None:
    """Muestra solo ``nombre``; si ya lo estaba, vuelven todas."""
    panel = panel_nativo(viewport.window())
    if panel is not None and callable(getattr(panel, "toggle_isolate", None)):
        panel.toggle_isolate([nombre])
    else:
        from core.layers import is_isolated, isolate, set_visible
        scene = viewport.scene
        if is_isolated(scene, nombre):
            set_visible(scene, [ly.name for ly in scene.layers], True)
        else:
            isolate(scene, [nombre])
    _avisar(viewport)


def bloqueada(scene, nombre) -> bool:
    ly = scene.layer(nombre) if nombre else None
    return bool(ly is not None and getattr(ly, "locked", False))


def oculta(scene, nombre) -> bool:
    ly = scene.layer(nombre) if nombre else None
    return bool(ly is not None and not getattr(ly, "visible", True))


def bloquear(viewport, nombre) -> bool:
    """Bloquea o desbloquea ``nombre``. Devuelve el estado nuevo."""
    nuevo = not bloqueada(viewport.scene, nombre)
    panel = panel_nativo(viewport.window())
    if panel is not None and callable(getattr(panel, "set_locked", None)):
        panel.set_locked([nombre], nuevo)
    else:
        from core.layers import set_locked
        set_locked(viewport.scene, [nombre], nuevo)
    _avisar(viewport)
    return nuevo


def _clave_punto(p):
    return (round(p.x(), 5), round(p.y(), 5), round(p.z(), 5))


def _clave_cara(f):
    return frozenset(_clave_punto(p) for p in f.vertices)


def _clave_arista(e):
    return frozenset((_clave_punto(e.a), _clave_punto(e.b)))


class Capas:
    """La capa activa vista desde el anillo y el vigilante que la aplica."""

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self._escena = None
        self._pila = 0
        self._vistos: set = set()             # órdenes ya tratadas (rehacer)
        self._caras: set = set()
        self._aristas: set = set()
        self._grupos: set = set()
        self.agrupando = False                # el anillo está creando el grupo
        self.mini = None                      # el mini panel (``_capas_panel``)

    # -- la capa elegida: la activa de IngeTrazo --
    def actual(self, scene) -> str:
        return activa(scene)

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

    # -- el mini panel bajo el cajetín --
    def abrir(self, viewport, global_pos) -> None:
        from . import _edicion
        if not _edicion.con("capas_panel"):
            self._lista(viewport, global_pos)
            return
        from ._capas_panel import MiniCapas
        if self.mini is None:
            self.mini = MiniCapas(self.cadena)
        self.mini.abrir(viewport, global_pos)

    def cerrar(self) -> None:
        if self.mini is not None:
            self.mini.close()

    def _lista(self, viewport, global_pos) -> None:
        """Sin el mini panel: la lista de capas en un menú; la elegida pasa a
        ser la activa. Al final, «Nueva capa…»."""
        from PySide6.QtWidgets import QInputDialog, QMenu
        from ._idioma import _tr
        scene = viewport.scene
        act = activa(scene)
        m = QMenu(self.cadena.app.window)
        for nombre in nombres(scene):
            a = m.addAction(_tr(nombre))
            a.setCheckable(True)
            a.setChecked(nombre == act)
            a.setData(nombre)
        m.addSeparator()
        nueva = m.addAction(_tr("Nueva capa…"))
        elegida = m.exec(global_pos)
        if elegida is None:
            return
        try:
            if elegida is nueva:
                nombre, ok = QInputDialog.getText(self.cadena.app.window, _tr("Nueva capa"),
                                                  _tr("Nombre de la capa:"),
                                                  text=_tr("Capa {0}", len(scene.layers)))
                nombre = (nombre or "").strip()
                if not ok or not nombre:
                    return
                from core.layers import Layer, unique_name     # como el mini panel
                if scene.layer(nombre) is not None:
                    nombre = unique_name({ly.name for ly in scene.layers}, nombre)
                scene.layers.append(Layer(nombre))
                hacer_activa(viewport, nombre)
            else:
                hacer_activa(viewport, elegida.data())
            viewport.flash_status(_tr("Capa activa: «{0}».", activa(scene)), 3000)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo cambiar la capa activa")
        viewport.update()


def pintar_aplicar(p, cx, cy, s=1.0) -> None:
    """Como «Pasar a la capa activa» de IngeTrazo, en claro: dos hojas, la de
    arriba naranja, y una flecha hacia abajo."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QBrush, QColor, QPen
    negro, naranja = QColor(30, 30, 30), QColor(240, 110, 40)
    p.setPen(QPen(negro, 1.1))
    p.setBrush(QBrush(QColor(255, 255, 255)))
    p.drawRoundedRect(QRectF(cx - 7 * s, cy - 2 * s, 10 * s, 7 * s), 1.5, 1.5)
    p.setBrush(QBrush(naranja))
    p.drawRoundedRect(QRectF(cx - 5 * s, cy - 6 * s, 10 * s, 7 * s), 1.5, 1.5)
    p.setPen(QPen(negro, 1.5))
    ax = cx + 6 * s
    p.drawLine(QPointF(ax, cy - 1 * s), QPointF(ax, cy + 6 * s))
    p.drawLine(QPointF(ax - 2.6 * s, cy + 3.4 * s), QPointF(ax, cy + 6 * s))
    p.drawLine(QPointF(ax + 2.6 * s, cy + 3.4 * s), QPointF(ax, cy + 6 * s))

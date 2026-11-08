# SPDX-License-Identifier: GPL-3.0-or-later
"""Rosco LT: la barra semicircular Desplazar · Escalar · Simetría · Rotar.
Con la barra de dibujo activa sus botones van en la mitad de abajo del anillo de
la barra de dibujo; esta barra suelta solo sale con Alinear (y su submenú) o anclada.

No hay herramientas propias: la barra ACTIVA las nativas de IngeTrazo 0.5.8
(``MoveTool``, ``ScaleTool``, ``FlipTool``, ``RotateTool``), que ya actúan
sobre la selección, y la de la extensión «alinear» (``window._rosco_lt_alinear``). Así
se conservan su snap, el bloqueo de ejes, Ctrl = copia, las medidas tecleadas
y el deshacer.

- Desplazar y Rotar tienen submenú, debajo del semicírculo: Desplazar =
  mover · copia · alinear; Rotar = sin copia · con copia. «Copia» deja la
  copia de la nativa (como Ctrl) armada en cada operación.

- Mientras el ratón se mueve, la barra ES el cursor
  (``_flotante.cursor_compuesto``): la dibuja el sistema, va exactamente con
  el ratón y el puntero queda siempre en su centro.
- Al parar el ratón (REPOSO_MS) se queda fija en una ventanita
  (``_flotante.Flotante``) para hacer clic en sus botones; al salir de ella
  vuelve a ser el cursor. Solo la banda, el rótulo y el submenú reciben clics.
- Es transparente, con contorno rojo de esquinas redondeadas; los iconos son
  siluetas negras macizas con halo blanco.
- Con Alinear activa, su submenú (paso actual, Mover/Copiar, Escalar) va
  encima del semicírculo y la barra sigue visible durante los cuatro puntos.
- El comando Seleccionar (su botón, su atajo o el botón activo de la barra)
  cierra la barra y la orden en curso, como pinchar fuera de la selección;
  vuelve al seleccionar de nuevo.
"""
from __future__ import annotations

from ._idioma import _tr
import logging
import math

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

from ._flotante import (
    HALO, ROJO, Flotante, app_activa, boton_en, chincheta_en, cursor_compuesto,
    dibujar_banda, dibujar_chincheta, etiqueta, mascara_chincheta, rect_etiqueta,
    restaurar_cursor, sector, texto_chincheta,
)
from . import _interruptor
from ._referencia import EscalaReferencia
from ._vertices import MENSAJE as MENSAJE_VERTICES, EditorVertices

log = logging.getLogger("ingetrazo.plugins.rosco_lt.modificar")

TINTA = QColor(44, 44, 42)

# ---- Los botones, de izquierda a derecha ---------------------------------------
ORDEN = ("move", "scale", "flip", "rotate")
NOMBRES = {"move": "Desplazar: mover · copia · alinear · empujar/tirar · vértices",
           "scale": "Escalar: libre · por referencia",
           "flip": "Simetría", "rotate": "Rotar: sin copia · con copia",
           "align": "Alinear", "select": "Seleccionar"}
EXTERNAS = ()                          # botones que abren otra extensión (ninguno)
MODOS = {"move": ("mover", "copia", "alinear", "empujar/tirar", "vértices"),
         "scale": ("libre", "por referencia"),
         "rotate": ("sin copia", "con copia")}
COPIA = {"move": "copia", "rotate": "con copia"}      # el modo que copia
MENSAJES = {
    "move": "Desplazar: clic en el punto base y en el destino (o teclea la "
            "distancia + Enter). Ctrl = dejar una copia.",
    "scale": "Escalar: arrastra un tirador verde de la caja (las esquinas "
             "mantienen la proporción) o teclea el factor + Enter.",
    "pushpull": "Empujar/Tirar: clic en una cara y mueve para darle altura (o "
                "teclea la distancia + Enter). También en grupos y componentes "
                "cerrados: en un componente, el cambio llega a todas sus copias. "
                "Sigue activa: clic derecho para terminar, doble clic izquierdo "
                "para cancelar.",
    "flip": "Simetría: clic en el plano rojo, verde o azul (o flechas para "
            "fijar el eje). Ctrl = simetría de una copia.",
    "rotate": "Rotar: clic en el centro, en el brazo de referencia y en el "
              "ángulo final (o teclea los grados + Enter). Ctrl = copia.",
}
_CLASES = {"SelectTool": "select", "MoveTool": "move", "ScaleTool": "scale",
           "FlipTool": "flip", "RotateTool": "rotate"}
TIP = ("Rosco LT: una barra semicircular junto al cursor para Desplazar, "
       "Escalar, Simetría y Rotar la selección.")

# ---- Geometría de la barra (píxeles) -----------------------------------------------
R_INT = 34.0                           # radio interior de la banda
R_EXT = 90.0                           # radio exterior
ZONA_R = R_EXT + 6.0                   # dentro de este semicírculo la barra no se mueve
ZONA_BAJO = 8.0                        # …y hasta estos px por debajo del ancla
MARGEN = 6.0                           # a los bordes del visor
TOLERANCIA = 2.0                       # px de más para acertar el clic
# Submenú de Alinear, encima del semicírculo.
SUB_W, SUB_H = 262.0, 56.0
SUB_HUECO = 8.0                        # entre la banda y el submenú
SUB_ZONA = 6.0                         # px de más alrededor (correa quieta)
# Submenú de modos (Desplazar, Rotar), debajo del semicírculo.
PANEL_W, PANEL_H = 336.0, 56.0
PANEL_HUECO = 14.0                     # entre el centro del arco y el submenú
# La ventanita: el rótulo, la chincheta y el submenú de Alinear encima; el
# de modos debajo.
VENTANA_W, VENTANA_H = 350, 305
ANCLA_LOCAL = QPointF(175.0, 220.0)
SINCRONIA_MS = 150                     # repaso de visibilidad sin mover el ratón
REPOSO_MS = 300                        # ratón parado este tiempo: la barra se fija


def _ajustes() -> QSettings:
    from ._ajustes import ajustes
    return ajustes("modificar")


def _leer_bool(valor, por_defecto: bool) -> bool:
    if valor is None:
        return por_defecto
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "yes", "si", "sí")
    return bool(valor)


def _ocupada(tool) -> bool:
    """La herramienta tiene una operación en curso (punto base puesto, tirador
    de escala cogido, giro desde los tiradores de Mover…)."""
    return any(getattr(tool, nombre, None) is not None
               for nombre in ("start_point", "_grip", "_grip_rot")) \
        or bool(getattr(tool, "dragging", False))     # Empujar/Tirar en marcha


def _firma(selection) -> frozenset:
    return frozenset(id(e) for e in selection)


class _Filtro(QObject):
    """Filtro de eventos del visor: le pasa el ratón a la barra."""

    def __init__(self, barra, parent) -> None:
        super().__init__(parent)
        self.barra = barra

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        try:
            return self.barra.evento(obj, ev)
        except Exception:  # noqa: BLE001 — un fallo nunca bloquea el ratón
            log.exception("fallo en el filtro de eventos")
            return False


class BarraModificar:
    def __init__(self, app) -> None:
        self.app = app
        self.visible = _leer_bool(
            _ajustes().value("visible"), True)
        self.cursor: QPointF | None = None    # última posición del ratón (px)
        self.ancla: QPointF | None = None     # centro del arco (px del visor)
        self._bajo: str | None = None         # botón bajo el cursor
        self._apretado = False                # un clic de la barra en curso
        self._cerrada: frozenset | None = None  # selección al cerrarla
        self._forzada = False                 # abierta desde la barra de dibujo, sin selección
        self.submenu_visible = False          # el de Alinear, a la vista
        self._accion = None
        self._filtro = None
        self.win = None
        self._pendiente = False
        self._reloj = None
        self.fijo = False                     # barra fija (ventanita) o cursor
        self.anclada = False                  # chincheta: fija y siempre visible
        self._reposo = None
        self._cursor = None                   # la barra como cursor
        self._cursor_clave = None
        self._cursor_puesto = False
        self._estado_pintado = None
        # Modos de Desplazar y Rotar (durante la sesión).
        self.modo = {clave: modos[0] for clave, modos in MODOS.items()}
        self._pila_armada = None              # deshacer cuando se armó la copia
        self._multicopia = None               # Desplazar · copia: (punto base, selección, pila)
        self.referencia = EscalaReferencia(self)   # Escalar «por referencia»
        self.vertices = EditorVertices(self)       # Desplazar «vértices»

    # -- instalación --
    def instalar(self) -> None:
        app = self.app
        self.win = Flotante(self, app.window, app.viewport,
                            VENTANA_W, VENTANA_H, ANCLA_LOCAL)
        # El overlay ya no dibuja nada: solo avisa de que algo pudo cambiar.
        app.add_overlay(self.dibujar)
        app.add_overlay(self.vertices.dibujar)    # el cuadradito verde
        self._filtro = _Filtro(self, app.viewport)
        app.viewport.installEventFilter(self._filtro)
        self._reloj = QTimer(app.window)
        self._reloj.setInterval(SINCRONIA_MS)
        self._reloj.timeout.connect(self._sincronizar)
        self._reloj.start()
        self._reposo = QTimer(app.window)
        self._reposo.setSingleShot(True)
        self._reposo.setInterval(REPOSO_MS)
        self._reposo.timeout.connect(self._fijar)
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.applicationStateChanged.connect(lambda _e: self._sincronizar())
        self._accion = _interruptor.entrada(
            app, "barra_modificar", "Barra de modificar (suelta)", self.alternar, TIP)
        _interruptor.apuntar(app, self._accion, "Barra de modificar (suelta)")
        if self._accion is not None:
            self._accion.setCheckable(True)
            self._accion.setChecked(self.visible)
        # El comando Seleccionar (botón, atajo, menú) cierra la barra. Solo
        # su ``triggered``: volver a Seleccionar por código (al terminar
        # Alinear) no la cierra.
        seleccionar = (getattr(app.window, "_tool_actions", None) or {}).get("select")
        if seleccionar is not None:
            seleccionar.triggered.connect(lambda _c=False: self.cerrar())
        else:
            log.warning("no encontré la acción Seleccionar: no cerrará la barra")
        if not self._herramientas():
            log.warning("no encontré window._tools: las herramientas nativas "
                        "se reconocerán por su clase")

    def alternar(self) -> None:
        if _interruptor.apagada(self.app):
            if self._accion is not None:
                self._accion.setChecked(self.visible)
            return
        if self._accion is not None:
            self.visible = self._accion.isChecked()
        else:
            self.visible = not self.visible
        _ajustes().setValue("visible", self.visible)
        vp = self.app.viewport
        vp.flash_status(_tr("Rosco LT: barra visible." if self.visible
                        else "Rosco LT: barra oculta."), 3000)
        self._sincronizar()

    def cerrar(self) -> None:
        """Como pinchar fuera de la selección: la barra se va hasta que se
        vuelva a seleccionar (la orden en curso ya la cerró Seleccionar)."""
        vp = self.app.viewport
        self._cerrada = _firma(vp.scene.selection)
        self._forzada = False
        self._soltar()
        self._sincronizar()

    def abrir(self) -> None:
        """Desde la barra de dibujo (su icono de media corona): Seleccionar con la barra
        abierta junto al cursor, aunque no haya nada seleccionado —
        Desplazar, Escalar y Rotar toman entonces lo que haya bajo el
        cursor en su primer clic."""
        if _interruptor.apagada(self.app):
            return
        vp = self.app.viewport
        if not self.visible:
            self.visible = True
            _ajustes().setValue("visible", True)
            if self._accion is not None:
                self._accion.setChecked(True)
        self._cerrada = None
        self._forzada = True
        self._soltar()
        aqui = vp.mapFromGlobal(QCursor.pos())
        if vp.rect().contains(aqui) and not self.anclada:
            # Llamada desde Rosco LT: aparece ya fija donde está el ratón.
            self.cursor = QPointF(aqui)
            self.fijo = True
            self.ancla = QPointF(aqui)
        # Por código, no con la acción: su ``triggered`` cerraría la barra.
        self._activar_nativa("select")
        vp.setFocus()
        vp.flash_status(_tr("Rosco LT: elige Desplazar, Escalar, Simetría o Rotar. "
                        "Sin selección, toman lo que haya bajo el cursor."), 7000)
        self._sincronizar()

    # -- herramientas --
    def _herramientas(self) -> dict:
        tools = getattr(self.app.window, "_tools", None)
        return tools if isinstance(tools, dict) else {}

    def _alinear(self):
        """El controlador de la extensión «alinear», si está cargada."""
        ctl = getattr(self.app.window, "_rosco_lt_alinear", None)
        return ctl if callable(getattr(ctl, "activar", None)) else None

    def _barra_dibujo(self):
        """La cadena de la barra de dibujo (``window._rosco_lt_barra_dibujo``), si está."""
        cadenas = getattr(self.app.window, "_rosco_lt_barra_dibujo", None) or {}
        return next((c for c in cadenas.values()
                     if callable(getattr(c, "activar", None))), None)

    def _extension(self, clave):
        return self._alinear() if clave == "align" else self._barra_dibujo()

    @staticmethod
    def _boton_de(clave):
        """El botón de la barra de una herramienta activa (Alinear y
        Empujar/Tirar van dentro de Desplazar)."""
        return "move" if clave in ("align", "pushpull", "vertices") else clave

    def _clave_activa(self, viewport) -> str | None:
        activa = viewport.active_tool
        if activa is self.referencia:
            return "scale"
        if activa is self.vertices:
            return "vertices"
        ctl = self._alinear()
        if ctl is not None and getattr(ctl, "tool", None) is activa:
            return "align"
        tools = self._herramientas()
        for clave in ("select", "move", "scale", "flip", "rotate", "pushpull"):
            if tools.get(clave) is not None and tools[clave] is activa:
                return clave
        # Sin ``window._tools`` (otra versión): por la clase nativa exacta,
        # nunca por una subclase de otra extensión.
        return _CLASES.get(type(activa).__name__) if not tools else None

    def activar(self, clave: str, cambiar: bool = False) -> None:
        """Activa la herramienta ``clave``; si ya es la activa, es el comando
        Seleccionar: cierra la orden y la barra. Con ``cambiar`` no mira cuál
        hay: Desplazar desde Empujar, que comparten botón aquí y no en el rosco."""
        vp = self.app.viewport
        self._bajo = None
        if not cambiar and clave == self._boton_de(self._clave_activa(vp)):
            self._seleccionar()
            return
        if clave == "move" and self.modo["move"] == "alinear":
            self._activar_alinear()
            return
        if clave == "move" and self.modo["move"] == "empujar/tirar":
            self._activar_empujar()
            return
        if clave == "move" and self.modo["move"] == "vértices":
            self._activar_vertices()
            return
        if clave == "scale" and self.modo["scale"] == "por referencia":
            self._activar_referencia()
            return
        if clave in EXTERNAS:
            ext = self._extension(clave)
            if ext is None:
                vp.flash_status(_tr("Rosco LT: la extensión «{0}» no está instalada (Extensiones ▸ Abrir carpeta de plugins).", NOMBRES[clave].split(':')[0]), 6000)
                return
            ext.activar()
            self._sincronizar()
            return
        # La barra sigue fija tras el clic (con el submenú de Alinear, si
        # toca): se eligen las opciones antes del primer punto.
        if not self._activar_nativa(clave):
            vp.flash_status(_tr("Rosco LT: no encontré la herramienta «{0}».", NOMBRES[clave]), 5000)
            return
        vp.setFocus()                   # lo tecleado (medidas) va al visor
        self._armar_copia(vp, decir=False)
        vp.flash_status(_tr(MENSAJES[clave]) + _tr(self._texto_copia(clave)), 7000)
        self._sincronizar()

    def _activar_alinear(self) -> None:
        vp = self.app.viewport
        ctl = self._alinear()
        if ctl is None:
            vp.flash_status(_tr("Rosco LT: la extensión «Alinear» no está instalada "
                            "(Extensiones ▸ Abrir carpeta de plugins)."), 6000)
            return
        ctl.activar()
        self._sincronizar()

    def _activar_empujar(self) -> None:
        vp = self.app.viewport
        if not self._activar_nativa("pushpull"):
            vp.flash_status(_tr("Rosco LT: no encontré Empujar/Tirar."), 4000)
            return
        vp.setFocus()
        vp.flash_status(_tr(MENSAJES["pushpull"]), 7000)
        self._sincronizar()

    def _activar_vertices(self) -> None:
        vp = self.app.viewport
        vp.set_active_tool(self.vertices)
        vp.setFocus()                   # la distancia tecleada va al visor
        vp.flash_status(_tr(MENSAJE_VERTICES), 9000)
        self._sincronizar()

    def _activar_referencia(self) -> None:
        vp = self.app.viewport
        vp.set_active_tool(self.referencia)
        vp.setFocus()                   # la longitud tecleada va al visor
        self._sincronizar()

    def _texto_copia(self, clave) -> str:
        if clave in COPIA and self.modo[clave] == COPIA[clave]:
            return " — Modo copia: cada operación deja el original."
        return ""

    # -- los modos (submenú de Desplazar y Rotar) --
    def elegir_modo(self, clave, modo) -> None:
        """Un modo del submenú: se aplica ya a la herramienta."""
        vp = self.app.viewport
        if modo == "alinear" and self._alinear() is None:
            self._activar_alinear()           # avisa de que falta la extensión
            return
        self.modo[clave] = modo
        activa = self._clave_activa(vp)
        if clave == "scale":
            # Libre = la nativa (tiradores); por referencia = la de la barra de modificar.
            if modo == "por referencia":
                if vp.active_tool is not self.referencia:
                    self._activar_referencia()
            elif vp.active_tool is self.referencia:
                self._activar_nativa("scale")
                vp.flash_status(_tr(MENSAJES["scale"]), 5000)
            self._sincronizar()
            return
        if clave == "move" and modo == "alinear":
            if activa != "align":
                self._activar_alinear()
            return
        if clave == "move" and modo == "empujar/tirar":
            if activa != "pushpull":
                self._activar_empujar()
            return
        if clave == "move" and modo == "vértices":
            if activa != "vertices":
                self._activar_vertices()
            return
        if clave == "move" and activa in ("align", "pushpull", "vertices"):
            self._activar_nativa("move")      # de Alinear / Empujar / Vértices a Mover / copia
            vp.flash_status(_tr(MENSAJES["move"]), 5000)
        self._armar_copia(vp)
        self._sincronizar()

    def _armar_copia(self, viewport, decir: bool = True) -> None:
        """Deja la copia de la nativa (``_copy``, como Ctrl) según el modo."""
        clave = self._clave_activa(viewport)
        if clave not in COPIA:
            return
        tool = viewport.active_tool
        quiere = self.modo[clave] == COPIA[clave]
        cambiar = getattr(tool, "_toggle_copy", None)      # interno de 0.5.8
        if not callable(cambiar) or bool(getattr(tool, "_copy", False)) == quiere:
            self._pila_armada = len(viewport.history.undo_stack)
            return
        try:
            cambiar(viewport, say=decir)
        except TypeError:
            cambiar(viewport)
        self._pila_armada = len(viewport.history.undo_stack)

    def vigilar_copias(self, viewport) -> None:
        """Desplazar en modo copia hace copias seguidas: tras cada copia se
        vuelve a coger lo mismo desde el mismo punto base, así cada clic deja
        otra copia, hasta Esc (que suelta la orden como siempre)."""
        tool = viewport.active_tool
        if self._clave_activa(viewport) != "move" or self.modo.get("move") != COPIA["move"]:
            self._multicopia = None
            return
        pila = len(getattr(viewport.history, "undo_stack", ()) or ())
        if getattr(tool, "start_point", None) is not None:
            grab = getattr(tool, "grab", None)
            if grab is not None and getattr(tool, "_copy", False):
                from PySide6.QtGui import QVector3D
                self._multicopia = (QVector3D(grab), list(viewport.scene.selection), pila)
            return
        if self._multicopia is None:
            return
        grab, sel, pila0 = self._multicopia
        self._multicopia = None
        if pila <= pila0 or not sel:
            return                              # cancelada con Esc: se acaban las copias
        QTimer.singleShot(0, lambda: self._otra_copia(viewport, grab, sel))

    def _otra_copia(self, viewport, grab, sel) -> None:
        """La siguiente copia: lo de antes, cogido otra vez por el mismo punto."""
        tool = viewport.active_tool
        if self._clave_activa(viewport) != "move" or getattr(tool, "start_point", None) is not None:
            return
        try:
            from PySide6.QtCore import QPointF as _P
            from tools.base import ToolContext
            viewport.scene.select(sel, mode="replace")
            self._armar_copia(viewport, decir=False)
            q = viewport._world_to_pixel(grab)
            pantalla = _P(q[0], q[1]) if q is not None else _P(0.0, 0.0)
            tool.on_click(ToolContext(viewport, grab, pantalla, Qt.NoModifier, None))
            # Apuntada ya la siguiente (sin esperar a que se mueva el ratón).
            self._multicopia = (grab, list(sel), len(viewport.history.undo_stack))
            viewport.notify_scene_changed()
            viewport.update()
            viewport.flash_status(_tr("Copia múltiple: cada clic deja otra copia · Esc termina."), 6000)
        except Exception:  # noqa: BLE001 — sin cadena, la copia hecha se queda
            log.exception("no se pudo seguir con la copia múltiple")

    def _rearmar_copia(self, viewport) -> None:
        """Las nativas desarman la copia tras cada operación: en modo copia
        se vuelve a armar (si Ctrl la quitó a mano, espera a la siguiente)."""
        clave = self._clave_activa(viewport)
        if (clave not in COPIA or self.modo[clave] != COPIA[clave]
                or _ocupada(viewport.active_tool)
                or getattr(viewport.active_tool, "_copy", True)):
            return
        if len(viewport.history.undo_stack) != self._pila_armada:
            self._armar_copia(viewport, decir=False)

    def _seleccionar(self) -> None:
        """El comando Seleccionar, como su botón: su ``triggered`` cierra la
        barra (y si no existe la acción, se cierra aquí)."""
        accion = (getattr(self.app.window, "_tool_actions", None) or {}).get("select")
        if accion is not None:
            accion.trigger()
            return
        self._activar_nativa("select")
        self.cerrar()

    def _activar_nativa(self, clave: str) -> bool:
        win, vp = self.app.window, self.app.viewport
        activar = getattr(win, "_activate_tool", None)      # interno de 0.5.8
        if callable(activar) and clave in self._herramientas():
            try:
                activar(clave)          # marca el botón y el rótulo de la barra
                return True
            except Exception:  # noqa: BLE001 — queda la acción del menú
                log.exception("_activate_tool(%r) falló", clave)
        accion = (getattr(win, "_tool_actions", None) or {}).get(clave)
        if accion is not None:
            accion.trigger()
            return True
        tool = self._herramientas().get(clave)
        if tool is None:
            return False
        vp.set_active_tool(tool)
        return True

    # -- cuándo se ve --
    def _en_juego(self, viewport) -> bool:
        if not self.visible:
            return False
        if self.anclada:
            return True                      # anclada: siempre a la vista
        clave = self._clave_activa(viewport)
        if clave is None:
            self._forzada = False            # otra herramienta: se acabó
            return False
        if not viewport.scene.selection and not self._forzada:
            return False
        if not self._forzada and self._con_barra_seleccion():
            # Con Seleccionar, Desplazar, Alinear, Escalar, Simetría y Rotar
            # manda la barra de selección de la barra de dibujo (lleva estos botones en su
            # arco de dentro, y Alinear su submenú); la barra de modificar sale anclado o
            # desde ``abrir``.
            return False
        if self._cerrada is not None:
            if _firma(viewport.scene.selection) == self._cerrada:
                return False
            self._cerrada = None             # otra selección: vuelve
        # Alinear sigue con la barra (y su submenú) durante sus cuatro puntos;
        # las nativas la ocultan mientras operan.
        if clave != "align" and _ocupada(viewport.active_tool):
            return False
        if getattr(viewport, "_box_active", False):     # ventana de selección
            return False
        if getattr(viewport, "nav_mode", None) is not None:
            return False
        return True

    def _con_barra_seleccion(self) -> bool:
        """La barra de dibujo está cargada."""
        return bool(getattr(self.app.window, "_rosco_lt_barra_dibujo", None))

    def _con_submenu(self, viewport) -> bool:
        return self._clave_activa(viewport) == "align" and self._alinear() is not None

    def _panel_clave(self, viewport):
        """El botón cuyo submenú de modos se ve (solo con la barra fija)."""
        if not self.fijo or self.ancla is None:
            return None
        boton = self._boton_de(self._clave_activa(viewport))
        return boton if boton in MODOS else None

    def _modo_en(self, p):
        """``(dentro_del_submenú_de_modos, modo)`` para el punto ``p``."""
        clave = self._panel_clave(self.app.viewport)
        if clave is None or p is None:
            return False, None
        g = _panel(self.ancla, clave)
        if not g["marco"].contains(p):
            return False, None
        for modo, r in g["chips"]:
            if r.contains(p):
                return True, modo
        return True, None

    def _pulsar_modo(self, modo) -> None:
        clave = self._panel_clave(self.app.viewport)
        if clave is not None and modo is not None:
            self.elegir_modo(clave, modo)

    def _sincronizar(self) -> None:
        """Al moverse, la barra es el cursor; parada, la ventanita fija."""
        self._pendiente = False
        if self.win is None or not _interruptor.ENCENDIDA:
            return
        try:
            self.vigilar_copias(self.app.viewport)
        except Exception:  # noqa: BLE001
            log.exception("fallo vigilando la copia múltiple")
        self.win.vigilar_pulsacion()
        if self.win.pulsando:
            return                           # clic sostenido: nada cambia hasta soltar
        vp = self.app.viewport
        en_juego = self._en_juego(vp)
        ver = (en_juego and app_activa() and vp.isVisible()
               and not self.app.window.isMinimized())
        if not ver:
            if self.win.isVisible():
                self.win.hide()
            self._quitar_cursor(vp)
            self.submenu_visible = False
            if not en_juego:
                self._soltar()
            return
        # Alinear sabe así que su submenú ya va en la barra (como cursor o fija).
        self.submenu_visible = self._con_submenu(vp)
        self._rearmar_copia(vp)
        if self.fijo and self.ancla is not None:
            self._quitar_cursor(vp)
            self.win.colocar(self.ancla)
            self._fijar_mascara(vp)
            estado = (self.ancla.x(), self.ancla.y(), self._bajo, self.anclada,
                      self._clave_submenu(vp), self._clave_activa(vp),
                      tuple(sorted(self.modo.items())))
            if not self.win.isVisible():
                self.win.show()
                self.win.update()
            elif estado != self._estado_pintado:
                self.win.update()
            self._estado_pintado = estado
        else:
            if self.win.isVisible():
                self.win.hide()
            self._poner_cursor(vp)

    def _clave_submenu(self, viewport):
        """Lo que cambia el dibujo del submenú de Alinear (o None)."""
        if not self._con_submenu(viewport):
            return None
        ctl = self._alinear()
        try:
            return (ctl.texto_paso(), bool(ctl.copiar), bool(ctl.escalar))
        except Exception:  # noqa: BLE001
            return ("?",)

    def _poner_cursor(self, viewport) -> None:
        """La barra como cursor del visor (la hace el sistema: sin retraso)."""
        tool = viewport.active_tool
        con_submenu = self._con_submenu(viewport)
        clave = (getattr(tool, "icon", None), self._clave_activa(viewport),
                 frozenset(self._faltan()), self._clave_submenu(viewport),
                 bool(getattr(tool, "_copy", False)),
                 round(viewport.devicePixelRatioF(), 2))
        if self._cursor is None or clave != self._cursor_clave:
            if con_submenu:
                medio = max(R_EXT, SUB_W / 2.0) + 6.0
                arriba = R_EXT + SUB_HUECO + SUB_H + 6.0
            else:
                medio = arriba = R_EXT + 6.0
            self._cursor = cursor_compuesto(viewport, tool, self._pintar_banda,
                                            medio, arriba)
            self._cursor_clave = clave
        viewport.setCursor(self._cursor)
        self._cursor_puesto = True

    def _quitar_cursor(self, viewport) -> None:
        if self._cursor_puesto:
            self._cursor_puesto = False
            restaurar_cursor(viewport)

    def _fijar(self) -> None:
        """El ratón se ha parado: la barra se queda fija donde está."""
        vp = self.app.viewport
        if (self.fijo or self.cursor is None or not self._en_juego(vp)
                or not vp.underMouse()):
            return
        self.fijo = True
        self.ancla = QPointF(self.cursor)
        self._bajo = None
        self._sincronizar()

    def _soltar(self) -> None:
        """Vuelve al modo cursor (la barra acompaña al ratón). Anclada se
        queda donde está."""
        self._bajo = None
        self._estado_pintado = None
        if self.anclada:
            return
        self.fijo = False
        self.ancla = None

    # -- la chincheta --
    def _y_chincheta(self, c) -> float:
        alto = R_EXT + (SUB_HUECO + SUB_H if self.submenu_visible else 0.0)
        return c.y() - alto - 16.0

    def _chincheta_en(self, p):
        if self.ancla is None:
            return None
        return chincheta_en(self.ancla.x(), self._y_chincheta(self.ancla), p)

    def _pulsar_chincheta(self, clave) -> None:
        vp = self.app.viewport
        if clave == "cerrar":
            self.anclada = False
            self.cerrar()
            vp.flash_status(_tr("Rosco LT: barra cerrada."), 2500)
            return
        self.anclada = not self.anclada
        vp.flash_status(
            _tr("Rosco LT: barra anclada aquí (la chincheta la suelta; ✕ la cierra)."
            if self.anclada else "Rosco LT: barra suelta: vuelve a seguir al ratón."), 4000)
        self._sincronizar()

    def _fijar_mascara(self, viewport) -> None:
        c = self.ancla
        path = sector(c, R_INT, R_EXT, 0.0, 180.0)
        mascara_chincheta(path, c.x(), self._y_chincheta(c))
        con_submenu = self.submenu_visible
        texto = self._texto_boton(self._clave_activa(viewport), self._faltan()) \
            if self._bajo is not None else None
        if con_submenu:
            path.addRect(_submenu(c)["marco"])
        modos = self._panel_clave(viewport)
        if modos is not None:
            path.addRect(_panel(c, modos)["marco"])
        if texto is not None:
            path.addRect(rect_etiqueta(self.win.font(), texto,
                                       self._pos_etiqueta(c, con_submenu)))
        self.win.fijar_mascara(path, clave=(con_submenu, modos, texto))

    @staticmethod
    def _pos_etiqueta(c, con_submenu) -> QPointF:
        # Encima de todo (de la chincheta y del submenú de Alinear, si está):
        # debajo va el de modos.
        alto = R_EXT + (SUB_HUECO + SUB_H if con_submenu else 0.0)
        return QPointF(c.x(), c.y() - alto - 40.0)

    def _faltan(self) -> set:
        return {k for k in EXTERNAS if self._extension(k) is None}

    def _zona_quieta(self, p) -> bool:
        """Con la barra fija: el cursor está eligiendo (dentro del semicírculo
        o del submenú), así que la barra no se mueve."""
        if self.ancla is None or p is None:
            return False
        d = p - self.ancla
        if d.y() <= ZONA_BAJO and math.hypot(d.x(), d.y()) <= ZONA_R:
            return True
        # La chincheta y el cerrar, y el hueco hasta ellos.
        if abs(d.x()) <= 30.0 and self._y_chincheta(self.ancla) - 12.0 <= p.y() <= self.ancla.y():
            return True
        vp = self.app.viewport
        if self._con_submenu(vp):
            zona = _submenu(self.ancla)["marco"].adjusted(
                -SUB_ZONA, -SUB_ZONA, SUB_ZONA, SUB_HUECO + SUB_ZONA)
            if zona.contains(p):
                return True
        modos = self._panel_clave(vp)
        if modos is not None:
            # El submenú de modos y el hueco hasta él: pasar del botón al
            # submenú nunca lo cierra.
            marco = _panel(self.ancla, modos)["marco"]
            ancho = max(PANEL_W / 2.0, R_EXT) + 10.0
            return abs(d.x()) <= ancho and 0.0 <= d.y() <= marco.bottom() - self.ancla.y() + 10.0
        return False

    def _boton_en(self, p) -> str | None:
        return boton_en(self.ancla, p, R_INT, R_EXT, ORDEN, TOLERANCIA)

    def _opcion_en(self, p):
        """``(dentro_del_submenú, opción)`` para el punto ``p``."""
        if self.ancla is None or not self._con_submenu(self.app.viewport):
            return False, None
        g = _submenu(self.ancla)
        if not g["marco"].contains(p):
            return False, None
        for nombre in ("mover", "copiar", "escalar"):
            if g[nombre].contains(p):
                return True, nombre
        return True, None

    def _pulsar_opcion(self, nombre) -> None:
        ctl, vp = self._alinear(), self.app.viewport
        if ctl is None or nombre is None:
            return
        if nombre == "escalar":
            ctl.alternar("escalar", vp)
        elif (nombre == "copiar") != bool(ctl.copiar):
            ctl.alternar("copiar", vp)
        vp.update()
        self._sincronizar()

    # -- ratón: sobre el visor (filtro) --
    def evento(self, obj, ev) -> bool:
        if not _interruptor.ENCENDIDA:
            return False
        t = ev.type()
        vp = self.app.viewport
        if t == QEvent.Type.MouseMove:
            p = QPointF(ev.position())
            self.cursor = p
            if not self._en_juego(vp):
                self._bajo = None
                if self._cursor_puesto or self.win.isVisible():
                    self._sincronizar()
                return False
            if self.fijo and not self.anclada and not self._zona_quieta(p):
                self._soltar()           # sale de la barra: vuelve a ser cursor
            if not self.fijo:
                self._reposo.start()     # si se para, la barra se fija
            self._bajo = None            # sobre el visor, no sobre un botón
            self._sincronizar()
            return False                # el visor sigue viendo el movimiento
        if t == QEvent.Type.Leave:
            self._reposo.stop()
            return False
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if ev.button() != Qt.LeftButton:
                return False
            if self.ancla is None or not self._en_juego(vp):
                self._quiza_reabrir(vp, t)
                return False
            # Normalmente la ventanita recibe el clic; esto es el respaldo
            # por si el clic llega al visor (p. ej. ventanita aún oculta).
            p = ev.position()
            clave = self._boton_en(p)
            dentro, opcion = (False, None) if clave else self._opcion_en(p)
            en_modos, modo = (False, None) if clave or dentro else self._modo_en(p)
            if clave is None and not dentro and not en_modos:
                return False
            self._apretado = True
            if t == QEvent.Type.MouseButtonPress:
                if clave is not None:
                    QTimer.singleShot(0, lambda c=clave: self.activar(c))
                elif dentro:
                    QTimer.singleShot(0, lambda o=opcion: self._pulsar_opcion(o))
                else:
                    QTimer.singleShot(0, lambda m=modo: self._pulsar_modo(m))
            return True                 # la herramienta activa no ve este clic
        if t == QEvent.Type.MouseButtonRelease and self._apretado:
            if ev.button() == Qt.LeftButton:
                self._apretado = False
                return True
        return False

    def _quiza_reabrir(self, viewport, tipo) -> None:
        """Cerrada por Seleccionar, un nuevo clic de selección la reabre (si
        tras él queda algo seleccionado), aunque sea sobre lo mismo."""
        if (self._cerrada is not None and tipo == QEvent.Type.MouseButtonPress
                and self._clave_activa(viewport) == "select"):
            self._cerrada = None
            self._soltar()

    # -- ratón: sobre la ventanita --
    def raton_movido(self, p: QPointF) -> None:
        vp = self.app.viewport
        self.cursor = QPointF(p)
        if not self._en_juego(vp):
            return
        if not self.anclada and not self._zona_quieta(self.cursor):
            self._soltar()
            self._sincronizar()
            return
        self._bajo = self._chincheta_en(self.cursor) or self._boton_en(self.cursor)
        self._sincronizar()

    def raton_clic(self, p: QPointF) -> None:
        pin = self._chincheta_en(p)
        if pin is not None:
            QTimer.singleShot(0, lambda c=pin: self._pulsar_chincheta(c))
            return
        clave = self._boton_en(p)
        if clave is not None:
            # Diferido: que la ventanita termine su propio evento.
            QTimer.singleShot(0, lambda c=clave: self.activar(c))
            return
        dentro, opcion = self._opcion_en(p)
        if dentro:
            QTimer.singleShot(0, lambda o=opcion: self._pulsar_opcion(o))
            return
        en_modos, modo = self._modo_en(p)
        if en_modos:
            QTimer.singleShot(0, lambda m=modo: self._pulsar_modo(m))

    def raton_fuera(self) -> None:
        if self._bajo is not None:
            self._bajo = None
            self._sincronizar()

    # -- dibujo --
    def dibujar(self, viewport, painter) -> None:
        """Overlay del visor: ya no pinta; programa un repaso de la
        ventanita (fuera del pintado del visor)."""
        if not _interruptor.ENCENDIDA:
            return
        if not self._pendiente:
            self._pendiente = True
            QTimer.singleShot(0, self._sincronizar)

    def _pintar_banda(self, painter, c, bajo=None, para_clic=False) -> None:
        """La barra (y el submenú de Alinear) centrada en ``c``; también la
        del cursor."""
        vp = self.app.viewport
        activa = self._boton_de(self._clave_activa(vp))
        dibujar_banda(painter, c, R_INT, R_EXT, ORDEN,
                      activa=activa if activa in ORDEN else None,
                      bajo=bajo, apagadas=self._faltan(), para_clic=para_clic)
        if self._con_submenu(vp):
            self._dibujar_submenu(painter, c)
        modos = self._panel_clave(vp) if para_clic else None
        if modos is not None:
            self._dibujar_modos(painter, c, modos)

    def _dibujar_modos(self, painter, c, clave) -> None:
        """El submenú de Desplazar o de Rotar (como los de la barra de dibujo)."""
        g = _panel(c, clave)
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 215)))
        painter.drawRoundedRect(g["marco"], 7.0, 7.0)
        for color, ancho in ((HALO, 3.4), (ROJO, 1.6)):
            painter.setPen(QPen(color, ancho))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(g["marco"], 7.0, 7.0)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(TINTA)
        painter.drawText(g["titulo"], Qt.AlignLeft | Qt.AlignVCenter,
                         _tr(NOMBRES[clave].split(":")[0]))
        f.setBold(False)
        painter.setFont(f)
        faltan = set() if self._alinear() is not None else {"alinear"}
        for modo, r in g["chips"]:
            activo = modo == self.modo[clave]
            fondo = QColor(ROJO)
            fondo.setAlpha(45)
            painter.setPen(QPen(ROJO if activo else QColor(180, 178, 169), 1.0))
            painter.setBrush(QBrush(fondo if activo else QColor(255, 255, 255, 230)))
            painter.drawRoundedRect(r, 4.0, 4.0)
            painter.setPen(QColor(150, 150, 146) if modo in faltan
                           else ROJO.darker(140) if activo else QColor(68, 68, 65))
            painter.drawText(r, Qt.AlignCenter, _tr(modo))

    def pintar(self, painter) -> None:
        """La barra fija, en coordenadas del visor (la ventanita traslada)."""
        c = self.ancla
        if c is None:
            return
        vp = self.app.viewport
        activa = self._clave_activa(vp)
        faltan = self._faltan()
        self._pintar_banda(painter, c, self._bajo, para_clic=True)
        con_submenu = self._con_submenu(vp)
        dibujar_chincheta(painter, c.x(), self._y_chincheta(c), self.anclada, self._bajo)
        if self._bajo is not None:
            etiqueta(painter, self._texto_boton(activa, faltan),
                     self._pos_etiqueta(c, con_submenu))

    def _texto_boton(self, activa, faltan) -> str:
        if self._bajo in ("chincheta", "cerrar"):
            return texto_chincheta(self._bajo, self.anclada)
        if self._bajo == self._boton_de(activa):
            return "Seleccionar (cerrar)"
        if self._bajo in faltan:
            return _tr("{0} (extensión no instalada)", _tr(NOMBRES[self._bajo].split(':')[0]))
        return f"{_tr(NOMBRES[self._bajo])}{_atajo(self._herramientas(), self._bajo)}"

    def _dibujar_submenu(self, painter, c) -> None:
        ctl = self._alinear()
        g = _submenu(c)
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 150)))
        painter.drawRoundedRect(g["marco"], 8.0, 8.0)
        for color, ancho in ((HALO, 3.4), (ROJO, 1.6)):
            painter.setPen(QPen(color, ancho))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(g["marco"], 8.0, 8.0)

        titulo = _tr("Alinear · ") + ctl.texto_paso()
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(TINTA)
        painter.drawText(g["titulo"], Qt.AlignCenter, _tr(titulo))
        f.setBold(False)
        painter.setFont(f)

        def boton(r, texto, activo) -> None:
            painter.setPen(QPen(ROJO if activo else QColor(180, 178, 169), 1.0))
            painter.setBrush(QBrush(QColor(250, 222, 222, 235) if activo
                                    else QColor(255, 255, 255, 220)))
            painter.drawRoundedRect(r, 5.0, 5.0)
            painter.setPen(QColor(130, 20, 20) if activo else QColor(68, 68, 65))
            painter.drawText(r, Qt.AlignCenter, _tr(texto))

        boton(g["mover"], "Mover", not ctl.copiar)
        boton(g["copiar"], "Copiar", ctl.copiar)
        boton(g["escalar"], ("☑" if ctl.escalar else "☐") + _tr(" Escalar al 2º"),
              ctl.escalar)


def _submenu(c) -> dict:
    """Rectángulos del submenú de Alinear, centrado encima del semicírculo."""
    x0 = c.x() - SUB_W / 2.0
    y0 = c.y() - R_EXT - SUB_HUECO - SUB_H
    fila = y0 + 28.0
    return {"marco": QRectF(x0, y0, SUB_W, SUB_H),
            "titulo": QRectF(x0 + 8.0, y0 + 5.0, SUB_W - 16.0, 18.0),
            "mover": QRectF(x0 + 8.0, fila, 66.0, 21.0),
            "copiar": QRectF(x0 + 78.0, fila, 66.0, 21.0),
            "escalar": QRectF(x0 + 152.0, fila, SUB_W - 160.0, 21.0)}


def _panel(c, clave) -> dict:
    """Rectángulos del submenú de modos de ``clave``, debajo del semicírculo."""
    x0 = c.x() - PANEL_W / 2.0
    y0 = c.y() + PANEL_HUECO
    modos = MODOS[clave]
    n = len(modos)
    ancho = (PANEL_W - 12.0 - 4.0 * (n - 1)) / n
    return {"marco": QRectF(x0, y0, PANEL_W, PANEL_H),
            "titulo": QRectF(x0 + 10.0, y0 + 4.0, PANEL_W - 20.0, 18.0),
            "chips": [(m, QRectF(x0 + 6.0 + i * (ancho + 4.0), y0 + 27.0, ancho, 22.0))
                      for i, m in enumerate(modos)]}


def _atajo(tools, clave) -> str:
    tecla = getattr(tools.get(clave), "shortcut", None)
    return f"  ({tecla})" if tecla else ""

# SPDX-License-Identifier: GPL-3.0-or-later
"""Controlador de Multiempuje: une opciones, herramienta, panel, barra (un botón) y menú."""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar

from . import _algo as A
from . import _settings as S
from ._i18n import _t, descripcion
from ._icons import mode_icon

log = logging.getLogger("ingetrazo.plugins.multiempuje")

NOMBRES = {"juntas": "Juntas", "direccion": "Una dirección", "cada_cara": "Cada cara"}
DIRECCIONES = {"normal": "normal de la cara", "media": "media del conjunto", "x": "eje X", "y": "eje Y", "z": "eje Z",
               "custom": "personalizada"}
TOOLBAR = "multiempuje_toolbar"


def _fmt_vec(v):
    try:
        return "(" + " · ".join(f"{float(k):.2f}".replace(".", ",") for k in v) + ")"
    except Exception:  # noqa: BLE001
        return ""


class Controlador:
    def __init__(self, app):
        from ._panel import Panel
        from ._tool import MultiTool
        self.app = app
        self.opc = S.Opciones()
        self.plano = None
        self.custom_origen = ""
        self.tool = MultiTool(self)
        self.panel = Panel(self)
        self.dock = None
        self.accion = None
        self.barra = None
        self._activo = False

    # ---- montaje
    def montar(self):
        app = self.app
        clave = app.key
        app.key = "multiempuje"                # la ventana recuerda el panel por este nombre
        try:
            self.dock = app.add_panel(_t("Multiempuje"), self.panel, name="multiempuje", start_hidden=True)
        except TypeError:
            self.dock = app.add_panel(_t("Multiempuje"), self.panel)
        except Exception:  # noqa: BLE001
            log.exception("panel no creado")
        finally:
            app.key = clave
        self._barra()
        try:
            menu = app.add_menu(_t("Multiempuje"))
            act = menu.addAction(mode_icon("principal", 32), _t("Multiempuje"))
            act.setToolTip(_t("Activa la herramienta y abre la pestaña"))
            act.triggered.connect(lambda _c=False: self.activar())
            menu.addSeparator()
            menu.addAction(_t("Mostrar el panel"), self.mostrar_panel)
        except Exception:  # noqa: BLE001
            log.exception("menú no creado")

    def _barra(self):
        w = self.app.window
        tb = w.findChild(QToolBar, TOOLBAR)
        if tb is None:
            maker = getattr(w, "_new_toolbar", None)
            try:
                tb = maker(_t("Multiempuje"), TOOLBAR) if callable(maker) else None
            except Exception:  # noqa: BLE001
                tb = None
            if tb is None:
                tb = QToolBar(_t("Multiempuje"), w)
                tb.setObjectName(TOOLBAR)
                try:
                    from views.icons import toolbar_icon_px
                    px = toolbar_icon_px()
                except Exception:  # noqa: BLE001
                    px = 24
                tb.setIconSize(QSize(px, px))
                w.addToolBar(Qt.TopToolBarArea, tb)
        act = QAction(mode_icon("principal", 64), _t("Multiempuje"), tb)
        act.setCheckable(True)
        act.setStatusTip(_t("Empujar/tirar varias caras a la vez (Juntas, Una dirección o Cada cara)."))
        act.triggered.connect(lambda _c=False: self.activar())
        tb.addAction(act)
        self.accion = act
        self.barra = tb
        self._ayuda_boton()
        # La primera vez que se instala, la barra se enseña; luego manda lo que decida el usuario.
        try:
            from PySide6.QtCore import QSettings
            qs = QSettings("IngeTrazo", "multiempuje")
            if not qs.value("barra_mostrada", False, type=bool):
                qs.setValue("barra_mostrada", True)
                QTimer.singleShot(1500, tb.show)
        except Exception:  # noqa: BLE001
            pass

    def _ayuda_boton(self):
        if self.accion is not None:
            self.accion.setToolTip(f"{_t('Multiempuje')} · {self.nombre_modo()}: {descripcion(self.opc.movimiento)}")

    # ---- activación
    def activar(self, movimiento=None):
        if movimiento and movimiento in S.MOVIMIENTOS:
            self.set_movimiento(movimiento)
        vp = self.app.viewport
        try:
            w = vp.window()
            for act in getattr(w, "_tool_actions", {}).values():
                try:
                    act.setChecked(False)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        self.mostrar_panel()
        if vp.active_tool is self.tool:
            self.tool._rearrancar()            # noqa: SLF001
            self.tool._hint()                  # noqa: SLF001
        else:
            self.tool.on_activate(vp)
        try:
            vp.setFocus()
        except Exception:  # noqa: BLE001
            pass

    def mostrar_panel(self):
        if self.dock is None:
            return
        try:
            self.app.show_panel(self.dock)
        except Exception:  # noqa: BLE001
            try:
                self.dock.show()
                self.dock.raise_()
            except Exception:  # noqa: BLE001
                pass

    def on_tool(self, activo):
        self._activo = activo
        if self.accion is not None:
            self.accion.setChecked(bool(activo))

    # ---- opciones
    def nombre_modo(self):
        return _t(NOMBRES.get(self.opc.movimiento, ""))

    def nombre_vector(self):
        d = self.opc.get("direccion")
        txt = _t(DIRECCIONES.get(d, ""))
        if d == "custom":
            txt += " " + _fmt_vec(self.opc.get("vector_custom") or ())
        elif d in ("x", "y", "z") and self.opc.get("vector_local"):
            txt += " " + _t("(ejes del grupo)")
        return txt

    def set_movimiento(self, m):
        if m not in S.MOVIMIENTOS or m == self.opc.movimiento:
            return
        self.opc.set("movimiento", m)
        self.panel.refrescar()
        self._ayuda_boton()
        self.tool._hint()                      # noqa: SLF001
        self.tool._cursor()                    # noqa: SLF001
        try:
            self.app.viewport.flash_status(f"{_t('Movimiento')}: {self.nombre_modo()} — {descripcion(m)}", 3000)
        except Exception:  # noqa: BLE001
            pass
        if self._activo:
            QTimer.singleShot(0, self.tool._rearrancar)   # noqa: SLF001

    def cambio(self, k, v, modo=None, rehacer=True):
        self.opc.set(k, v)
        self.panel.refrescar()
        self._ayuda_boton()
        self.tool._hint()                      # noqa: SLF001
        self.tool._cursor()                    # noqa: SLF001
        if rehacer and self._activo:
            QTimer.singleShot(0, self.tool._rearrancar)   # noqa: SLF001

    def recordar_distancia(self, v):
        self.opc.set("distancia", float(v))
        self.panel.refrescar()

    def distancia_tecleada(self, v):
        """Distancia escrita en el panel: rehace el último empuje o, si no hay, se guarda para Enter."""
        if self._activo and self.tool._ultimo_es_mio():   # noqa: SLF001
            sign = -1.0 if self.tool.last["offset"] < 0 and v > 0 else 1.0
            self.tool.reaplicar(sign * v)

    def ciclar_seleccion(self):
        modos = S.SEL_MODES
        actual = self.opc.get("sel_mode")
        i = (modos.index(actual) + 1) % len(modos) if actual in modos else 0
        self.opc.set("sel_mode", modos[i])
        self.panel.refrescar()
        from ._tool import NOMBRES_SEL
        try:
            self.app.viewport.flash_status(f"Modo de selección: {NOMBRES_SEL[modos[i]]}", 2500)
        except Exception:  # noqa: BLE001
            pass

    def set_direccion(self, d):
        if d not in S.DIRECCIONES or d == self.opc.get("direccion"):
            self.panel.refrescar()
            return
        if d == "custom" and not self.opc.get("vector_custom"):
            self.app.viewport.flash_status("No hay dirección personalizada: elígela en el dibujo o tecléala (x ; y ; z).", 4000)
            self.panel.refrescar()
            return
        self.opc.set("direccion", d)
        self.panel.refrescar()
        self.tool._hint()                      # noqa: SLF001
        if self._activo:
            QTimer.singleShot(0, self.tool._rearrancar)   # noqa: SLF001

    def set_vector_custom(self, vec, origen=""):
        """Dirección personalizada (tomada del dibujo o tecleada), en coordenadas del modelo."""
        v = A.norm(tuple(float(k) for k in vec)) if vec else None
        if v is None:
            self.app.viewport.flash_status("Esa dirección no vale (vector nulo).", 3000)
            self.panel.refrescar()
            return False
        self.opc.set("vector_custom", [round(k, 6) for k in v])
        self.custom_origen = origen or ""
        self.opc.set("direccion", "custom")
        self.panel.refrescar()
        self.tool._hint()                      # noqa: SLF001
        if self._activo:
            QTimer.singleShot(0, self.tool._rearrancar)   # noqa: SLF001
        return True

    def pedir_direccion(self):
        if self.opc.movimiento != "direccion":
            self.set_movimiento("direccion")
        if not self._activo:
            self.activar()
        self.tool.pedir_direccion()

    def toggle_local(self):
        v = not bool(self.opc.get("vector_local"))
        self.opc.set("vector_local", v)
        self.panel.refrescar()
        self.tool._hint()                      # noqa: SLF001
        try:
            self.app.viewport.flash_status("Ejes X, Y, Z: " + ("del grupo abierto (locales)" if v else "del modelo"), 2500)
        except Exception:  # noqa: BLE001
            pass

    def set_plano(self, plano):
        self.plano = plano
        self.panel.refrescar()
        self.tool._hint()                      # noqa: SLF001
        if self._activo:
            QTimer.singleShot(0, self.tool.reaplicar)

    def pedir_plano(self):
        if not self._activo:
            self.activar()
        self.tool.pedir_plano()

    def aplicar_panel(self):
        if not self._activo:
            self.activar()
        self.panel._distancia()                # noqa: SLF001
        d = float(self.opc.get("distancia") or 0.0)
        self.tool.aplicar_seleccion(d)

    def deshacer_ultimo(self):
        if not self.tool.deshacer_ultimo():
            try:
                self.app.viewport.flash_status("No hay un empuje de Multiempuje que deshacer.", 3000)
            except Exception:  # noqa: BLE001
                pass

    def on_aplicado(self, off):
        pass

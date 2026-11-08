# SPDX-License-Identifier: GPL-3.0-or-later
"""El controlador de las Tareas de Rosco LT: el botón de Tareas
en la barra «Rosco LT», las dos entradas en Extensiones ▸
Rosco LT y una sola ventana reutilizada.

El interruptor de Rosco LT no las toca: con ella apagada, las Tareas
siguen a mano (por eso el botón no va en ``_rosco_lt_refs`` ni las entradas
en ``_rosco_lt_menu``)."""
from __future__ import annotations

from .._idioma import _tr
import copy
import logging

from PySide6.QtGui import QAction

from . import _datos, _iconos

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

# La clave de las tareas del modelo en el .igz.
CLAVE_DATOS = "rosco_lt_tareas"

TEXTOS = {
    "notas_modelo": ("modelo", "Tareas del modelo actual", "Lista de tareas del modelo actual"),
    "notas_global": ("global", "Tareas de IngeTrazo",
                     "Lista de tareas de IngeTrazo (todos los modelos)"),
}


class ListasTareas:

    def __init__(self, app) -> None:
        self.diana = app                         # menús y barra de Rosco LT
        # Los datos del modelo van por su propia clave: una copia de la
        # app con esa clave.
        self.app = copy.copy(app)
        self.app.key = CLAVE_DATOS
        self.almacen = _datos.Almacen()
        self._ventana = None
        self._acciones = {}
        self._boton = None

    # ---- Instalación -------------------------------------------------------------------
    def instalar(self) -> None:
        self._menu()
        try:
            self._barra()
        except Exception:  # noqa: BLE001 — el menú sigue funcionando
            log.exception("Tareas: no se pudo poner el botón en la barra")
        self.diana.on_document_changed(self._documento_cambiado)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._actualizar_tips)

    def _menu(self) -> None:
        from .._interruptor import entrada
        for orden, (lista, texto, tip) in TEXTOS.items():
            self._acciones[lista] = entrada(
                self.diana, orden, texto, lambda k=lista: self.ventana().mostrar(k), tip)

    def _barra(self) -> None:
        """Un solo botón, la libreta de color; abre la ventana en la última
        pestaña usada. Va entre Reiniciar y el interruptor."""
        from .._barra import barra
        win = self.diana.window
        self._boton = QAction(_iconos.libreta(), _tr("Tareas"), win)
        self._boton.setStatusTip(_tr("Listas de tareas del modelo y de IngeTrazo"))
        self._boton.triggered.connect(lambda _c=False: self.ventana().mostrar())
        barra(self.diana).addAction(_tr(self._boton))

    # ---- La ventana (una sola, reutilizada) --------------------------------------------
    def ventana(self):
        if self._ventana is None:
            from ._tareas import VentanaTareas
            self._ventana = VentanaTareas(self.app, self.almacen)
            self._ventana.guardada.connect(self._actualizar_tips)
        return self._ventana

    # ---- Seguimiento del documento -----------------------------------------------------
    def _documento_cambiado(self) -> None:
        try:
            self._actualizar_tips()
            if self._ventana is not None:
                self._ventana.documento_cambiado()
        except Exception:  # noqa: BLE001 — nunca romper la edición del usuario
            log.exception("Tareas: error al seguir el documento")

    def _actualizar_tips(self) -> None:
        """Las tareas abiertas/hechas de las dos listas, en el tooltip del botón."""
        lineas = [_tr("Tareas")]
        for clave, lista in (("modelo", _datos.tareas_modelo(self.app)),
                             ("global", self.almacen.tareas)):
            abiertas, hechas = _datos.resumen(lista)
            nombre = "Modelo" if clave == "modelo" else "IngeTrazo"
            lineas.append(_tr("{0}: {1} abiertas · {2} hechas", _tr(nombre), abiertas, hechas))
        if self._boton is not None:
            self._boton.setToolTip("\n".join(lineas))

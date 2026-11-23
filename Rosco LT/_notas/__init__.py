# SPDX-License-Identifier: GPL-3.0-or-later
"""Las listas de tareas de Rosco.

Tareas del modelo (``_tareas.py``)
    Guardadas dentro del .igz; «Guardar cambios» es un paso de deshacer.
Tareas de IngeTrazo (``_tareas.py``)
    Una lista común a todos los modelos.

Cada lista tiene abiertas y hechas (plegables), borrar con recuperación hasta
guardar, subir/bajar, arrastrar, Intro = tarea nueva debajo, dictado,
imprimir y exportar a texto o CSV.

Datos globales: ``%APPDATA%\\IngeTrazo\\<clave>\\tareas.json``; las del
modelo, en el .igz con la clave «<clave>_tareas» (``_datos``). Se abre con el
botón de Tareas de la barra «Rosco», el botón de notas del anillo o
Extensiones ▸ Rosco. La pieza se encuentra en ``window._<clave>_tareas``.
"""
from __future__ import annotations

from .._ajustes import atributo


def instalar(app):
    previo = getattr(app.window, atributo("tareas"), None)
    if previo is not None:                       # ya instalada
        return previo
    from ._control import ListasTareas
    listas = ListasTareas(app)
    listas.instalar()
    setattr(app.window, atributo("tareas"), listas)
    return listas

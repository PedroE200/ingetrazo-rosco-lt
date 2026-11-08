# SPDX-License-Identifier: GPL-3.0-or-later
"""Las listas de tareas de Rosco LT.

Tareas del modelo (``_tareas.py``)
    Guardadas dentro del .igz; «Guardar cambios» es un paso de deshacer.
Tareas de IngeTrazo (``_tareas.py``)
    Una lista común a todos los modelos.

Cada lista tiene abiertas y hechas (plegables), borrar con recuperación hasta
guardar, subir/bajar, arrastrar, Intro = tarea nueva debajo, dictado,
imprimir y exportar a texto o CSV.

Datos globales: ``%APPDATA%\\IngeTrazo\\rosco_lt\\tareas.json``; las del
modelo, en el .igz con la clave «rosco_lt_tareas». Se abre con el botón de Tareas
de la barra «Rosco LT», el botón de notas del anillo o Extensiones ▸
Rosco LT. La pieza se encuentra en ``window._rosco_lt_tareas``.
"""
from __future__ import annotations


def instalar(app):
    previo = getattr(app.window, "_rosco_lt_tareas", None)
    if previo is not None:                       # ya instalada
        return previo
    from ._control import ListasTareas
    listas = ListasTareas(app)
    listas.instalar()
    app.window._rosco_lt_tareas = listas
    return listas

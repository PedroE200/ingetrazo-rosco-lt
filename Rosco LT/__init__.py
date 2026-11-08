# SPDX-License-Identifier: GPL-3.0-or-later
"""Rosco LT — barras semicirculares junto al cursor para dibujar y
transformar en IngeTrazo (API 2). Reúne en una sola extensión:

La barra (``_cadena.py``)
    Un anillo partido alrededor del cursor, con contorno rojo; mientras te
    mueves es el propio cursor y al parar el ratón se queda fijo para hacer
    clic. Arriba, dibujar: una base (rectángulo, polígono, arco, círculo,
    línea) y Empujar/Tirar encadenados, y las herramientas. Abajo,
    modificar (``_seleccion.py``): Desplazar, Escalar, Simetría y Rotar
    (``_arco.py``) y suprimir, agrupar, cortar, copiar e invertir cara; un clic
    añade a la selección o lo quita. Cada botón tiene su submenú debajo.
    Encima, la diana de vistas (``_diana.py``): zoom extensión, a la
    selección, previo, encuadre, ocultar el resto, vistas estándar,
    frontal/posterior, deshacer y rehacer, cónica y paralela, el buscador de
    órdenes, la chincheta y Pantalla limpia por partes (``_limpia.py``). El
    ✕ de cerrar, junto al cursor. En cada punto, la ventanita de medidas con
    calculadora (``_medidas.py``); la calculadora suelta, bajo Apagar
    (``_calculadora.py``), y el Control de tiempo (``_tiempo.py``). Temas (``_temas.py``): A · Relieve 3D,
    B · Transparente con glifos y C a N, el B en color con glifos de líneas
    y sombreado, en Opciones ▸ Tema de la barra.
    Se lanza desde la barra «Rosco LT» (el arquitecto) o Extensiones ▸
    Rosco LT ▸ Abrir la barra.

Modificar (``_arco.py``)
    Desplazar (mover · copia · alinear · empujar/tirar · vértices,
    ``_vertices.py``: mover cualquier vértice, también dentro de grupos
    cerrados), Escalar (libre · por referencia,
    ``_referencia.py``), Simetría y Rotar (sin copia · con copia), sobre la
    selección y con las herramientas nativas. Sus botones van en la mitad de
    abajo del anillo; su barra suelta sale con Alinear.

Alinear (``_alinear.py``)
    Dos pares de puntos origen → destino; mover o copiar y, si se quiere,
    escalar. Desde Desplazar ▸ alinear o
    Extensiones ▸ Rosco LT ▸ Alinear.

Reiniciar (``_reiniciar.py``)
    Cierra y vuelve a abrir IngeTrazo (pregunta antes si guardar): barra
    «Rosco LT», Extensiones ▸ Rosco LT ▸ Reiniciar IngeTrazo o Ctrl+Alt+R.

Tareas (``_notas``)
    Dos listas de tareas, la del modelo (dentro del .igz) y la de IngeTrazo,
    en una ventana con pestañas: botón de la libreta en la barra
    «Rosco LT», botón de notas del anillo o Extensiones ▸ Rosco LT
    ▸ Tareas del modelo actual / Tareas de IngeTrazo. El interruptor no las
    apaga.

Interruptor (``_interruptor.py``)
    Apaga y enciende Rosco LT entero al momento, sin reiniciar: el botón de
    encendido del principio de la barra «Rosco LT» o la casilla Extensiones ▸
    Rosco LT ▸ Rosco LT activado; también apaga Opciones ▸ Desactivar
    Rosco LT. Se recuerda al cerrar. También pone el submenú Extensiones ▸
    Rosco LT, con todas las órdenes de Rosco LT.

Las piezas se encuentran entre sí por ``window._rosco_lt_barra_dibujo``, ``window._rosco_lt_barra_modificar``,
``window._rosco_lt_alinear``, ``window._rosco_lt_tareas`` y ``window._rosco_lt_interruptor``. Las Tool viven fuera
de este archivo a propósito: IngeTrazo crearía una entrada de menú por cada
Tool definida aquí.
"""
from __future__ import annotations

import logging

__version__ = "1.0.0"
__plugin_name__ = "Rosco LT"

log = logging.getLogger("ingetrazo.plugins.rosco_lt")


def _alinear(app):
    from ._alinear import Alinear
    ctl = getattr(app.window, "_rosco_lt_alinear", None)
    if ctl is None:
        ctl = Alinear(app)
        ctl.instalar()
        app.window._rosco_lt_alinear = ctl
    return ctl


def _barra_modificar(app):
    from ._arco import BarraModificar
    barras = getattr(app.window, "_rosco_lt_barra_modificar", None)
    if barras is None:
        barras = app.window._rosco_lt_barra_modificar = {}
    if app.key not in barras:
        barra = BarraModificar(app)
        barra.instalar()
        barras[app.key] = barra
    return barras[app.key]


def _barra_dibujo(app):
    from ._cadena import Cadena
    cadenas = getattr(app.window, "_rosco_lt_barra_dibujo", None)
    if cadenas is None:
        cadenas = app.window._rosco_lt_barra_dibujo = {}
    if app.key not in cadenas:
        cadena = Cadena(app)
        cadena.instalar()
        cadenas[app.key] = cadena
    return cadenas[app.key]


def _reiniciar(app):
    from ._reiniciar import instalar
    if not getattr(app.window, "_rosco_lt_reiniciar", False):
        instalar(app)
        app.window._rosco_lt_reiniciar = True


def _notas(app):
    """Las tareas, antes de la raya y el interruptor de la barra."""
    from ._notas import instalar
    return instalar(app)


def _poner_interruptor(app):
    """Después de las demás piezas: si se cerró apagada, arranca apagada."""
    from ._interruptor import Interruptor, guardada
    ctl = getattr(app.window, "_rosco_lt_interruptor", None)
    if ctl is None:
        ctl = Interruptor(app)
        ctl.instalar()
        app.window._rosco_lt_interruptor = ctl
        # Solo una variante encendida: la que ya esté en marcha tiene preferencia.
        if not guardada() or any(o.encendida() for o in ctl._otros()):
            ctl.apagar(arranque=True)
    return ctl


def setup(app):
    if getattr(app, "api_version", 0) < 2:
        from ._idioma import _tr
        raise RuntimeError(_tr("Rosco LT requiere la API de extensiones 2"))
    # IngeTrazo saca la clave del nombre de la carpeta; se fija para que lo
    # que va por ella no dependa de cómo se llame la carpeta.
    from ._ajustes import CLAVE
    app.key = CLAVE
    # Una pieza que falle no impide cargar las demás; el error va al registro.
    piezas = {}
    for nombre, instalar in (("alinear", _alinear), ("barra_modificar", _barra_modificar),
                             ("barra_dibujo", _barra_dibujo), ("reiniciar", _reiniciar),
                             ("notas", _notas)):
        try:
            piezas[nombre] = instalar(app)
        except Exception:  # noqa: BLE001
            log.exception("Rosco LT: no se pudo cargar %s", nombre)
    try:
        piezas["interruptor"] = _poner_interruptor(app)
    except Exception:  # noqa: BLE001
        log.exception("Rosco LT: no se pudo cargar el interruptor")
    log.info("Rosco LT %s cargado: %s", __version__, ", ".join(piezas))
    return piezas

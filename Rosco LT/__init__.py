# SPDX-License-Identifier: GPL-3.0-or-later
"""Rosco — barras semicirculares junto al cursor para dibujar y
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
    Se lanza desde la barra «Rosco» (el arquitecto) o Extensiones ▸
    Rosco ▸ Abrir la barra.
    Bajo el anillo, el cajetín de capa (``_capas.py``): siempre la capa
    activa de IngeTrazo, con Aplicar capa, hacer activa, aislar y bloquear;
    su ▾ abre el mini panel de capas (``_capas_panel.py``). Mantener
    pulsado deshacer o rehacer saca sus 10 últimos pasos (``_pasos.py``).

Modificar (``_arco.py``)
    Desplazar (mover · copia · alinear · estirar · vértices; estirar lleva
    sub-submenú, ``_subsub.py``: estirar por ventana · prolongar a plano,
    ``_estirar.py``;
    ``_vertices.py``: mover cualquier vértice, también dentro de grupos
    cerrados), Escalar (libre · por referencia,
    ``_referencia.py``), Simetría y Rotar (sin copia · con copia), sobre la
    selección y con las herramientas nativas. Sus botones van en la mitad de
    abajo del anillo; su barra suelta sale con Alinear.

Alinear (``_alinear.py``)
    Dos pares de puntos origen → destino; mover o copiar y, si se quiere,
    escalar. Desde Desplazar ▸ alinear o
    Extensiones ▸ Rosco ▸ Alinear.

Reiniciar (``_reiniciar.py``)
    Cierra y vuelve a abrir IngeTrazo (pregunta antes si guardar): barra
    «Rosco», Extensiones ▸ Rosco ▸ Reiniciar IngeTrazo o Ctrl+Alt+R.

Tareas (``_notas``)
    Dos listas de tareas, la del modelo (dentro del .igz) y la de IngeTrazo,
    en una ventana con pestañas: botón de la libreta en la barra
    «Rosco», botón de notas del anillo o Extensiones ▸ Rosco
    ▸ Tareas del modelo actual / Tareas de IngeTrazo. El interruptor no las
    apaga.

Multiempuje (``_multiempuje``)
    Empujar/tirar varias caras a la vez, con su barra, su entrada en
    Extensiones y su pestaña lateral, que también abre el botón Empujar del
    anillo. El interruptor no la apaga.

Interruptor (``_interruptor.py``)
    Apaga y enciende Rosco entero al momento, sin reiniciar: el botón de
    encendido del principio de la barra «Rosco» o la casilla Extensiones ▸
    Rosco ▸ Rosco activado; también lo apaga el botón Apagar del
    anillo; dos toques en Bloq Mayús lo encienden o lo apagan. Se recuerda al cerrar. También pone el submenú Extensiones ▸
    Rosco, con todas las órdenes de Rosco.

Las piezas se encuentran entre sí por atributos de la ventana con el nombre
``_ajustes.atributo(...)`` (``_<clave>_anillos``, ``_<clave>_arcos``,
``_<clave>_alinear``, ``_<clave>_tareas`` y ``_<clave>_interruptor``), así
que dos ediciones cargadas a la vez no se pisan. Las Tool viven fuera
de este archivo a propósito: IngeTrazo crearía una entrada de menú por cada
Tool definida aquí.
"""
from __future__ import annotations

import logging

__version__ = "4.0.0"
__plugin_name__ = "Rosco LT"

from ._ajustes import atributo, registro

log = registro()
def _alinear(app):
    from ._alinear import Alinear
    ctl = getattr(app.window, atributo("alinear"), None)
    if ctl is None:
        ctl = Alinear(app)
        ctl.instalar()
        setattr(app.window, atributo("alinear"), ctl)
    return ctl


def _arco_modificar(app):
    from ._arco import ArcoModificar
    barras = getattr(app.window, atributo("arcos"), None)
    if barras is None:
        barras = {}
        setattr(app.window, atributo("arcos"), barras)
    if app.key not in barras:
        barra = ArcoModificar(app)
        barra.instalar()
        barras[app.key] = barra
    return barras[app.key]


def _anillo(app):
    from ._cadena import Cadena
    cadenas = getattr(app.window, atributo("anillos"), None)
    if cadenas is None:
        cadenas = {}
        setattr(app.window, atributo("anillos"), cadenas)
    if app.key not in cadenas:
        cadena = Cadena(app)
        cadena.instalar()
        cadenas[app.key] = cadena
    return cadenas[app.key]


def _reiniciar(app):
    from ._reiniciar import instalar
    if not getattr(app.window, atributo("reiniciar"), False):
        instalar(app)
        setattr(app.window, atributo("reiniciar"), True)


def _notas(app):
    """Las Tareas, antes de la raya y el interruptor de la barra."""
    from ._notas import instalar
    return instalar(app)


def _multiempuje(app):
    from . import _edicion
    if not _edicion.con("multiempuje"):
        return None
    from ._multiempuje import instalar
    return instalar(app)


def _poner_interruptor(app):
    """Después de las demás piezas: si se cerró apagada, arranca apagada."""
    from ._interruptor import Interruptor, guardada
    ctl = getattr(app.window, atributo("interruptor"), None)
    if ctl is None:
        ctl = Interruptor(app)
        ctl.instalar()
        setattr(app.window, atributo("interruptor"), ctl)
        # Solo una variante encendida: la que ya esté en marcha tiene preferencia.
        if not guardada() or any(o.encendida() for o in ctl._otros()):
            ctl.apagar(arranque=True)
    return ctl


def setup(app):
    if getattr(app, "api_version", 0) < 2:
        from ._idioma import _tr
        raise RuntimeError(_tr("Rosco requiere la API de extensiones 2"))
    # IngeTrazo saca la clave del nombre de la carpeta; se fija para que lo
    # que va por ella no dependa de cómo se llame la carpeta.
    from ._ajustes import CLAVE
    app.key = CLAVE
    # Una pieza que falle no impide cargar las demás; el error va al registro.
    from . import _edicion
    piezas = {}
    for nombre, instalar in (("alinear", _alinear), ("arco_modificar", _arco_modificar),
                             ("anillo", _anillo), ("reiniciar", _reiniciar),
                             ("notas", _notas), ("multiempuje", _multiempuje)):
        if not _edicion.con(nombre) and nombre in _edicion.PARTES:
            continue                         # una parte que esta edición no lleva
        try:
            piezas[nombre] = instalar(app)
        except Exception:  # noqa: BLE001
            log.exception("%s: no se pudo cargar %s", __plugin_name__, nombre)
    try:
        piezas["interruptor"] = _poner_interruptor(app)
    except Exception:  # noqa: BLE001
        log.exception("%s: no se pudo cargar el interruptor", __plugin_name__)
    log.info("%s %s cargado: %s", __plugin_name__, __version__, ", ".join(piezas))
    return piezas

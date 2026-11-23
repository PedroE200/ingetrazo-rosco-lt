# SPDX-License-Identifier: GPL-3.0-or-later
"""Multiempuje, pieza de Rosco: empujar/tirar varias caras a la vez. Tres movimientos (Juntas,
Una dirección, Cada cara) con acabado empujar/engrosar, borde exterior en inglete / siguiendo las
vecinas / promediado, redondeo de aristas, dirección libre (eje, media, arista, cara, guía o
tecleada), bordes nuevos, resultado en grupo, rematado, desmoldeo, aleatorio, plano destino y
recorte de huecos. Elige caras sueltas y de varios grupos y componentes cerrados a la vez
(sin abrirlos) y lleva un cursor propio.

Un botón «Multiempuje» en su barra, una entrada en Extensiones y la pestaña lateral con todo.
El interruptor de Rosco no la apaga."""
from __future__ import annotations


def instalar(app):
    w = app.window
    ctrl = getattr(w, "_multiempuje", None)
    if ctrl is None:
        from ._extension import Controlador
        ctrl = Controlador(app)
        ctrl.montar()
        w._multiempuje = ctrl
    return ctrl

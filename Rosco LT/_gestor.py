# SPDX-License-Identifier: GPL-3.0-or-later
"""El gestor de barras de IngeTrazo (otra extensión), si está instalado: se
reconoce por las órdenes que ofrece, y de él sale el tipo de sus arrastres."""
from __future__ import annotations

import sys

_TIPO_SERIE = "application/x-rosco-hueco"
_tipo = _TIPO_SERIE


def gestor_barras(win):
    """El gestor publicado en la ventana, o None."""
    for valor in list(vars(win).values()):
        try:
            if callable(getattr(valor, "abrir_master", None)) and callable(getattr(valor, "ejecutar", None)):
                return valor
        except Exception:  # noqa: BLE001 — un atributo raro no rompe la búsqueda
            continue
    return None


def fijar_tipo(gestor) -> None:
    """Toma del gestor el tipo de sus arrastres (al crear su apartado)."""
    global _tipo
    paquete = type(gestor).__module__.rsplit(".", 1)[0]
    _tipo = str(getattr(sys.modules.get(paquete + "._boton"), "MIME", _TIPO_SERIE))


def tipo_arrastre() -> str:
    return _tipo

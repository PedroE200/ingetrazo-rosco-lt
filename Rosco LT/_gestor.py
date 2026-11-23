# SPDX-License-Identifier: GPL-3.0-or-later
"""Las otras extensiones con las que se entiende Rosco, si están instaladas:
el gestor de barras (se reconoce por las órdenes que ofrece, y de él sale el
tipo de sus arrastres), la biblioteca de texturas y las órdenes por voz.

Los nombres técnicos que esas extensiones esperan (atributos de la ventana,
prefijos guardados) van aquí, en constantes, y en ningún otro sitio: no se
pueden cambiar sin romper la integración o los datos ya guardados."""
from __future__ import annotations

import sys

# La lista de la ventana donde el gestor de barras busca a quién ofrecer su
# árbol de comandos (la lee él: su nombre no se puede cambiar).
DESTINOS_GESTOR = "_maestro_destinos"  # nombre técnico
# El prefijo con que se guardan en los huecos los comandos del gestor de barras
# (ya está en los ajustes de los usuarios).
PREFIJO_EXTERNO = "mh:"  # nombre técnico
# El atributo de la ventana donde la biblioteca de texturas publica su controlador.
ATRIB_TEXTURAS = "_texturelab"  # nombre técnico
# La clave con que se guardaba antes en los huecos el ojo de la biblioteca de
# texturas (ahora «texturas»; se cambia al leer los ajustes).
CLAVE_TEXTURAS_ANTES = "texturelab"  # nombre técnico


def texturas(win):
    """El controlador de la biblioteca de texturas, o None."""
    return getattr(win, ATRIB_TEXTURAS, None)

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


def ordenes_voz(win):
    """La extensión de órdenes por voz publicada en la ventana, o None."""
    for valor in list(vars(win).values()):
        try:
            if (callable(getattr(valor, "empezar", None)) and callable(getattr(valor, "parar", None))
                    and hasattr(valor, "catalogo")):
                return valor
        except Exception:  # noqa: BLE001
            continue
    return None


def fijar_tipo(gestor) -> None:
    """Toma del gestor el tipo de sus arrastres (al crear su apartado)."""
    global _tipo
    paquete = type(gestor).__module__.rsplit(".", 1)[0]
    _tipo = str(getattr(sys.modules.get(paquete + "._boton"), "MIME", _TIPO_SERIE))


def tipo_arrastre() -> str:
    return _tipo

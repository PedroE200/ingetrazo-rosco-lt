# SPDX-License-Identifier: GPL-3.0-or-later
"""El idioma (Opciones ▸ Idioma).

Los textos se escriben en español y se traducen en el momento de enseñarlos,
porque muchos también son claves internas (los modos de cada orden, por
ejemplo). ``_tr(texto)`` busca en ``_traducciones.TEXTOS``; lo que no esté se
enseña en español, nunca falla. Con argumentos es una plantilla:
``_tr("Lados: {0}", n)``.

Lo ya pintado se actualiza solo; las ventanas ya construidas (Texto, Tareas…)
cambian al reabrirlas o al reiniciar IngeTrazo.
"""
from __future__ import annotations

import re

from ._ajustes import NOMBRE, NOMBRE_BASE, registro

log = registro("idioma")

IDIOMAS = (("es", "Español"), ("en", "English"), ("fr", "Français"), ("de", "Deutsch"), ("zh", "中文"),
           ("hi", "हिन्दी"))
_COLUMNA = {"en": 0, "fr": 1, "de": 2, "zh": 3, "hi": 4}
# La fuente que tiene todos los caracteres de cada escritura (nombres de familia
# de las fuentes que trae el sistema; no se pueden cambiar).
_SUSTITUTAS = {"zh": ["Microsoft YaHei UI", "Microsoft YaHei"], "hi": ["Nirmala UI"]}  # nombre técnico
CLAVE = "idioma/actual"
# El nombre de la edición en los textos: los textos se escriben con el de la
# completa y, en otra edición, se cambia al enseñarlos (también traducidos).
_NOMBRE = re.compile(r"\b" + re.escape(NOMBRE_BASE) + r"\b(?! LT\b)") if NOMBRE != NOMBRE_BASE else None

_actual = None
_previas: tuple | None = None           # (familia, sustitutas que tenía) mientras hay una puesta
_faltan: set | None = None              # solo en las pruebas: lo que no se encontró


def con_nombre(texto: str) -> str:
    """``texto`` con el nombre de esta edición."""
    if _NOMBRE is None or not isinstance(texto, str):
        return texto
    return _NOMBRE.sub(NOMBRE, texto)


def _fuente() -> None:
    """En chino y en hindi, una sola fuente para todos los caracteres: si no,
    el sistema mezcla varias y algunos salen con otro grosor. Al cambiar de
    idioma se quita la anterior, para que no se pisen."""
    global _previas
    sustitutas = _SUSTITUTAS.get(_actual)
    if _previas is None and not sustitutas:
        return
    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        if _previas is not None:
            familia, antes = _previas
            QFont.removeSubstitutions(familia)
            if antes:
                QFont.insertSubstitutions(familia, antes)
            _previas = None
        if sustitutas:
            familia = QApplication.font().family()
            _previas = (familia, list(QFont.substitutes(familia)))
            QFont.insertSubstitutions(familia, sustitutas)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo cambiar la fuente del idioma")


def _ajustes():
    from ._ajustes import ajustes
    return ajustes()


def actual() -> str:
    global _actual
    if _actual is None:
        try:
            v = str(_ajustes().value(CLAVE, "es") or "es")
        except Exception:  # noqa: BLE001
            v = "es"
        _actual = v if v == "es" or v in _COLUMNA else "es"
        _fuente()
    return _actual


def poner(idioma: str) -> None:
    global _actual
    _actual = idioma if idioma == "es" or idioma in _COLUMNA else "es"
    _fuente()
    try:
        _ajustes().setValue(CLAVE, _actual)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo guardar el idioma")


def _tabla() -> dict:
    from ._traducciones import TEXTOS
    return TEXTOS


def _tr(texto, *args):
    """``texto`` en el idioma actual. Lo que no sea texto se devuelve tal cual."""
    if not isinstance(texto, str):
        return texto
    columna = _COLUMNA.get(actual())
    salida = texto
    if columna is not None and texto:
        fila = _tabla().get(texto)
        if fila is not None:
            salida = fila[columna] or texto
        elif _faltan is not None and any(c.isalpha() for c in texto):
            _faltan.add(texto)
    salida = con_nombre(salida)
    if args:
        try:
            return salida.format(*args)
        except (IndexError, KeyError, ValueError):
            log.warning("plantilla mal traducida: %r", salida)
            return con_nombre(texto).format(*args)
    return salida


def vigilar_faltan() -> set:
    """Para las pruebas: empieza a apuntar lo que no tiene traducción."""
    global _faltan
    _faltan = set()
    return _faltan

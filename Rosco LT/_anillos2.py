# SPDX-License-Identifier: GPL-3.0-or-later
"""Rosco: lo que va en los dos anillos y en la subbarra de cada botón,
guardado por grupo de huecos (los de la barra: General, y los que se creen).

Cada grupo guarda ``{"dentro": [7 claves], "fuera": [17 claves], "sub":
{clave: {"o": [[tipo, valor], …], "c": [[tipo, valor], …]}}}``: «o» son las
órdenes (rosa) y «c» los complementos (verde) de la subbarra de ``clave``; la
que no está en «sub» lleva su subbarra de serie. En «fuera» los huecos 0 y 8
son los ojos amarillo y verde (siempre «»). Una clave «» es un hueco en
blanco.

General, y los grupos que ya había antes de esta versión, empiezan con los
botones de serie; los grupos nuevos, con todos los huecos en blanco.
"""
from __future__ import annotations

import json
import logging

from ._ajustes import registro

log = registro("anillos2")
N_DENTRO, N_FUERA = 7, 17
OJOS_FUERA = (0, 8)                    # los ojos amarillo y verde, en el anillo de fuera
DEFECTO_DENTRO = ("seleccionar", "suprimir", "flip", "scale", "rotate", "empujar", "move")
DEFECTO_FUERA = ("", "medir", "linea", "rect", "circle", "poly", "arco", "texto",
                 "", "guardar", "bloquear", "ocultar", "agrupar", "invertir", "portapapeles", "borrar", "pintar")
_SECCION = "anillos2"


def _ajustes():
    from ._ajustes import ajustes
    return ajustes(_SECCION)


def defecto() -> dict:
    return {"dentro": list(DEFECTO_DENTRO), "fuera": list(DEFECTO_FUERA), "sub": {}}


def blanco() -> dict:
    return {"dentro": [""] * N_DENTRO, "fuera": [""] * N_FUERA, "sub": {}}


def _lista(valor, n) -> list:
    lista = [str(k or "") for k in (valor if isinstance(valor, list) else [])][:n]
    return lista + [""] * (n - len(lista))


def _pares(valor) -> list:
    salida = []
    for x in valor if isinstance(valor, list) else []:
        if isinstance(x, (list, tuple)) and len(x) == 2 and x[1]:
            salida.append([str(x[0]), str(x[1])])
    return salida


def normalizar(cfg) -> dict:
    if not isinstance(cfg, dict):
        return defecto()
    fuera = _lista(cfg.get("fuera"), N_FUERA)
    for i in OJOS_FUERA:
        fuera[i] = ""
    sub = {}
    for clave, s in (cfg.get("sub") or {}).items():
        if isinstance(s, dict):
            sub[str(clave)] = {"o": _pares(s.get("o")), "c": _pares(s.get("c"))}
    return {"dentro": _lista(cfg.get("dentro"), N_DENTRO), "fuera": fuera, "sub": sub}


def _con_defecto(s) -> set:
    try:
        return {int(x) for x in json.loads(str(s.value("con_defecto", "[]")))}
    except Exception:  # noqa: BLE001
        return set()


def preparar(huecos) -> None:
    """La primera vez: los grupos que ya existen se quedan con los botones de
    serie (solo los que se creen después empiezan en blanco)."""
    try:
        s = _ajustes()
        if str(s.value("preparado", False)).lower() in ("true", "1"):
            return
        ids = [int(j[0]) for j in huecos.juegos()]
        s.setValue("con_defecto", json.dumps(ids))
        s.setValue("preparado", True)
        s.sync()
    except Exception:  # noqa: BLE001
        log.exception("no se pudieron preparar los anillos de Rosco")


def leer(id_juego) -> dict:
    from ._huecos import ID_GENERAL
    s = _ajustes()
    crudo = s.value(f"j{int(id_juego)}", None)
    if crudo:
        try:
            return normalizar(json.loads(str(crudo)))
        except Exception:  # noqa: BLE001
            log.exception("anillos de Rosco ilegibles (grupo %s)", id_juego)
    if int(id_juego) == ID_GENERAL or int(id_juego) in _con_defecto(s):
        return defecto()
    return blanco()


def guardar(id_juego, cfg) -> None:
    s = _ajustes()
    s.setValue(f"j{int(id_juego)}", json.dumps(normalizar(cfg), ensure_ascii=False))
    s.sync()


def borrar(id_juego) -> None:
    """Al eliminar un grupo: fuera también lo suyo."""
    s = _ajustes()
    s.remove(f"j{int(id_juego)}")
    ids = _con_defecto(s) - {int(id_juego)}
    s.setValue("con_defecto", json.dumps(sorted(ids)))
    s.sync()

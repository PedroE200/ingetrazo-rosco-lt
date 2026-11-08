# SPDX-License-Identifier: GPL-3.0-or-later
"""Dónde guarda Rosco LT lo que recuerda: ``QSettings("IngeTrazo",
"rosco_lt")``, lo general en la raíz y un apartado por pieza
(«anillo», «modificar», «alinear»)."""
from __future__ import annotations

import logging

from PySide6.QtCore import QSettings

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

CLAVE = "rosco_lt"
CLAVE_MODELO = "rosco"                 # la de los datos dentro de los modelos

def ajustes(grupo: str = "") -> QSettings:
    """Los ajustes (de ``grupo``, si se da)."""
    s = QSettings("IngeTrazo", CLAVE)
    if grupo:
        s.beginGroup(grupo)
    return s


# Lo que se guarda en los grupos de los modelos: los archivos de antes lo tienen
# con otra clave y se reconoce por su contenido.
_MARCAS_MODELO = {"texto", "marco", "hotspots"}


def ext_al_dia(ext: dict) -> dict:
    """``ext`` de un grupo, con lo nuestro bajo la clave actual."""
    if ext and CLAVE_MODELO not in ext:
        for k, v in list(ext.items()):
            if isinstance(v, dict) and _MARCAS_MODELO & set(v):
                ext[CLAVE_MODELO] = ext.pop(k)
                break
    return ext


# ---- Exportar e importar (Opciones ▸ Configuración) ------------------------------------
_FORMATO = "rosco_lt_configuracion"


def _a_json(valor):
    """Un valor de QSettings en algo que se pueda escribir en JSON."""
    from PySide6.QtCore import QByteArray
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, (list, tuple)):
        return [_a_json(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _a_json(v) for k, v in valor.items()}
    if isinstance(valor, (QByteArray, bytes, bytearray)):
        import base64
        return {"__bytes__": base64.b64encode(bytes(valor)).decode("ascii")}
    return str(valor)


def _de_json(valor):
    if isinstance(valor, dict) and set(valor) == {"__bytes__"}:
        import base64
        from PySide6.QtCore import QByteArray
        return QByteArray(base64.b64decode(valor["__bytes__"]))
    if isinstance(valor, list):
        return [_de_json(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _de_json(v) for k, v in valor.items()}
    return valor


def _formato_valido(formato) -> bool:
    """Vale también lo exportado por versiones anteriores del rosco."""
    return isinstance(formato, str) and formato.startswith("rosco") and formato.endswith("configuracion")


def exportar(ruta: str) -> int:
    """Escribe todos los ajustes del rosco en ``ruta`` (JSON). Devuelve cuántos."""
    import json
    s = ajustes()
    datos = {k: _a_json(s.value(k)) for k in s.allKeys()}
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"formato": _FORMATO, "version": 1, "ajustes": datos}, f,
                  ensure_ascii=False, indent=1, sort_keys=True)
    return len(datos)


def importar(ruta: str) -> int:
    """Lee un archivo hecho con ``exportar`` y pone sus ajustes (los que no
    vienen en el archivo se quedan como estaban). Devuelve cuántos."""
    import json
    with open(ruta, encoding="utf-8") as f:
        contenido = json.load(f)
    if not isinstance(contenido, dict) or not _formato_valido(contenido.get("formato")):
        from ._idioma import _tr
        raise ValueError(_tr("no es un archivo de configuración de Rosco LT"))
    datos = contenido.get("ajustes") or {}
    s = ajustes()
    for k, v in datos.items():
        s.setValue(str(k), _de_json(v))
    s.sync()
    return len(datos)

# SPDX-License-Identifier: GPL-3.0-or-later
r"""Quién es esta edición y dónde guarda lo que recuerda.

La identidad sale toda de aquí (el empaquetador solo cambia ``CLAVE`` y
``NOMBRE``):

- ``QSettings("IngeTrazo", CLAVE)``: lo general en la raíz y un apartado por
  pieza («anillo», «modificar», «alinear»…);
- ``atributo(nombre)``: lo que se cuelga de la ventana, del visor o de las
  herramientas nativas (``_<CLAVE>_<nombre>``), para que dos ediciones
  cargadas a la vez no se pisen;
- ``registro(parte)``: el registro ``ingetrazo.plugins.<CLAVE>[.parte]``;
- ``carpeta_datos()``: ``%APPDATA%\IngeTrazo\<CLAVE>``;
- ``CLAVE_MODELO``: la de los datos dentro de los modelos, la misma en todas
  las ediciones.

En la completa (``CLAVE = "rosco"``), la primera vez se copian los ajustes de
las claves con las que se guardaban antes (que se quedan como estaban)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QSettings

CLAVE = "rosco_lt"                        # la edición (el empaquetador la cambia)
NOMBRE = "Rosco LT"                       # el nombre que se enseña (ídem)
NOMBRE_BASE = "Rosco"                  # el que llevan los textos escritos en el código
CLAVE_MODELO = "rosco"                 # la de los datos dentro de los modelos (compartida)


def registro(parte: str = "") -> logging.Logger:
    """El registro de esta edición (o de una de sus partes)."""
    return logging.getLogger(f"ingetrazo.plugins.{CLAVE}" + (f".{parte}" if parte else ""))


def atributo(nombre: str) -> str:
    """El nombre con que esta edición cuelga ``nombre`` de un objeto ajeno."""
    return f"_{CLAVE}_{nombre}"


def objeto(nombre: str) -> str:
    """Un nombre de objeto de Qt propio de esta edición (``<CLAVE>_<nombre>``)."""
    return f"{CLAVE}_{nombre}"


def carpeta_datos() -> Path:
    r"""``%APPDATA%\IngeTrazo\<CLAVE>``: lo que se guarda fuera de la carpeta
    de la extensión (reinstalarla no lo borra)."""
    try:
        from core.extensions import user_plugins_dir
        return Path(user_plugins_dir()).parent / CLAVE
    except Exception:  # noqa: BLE001 — misma regla que IngeTrazo
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "ingetrazo" / CLAVE


log = registro()

# Las claves de antes y el apartado donde quedan ahora (solo la completa las tuvo).
_ANTES = (("alinear", "alinear"),) if CLAVE == "rosco" else ()
_MARCA = "ajustes/copiados"
_mirado = False


def _copiar_antiguos() -> None:
    global _mirado
    if _mirado or not _ANTES:
        return
    _mirado = True
    nuevos = QSettings("IngeTrazo", CLAVE)
    if str(nuevos.value(_MARCA, "")).lower() in ("1", "true"):
        return
    try:
        for clave, grupo in _ANTES:
            viejos = QSettings("IngeTrazo", clave)
            for k in viejos.allKeys():
                destino = k
                if grupo:
                    destino = f"{grupo}/{destino}"
                if not nuevos.contains(destino):
                    nuevos.setValue(destino, viejos.value(k))
    except Exception:  # noqa: BLE001 — sin copia, valen los de serie
        log.exception("no se pudieron copiar los ajustes de antes")
    nuevos.setValue(_MARCA, True)
    nuevos.sync()


def ajustes(grupo: str = "") -> QSettings:
    """Los ajustes (de ``grupo``, si se da)."""
    _copiar_antiguos()
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
_FORMATO = f"{CLAVE}_configuracion"


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


def _leer_archivo(ruta: str) -> dict:
    """Los ajustes de un archivo hecho con ``exportar``."""
    import json
    with open(ruta, encoding="utf-8") as f:
        contenido = json.load(f)
    if not isinstance(contenido, dict) or not _formato_valido(contenido.get("formato")):
        from ._idioma import _tr
        raise ValueError(_tr("no es un archivo de configuración de Rosco"))
    return contenido.get("ajustes") or {}


def comprobar_importacion(ruta: str) -> bool:
    """Si el archivo trae grupos de huecos. Si los trae y no valen, lanza
    ``ValueError`` antes de escribir nada."""
    import json
    from ._huecos import CLAVE_GRUPOS, contenedor_valido
    from ._idioma import _tr
    datos = _leer_archivo(ruta)
    if CLAVE_GRUPOS not in datos:
        return False
    try:
        grupos = json.loads(datos[CLAVE_GRUPOS])
    except (TypeError, ValueError):
        grupos = None
    if not contenedor_valido(grupos):
        raise ValueError(_tr("El archivo trae unos grupos que no son válidos."))
    return True


def importar(ruta: str) -> int:
    """Lee un archivo hecho con ``exportar`` y pone sus ajustes (los que no
    vienen en el archivo se quedan como estaban, salvo el grupo activo, que
    vuelve a General si el archivo no dice otro). Devuelve cuántos."""
    from ._huecos import CLAVE_ACTIVO
    datos = _leer_archivo(ruta)
    s = ajustes()
    s.remove(CLAVE_ACTIVO)
    for k, v in datos.items():
        s.setValue(str(k), _de_json(v))
    s.sync()
    return len(datos)

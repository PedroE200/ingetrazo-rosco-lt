# SPDX-License-Identifier: GPL-3.0-or-later
"""Dónde se guardan las tareas.

- **De IngeTrazo** (para todos los modelos) y opciones: un JSON en
  ``%APPDATA%\\IngeTrazo\\<clave>\\tareas.json`` (``_ajustes.carpeta_datos``),
  fuera de la carpeta del plugin para que reinstalarlo no lo borre.
- **Del modelo**: el valor de ``app.document_data`` dentro del ``.igz``, un
  dict ``{"tareas": [...]}``, con la clave «<clave>_tareas» (la ``app`` que
  llega aquí es una copia de la de Rosco con esa clave).

La completa (clave «rosco») guardaba antes las tareas en otro sitio
(``ANTES``): si el archivo o la clave nuevos no existen y los de antes sí, se
leen los de antes (el archivo se copia ya al sitio nuevo; la clave del
modelo pasa a la nueva al guardar). Los de antes no se borran.

Una tarea es ``{"texto", "hecha", "creada", "hecha_en"}`` (fechas ISO).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from .._ajustes import CLAVE, carpeta_datos, registro

log = registro("tareas")
CLAVE_MODELO = f"{CLAVE}_tareas"       # la clave de las tareas del modelo en el .igz
# Dónde las guardaba la completa antes de esta versión: (carpeta, archivo, clave
# del modelo). Son nombres técnicos de datos ya guardados por los usuarios.
ANTES = {"rosco": ("bitnotes", "bitnotes.json", "bitnotes")}.get(CLAVE)  # nombre técnico
VERSION_DATOS = 1


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def limpias(lista) -> list[dict]:
    """Solo tareas con texto, con las cuatro claves."""
    out = []
    for t in lista or []:
        if isinstance(t, dict) and str(t.get("texto", "")).strip():
            out.append({"texto": str(t["texto"]).strip(), "hecha": bool(t.get("hecha")),
                        "creada": t.get("creada"), "hecha_en": t.get("hecha_en")})
    return out


def resumen(lista) -> tuple[int, int]:
    tareas = limpias(lista)
    hechas = sum(1 for t in tareas if t["hecha"])
    return len(tareas) - hechas, hechas


def carpeta_usuario_plugins() -> Path:
    try:
        from core.extensions import user_plugins_dir
        return Path(user_plugins_dir())
    except Exception:  # noqa: BLE001 — misma regla que IngeTrazo 0.5.8
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "ingetrazo" / "plugins"


def ruta_datos() -> Path:
    return carpeta_datos() / "tareas.json"


def ruta_antigua() -> Path | None:
    """El archivo de antes (solo la completa lo tuvo)."""
    if not ANTES:
        return None
    return carpeta_usuario_plugins().parent / ANTES[0] / ANTES[1]


# ---- Almacén global ------------------------------------------------------------

class Almacen:
    """El JSON global. Se lee una vez y se escribe entero (atómico) en cada
    cambio: son pocos KB."""

    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or ruta_datos()
        self.datos = self._vacio()
        if ruta is None:
            self._traer_antiguo()
        self._leer()

    def _traer_antiguo(self) -> None:
        """Sin archivo nuevo y con el de antes: se copia al sitio nuevo (el de
        antes se queda como estaba)."""
        antiguo = ruta_antigua()
        try:
            if antiguo is None or self.ruta.exists() or not antiguo.is_file():
                return
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.ruta.write_bytes(antiguo.read_bytes())
            log.info("tareas copiadas de %s a %s", antiguo, self.ruta)
        except OSError:
            log.exception("no se pudieron copiar las tareas de antes")

    @staticmethod
    def _vacio() -> dict:
        return {"version": VERSION_DATOS, "tareas": [],
                "opciones": {"formato_export": "txt"}}

    def _leer(self) -> None:
        try:
            crudo = json.loads(self.ruta.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.exception("%s ilegible; se aparta y se empieza de cero", self.ruta.name)
            try:
                self.ruta.replace(self.ruta.with_suffix(".json.roto"))
            except OSError:
                pass
            return
        if isinstance(crudo, dict):
            for clave, defecto in self._vacio().items():
                valor = crudo.get(clave, defecto)
                if type(valor) is type(defecto):
                    self.datos[clave] = valor
            self.datos["opciones"] = {**self._vacio()["opciones"],
                                      **self.datos["opciones"]}

    def guardar(self) -> None:
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ruta.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, self.ruta)
        except OSError:
            log.exception("no se pudo guardar %s", self.ruta)

    # -- opciones
    def opcion(self, clave, defecto=None):
        return self.datos["opciones"].get(clave, defecto)

    def poner_opcion(self, clave, valor) -> None:
        if self.datos["opciones"].get(clave) != valor:
            self.datos["opciones"][clave] = valor
            self.guardar()

    # -- tareas de IngeTrazo
    @property
    def tareas(self) -> list:
        return self.datos["tareas"]

    def poner_tareas(self, lista: list) -> None:
        self.datos["tareas"] = lista
        self.guardar()


# ---- Datos del modelo -----------------------------------------------------------

def _antiguas_modelo(app):
    """Las tareas del modelo guardadas con la clave de antes, o None."""
    if not ANTES:
        return None
    try:
        import copy
        vieja = copy.copy(app)
        vieja.key = ANTES[2]
        return vieja.document_data({}) or None
    except Exception:  # noqa: BLE001
        log.exception("no se pudieron leer las tareas de antes del modelo")
        return None


def tareas_modelo(app) -> list[dict]:
    crudo = app.document_data({}) or {}
    if not crudo:
        crudo = _antiguas_modelo(app) or {}   # pasan a la clave nueva al guardarlas
    if not isinstance(crudo, dict):
        return []
    return limpias(crudo.get("tareas"))


def poner_tareas_modelo(app, lista: list[dict]) -> None:
    """Un paso de deshacer; deja el modelo sin guardar, como cualquier edición."""
    crudo = app.document_data({}) or _antiguas_modelo(app) or {}
    datos = dict(crudo) if isinstance(crudo, dict) else {}
    datos["tareas"] = lista
    limpio = {k: v for k, v in datos.items() if v}
    app.set_document_data(limpio or None)


def ruta_actual(app) -> Path | None:
    ruta = getattr(app.window, "_current_path", None)
    return Path(ruta) if ruta else None


def nombre_modelo(app) -> str:
    ruta = ruta_actual(app)
    return ruta.name if ruta else "Sin título"


def abrir_externo(ruta: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))

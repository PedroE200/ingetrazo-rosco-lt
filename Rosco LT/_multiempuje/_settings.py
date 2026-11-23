# SPDX-License-Identifier: GPL-3.0-or-later
"""Opciones de Multiempuje (QSettings: preferencias del usuario, no del documento).

Desde la 1.2 el usuario elige un **movimiento** (Juntas, Una dirección, Cada cara) y unas
pocas opciones; de ahí sale el modo del motor (``_algo``): Juntas → conjunto / seguir /
redondeo; Una dirección → vector / extruir; Cada cara → normal."""
from __future__ import annotations

import json
import logging

from . import _algo as A

log = logging.getLogger("ingetrazo.plugins.multiempuje")

MOVIMIENTOS = ("juntas", "direccion", "cada_cara")
BORDES_EXT = ("inglete", "seguir", "promedio")
DIRECCIONES = ("normal", "media", "x", "y", "z", "custom")
SEL_MODES = ("single", "surface", "material", "all")

DEFECTO = {
    "movimiento": "juntas",
    "distancia": 0.0,          # metros; 0 = sin valor tecleado
    "sel_mode": "surface",     # single | surface | material | all
    "gen_group": False,
    "auto_open_group": True,   # clic en la cara de un grupo cerrado: abrirlo y empujar dentro
    "ayudas": True,            # popups con ilustración 3D al pasar el ratón por las opciones
    # Juntas
    "borde": "inglete",        # inglete | seguir | promedio
    "redondear": False,
    "angle_round": 20.0,
    "segment_round": 6,
    # Una dirección
    "direccion": "normal",     # normal | media | x | y | z | custom
    "vector_custom": None,
    "vector_local": False,
    "plana": False,            # cara superior plana (proyectada)
    # Cada cara
    "coquad": True,
    # variaciones
    "taper_on": False,
    "taper_pct": 80.0,
    "molding_on": False,
    "molding_angle": 5.0,
    "random_on": False,
    "rmin": 0.5,
    "rmax": 2.0,
    "seed": 2345,
}

# acabado y bordes nuevos se recuerdan por movimiento
POR_MOV = {
    "juntas": {"finishing": "thicken", "borders": "contour"},
    "direccion": {"finishing": "push", "borders": "contour"},
    "cada_cara": {"finishing": "push", "borders": "grid"},
}

# a qué modo antiguo (1.1) corresponde cada combinación, para migrar las preferencias
_MODO_VIEJO = {
    "engrosar": ("juntas", {}), "conjunto": ("juntas", {}), "seguir": ("juntas", {"borde": "seguir"}),
    "redondeo": ("juntas", {"redondear": True}), "vector": ("direccion", {}),
    "extruir": ("direccion", {"direccion": "media"}), "normal": ("cada_cara", {}),
}


class Opciones:
    def __init__(self):
        self.o = dict(DEFECTO)
        self.por_mov = {k: dict(v) for k, v in POR_MOV.items()}
        self.cargar()

    # ---- persistencia
    def _qs(self):
        from PySide6.QtCore import QSettings
        return QSettings("IngeTrazo", "multiempuje")

    def cargar(self):
        try:
            raw = self._qs().value("opciones", "")
            if not raw:
                return
            d = json.loads(raw)
            if "local" in d and "comun" in d:
                self._migrar_v1(d)
                return
            for k, v in (d.get("o") or {}).items():
                if k in self.o:
                    self.o[k] = v
            for m, dd in (d.get("por_mov") or {}).items():
                if m in self.por_mov:
                    for k, v in dd.items():
                        if k in self.por_mov[m]:
                            self.por_mov[m][k] = v
        except Exception:  # noqa: BLE001
            log.debug("opciones no leídas", exc_info=True)
        self._sanear()

    def _migrar_v1(self, d):
        """Preferencias de la 1.0/1.1 (modo + opciones por modo)."""
        for k, v in (d.get("comun") or {}).items():
            if k in self.o:
                self.o[k] = v
        local = d.get("local") or {}
        viejo = d.get("modo")
        if viejo in _MODO_VIEJO:
            mov, extra = _MODO_VIEJO[viejo]
            self.o["movimiento"] = mov
            self.o.update(extra)
        for viejo_m, nuevo_m in (("conjunto", "juntas"), ("vector", "direccion"), ("normal", "cada_cara")):
            dd = local.get(viejo_m) or {}
            for k in ("finishing", "borders"):
                if k in dd:
                    self.por_mov[nuevo_m][k] = dd[k]
        vd = local.get("vector") or {}
        if vd.get("vector_dir") in ("normal", "x", "y", "z", "custom"):
            self.o["direccion"] = vd["vector_dir"]
        self.o["vector_custom"] = vd.get("vector_custom")
        self.o["vector_local"] = bool(vd.get("vector_local"))
        self.o["plana"] = bool(vd.get("vector_projected")) or bool((local.get("extruir") or {}).get("extrude_flat"))
        self.o["coquad"] = bool((local.get("normal") or {}).get("coquad", True))
        self.o["angle_round"] = float((local.get("redondeo") or {}).get("angle_round", 20.0))
        self.o["segment_round"] = int((local.get("redondeo") or {}).get("segment_round", 6))
        if (local.get("conjunto") or {}).get("influence"):
            self.o["borde"] = "promedio"
        self._sanear()
        self.guardar()

    def _sanear(self):
        o = self.o
        if o["movimiento"] not in MOVIMIENTOS:
            o["movimiento"] = "juntas"
        if o["borde"] not in BORDES_EXT:
            o["borde"] = "inglete"
        if o["direccion"] not in DIRECCIONES:
            o["direccion"] = "normal"
        if o["direccion"] == "custom" and not o.get("vector_custom"):
            o["direccion"] = "normal"
        if o["sel_mode"] not in SEL_MODES:
            o["sel_mode"] = "surface"

    def guardar(self):
        try:
            self._qs().setValue("opciones", json.dumps({"version": 2, "o": self.o, "por_mov": self.por_mov}))
        except Exception:  # noqa: BLE001
            log.debug("opciones no guardadas", exc_info=True)

    # ---- acceso
    @property
    def movimiento(self):
        return self.o["movimiento"]

    @movimiento.setter
    def movimiento(self, m):
        if m in MOVIMIENTOS:
            self.o["movimiento"] = m

    @property
    def modo(self):
        """Modo del motor que corresponde a las opciones actuales."""
        m = self.movimiento
        if m == "juntas":
            if self.o["redondear"]:
                return "redondeo"
            if self.o["borde"] == "seguir":
                return "seguir"
            return "conjunto"
        if m == "direccion":
            return "extruir" if self.o["direccion"] == "media" else "vector"
        return "normal"

    def get(self, k, modo=None):
        if k in ("finishing", "borders"):
            return self.por_mov[self.movimiento][k]
        return self.o.get(k)

    def set(self, k, v, modo=None):
        if k in ("finishing", "borders"):
            self.por_mov[self.movimiento][k] = v
        elif k == "movimiento":
            self.movimiento = v
        else:
            self.o[k] = v
        self.guardar()

    def tiene(self, k, modo=None):
        return k in self.o or k in ("finishing", "borders")

    # ---- parámetros del motor
    def params(self, offset=0.0, vector=None, plano=None, invertir_acabado=False):
        o = self.o
        fin = self.get("finishing")
        if invertir_acabado:
            fin = "push" if fin == "thicken" else "thicken"
        return A.Params(
            mode=self.modo,
            offset=float(offset),
            finishing=fin,
            borders=self.get("borders"),
            influence=(o["borde"] == "promedio"),
            coquad=bool(o["coquad"]),
            angle_round=float(o["angle_round"] or 20.0),
            segment_round=int(o["segment_round"] or 6),
            vector=vector,
            vector_projected=bool(o["plana"]),
            extrude_flat=bool(o["plana"]),
            taper_on=bool(o["taper_on"]),
            taper=float(o["taper_pct"]) / 100.0,
            molding_on=bool(o["molding_on"]),
            molding_angle=float(o["molding_angle"]),
            random_on=bool(o["random_on"]),
            rmin=float(o["rmin"]),
            rmax=float(o["rmax"]),
            seed=int(o["seed"]),
            target_plane=plano,
        )

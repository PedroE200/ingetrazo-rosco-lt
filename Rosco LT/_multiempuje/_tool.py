# SPDX-License-Identifier: GPL-3.0-or-later
"""Herramienta interactiva de Multiempuje.

Estados: ``sel`` (pasar por las caras; Mayús las añade sin clic), ``pulsado`` (botón abajo,
aún sin mover), ``arrastre`` (clic y arrastra: se confirma al soltar), ``libre`` (clic largo: se
confirma con el siguiente clic), ``plano`` (el siguiente clic elige el plano destino) y
``direccion`` (el siguiente clic toma la dirección de una arista, cara, guía o eje).

Las caras de grupos y componentes cerrados se eligen sin abrirlos (3.3.0): se pueden juntar
caras sueltas y de varios grupos o componentes, y un solo arrastre (o la distancia tecleada)
las empuja todas a la vez, en un único paso de deshacer. Cada conjunto trabaja en las
coordenadas de su grupo y se dibuja con su matriz (componentes movidos o girados)."""
from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D

from tools.base import Tool

from . import _algo as A
from . import _bridge as BR
from . import _icons as IC
from ._i18n import _t

log = logging.getLogger("ingetrazo.plugins.multiempuje")

ARRASTRE_PX = 6.0
CLIC_LARGO_S = 0.45
UMBRAL_PX = 9.0
COLOR = (0.91, 0.55, 0.19, 1.0)

NOMBRES_SEL = {"single": "individual", "surface": "superficie", "material": "mismo material", "all": "todas las unidas"}
EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

try:
    from tools.base import POINT_SNAP_KINDS
except Exception:  # noqa: BLE001
    POINT_SNAP_KINDS = frozenset({"endpoint", "midpoint", "on_edge", "center", "intersection"})


def _fmt_vec(v):
    return "(" + " · ".join(f"{k:.2f}".replace(".", ",") for k in v) + ")"


class _Conj:
    """Un conjunto de caras de una misma malla: la abierta (o suelta) o la de un grupo o
    componente cerrado, con su matriz al mundo (None = identidad)."""

    def __init__(self, mesh, caras, m=None, grp=None):
        self.mesh = mesh
        ids = set(map(id, mesh.faces))
        self.caras = [f for f in caras if id(f) in ids]
        self.m = m
        self.grp = grp
        self.minv = None
        if m is not None:
            try:
                inv, ok = m.inverted()
                self.minv = inv if ok else None
            except Exception:  # noqa: BLE001
                self.minv = None
        self.cap = self.an = self.plan = None

    def mundo(self, p):
        if self.m is None:
            return p
        try:
            return BR.t3(self.m.map(BR.q3(p)))
        except Exception:  # noqa: BLE001
            return p

    def local(self, p):
        if self.minv is None:
            return p
        try:
            return BR.t3(self.minv.map(BR.q3(p)))
        except Exception:  # noqa: BLE001
            return p

    def vec_mundo(self, v):
        if v is None or self.m is None:
            return v
        try:
            return A.norm(BR.t3(self.m.mapVector(BR.q3(v)))) or v
        except Exception:  # noqa: BLE001
            return v

    def vec_local(self, v):
        if v is None or self.minv is None:
            return v
        try:
            return A.norm(BR.t3(self.minv.mapVector(BR.q3(v)))) or v
        except Exception:  # noqa: BLE001
            return v

    def tiene(self, face):
        return any(f is face for f in self.caras)


class MultiTool(Tool):
    name = "Multiempuje"
    description = "Empujar/tirar varias caras a la vez con siete métodos."
    icon = None
    shortcut = None
    uses_snap = True
    box_select = False
    vcb_label = "Distancia"
    wireframe_color = COLOR
    wireframe_depth_tested = False

    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.vp = None
        self.last = None
        self.last_distance = None
        self._aviso_grupo = 0.0
        self._marca = None
        self.extra = {}            # id(malla) → {"mesh", "grp", "m", "caras"}: caras de grupos cerrados
        self._lineas_extra = []
        self._reset()

    # ------------------------------------------------------------ estado
    def _reset(self):
        self.estado = "sel"
        self.press = None
        self.cap = None
        self.an = None
        self.plan = None
        self.offset = 0.0
        self.eje = None
        self.grab = None
        self._prev = []
        self._lines = []
        self._guia = []
        self.ctrl_down = False
        self._sign_an = 1.0
        self._caras_drag = []
        self._fin_an = None
        self._cand = None
        self._hover_grp = None
        self._etiqueta = None
        self._conjs = []
        self._prim = None
        self._n_mundo = None

    def _limpiar_previa(self):
        self._prev, self._lines, self._guia = [], [], []
        self._etiqueta = None
        if self.vp is not None:
            try:
                self.vp.set_suppressed_faces(set())
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ cursor
    @property
    def qt_cursor(self):
        return IC.tool_cursor(self._marca_actual())

    def _marca_actual(self):
        if self.estado == "plano":
            return "plano"
        if self.estado == "direccion":
            return "direccion"
        if self.estado == "libre":
            return "ok"
        if self.estado == "sel" and self._hover_grp is not None:
            return "grupo"
        if self._acabado() == "thicken":
            return "mas"
        return None

    def _cursor(self, forzar=False):
        m = self._marca_actual()
        if (m == self._marca and not forzar) or self.vp is None:
            return
        self._marca = m
        try:
            self.vp._apply_tool_cursor()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            try:
                self.vp.setCursor(IC.tool_cursor(m))
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ ciclo de vida
    def on_activate(self, viewport):
        if viewport.active_tool is not self:
            viewport.set_active_tool(self)
            return
        self.vp = viewport
        self._reset()
        self._marca = None
        n = len(BR.caras_seleccionadas(viewport.scene))
        modo = self.ctrl.nombre_modo()
        msg = f"Multiempuje · {modo}: pasa el ratón por una cara y arrastra para empujar; Mayús añade caras sin hacer clic."
        if n:
            msg = f"Multiempuje · {modo}: {n} caras elegidas. Arrastra sobre una de ellas o teclea la distancia y Enter."
        viewport.flash_status(msg, 7000)
        self._hint()
        self.ctrl.on_tool(True)
        self._cursor(forzar=True)

    def on_deactivate(self, viewport):
        self._limpiar_previa()
        self.extra = {}
        self._lineas_extra = []
        try:
            viewport.set_hover(None)
        except Exception:  # noqa: BLE001
            pass
        self._reset()
        self._marca = None
        viewport.update()
        self.ctrl.on_tool(False)

    def _hint(self):
        try:
            self.refresh_hint(self.vp)
        except Exception:  # noqa: BLE001
            pass

    def status_clause(self):
        fin = "engrosar" if self._acabado() == "thicken" else "empujar"
        txt = (f"{self.ctrl.nombre_modo()} (1-2-3) · selección: {NOMBRES_SEL.get(self.ctrl.opc.get('sel_mode'), '')} (Tab) · "
               f"Mayús añade caras · {fin} (Ctrl)")
        if self.ctrl.opc.movimiento == "direccion":
            txt += f" · dirección: {self.ctrl.nombre_vector()} (flechas)"
        if self.ctrl.plano is not None:
            txt += " · hasta el plano destino"
        try:
            g = self.vp.scene.edit_group if self.vp is not None else None
            if g is not None:
                txt += f" · dentro de «{getattr(g, 'name', '')}» (Esc o clic fuera sube un nivel)"
        except Exception:  # noqa: BLE001
            pass
        return txt

    def _acabado(self):
        fin = self.ctrl.opc.get("finishing")
        if self.ctrl_down:
            fin = "push" if fin == "thicken" else "thicken"
        return fin

    # ------------------------------------------------------------ utilidades
    def _pick(self, x, y):
        try:
            hit = self.vp.pick_face_any(x, y)
        except Exception:  # noqa: BLE001
            return None, None
        if not isinstance(hit, tuple):
            return hit, None
        face, grp = hit[0], hit[1] if len(hit) > 1 else None
        return face, grp

    def _mesh(self):
        return self.vp.scene.mesh

    def _en_malla(self, face):
        return face is not None and any(f is face for f in self._mesh().faces)

    def _seleccion(self):
        return BR.caras_seleccionadas(self.vp.scene)

    def _seleccionar(self, caras, modo="replace"):
        sc = self.vp.scene
        try:
            sc.select(list(caras), mode=modo)
        except Exception:  # noqa: BLE001
            if modo == "replace":
                sc.selection.clear()
            for f in caras:
                if modo == "remove":
                    sc.selection.discard(f)
                else:
                    sc.selection.add(f)
        try:
            sc.bump_view()
        except Exception:  # noqa: BLE001
            pass
        self.vp.update()

    def _avisar_grupo(self):
        ahora = time.monotonic()
        if ahora - self._aviso_grupo > 4.0:
            self._aviso_grupo = ahora
            self.vp.flash_status("No se puede elegir esa cara.", 3000)

    # ------------------------------------------------------------ caras de grupos cerrados
    def _matriz_ctx(self):
        """Matriz al mundo del grupo abierto (None = el modelo)."""
        try:
            return self.vp.window()._edit_group_matrix()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None

    def _grupo_de(self, face, grp):
        """``(grupo, matriz al mundo)`` del grupo o componente cuya malla tiene ``face``."""
        def tiene(g):
            mesh = getattr(g, "mesh", None)
            return mesh is not None and any(f is face for f in mesh.faces)
        if grp is not None and tiene(grp):
            return grp, self._matriz(grp)
        try:
            for g, m in self.vp.scene.placements():
                if tiene(g):
                    return g, m
        except Exception:  # noqa: BLE001
            pass
        return grp, self._matriz(grp)

    def _extras_vivos(self):
        """Las caras elegidas en grupos cerrados que siguen existiendo."""
        for k in list(self.extra):
            ent = self.extra[k]
            ids = set(map(id, ent["mesh"].faces))
            ent["caras"] = [f for f in ent["caras"] if id(f) in ids]
            if not ent["caras"]:
                del self.extra[k]
        return self.extra

    def _n_elegidas(self):
        return len(self._seleccion()) + sum(len(e["caras"]) for e in self._extras_vivos().values())

    def _hay_elegidas(self):
        return self._n_elegidas() > 0

    def _olvidar_extras(self):
        if self.extra:
            self.extra = {}
            self._pintar_extras()

    def _pintar_extras(self):
        """El contorno de las caras elegidas en grupos cerrados (en el mundo)."""
        lineas = []
        for ent in self._extras_vivos().values():
            m = ent["m"]
            for f in ent["caras"]:
                pts = [v.position for v in f.loop]
                if m is not None:
                    pts = [m.map(p) for p in pts]
                for i in range(len(pts)):
                    lineas.append((QVector3D(pts[i]), QVector3D(pts[(i + 1) % len(pts)])))
        self._lineas_extra = lineas
        if self.vp is not None:
            self.vp.update()

    def _elegir_en_grupo(self, face, grp, m, quitar=False):
        """Clic en una cara de un grupo o componente cerrado: se suma (o se quita) sin abrirlo."""
        mesh = getattr(grp, "mesh", None)
        if mesh is None:
            return
        caras = BR.ampliar(mesh, face, self.ctrl.opc.get("sel_mode"))
        k = id(mesh)
        ent = self.extra.get(k)
        ya = ent is not None and any(f is face for f in ent["caras"])
        if quitar or ya:
            if ent is not None:
                fuera = set(map(id, caras))
                ent["caras"] = [f for f in ent["caras"] if id(f) not in fuera]
                if not ent["caras"]:
                    del self.extra[k]
        else:
            if ent is None:
                ent = self.extra[k] = {"mesh": mesh, "grp": grp, "m": m, "caras": []}
            dentro = set(map(id, ent["caras"]))
            ent["caras"] += [f for f in caras if id(f) not in dentro]
        self.last = None
        self._pintar_extras()
        grupos = len(self._extras_vivos())
        self.vp.flash_status(f"Caras elegidas: {self._n_elegidas()} (en {grupos} grupo(s) o componente(s) "
                             "sin abrir). Arrastra una de ellas o teclea la distancia.", 2500)

    def _conjuntos(self):
        """Lo elegido, como conjuntos por malla: el de la malla abierta y uno por grupo."""
        conjs = []
        sel = self._seleccion()
        if sel:
            conjs.append(_Conj(self._mesh(), sel, self._matriz_ctx(), None))
        for ent in self._extras_vivos().values():
            conjs.append(_Conj(ent["mesh"], ent["caras"], ent["m"], ent["grp"]))
        return [c for c in conjs if c.caras]

    def _params_conj(self, conj, offset, n_mundo, invertir=None):
        inv = self.ctrl_down if invertir is None else invertir
        vec = None
        if self.ctrl.opc.modo == "vector":
            vec = conj.vec_local(self._vector(n_mundo))
        plano = self.ctrl.plano
        if plano is not None and conj.minv is not None:
            try:
                p, n = plano
                plano = (conj.local(tuple(p)), conj.vec_local(tuple(n)))
            except Exception:  # noqa: BLE001
                pass
        return self.ctrl.opc.params(offset=offset, vector=vec, plano=plano, invertir_acabado=inv)

    def _matriz(self, grp):
        """Matriz mundo de un grupo (instancias y grupos anidados) o None (identidad)."""
        if grp is None:
            return None
        try:
            for g, m in self.vp.scene.placements():
                if g is grp:
                    return m
        except Exception:  # noqa: BLE001
            pass
        return getattr(grp, "xform", None)

    @staticmethod
    def _mapear(m, p):
        if m is None:
            return p
        try:
            return BR.t3(m.map(BR.q3(p)))
        except Exception:  # noqa: BLE001
            return p

    @staticmethod
    def _mapear_vec(m, v):
        if m is None:
            return v
        try:
            return A.norm(BR.t3(m.mapVector(BR.q3(v)))) or v
        except Exception:  # noqa: BLE001
            return v

    def _matriz_local(self):
        """Matriz con los ejes del grupo o componente abierto (None = ejes del modelo)."""
        try:
            sc = self.vp.scene
            pila = getattr(sc, "_edit_stack", None) or []
            if pila and isinstance(pila[-1], dict):
                share = pila[-1].get("share")
                if share and len(share) > 2 and share[2] is not None:
                    return share[2]
                frame = pila[-1].get("frame")
                if frame is not None and hasattr(frame, "column"):
                    return frame
            m = self.vp.window()._edit_group_matrix()  # noqa: SLF001
            if m is not None:
                return m
        except Exception:  # noqa: BLE001
            pass
        return None

    def _eje_local(self, d):
        m = self._matriz_local()
        if m is None or d not in ("x", "y", "z"):
            return None
        try:
            c = m.column("xyz".index(d))
            return A.norm((float(c.x()), float(c.y()), float(c.z())))
        except Exception:  # noqa: BLE001
            return None

    def _vector(self, normal=None):
        d = self.ctrl.opc.get("direccion") or "normal"
        if d in EJES:
            v = EJES[d]
            if self.ctrl.opc.get("vector_local"):
                v = self._eje_local(d) or v
            return v
        if d == "custom":
            c = self.ctrl.opc.get("vector_custom")
            if c:
                v = A.norm(tuple(float(k) for k in c))
                if v:
                    return v
        return normal

    def _params(self, offset, normal=None, invertir=None):
        inv = self.ctrl_down if invertir is None else invertir
        vec = self._vector(normal) if self.ctrl.opc.modo == "vector" else None
        return self.ctrl.opc.params(offset=offset, vector=vec, plano=self.ctrl.plano, invertir_acabado=inv)

    def _ultimo_es_mio(self):
        if not self.last or self.vp is None:
            return False
        pila = getattr(self.vp.history, "undo_stack", None) or []
        return bool(pila) and pila[-1] is self.last.get("cmd")

    # ------------------------------------------------------------ grupos
    def _abrir_grupo(self, grp, x, y):
        """Abre ``grp`` (como el doble clic de Seleccionar) y devuelve la cara bajo el ratón ya
        dentro de él, o None si no se pudo."""
        if getattr(grp, "locked", False):
            self.vp.flash_status("Ese grupo está bloqueado: desbloquéalo antes.", 3000)
            return None
        try:
            self.vp.begin_group_edit(grp)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo abrir el grupo")
            self.vp.flash_status("No se pudo abrir el grupo.", 3000)
            return None
        self.last = None
        self._limpiar_previa()
        self._hover_grp = None
        face, g2 = self._pick(x, y)
        if face is not None and g2 is not None:
            # un grupo anidado más
            try:
                self.vp.begin_group_edit(g2)
            except Exception:  # noqa: BLE001
                return None
            face, g2 = self._pick(x, y)
        if face is None or g2 is not None or not self._en_malla(face):
            return None
        nombre = getattr(grp, "name", "") or ""
        self.vp.flash_status(f"Grupo «{nombre}» abierto: empuja sus caras; Esc (sin selección) o clic fuera sube un nivel.", 4000)
        self._hint()
        return face

    def _clic_en_vacio(self, x, y):
        try:
            if self.vp.scene.edit_group is None:
                return
            if not self.vp.edit_group_box_contains_pixel(x, y):
                self.vp.end_one_group_edit()
                self.last = None
                self.vp.flash_status("Grupo cerrado.", 2000)
                self._hint()
        except Exception:  # noqa: BLE001
            log.debug("no se pudo cerrar el grupo", exc_info=True)

    # ------------------------------------------------------------ ratón
    def on_hover(self, ctx):
        self.vp = ctx.viewport or self.vp
        mods = ctx.modifiers
        ctrl_now = bool(mods & Qt.ControlModifier)
        if ctrl_now != self.ctrl_down:
            self.ctrl_down = ctrl_now
            self._hint()
        x, y = ctx.screen.x(), ctx.screen.y()
        if self.estado == "pulsado":
            if math.hypot(x - self.press["x"], y - self.press["y"]) > ARRASTRE_PX:
                self._empezar_arrastre()
            self._cursor()
            return
        if self.estado in ("arrastre", "libre"):
            self._mover(ctx)
            self._cursor()
            return
        if self.estado == "direccion":
            self._hover_direccion(x, y)
            self._cursor()
            return
        if self.estado == "plano":
            self._hover_plano(x, y)
            self._cursor()
            return
        face, grp = self._pick(x, y)
        self._hover_grp = grp if (face is not None and grp is not None) else None
        if face is not None and grp is not None:
            try:
                self.vp.set_hover(face, grp)
            except Exception:  # noqa: BLE001
                try:
                    self.vp.set_hover(None)
                except Exception:  # noqa: BLE001
                    pass
        else:
            en = self._en_malla(face)
            try:
                self.vp.set_hover(face if en else None)
            except Exception:  # noqa: BLE001
                pass
            if en and (mods & Qt.ShiftModifier):
                self._anadir_por_paso(face)
        self._cursor()

    def _anadir_por_paso(self, face):
        caras = BR.ampliar(self._mesh(), face, self.ctrl.opc.get("sel_mode"))
        ids = set(map(id, self._seleccion()))
        nuevas = [f for f in caras if id(f) not in ids]
        if not nuevas:
            return
        self._seleccionar(nuevas, "add")
        self.last = None
        self.vp.flash_status(f"Caras elegidas: {len(self._seleccion())} (Mayús + clic quita)", 1500)

    def on_click(self, ctx):
        self.vp = ctx.viewport or self.vp
        x, y = ctx.screen.x(), ctx.screen.y()
        mods = ctx.modifiers
        if self.estado == "libre":
            self._confirmar()
            return
        if self.estado == "direccion":
            self._fijar_direccion()
            return
        face, grp = self._pick(x, y)
        if self.estado == "plano":
            self._elegir_plano(face, grp, x, y)
            return
        if face is None:
            if self._hay_elegidas():
                self._seleccionar([], "replace")
                self._olvidar_extras()
                self.last = None
                return
            self._clic_en_vacio(x, y)
            return
        ext = None
        if grp is not None or not self._en_malla(face):
            # 3.3.0: una cara de un grupo o componente cerrado se elige sin abrirlo.
            g, m = self._grupo_de(face, grp)
            if g is None or getattr(g, "mesh", None) is None:
                self._avisar_grupo()
                return
            if getattr(g, "locked", False):
                self.vp.flash_status("Ese grupo está bloqueado: desbloquéalo antes.", 3000)
                return
            ext = (g, m)
        self.press = {"face": face, "x": x, "y": y, "t": time.monotonic(), "shift": bool(mods & Qt.ShiftModifier),
                      "ext": ext}
        self.estado = "pulsado"

    def on_release(self, viewport):
        self.vp = viewport or self.vp
        if self.estado == "arrastre":
            self._confirmar()
            return
        if self.estado != "pulsado":
            return
        face = self.press["face"]
        if time.monotonic() - self.press["t"] > CLIC_LARGO_S:
            self._empezar_arrastre()
            if self.estado == "arrastre":
                self.estado = "libre"
                self._cursor()
                self.vp.flash_status("Arrastre libre: mueve el ratón y haz clic para confirmar (o teclea la distancia).", 5000)
            return
        if self.press.get("ext") is not None:
            g, m = self.press["ext"]
            self._elegir_en_grupo(face, g, m, quitar=bool(self.press.get("shift")))
            self.estado = "sel"
            self.press = None
            self._cursor()
            return
        caras = BR.ampliar(self._mesh(), face, self.ctrl.opc.get("sel_mode"))
        sel = self._seleccion()
        ya = any(f is face for f in sel)
        if self.press.get("shift"):
            modo = "remove"
        else:
            modo = "remove" if ya else "add"
        self._seleccionar(caras, modo)
        self.last = None
        self.estado = "sel"
        self.press = None
        n = self._n_elegidas()
        self.vp.flash_status(f"Caras elegidas: {n}", 2000)
        self._cursor()

    def on_double_click(self, ctx):
        self.vp = ctx.viewport or self.vp
        x, y = ctx.screen.x(), ctx.screen.y()
        face, grp = self._pick(x, y)
        if self.last_distance is None or face is None:
            return
        if grp is not None or not self._en_malla(face):
            g, m = self._grupo_de(face, grp)
            if g is None or getattr(g, "mesh", None) is None:
                return
            self._reset_drag()
            conj = _Conj(g.mesh, BR.ampliar(g.mesh, face, self.ctrl.opc.get("sel_mode")), m, g)
            self._aplicar_conjs([conj], self.last_distance, conj.vec_mundo(BR.t3(face.normal())))
            return
        self._reset_drag()
        sel = self._seleccion()
        caras = sel if any(f is face for f in sel) else BR.ampliar(self._mesh(), face, self.ctrl.opc.get("sel_mode"))
        self._aplicar(caras, self.last_distance, normal=BR.t3(face.normal()))

    def on_triple_click(self, ctx):
        return

    # ------------------------------------------------------------ arrastre
    def _reset_drag(self):
        self._limpiar_previa()
        self.estado = "sel"
        self.press = None
        self.cap = self.an = self.plan = None
        self._cand = None

    def _analizar(self, sign):
        n = self._normal_press()
        fin = None
        for conj in self._conjs:
            p = self._params_conj(conj, sign * 1e-3, n)
            conj.an = conj.cap.analizar(p)
            fin = p.finishing
        self.an = self._prim.an if self._prim is not None else None
        self._sign_an = sign
        self._fin_an = fin

    def _normal_press(self):
        """La normal (en el mundo) de la cara donde empezó el arrastre."""
        if self._n_mundo is not None:
            return self._n_mundo
        f = (self.press or {}).get("face")
        return A.norm(BR.t3(f.normal())) if f is not None else None

    def _empezar_arrastre(self):
        face = self.press["face"]
        ext = self.press.get("ext")
        # La cara donde se empieza, si no estaba elegida, deja solo su conjunto.
        if ext is None:
            if not any(f is face for f in self._seleccion()):
                self._seleccionar(BR.ampliar(self._mesh(), face, self.ctrl.opc.get("sel_mode")), "replace")
                self._olvidar_extras()
        else:
            g, m = ext
            ent = self._extras_vivos().get(id(g.mesh))
            if ent is None or not any(f is face for f in ent["caras"]):
                self._seleccionar([], "replace")
                self.extra = {}
                self._elegir_en_grupo(face, g, m)
        self.last = None
        self._hover_grp = None
        self._conjs = self._conjuntos()
        self._prim = next((c for c in self._conjs if c.tiene(face)), None)
        if self._prim is None:
            self.vp.flash_status("No se pueden analizar esas caras.", 4000)
            self._reset_drag()
            return
        self._caras_drag = [f for c in self._conjs for f in c.caras]
        prim = self._prim
        self._n_mundo = A.norm(prim.vec_mundo(BR.t3(face.normal()))) or (0.0, 0.0, 1.0)
        try:
            for conj in self._conjs:
                conj.cap = BR.Captura(conj.mesh, conj.caras)
            self.cap = prim.cap
            self._analizar(1.0)
        except Exception:  # noqa: BLE001
            log.exception("análisis fallido")
            self.vp.flash_status("No se pueden analizar esas caras.", 4000)
            self._reset_drag()
            return
        n = self._n_mundo
        fid = self.cap.fid.get(id(face))
        if self.ctrl.opc.modo == "vector":
            eje = A.norm(self._vector(n) or n) or n
        elif self.ctrl.opc.modo == "extruir" and fid is not None:
            eje = prim.vec_mundo(self.an.block_vec.get(self.an.block_of.get(fid), prim.vec_local(n)))
        else:
            eje = n
        c = QVector3D(*prim.mundo(BR.t3(face.centroid())))
        try:
            hit = self.vp._ray_hit_plane((self.press["x"], self.press["y"]), (c, QVector3D(*n)))  # noqa: SLF001
        except Exception:  # noqa: BLE001
            hit = None
        self.grab = BR.t3(hit) if hit is not None else BR.t3(c)
        self.eje = eje
        self.offset = 0.0
        self.estado = "arrastre"
        self._lineas_extra = []
        self.vp.flash_status(f"{self.ctrl.nombre_modo()}: arrastra hasta la distancia deseada (o teclea la distancia). Ctrl = conservar la original.", 5000)

    def _mover(self, ctx):
        if self.an is None:
            return
        x, y = ctx.screen.x(), ctx.screen.y()
        try:
            proj = self.vp._project_to_lock_line(BR.q3(self.grab), BR.q3(self.eje), x, y)  # noqa: SLF001
            off = A.dot(A.sub(BR.t3(proj), self.grab), self.eje)
        except Exception:  # noqa: BLE001
            off = self.offset
        snap = getattr(ctx, "snap", None)
        if snap is not None and getattr(snap, "kind", None) in POINT_SNAP_KINDS and getattr(snap, "point", None) is not None:
            sp = BR.t3(snap.point)
            if not self._punto_propio(sp):
                off = A.dot(A.sub(sp, self.grab), self.eje)
        sign = 1.0 if off >= 0 else -1.0
        fin = self._acabado()
        if (sign != self._sign_an and self.ctrl.opc.modo == "redondeo") or fin != self._fin_an:
            self._analizar(sign)
        for conj in self._conjs:
            if conj.an is not None:
                conj.an.p.finishing = fin
        self.offset = off
        self._previa()

    def _punto_propio(self, p):
        if not self.cap:
            return False
        if self._prim is not None:
            p = self._prim.local(p)
        k = A.pkey(p, 1e-5)
        return any(A.pkey(self.cap.mi.pos[v], 1e-5) == k for fid in self.cap.sel for v in self.cap.mi.faces[fid].loop)

    def _previa(self):
        prev, lineas = [], []
        for conj in self._conjs:
            try:
                conj.plan = A.build_plan(conj.an, self.offset, for_preview=True)
            except Exception:  # noqa: BLE001
                log.exception("vista previa fallida")
                conj.plan = None
            if conj.plan is None or not conj.plan.ok:
                continue
            caras = BR.vista_previa(conj.plan)
            trazos = BR.lineas_previa(conj.plan)
            if conj.m is not None:
                caras = BR.mover_previa(caras, conj.m)
                trazos = [(conj.m.map(a), conj.m.map(b)) for a, b in trazos]
            prev += caras
            lineas += trazos
        self.plan = self._prim.plan if self._prim is not None else None
        self._prev, self._lines = prev, lineas
        push = self.an is not None and self.an.p.finishing == "push" and not self.ctrl.opc.get("gen_group")
        try:
            self.vp.set_suppressed_faces(set(self._caras_drag) if push and self._prev else set())
        except Exception:  # noqa: BLE001
            pass
        if self.grab and self.eje:
            fin = A.add(self.grab, A.mul(self.eje, self.offset))
            self._guia = [(BR.q3(self.grab), BR.q3(fin))]
        self.vp.update()

    def _confirmar(self, off=None):
        off = self.offset if off is None else off
        conjs = list(self._conjs)
        normal = self._normal_press()
        self._reset_drag()
        self._cursor()
        if self.ctrl.plano is None and abs(off) < 1e-6:
            self.vp.flash_status("Distancia demasiado pequeña: arrastra más o teclea la distancia.", 3000)
            self._pintar_extras()
            return
        self._aplicar_conjs(conjs, off, normal)

    # ------------------------------------------------------------ aplicar
    def _aplicar(self, caras, off, cap=None, normal=None, invertir=None):
        """Las caras de la malla abierta y, además, las elegidas en grupos cerrados."""
        conjs = []
        if caras:
            conjs.append(_Conj(self._mesh(), caras, self._matriz_ctx(), None))
        for ent in self._extras_vivos().values():
            conjs.append(_Conj(ent["mesh"], ent["caras"], ent["m"], ent["grp"]))
        conjs = [c for c in conjs if c.caras]
        if not conjs:
            self.vp.flash_status("No hay caras elegidas.", 3000)
            return False
        if normal is None:
            normal = A.norm(conjs[0].vec_mundo(BR.t3(conjs[0].caras[0].normal())))
        return self._aplicar_conjs(conjs, off, normal, invertir)

    def _aplicar_conjs(self, conjs, off, normal, invertir=None):
        """Empuja cada conjunto en su propia malla: todo en un solo paso de deshacer."""
        vp = self.vp
        scene = vp.scene
        from core.history import CompoundCommand, InsertGroupCommand, SnapshotMutation
        cmds, hechos, res = [], [], {}
        try:
            for conj in conjs:
                ids = set(map(id, conj.mesh.faces))
                caras = [f for f in conj.caras if id(f) in ids]
                if not caras:
                    continue
                cap = conj.cap if (conj.cap is not None and conj.cap.mesh is conj.mesh) else BR.Captura(conj.mesh, caras)
                if not cap.sel:
                    continue
                n_mundo = normal or A.norm(conj.vec_mundo(BR.t3(cap.caras[0].normal())))
                params = self._params_conj(conj, off, n_mundo, invertir)
                plan = A.build_plan(cap.analizar(params), off)
                if not plan.ok:
                    continue
                propia = conj.mesh is scene.mesh
                if self.ctrl.opc.get("gen_group") and propia:
                    cmds.append(InsertGroupCommand(BR.grupo_con(plan, cap, nombre=_t("Multiempuje"),
                                                                engrosar=params.finishing == "thicken")))
                else:
                    def mutar(sc, cap=cap, plan=plan, conj=conj):
                        res[id(conj)] = BR.aplicar(sc, cap, plan, mesh=conj.mesh)
                    cmds.append(SnapshotMutation(mutar, mesh=conj.mesh))
                hechos.append((conj, cap))
        except Exception:  # noqa: BLE001
            log.exception("cálculo fallido")
            vp.flash_status("Error en el cálculo de la geometría.", 5000)
            return False
        if not cmds:
            vp.flash_status("No hay nada que generar con esa distancia.", 3000)
            return False
        cmd = cmds[0] if len(cmds) == 1 else CompoundCommand(cmds)
        try:
            vp.history.last_error = None
        except Exception:  # noqa: BLE001
            pass
        vp.history.execute(cmd)
        err = getattr(vp.history, "last_error", None)
        try:
            vp.set_suppressed_faces(set())
        except Exception:  # noqa: BLE001
            pass
        if err:
            vp.flash_status(f"Error en la generación de la geometría: {err}", 6000)
            return False
        # Las caras de arriba quedan elegidas: las de la malla abierta, seleccionadas; las de
        # los grupos cerrados, marcadas.
        self.extra = {}
        tops_ctx = []
        for conj, _cap in hechos:
            tops = res.get(id(conj)) or []
            if conj.mesh is scene.mesh:
                tops_ctx += tops
            elif tops:
                self.extra[id(conj.mesh)] = {"mesh": conj.mesh, "grp": conj.grp, "m": conj.m, "caras": list(tops)}
        self._seleccionar(tops_ctx, "replace")
        self._pintar_extras()
        self.last = {"cmd": cmd, "conjs": [(c.mesh, list(cap.caras), c.m, c.grp) for c, cap in hechos],
                     "caras": [f for _c, cap in hechos for f in cap.caras], "offset": off,
                     "normal": normal, "invertir": invertir}
        self.last_distance = off
        try:
            vp.notify_scene_changed()
        except Exception:  # noqa: BLE001
            pass
        vp.update()
        try:
            from core.units import fmt_len
            txt = fmt_len(off)
        except Exception:  # noqa: BLE001
            txt = f"{off:.3f} m"
        n = sum(len(cap.sel) for _c, cap in hechos)
        vp.flash_status(f"{self.ctrl.nombre_modo()}: {n} caras a {txt}. Cambia opciones del panel para rehacerlo; "
                        f"Retroceso lo deshace; doble clic repite.", 6000)
        self.ctrl.on_aplicado(off)
        return True

    def reaplicar(self, offset=None):
        """Rehace la última operación con las opciones actuales (si sigue siendo lo último)."""
        if self.estado != "sel" or not self._ultimo_es_mio():
            return False
        last = self.last
        self.vp.history.undo()
        conjs = [_Conj(mesh, caras, m, g) for mesh, caras, m, g in last.get("conjs") or ()]
        conjs = [c for c in conjs if c.caras]
        if not conjs:
            self.last = None
            return False
        off = last["offset"] if offset is None else offset
        return self._aplicar_conjs(conjs, off, last.get("normal"), last.get("invertir"))

    def deshacer_ultimo(self):
        if not self._ultimo_es_mio():
            return False
        conjs = self.last.get("conjs") or ()
        self._limpiar_previa()
        self.vp.history.undo()
        mesh_ctx = self._mesh()
        self.extra = {}
        sel = []
        for mesh, caras, m, g in conjs:
            ids = set(map(id, mesh.faces))
            vivas = [f for f in caras if id(f) in ids]
            if mesh is mesh_ctx:
                sel += vivas
            elif vivas:
                self.extra[id(mesh)] = {"mesh": mesh, "grp": g, "m": m, "caras": vivas}
        self._seleccionar(sel, "replace")
        self._pintar_extras()
        self.last = None
        try:
            self.vp.notify_scene_changed()
        except Exception:  # noqa: BLE001
            pass
        return True

    def aplicar_seleccion(self, off):
        caras = self._seleccion()
        if not caras and not self._hay_elegidas():
            self.vp.flash_status("Elige primero las caras (pasa el ratón con Mayús o haz clic sobre ellas).", 3000)
            return False
        if self.ctrl.plano is None and abs(off) < 1e-9:
            self.vp.flash_status("Teclea una distancia distinta de cero.", 3000)
            return False
        return self._aplicar(caras, off)

    # ------------------------------------------------------------ teclado y medidas
    def on_value(self, viewport, value):
        self.vp = viewport or self.vp
        if isinstance(value, (tuple, list)):
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if self.estado in ("arrastre", "libre"):
            sign = -1.0 if self.offset < 0 else 1.0
            self._confirmar(sign * v)
            return True
        if self._ultimo_es_mio():
            sign = -1.0 if self.last["offset"] < 0 else 1.0
            self.ctrl.recordar_distancia(v)
            return bool(self.reaplicar(sign * v))
        if self._hay_elegidas():
            self.ctrl.recordar_distancia(v)
            return bool(self.aplicar_seleccion(v))
        return False

    def on_key(self, viewport, key, modifiers):
        self.vp = viewport or self.vp
        if key == Qt.Key_Backspace:
            if self.estado in ("arrastre", "libre", "plano", "direccion"):
                return False
            if self._ultimo_es_mio():
                self.deshacer_ultimo()
                self.vp.flash_status("Último empuje deshecho; las caras originales vuelven a estar elegidas.", 3000)
                return True
            return False
        if key == Qt.Key_Tab:
            if self.estado in ("arrastre", "libre") and self.ctrl.opc.movimiento == "direccion":
                self.ctrl.toggle_local()
                self._rearrancar()
                return True
            self.ctrl.ciclar_seleccion()
            self._hint()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self.estado in ("arrastre", "libre"):
                self._confirmar()
                return True
            if self.estado in ("plano", "direccion"):
                return False
            d = float(self.ctrl.opc.get("distancia") or 0.0)
            if self._hay_elegidas() and (abs(d) > 1e-9 or self.ctrl.plano is not None):
                self.aplicar_seleccion(d)
                return True
            return False
        movs = {Qt.Key_1: "juntas", Qt.Key_2: "direccion", Qt.Key_3: "cada_cara"}
        if key in movs and self.estado in ("sel", "arrastre", "libre"):
            self.ctrl.set_movimiento(movs[key])
            self._rearrancar()
            return True
        if self.ctrl.opc.movimiento == "direccion":
            ejes = {Qt.Key_Right: "x", Qt.Key_Left: "y", Qt.Key_Up: "z", Qt.Key_Down: "normal"}
            if key in ejes:
                nuevo = ejes[key]
                if nuevo != "normal" and nuevo == self.ctrl.opc.get("direccion"):
                    nuevo = "normal"
                self.ctrl.set_direccion(nuevo)
                self._rearrancar()
                return True
        return False

    def _rearrancar(self):
        """Tras cambiar la dirección o el modo durante el arrastre, recalcula."""
        self._hint()
        self._cursor()
        if self.estado in ("arrastre", "libre") and self.cap is not None:
            normal = self._normal_press() or (0.0, 0.0, 1.0)
            self._analizar(1.0 if self.offset >= 0 else -1.0)
            if self.ctrl.opc.modo == "vector":
                self.eje = A.norm(self._vector(normal) or normal) or normal
            self._previa()
        elif self.estado == "sel":
            self.reaplicar()

    def on_cancel(self, viewport):
        self.vp = viewport or self.vp
        if self.estado in ("plano", "direccion"):
            self._reset_drag()
            try:
                self.vp.set_hover(None)
            except Exception:  # noqa: BLE001
                pass
            self.vp.flash_status("Elección cancelada.", 2000)
            self._cursor()
            self.vp.update()
            return
        if self.estado != "sel":
            self._reset_drag()
            self._cursor()
            self.vp.update()
            return
        if self._hay_elegidas():
            self._seleccionar([], "replace")
            self._olvidar_extras()
            self.last = None
            return
        try:
            if self.vp.scene.edit_group is not None:
                self.vp.end_one_group_edit()
                self.last = None
                self._hover_grp = None
                self.vp.flash_status("Grupo cerrado (otro Esc sale de la herramienta).", 2500)
                self._hint()
                self._cursor()
                return
        except Exception:  # noqa: BLE001
            log.debug("no se pudo cerrar el grupo", exc_info=True)
        try:
            w = self.vp.window()
            if hasattr(w, "_activate_tool"):
                w._activate_tool("select")  # noqa: SLF001
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            self.vp.set_active_tool(None)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ plano destino
    def pedir_plano(self):
        self._reset_drag()
        self.estado = "plano"
        self.vp.flash_status("Haz clic en la cara (o plano de sección) que marca el plano destino; vale una cara de un grupo cerrado. Esc cancela.", 6000)
        self._cursor()

    def _hover_plano(self, x, y):
        face, grp = self._pick(x, y)
        self._etiqueta = None
        try:
            self.vp.set_hover(face, grp) if face is not None else self.vp.set_hover(None)
        except Exception:  # noqa: BLE001
            pass
        if face is not None:
            n = self._mapear_vec(self._matriz(grp), A.norm(BR.t3(face.normal())) or (0.0, 0.0, 1.0))
            p = self._punto_bajo_cursor(x, y) or self._mapear(self._matriz(grp), BR.t3(face.centroid()))
            self._etiqueta = (f"{_t('Plano destino')}: {_t('cara')} · normal {_fmt_vec(n)}", BR.q3(p))
        self.vp.update()

    def _punto_bajo_cursor(self, x, y):
        try:
            p = self.vp._world_under_cursor(x, y)  # noqa: SLF001
            return BR.t3(p) if p is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _plano_seccion(self, x, y):
        try:
            sp = self.vp.pick_section_plane(x, y)
        except Exception:  # noqa: BLE001
            return None
        if sp is None:
            return None
        n = getattr(sp, "normal", None)
        p = getattr(sp, "origin", None) or getattr(sp, "point", None) or getattr(sp, "center", None)
        if n is None or p is None:
            return None
        try:
            n = n() if callable(n) else n
            p = p() if callable(p) else p
            nn = A.norm(BR.t3(n))
            return (BR.t3(p), nn) if nn else None
        except Exception:  # noqa: BLE001
            return None

    def _elegir_plano(self, face, grp, x, y):
        self.estado = "sel"
        self._etiqueta = None
        try:
            self.vp.set_hover(None)
        except Exception:  # noqa: BLE001
            pass
        if face is None:
            plano = self._plano_seccion(x, y)
            if plano is None:
                self.vp.flash_status("No hay ninguna cara ni plano ahí.", 3000)
                self._cursor()
                return
            self.ctrl.set_plano(plano)
        else:
            m = self._matriz(grp)
            p = BR.t3(face.loop[0].position) if face.loop else BR.t3(face.centroid())
            p = self._mapear(m, p)
            nn = self._mapear_vec(m, A.norm(BR.t3(face.normal())) or (0.0, 0.0, 1.0))
            self.ctrl.set_plano((p, nn))
        self.vp.flash_status("Plano destino fijado: las caras llegarán hasta él.", 4000)
        self._hint()
        self._cursor()

    # ------------------------------------------------------------ dirección (modo Vector)
    def pedir_direccion(self):
        self._reset_drag()
        self.estado = "direccion"
        self._cand = None
        self.vp.flash_status("Pasa el ratón por una arista, una cara, una guía o un eje y haz clic para tomar su dirección (Esc cancela).", 7000)
        self._cursor()

    @staticmethod
    def _puntos_arista(e):
        if e is None:
            return None
        try:
            return BR.t3(e.v0.position), BR.t3(e.v1.position)
        except Exception:  # noqa: BLE001
            pass
        for ka, kb in (("a", "b"), ("p0", "p1"), ("start", "end")):
            a, b = getattr(e, ka, None), getattr(e, kb, None)
            if a is None or b is None:
                continue
            try:
                a = a() if callable(a) else a
                b = b() if callable(b) else b
                return (BR.t3(a) if hasattr(a, "x") else tuple(a)), (BR.t3(b) if hasattr(b, "x") else tuple(b))
            except Exception:  # noqa: BLE001
                continue
        if isinstance(e, (tuple, list)) and len(e) >= 2:
            try:
                return tuple(e[0]), tuple(e[1])
            except Exception:  # noqa: BLE001
                return None
        return None

    def _arista_grupo(self, grp, x, y):
        """Arista de un grupo cerrado más cercana al cursor (proyección propia)."""
        m = self._matriz(grp)
        mesh = getattr(grp, "mesh", None)
        if mesh is None:
            return None
        vs, idx = [], {}
        edges = list(mesh.edges)[:40000]
        for e in edges:
            for v in (e.v0, e.v1):
                if id(v) not in idx:
                    idx[id(v)] = len(vs)
                    vs.append(self._mapear(m, BR.t3(v.position)))
        if not vs:
            return None
        try:
            xs, ys, _fr = self.vp.world_to_pixels([list(p) for p in vs])
        except Exception:  # noqa: BLE001
            return None
        mejor = None
        for e in edges:
            i, j = idx[id(e.v0)], idx[id(e.v1)]
            ax, ay, bx, by = float(xs[i]), float(ys[i]), float(xs[j]), float(ys[j])
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
            d = math.hypot(ax + dx * t - x, ay + dy * t - y)
            if d <= UMBRAL_PX and (mejor is None or d < mejor[0]):
                mejor = (d, vs[i], vs[j])
        return (mejor[1], mejor[2]) if mejor else None

    def _pick_arista(self, x, y):
        e = None
        try:
            e = self.vp.pick_edge_any(x, y)
        except Exception:  # noqa: BLE001
            try:
                e = self.vp.pick_edge(x, y)
            except Exception:  # noqa: BLE001
                e = None
        pts = self._puntos_arista(e)
        if pts is None:
            try:
                grp = self.vp.pick_group(x, y)
            except Exception:  # noqa: BLE001
                grp = None
            if grp is not None and getattr(grp, "mesh", None) is not None:
                pts = self._arista_grupo(grp, x, y)
        if pts is None:
            return None
        a, b = pts
        d = A.norm(A.sub(b, a))
        if d is None:
            return None
        return {"dir": d, "origen": self._sobre_linea(a, d, x, y), "texto": _t("Arista")}

    def _sobre_linea(self, a, d, x, y):
        try:
            p = self.vp._project_to_lock_line(BR.q3(a), BR.q3(d), x, y)  # noqa: SLF001
            return BR.t3(p)
        except Exception:  # noqa: BLE001
            return a

    def _candidato_direccion(self, x, y):
        vp = self.vp
        c = self._pick_arista(x, y)
        if c:
            return c
        try:
            g = vp.pick_guide(x, y)
        except Exception:  # noqa: BLE001
            g = None
        if g is not None:
            try:
                a, b = g.segment()
                a, b = BR.t3(a), BR.t3(b)
                d = A.norm(A.sub(b, a))
                if d:
                    return {"dir": d, "origen": self._sobre_linea(a, d, x, y), "texto": _t("Guía")}
            except Exception:  # noqa: BLE001
                pass
        try:
            ax = vp.pick_axis(x, y)
        except Exception:  # noqa: BLE001
            ax = None
        if ax in EJES:
            d = EJES[ax]
            try:
                from core.axes import origin as _ori
                o = BR.t3(_ori())
            except Exception:  # noqa: BLE001
                o = (0.0, 0.0, 0.0)
            return {"dir": d, "origen": self._sobre_linea(o, d, x, y), "texto": f"{_t('Eje')} {ax.upper()}"}
        face, grp = self._pick(x, y)
        if face is not None:
            m = self._matriz(grp)
            n = self._mapear_vec(m, A.norm(BR.t3(face.normal())) or (0.0, 0.0, 1.0))
            o = self._punto_bajo_cursor(x, y) or self._mapear(m, BR.t3(face.centroid()))
            return {"dir": n, "origen": o, "texto": _t("Cara (normal)"), "face": face, "grp": grp}
        plano = self._plano_seccion(x, y)
        if plano is not None:
            return {"dir": plano[1], "origen": plano[0], "texto": _t("Plano de sección (normal)")}
        return None

    def _largo_guia(self):
        try:
            return max(0.5, float(self.vp.camera.distance) * 0.3)
        except Exception:  # noqa: BLE001
            return 1.0

    def _hover_direccion(self, x, y):
        cand = self._candidato_direccion(x, y)
        self._cand = cand
        self._lines, self._guia, self._etiqueta = [], [], None
        try:
            if cand and cand.get("face") is not None:
                self.vp.set_hover(cand["face"], cand.get("grp"))
            else:
                self.vp.set_hover(None)
        except Exception:  # noqa: BLE001
            pass
        if cand:
            o, d = cand["origen"], cand["dir"]
            L = self._largo_guia()
            self._lines = [(BR.q3(A.sub(o, A.mul(d, L))), BR.q3(A.add(o, A.mul(d, L))))]
            self._guia = [(BR.q3(o), BR.q3(A.add(o, A.mul(d, L * 0.5))))]
            self._etiqueta = (f"{cand['texto']}: {_fmt_vec(d)} — clic para fijar", BR.q3(o))
        self.vp.update()

    def _fijar_direccion(self):
        cand = self._cand
        self._reset_drag()
        try:
            self.vp.set_hover(None)
        except Exception:  # noqa: BLE001
            pass
        if not cand:
            self.vp.flash_status("No hay ninguna arista, cara, guía ni eje bajo el ratón.", 3000)
            self._cursor()
            return
        self.ctrl.set_vector_custom(cand["dir"], cand["texto"])
        self.vp.flash_status(f"Dirección fijada: {cand['texto']} {_fmt_vec(cand['dir'])}.", 4000)
        self._cursor()

    # ------------------------------------------------------------ dibujo
    def rubber_band_lines(self):
        if self.estado in ("arrastre", "libre"):
            return self._lines
        return self._lines + self._lineas_extra

    def preview_faces(self):
        return self._prev

    def inference_guide_lines(self):
        return self._guia

    def value_label(self):
        if self.estado in ("arrastre", "libre") and self.grab:
            try:
                from core.units import fmt_len
                txt = fmt_len(self.offset)
            except Exception:  # noqa: BLE001
                txt = f"{self.offset:.3f}"
            return (txt, BR.q3(A.add(self.grab, A.mul(self.eje, self.offset))))
        if self.estado in ("plano", "direccion") and self._etiqueta:
            return self._etiqueta
        return None

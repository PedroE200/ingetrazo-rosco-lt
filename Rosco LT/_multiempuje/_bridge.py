# SPDX-License-Identifier: GPL-3.0-or-later
"""Puente entre la malla de IngeTrazo y el motor ``_algo``.

- ``Captura``: traduce las caras elegidas (y su vecindad) a ``MeshIn`` y guarda la
  correspondencia con los objetos ``Face``/``Vertex`` reales.
- ``vista_previa``: caras ``core.geometry.Face`` para dibujar el resultado mientras se arrastra.
- ``aplicar``: lleva el ``Plan`` a la malla dentro de un único paso de deshacer.
- ``ampliar``: selección por cara, superficie, material o todo lo unido.
"""
from __future__ import annotations

import copy
import logging
import math

from PySide6.QtGui import QVector3D

from . import _algo as A

log = logging.getLogger("ingetrazo.plugins.multiempuje")

PAINT = ("color", "mat", "texture", "opacity")


def t3(v) -> tuple:
    return (float(v.x()), float(v.y()), float(v.z()))


def q3(p) -> QVector3D:
    return QVector3D(float(p[0]), float(p[1]), float(p[2]))


# ------------------------------------------------------------------ captura
class Captura:
    def __init__(self, mesh, caras):
        self.mesh = mesh
        self.caras = self._filtra(mesh, caras)
        self.vid = {}          # id(Vertex) -> int
        self.vobj = {}         # int -> Vertex
        self.fid = {}          # id(Face) -> int
        self.fobj = {}         # int -> Face
        self._construir()

    @staticmethod
    def _filtra(mesh, caras):
        todas = set(map(id, mesh.faces))
        return [f for f in caras if id(f) in todas]

    def _v(self, vx):
        k = id(vx)
        if k not in self.vid:
            i = len(self.vid)
            self.vid[k] = i
            self.vobj[i] = vx
        return self.vid[k]

    def _f(self, fc):
        k = id(fc)
        if k not in self.fid:
            i = len(self.fid)
            self.fid[k] = i
            self.fobj[i] = fc
        return self.fid[k]

    def _construir(self):
        sel_ids = set(map(id, self.caras))
        caras = list(self.caras)
        vistos = set(sel_ids)
        # vecindad: todas las caras que tocan algún vértice de las elegidas
        for fc in self.caras:
            for ring in [fc.loop] + list(fc.hole_loops):
                for vx in ring:
                    for e in vx.edges:
                        for g in e.faces:
                            if id(g) not in vistos:
                                vistos.add(id(g))
                                caras.append(g)
        faces, edges, pos = {}, {}, {}
        for fc in caras:
            i = self._f(fc)
            loop = [self._v(vx) for vx in fc.loop]
            holes = [[self._v(vx) for vx in h] for h in fc.hole_loops]
            n = fc.normal()
            nn = A.norm(t3(n)) or (0.0, 0.0, 1.0)
            try:
                area = float(fc.area())
            except Exception:  # noqa: BLE001
                area = 1.0
            faces[i] = A.FaceIn(i, loop, holes, nn, area, id(fc) in sel_ids)
        for i, vx in self.vobj.items():
            pos[i] = t3(vx.position)
        for i, vx in list(self.vobj.items()):
            for e in vx.edges:
                a, b = self.vid.get(id(e.v0)), self.vid.get(id(e.v1))
                if a is None or b is None or a == b:
                    continue
                k = (a, b) if a < b else (b, a)
                if k in edges:
                    continue
                fs = [self.fid[id(g)] for g in e.faces if id(g) in self.fid]
                edges[k] = A.EdgeIn(k[0], k[1], fs, bool(getattr(e, "soft", False)), bool(getattr(e, "hidden", False)))
        self.mi = A.MeshIn(pos, faces, edges).finish()
        self.sel = [self.fid[id(f)] for f in self.caras]

    def analizar(self, params):
        return A.Analysis(self.mi, self.sel, params)


# ------------------------------------------------------------------ vista previa
def vista_previa(plan, limite=6000):
    try:
        from core.geometry import Face as GFace
    except Exception:  # noqa: BLE001
        return []
    out = []
    caras = plan.faces
    if len(caras) > limite:
        caras = [f for f in caras if f.kind == "top"][:limite]
    for nf in caras:
        try:
            out.append(GFace(vertices=[q3(p) for p in nf.pts], holes=[[q3(p) for p in h] for h in nf.holes]))
        except Exception:  # noqa: BLE001
            pass
    return out


def mover_previa(caras, m):
    """Las caras de la vista previa llevadas al mundo con la matriz ``m`` (las de un grupo o
    componente cerrado, o del abierto si está movido)."""
    try:
        from core.geometry import Face as GFace
    except Exception:  # noqa: BLE001
        return caras
    out = []
    for f in caras:
        try:
            out.append(GFace(vertices=[m.map(p) for p in f.vertices],
                             holes=[[m.map(p) for p in h] for h in (getattr(f, "holes", None) or [])]))
        except Exception:  # noqa: BLE001
            out.append(f)
    return out


def lineas_previa(plan, limite=20000):
    out = []
    for nf in plan.faces:
        if nf.kind not in ("top", "border"):
            continue
        pts = [q3(p) for p in nf.pts]
        for i in range(len(pts)):
            out.append((pts[i], pts[(i + 1) % len(pts)]))
            if len(out) > limite:
                return out
    return out


# ------------------------------------------------------------------ utilidades de malla
def _attrs(fc):
    try:
        return copy.deepcopy(dict(fc.attrs or {}))
    except Exception:  # noqa: BLE001
        return dict(fc.attrs or {})


def _plano(fc):
    n = A.norm(t3(fc.normal()))
    return n, t3(fc.loop[0].position) if fc.loop else (0.0, 0.0, 0.0)


def _coplanares(f1, f2, tol=1e-6):
    n1, p1 = _plano(f1)
    n2, p2 = _plano(f2)
    if n1 is None or n2 is None:
        return 0
    c = A.dot(n1, n2)
    if abs(c) < 0.99999:
        return 0
    if abs(A.dot(A.sub(p2, p1), n1)) > tol:
        return 0
    return 1 if c > 0 else -1


def _dentro(pt, fc):
    """Punto estrictamente dentro del contorno de ``fc`` (en su plano)."""
    n, _p = _plano(fc)
    if n is None:
        return False
    ax = max(range(3), key=lambda i: abs(n[i]))
    i, j = [k for k in range(3) if k != ax]
    poly = [(t3(v.position)[i], t3(v.position)[j]) for v in fc.loop]
    x, y = pt[i], pt[j]
    dentro = False
    m = len(poly)
    for k in range(m):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % m]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xc > x:
                dentro = not dentro
    return dentro


def _base_plano(fc):
    n = A.norm(t3(fc.normal()))
    o = t3(fc.loop[0].position)
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = A.norm(A.cross(n, ref))
    v = A.cross(n, u)
    return o, u, v


def _restar(g, pts):
    """``g`` menos el polígono ``pts`` (coplanario). Lista de (contorno, huecos) en 3D o
    ``None`` si no se puede."""
    try:
        from shapely.geometry import Polygon
    except Exception:  # noqa: BLE001
        return None
    o, u, v = _base_plano(g)

    def a2(p):
        d = A.sub(p, o)
        return (A.dot(d, u), A.dot(d, v))

    def a3(xy):
        return A.add(o, A.add(A.mul(u, xy[0]), A.mul(v, xy[1])))
    try:
        pg = Polygon([a2(t3(x.position)) for x in g.loop], [[a2(t3(x.position)) for x in h] for h in g.hole_loops])
        pb = Polygon([a2(p) for p in pts])
        if not pg.is_valid or not pb.is_valid:
            return None
        r = pg.difference(pb)
    except Exception:  # noqa: BLE001
        return None
    if r.is_empty:
        return []
    geoms = list(getattr(r, "geoms", [r]))
    out = []
    for gm in geoms:
        if gm.geom_type != "Polygon" or gm.area < 1e-12:
            continue
        gm = gm.simplify(0)
        ext = [a3(c) for c in list(gm.exterior.coords)[:-1]]
        holes = [[a3(c) for c in list(h.coords)[:-1]] for h in gm.interiors]
        out.append((ext, holes))
    return out


def _voltear(fc):
    try:
        from core.mesh import turn_face_over
        turn_face_over(fc)
        return
    except Exception:  # noqa: BLE001
        pass
    fc.loop.reverse()
    for h in fc.hole_loops:
        h.reverse()


def _arista(mesh, p, q):
    a, b = mesh.vertex_at(q3(p)), mesh.vertex_at(q3(q))
    if a is None or b is None:
        return None
    return mesh.find_edge(a, b)


# ------------------------------------------------------------------ aplicar
def aplicar(scene, captura: Captura, plan, recortar_huecos=True, unir_coplanares=True, mesh=None):
    """Lleva el plan a ``scene.mesh`` (o a ``mesh``, la de un grupo o componente cerrado).
    Devuelve las caras superiores creadas."""
    propia = mesh is None or mesh is scene.mesh
    mesh = scene.mesh if mesh is None else mesh
    if mesh is not captura.mesh:
        raise RuntimeError("La malla activa ha cambiado")
    fobj = captura.fobj
    quitadas = []
    candidatas = set()             # aristas que pueden quedar sin caras

    def quitar(fc):
        for ring in [fc.loop] + list(fc.hole_loops):
            n = len(ring)
            for i in range(n):
                e = mesh.find_edge(ring[i], ring[(i + 1) % n])
                if e is not None:
                    candidatas.add(e)
        mesh.remove_face(fc)
        quitadas.append(fc)

    for i in plan.remove:
        fc = fobj.get(i)
        if fc is not None and fc in mesh.faces:
            quitar(fc)

    nuevas = []                     # (NewFace, Face)
    for nf in plan.faces:
        try:
            fc = mesh.add_face([q3(p) for p in nf.pts], [[q3(p) for p in h] for h in nf.holes] or None)
        except Exception as e:  # noqa: BLE001
            log.debug("cara no creada: %s", e)
            continue
        if nf.src is not None and nf.src in fobj:
            fc.attrs.clear()
            fc.attrs.update(_attrs(fobj[nf.src]))
        nuevas.append((nf, fc))

    for i in plan.flip:
        fc = fobj.get(i)
        if fc is not None and fc in mesh.faces:
            _voltear(fc)

    # indicadores de arista (suave / oculta) de las originales y suavizado de curvas
    for p, q, soft, hidden in plan.flags:
        e = _arista(mesh, p, q)
        if e is not None:
            e.soft = e.soft or bool(soft)
            e.hidden = e.hidden or bool(hidden)
    for p, q in plan.soft:
        e = _arista(mesh, p, q)
        if e is not None:
            e.soft = True

    empuje = bool(plan.remove)
    if empuje and unir_coplanares:
        _resolver_bordes(mesh, nuevas, fobj, quitar, captura.mi.pos)

    tops = [fc for nf, fc in nuevas if nf.kind == "top" and fc in mesh.faces]
    if empuje and recortar_huecos:
        tops = _recortar(mesh, tops, set(id(fc) for _nf, fc in nuevas), quitar)

    for e in list(candidatas):
        try:
            if e in mesh.edges and not e.faces:
                mesh.remove_edge(e)
        except Exception:  # noqa: BLE001
            pass
    try:
        mesh.prune_orphan_vertices()
    except Exception:  # noqa: BLE001
        pass

    if empuje and unir_coplanares and propia:      # (la fusión trabaja en la malla abierta)
        try:
            from core.history import CoplanarMergeCommand
            semillas = []
            for _nf, fc in nuevas:
                if fc in mesh.faces:
                    semillas.extend(v.position for v in fc.loop)
            if semillas:
                CoplanarMergeCommand(semillas).do(scene)
        except Exception:  # noqa: BLE001
            log.debug("fusión coplanaria no disponible", exc_info=True)
    tops = [fc for fc in tops if fc in mesh.faces]
    try:
        scene.version += 1
    except Exception:  # noqa: BLE001
        pass
    return tops


def _resolver_bordes(mesh, nuevas, fobj, quitar, pos):
    """Bordes coplanarios con la cara vecina: si la prolongan, se funden (dissolve_edge); si
    se meten dentro de ella (empujar hacia dentro de un sólido), la recortan."""
    for nf, fc in nuevas:
        if nf.kind != "border" or fc not in mesh.faces or not nf.edge:
            continue
        pa, pb = pos[nf.edge[0]], pos[nf.edge[1]]
        for gi in nf.neighbours:
            g = fobj.get(gi)
            if g is None or g not in mesh.faces:
                continue
            lado = _coplanares(fc, g)
            if lado == 0:
                continue
            if _dentro(A.centroid(nf.pts), g):
                restos = _restar(g, nf.pts)
                if restos is not None:
                    at = _attrs(g)
                    gn = A.norm(t3(g.normal()))
                    quitar(g)
                    quitar(fc)
                    for loop, huecos in restos:
                        try:
                            ng = mesh.add_face([q3(p) for p in loop], [[q3(p) for p in h] for h in huecos] or None)
                            ng.attrs.update(copy.deepcopy(at))
                            if gn and A.dot(A.norm(t3(ng.normal())) or gn, gn) < 0:
                                _voltear(ng)
                        except Exception:  # noqa: BLE001
                            log.debug("no se pudo recortar la cara vecina", exc_info=True)
                    break
            elif lado > 0:
                e = _arista(mesh, pa, pb)
                if e is not None and len(e.faces) == 2:
                    try:
                        mesh.dissolve_edge(e)
                    except Exception:  # noqa: BLE001
                        pass
                break


def _recortar(mesh, tops, nuevas_ids, quitar):
    """Una cara empujada que llega a la cara opuesta del sólido abre un hueco pasante."""
    salida = []
    for t in tops:
        if t not in mesh.faces:
            continue
        tn = A.norm(t3(t.normal()))
        hecho = False
        puntos = [v.position for v in t.loop]
        claves = sorted(A.pkey(t3(p), 1e-6) for p in puntos)
        for g in list(mesh.faces):
            if g is t or id(g) in nuevas_ids:
                continue
            if _coplanares(t, g) >= 0:
                continue
            if sorted(A.pkey(t3(v.position), 1e-6) for v in g.loop) == claves:
                quitar(t)
                quitar(g)
                hecho = True
                break
        if not hecho:
            try:
                from core.history import find_containing_face
                cands = [g for g in mesh.faces if g is not t and id(g) not in nuevas_ids and _coplanares(t, g) < 0]
                madre = find_containing_face(cands, puntos, exclude=t) if cands else None
            except Exception:  # noqa: BLE001
                madre = None
            if madre is not None:
                quitar(t)
                try:
                    mesh.add_hole(madre, puntos)
                except Exception:  # noqa: BLE001
                    log.debug("no se pudo abrir el hueco", exc_info=True)
                hecho = True
        if not hecho and tn is not None:
            salida.append(t)
    return salida


# ------------------------------------------------------------------ grupo nuevo
def grupo_con(plan, captura: Captura, nombre="Multiempuje", engrosar=False):
    """Un ``Group`` con el resultado (la geometría original no se toca). Al engrosar, el grupo
    lleva además una copia de la base para que sea un sólido cerrado."""
    from core.group import Group
    from core.mesh import Mesh
    m = Mesh()
    fobj = captura.fobj
    extra = base_para_grupo(plan, captura) if engrosar else []
    for nf in list(plan.faces) + extra:
        try:
            fc = m.add_face([q3(p) for p in nf.pts], [[q3(p) for p in h] for h in nf.holes] or None)
        except Exception:  # noqa: BLE001
            continue
        if nf.src is not None and nf.src in fobj:
            fc.attrs.update(_attrs(fobj[nf.src]))
    for p, q, soft, hidden in plan.flags:
        e = _arista(m, p, q)
        if e is not None:
            e.soft = e.soft or bool(soft)
            e.hidden = e.hidden or bool(hidden)
    for p, q in plan.soft:
        e = _arista(m, p, q)
        if e is not None:
            e.soft = True
    return Group(m, name=nombre)


def base_para_grupo(plan, captura: Captura):
    """Caras de la base (copia de las originales) para un engrosado generado en grupo."""
    out = []
    for i in captura.sel:
        fc = captura.fobj[i]
        pts = [t3(v.position) for v in fc.loop]
        holes = [[t3(v.position) for v in h] for h in fc.hole_loops]
        if plan.sign > 0:
            pts = list(reversed(pts))
            holes = [list(reversed(h)) for h in holes]
        out.append(A.NewFace(pts, holes, i, "bottom"))
    return out


# ------------------------------------------------------------------ selección ampliada
def _pintura(fc):
    a = fc.attrs or {}
    return tuple(repr(a.get(k)) for k in PAINT)


def ampliar(mesh, cara, modo):
    if cara is None:
        return []
    if modo == "single":
        return [cara]
    if modo == "surface":
        try:
            return list(mesh.surface_of(cara))
        except Exception:  # noqa: BLE001
            return [cara]
    ref = _pintura(cara)
    vistos = {id(cara)}
    out = [cara]
    pila = [cara]
    while pila:
        c = pila.pop()
        for ring in [c.loop] + list(c.hole_loops):
            n = len(ring)
            for i in range(n):
                e = mesh.find_edge(ring[i], ring[(i + 1) % n])
                if e is None:
                    continue
                for g in e.faces:
                    if id(g) in vistos:
                        continue
                    if modo == "material" and _pintura(g) != ref:
                        continue
                    vistos.add(id(g))
                    out.append(g)
                    pila.append(g)
    return out


def caras_seleccionadas(scene):
    try:
        from core.mesh import Face
    except Exception:  # noqa: BLE001
        return []
    mesh = scene.mesh
    ids = set(map(id, mesh.faces))
    return [e for e in scene.selection if isinstance(e, Face) and id(e) in ids]


def angulo(a, b):
    c = max(-1.0, min(1.0, A.dot(a, b)))
    return math.degrees(math.acos(c))

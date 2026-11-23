# SPDX-License-Identifier: GPL-3.0-or-later
"""Motor geométrico de Multiempuje (Python puro, sin Qt).

Recibe una descripción neutra de la malla (``MeshIn``: posiciones, caras con su contorno y
huecos, aristas y adyacencias) y los parámetros (``Params``), y devuelve un ``Plan`` con las
caras nuevas ya orientadas, las originales que hay que borrar o voltear y las aristas que hay
que suavizar. Quien llama (``_bridge``) lo aplica a la malla de IngeTrazo dentro de un paso de
deshacer.

Idea de cada modo (cómo se mueve cada vértice «v» de las caras seleccionadas):

- conjunto / engrosar / redondeo: las caras de un mismo bloque (unidas por aristas) comparten
  vértices; la dirección «d» de cada vértice cumple d·n = 1 para las normales n de sus caras
  (intersección de los planos desplazados), así cada cara se separa exactamente la distancia.
- vector: todos los vértices en la misma dirección.
- normal: cada cara por separado, según su propia normal.
- extruir: todo el bloque según su normal media (ponderada por áreas).
- seguir: los vértices del borde resbalan por la arista de la cara vecina no seleccionada más
  alineada con la normal; los interiores, como en conjunto.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

EPS = 1e-9
MAX_FACTOR = 6.0

MODES = ("engrosar", "conjunto", "redondeo", "vector", "normal", "extruir", "seguir")
JOINTIVE = ("engrosar", "conjunto", "redondeo", "vector", "extruir", "seguir")


# ------------------------------------------------------------------ vectores (tuplas)
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    ln = length(a)
    if ln < EPS:
        return None
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def slerp(u, v, t):
    """Interpolación esférica entre dos vectores unitarios."""
    c = max(-1.0, min(1.0, dot(u, v)))
    ang = math.acos(c)
    if ang < 1e-6:
        return norm(lerp(u, v, t)) or u
    s = math.sin(ang)
    a = math.sin((1 - t) * ang) / s
    b = math.sin(t * ang) / s
    return norm(add(mul(u, a), mul(v, b))) or u


def newell(pts):
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0, z0 = pts[i]
        x1, y1, z1 = pts[(i + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return (nx, ny, nz)


def centroid(pts):
    n = float(len(pts)) or 1.0
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def pkey(p, q=1e-6):
    return (round(p[0] / q), round(p[1] / q), round(p[2] / q))


def _solve3(m, r):
    """Resuelve m·x = r (3×3) por Cramer; ``None`` si es singular."""
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-10:
        return None
    x = (r[0] * (e * i - f * h) - b * (r[1] * i - f * r[2]) + c * (r[1] * h - e * r[2])) / det
    y = (a * (r[1] * i - f * r[2]) - r[0] * (d * i - f * g) + c * (d * r[2] - r[1] * g)) / det
    z = (a * (e * r[2] - r[1] * h) - b * (d * r[2] - r[1] * g) + r[0] * (d * h - e * g)) / det
    return (x, y, z)


def unique_normals(normals, cos_tol=0.99995):
    out = []
    for n in normals:
        if n is None:
            continue
        if not any(dot(n, u) > cos_tol for u in out):
            out.append(n)
    return out


def exact_direction(normals):
    """Vector d con d·n = 1 para cada normal (mínimos cuadrados). Su longitud es el factor
    que hace que cada plano se separe exactamente la distancia pedida."""
    ns = unique_normals(normals)
    if not ns:
        return None
    if len(ns) == 1:
        return ns[0]
    if len(ns) == 2:
        n1, n2 = ns
        c = dot(n1, n2)
        if c < -0.95:                     # caras casi plegadas una sobre otra
            return n1
        return mul(add(n1, n2), 1.0 / (1.0 + c))
    m = [[0.0] * 3 for _ in range(3)]
    r = [0.0, 0.0, 0.0]
    for n in ns:
        for i in range(3):
            r[i] += n[i]
            for j in range(3):
                m[i][j] += n[i] * n[j]
    d = _solve3(m, r)
    if d is None or length(d) > MAX_FACTOR:
        s = norm(tuple(sum(n[i] for n in ns) for i in range(3)))
        if s is None:
            return ns[0]
        c = max(min(dot(s, n) for n in ns), 1.0 / MAX_FACTOR)
        return mul(s, 1.0 / c)
    return d


def cap(d):
    ln = length(d)
    if ln > MAX_FACTOR:
        return mul(d, MAX_FACTOR / ln)
    return d


# ------------------------------------------------------------------ datos
@dataclass
class FaceIn:
    fid: int
    loop: list
    holes: list
    normal: tuple
    area: float
    selected: bool = False


@dataclass
class EdgeIn:
    a: int
    b: int
    faces: list
    soft: bool = False
    hidden: bool = False


@dataclass
class MeshIn:
    pos: dict
    faces: dict
    edges: dict                         # (min, max) -> EdgeIn
    vfaces: dict = field(default_factory=dict)
    vedges: dict = field(default_factory=dict)

    def finish(self):
        self.vfaces = {}
        self.vedges = {}
        for f in self.faces.values():
            for ring in [f.loop] + list(f.holes):
                for v in ring:
                    self.vfaces.setdefault(v, [])
                    if f.fid not in self.vfaces[v]:
                        self.vfaces[v].append(f.fid)
        for k in self.edges:
            for v in k:
                self.vedges.setdefault(v, []).append(k)
        return self


@dataclass
class Params:
    mode: str = "conjunto"
    offset: float = 0.0
    finishing: str = "push"             # push (borra la original) | thicken (la conserva)
    borders: str = "contour"            # contour | grid | none
    influence: bool = False             # conjunto: las caras vecinas influyen en el borde
    coquad: bool = True                 # normal: triángulos pareados como un cuadrilátero
    angle_round: float = 20.0
    segment_round: int = 6
    vector: tuple | None = None
    vector_projected: bool = False
    extrude_flat: bool = False
    taper_on: bool = False
    taper: float = 1.0                  # 0.8 = la cara superior al 80 %
    molding_on: bool = False
    molding_angle: float = 0.0          # grados
    random_on: bool = False
    rmin: float = 0.5
    rmax: float = 2.0
    seed: int = 2345
    target_plane: tuple | None = None   # (punto, normal)
    soften_angle: float = 30.0


@dataclass
class NewFace:
    pts: list
    holes: list
    src: int | None
    kind: str                           # top | bottom | border | round | cap
    edge: tuple | None = None           # arista original (vid, vid) de un borde
    neighbours: list = field(default_factory=list)   # caras no seleccionadas de esa arista


@dataclass
class Plan:
    faces: list = field(default_factory=list)
    remove: list = field(default_factory=list)
    flip: list = field(default_factory=list)
    soft: list = field(default_factory=list)          # [(p, q)] aristas a suavizar
    flags: list = field(default_factory=list)         # [(p, q, soft, hidden)] copiadas de la original
    sign: float = 1.0
    message: str = ""

    @property
    def ok(self):
        return bool(self.faces)


# ------------------------------------------------------------------ análisis
class Analysis:
    """Lo que no depende de la distancia: bloques, vértices y sus direcciones.
    Se calcula una vez al empezar a arrastrar y se reutiliza en cada fotograma."""

    def __init__(self, mesh: MeshIn, sel: list, params: Params):
        self.m = mesh
        self.p = params
        self.sel = [f for f in sel if f in mesh.faces]
        self.selset = set(self.sel)
        self.sign_hint = 1.0 if params.offset >= 0 else -1.0
        self._blocks()
        self._clusters()
        self._directions()

    # ---- bloques
    def _edge_key(self, a, b):
        return (a, b) if a < b else (b, a)

    def face_edges(self, fid):
        f = self.m.faces[fid]
        out = []
        for ring in [f.loop] + list(f.holes):
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                if a != b:
                    out.append((a, b))
        return out

    def _blocks(self):
        m, p = self.m, self.p
        self.block_of = {}
        blocks = []
        if p.mode == "normal":
            used = set()
            for fid in self.sel:
                if fid in used:
                    continue
                blk = [fid]
                used.add(fid)
                f = m.faces[fid]
                if p.coquad and len(f.loop) == 3 and not f.holes:
                    for a, b in self.face_edges(fid):
                        e = m.edges.get(self._edge_key(a, b))
                        if not e:
                            continue
                        for g in e.faces:
                            if g == fid or g in used or g not in self.selset:
                                continue
                            gf = m.faces[g]
                            if len(gf.loop) == 3 and not gf.holes and dot(gf.normal, f.normal) > math.cos(math.radians(15)):
                                blk.append(g)
                                used.add(g)
                                break
                        if len(blk) == 2:
                            break
                blocks.append(blk)
        else:
            seen = set()
            for fid in self.sel:
                if fid in seen:
                    continue
                stack, blk = [fid], []
                seen.add(fid)
                while stack:
                    c = stack.pop()
                    blk.append(c)
                    for a, b in self.face_edges(c):
                        e = m.edges.get(self._edge_key(a, b))
                        if not e:
                            continue
                        for g in e.faces:
                            if g in self.selset and g not in seen:
                                seen.add(g)
                                stack.append(g)
                blocks.append(blk)
        self.blocks = blocks
        for i, blk in enumerate(blocks):
            for fid in blk:
                self.block_of[fid] = i

    # ---- aristas redondeadas y agrupación alrededor de cada vértice
    def face_centroid(self, fid):
        f = self.m.faces[fid]
        return centroid([self.m.pos[v] for v in f.loop])

    def is_rounded(self, ek):
        """Arista convexa (respecto al lado al que se empuja) entre dos caras del mismo bloque
        con un ángulo mayor que el mínimo de redondeo."""
        if self.p.mode != "redondeo":
            return False
        e = self.m.edges.get(ek)
        if not e:
            return False
        fs = [g for g in e.faces if g in self.selset]
        if len(fs) != 2 or self.block_of[fs[0]] != self.block_of[fs[1]]:
            return False
        n1, n2 = self.m.faces[fs[0]].normal, self.m.faces[fs[1]].normal
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot(n1, n2)))))
        if ang < max(self.p.angle_round, 0.5):
            return False
        mid = lerp(self.m.pos[ek[0]], self.m.pos[ek[1]], 0.5)
        c2 = self.face_centroid(fs[1])
        return self.sign_hint * dot(sub(c2, mid), n1) < 0

    def _clusters(self):
        """pv[(fid, vid)] -> clave del vértice desplazado. Fuera de «redondeo» todas las caras
        de un bloque comparten el vértice; en «redondeo» se separan en las aristas redondeadas."""
        self.pv_of = {}
        self.pv_faces = {}
        self.rounded = set()
        if self.p.mode == "redondeo":
            for fid in self.sel:
                for a, b in self.face_edges(fid):
                    ek = self._edge_key(a, b)
                    if ek not in self.rounded and self.is_rounded(ek):
                        self.rounded.add(ek)
        for bi, blk in enumerate(self.blocks):
            bset = set(blk)
            verts = {}
            for fid in blk:
                for ring in [self.m.faces[fid].loop] + list(self.m.faces[fid].holes):
                    for v in ring:
                        verts.setdefault(v, [])
                        if fid not in verts[v]:
                            verts[v].append(fid)
            for v, fids in verts.items():
                if not self.rounded:
                    key = (bi, v, 0)
                    for fid in fids:
                        self.pv_of[(fid, v)] = key
                    self.pv_faces[key] = list(fids)
                    continue
                # unión de caras por aristas NO redondeadas que pasan por v
                parent = {f: f for f in fids}

                def find(x):
                    while parent[x] != x:
                        parent[x] = parent[parent[x]]
                        x = parent[x]
                    return x
                for ek in self.m.vedges.get(v, []):
                    e = self.m.edges[ek]
                    fs = [g for g in e.faces if g in bset and g in parent]
                    if len(fs) >= 2 and ek not in self.rounded:
                        for g in fs[1:]:
                            parent[find(g)] = find(fs[0])
                roots = {}
                for fid in fids:
                    r = find(fid)
                    roots.setdefault(r, len(roots))
                    key = (bi, v, roots[r])
                    self.pv_of[(fid, v)] = key
                    self.pv_faces.setdefault(key, []).append(fid)

    # ---- direcciones
    def block_normal(self, bi):
        sx = sy = sz = 0.0
        for fid in self.blocks[bi]:
            f = self.m.faces[fid]
            sx += f.normal[0] * f.area
            sy += f.normal[1] * f.area
            sz += f.normal[2] * f.area
        return norm((sx, sy, sz))

    def block_centroid(self, bi):
        sx = sy = sz = sa = 0.0
        for fid in self.blocks[bi]:
            f = self.m.faces[fid]
            c = self.face_centroid(fid)
            a = max(f.area, 1e-12)
            sx += c[0] * a
            sy += c[1] * a
            sz += c[2] * a
            sa += a
        return (sx / sa, sy / sa, sz / sa)

    def at_border(self, key):
        """El vértice está en el contorno de su bloque (alguna de sus aristas solo tiene una
        cara del bloque)."""
        bi, v, _c = key
        bset = set(self.blocks[bi])
        for ek in self.m.vedges.get(v, []):
            e = self.m.edges[ek]
            n_in = sum(1 for g in e.faces if g in bset)
            if n_in == 1:
                return True
        return False

    def main_normal(self, key):
        fids = self.pv_faces[key]
        best = max(fids, key=lambda f: self.m.faces[f].area)
        return self.m.faces[best].normal

    def _dir_joint(self, key, influence=False):
        normals = [self.m.faces[f].normal for f in self.pv_faces[key]]
        if influence and self.at_border(key):
            n0 = self.main_normal(key)
            _bi, v, _c = key
            for g in self.m.vfaces.get(v, []):
                if g in self.selset:
                    continue
                n = self.m.faces[g].normal
                normals.append(n if dot(n0, n) > 0 else mul(n, -1.0))
        d = exact_direction(normals)
        return cap(d) if d else self.main_normal(key)

    def _dir_follow(self, key):
        bi, v, _c = key
        if self.at_border(key):
            bset = set(self.blocks[bi])
            n0 = self.main_normal(key)
            best = None
            for ek in self.m.vedges.get(v, []):
                e = self.m.edges[ek]
                if not e.faces or any(g in bset for g in e.faces):
                    continue
                other = ek[1] if ek[0] == v else ek[0]
                u = norm(sub(self.m.pos[other], self.m.pos[v]))
                if u is None:
                    continue
                ps = abs(dot(n0, u))
                if best is None or ps > best[0]:
                    best = (ps, u)
            if best is not None and best[0] > 0.05:
                u = best[1]
                return cap(mul(u, 1.0 / dot(u, n0)))
        return self._dir_joint(key)

    def _directions(self):
        p = self.p
        self.dir = {}
        self.block_vec = {}
        for bi in range(len(self.blocks)):
            if p.mode == "vector":
                vec = norm(p.vector) if p.vector else None
                self.block_vec[bi] = vec or self.block_normal(bi) or (0.0, 0.0, 1.0)
            elif p.mode == "extruir":
                self.block_vec[bi] = self.block_normal(bi) or (0.0, 0.0, 1.0)
        for key in self.pv_faces:
            bi = key[0]
            if p.mode in ("vector", "extruir"):
                self.dir[key] = self.block_vec[bi]
            elif p.mode == "seguir":
                self.dir[key] = self._dir_follow(key)
            elif p.mode == "normal":
                self.dir[key] = self._dir_joint(key)
            else:
                self.dir[key] = self._dir_joint(key, influence=(p.influence and p.mode == "conjunto"))
        # aleatorio (por bloque)
        self.rand = {}
        if p.random_on:
            rng = random.Random(int(p.seed))
            lo, hi = float(p.rmin), float(p.rmax)
            for bi in range(len(self.blocks)):
                r = rng.random()
                self.rand[bi] = lo * (1 - r) + hi * r

    # ---- posiciones finales
    def targets(self, offset):
        p, m = self.p, self.m
        tgt = {}
        plane = p.target_plane
        for key, d in self.dir.items():
            bi, v, _c = key
            o = m.pos[v]
            off = offset * self.rand.get(bi, 1.0)
            if plane is not None:
                pp, pn = plane
                den = dot(d, pn)
                if abs(den) > 1e-9:
                    t = dot(sub(pp, o), pn) / den
                    tgt[key] = add(o, mul(d, t))
                    continue
            tgt[key] = add(o, mul(d, off))
        # caras superiores planas (vector proyectado / extruir aplanado)
        if plane is None and ((p.mode == "vector" and p.vector_projected) or (p.mode == "extruir" and p.extrude_flat)):
            for bi in range(len(self.blocks)):
                vec = self.block_vec[bi]
                c = add(self.block_centroid(bi), mul(vec, offset))
                for key in self.dir:
                    if key[0] != bi:
                        continue
                    o = m.pos[key[1]]
                    tgt[key] = add(o, mul(vec, dot(sub(c, o), vec)))
        # rematado
        fac = float(p.taper)
        if p.taper_on and abs(fac - 1.0) > 1e-9 and p.mode in ("extruir", "vector", "normal"):
            if p.mode in ("extruir", "vector"):
                for bi in range(len(self.blocks)):
                    c = add(self.block_centroid(bi), mul(self.block_vec[bi], offset))
                    for key in self.dir:
                        if key[0] == bi:
                            tgt[key] = add(c, mul(sub(tgt[key], c), fac))
            else:
                for bi, blk in enumerate(self.blocks):
                    pts = [m.pos[v] for fid in blk for v in m.faces[fid].loop]
                    c0 = centroid(pts)
                    keys = [k for k in self.dir if k[0] == bi]
                    if not keys:
                        continue
                    d = self.dir[keys[0]]
                    c = add(c0, mul(d, offset * self.rand.get(bi, 1.0)))
                    for key in keys:
                        tgt[key] = add(c, mul(sub(tgt[key], c), fac))
        # desmoldeo
        if p.molding_on and abs(p.molding_angle) > 1e-6 and p.mode in ("conjunto", "extruir", "vector", "normal"):
            self._molding(tgt, offset)
        return tgt

    def _molding(self, tgt, offset):
        m = self.m
        shift = abs(offset) * math.tan(math.radians(max(-80.0, min(80.0, self.p.molding_angle))))
        outs = {}
        for bi, blk in enumerate(self.blocks):
            bset = set(blk)
            for fid in blk:
                f = m.faces[fid]
                rings = [(f.loop, False)] + [(h, True) for h in f.holes]
                for ring, is_hole in rings:
                    n = len(ring)
                    rc = centroid([m.pos[v] for v in ring])
                    for i in range(n):
                        a, b = ring[i], ring[(i + 1) % n]
                        e = m.edges.get(self._edge_key(a, b))
                        if not e or sum(1 for g in e.faces if g in bset) != 1:
                            continue
                        pa, pb = m.pos[a], m.pos[b]
                        o = norm(cross(sub(pb, pa), f.normal))
                        if o is None:
                            continue
                        mid = lerp(pa, pb, 0.5)
                        inside = dot(sub(rc, mid), o) > 0
                        if inside != is_hole:      # contorno: hacia fuera; hueco: hacia el hueco
                            o = mul(o, -1.0)
                        for v in (a, b):
                            outs.setdefault(self.pv_of[(fid, v)], []).append(o)
        for key, os_ in outs.items():
            s = norm(tuple(sum(o[i] for o in os_) for i in range(3)))
            if s is None:
                continue
            c = max(min(dot(s, o) for o in os_), 0.2)
            tgt[key] = add(tgt[key], mul(s, shift / c))


# ------------------------------------------------------------------ construcción del plan
def _orient(pts, want):
    n = newell(pts)
    if dot(n, want) < 0:
        return list(reversed(pts)), True
    return list(pts), False


def _planar(pts, tol):
    if len(pts) <= 3:
        return True
    n = norm(newell(pts))
    if n is None:
        return False
    c = centroid(pts)
    return all(abs(dot(sub(q, c), n)) <= tol for q in pts)


def _area(pts):
    return length(newell(pts)) * 0.5


def build_plan(an: Analysis, offset: float, for_preview: bool = False) -> Plan:
    m, p = an.m, an.p
    plan = Plan()
    if not an.sel:
        plan.message = "no-faces"
        return plan
    tgt = an.targets(offset)
    if p.target_plane is not None:
        # sentido efectivo: el de la mayoría de los vértices
        acc = 0.0
        for key, t in tgt.items():
            acc += dot(sub(t, m.pos[key[1]]), an.main_normal(key))
        s = 1.0 if acc >= 0 else -1.0
    else:
        s = 1.0 if offset >= 0 else -1.0
    plan.sign = s
    thick = p.finishing == "thicken"
    size = max((length(sub(m.pos[a], m.pos[b])) for fid in an.sel for a, b in an.face_edges(fid)), default=1.0)
    tol = max(1e-7, size * 1e-5)
    moved = any(length(sub(t, m.pos[k[1]])) > tol for k, t in tgt.items())
    if not moved:
        plan.message = "zero"
        return plan

    def T(fid, v):
        return tgt[an.pv_of[(fid, v)]]

    def P(v):
        return m.pos[v]

    top_sign = s if thick else 1.0
    side_sign = 1.0 if thick else s

    # ---- caras superiores
    for fid in an.sel:
        f = m.faces[fid]
        pts = [T(fid, v) for v in f.loop]
        holes = [[T(fid, v) for v in h] for h in f.holes]
        want = mul(f.normal, top_sign)
        if _area(pts) < tol * tol:
            continue
        pts, rev = _orient(pts, want)
        holes = [list(reversed(h)) if rev else list(h) for h in holes]
        if not holes and not _planar(pts, tol * 10) and len(pts) > 3:
            for tri in _split_nonplanar(pts):
                plan.faces.append(NewFace(tri, [], fid, "top"))
            for i in range(1, len(pts) - 2):
                plan.soft.append((pts[0], pts[i + 1]))
        else:
            plan.faces.append(NewFace(pts, holes, fid, "top"))
        # aristas: se copian los indicadores de la original
        for a, b in an.face_edges(fid):
            e = m.edges.get(an._edge_key(a, b))
            if e and (e.soft or e.hidden):
                plan.flags.append((T(fid, a), T(fid, b), e.soft, e.hidden))
        if thick and not for_preview:
            if s > 0:
                plan.flip.append(fid)
        elif not thick:
            plan.remove.append(fid)

    # ---- bordes
    done = set()
    if p.borders != "none":
        for fid in an.sel:
            f = m.faces[fid]
            bset = set(an.blocks[an.block_of[fid]])
            for ring in [f.loop] + list(f.holes):
                n = len(ring)
                rc = centroid([P(v) for v in ring])
                is_hole = ring is not f.loop
                for i in range(n):
                    a, b = ring[i], ring[(i + 1) % n]
                    ek = an._edge_key(a, b)
                    e = m.edges.get(ek)
                    if ek in an.rounded:
                        continue
                    n_in = sum(1 for g in e.faces if g in bset) if e else 1
                    boundary = n_in <= 1
                    if p.borders == "contour" and not boundary:
                        continue
                    ta, tb = T(fid, a), T(fid, b)
                    quad = [P(a), P(b), tb, ta]
                    k = frozenset(pkey(q) for q in quad)
                    if k in done:
                        continue
                    done.add(k)
                    clean = _dedupe(quad, tol)
                    if len(clean) < 3 or _area(clean) < tol * tol:
                        continue
                    o = norm(cross(sub(P(b), P(a)), f.normal)) or (0.0, 0.0, 1.0)
                    mid = lerp(P(a), P(b), 0.5)
                    inside = dot(sub(rc, mid), o) > 0
                    if inside != is_hole:
                        o = mul(o, -1.0)
                    clean, _r = _orient(clean, mul(o, side_sign))
                    neigh = [g for g in (e.faces if e else []) if g not in an.selset]
                    src = _border_source(m, neigh, clean, fid)
                    plan.faces.append(NewFace(clean, [], src, "border", (a, b), neigh))

    # ---- redondeos
    if an.rounded:
        _rounding(an, tgt, plan, s, thick, tol)

    # ---- suavizado de los bordes casi alineados
    _soften_borders(plan, p.soften_angle)
    return plan


def _split_nonplanar(pts):
    if len(pts) == 4:
        d02 = length(sub(pts[0], pts[2]))
        d13 = length(sub(pts[1], pts[3]))
        if d02 <= d13:
            return [[pts[0], pts[1], pts[2]], [pts[0], pts[2], pts[3]]]
        return [[pts[1], pts[2], pts[3]], [pts[1], pts[3], pts[0]]]
    return [[pts[0], pts[i], pts[i + 1]] for i in range(1, len(pts) - 1)]


def _dedupe(pts, tol):
    out = []
    for q in pts:
        if not out or length(sub(q, out[-1])) > tol:
            out.append(q)
    if len(out) > 1 and length(sub(out[0], out[-1])) <= tol:
        out.pop()
    return out


def _border_source(m, neigh, pts, fid):
    n = norm(newell(pts))
    if n is None:
        return fid
    for g in neigh:
        gn = m.faces[g].normal
        if abs(dot(gn, n)) > 0.9999:
            g0 = m.pos[m.faces[g].loop[0]]
            if abs(dot(sub(pts[0], g0), n)) < 1e-6:
                return g
    return fid


def _rounding(an, tgt, plan, s, thick, tol):
    m, p = an.m, an.p
    strip_sign = 1.0 if thick else s
    nseg90 = max(1, int(p.segment_round))
    arcs_at = {}                                  # vid -> [(keyA, keyB, [puntos])]

    def arc(v, ka, kb):
        o = m.pos[v]
        ra, rb = sub(tgt[ka], o), sub(tgt[kb], o)
        la, lb = length(ra), length(rb)
        ua, ub = norm(ra), norm(rb)
        if ua is None or ub is None:
            return [tgt[ka], tgt[kb]]
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot(ua, ub)))))
        n = max(1, int(round(nseg90 * ang / 90.0)))
        return [add(o, mul(slerp(ua, ub, i / n), la + (lb - la) * i / n)) for i in range(n + 1)]

    for ek in sorted(an.rounded):
        e = m.edges[ek]
        f1, f2 = [g for g in e.faces if g in an.selset][:2]
        a, b = ek
        ka1, ka2 = an.pv_of[(f1, a)], an.pv_of[(f2, a)]
        kb1, kb2 = an.pv_of[(f1, b)], an.pv_of[(f2, b)]
        arc_a = arc(a, ka1, ka2)
        arc_b = arc(b, kb1, kb2)
        arcs_at.setdefault(a, []).append((ka1, ka2, arc_a))
        arcs_at.setdefault(b, []).append((kb1, kb2, arc_b))
        n = min(len(arc_a), len(arc_b)) - 1
        if len(arc_a) != len(arc_b):
            arc_b = [arc_b[round(i * (len(arc_b) - 1) / max(1, len(arc_a) - 1))] for i in range(len(arc_a))]
            n = len(arc_a) - 1
        for i in range(n):
            quad = [arc_a[i], arc_b[i], arc_b[i + 1], arc_a[i + 1]]
            q = _dedupe(quad, tol)
            if len(q) < 3:
                continue
            mid = centroid(q)
            emid = lerp(m.pos[a], m.pos[b], 0.5)
            want = mul(norm(sub(mid, emid)) or (0.0, 0.0, 1.0), strip_sign)
            q, _r = _orient(q, want)
            plan.faces.append(NewFace(q, [], f1, "round"))
            if i > 0:
                plan.soft.append((arc_a[i], arc_b[i]))
        plan.soft.append((arc_a[0], arc_b[0]))
        plan.soft.append((arc_a[-1], arc_b[-1]))

    # esquinas: varias aristas redondeadas que forman un ciclo alrededor del vértice
    for v, arcs in arcs_at.items():
        o = m.pos[v]
        nodes = {}
        for ka, kb, pts in arcs:
            nodes.setdefault(ka, []).append((kb, pts))
            nodes.setdefault(kb, []).append((ka, list(reversed(pts))))
        if len(nodes) >= 3 and all(len(x) == 2 for x in nodes.values()):
            start = next(iter(nodes))
            ring, cur, prev = [], start, None
            for _ in range(len(nodes)):
                nxt = [x for x in nodes[cur] if x[0] != prev] if prev is not None else nodes[cur][:1]
                if not nxt:
                    break
                k2, pts = nxt[0]
                ring.extend(pts[:-1])
                prev, cur = cur, k2
                if cur == start:
                    break
            if len(ring) >= 3:
                dirs = [norm(sub(q, o)) for q in ring]
                dirs = [d for d in dirs if d]
                cdir = norm(tuple(sum(d[i] for d in dirs) for i in range(3)))
                if cdir:
                    rl = sum(length(sub(q, o)) for q in ring) / len(ring)
                    c = add(o, mul(cdir, rl))
                    for i in range(len(ring)):
                        tri = [c, ring[i], ring[(i + 1) % len(ring)]]
                        want = mul(norm(sub(centroid(tri), o)) or cdir, strip_sign)
                        tri, _r = _orient(tri, want)
                        if _area(tri) > tol * tol:
                            plan.faces.append(NewFace(tri, [], None, "round"))
                        plan.soft.append((c, ring[i]))
                        plan.soft.append((ring[i], ring[(i + 1) % len(ring)]))
        # tapas en el contorno: donde termina una arista redondeada en el borde del bloque
        for ka, kb, pts in arcs:
            if an.p.borders == "none":
                continue
            if an.at_border(ka) and an.at_border(kb) and not (len(nodes) >= 3 and all(len(x) == 2 for x in nodes.values())):
                fan = [o] + pts
                fan = _dedupe(fan, tol)
                if len(fan) < 3:
                    continue
                n_ = norm(newell(fan))
                if n_ is None:
                    continue
                # misma orientación que el borde vecino (hacia fuera del sólido)
                want = None
                for nf in plan.faces:
                    if nf.kind == "border" and any(length(sub(q, o)) < tol for q in nf.pts):
                        want = norm(newell(nf.pts))
                        break
                if want is None:
                    continue
                if _planar(fan, tol * 10):
                    fan, _r = _orient(fan, want)
                    plan.faces.append(NewFace(fan, [], None, "cap"))
                else:
                    for i in range(1, len(fan) - 1):
                        tri, _r = _orient([fan[0], fan[i], fan[i + 1]], want)
                        plan.faces.append(NewFace(tri, [], None, "cap"))
                        if i > 1:
                            plan.soft.append((fan[0], fan[i]))


def _soften_borders(plan, angle):
    """Suaviza la arista entre dos bordes vecinos casi alineados (superficies curvas)."""
    if angle <= 0:
        return
    lim = math.cos(math.radians(angle))
    by_edge = {}
    for i, nf in enumerate(plan.faces):
        if nf.kind not in ("border", "cap"):
            continue
        pts = nf.pts
        for j in range(len(pts)):
            a, b = pts[j], pts[(j + 1) % len(pts)]
            k = frozenset((pkey(a), pkey(b)))
            by_edge.setdefault(k, []).append((i, a, b))
    for k, lst in by_edge.items():
        if len(lst) != 2:
            continue
        (i, a, b), (j, _a, _b) = lst
        n1 = norm(newell(plan.faces[i].pts))
        n2 = norm(newell(plan.faces[j].pts))
        if n1 and n2 and dot(n1, n2) > lim and dot(n1, n2) < 0.99999:
            plan.soft.append((a, b))

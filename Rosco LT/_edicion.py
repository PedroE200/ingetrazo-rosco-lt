# SPDX-License-Identifier: GPL-3.0-or-later
"""Qué partes lleva esta edición de Rosco.

La completa no deja nada fuera (``FUERA`` vacío). El empaquetador
(``herramientas\\empaquetar.ps1`` de Publicar-Pe) rellena ``FUERA`` con las
partes de la edición que se publica y quita del paquete sus archivos
(``PARTES``). El código pregunta ``con("parte")`` antes de usar una parte, así
que funciona igual con sus archivos o sin ellos.

Una parte = una opción que se puede dar o quitar. Además de sus archivos, una
parte puede tener:

- ``MODOS``: opciones del subrosco de un botón, ``(botón, modo)``;
- ``CLAVES``: botones o huecos propios (lo guardado en un hueco con una
  clave de una parte que falta se ignora, sin error);
- ``OPCIONES``: casillas de Opciones (``seleccionar/<clave>``): sin la parte,
  la casilla no sale y la opción vale «no».
- ``FRASES``: trozos de los textos de ayuda, nombres y avisos que hablan de
  la parte. Sin ella se quitan (o se cambian por su sustituto) con
  ``sin_partes``; ``limpiar`` lo hace en una tabla entera de textos (y quita
  sus entradas con claves o modos de partes ausentes). Así ningún texto
  enseña nada de lo que la edición no lleva.
- ``MENCIONES``: palabras que delatan la parte en un texto (para las pruebas
  del empaquetado: ``mencion``).
"""
from __future__ import annotations

FUERA: set = {"alinear_vista", "anotar", "arbol_borrar", "estirar", "modo2d", "texturas", "voz_ordenes"}                     # el empaquetador lo rellena

# Parte → archivos o carpetas (relativos a la carpeta de la extensión).
PARTES: dict = {
    "multiempuje": ["_multiempuje"],
    "anotar": ["_anotar.py"],
    "estirar": ["_estirar.py"],
    "arbol_borrar": ["_arbol_borrar.py"],
    "capas_panel": ["_capas_panel.py"],
    "aviso_capa": ["_aviso.py"],
    "pasos": ["_pasos.py"],
    "sostener": ["_sostener.py"],
    "triple_derecho": [],
    "doble_bloq": [],
    "previa": ["_previa.py", "sonidos"],
    "sel_rapida": ["_sel_rapida.py"],
    "panel_ayuda": ["_panel_ayuda.py", "_anima.py"],
    "anillos2": ["_anillos2.py"],
    "texturas": [],
    "modo2d": [],
    "alinear_vista": [],
    "navegador_chincheta": [],
    "voz_ordenes": [],
    "contorno_3d": [],
    "ordenes_nativas": [],
}

# Parte → opciones del subrosco de un botón.
MODOS: dict = {
    "anotar": [("linea", "anotar"), ("linea", "borrar anotaciones")],
    "estirar": [("move", "estirar"), ("move", "estirar ventana"), ("move", "prolongar a plano")],
    "arbol_borrar": [("seleccionar", "dentro")],
    "contorno_3d": [("linea", "contorno 3D")],
    "ordenes_nativas": [("empujar", "sígueme"), ("empujar", "puente"), ("medir", "ruta"),
                        ("medir", "transportador"), ("linea", "mano alzada"),
                        ("texto", "etiqueta"), ("texto", "texto 3D")],
}

# Parte → botones o huecos propios.
CLAVES: dict = {
    "sel_rapida": ["sel_rapida"],
    "texturas": ["texturas"],
    "modo2d": ["modo2d"],
    "alinear_vista": ["alinear_vista"],
    "capas_panel": ["capa_activa", "capa_aislar", "capa_bloq"],
    "estirar": ["estirar ventana", "prolongar a plano"],
    "anotar": ["anotar", "borrar anotaciones"],
}

# Parte → casillas de Opciones.
OPCIONES: dict = {
    "sostener": ["derecho_sostenido"],
    "triple_derecho": ["triple_derecho"],
    "doble_bloq": ["doble_bloq"],
    "previa": ["vista_previa"],
    "voz_ordenes": ["pulsacion_voz"],
}

# Parte → [(trozo de texto, sustituto)]. El trozo se busca tal cual (en
# español, antes de traducir); el texto que queda tiene su propia traducción.
FRASES: dict = {
    "triple_derecho": [("<b>Triple clic derecho</b> rápido: apaga Rosco; con Rosco apagado, lo enciende.", "")],
    "voz_ordenes": [(" Sobre un botón, además escucha una orden de voz.", "")],
    "doble_bloq": [(" Doble toque rápido en Bloq Mayús: enciende o apaga Rosco.", ""),
                   ("; dos toques en Bloq Mayús lo encienden o lo apagan", "")],
    "texturas": [('Los ojos (la rueda y el historial se abren al pasar el ratón; los demás, con un clic)',
                  'Los ojos (la rueda, el historial y la ayuda rápida se abren al pasar el ratón; los demás, con un clic)')],
    "estirar": [("Desplazar: mover · copia · alinear · estirar · vértices",
                 "Desplazar: mover · copia · alinear · vértices")],
    "ordenes_nativas": [("Texto: texto · etiqueta · texto 3D · notas", "Texto: texto · notas")],
}

# Parte → palabras (expresiones regulares, en minúsculas) que la delatan.
MENCIONES: dict = {
    "ordenes_nativas": [r"sígueme", r"\bpuente\b", r"\bruta\b", r"transportador", r"texto 3d", r"mano alzada"],
    "contorno_3d": [r"contorno 3d"],
    "estirar": [r"\bestirar\b", r"\bestirad", r"prolongar a plano", r"\bprolongad"],
    "anotar": [r"\banota"],
    "multiempuje": [r"multiempuje"],
    "pasos": [r"últimos .*pasos", r"deshacer hasta", r"rehacer hasta", r"\d+ pasos"],
    "sel_rapida": [r"selección rápida"],
    "modo2d": [r"modo 2d"],
    "alinear_vista": [r"alinear (la )?vista"],
    "triple_derecho": [r"triple clic"],
    "doble_bloq": [r"bloq may"],
    "sostener": [r"clic derecho sostenido", r"sostener hasta"],
    "previa": [r"vista previa", r"subrosco, pequeño"],
    "texturas": [r"biblioteca de texturas", r"\btexturas\b"],
    "voz_ordenes": [r"órdenes por voz", r"orden de voz"],
    "arbol_borrar": [r"seleccionar dentro de grupos", r"borrado dentro del grupo", r"rueda: nivel"],
    "capas_panel": [r"cuentagotas", r"aislar capa", r"mini panel"],
    "navegador_chincheta": [r"automático", r"⟳ actualizar"],
}


def con(parte: str) -> bool:
    """Si esta edición lleva ``parte``."""
    return parte not in FUERA


def _de(tabla: dict, cosa) -> str | None:
    return next((parte for parte, cosas in tabla.items() if cosa in cosas), None)


def modo(clave, m) -> bool:
    """Si el modo ``m`` del botón ``clave`` está en esta edición."""
    parte = _de(MODOS, (clave, m))
    return parte is None or con(parte)


def modos(clave, lista):
    """``lista`` (los modos de ``clave``) sin los de las partes que faltan,
    del mismo tipo (tupla o lista)."""
    if lista is None:
        return None
    return type(lista)(m for m in lista if modo(clave, m))


def clave(k) -> bool:
    """Si el botón o hueco ``k`` está en esta edición."""
    parte = _de(CLAVES, k)
    return parte is None or con(parte)


def opcion(k) -> bool:
    """Si la casilla de Opciones ``k`` está en esta edición."""
    parte = _de(OPCIONES, k)
    return parte is None or con(parte)


def opciones(lista):
    """Las casillas ``((clave, texto), …)`` que están en esta edición."""
    return tuple(o for o in lista if opcion(o[0]))


def sin_partes(texto):
    """``texto`` sin los trozos de las partes que faltan (o con su sustituto)."""
    if not isinstance(texto, str) or not FUERA:
        return texto
    for parte in FUERA:
        for trozo, sustituto in FRASES.get(parte, ()):
            if trozo in texto:
                texto = texto.replace(trozo, sustituto)
    return texto


def _dentro(k) -> bool:
    if isinstance(k, tuple) and len(k) == 2 and all(isinstance(x, str) for x in k):
        return modo(*k)
    return not isinstance(k, str) or clave(k)


def limpiar(tabla):
    """Una tabla de textos (dict, tupla o lista, anidados) para esta edición:
    sin las entradas cuya clave o modo es de una parte que falta y con los
    textos pasados por ``sin_partes``. Las filas que se quedan sin texto
    (una cadena vacía) se quitan."""
    if not FUERA:
        return tabla
    if isinstance(tabla, str):
        return sin_partes(tabla)
    if isinstance(tabla, dict):
        return {k: limpiar(v) for k, v in tabla.items() if _dentro(k)}
    if isinstance(tabla, (tuple, list)):
        salida = []
        solo_textos = all(isinstance(x, str) for x in tabla)
        for x in tabla:
            y = limpiar(x)
            if solo_textos and x and not y:
                continue                     # una frase entera de una parte que falta
            if isinstance(x, (tuple, list)) and any(isinstance(e, str) and e and not f
                                                    for e, f in zip(x, y)):
                continue                     # una fila cuyo texto era de una parte que falta
            salida.append(y)
        return type(tabla)(salida)
    return tabla


def mencion(texto: str) -> str | None:
    """La parte que falta de la que habla ``texto`` (en español), o None."""
    import re
    t = (texto or "").lower()
    for parte in FUERA:
        if any(re.search(rx, t) for rx in MENCIONES.get(parte, ())):
            return parte
    return None


def archivos_fuera() -> list:
    """Los archivos y carpetas de las partes que faltan (para el empaquetador)."""
    return sorted({a for parte in FUERA for a in PARTES.get(parte, ())})

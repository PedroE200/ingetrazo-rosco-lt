# SPDX-License-Identifier: GPL-3.0-or-later
"""Textos de Multiempuje. Las cadenas base están en español; con IngeTrazo en inglés se
traducen con este diccionario (lo que no esté, sale en español)."""
from __future__ import annotations

_EN = {
    "Multiempuje": "Multi Push",
    "Modo": "Mode",
    "Empuje": "Push",
    "Opciones del modo": "Mode options",
    "Variaciones": "Variations",
    "Uso": "Usage",
    "Engrosar": "Thicken",
    "Conjunto": "Joint",
    "Redondeo": "Round",
    "Vector": "Vector",
    "Normal": "Normal",
    "Extruir": "Extrude",
    "Seguir": "Follow",
    "Distancia:": "Distance:",
    "Acabado:": "Finish:",
    "Empujar (borra la original)": "Push (erase original)",
    "Engrosar (la conserva)": "Thicken (keep original)",
    "Bordes:": "Borders:",
    "Contorno (solo el perímetro)": "Contour (outline only)",
    "Cuadrícula (uno por cara)": "Grid (one per face)",
    "Ninguno": "None",
    "Selección:": "Selection:",
    "Superficie (caras unidas por aristas suaves)": "Surface (faces joined by soft edges)",
    "Individual": "Single face",
    "Mismo material": "Same material",
    "Todas las unidas": "All connected",
    "Crear el resultado en un grupo": "Create the result in a group",
    "Plano destino:": "Target plane:",
    "Plano destino": "Target plane",
    "ninguno": "none",
    "Elegir cara…": "Pick face…",
    "Elegir en el dibujo…": "Pick in the drawing…",
    "Quitar": "Clear",
    "Grupos y componentes": "Groups and components",
    "Abrir el grupo o componente al hacer clic en una de sus caras": "Open the group or component when clicking one of its faces",
    "Personalizada": "Custom",
    "Teclear:": "Type:",
    "Usar los ejes del grupo abierto (locales) para X, Y y Z": "Use the open group's (local) axes for X, Y and Z",
    "Arista": "Edge",
    "Guía": "Guide",
    "Eje": "Axis",
    "cara": "face",
    "Cara (normal)": "Face (normal)",
    "Plano de sección (normal)": "Section plane (normal)",
    "arista, cara, guía o eje": "edge, face, guide or axis",
    "Mostrar ayudas con imagen al pasar el ratón por las opciones": "Show picture hints when hovering the options",
    "Movimiento:": "Movement:",
    "Movimiento": "Movement",
    "Juntas": "Joined",
    "Una dirección": "One direction",
    "Cada cara": "Each face",
    "tecla": "key",
    "Opciones de «{m}»": "Options for “{m}”",
    "Borde exterior:": "Outer border:",
    "En inglete (cada cara a su distancia)": "Mitred (each face at its distance)",
    "Siguiendo las caras vecinas (p. ej. un tejado entre paredes)": "Following the neighbour faces (e.g. a roof between walls)",
    "Promediado con las caras vecinas": "Averaged with the neighbour faces",
    "Redondear las aristas salientes": "Round the convex edges",
    "segmentos por 90°": "segments per 90°",
    "Media del conjunto": "Average of the set",
    "Cara superior plana (proyectada sobre un plano)": "Flat top (projected onto a plane)",
    "Más opciones": "More options",
    "Bordes nuevos:": "New borders:",
    "Rematado (estrechar la cara superior)": "Taper (shrink the top face)",
    "Desmoldeo (inclinar los bordes)": "Draft (slant the borders)",
    "Deshacer el último  (Retroceso)": "Undo last  (Backspace)",
    "Activa la herramienta y abre la pestaña": "Activates the tool and opens the tab",
    "Empujar/tirar varias caras a la vez (Juntas, Una dirección o Cada cara).": "Push/pull several faces at once (Joined, One direction or Each face).",
    "(ejes del grupo)": "(group axes)",
    "normal de la cara": "face normal",
    "media del conjunto": "average of the set",
    "eje X": "X axis",
    "eje Y": "Y axis",
    "eje Z": "Z axis",
    "personalizada": "custom",
    "el rematado solo actúa en «Una dirección» y «Cada cara»": "taper only acts in “One direction” and “Each face”",
    "el desmoldeo no actúa con borde «siguiendo las vecinas» ni con redondeo": "draft does not act with the border “following the neighbours” nor with rounding",
    "los grupos y componentes se abren solos al hacer clic en sus caras": "groups and components open by themselves when you click their faces",
    "tecleada": "typed",
    "Sin dirección personalizada: elígela en el dibujo o tecléala.": "No custom direction yet: pick it in the drawing or type it.",
    "Teclas: → X · ← Y · ↑ Z · ↓ normal (la misma flecha otra vez vuelve a Normal).": "Keys: → X · ← Y · ↑ Z · ↓ normal (the same arrow again returns to Normal).",
    "El plano destino y la dirección se pueden tomar de caras y aristas de cualquier grupo, abierto o no.": "The target plane and the direction can be taken from faces and edges of any group, open or not.",
    "Las caras vecinas no seleccionadas influyen en los bordes": "Unselected neighbour faces influence the borders",
    "Redondeo:": "Rounding:",
    "ángulo mín.": "min. angle",
    "segmentos (90°)": "segments (90°)",
    "Dirección:": "Direction:",
    "Normal de la cara": "Face normal",
    "Eje X (rojo)": "X axis (red)",
    "Eje Y (verde)": "Y axis (green)",
    "Eje Z (azul)": "Z axis (blue)",
    "Proyectar sobre un plano (cara superior plana)": "Project onto a plane (flat top)",
    "Mantener unidos los triángulos que forman un cuadrilátero": "Keep triangles that form a quad together",
    "Aplanar las caras superiores": "Flatten the top faces",
    "Este modo no tiene más opciones.": "This mode has no further options.",
    "Rematado (estrechar)": "Taper (shrink)",
    "Desmoldeo (inclinar bordes)": "Draft (slant borders)",
    "Aleatorio  mín / máx": "Random  min / max",
    "Patrón aleatorio anterior": "Previous random pattern",
    "Patrón aleatorio siguiente": "Next random pattern",
    "Comenzar  (Enter)": "Start  (Enter)",
    "Plegar todo": "Collapse all",
    "Desplegar todo": "Expand all",
    "Pliega o despliega todas las secciones": "Collapses or expands all the sections",
    "Vista previa / deshacer": "Preview / undo",
    "Dictar por voz": "Dictate",
}

_USO_ES = ("Pasa el ratón por una cara y <b>clic y arrastra</b>: la empuja · <b>Mayús + pasar el ratón</b>: añade caras "
           "sin clic (Mayús + clic las quita) · <b>clic</b> suelto: elige/quita · teclea la distancia + <b>Enter</b> · "
           "<b>doble clic</b>: repite el último · <b>Retroceso</b>: deshace el último · <b>1 2 3</b>: Juntas / Una "
           "dirección / Cada cara · <b>Ctrl</b>: invierte el acabado · <b>Tab</b>: modo de selección (en Una dirección, "
           "durante el arrastre: ejes locales/del modelo) · <b>flechas</b> (Una dirección): → X · ← Y · ↑ Z · ↓ normal · "
           "las caras de un <b>grupo cerrado</b> se empujan directamente: el clic lo abre; <b>Esc</b> o clic fuera sube "
           "un nivel · <b>Esc</b>: cancelar")
_USO_EN = ("Hover a face and <b>click and drag</b>: pushes it · <b>Shift + hover</b>: adds faces without clicking "
           "(Shift + click removes) · plain <b>click</b>: pick/unpick · type the distance + <b>Enter</b> · "
           "<b>double click</b>: repeat last · <b>Backspace</b>: undo last · <b>1 2 3</b>: Joined / One direction / "
           "Each face · <b>Ctrl</b>: invert the finish · <b>Tab</b>: selection mode (One direction, while dragging: "
           "local/model axes) · <b>arrows</b> (One direction): → X · ← Y · ↑ Z · ↓ normal · faces of a <b>closed "
           "group</b> are pushed directly: the click opens it; <b>Esc</b> or a click outside goes up one level · "
           "<b>Esc</b>: cancel")


def idioma() -> str:
    try:
        from core.i18n import current_language
        return current_language() or "es"
    except Exception:  # noqa: BLE001
        return "es"


def _t(s: str, **kw) -> str:
    out = _EN.get(s, s) if idioma().startswith("en") else s
    return out.format(**kw) if kw else out


def uso() -> str:
    return _USO_EN if idioma().startswith("en") else _USO_ES


DESCRIPCION = {
    "juntas": "La superficie sigue unida: los vértices se mueven en inglete y cada cara queda a la distancia. "
              "Con «Engrosar» da grosor (sólido cerrado); el borde puede seguir las caras vecinas; las aristas se pueden redondear.",
    "direccion": "Todas las caras se desplazan en la misma dirección: la normal de la cara, la media del conjunto, un eje o una personalizada.",
    "cada_cara": "Cada cara se empuja por separado según su propia normal.",
    "engrosar": "Da grosor a una superficie y conserva la cara original (sólido cerrado).",
    "conjunto": "Empuja todas las caras juntas: la superficie sigue unida (inglete en las esquinas).",
    "redondeo": "Como Engrosar, pero redondea las esquinas salientes.",
    "vector": "Empuja todas las caras en una misma dirección: normal de la cara, eje X/Y/Z o una tomada de una arista, cara, guía o eje.",
    "normal": "Empuja cada cara por separado según su propia normal.",
    "extruir": "Empuja el conjunto según la normal media (extrusión compacta).",
    "seguir": "Los bordes resbalan por las caras vecinas no seleccionadas (empuje «inteligente»).",
}

DESCRIPCION_EN = {
    "juntas": "The surface stays joined: vertices move mitred and each face ends at the distance. "
              "With “Thicken” it gives thickness (closed solid); the border can follow the neighbour faces; edges can be rounded.",
    "direccion": "All faces move along one direction: the face normal, the average of the set, an axis or a custom one.",
    "cada_cara": "Each face is pushed separately along its own normal.",
    "engrosar": "Gives a surface thickness and keeps the original face (closed solid).",
    "conjunto": "Pushes all faces together: the surface stays joined (mitred corners).",
    "redondeo": "Like Thicken, but rounds the convex corners.",
    "vector": "Pushes all faces along one direction: face normal, X/Y/Z axis or one taken from an edge, face, guide or axis.",
    "normal": "Pushes each face separately along its own normal.",
    "extruir": "Pushes the whole set along the average normal (compact extrusion).",
    "seguir": "Borders slide along the unselected neighbour faces (smart push).",
}


def descripcion(modo: str) -> str:
    if idioma().startswith("en"):
        return DESCRIPCION_EN.get(modo, "")
    return DESCRIPCION.get(modo, "")

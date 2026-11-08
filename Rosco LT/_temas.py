# SPDX-License-Identifier: GPL-3.0-or-later
"""Los temas de la barra de Rosco LT: A · Relieve 3D, B · Transparente con
glifos (desde la 2.12.0 no quedan los demás; hasta la 2.12.0 se llamaban F
y G) y, desde la 2.17.0, C a N: el B en color, con glifos de líneas y
sombreado (``paleta``). Se eligen en
Opciones ▸ Tema de la barra, con una vista previa al pasar el ratón por
cada uno, y se recuerdan.

Cada tema da los radios de las dos bandas, el tamaño de sus iconos, la
escala de la diana, el ancho de la capa y del submenú, y qué se pliega:

- ``cursor_ligero``: mientras el ratón se mueve, el cursor lleva solo el
  anillo. Windows dibuja por hardware los cursores de hasta 256 px; los
  mayores los compone por software y van a tirones (y en algún equipo se
  recortan por los bordes). Lo demás aparece al parar el ratón, que es
  cuando se puede hacer clic.
- ``diana_plegada``: las vistas se abren con un botón en el hueco izquierdo
  del anillo y salen debajo de él, como un submenú. Deshacer y rehacer suben
  a los botoncitos del anillo; la fila de la lupa queda encima de ellos.
- ``cajetines_plegados``: la capa queda en una píldora corta bajo el anillo
  y el Navegador y las propiedades son botoncitos redondos.
- ``rueda`` (con ``diana_plegada``): la maquetación del tema A. No hay fila
  de la lupa: sus botones, la chincheta y Pantalla limpia se reparten como
  botoncitos alrededor del anillo exterior (deshacer y rehacer, juntos) y el
  extracto de propiedades baja hasta encima de ellos. Sobre Seleccionar hay
  un ojo de pupila verde: al pasar el ratón por él, el anillo y sus
  botoncitos desaparecen y se abre, centrada en el ojo, la diana en forma de
  rueda (``_diana.rueda_pintar``); al salir de ella vuelven los arcos.
- ``relieve``: las bandas, los botoncitos y los chips con volumen
  (degradado, sombra y biseles) y el botón activo rayado en verde.
- ``glifos``: todos los iconos de Rosco LT en silueta negra con detalles en
  blanco y halo (``_iconos.SILUETAS``), en vez de los de colores. El tema B
  es el A con esto y sin relieve: bandas y botoncitos de solo contorno.
- ``paleta`` (con ``glifos``): los temas C a N. Los glifos van en líneas
  del color con el interior sombreado de claro a intenso, y el rojo de la
  barra (contorno, divisiones, botón activo) pasa al color del tema
  (``_flotante.poner_paleta``). En las mezclas el contorno va de un color a
  otro de izquierda a derecha; en N todo se degrada desde la diana.
"""
from __future__ import annotations

import dataclasses

from PySide6.QtCore import QSettings

CHICO_R = 9.5                          # los botoncitos redondos pegados al anillo
HUECO = 12.0                           # grados libres entre las dos mitades
HUECO_RUEDA = 20.0                     # … con ojos: caben los huecos de los lados


@dataclasses.dataclass(frozen=True)
class Paleta:
    """Los colores de un tema de líneas y sombreado (C a N), en #rrggbb."""
    linea: str                         # el trazo de los glifos
    claro: str                         # su sombreado: de claro (arriba a la izquierda)…
    fuerte: str                        # … a intenso (abajo a la derecha)
    acento: str                        # el glifo activo o bajo el ratón
    borde: str                         # el contorno del anillo…
    div: str                           # … y sus divisiones
    borde2: str | None = None          # mezclas: el contorno va de ``borde`` a este
    radial: bool = False               # N: de ``borde`` en la diana a ``borde2`` fuera


@dataclasses.dataclass(frozen=True)
class Tema:
    clave: str
    nombre: str
    descripcion: str
    r1: tuple                          # banda interior: (radio interior, exterior)
    r2: tuple                          # banda exterior
    tam1: float = 24.0                 # iconos de la banda interior
    tam2: float = 24.0                 # … y de la exterior
    escala_diana: float = 1.0
    diana_plegada: bool = False
    cursor_ligero: bool = False
    cajetines_plegados: bool = False
    rueda: bool = False
    relieve: bool = False
    glifos: bool = False
    paleta: Paleta | None = None
    # El submenú de una herramienta sale a la derecha del cursor (los arcos y
    # los ojos se esconden) hasta que se sale de él o se empieza a dibujar.
    submenu_centrado: bool = False
    capa_w: float = 150.0
    capa_h: float = 22.0
    panel_w: float = 320.0
    # Qué botón va en cada banda, de izquierda a derecha en pantalla (None:
    # el reparto de siempre, el de ``_cadena`` y ``_seleccion``).
    arriba_int: tuple | None = None
    arriba_ext: tuple | None = None
    abajo_int: tuple | None = None
    abajo_ext: tuple | None = None
    tam_abajo_ext: float | None = None  # iconos de la banda exterior de abajo

    @property
    def r_ext(self) -> float:
        return self.r2[1]

    @property
    def hueco(self) -> float:
        """Grados libres a cada lado entre las dos mitades (con ojos, más:
        ahí van los huecos de los lados)."""
        return HUECO_RUEDA if self.rueda else HUECO

    @property
    def a_arriba(self) -> float:
        return self.hueco

    @property
    def a_abajo(self) -> float:
        return 180.0 + self.hueco

    @property
    def barrido(self) -> float:
        return 180.0 - 2.0 * self.hueco

    @property
    def cerrar_r(self) -> float:
        """El radio del ✕ (y del botón de las vistas): el medio del hueco."""
        return (self.r1[0] + self.r2[1]) / 2.0

    @property
    def abajo_anillo(self) -> float:
        """Del cursor al pie de los botoncitos de debajo del anillo."""
        return self.r2[1] + 2.0 * CHICO_R + 3.0


_CLASICO = ((24.0, 62.0), (66.0, 104.0))
_RELIEVE = Tema(
    "relieve", "A · Relieve 3D",
    "Cursor ligero, con volumen y el botón activo rayado; cuatro ojos (el azul abre la "
    "rueda de vistas), los botones de arriba rodean el anillo y las bandas van a su manera.",
    *_CLASICO, cursor_ligero=True, diana_plegada=True, rueda=True, relieve=True,
    submenu_centrado=True,
    arriba_int=("medir", "seleccionar", "pintar"),
    arriba_ext=("linea", "rect", "circle", "poly", "arco"),
    abajo_ext=("borrar", "copiar", "cortar", "pegar", "pegar_sitio", "agrupar",
               "bloquear", "ocultar", "invertir"),
    tam_abajo_ext=18.0)
_TRANSPARENTE = dataclasses.replace(
    _RELIEVE, clave="transparente", nombre="B · Transparente con glifos",
    descripcion="Como A, sin relieve: bandas de solo contorno, se ve el modelo "
                "a través, y siluetas negras en vez de los iconos de colores.",
    relieve=False, glifos=True)


def _color(clave, nombre, descripcion, paleta) -> Tema:
    return dataclasses.replace(_TRANSPARENTE, clave=clave, nombre=nombre,
                               descripcion=descripcion, paleta=paleta)


_UNO = "Como B, en {}: glifos de líneas con el interior sombreado y el anillo de ese color."
_DOS = ("Como B, de {} a {}: glifos de líneas con el sombreado de un color al otro y "
        "el contorno del anillo igual, de izquierda a derecha.")
_LISTA = (
    _RELIEVE,
    _TRANSPARENTE,
    _color("turquesa", "C · Turquesa", _UNO.format("turquesa"),
           Paleta("#0b5f5b", "#d6f6f2", "#1fb5ad", "#0e8f88", "#139c95", "#7fd3cd")),
    _color("azul", "D · Azul", _UNO.format("azul"),
           Paleta("#123a7a", "#dbe8fc", "#2f6fd6", "#2458b0", "#2a62c4", "#8fb2ea")),
    _color("turquesa_azul", "E · Turquesa y azul", _DOS.format("turquesa", "azul"),
           Paleta("#0f3f63", "#d2f5f1", "#2f6fd6", "#1b8fb0", "#1fb5ad", "#88c6e0",
                  borde2="#2a62c4")),
    _color("roja", "F · Roja", _UNO.format("rojo"),
           Paleta("#7a1414", "#fde0dc", "#e0453a", "#b3261e", "#c62828", "#ec9a94")),
    _color("magenta", "G · Magenta", _UNO.format("magenta"),
           Paleta("#6b0f52", "#fbdcf1", "#d63aa8", "#a8237f", "#c02a92", "#e79ad0")),
    _color("amarilla", "H · Amarilla",
           _UNO.format("amarillo") + " Las líneas, en ocre oscuro para leerse sobre lo claro.",
           Paleta("#6b5200", "#fff6cc", "#f2c21a", "#a07c00", "#d9a800", "#ecd270")),
    _color("gris", "I · Gris", _UNO.format("gris"),
           Paleta("#2f3338", "#f3f4f6", "#8a9099", "#4a4f56", "#6b7178", "#b4b8be")),
    _color("naranja", "J · Naranja", _UNO.format("naranja"),
           Paleta("#7a3300", "#ffe6d1", "#f07b1d", "#b85410", "#e06a10", "#f2b07a")),
    _color("amarilla_naranja", "K · Amarilla y naranja", _DOS.format("amarillo", "naranja"),
           Paleta("#6e4300", "#fff4c2", "#f07b1d", "#b06a00", "#e8b400", "#f0c870",
                  borde2="#e06a10")),
    _color("marron_naranja", "L · Marrón y naranja", _DOS.format("naranja", "marrón"),
           Paleta("#4a2a12", "#ffe2c4", "#8b4a1e", "#8a4a1a", "#e06a10", "#d6a77e",
                  borde2="#7a4520")),
    _color("purpura_azul", "M · Púrpura y azul", _DOS.format("púrpura", "azul"),
           Paleta("#2e1a66", "#e9ddfb", "#3f62d8", "#4b3aa8", "#7b3fc4", "#a99ae6",
                  borde2="#2a62c4")),
    _color("marino_turquesa", "N · Azul marino a turquesa",
           "Como B, degradado desde la diana: contorno, divisiones y glifos azul marino "
           "en el centro y turquesa en el borde; dentro de cada glifo las líneas siguen "
           "aclarándose hacia el turquesa.",
           Paleta("#0b1f4d", "#d2f2f0", "#1fc8bd", "#0b1f4d", "#0b1f4d", "#6fa8c0",
                  borde2="#1fc8bd", radial=True)),
)
TEMAS = {t.clave: t for t in _LISTA}
POR_DEFECTO = "relieve"            # también si se guardó uno de los temas quitados


def tema(clave) -> Tema:
    return TEMAS.get(str(clave), TEMAS[POR_DEFECTO])


def _ajustes() -> QSettings:
    from ._ajustes import ajustes
    return ajustes()


def guardado() -> Tema:
    return tema(_ajustes().value("barra/tema", POR_DEFECTO))


def guardar(clave: str) -> None:
    _ajustes().setValue("barra/tema", clave)


# ---- La escala de la barra (Configuración ▸ Tamaño) ---------------------------------
ESCALA_MIN, ESCALA_MAX = 0.6, 1.3


def escalar(t: Tema, factor: float) -> Tema:
    """El tema con todas sus medidas multiplicadas por ``factor`` (los
    botoncitos redondos y la rueda no cambian)."""
    f = max(ESCALA_MIN, min(ESCALA_MAX, float(factor)))
    if abs(f - 1.0) < 1e-6:
        return t
    return dataclasses.replace(
        t, r1=tuple(x * f for x in t.r1), r2=tuple(x * f for x in t.r2),
        tam1=t.tam1 * f, tam2=t.tam2 * f,
        tam_abajo_ext=t.tam_abajo_ext * f if t.tam_abajo_ext else None,
        escala_diana=t.escala_diana * f, capa_w=t.capa_w * f, capa_h=t.capa_h * f,
        panel_w=t.panel_w * f)


def escala_guardada() -> float:
    try:
        return max(ESCALA_MIN, min(ESCALA_MAX, float(_ajustes().value("barra/escala", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def guardar_escala(factor: float) -> None:
    _ajustes().setValue("barra/escala", float(factor))

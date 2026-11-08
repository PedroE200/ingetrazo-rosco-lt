# SPDX-License-Identifier: GPL-3.0-or-later
"""Rosco LT: la cadena Base → Empujar/Tirar → Base…, con su anillo partido.

El anillo lo reúne todo alrededor del cursor, sin botones para saltar de
una barra a otra: la mitad de arriba dibuja (lo de abajo de esta nota) y la
de abajo modifica (la barra de modificar dentro; Suprimir, Agrupar, Cortar, Copiar e
Invertir cara fuera). El ✕ va en el hueco de la derecha, junto al cursor;
arriba, al lado de la chincheta, Pantalla limpia.

Herramientas (subclases de las nativas de IngeTrazo 0.5.8):

- Arco interior, las bases que pasan a Empujar/Tirar:
  ``RectanguloCadena`` (esquina / centro), ``GiradoCadena`` (lado: dos clics
  por los ejes y el fondo; girado: el rectángulo girado nativo),
  ``PoligonoCadena`` y ``CirculoCadena`` (centro / lado o diámetro; lados),
  ``LineaCadena`` (polilínea; al cerrarse).
- Arco exterior: Línea (``LineaLibreCadena``, pasa a la altura si cierra una
  cara; o ``GuiaCadena``, una línea guía por dos puntos), Borrar
  (``BorradorCadena``: borrar u ocultar), Seleccionar (``SeleccionCadena``:
  ventana nativa o lazo), Grupo (al terminar cada pieza: nada, grupo o
  componente, con nombre opcional) y el enlace a la barra de modificar.

Al confirmar una base, ``EmpujarCadena`` (``PushPullTool``) recibe la cara
nueva y simula su primer clic: entra directamente en «arrastrando altura». Al
confirmar (clic o Enter) o cancelar (Esc), vuelve a la herramienta elegida.

Selector: mientras el ratón se mueve, los dos arcos SON el cursor
(``_flotante.cursor_compuesto``), sin retraso y con el puntero en su centro.
Al parar el ratón (REPOSO_MS) se quedan fijos en una ventanita
(``_flotante.Flotante``). Un clic en un botón elige la herramienta y abre su
submenú encima de los arcos, que sigue ahí hasta que el cursor sale de la
barra: así se eligen las opciones antes del primer punto. Un clic fuera pone
el primer punto. Esc sin nada en curso oculta o muestra el selector.

Los cambios de herramienta se difieren con ``QTimer.singleShot(0, …)``: el visor
aún usa la herramienta activa justo después de ``on_click`` / ``on_value``.
"""
from __future__ import annotations

from ._gestor import gestor_barras
from ._idioma import _tr
import dataclasses
import logging
import math
import os
import re
import time

from PySide6.QtCore import (
    QByteArray, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QTextDocument,
    QAction, QBrush, QColor, QCursor, QFont, QFontMetricsF, QIcon, QPainter,
    QLinearGradient, QPainterPath, QPen, QPixmap, QPolygonF, QTransform, QVector3D,
)
from PySide6.QtWidgets import QApplication, QInputDialog

from core.units import fmt_len
from tools.base import Tool, ToolContext
from tools.arc import ArcTool, CenterArcTool, PieTool, ThreePointArcTool
from tools.circle import CircleTool, PolygonTool
from tools.dimension import DimensionTool
from tools.eraser import EraserTool
from tools.fillet import FilletTool
from tools.offset import OffsetTool
from tools.tape import TapeMeasureTool
from tools.line import LineTool
from tools.pushpull import PushPullTool
from tools.rectangle import RectangleTool
from tools.rotated_rectangle import RotatedRectangleTool
from tools.select import SelectTool

from ._flotante import (
    BLANCO, CHINCHETA_R, HALO, NEGRO, ROJO, ROJO_OSCURO, ROSA_CLARO, Flotante,
    app_activa, boton_en, centros_chincheta, chincheta_en, cursor_compuesto,
    dibujar_banda, dibujar_boton_redondo, dibujar_chincheta, etiqueta, glifo,
    mascara_chincheta, rayar, rect_etiqueta, relieve_redondo, restaurar_cursor,
    sector, sombra, texto_chincheta, _flecha, centro_boton,
)
from . import _anima, _capas, _diana, _empuje, _flotante, _huecos, _iconos, _idioma, _interruptor, _seleccion, _temas
from ._temas import CHICO_R
from ._capas import Capas
from ._diana import Diana
from ._medidas import Medidas
from ._navegador import Navegador

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

TITULO = "Abrir la barra"
ACCENT = QColor(240, 110, 40)          # el naranja de IngeTrazo
TINTA = QColor(44, 44, 42)
_TOL2 = 1e-8                           # (0,1 mm)² para reconocer los vértices
_ICONO_SVG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "icons", "barra_dibujo.svg")

# ---- Los botones y sus opciones ---------------------------------------------------
BASES = ("rect", "poly", "arco", "circle")                       # arco interior
HERRAMIENTAS = ("linea", "borrar", "seleccionar", "pintar", "medir")  # exterior
CONSTRUYEN = ("rect", "poly", "arco", "circle", "linea")         # pasan a la altura
# Al terminar una pieza (en el submenú de cada herramienta de dibujo): nada,
# grupo, componente o grupo con nombre. Un solo ajuste para todas.
FINALES = ("nada", "grupo", "componente", "con nombre")
NOMBRES = {"rect": "Rectángulo", "poly": "Polígono regular", "arco": "Arco",
           "line": "Polilínea cerrada", "circle": "Círculo",
           "linea": "Línea", "borrar": "Borrar", "seleccionar": "Seleccionar",
           "pintar": "Pintar: pintar · muestrear material", "medir": "Medir",
           "vistas": "Vistas y zoom: abre la diana debajo del anillo",
           "ojo": "Pasa por el ojo: se abre la rueda de vistas",
           "cerrar_app": "Cerrar IngeTrazo (pregunta si guardar)",
           "apagar": "Apagar: salir de IngeTrazo · reiniciar IngeTrazo",
           "historial": "Últimos comandos (pasa por el ojo amarillo)",
           "ayuda": "Ayuda de Rosco LT (pasa por el ojo verde)",
           "preferencias": "Preferencias: de IngeTrazo · información del dibujo",
           "nav": "Navegador: grupos y componentes del modelo",
           **_diana.NOMBRES, **_seleccion.NOMBRES}
DIANA = _diana.PARTES                  # la diana, encima de los arcos
MODOS = {"rect": ("esquina", "centro", "lado", "girado"),
         "poly": ("centro", "lado"),
         "arco": ("arco", "3 puntos", "centro", "porción"),
         "circle": ("centro", "diámetro"),
         "linea": ("línea", "guía", "equidist.", "paralela", "redondear"),
         "borrar": ("borrar", "ocultar"),
         "seleccionar": ("ventana", "lazo"),
         "pintar": ("pintar", "muestrear material"),
         "medir": ("cota", "medir")}
LIMITES_LADOS = {"poly": (3, 96), "circle": (6, 96)}
COLOR_GRUPO = {"grupo": QColor(214, 34, 34), "con nombre": QColor(214, 34, 34),
               "componente": QColor(24, 95, 165)}
ETIQUETA_LADOS = {"poly": "Lados", "circle": "Segmentos"}

# ---- Geometría del selector (píxeles) ----------------------------------------------
# Un anillo partido alrededor del cursor: la mitad de arriba dibuja (bases
# dentro, herramientas fuera) y la de abajo modifica (la barra de modificar dentro,
# acciones de la selección fuera). Entre las dos mitades quedan unos grados
# libres a cada lado: en el de la derecha va el ✕ de cerrar y, con la diana
# plegada, en el de la izquierda el botón de las vistas. Los radios, el
# tamaño de los iconos y qué se pliega los da el tema (``_temas.py``).
# Las bandas se recorren de a0 + barrido a a0: abajo eso va de derecha a
# izquierda, así que se dan al revés para leerse de izquierda a derecha.
# Lo que puede ir en una banda, por lo que hace al pulsarlo.
ACCIONES_SEL = ("suprimir", "cortar", "copiar", "invertir", "ocultar", "bloquear")
PEGADOS = ("pegar", "pegar_sitio")
# Submenús que, centrados (temas A y B), dejan a la vista las propiedades, la capa
# y el navegador: trabajan sobre la selección.
CON_CAJETINES = ("seleccionar", "move", "scale", "rotate", "flip", "align")
TOLERANCIA = 2.0                       # px de más para acertar el clic
# Los chips de los submenús: icono encima y etiqueta debajo.
CHIP_H, CHIP_ICONO = 40.0, 16.0
ICONO_MODO = {
    ("rect", "esquina"): "m_esquina", ("rect", "centro"): "m_centro_rect",
    ("rect", "lado"): "m_lado_rect", ("rect", "girado"): "m_girado",
    ("poly", "centro"): "m_centro_poly", ("poly", "lado"): "m_lado_poly",
    ("arco", "arco"): "arco", ("arco", "3 puntos"): "m_arco3",
    ("arco", "centro"): "m_arco_centro", ("arco", "porción"): "m_porcion",
    ("circle", "centro"): "m_centro_circ", ("circle", "diámetro"): "m_diametro",
    ("linea", "línea"): "linea", ("linea", "guía"): "m_guia", ("linea", "equidist."): "m_equidist",
    ("linea", "paralela"): "m_paralela", ("linea", "redondear"): "m_redondear",
    ("borrar", "borrar"): "borrar", ("borrar", "ocultar"): "ocultar",
    ("seleccionar", "ventana"): "m_ventana", ("seleccionar", "lazo"): "m_lazo",
    ("pintar", "pintar"): "pintar", ("pintar", "muestrear material"): "muestrear",
    ("fin", "nada"): "m_nada", ("fin", "grupo"): "grupo", ("fin", "componente"): "m_componente",
    ("fin", "con nombre"): "m_con_nombre",
    ("medir", "cota"): "m_cota", ("medir", "medir"): "medir",
    ("agrupar", "grupo"): "grupo", ("agrupar", "con nombre"): "m_con_nombre",
    ("agrupar", "componente"): "m_componente", ("agrupar", "desagrupar"): "m_desagrupar",
    ("move", "mover"): "move", ("move", "copia"): "copiar", ("move", "alinear"): "align",
    ("move", "empujar/tirar"): "m_empujar", ("move", "vértices"): "m_vertices",
    ("scale", "libre"): "scale", ("scale", "por referencia"): "m_referencia",
    ("rotate", "sin copia"): "rotate", ("rotate", "con copia"): "m_rotar_copia",
}
# El submenú de la Simetría propia: arriba el plano (o el editor de
# hotspots), abajo los interruptores (copia y eje fijo).
MODOS_FLIP = ("cursor", "centro", "puntos", "hotspots")
EXTRAS_FLIP = ("copia", "x", "y", "z")
TEXTO_FLIP = {"cursor": "bajo el cursor", "centro": "por el centro", "puntos": "dos puntos A→B",
              "hotspots": "hotspots", "copia": "copia", "x": "eje X", "y": "eje Y", "z": "eje Z"}
TEXTO_FLIP_ROSCO = {**TEXTO_FLIP, "cursor": "bajo el\ncursor", "centro": "por el\ncentro",
                    "puntos": "dos puntos\nA→B"}
COLOR_FLIP = {"x": QColor(214, 40, 40), "y": QColor(40, 160, 60), "z": QColor(40, 90, 214)}
ICONO_FLIP = {"cursor": "flip", "centro": "m_centro_rect", "puntos": "m_diametro",
              "hotspots": "m_vertices", "copia": "copiar"}
# El submenú de Alinear (dentro de Desplazar): mover o copiar, y escalar al 2.º.
MODOS_ALINEAR = ("mover", "copiar", "escalar")
TEXTO_ALINEAR = {"mover": "mover", "copiar": "copiar", "escalar": "escalar al 2.º"}
ICONO_ALINEAR = {"mover": "move", "copiar": "copiar", "escalar": "scale"}
NOMBRES["align"] = "Alinear"
NOMBRES["empujar"] = "Empujar / tirar"
# Las órdenes de edición a las que se les puede dictar la medida (Opciones).
EDICION_CON_MEDIDA = {"move": "Desplazar", "rotate": "Rotar", "scale": "Escalar",
                      "pushpull": "Empujar / tirar", "vertices": "Vértices", "align": "Alinear"}
# El botón derecho (2.35.0) hace lo que hacía el botoncito ✕ junto al cursor, y
# más, para que durante una orden solo queden el lápiz, la medida y la tira:
# - con una orden: clic = terminar aceptando (como Esc: suelta lo que cuelga del
#   ratón y conserva lo hecho; sin nada a medias, sale a Seleccionar); doble
#   clic = atrás un paso (deshace lo último sin salir de la orden);
# - sin orden: clic en vacío = mostrar u ocultar el rosco; doble clic en vacío =
#   deshacer; sobre un objeto, el menú de IngeTrazo de siempre.
# Con Ctrl, Mayús o Alt no se toca nada. El ✕ sigue en el código por si se
# vuelve a querer (CON_ASPA).
CON_ASPA = False
# El botoncito de cancelar, junto al cursor con cualquier orden elegida (desde
# que se pincha; sin empezar, vuelve a Seleccionar):
# abajo a la izquierda (el lápiz y la flecha van hacia el otro lado). Sigue al
# ratón en cada movimiento; solo se queda quieto si el ratón va hacia él (y
# está a menos de CANCELAR_QUIETO), para poder pulsarlo.
CANCELAR_DX, CANCELAR_DY = 38.0, -38.0   # detrás del lápiz, junto a la goma
CANCELAR_QUIETO = 64.0
TEXTO_CANCELAR = "Cancelar la orden"
DIANA_HUECO = 6.0                      # entre el arco exterior y la diana
PANEL_HUECO = 8.0                      # entre lo de debajo del anillo y el submenú
# El submenú de una herramienta (temas A y B): del cursor a su esquina de
# arriba a la izquierda.
SUBMENU_DY = -20.0                     # en horizontal, ``Cadena.distancia_submenu``
ROSCO_MARGEN = 60.0                    # el rosco no se mueve si el ratón lo rodea a esta distancia
CAJETIN_HUECO = 8.0                    # submenú al centro: entre él y sus cajetines
BORDE_VISOR = 4.0                      # nada de la barra se acerca más al borde del visor
MENUS_SEL_X = 46.0                     # selección: el botón de menús, junto a la chincheta
# Los botoncitos de encima (dibujar): ángulo (0 = derecha, 90 = arriba) y
# nombre; los de debajo son los de la selección (``_seleccion.CHICOS``). Con
# la diana plegada se añaden deshacer y rehacer; con los cajetines plegados,
# el Navegador y (con selección) las propiedades.
CHICOS_BARRA_DIBUJO = {"notas": 118.0, "tiempo": 106.0, "pegar": 74.0, "pegar_sitio": 62.0}
CHICOS_DIANA = {"deshacer": 130.0, "rehacer": 50.0}
CHICOS_CAJETINES = {"nav": 308.0, "propiedades": 232.0}
# Las órdenes de los botoncitos (las atiende ``_accion_chico``, estén donde estén).
ORDENES_CHICAS = ("notas", "tiempo", "calc", "guardar", "copia", "texto",
                  "deshacer", "rehacer", "chincheta", "limpia",
                  "preferencias", "apagar", "nav", "propiedades", "opciones",
                  "buscar", "reiniciar", "ext", "bar")
# Los temas A y B: sin fila de la lupa; todo repartido alrededor del anillo, con
# deshacer y rehacer juntos y el ojo (a 90°) libre entre tiempo y pegar.
# Mirando al ojo de arriba: a la derecha deshacer, configurar, pantalla limpia,
# apagar y la calculadora; a la izquierda rehacer, buscar (que lleva también
# los menús de IngeTrazo), preferencias, extensiones y gestor de barras.
# Mirando al de abajo: notas a la derecha (izquierda de pantalla) y el reloj a
# la izquierda.
CHICOS_F = {"deshacer": 76.0, "opciones": 63.0, "limpia": 50.0, "apagar": 37.0, "calc": 24.0,
            "rehacer": 104.0, "buscar": 117.0, "preferencias": 130.0, "ext": 143.0, "bar": 156.0,
            "notas": 256.0, "tiempo": 284.0}
OJO_R = 13.0                           # los ojos (alto 2·OJO_R·0.7)
# Los huecos de los lados (temas con ojos): entre la mitad de arriba y la de
# abajo, a cada lado, uno en la banda de dentro y, en la de fuera, uno encima
# y otro debajo del ojo. Notas y el reloj vienen de los botoncitos de abajo.
# El hueco de dentro de la izquierda va partido: «izq_dentro» arriba e «izq_dentro_b»
# abajo (el último, para no mover los índices de lo ya guardado).
LADOS = ("izq_arriba", "izq_dentro", "izq_abajo", "der_arriba", "der_dentro", "der_abajo", "izq_dentro_b")
LADOS_DEF = ("texto", "empujar", "notas", "guardar", "move", "copia", "")
# El subrosco de la Cámara (botón del aro de la rueda): sale en lugar de ella.
CAMARA_OPCIONES = {"situar_camara": "situar\ncámara", "caminar": "caminar",
                   "mirar_alrededor": "mirar\nalrededor"}
LADO_OJO = 8.0                         # grados que deja libres el ojo a cada lado
# Los cuatro ojos: ángulo, dónde (al borde del anillo o entre los arcos
# exteriores) y color del iris. De serie, el de arriba abre la rueda, el de
# la izquierda (amarillo) el historial y el de la derecha (verde) la ayuda;
# el de abajo no hace nada.
OJOS = {"arriba": (90.0, "borde", QColor(55, 138, 221)),
        "abajo": (270.0, "borde", QColor(224, 52, 47)),
        "derecha": (0.0, "banda", QColor(47, 191, 107)),
        "izquierda": (180.0, "banda", QColor(242, 194, 26))}
PREFERENCIAS = ("Preferencias…", "Preferencias", "Preferences…", "Preferences")
INFO_MODELO = ("Info del modelo", "Model Info", "Información del modelo")
# El historial del ojo amarillo: los últimos comandos (herramientas y órdenes).
HIST_MAX, HIST_W = 10, 170.0
# Menús cuyas órdenes no se apuntan (vistas, cámara, zoom).
HIST_SIN = ("vista", "view", "cámara", "camara", "camera", "zoom")
# Los paneles que se abren al pasar por un ojo y salen a su lado.
PANELES_OJO = ("historial", "ayuda")
# La ayuda del ojo verde: apartados (título, texto) o (título, [(ojo, texto)]).
AYUDA_W, AYUDA_MAX_H = 430.0, 730.0
# La primera pestaña: los clics. Cada fila: (botón, veces, texto); botón «i»
# izquierdo o «d» derecho; veces 1, 2 o 0 si es mantener pulsado.
AYUDA_PESTANAS = ("Los clics", "Todo lo demás")
AYUDA_ARRIBA, AYUDA_RATON = 52.0, 30.0   # donde empieza el texto; sitio para el ratoncito
AYUDA_CLICS = (
    ("Sin orden (Seleccionar)",
     (("i", 1, "<b>Clic izquierdo</b> en vacío: abre el rosco; si hay selección, la quita (tras una orden, "
               "vuelve el anillo con esa selección). En un objeto: lo selecciona y sale el anillo de selección. "
               "Con un grupo abierto: dentro de su caja abre el rosco; fuera, cierra el grupo.", ("vacio", "objeto")),
      ("i", 2, "<b>Doble clic izquierdo</b> en vacío: repite la última orden. En un grupo: entra a editarlo.", ("repite",)),
      ("d", 1, "<b>Clic derecho</b>, en vacío o en un objeto: el menú de IngeTrazo. Con el rosco a la vista, "
               "en vacío: un paso atrás (del submenú o la rueda al rosco; del rosco, Seleccionar y se esconde).",
       ("menu", "alterna")),
      ("d", 2, "<b>Doble clic derecho</b> en vacío: deshace el último cambio.", ("deshace",)))),
    ("Sobre el rosco",
     (("i", 1, "<b>Clic en un botón</b>: elige la orden y abre sus opciones.", ("boton",)),
      ("i", 2, "<b>Doble clic en el centro</b>: repite la última orden.", ("repite",)),
      ("d", 1, "<b>Clic derecho</b>: un paso atrás. En un submenú o en la rueda de vistas vuelve al rosco "
               "principal; en el rosco principal, Seleccionar y el rosco se esconde.", ("boton",)),
      ("i", 0, "<b>Mantener pulsado</b>: el rosco se vuelve transparente para ver el modelo y, al soltar, vuelve "
               "donde esté el cursor. Sobre un botón, además escucha una orden de voz.", ("pulsado",)))),
    ("Con una orden en marcha",
     (("i", 1, "<b>Clic izquierdo</b>, en vacío o en un objeto: pone el siguiente punto. Nunca abre nada. "
               "Al acabar, la orden sigue activa para otra vez.", ("punto",)),
      ("i", 2, "<b>Doble clic izquierdo</b>: cancela la orden. Descarta lo que estaba a medias; "
               "lo terminado se queda.", ("cancela",)),
      ("d", 1, "<b>Clic derecho</b>: termina la orden, conserva lo hecho (lo que cuelga del ratón "
               "se suelta) y abre el rosco con el submenú de esa orden. Otro clic derecho: al rosco "
               "principal; otro más: Seleccionar. Con una orden de editar, encima de un objeto: "
               "termina y sale el menú de IngeTrazo.", ("termina",)),
      ("d", 2, "<b>Doble clic derecho</b>: un paso atrás. Quita lo último y sigues en la orden.", ("atras",)))),
)
AYUDA_ESCENAS = tuple(dict.fromkeys(e for _t, filas in AYUDA_CLICS for fila in filas for e in fila[3]))
ANIMA_ALTO = 130.0                     # la pantallita animada de la pestaña de clics
# La segunda pestaña: apartados (título, texto) o (título, [(ojo, texto)]).
AYUDA = (
    ("Moverse y parar",
     "Al mover el ratón, el anillo va con el cursor. Al pararte se queda fijo y ya puedes "
     "hacer clic en sus botones. Si te alejas, vuelve a seguirte."),
    ("Arriba: dibujar",
     "Fuera: línea, rectángulo, círculo, polígono y arco. Dentro: medir, seleccionar y "
     "pintar. Un clic elige la herramienta y abre sus opciones a la derecha del cursor "
     "(lados, modo, «al terminar»…)."),
    ("Abajo: modificar lo seleccionado",
     "Dentro: suprimir, simetría, escalar y rotar. Fuera: borrar, copiar, cortar, pegar, "
     "pegar en su sitio, crear grupo, bloquear, ocultar e invertir cara."),
    ("Los ojos (se abren pasando el ratón por encima)",
     [("arriba", "Azul: la rueda de vistas (zoom, vistas estándar, cónica/paralela, plano de "
                 "sección, cámara, ocultar…)."),
      ("izquierda", "Amarillo: los 10 últimos comandos."),
      ("derecha", "Verde: esta ayuda."),
      ("abajo", "Rojo: ocultar el resto del modelo (otro clic lo vuelve a mostrar).")]),
    ("Los botoncitos del borde",
     "Deshacer y rehacer, opciones, pantalla limpia, buscar (con la barra quieta, teclea para "
     "buscar una orden; con un clic, los menús de IngeTrazo en árbol), preferencias, gestor de "
     "barras, extensiones, apagar y calculadora. A la izquierda: texto, empujar/tirar y notas "
     "(con el reloj en «Tareas del modelo»); a la derecha: guardar, desplazar y copia "
     "con nombre y comentario. Todos los huecos se cambian en el gestor de barras ▸ "
     "Barra Rosco LT."),
    ("La casilla de medidas",
     "Sale junto al lápiz tras cada punto. Teclea la medida (admite cuentas, como 120/2) o díctala "
     "con el micrófono: rojo mientras escucha. La V acepta, el retroceso borra una cifra y el aspa "
     "toda la casilla."),
    ("Con el teclado",
     "Esc cancela la orden o cierra el panel abierto. Ctrl+Alt+R reinicia IngeTrazo."),
    ("Ajustes",
     "En Opciones: idioma, tema de la barra, tamaño, distancia del cursor al submenú, tamaño del "
     "rosco de submenús, dictado de medidas tras el primer punto, qué hacer al terminar una orden, "
     "fijar la barra con la chincheta y desactivar Rosco LT."),
)
# Lo que el doble clic en el vacío se salta al repetir la última orden.
NO_REPETIR = {"seleccionar", "select", "deshacer", "rehacer", "undo", "redo",
              NOMBRES["seleccionar"].split(":")[0].strip().lower()}
NOMBRES_CHICOS = {"notas": "Tareas",
                  "tiempo": "Control de tiempo", "calc": "Calculadora",
                  "guardar": "Guardar el dibujo",
                  "copia": "Guardar una copia (con nombre y comentario)",
                  "texto": "Texto",
                  "opciones": "Opciones", "pegar": "Pegar",
                  "pegar_sitio": "Pegar en su sitio"}
# El lápiz del cursor según la herramienta de la barra de dibujo.
FORMA_LAPIZ = {"rect": "rect", "poly": "poly", "arco": "arco", "circle": "circulo",
               "linea": "linea", "borrar": "borrar", "seleccionar": "seleccionar",
               "medir": "medir"}
PROPS_W, PROPS_H = 250.0, 38.0         # el extracto de propiedades (selección)
CAPA_HUECO = 8.0                       # entre la pastilla y lo que tiene al lado
POSICIONES_CAPA = ("abajo", "arriba", "izquierda")   # bajo el anillo / buscador / izquierda
# La ventanita: rótulo, buscador, diana y la mitad de dibujar encima; la de
# modificar, la capa y el submenú debajo.
VENTANA_W, VENTANA_H = 940, 780       # con sitio para la barra al 130 % (y el submenú, a la derecha)
ANCLA_LOCAL = QPointF(350.0, 390.0)
SINCRONIA_MS = 150                     # repaso de visibilidad sin mover el ratón
REPOSO_MS = 300                        # ratón parado este tiempo: la barra se fija

TIP = ("Rosco LT: dibuja una base (rectángulo, polígono, arco, círculo o "
       "línea) y, sin soltar la orden, Empujar/Tirar su cara.")
MSG = {
    ("rect", "esquina"): "Rosco LT · rectángulo: clic en una esquina y en la "
                         "opuesta (o teclea ancho;alto + Enter).",
    ("rect", "centro"): "Rosco LT · rectángulo desde el centro: clic en el centro "
                        "y en una esquina (o teclea ancho;alto + Enter).",
    ("rect", "lado"): "Rosco LT · rectángulo por lado: dos clics para un lado "
                      "(va por los ejes) y un tercero para el fondo.",
    ("rect", "girado"): "Rosco LT · rectángulo girado: dos clics para un lado en "
                        "cualquier dirección y un tercero para el fondo.",
    ("poly", "centro"): "Rosco LT · polígono: clic en el centro y en un vértice "
                        "(o teclea el radio + Enter).",
    ("poly", "lado"): "Rosco LT · polígono por lado: clic en los dos extremos de "
                      "una arista (o teclea su longitud + Enter). Crece a la "
                      "izquierda de la arista.",
    ("line", None): "Rosco LT · polilínea: clic en cada punto; cierra en el primero.",
    ("circle", "centro"): "Rosco LT · círculo: clic en el centro y en el borde "
                          "(o teclea el radio + Enter).",
    ("circle", "diámetro"): "Rosco LT · círculo por diámetro: clic en dos puntos "
                            "opuestos (o teclea el diámetro + Enter).",
    ("linea", "línea"): "Rosco LT · línea: clic en cada punto; si cierras un "
                        "contorno, pasa a la altura.",
    ("linea", "guía"): "Rosco LT · línea guía: clic en dos puntos por los que "
                       "pasa la guía.",
    ("linea", "equidist."): "Rosco LT · equidistancia: clic en una cara (o en una "
                            "polilínea), arrastra o teclea la distancia.",
    ("linea", "paralela"): "Rosco LT · paralela: clic en un segmento o en una línea "
                           "abierta, lleva el ratón al lado y haz clic o teclea "
                           "la distancia.",
    ("linea", "redondear"): "Rosco LT · redondear 3D: clic en una arista (o usa las "
                            "seleccionadas), aleja el ratón o teclea el radio.",
    ("arco", "arco"): "Rosco LT · arco: clic en los dos extremos y luego en la "
                      "flecha (o tecléala).",
    ("arco", "3 puntos"): "Rosco LT · arco por 3 puntos: inicio, un punto del arco "
                          "y final.",
    ("arco", "centro"): "Rosco LT · arco por centro: centro, inicio del arco y "
                        "ángulo final.",
    ("arco", "porción"): "Rosco LT · porción: centro, inicio y ángulo final; la "
                         "porción pasa a la altura.",
    ("medir", "cota"): "Rosco LT · cota: clic en dos puntos y en la posición de la "
                       "línea de cota.",
    ("medir", "medir"): "Rosco LT · medir: clic en dos puntos (desde una arista "
                        "deja una guía).",
    ("borrar", "borrar"): "Rosco LT · borrar: clic o arrastra sobre aristas u "
                          "objetos para borrarlos.",
    ("borrar", "ocultar"): "Rosco LT · ocultar: clic o arrastra sobre aristas u "
                           "objetos para ocultarlos.",
    ("seleccionar", "ventana"): "Rosco LT · seleccionar: clic, o arrastra una "
                                "ventana (izq.→der.) o captura (der.→izq.).",
    ("seleccionar", "lazo"): "Rosco LT · seleccionar con lazo: arrastra rodeando "
                             "lo que quieras (Ctrl añade, Mayús alterna).",
}
MSG_ALTURA = ("Altura: mueve el ratón y haz clic, o teclea la medida + Enter. "
              "Esc = dejarla plana.")
MSG_ESPERA = ("Rosco LT: para el ratón y elige una herramienta en la barra. Un clic "
              "fuera de la barra (o Esc) la cierra.")


# Lo que delata una orden a medias en cualquier herramienta (nativa o de una
# extensión): el punto base, el tirador cogido, el arrastre, los puntos ya
# puestos… con los nombres que suelen usar.
SENAS_EN_MARCHA = (
    "start_point", "_start_point", "first_point", "_first_point", "first", "_first",
    "p1", "_p1", "point1", "_pt1", "origin", "_origin", "anchor", "_anchor",
    "start", "_start", "pivot", "_pivot", "from_point", "_from",
    "_grip", "_grip_rot", "dragging", "_drag", "_dragging", "_stroke", "base_face",
    "sizing", "measuring", "_measuring", "puntos", "pts", "_pts", "points", "_points",
)


def _puesto(valor) -> bool:
    """El atributo tiene algo (no None, False ni vacío)."""
    if valor is None or valor is False or callable(valor):
        return False
    if isinstance(valor, (list, tuple, set, dict, str)):
        return bool(valor)
    return True


def _con_senas(tool) -> bool:
    """¿Alguna de las señas de orden a medias está puesta en ``tool``?"""
    return any(_puesto(getattr(tool, nombre, None)) for nombre in SENAS_EN_MARCHA)


# Atributos que cambian solos con el ratón (no delatan una orden a medias).
_SIN_SENA = ("hover", "snap", "cursor", "last", "mouse", "pos", "screen", "preview",
             "cache", "pending", "timer", "_copy", "lock", "tooltip", "status",
             "plane")                    # work_plane: lo que hay bajo el ratón


def _foto_tool(tool) -> dict:
    """Qué atributos de la herramienta tienen algo ahora mismo (para ver
    luego cuáles se han llenado: una orden a medias)."""
    foto = {}
    try:
        items = list(vars(tool).items())
    except TypeError:
        return foto
    for nombre, valor in items:
        if any(s in nombre.lower() for s in _SIN_SENA):
            continue
        foto[nombre] = _puesto(valor)
    return foto


def _pila(viewport):
    pila = getattr(viewport.history, "undo_stack", None)
    return len(pila) if pila is not None else None


def _dot(a, b) -> float:
    return QVector3D.dotProduct(a, b)


def _en_poligono(x: float, y: float, poli) -> bool:
    """Punto dentro de un polígono de pantalla (regla par-impar)."""
    dentro = False
    n = len(poli)
    j = n - 1
    for i in range(n):
        xi, yi = poli[i]
        xj, yj = poli[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


# ---- Encontrar la cara recién creada -------------------------------------------

def _cara_con_puntos(mesh, puntos):
    """La cara que contiene todos ``puntos``. Si las aristas cortaron otras,
    la cara puede tener vértices de más: se prefiere la de menos vértices y,
    a igualdad, la de centro más cercano."""
    if not puntos:
        return None
    centro = QVector3D()
    for p in puntos:
        centro = centro + p
    centro = centro * (1.0 / len(puntos))
    mejor = None
    for cara in list(mesh.faces):
        pts = cara.vertices
        if len(pts) < len(puntos):
            continue
        if not all(any((p - c).lengthSquared() < _TOL2 for p in pts)
                   for c in puntos):
            continue
        clave = (len(pts), (cara.centroid() - centro).lengthSquared())
        if mejor is None or clave < mejor[0]:
            mejor = (clave, cara)
    return None if mejor is None else mejor[1]


# ---- Fase 1: las herramientas del selector ---------------------------------------

class _BaseCadena:
    """Lo común: el cursor alimenta el selector, el primer clic puede ser
    para el selector, y Esc sin nada en curso oculta o muestra el arco."""
    clave = ""
    shortcut = None
    shortcut_alt = None

    def on_hover(self, ctx: ToolContext) -> None:
        self.cadena.cursor_movido(ctx.screen, self)
        super().on_hover(ctx)

    def on_click(self, ctx: ToolContext) -> None:
        if (not self.cadena.ocupada(self)
                and self.cadena.clic_en_selector(ctx.viewport, ctx.screen)):
            return
        super().on_click(ctx)

    def on_cancel(self, viewport) -> None:
        ocioso = not self.cadena.ocupada(self)
        super().on_cancel(viewport)
        if ocioso:
            self.cadena.alternar_arco(viewport)


class RectanguloCadena(_BaseCadena, RectangleTool):
    clave = "rect"
    name = "Rosco LT · rectángulo"
    description = "Draw a rectangle; its face goes straight to Push/Pull."

    def __init__(self, cadena) -> None:
        RectangleTool.__init__(self)
        self.cadena = cadena

    def on_activate(self, viewport) -> None:
        super().on_activate(viewport)          # la nativa vuelve a «esquina»
        if self.cadena.modo["rect"] == "centro":
            self._set_from_center(viewport, True)

    def _commit_rect(self, viewport, corners) -> None:
        pts = [QVector3D(c) for c in corners]
        antes = _pila(viewport)
        super()._commit_rect(viewport, corners)
        self.cadena.base_hecha(viewport, self, pts, antes)


class GiradoCadena(_BaseCadena, RotatedRectangleTool):
    """Rectángulo de tres clics: un lado y el fondo. En modo «lado» el primer
    lado va por los ejes del plano de dibujo; en «girado», donde sea."""
    clave = "rect"
    name = "Rosco LT · rectángulo por lado"
    icon = "rotated_rect"

    def __init__(self, cadena) -> None:
        RotatedRectangleTool.__init__(self)
        self.cadena = cadena

    def _por_ejes(self) -> bool:
        return (self.cadena.modo["rect"] == "lado" and self.start_point is not None
                and self.base_point is None)

    def _a_eje(self, p):
        """``p`` llevado al eje del plano (u o v) que más se parece a la
        dirección desde el primer punto."""
        from core.axes import plane_axes
        u, v = plane_axes(self._normal())
        d = p - self.start_point
        du, dv = _dot(d, u), _dot(d, v)
        return self.start_point + (u * du if abs(du) >= abs(dv) else v * dv)

    def on_hover(self, ctx: ToolContext) -> None:
        super().on_hover(ctx)
        if self._por_ejes() and self.hover_point is not None:
            self.hover_point = self._a_eje(self.hover_point)

    def on_click(self, ctx: ToolContext) -> None:
        if self._por_ejes():
            ctx = dataclasses.replace(ctx, world=self._a_eje(ctx.world))
        super().on_click(ctx)

    def _width_and_angle(self, cursor, forced=None):
        """En «lado» el fondo se queda en el plano de dibujo (el rectángulo
        tumbado): solo cuenta la distancia al lado, hacia un lado u otro. En
        «girado» manda la nativa (que también deja inclinarlo)."""
        if self.cadena.modo["rect"] != "lado" or self.base_point is None:
            return super()._width_and_angle(cursor, forced)
        perp = self._perp()
        if perp.length() < 1e-6:
            return 0.0, 0.0
        w = _dot(cursor - self.base_point, perp)
        return abs(w), (0.0 if w >= 0.0 else 180.0)

    def _commit(self, viewport, corners) -> None:
        pts = [QVector3D(c) for c in corners]
        antes = _pila(viewport)
        super()._commit(viewport, corners)
        self.cadena.base_hecha(viewport, self, pts, antes)


class _RadialCadena(_BaseCadena):
    """Polígono y círculo: el modo centro es el nativo; el modo lado/diámetro
    toma el primer clic como un extremo y el segundo como el otro."""

    def _por_lado(self) -> bool:
        return self.cadena.modo[self.clave] != "centro"

    def _points(self, a, b):
        if not self._por_lado():
            return super()._points(a, b)
        u, v = self._axes()
        d = b - a
        du, dv = _dot(d, u), _dot(d, v)
        s = math.hypot(du, dv)
        if s < 1e-6:
            return []
        en_plano = u * du + v * dv
        if self.clave == "circle":
            # Diámetro: centro en el punto medio, un vértice en el segundo clic.
            medio = a + en_plano * 0.5
            return super()._points(medio, a + en_plano)
        n = max(int(self.sides), 3)
        ex, ey = du / s, dv / s
        apotema = s / (2.0 * math.tan(math.pi / n))
        radio = s / (2.0 * math.sin(math.pi / n))
        # El polígono queda a la izquierda de la arista a → b (sentido
        # antihorario en el plano de dibujo); a y b son dos vértices seguidos.
        centro = a + en_plano * 0.5 + (u * (-ey) + v * ex) * apotema
        ca = a - centro
        a0 = math.atan2(_dot(ca, v), _dot(ca, u))
        return [centro + (u * math.cos(a0 + 2.0 * math.pi * k / n)
                          + v * math.sin(a0 + 2.0 * math.pi * k / n)) * radio
                for k in range(n)]

    def value_label(self):
        if (not self._por_lado() or self.start_point is None
                or self.hover_point is None):
            return super().value_label()
        u, v = self._axes()
        d = self.hover_point - self.start_point
        s = math.hypot(_dot(d, u), _dot(d, v))
        prefijo = "Ø " if self.clave == "circle" else "L "
        return (_tr("{0}{1}  ({2} lados)", prefijo, fmt_len(s), int(self.sides)),
                self.hover_point)

    def on_value(self, viewport, value) -> bool:
        if (self._por_lado() and self.start_point is not None
                and not isinstance(value, tuple)):
            # Lo tecleado es la longitud del lado (o el diámetro), en la
            # dirección hacia la que apunta el cursor.
            if self.hover_point is None or value <= 0.0:
                return False
            u, v = self._axes()
            d = self.hover_point - self.start_point
            ang = math.atan2(_dot(d, v), _dot(d, u))
            b = self.start_point + (u * math.cos(ang) + v * math.sin(ang)) * value
            pts = self._points(self.start_point, b)
            if pts:
                self._commit(viewport, pts)
            return True
        return super().on_value(viewport, value)

    def _commit(self, viewport, pts) -> None:
        copia = [QVector3D(p) for p in pts]
        antes = _pila(viewport)
        super()._commit(viewport, pts)
        self.cadena.base_hecha(viewport, self, copia, antes)


class PoligonoCadena(_RadialCadena, PolygonTool):
    clave = "poly"
    name = "Rosco LT · polígono"
    icon = "polygon"

    def __init__(self, cadena) -> None:
        PolygonTool.__init__(self)
        self.cadena = cadena


class CirculoCadena(_RadialCadena, CircleTool):
    clave = "circle"
    name = "Rosco LT · círculo"
    icon = "circle"

    def __init__(self, cadena) -> None:
        CircleTool.__init__(self)
        self.cadena = cadena


class LineaCadena(_BaseCadena, LineTool):
    """Polilínea: al cerrarse en su primer punto, su cara pasa a la altura."""
    clave = "line"
    name = "Rosco LT · polilínea"
    icon = "line"

    def __init__(self, cadena) -> None:
        LineTool.__init__(self)
        self.cadena = cadena

    def on_click(self, ctx: ToolContext) -> None:
        if (self.start_point is None
                and self.cadena.clic_en_selector(ctx.viewport, ctx.screen)):
            return
        vp = ctx.viewport
        antes = [QVector3D(p) for p in self.chain_vertices]
        pila = _pila(vp)
        LineTool.on_click(self, ctx)
        puntos = None
        if self.start_point is None and len(antes) >= 3:
            # La nativa reinicia la cadena al cerrar (snap «cerrar»).
            puntos = antes
        elif (self.start_point is not None and len(self.chain_vertices) >= 4
              and (self.chain_vertices[-1] - self.chain_vertices[0])
              .lengthSquared() < 1e-12):
            # Cerrada con otro snap sobre el primer punto: también vale.
            puntos = [QVector3D(p) for p in self.chain_vertices[:-1]]
            self._reset()
        if puntos is not None:
            self.cadena.base_hecha(vp, self, puntos, pila)


class LineaLibreCadena(LineaCadena):
    """El botón Línea: líneas encadenadas; si cierran una cara, a la altura."""
    clave = "linea"
    name = "Rosco LT · línea"


class GuiaCadena(_BaseCadena, LineTool):
    """Línea guía (de construcción) por dos puntos, como las de la cinta."""
    clave = "linea"
    name = "Rosco LT · línea guía"
    icon = "tape"

    def __init__(self, cadena) -> None:
        LineTool.__init__(self)
        self.cadena = cadena

    def on_click(self, ctx: ToolContext) -> None:
        if self.start_point is None:
            if self.cadena.clic_en_selector(ctx.viewport, ctx.screen):
                return
            LineTool.on_click(self, ctx)       # primer punto
            return
        self._poner_guia(ctx.viewport, QVector3D(self.start_point),
                         QVector3D(ctx.world))

    def on_value(self, viewport, value) -> bool:
        if (self.start_point is None or self.hover_point is None
                or isinstance(value, tuple)):
            return False
        d = self.hover_point - self.start_point
        if d.length() < 1e-9 or value == 0.0:
            return False
        self._poner_guia(viewport, QVector3D(self.start_point),
                         self.start_point + d.normalized() * value)
        return True

    def _poner_guia(self, viewport, a, b) -> None:
        if (b - a).length() < 1e-6:
            return
        from core.guide import Guide
        from core.history import AddGuideCommand
        viewport.history.execute(AddGuideCommand(Guide(a, b - a)))
        self._reset()
        viewport.update()
        viewport.flash_status(_tr("Línea guía creada. Clic en dos puntos para otra."), 3000)


class BorradorCadena(_BaseCadena, EraserTool):
    """El borrador nativo; en modo «ocultar», como con Mayús: oculta."""
    clave = "borrar"
    name = "Rosco LT · borrar"
    icon = "eraser"

    def __init__(self, cadena) -> None:
        EraserTool.__init__(self)
        self.cadena = cadena

    def on_click(self, ctx: ToolContext) -> None:
        if (not self._stroke
                and self.cadena.clic_en_selector(ctx.viewport, ctx.screen)):
            return
        EraserTool.on_click(self, ctx)
        if self.cadena.modo["borrar"] == "ocultar" and not self._hide:
            from core.group import Group
            from core.mesh import Edge
            self._hide = True
            # Solo aristas y objetos se ocultan (como el trazo con Mayús).
            self.marked = {m for m in self.marked if isinstance(m, (Edge, Group))}


class SeleccionCadena(_BaseCadena, SelectTool):
    """Seleccionar nativo; en modo «lazo», la ventana la sustituye el lazo
    que dibuja la cadena (``Cadena._lazo``)."""
    clave = "seleccionar"
    name = "Rosco LT · seleccionar"

    def __init__(self, cadena) -> None:
        SelectTool.__init__(self)
        self.cadena = cadena

    @property
    def box_select(self):                      # type: ignore[override]
        return self.cadena.modo["seleccionar"] == "ventana"


class _ArcoCadena(_BaseCadena):
    """Los arcos nativos. La porción cierra su cara con el centro y pasa a la
    altura; los demás arcos solo si cierran una cara con lo que ya hay."""
    clave = "arco"
    porcion = False

    def _commit(self, viewport, pts, *args, **kwargs) -> None:
        copia = [QVector3D(p) for p in pts]
        centro = (QVector3D(self.start_point)
                  if self.porcion and self.start_point is not None else None)
        antes = _pila(viewport)
        super()._commit(viewport, pts, *args, **kwargs)
        if centro is not None:
            copia.append(centro)
        self.cadena.base_hecha(viewport, self, copia, antes,
                               silencioso=centro is None)


class ArcoCadena(_ArcoCadena, ArcTool):
    name = "Rosco LT · arco"
    icon = "arc"

    def __init__(self, cadena) -> None:
        ArcTool.__init__(self)
        self.cadena = cadena


class Arco3Cadena(_ArcoCadena, ThreePointArcTool):
    name = "Rosco LT · arco por 3 puntos"
    icon = "arc3"

    def __init__(self, cadena) -> None:
        ThreePointArcTool.__init__(self)
        self.cadena = cadena


class ArcoCentroCadena(_ArcoCadena, CenterArcTool):
    name = "Rosco LT · arco por centro"
    icon = "center_arc"

    def __init__(self, cadena) -> None:
        CenterArcTool.__init__(self)
        self.cadena = cadena


class PorcionCadena(_ArcoCadena, PieTool):
    name = "Rosco LT · porción"
    icon = "pie"
    porcion = True

    def __init__(self, cadena) -> None:
        PieTool.__init__(self)
        self.cadena = cadena


class CotaCadena(_BaseCadena, DimensionTool):
    clave = "medir"
    name = "Rosco LT · cota"
    icon = "dimension"

    def __init__(self, cadena) -> None:
        DimensionTool.__init__(self)
        self.cadena = cadena


class CintaCadena(_BaseCadena, TapeMeasureTool):
    clave = "medir"
    name = "Rosco LT · medir"
    icon = "tape"

    def __init__(self, cadena) -> None:
        TapeMeasureTool.__init__(self)
        self.cadena = cadena


class EquidistanciaCadena(_BaseCadena, OffsetTool):
    clave = "linea"
    name = "Rosco LT · equidistancia"
    icon = "offset"

    def __init__(self, cadena) -> None:
        OffsetTool.__init__(self)
        self.cadena = cadena


class RedondeoCadena(_BaseCadena, FilletTool):
    clave = "linea"
    name = "Rosco LT · redondear 3D"
    icon = "fillet"

    def __init__(self, cadena) -> None:
        FilletTool.__init__(self)
        self.cadena = cadena


def _tramo_de(mesh, arista):
    """Los puntos, en orden, de la línea a la que pertenece ``arista``: se
    sigue por los vértices de los que solo salen dos aristas (una línea sin
    ramificaciones). Devuelve ``(puntos, cerrada)``."""
    va, vb = mesh.vertex_at(arista.a), mesh.vertex_at(arista.b)
    if va is None or vb is None:
        return [QVector3D(arista.a), QVector3D(arista.b)], False
    usadas = {id(arista)}

    def andar(v):
        out = []
        while len(v.edges) == 2:
            siguientes = [e for e in v.edges if id(e) not in usadas]
            if not siguientes:
                break
            e = siguientes[0]
            usadas.add(id(e))
            v = e.other(v)
            out.append(v)
        return out

    hacia_b = andar(vb)
    if hacia_b and hacia_b[-1] is va:
        # Volvió al principio: una línea cerrada.
        return [QVector3D(v.position) for v in [va, vb] + hacia_b[:-1]], True
    hacia_a = andar(va)
    orden = list(reversed(hacia_a)) + [va, vb] + hacia_b
    return [QVector3D(v.position) for v in orden], False


class ParalelaCadena(_BaseCadena, Tool):
    """Paralela a un segmento o a una línea abierta (o cerrada sin cara): clic
    en la línea, el ratón da el lado y la distancia (o se teclea). Para
    varias aristas usa el mismo cálculo de esquinas que la Equidistancia de
    IngeTrazo (``core.offset.offset_chain``)."""
    clave = "linea"
    name = "Rosco LT · paralela"
    icon = "offset"
    vcb_label = "Distance"
    wireframe_color = (0.84, 0.13, 0.13, 1.0)

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        self._reset()

    def _reset(self) -> None:
        self.start_point = None              # la cadena elegida (para «ocupada»)
        self.hover_point = None
        self.hover_edge = None
        self._pts: list = []
        self._cerrada = False
        self._normal = None
        self.distancia = 0.0

    def on_activate(self, viewport) -> None:
        self._reset()

    def on_deactivate(self, viewport) -> None:
        viewport.set_hover(None)
        self._reset()

    def on_cancel(self, viewport) -> None:
        ocioso = self.start_point is None
        viewport.set_hover(None)
        self._reset()
        viewport.update()
        if ocioso:
            self.cadena.alternar_arco(viewport)

    # -- geometría --
    def _plano(self, viewport):
        """Normal del plano de la línea; para una línea recta, el suelo (o,
        si es vertical, el plano que mira a la cámara)."""
        pts = self._pts
        n = QVector3D()
        for i in range(len(pts) - 2):
            c = QVector3D.crossProduct(pts[i + 1] - pts[i], pts[i + 2] - pts[i + 1])
            if c.length() > 1e-9:
                n = n + (c.normalized() if _dot(c, n) >= 0 else -c.normalized())
        if n.length() > 1e-9:
            return n.normalized()
        d = (pts[-1] - pts[0]).normalized()
        if abs(d.z()) < 0.95:
            return QVector3D(0.0, 0.0, 1.0)
        cam = viewport.camera
        f = cam.target - cam.eye()
        f = f - d * _dot(f, d)
        return f.normalized() if f.length() > 1e-9 else QVector3D(1.0, 0.0, 0.0)

    def _desplazados(self, d):
        """La línea desplazada ``d`` (con signo) en su plano."""
        pts, n = self._pts, self._normal
        if len(pts) >= 3:
            try:
                from core.offset import offset_chain
                res = list(offset_chain(pts, n, d))
                if self._cerrada and res and (res[0] - res[-1]).length() > 1e-9:
                    res.append(QVector3D(res[0]))
                # Que el lado sea el del cursor, sea cual sea el convenio.
                lado = QVector3D.crossProduct(n, (pts[1] - pts[0]).normalized())
                if res and _dot(res[0] - pts[0], lado) * d < 0:
                    res = list(offset_chain(pts, n, -d))
                    if self._cerrada and res:
                        res.append(QVector3D(res[0]))
                return res
            except Exception:  # noqa: BLE001 — el cálculo propio de abajo
                log.exception("offset_chain no sirvió; uso el cálculo propio")
        dirs = [(pts[i + 1] - pts[i]).normalized() for i in range(len(pts) - 1)]
        normales = [QVector3D.crossProduct(n, di).normalized() for di in dirs]
        out = []
        for k, p in enumerate(pts):
            if k == 0:
                out.append(p + normales[0] * d)
            elif k == len(pts) - 1:
                out.append(p + normales[-1] * d)
            else:
                m = normales[k - 1] + normales[k]
                if m.length() < 1e-9:
                    out.append(p + normales[k] * d)
                    continue
                m = m.normalized()
                coseno = max(_dot(m, normales[k]), 0.2)
                out.append(p + m * (d / coseno))
        return out

    def _distancia_al_cursor(self, p):
        """Distancia con signo del cursor (llevado al plano) a la línea."""
        pts, n = self._pts, self._normal
        q = p - n * _dot(p - pts[0], n)
        mejor = None
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            ab = b - a
            t = max(0.0, min(1.0, _dot(q - a, ab) / max(_dot(ab, ab), 1e-12)))
            cerca = a + ab * t
            dist = (q - cerca).length()
            if mejor is None or dist < mejor[0]:
                lado = QVector3D.crossProduct(n, ab.normalized())
                mejor = (dist, _dot(q - a, lado))
        return mejor[1] if mejor else 0.0

    # -- ratón --
    def on_hover(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        self.cadena.cursor_movido(ctx.screen, self)
        if self.start_point is None:
            self.hover_edge = vp.pick_edge(ctx.screen.x(), ctx.screen.y())
            vp.set_hover(self.hover_edge)
        else:
            self.hover_point = QVector3D(ctx.world)
            self.distancia = self._distancia_al_cursor(self.hover_point)
        vp.update()

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        if self.start_point is None:
            if self.cadena.clic_en_selector(vp, ctx.screen):
                return
            arista = vp.pick_edge(ctx.screen.x(), ctx.screen.y())
            if arista is None:
                vp.flash_status(_tr("Paralela: haz clic sobre una línea o un segmento."), 4000)
                return
            self._pts, self._cerrada = _tramo_de(vp.scene.mesh, arista)
            if len(self._pts) < 2:
                return
            if self._cerrada:
                self._pts = self._pts + [QVector3D(self._pts[0])]
            self._normal = self._plano(vp)
            self.start_point = QVector3D(self._pts[0])
            self.hover_point = QVector3D(ctx.world)
            vp.set_hover(None)
            vp.flash_status(_tr("Paralela: lleva el ratón al lado y haz clic, o teclea "
                            "la distancia + Enter. Esc cancela."), 6000)
            vp.update()
            return
        d = self._distancia_al_cursor(QVector3D(ctx.world))
        if abs(d) < 1e-6:
            return
        self._poner(vp, d)

    def on_value(self, viewport, value) -> bool:
        if self.start_point is None or isinstance(value, tuple) or value == 0.0:
            return False
        signo = -1.0 if self.distancia < 0 else 1.0
        self._poner(viewport, signo * abs(value))
        return True

    def _poner(self, viewport, d) -> None:
        pts = self._desplazados(d)
        if len(pts) < 2:
            return
        from core.edits import build_add_edges
        tramos = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)
                  if (pts[i + 1] - pts[i]).length() > 1e-9]
        viewport.history.execute(build_add_edges(viewport.scene, tramos,
                                                 detect_faces=False))
        error = viewport.history.last_error
        self._reset()
        viewport.notify_scene_changed()
        viewport.flash_status(_tr(_tr("Paralela: no se pudo crear: {0}", error) if error else
                              _tr("Paralela creada a {0}. Clic en otra línea para otra.", fmt_len(abs(d)))), 4000)

    def rubber_band_lines(self):
        if self.start_point is None or self.hover_point is None:
            return []
        pts = self._desplazados(self.distancia)
        return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]

    def value_label(self):
        if self.start_point is None or self.hover_point is None:
            return None
        return (fmt_len(abs(self.distancia)), self.hover_point)


class EsperaCadena(_BaseCadena, Tool):
    """La barra de dibujo recién llamado, sin herramienta elegida: solo la barra. Un clic
    fuera de ella (o Esc) cierra la barra de dibujo y deja Seleccionar de IngeTrazo."""
    clave = "espera"
    name = "Rosco LT"
    description = "Choose a tool on the Rosco LT bar."
    uses_snap = False
    start_point = None

    def __init__(self, cadena) -> None:
        self.cadena = cadena

    def on_activate(self, viewport) -> None:
        pass

    def on_deactivate(self, viewport) -> None:
        pass

    def on_hover(self, ctx: ToolContext) -> None:
        self.cadena.cursor_movido(ctx.screen, self)

    def on_click(self, ctx: ToolContext) -> None:
        if self.cadena.clic_en_selector(ctx.viewport, ctx.screen):
            return
        cadena = self.cadena
        QTimer.singleShot(0, lambda: cadena.cerrar_barra_dibujo(ctx))

    def on_cancel(self, viewport) -> None:
        QTimer.singleShot(0, self.cadena.cerrar_barra_dibujo)


# ---- Fase 2: empujar / tirar ----------------------------------------------------

class EmpujarCadena(PushPullTool):
    name = "Rosco LT · altura"
    shortcut = None
    shortcut_alt = None
    icon = "pushpull"                    # el cursor de Empujar/Tirar

    def __init__(self, cadena) -> None:
        super().__init__()
        self.cadena = cadena

    def on_activate(self, viewport) -> None:
        super().on_activate(viewport)
        # La nativa se «arma» sobre una cara seleccionada; aquí la cara la da
        # la cadena, así que se deshace ese armado.
        if self._selected_arm:
            self._selected_arm = False
            self.hovered_face = None
            viewport.set_hover(None)

    def enganchar(self, viewport, cara) -> bool:
        """Empieza el arrastre sobre ``cara`` como si el usuario hubiera hecho
        el primer clic de Empujar/Tirar. Devuelve si quedó arrastrando."""
        self.hovered_face = cara
        self._hover_group = None
        self._selected_arm = False
        pos = self.cadena.cursor_px
        if pos is None:
            pos = getattr(viewport, "_last_mouse_pos", None)
        if pos is None:
            pos = QPointF(viewport.width() * 0.5, viewport.height() * 0.5)
        ctx = ToolContext(viewport=viewport, world=cara.centroid(),
                          screen=QPointF(pos), modifiers=Qt.NoModifier,
                          snap=None)
        self.on_click(ctx)
        # Solo ritmo clic-clic: soltar el botón del último clic de la base no
        # debe confirmar la altura (ver PushPullTool.on_release).
        self._press_screen = None
        return bool(self.dragging)

    def on_hover(self, ctx: ToolContext) -> None:
        self.cadena.anotar_cursor(ctx.screen)
        super().on_hover(ctx)

    def _commit(self, viewport) -> None:
        arrastrando = self.dragging
        antes = _pila(viewport)
        super()._commit(viewport)
        ahora = _pila(viewport)
        if (arrastrando and not viewport.history.last_error
                and antes is not None and ahora is not None and ahora > antes):
            self.cadena.empuje_hecho(viewport)
        if arrastrando and not self.dragging:
            self.cadena.volver_a_la_base(viewport)

    def on_cancel(self, viewport) -> None:
        super().on_cancel(viewport)
        self.cadena.olvidar_antes()
        self.cadena.volver_a_la_base(viewport)


# ---- La cadena: estado, selector, ventanitas, menú y barra ------------------------

class Cadena:
    @property
    def tema(self) -> _temas.Tema:
        return self._tema

    @tema.setter
    def tema(self, t: _temas.Tema) -> None:
        # Con el tema B todos los iconos de Rosco LT van en silueta negra
        # (también en la vista previa del menú de temas); con C a N, en
        # líneas y sombreado, y el rojo de la barra pasa al color del tema.
        self._tema = t
        _iconos.SILUETAS = bool(t.glifos)
        _flotante.poner_paleta(t.paleta)

    @property
    def panel(self) -> str | None:
        """El botón cuyo submenú está abierto (o None)."""
        return self._panel_abierto

    @panel.setter
    def panel(self, clave: str | None) -> None:
        # Al abrir un submenú se recuerda dónde estaba el ratón (desde el
        # centro del anillo): en los temas A y B sale a su lado.
        antes = getattr(self, "_panel_abierto", None)
        if clave == "vistas" and antes != "vistas":
            # La rueda abierta desde un submenú: al salir de ella se vuelve a él.
            self._antes_rueda = ((antes, QPointF(getattr(self, "_panel_raton", QPointF())))
                                 if antes in MODOS or antes in CON_CAJETINES else None)
        if clave is not None and clave != antes:
            ancla, raton = getattr(self, "ancla", None), getattr(self, "cursor_px", None)
            self._panel_raton = (QPointF(raton.x() - ancla.x(), raton.y() - ancla.y())
                                 if ancla is not None and raton is not None else QPointF(0.0, 0.0))
        if clave != "vistas":
            self._ojo_rosco = None            # la rueda vuelve a su ojo de siempre
        self._panel_abierto = clave

    def __init__(self, app) -> None:
        self.app = app
        self.bases = {"rect": RectanguloCadena(self), "poly": PoligonoCadena(self),
                      "circle": CirculoCadena(self),
                      "linea": LineaLibreCadena(self),
                      "borrar": BorradorCadena(self),
                      "seleccionar": SeleccionCadena(self)}
        self.girado = GiradoCadena(self)
        self.guia = GuiaCadena(self)
        # Herramientas según la opción del submenú de cada botón.
        self.por_modo = {
            ("arco", "arco"): ArcoCadena(self),
            ("arco", "3 puntos"): Arco3Cadena(self),
            ("arco", "centro"): ArcoCentroCadena(self),
            ("arco", "porción"): PorcionCadena(self),
            ("medir", "cota"): CotaCadena(self),
            ("medir", "medir"): CintaCadena(self),
            ("linea", "guía"): self.guia,
            ("linea", "equidist."): EquidistanciaCadena(self),
            ("linea", "paralela"): ParalelaCadena(self),
            ("linea", "redondear"): RedondeoCadena(self),
            ("rect", "lado"): self.girado,
            ("rect", "girado"): self.girado,
        }
        self._todas = list(self.bases.values()) + [
            t for t in self.por_modo.values()
            if not any(t is o for o in self.bases.values())]
        self._todas = [t for i, t in enumerate(self._todas)
                       if not any(t is o for o in self._todas[:i])]
        self.base = None                      # la herramienta elegida (ninguna al llamar)
        self.modo = {clave: modos[0] for clave, modos in MODOS.items()}
        self.modo["grupo"] = "nada"           # al terminar: nada, grupo o componente
        self.pedir_nombre = False             # grupo: pedir el nombre al crearlo
        self._antes_clic = (False, False)     # (barra a la vista, orden a medias) al pulsar
        self._pila_al_pulsar = None           # el historial al pulsar el izquierdo
        self._pila_ultima = None              # la de la última orden acabada
        self._pila_orden0 = None              # orden que sigue: el historial al empezarla
        self._tool_orden0 = None              # … y de qué herramienta
        self._cargar_grupo()                  # la opción de Grupo se recuerda
        self.espera = EsperaCadena(self)      # La barra de dibujo sin herramienta elegida
        self._todas.append(self.espera)
        self.push = EmpujarCadena(self)
        self.cursor_px: QPointF | None = None
        self.buffer = ""
        # Selector
        self.arco_visible = True
        self.ancla: QPointF | None = None     # centro de los arcos (px del visor)
        self.panel: str | None = None         # botón cuyo submenú está abierto
        self._bajo: str | None = None         # botón bajo el cursor
        self.fijo = False                     # barra fija (ventanita) o cursor
        # El rosco en espera, pulsando en vacío (ver ``_evento_espera``).
        self._pulso_espera = None             # el evento de pulsar: (pos, global, teclas)
        self._pulso_largo = False             # ya es pulsación larga: se ve el modelo
        self._reloj_espera = None
        self._pasar_clic = False              # el clic repetido no se vuelve a retener
        # La línea de órdenes (``_linea``): el paso a paso de la orden en curso.
        self.linea = None
        self._clics_orden = 0
        self._linea_tool = None
        self._cursor_barra = None             # el cursor puesto sobre los botones
        self._ayuda_pagina = 0                # la pestaña abierta de la ayuda
        self._reloj_anima = None
        self._anima_esc = AYUDA_ESCENAS[0]    # el gesto que enseña la pantallita
        self._anima_t = time.monotonic()
        self._anima_fila = None               # los gestos de la fila bajo el ratón
        self._ayuda_cache = None
        # El botón derecho: qué espera el clic retenido («orden» o «rosco») y su reloj.
        self._derecho = None
        self._reloj_derecho = None
        self._tragar_menu = False             # el menú contextual de este clic no sale
        # El dictado de medidas tras cada punto (Opciones).
        self._dictado_llave = None            # (orden, clics, medidas aplicadas) ya atendidos
        self.anclada = False                  # chincheta: fija y siempre visible
        self.escala = _temas.escala_guardada()
        self.tema = _temas.escalar(_temas.guardado(), self.escala)   # la maquetación del anillo
        # Qué va en cada hueco (temas con rueda): se configura desde
        # el gestor de barras, apartado «Barra Rosco LT».
        self.huecos = _huecos.Huecos(self._huecos_defecto(), tuple(CHICOS_F.values()),
                                     al_cambiar=self._huecos_cambiados)
        self._poner_rueda()
        _diana.NOMBRE_CORTO = self._texto_icono       # etiquetas de gajos y disco
        self.escondida = False                # Simetría: todo oculto hasta que termine
        self._tool_escondida = None
        self._estaba_en_marcha = False
        self._pila_al_empezar = None          # el historial cuando empezó la orden
        # Tras cada orden (opción «esconder_tras») la barra se duerme: queda
        # Seleccionar y no vuelve hasta un clic en el vacío o una selección.
        self.dormida = False
        self._sel_dormida = frozenset()       # la selección al dormirse
        self._pila_vista = None               # el historial en el último repaso
        self._obra = False                    # la orden en curso ya hizo algo
        self._altura_pendiente = False        # base hecha, la altura aún no empezó
        self._foto_tool0: dict = {}           # la herramienta nativa recién activada
        self._cancelando = False              # cancelar sin apagar el selector
        self._es_sel = False                  # la barra es la de selección
        self.win = None
        self._filtro = None
        self._reloj = None
        self._reposo = None
        self._pendiente = False
        self._cursor = None                   # los arcos como cursor
        self._cursor_clave = None
        self._cursor_puesto = False
        self._estado_pintado = None
        self._fondo = None                    # la barra fija sin el ratón: (clave, QPixmap)
        self._cache_sel = None                # (firma, resumen, capa) de la selección
        self._etiqueta_w = None               # la etiqueta más ancha (para la máscara)
        self.cancelar = None                  # el botoncito de cancelar, en su ventanita
        # El historial del ojo amarillo: [(nombre, repetir)], lo último primero.
        self.historial: list = []
        self._historial_v = 0
        self._ultima_tool = None
        self._tic_acciones = 0
        # Aplicar capa: lo que se vaya seleccionando pasa a la capa actual.
        self.aplicar_capa = False
        self._ids_aplicados: frozenset = frozenset()
        # Grupo / componente: lo que había antes de la pieza en curso.
        self._antes = None
        # Lazo de selección en curso (px del visor) y sus modificadores.
        self._lazo: list | None = None
        self._lazo_mods = Qt.NoModifier
        # Diana (vistas, zoom, deshacer, buscador) y la herramienta a la que
        # volver tras el encuadre.
        self.diana = Diana(app, al_encuadre=self._encuadre,
                           al_terminar=self._sincronizar)
        self._tras_encuadre = None
        # La capa de dibujo y dónde va su pastilla en la barra.
        self.capas = Capas(self)
        self.pos_capa = "abajo"
        # El desplegable Navegador (espejo del panel), al lado de la capa.
        self.navegador = Navegador(self)
        # Los menús de IngeTrazo en árbol (botón junto a la lupa / la chincheta).
        self.menus_arbol = None
        self._tragar_hasta = 0.0              # descartar el clic que cerró un desplegable
        # Control de tiempo: el cronómetro cuenta siempre; el panel, a demanda.
        self.crono = None
        self.panel_tiempo = None
        # La calculadora suelta (botoncito bajo Apagar) y la Pantalla limpia
        # por partes, a demanda.
        self.calculadora = None
        self.limpieza = None
        # Submenús en rectángulo (de siempre) o en rosco (``_rosco``).
        self.submenus_radiales = _seleccion.forma_submenus() == "radial"
        self.distancia_submenu = _seleccion.distancia_submenu()     # Opciones, en px
        self.sitio_submenu = _seleccion.sitio_submenu()             # «derecha» o «centro»
        self.escala_rosco = _seleccion.escala_rosco()               # Opciones, en %
        # La ventanita de medidas (renglones y calculadora).
        self.medidas = None

    # -- la opción de Grupo, recordada entre sesiones --
    @staticmethod
    def _ajustes():
        from ._ajustes import ajustes
        return ajustes("anillo")

    def _cargar_grupo(self) -> None:
        try:
            s = self._ajustes()
            modo = s.value("grupo/modo", "nada")
            if modo in ("nada", "grupo", "componente"):
                self.modo["grupo"] = modo
            pedir = s.value("grupo/pedir_nombre", False)
            self.pedir_nombre = (pedir.strip().lower() in ("1", "true")
                                 if isinstance(pedir, str) else bool(pedir))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo leer la opción de Grupo")

    def _guardar_grupo(self) -> None:
        try:
            s = self._ajustes()
            s.setValue("grupo/modo", self.modo["grupo"])
            s.setValue("grupo/pedir_nombre", bool(self.pedir_nombre))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar la opción de Grupo")

    def cerrar_barra_dibujo(self, ctx=None) -> None:
        """Clic fuera de la barra sin herramienta elegida (o Esc): se cierra
        la barra de dibujo y queda Seleccionar de IngeTrazo; el clic, si lo hubo, le llega
        a Seleccionar (selecciona lo que haya debajo, o nada)."""
        vp = self.app.viewport
        self._soltar()
        self.aplicar_capa = False            # se apaga al cerrar la barra
        sel = self._a_seleccionar(vp)
        if ctx is not None and sel is not None and vp.active_tool is sel:
            try:
                # El clic que cierra la barra de dibujo no cuenta como «clic en el vacío»
                # (volvería a abrir la barra de dibujo): va al Seleccionar sin ese añadido.
                getattr(sel, "_clic_original", sel.on_click)(ctx)
            except Exception:  # noqa: BLE001
                log.exception("Seleccionar no aceptó el clic")
        self._sincronizar()
        vp.update()

    def _a_seleccionar(self, vp):
        """Deja puesto el Seleccionar de IngeTrazo (y lo devuelve)."""
        win = self.app.window
        activar = getattr(win, "_activate_tool", None)       # interno de 0.5.8
        sel = (getattr(win, "_tools", None) or {}).get("select")
        try:
            if callable(activar) and sel is not None:
                activar("select")
            elif sel is not None:
                vp.set_active_tool(sel)
            else:
                vp.set_active_tool(None)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo volver a Seleccionar")
        return sel

    # -- dormirse tras cada orden (salvo Seleccionar) --
    @staticmethod
    def _ids_sel(viewport) -> frozenset:
        try:
            return frozenset(id(e) for e in viewport.scene.selection)
        except Exception:  # noqa: BLE001
            return frozenset()

    def _de_la_barra(self, viewport) -> bool:
        """La herramienta activa es de las que da la barra (y no Seleccionar):
        las de la barra de dibujo y su altura, Pintar y las de la barra de modificar."""
        tool = viewport.active_tool
        if tool is None or tool is self._select_nativo() or tool is self.bases["seleccionar"]:
            return False
        return (self._es_base(tool) or tool is self.push or self._pintando(viewport)
                or self._semi_activa(viewport) is not None
                or tool is getattr(self, "simetria", None))

    def _seguir_orden(self, viewport) -> bool:
        """Las órdenes de dibujar y de modificar del rosco siguen activas tras
        cada uso (sin la barra) hasta el clic derecho (terminar) o el doble
        clic izquierdo (cancelar). Texto no: se queda sola y su doble clic
        edita un texto; Alinear tampoco: necesita una selección nueva."""
        return self._de_la_barra(viewport)

    def _editando(self, viewport) -> bool:
        """Una orden de editar (las de modificar y Alinear)."""
        if self._modificando(viewport):
            return True
        barra = self._barra_modificar()
        try:
            return barra is not None and barra._clave_activa(viewport) == "align"
        except Exception:  # noqa: BLE001
            return False

    def _modificando(self, viewport) -> bool:
        return (self._semi_activa(viewport) is not None
                or viewport.active_tool is getattr(self, "simetria", None))

    def _seguir(self, viewport) -> None:
        """Una orden acabada que sigue: la barra se esconde y, si es de
        modificar, se suelta la selección (la próxima vez, lo que haya bajo
        el cursor)."""
        if self._pila_orden0 is None:
            self._pila_orden0 = self._pila_ultima   # para «un paso atrás»
        self._obra = False
        self.dormida = True
        self.panel = None
        self.escondida = False
        simetria = getattr(self, "simetria", None)
        copiando = viewport.active_tool is simetria and getattr(simetria, "copiando", False)
        barra = self._barra_modificar()
        if barra is not None and not copiando:
            # Desplazar o Rotar con copia vuelven a coger lo mismo para otra copia.
            from ._arco import COPIA
            try:
                clave = barra._clave_activa(viewport)
                copiando = clave in COPIA and barra.modo.get(clave) == COPIA[clave]
            except Exception:  # noqa: BLE001
                copiando = False
        # Escalar no: sin selección no hay caja ni tiradores que pinchar.
        if (self._modificando(viewport) and not copiando and viewport.scene.selection
                and self._semi_activa(viewport) != "scale"):
            viewport.scene.select([], mode="replace")
            viewport.notify_scene_changed()
        self._sel_dormida = self._ids_sel(viewport)
        self._soltar()
        self._sincronizar()

    def _orden_hecha(self, viewport) -> None:
        """Algo terminó de hacerse (un dibujo, un movimiento, borrar…): se
        mira en cuanto la herramienta ha dicho si sigue (la barra de dibujo pasa de la
        base a la altura; la línea encadena tramos). También dormida: lo
        repetido con doble clic acaba igual, en Seleccionar."""
        if not _seleccion.opcion("esconder_tras"):
            return
        self._obra = True
        tool = viewport.active_tool
        if tool is self.push:
            tool = self.herramienta
        if self._es_base(tool):
            self._apuntar_herramienta(viewport, tool)   # el doble clic: con este modo
        QTimer.singleShot(0, lambda: self._quizas_dormir(viewport))

    def _quizas_dormir(self, viewport) -> None:
        if not self._obra:
            return
        if (self._en_marcha(viewport) or viewport.active_tool is self.push
                or self._altura_pendiente):
            return                           # sigue: se duerme cuando acabe
        if self._seguir_orden(viewport):
            self._seguir(viewport)
            return
        self._dormir(viewport)

    def _cancelar_seguida(self, viewport, antes) -> None:
        """Doble clic izquierdo con una orden que sigue: descarta lo que esté a
        medias (también lo que cerró el primer clic de ese doble clic) y
        termina la orden; lo acabado antes se queda."""
        if self._en_marcha(viewport):
            self._cancelar(viewport)

        def luego():
            try:
                ahora = len(viewport.history.undo_stack)
            except Exception:  # noqa: BLE001
                ahora = None
            if antes is not None and ahora is not None and ahora > antes:
                self.diana.usar(viewport, "deshacer")
            if self._cancelable(viewport):
                self._terminar_orden(viewport)
                viewport.flash_status(_tr("Orden cancelada: vuelve Seleccionar."), 2500)
        QTimer.singleShot(0, luego)

    def _dormir(self, viewport) -> None:
        self._obra = False
        self.dormida = True
        self.panel = None
        self.escondida = False
        self._sel_dormida = self._ids_sel(viewport)
        self._soltar()
        self._a_seleccionar(viewport)
        self._sincronizar()
        viewport.update()

    # -- herramientas --
    def _tool_de(self, clave):
        if clave is None:
            return self.espera
        tool = self.por_modo.get((clave, self.modo.get(clave)))
        if tool is not None:
            return tool
        return self.bases[clave]

    @property
    def herramienta(self):
        return self._tool_de(self.base)

    def _es_base(self, tool) -> bool:
        return any(tool is t for t in self._todas)

    # -- Pintar: la herramienta nativa, con la barra a la vista --
    def _tool_pintar(self):
        tools = getattr(self.app.window, "_tools", None) or {}
        tool = tools.get("paint")
        if tool is None:
            tool = next((t for k, t in tools.items()
                         if "paint" in str(k).lower() or "paint" in type(t).__name__.lower()), None)
        return tool

    def _pintando(self, viewport) -> bool:
        tool = self._tool_pintar()
        return tool is not None and viewport.active_tool is tool

    def _pintar(self, viewport, modo) -> None:
        """Pintar (o Muestrear material) de IngeTrazo; el anillo sigue a la
        vista mientras se pinta."""
        win = self.app.window
        muestrear = modo == "muestrear material"
        textos = (("Muestrear material", "Sample material") if muestrear
                  else ("Pintar", "Paint"))
        hecho = False
        if not muestrear and self._tool_pintar() is not None:
            activar = getattr(win, "_activate_tool", None)          # interno de 0.5.8
            try:
                if callable(activar):
                    activar("paint")
                else:
                    viewport.set_active_tool(self._tool_pintar())
                hecho = viewport.active_tool is self._tool_pintar()
            except Exception:  # noqa: BLE001
                hecho = False
        if not hecho:
            try:
                hecho = _seleccion.disparar_menu(win, textos)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo lanzar %s", textos[0])
                hecho = False
        if not hecho:
            viewport.flash_status(_tr("No encontré la orden «{0}» de IngeTrazo.", textos[0]), 4000)
            return
        viewport.setFocus()
        viewport.flash_status(_tr("Muestrear: clic en una cara para tomar su material." if muestrear
                              else "Pintar: clic en las caras con el material activo."), 5000)
        self._sincronizar()

    def _final_actual(self) -> str:
        """Lo que será lo dibujado al terminar (uno de FINALES)."""
        if self.modo["grupo"] == "grupo" and self.pedir_nombre:
            return "con nombre"
        return self.modo["grupo"]

    def _poner_final(self, viewport, fin) -> None:
        self.modo["grupo"] = "grupo" if fin == "con nombre" else fin
        self.pedir_nombre = fin == "con nombre"
        self._guardar_grupo()
        viewport.flash_status(
            _tr({"nada": "Rosco LT: al terminar, las piezas quedan sueltas.",
             "grupo": "Rosco LT: al terminar, cada pieza será un grupo.",
             "con nombre": "Rosco LT: al terminar, cada pieza será un grupo con nombre.",
             "componente": "Rosco LT: al terminar, cada pieza será un componente."}[fin]), 4000)

    def ocupada(self, tool) -> bool:
        """La herramienta tiene una operación en curso."""
        if getattr(tool, "start_point", None) is not None:
            return True
        if getattr(tool, "_stroke", False):
            return True
        # Equidistancia (cara elegida, arrastrando) y redondeo (midiendo).
        for nombre in ("base_face", "dragging", "sizing"):
            if getattr(tool, nombre, None):
                return True
        if tool is self.por_modo.get(("linea", "redondear")) and getattr(tool, "edges", None):
            return True
        if tool is self.bases["seleccionar"]:
            return self._lazo is not None
        # Las nativas que no usan ``start_point`` (cota, cinta…): por sus señas.
        return _con_senas(tool)

    # -- instalación --
    def instalar(self) -> None:
        app = self.app
        self.win = Flotante(self, app.window, app.viewport,
                            VENTANA_W, VENTANA_H, ANCLA_LOCAL)
        self.cancelar = _Cancelar(self)
        app.add_overlay(self.dibujar)
        # Las piezas propias (Simetría, Texto) dibujan su ayuda encima del visor.
        app.add_overlay(self._dibujar_piezas)
        self._filtro = _Filtro(self, app.viewport)
        app.viewport.installEventFilter(self._filtro)
        self.medidas = Medidas(app.window, app.viewport, self._parsear)
        self._reloj = QTimer(app.window)
        self._reloj.setInterval(SINCRONIA_MS)
        self._reloj.timeout.connect(self._sincronizar)
        self._reloj.timeout.connect(self.diana.vigilar)
        self._reloj.timeout.connect(self._vigilar_capa)
        self._reloj.timeout.connect(self._vigilar_seccion)
        # Selección múltiple (clic = añade o quita) en los dos Seleccionar.
        _seleccion.hacer_multiple(self.bases["seleccionar"])
        QTimer.singleShot(0, self._preparar_seleccionar)
        self._instalar_lapiz(app.viewport)
        try:
            from ._tiempo import Cronometro
            self.crono = Cronometro(app)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo poner en marcha el control de tiempo")
        try:
            from ._copia import avisar_al_abrir
            avisar_al_abrir(app)             # el comentario de una copia, al abrirla
        except Exception:  # noqa: BLE001
            log.exception("no se pudo vigilar los comentarios de las copias")
        self._reloj.start()
        self._reposo = QTimer(app.window)
        self._reposo.setSingleShot(True)
        self._reposo.setInterval(REPOSO_MS)
        self._reposo.timeout.connect(self._fijar)
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.applicationStateChanged.connect(lambda _e: self._sincronizar())
        senal = getattr(app.viewport, "valueBufferChanged", None)
        if senal is not None:
            try:
                senal.connect(self._buffer_cambiado)
            except Exception:  # noqa: BLE001 — queda el respaldo de _buffer()
                log.exception("no se pudo escuchar el búfer de medidas")
        _interruptor.apuntar(app, _interruptor.entrada(app, "barra_dibujo", TITULO, self.activar, TIP),
                             TITULO)
        try:
            self._instalar_barra()
        except Exception:  # noqa: BLE001 — el menú sigue funcionando
            log.exception("no se pudo crear la barra de herramientas")
        try:
            # Los huecos se configuran desde el gestor del gestor de barras.
            from ._enlace_gestor import Enlace
            self.enlace = Enlace(self)
        except Exception:  # noqa: BLE001 — la barra sigue con lo guardado
            log.exception("no se pudo enlazar con el gestor de barras")
        QTimer.singleShot(0, self._enganchar_acciones)

    # -- el historial de comandos (el ojo amarillo) --
    def _enganchar_acciones(self) -> None:
        """Cada orden de menú o de barra de IngeTrazo (y de las extensiones)
        que se lance se apunta en el historial. Se repasa de vez en cuando
        por si aparecen órdenes nuevas."""
        win = self.app.window
        de_herramienta = {id(a) for a in (getattr(win, "_tool_actions", None) or {}).values()}
        try:
            acciones = win.findChildren(QAction)
        except Exception:  # noqa: BLE001
            return
        for a in acciones:
            if id(a) in de_herramienta or getattr(a, "_rosco_lt_hist", False):
                continue
            texto = a.text().split("\t")[0].replace("&", "").strip().rstrip("…").rstrip(".")
            if not texto:
                continue
            padre = a.parent()
            titulo = ""
            for nombre in ("title", "windowTitle"):
                fn = getattr(padre, nombre, None)
                if callable(fn):
                    try:
                        titulo = str(fn() or "")
                    except Exception:  # noqa: BLE001
                        titulo = ""
                    break
            if any(palabra in titulo.lower() for palabra in HIST_SIN):
                continue
            a._rosco_lt_hist = True
            a.triggered.connect(lambda _c=False, a=a, t=texto: self._apuntar(t, a.trigger))

    def _apuntar(self, nombre: str, repetir) -> None:
        """Lo último usado, arriba; sin repetidos."""
        if self.historial and self.historial[0][0] == nombre:
            self.historial[0] = (nombre, repetir)   # con el modo de ahora
            return
        self.historial = [(n, f) for n, f in self.historial if n != nombre]
        self.historial.insert(0, (nombre, repetir))
        del self.historial[HIST_MAX:]
        self._historial_v += 1

    def _apuntar_herramienta(self, viewport, tool) -> None:
        """La herramienta recién activada (no la de espera, ni la altura de
        la barra de dibujo, ni el Seleccionar de IngeTrazo)."""
        if tool is None or tool is self.espera or tool is self.push or tool is self._select_nativo():
            return
        win = self.app.window
        if self._es_base(tool):
            clave = getattr(tool, "clave", None)
            nombre = NOMBRES.get(clave, getattr(tool, "name", "Rosco LT")).split(":")[0]

            def repetir(c=clave, m=self.modo.get(clave)):
                # La misma herramienta con el mismo modo (rectángulo por
                # esquinas o desde el centro, cota o cinta…).
                vp = self.app.viewport
                self.base = c
                if m is not None:
                    self.modo[c] = m
                if c == "rect" and m in ("esquina", "centro"):
                    self.bases["rect"]._set_from_center(vp, m == "centro")
                vp.set_active_tool(self._tool_de(c))
                vp.setFocus()                 # lo tecleado (medidas) va al visor
                vp.flash_status(_tr(self._mensaje_base()), 4000)
        else:
            nombre = getattr(tool, "name", None) or type(tool).__name__
            try:
                from core.i18n import tr
                nombre = tr(nombre)
            except Exception:  # noqa: BLE001
                pass
            tools = getattr(win, "_tools", None) or {}
            clave = next((k for k, v in tools.items() if v is tool), None)

            def repetir(k=clave, t=tool):
                activar = getattr(win, "_activate_tool", None)
                if k is not None and callable(activar):
                    activar(k)
                else:
                    self.app.viewport.set_active_tool(t)
        self._apuntar(str(nombre), repetir)

    def _usar_historial(self, i: int) -> None:
        if not 0 <= i < len(self.historial):
            return
        nombre, repetir = self.historial[i]
        self.panel = None
        try:
            repetir()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo repetir %s", nombre)
            self.app.viewport.flash_status(_tr("No se pudo repetir «{0}».", nombre), 4000)
        else:
            self.app.viewport.flash_status(_tr("Repetido: {0}.", nombre), 2500)
        self._sincronizar()

    def repetir_ultima(self) -> bool:
        """El doble clic en el vacío: la última orden de la columna del ojo
        amarillo que no sea Seleccionar, Deshacer ni Rehacer (la de
        IngeTrazo sería Seleccionar, que la barra pone al dormirse)."""
        for i, (nombre, _repetir) in enumerate(self.historial):
            if str(nombre).strip().lower() not in NO_REPETIR:
                if _seleccion.opcion("esconder_tras"):
                    self.dormida = True      # lo repetido va sin la barra
                    self._sel_dormida = self._ids_sel(self.app.viewport)
                self._usar_historial(i)
                return True
        return False

    def despertar(self, previa) -> None:
        """Clic en el vacío con la barra dormida y algo seleccionado: vuelve
        la barra (la de selección) con lo que había seleccionado."""
        self.recuperar_seleccion(previa)
        self.dormida = False
        self._obra = False
        self._sel_dormida = self._ids_sel(self.app.viewport)
        self._soltar()
        self._sincronizar()

    def recuperar_seleccion(self, previa) -> None:
        """La selección que quitó el primer clic de un doble clic en el
        vacío: vuelve antes de repetir (Mover otra vez lo mismo)."""
        vp = self.app.viewport
        try:
            vp.scene.select(list(previa), mode="replace")
        except Exception:  # noqa: BLE001
            log.exception("no se pudo recuperar la selección")
        vp.update()

    def _gesto_historial(self, p) -> None:
        """Temas A y B: pasar por el ojo del historial (de serie, el
        amarillo) o por el de la ayuda (el verde) abre su panel al lado;
        salir de él (y del ojo) lo cierra."""
        if not self.tema.rueda or self.ancla is None or p is None:
            return
        if self.panel in PANELES_OJO:
            cual = self._ojo_de(self.panel)
            if cual is None or (not self._en_historial(p) and not self._ojo_en(p, cual)):
                self.panel = None
            return
        if self.panel is None:
            for funcion in PANELES_OJO:
                cual = self._ojo_de(funcion)
                if cual is not None and self._ojo_en(p, cual):
                    self.panel = funcion
                    return

    def _en_historial(self, p) -> bool:
        """El panel abierto por un ojo (historial o ayuda, con margen) y el
        pasillo que va del ojo hasta él: cruzarlo no lo cierra ni suelta la
        barra."""
        g = self._panel() if self.panel in PANELES_OJO else None
        cual = self._ojo_de(self.panel) if g is not None else None
        if g is None or p is None or cual is None:
            return False
        m = g["marco"]
        if m.adjusted(-12.0, -12.0, 12.0, 12.0).contains(p):
            return True
        q = self._centro_ojo(self.ancla, cual)
        a = OJO_R + 8.0
        if cual in ("izquierda", "derecha"):
            x0, x1 = sorted((q.x(), m.right() if cual == "izquierda" else m.left()))
            return QRectF(x0, q.y() - a, x1 - x0, 2.0 * a).contains(p)
        y0, y1 = sorted((q.y(), m.bottom() if cual == "arriba" else m.top()))
        return QRectF(q.x() - a, y0, 2.0 * a, y1 - y0).contains(p)

    def _ayuda_maqueta(self):
        """Cómo se reparte la pestaña abierta de la ayuda: ``(alto, piezas,
        fuente)``, con cada pieza ``(tipo, rectángulo desde la esquina del
        panel, texto o documento, extra)``: «titulo», «texto» (extra: el ojo
        de color) o «clic» (extra: botón y veces)."""
        f = QFont(self.win.font() if self.win is not None else QFont())
        f.setPointSizeF(8.5)
        f.setBold(False)
        clave = (f.toString(), _idioma.actual(), self._ayuda_pagina)
        guardada = getattr(self, "_ayuda_cache", None)
        if guardada is not None and guardada[0] == clave:
            return guardada[1]
        negrita = QFont(f)
        negrita.setBold(True)
        fm, alto_titulo = QFontMetricsF(f), QFontMetricsF(negrita).height()
        ancho = AYUDA_W - 20.0
        y = AYUDA_ARRIBA
        piezas = []
        if self._ayuda_pagina == 0:
            y += ANIMA_ALTO + 4.0
            for titulo, filas in AYUDA_CLICS:
                piezas.append(("titulo", QRectF(10.0, y, ancho, alto_titulo), _tr(titulo), None))
                y += alto_titulo + 3.0
                for boton, veces, html, escenas in filas:
                    doc = QTextDocument()
                    doc.setDefaultFont(f)
                    doc.setDocumentMargin(0.0)
                    doc.setTextWidth(ancho - AYUDA_RATON)
                    doc.setHtml("<div style='color:#30302e'>" + _tr(html) + "</div>")
                    alto = max(doc.size().height(), 22.0)
                    piezas.append(("clic", QRectF(10.0, y, ancho, alto), doc, (boton, veces, escenas)))
                    y += alto + 4.0
                y += 3.0
        else:
            for titulo, cuerpo in AYUDA:
                piezas.append(("titulo", QRectF(10.0, y, ancho, alto_titulo), _tr(titulo), None))
                y += alto_titulo + 1.0
                for ojo, texto in (cuerpo if isinstance(cuerpo, list) else [(None, cuerpo)]):
                    x = 10.0 + (14.0 if ojo else 0.0)
                    texto = _tr(texto)
                    r = fm.boundingRect(QRectF(x, y, 10.0 + ancho - x, 2000.0),
                                        Qt.AlignLeft | Qt.TextWordWrap, texto)
                    piezas.append(("texto", QRectF(x, y, 10.0 + ancho - x, r.height()), texto, ojo))
                    y += r.height()
                y += 5.0
        resultado = (y + 4.0, piezas, f)
        self._ayuda_cache = (clave, resultado)
        return resultado

    @staticmethod
    def _ratoncito(painter, x, y, boton, veces) -> None:
        """El ratón pequeño de la ayuda, con el botón que toca en rojo."""
        painter.save()
        cuerpo = QRectF(x, y + 1.0, 13.0, 19.0)
        painter.setPen(QPen(QColor(40, 40, 38), 1.1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(cuerpo, 5.0, 5.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ROJO))
        painter.drawRoundedRect(QRectF(x + (1.5 if boton == "i" else 7.0), y + 2.5, 4.5, 7.5), 2.0, 2.0)
        painter.setPen(QColor(40, 40, 38))
        marca = {2: "×2", 0: "…"}.get(veces)
        if marca:
            f = QFont(painter.font())
            f.setPointSizeF(7.0)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(x + 12.0, y + 9.0, 16.0, 12.0), Qt.AlignLeft | Qt.AlignVCenter, marca)
        painter.restore()

    def _pintar_ayuda(self, painter, g) -> None:
        """El panel de la ayuda (el marco y «volver» ya están)."""
        _alto, piezas, f = self._ayuda_maqueta()
        caja = g["marco"]
        negrita = QFont(f)
        negrita.setBold(True)
        painter.save()
        painter.setFont(negrita)
        painter.setPen(TINTA)
        painter.drawText(g["titulo"], Qt.AlignLeft | Qt.AlignVCenter, _tr("Ayuda de Rosco LT"))
        # Las pestañas.
        for i, r in g["pestanas"]:
            activa = i == self._ayuda_pagina
            painter.setPen(QPen(QColor(91, 91, 214) if activa else QColor(190, 188, 180), 1.0))
            painter.setBrush(QBrush(QColor(236, 234, 249) if activa else QColor(255, 255, 255)))
            painter.drawRoundedRect(r, 4.0, 4.0)
            painter.setFont(negrita if activa else f)
            painter.setPen(QColor(45, 36, 112) if activa else QColor(90, 90, 86))
            painter.drawText(r, Qt.AlignCenter, _tr(AYUDA_PESTANAS[i]))
        painter.setClipRect(self._ayuda_recorte(g))
        alto_linea = QFontMetricsF(f).height()
        dy = self._ayuda_dy()
        if getattr(self, "_ayuda_sobra", 0.0):
            # La barrita de la derecha: dice que hay más y por dónde vas.
            vista = self._ayuda_recorte(g)
            total = vista.height() + self._ayuda_sobra
            h = max(24.0, vista.height() * vista.height() / total)
            y = vista.top() + (vista.height() - h) * (dy / self._ayuda_sobra)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(91, 91, 214, 110)))
            painter.drawRoundedRect(QRectF(caja.right() - 6.0, y, 3.5, h), 1.75, 1.75)
        for tipo, r, texto, extra in piezas:
            r = r.translated(caja.left(), caja.top() - dy)
            if tipo == "titulo":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(ROJO))
                painter.drawEllipse(QPointF(r.left() + 4.0, r.center().y()), 3.5, 3.5)
                painter.setFont(negrita)
                painter.setPen(ROJO_OSCURO)
                painter.drawText(r.adjusted(12.0, 0.0, 0.0, 0.0), Qt.AlignLeft | Qt.AlignVCenter, texto)
                continue
            if tipo == "clic":
                self._ratoncito(painter, r.left(), r.top(), extra[0], extra[1])
                painter.save()
                painter.translate(r.left() + AYUDA_RATON, r.top())
                texto.drawContents(painter)
                painter.restore()
                continue
            if extra is not None:
                painter.setPen(QPen(QColor(60, 60, 58), 0.8))
                painter.setBrush(QBrush(OJOS[extra][2]))
                painter.drawEllipse(QPointF(r.left() - 7.0, r.top() + alto_linea / 2.0), 4.0, 4.0)
            painter.setFont(f)
            painter.setPen(QColor(48, 48, 46))
            painter.drawText(r, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, texto)
        painter.restore()

    # -- la pantallita animada de la ayuda --
    def _anima_activa(self) -> bool:
        return (self.panel == "ayuda" and self._ayuda_pagina == 0 and self.win is not None
                and self.win.isVisible() and not self.win._transparente)

    def _anima_caja(self, g) -> QRectF:
        m = g["marco"]
        return QRectF(m.left() + 10.0, m.top() + AYUDA_ARRIBA - self._ayuda_dy(),
                      AYUDA_W - 20.0, ANIMA_ALTO)

    def _anima_vigilar(self) -> None:
        """El reloj de la animación solo anda con la pestaña de clics a la vista."""
        if not self._anima_activa():
            if self._reloj_anima is not None and self._reloj_anima.isActive():
                self._reloj_anima.stop()
            return
        if self._reloj_anima is None:
            self._reloj_anima = QTimer(self.app.window)
            self._reloj_anima.setInterval(40)
            self._reloj_anima.timeout.connect(self._anima_paso)
        if not self._reloj_anima.isActive():
            self._anima_t = time.monotonic()
            self._reloj_anima.start()

    def _anima_paso(self) -> None:
        if not self._anima_activa():
            self._reloj_anima.stop()
            return
        g = self._panel()
        if g is None or self.ancla is None:
            return
        if time.monotonic() - self._anima_t >= _anima.DURACION_S:
            lista = self._anima_fila or AYUDA_ESCENAS
            i = lista.index(self._anima_esc) if self._anima_esc in lista else -1
            self._anima_esc = lista[(i + 1) % len(lista)]
            self._anima_t = time.monotonic()
            self.win.update()                # cambia también la fila resaltada
            return
        caja = self._anima_caja(g).translated(-self.win.origen.x(), -self.win.origen.y())
        self.win.update(caja.adjusted(-1.0, -1.0, 1.0, 1.0).toAlignedRect())

    def _anima_raton(self, p) -> None:
        """Al pasar por una fila, se queda en sus gestos."""
        fila = None
        if p is not None and self._anima_activa():
            g = self._panel()
            if g is not None:
                m = g["marco"].topLeft()
                for tipo, r, _d, extra in self._ayuda_maqueta()[1]:
                    if tipo == "clic" and r.translated(m.x(), m.y() - self._ayuda_dy()).contains(p):
                        fila = extra[2]
                        break
        if fila != self._anima_fila:
            self._anima_fila = fila
            if fila and self._anima_esc not in fila:
                self._anima_esc = fila[0]
                self._anima_t = time.monotonic()
                self.win.update()

    def _pintar_anima(self, painter, c) -> None:
        """Encima del fondo guardado: la pantallita y la fila que le toca."""
        g = self._panel(c)
        if g is None or "pestanas" not in g:
            return
        k = min(1.0, max(0.0, (time.monotonic() - self._anima_t) / _anima.DURACION_S))
        painter.save()
        painter.setClipRect(self._ayuda_recorte(g))
        _anima.pintar(painter, self._anima_caja(g), self._anima_esc, k)
        m = g["marco"].topLeft()
        dy = self._ayuda_dy()
        for tipo, r, _d, extra in self._ayuda_maqueta()[1]:
            if tipo == "clic" and self._anima_esc in extra[2]:
                painter.save()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(91, 91, 214, 38)))
                painter.drawRoundedRect(r.translated(m.x(), m.y() - dy).adjusted(-4.0, -1.0, 4.0, 1.0), 4.0, 4.0)
                painter.restore()
                break
        painter.restore()

    # -- la ayuda que no cabe entera: se desplaza con la rueda --
    def _ayuda_dy(self) -> float:
        return float(getattr(self, "_ayuda_scroll", 0.0) or 0.0)

    def _ayuda_recorte(self, g) -> QRectF:
        """Por dónde se ve el contenido de la ayuda (bajo las pestañas)."""
        m = g["marco"]
        return QRectF(m.left() + 1.0, m.top() + AYUDA_ARRIBA - 4.0, m.width() - 2.0,
                      m.height() - AYUDA_ARRIBA + 3.0)

    def _zona_visible(self, c) -> QRectF:
        """Lo que se ve de la ventanita del rosco centrada en ``c`` (px del
        visor): su rectángulo recortado al monitor y a la pantalla gráfica."""
        zona = QRectF(c.x() - ANCLA_LOCAL.x() + 4.0, c.y() - ANCLA_LOCAL.y() + 4.0,
                      VENTANA_W - 8.0, VENTANA_H - 8.0)
        try:
            from PySide6.QtGui import QGuiApplication
            vp = self.app.viewport
            origen = vp.mapToGlobal(QPoint(0, 0))
            pantalla = (QGuiApplication.screenAt(vp.mapToGlobal(QPoint(round(c.x()), round(c.y()))))
                        or vp.screen())
            g = pantalla.availableGeometry()
            monitor = QRectF(g.x() - origen.x() + 4.0, g.y() - origen.y() + 4.0,
                             g.width() - 8.0, g.height() - 8.0)
            # Y dentro de la pantalla gráfica: lo de fuera del visor no se ve.
            visor = QRectF(vp.rect()).adjusted(4.0, 4.0, -4.0, -4.0)
            visible = zona.intersected(monitor).intersected(visor)
            if visible.width() > 0 and visible.height() > 0:
                return visible
        except Exception:  # noqa: BLE001 — sin monitor, la ventanita
            log.exception("no se pudo medir el monitor")
        return zona

    def raton_rueda(self, p, delta) -> bool:
        """La rueda sobre la ayuda que no cabe entera la desplaza (True)."""
        if self.panel != "ayuda" or not getattr(self, "_ayuda_sobra", 0.0):
            return False
        g = self._panel()
        if g is None or not g["marco"].contains(p):
            return False
        nuevo = min(self._ayuda_sobra, max(0.0, self._ayuda_dy() - delta / 120.0 * 40.0))
        if nuevo != self._ayuda_dy():
            self._ayuda_scroll = nuevo
            self._sincronizar()
            if self.win is not None:
                self.win.update()
        return True

    def idioma_cambiado(self) -> None:
        """Otro idioma (Opciones): lo pintado se rehace; las ventanas ya hechas
        cambian al reabrirlas o al reiniciar IngeTrazo."""
        self._ayuda_cache = None
        self._cache_sel = None
        self._etiqueta_w = None
        self._rehacer_dibujo()
        self.app.viewport.flash_status(
            _tr("Idioma cambiado. Algunas ventanas cambian al reabrirlas o al reiniciar IngeTrazo."), 6000)
        self._sincronizar()

    # -- aplicar capa (el icono del cajetín de capas) --
    def _capa_icono_en(self, p) -> bool:
        if not self._capa_en(p):
            return False
        return p.x() <= self._rect_capa(self.ancla).left() + 26.0

    def _menu_aplicar_capa(self, viewport) -> None:
        from PySide6.QtWidgets import QMenu
        if self.ancla is None:
            return
        r = self._rect_capa(self.ancla)
        pos = viewport.mapToGlobal(QPoint(round(r.left()), round(r.bottom()) + 2))
        m = QMenu(self.app.window)
        m.addSection(_tr("Aplicar capa"))
        a = m.addAction(_tr("Aplicar la capa actual a lo que seleccione"))
        a.setCheckable(True)
        a.setChecked(self.aplicar_capa)
        info = m.addAction(_tr("Capa actual: {0}", self.capas.actual(viewport.scene)))
        info.setEnabled(False)
        elegida = m.exec(pos)
        self.tragar_clic()
        if elegida is a:
            self.aplicar_capa = a.isChecked()
            self._ids_aplicados = frozenset()        # también lo ya seleccionado
            viewport.flash_status(_tr("Aplicar capa: cada elemento que selecciones pasa a la capa "
                                  "actual." if self.aplicar_capa else "Aplicar capa: desactivado."), 4000)
        self._sincronizar()

    def _aplicar_capa_a_nuevos(self, viewport) -> None:
        scene = viewport.scene
        try:
            seleccion = list(scene.selection)
            ids = frozenset(id(e) for e in seleccion)
        except Exception:  # noqa: BLE001
            return
        nuevos = ids - self._ids_aplicados
        self._ids_aplicados = ids
        if not nuevos:
            return
        entidades = [e for e in seleccion if id(e) in nuevos]
        nombre = self.capas.actual(scene)
        try:
            if _capas.asignar(viewport, entidades, nombre):
                viewport.flash_status(_tr("Capa «{0}»: {1} elemento(s).", nombre, len(entidades)), 2500)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo aplicar la capa")

    def _menu_apagar(self, viewport, pos) -> None:
        """Salir de IngeTrazo o reiniciarlo."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self.app.window)
        salir = m.addAction(_tr("Salir de IngeTrazo"))
        reiniciar = m.addAction(_tr("Reiniciar IngeTrazo"))
        elegida = m.exec(pos)
        self.tragar_clic()
        if elegida is salir:
            QTimer.singleShot(0, self._cerrar_ingetrazo)
        elif elegida is reiniciar:
            self.diana.usar(viewport, "reiniciar")

    def _instalar_barra(self) -> None:
        """El botón de la barra de dibujo en la barra «Rosco LT»."""
        from ._barra import anadir
        win = self.app.window
        act = QAction(_icono_barra(win), _tr(TITULO), win)
        act.setToolTip(_tr(TIP))
        act.setStatusTip(_tr(TIP))
        act.triggered.connect(lambda _checked=False: self.activar())
        anadir(self.app, act)

    # -- cambios de fase --
    def _mensaje_base(self) -> str:
        if self.base is None:
            return MSG_ESPERA
        return MSG.get((self.base, self.modo.get(self.base)), TIP)

    def _cursor_en_visor(self):
        """El ratón en px del visor, si está encima de él."""
        vp = self.app.viewport
        p = vp.mapFromGlobal(QCursor.pos())
        return QPointF(p) if vp.rect().contains(p) else None

    def activar(self) -> None:
        """Llamada a Rosco LT: sin herramienta elegida y con las opciones de cada
        botón como al principio (salvo Grupo, que se recuerda). Hasta que no
        se elija un botón, un clic fuera de la barra la cierra."""
        if _interruptor.apagada(self.app):
            return
        vp = self.app.viewport
        self.dormida = False                 # llamada: se despierta
        self._obra = False
        self.base = None
        for clave, modos in MODOS.items():
            if clave != "grupo":
                self.modo[clave] = modos[0]
        self.bases["rect"]._set_from_center(vp, False)
        vp.set_active_tool(self.herramienta)
        self.arco_visible = True
        self._soltar()
        aqui = None if self.anclada else self._cursor_en_visor()
        if aqui is not None:
            # Llamado desde otra barra (la barra de modificar): la barra aparece ya fija
            # donde está el ratón, para elegir una herramienta.
            self.cursor_px = aqui
            self.fijo = True
            self.ancla = QPointF(aqui)
        vp.setFocus()                        # para que lo tecleado llegue al visor
        vp.flash_status(_tr(self._mensaje_base()), 6000)
        self._sincronizar()

    def base_hecha(self, viewport, tool, puntos, antes, silencioso=False) -> None:
        """Una base terminada. ``silencioso``: si no forma cara (un arco
        abierto), no se avisa: simplemente no pasa a la altura."""
        if viewport.history.last_error:
            return                           # el historial ya lo deshizo y avisa
        ahora = _pila(viewport)
        if antes is not None and ahora is not None and ahora <= antes:
            return                           # no se creó nada
        self._altura_pendiente = True        # la barra no se duerme entre base y altura
        self._orden_hecha(viewport)
        QTimer.singleShot(0, lambda: self._pasar_a_altura(viewport, tool, puntos,
                                                          silencioso))

    def _pasar_a_altura(self, viewport, tool, puntos, silencioso=False) -> None:
        self._altura_pendiente = False
        if viewport.active_tool is not tool:
            return                           # el usuario cambió de herramienta
        cara = _cara_con_puntos(viewport.scene.mesh, puntos)
        if cara is None and silencioso:
            self.olvidar_antes()
            self._orden_hecha(viewport)      # sin altura: la orden acaba aquí
            return
        if cara is None:
            viewport.flash_status(
                _tr("Base dibujada, pero no encontré una cara entera para empujarla "
                "(¿contorno abierto, no plano o partido por otra geometría?)."),
                7000)
            self.olvidar_antes()
            self._orden_hecha(viewport)
            return
        viewport.set_active_tool(self.push)
        try:
            ok = self.push.enganchar(viewport, cara)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo empezar Empujar/Tirar")
            ok = False
        if not ok:
            viewport.set_active_tool(tool)
            viewport.flash_status(_tr("No se pudo empujar esa cara; queda plana."), 6000)
            self.olvidar_antes()
            self._orden_hecha(viewport)
            return
        viewport.flash_status(_tr(MSG_ALTURA), 8000)
        viewport.update()

    def volver_a_la_base(self, viewport) -> None:
        QTimer.singleShot(0, lambda: self._volver(viewport))

    def _volver(self, viewport) -> None:
        if viewport.active_tool is self.push and not self.push.dragging:
            if self._obra and _seleccion.opcion("esconder_tras"):
                # La pieza ya está: vuelve la base, sin la barra, para otra.
                self._apuntar_herramienta(viewport, self.herramienta)
                viewport.set_active_tool(self.herramienta)
                self._seguir(viewport)
                return
            viewport.set_active_tool(self.herramienta)
            self._soltar()                   # el arco vuelve a ser el cursor
            viewport.flash_status(_tr(self._mensaje_base()), 4000)
            self._sincronizar()

    # -- grupo / componente al terminar --
    def olvidar_antes(self) -> None:
        self._antes = None

    @staticmethod
    def _clave_punto(p):
        return (round(p.x(), 5), round(p.y(), 5), round(p.z(), 5))

    def _clave_cara(self, f):
        return frozenset(self._clave_punto(p) for p in f.vertices)

    def _clave_arista(self, e):
        return frozenset((self._clave_punto(e.a), self._clave_punto(e.b)))

    def _recordar_antes(self, viewport) -> None:
        """Lo que hay antes de empezar una pieza, para agrupar lo nuevo.
        Por GEOMETRÍA, no por objeto: Empujar/Tirar recrea los objetos de
        todas las caras al previsualizar, y comparar objetos metía en el
        grupo/componente todo lo suelto que ya había (bases anteriores)."""
        if self.modo["grupo"] == "nada":
            self._antes = None
            return
        mesh = viewport.scene.mesh
        self._antes = ({self._clave_cara(f) for f in mesh.faces},
                       {self._clave_arista(e) for e in mesh.edges})

    def empuje_hecho(self, viewport) -> None:
        if self._antes is not None and self.modo["grupo"] != "nada":
            QTimer.singleShot(0, lambda: self._agrupar(viewport))

    def _preparar_seleccionar(self) -> None:
        """El Seleccionar de IngeTrazo: selección múltiple y, sin nada
        seleccionado, clic en vacío = la barra de dibujo, doble clic = repetir."""
        nativo = self._select_nativo()
        _seleccion.hacer_multiple(nativo)
        _seleccion.hacer_vacio(self, nativo)
        _empuje.instalar((getattr(self.app.window, "_tools", None) or {}).get("pushpull"))

    def _vigilar_capa(self) -> None:
        try:
            self.capas.vigilar(self.app.viewport)
        except Exception:  # noqa: BLE001 — nunca rompe el reloj
            log.exception("fallo al vigilar la capa de dibujo")

    def _agrupar(self, viewport) -> None:
        # Mientras se crea el grupo (y se pide su nombre) la capa espera: va
        # al grupo entero, no a sus caras.
        self.capas.agrupando = True
        try:
            self._agrupar_pieza(viewport)
        finally:
            self.capas.agrupando = False

    def _agrupar_pieza(self, viewport) -> None:
        antes, self._antes = self._antes, None
        if antes is None:
            return
        if viewport.scene.edit_group is not None:
            viewport.flash_status(_tr("Rosco LT: dentro de un grupo abierto no se puede "
                                  "agrupar; la pieza queda suelta."), 5000)
            return
        caras_antes, aristas_antes = antes
        mesh = viewport.scene.mesh
        caras = [f for f in mesh.faces if self._clave_cara(f) not in caras_antes]
        aristas = [e for e in mesh.edges if self._clave_arista(e) not in aristas_antes]
        if not caras:
            return
        componente = self.modo["grupo"] == "componente"
        nombre = None
        if componente or self.pedir_nombre:
            n = len(viewport.scene.groups) + 1
            titulo = "Componente" if componente else "Grupo"
            nombre, ok = QInputDialog.getText(
                self.app.window, "Rosco LT · {0}".format(_tr(titulo.lower())),
                _tr("Nombre del {0}:", _tr(titulo.lower())), text=f"{_tr(titulo)} {n}")
            if not ok:
                viewport.flash_status(_tr("Rosco LT: sin nombre, la pieza queda suelta."), 4000)
                return
            nombre = nombre.strip() or f"{titulo} {n}"
        from core.history import MakeGroupCommand
        viewport.history.execute(MakeGroupCommand(caras, aristas,
                                                  component=componente, name=nombre))
        error = viewport.history.last_error
        viewport.notify_scene_changed()
        if error:
            viewport.flash_status(_tr("Rosco LT: no se pudo agrupar: {0}", error), 6000)
        else:
            viewport.flash_status(_tr("Componente creado. Ctrl+Z lo deshace." if componente
                                  else "Grupo creado. Ctrl+Z lo deshace."), 4000)

    # -- la ventanita de medidas --
    def _parsear_simple(self, texto: str):
        vp = self.app.viewport
        try:
            valor = type(vp)._parse_value_buffer(texto.strip())
        except Exception:  # noqa: BLE001
            return None
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return None
        return float(valor)

    def _parsear(self, texto: str):
        """Una medida tecleada («2,5», «30cm»…) en metros, o None. Admite
        cuentas: «120+30», «2m+35cm», «(3-0,2)/2», «4*25»: los números con
        unidad se pasan a la unidad del documento, se calcula y el resultado
        se lee como una medida en esa unidad."""
        texto = (texto or "").strip()
        if not texto:
            return None
        valor = self._parsear_simple(texto)
        if valor is not None:
            return valor
        if not any(op in texto[1:] for op in "+-*/×÷−") and "(" not in texto:
            return None
        import re
        from ._medidas import calcular
        unidad = self._parsear_simple("1")          # 1 unidad del documento, en m
        if not unidad:
            return None

        def a_unidad_doc(m):
            num, uni = m.group(1), m.group(2)
            if not uni:
                return num.replace(",", ".")
            metros = self._parsear_simple(num + uni)
            if metros is None:
                raise ValueError(uni)
            return repr(metros / unidad)

        try:
            expr = re.sub(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m|in|ft|\"|')?", a_unidad_doc, texto)
            resultado = calcular(expr)
        except Exception:  # noqa: BLE001 — una cuenta mal escrita
            return None
        return resultado * unidad

    def _aplicar_valor(self, viewport, tool, valor) -> bool:
        if viewport.active_tool is not tool:
            return False
        ok = tool.on_value(viewport, valor)
        viewport.update()
        return ok is not False

    def _poner_lados(self, viewport, tool, texto) -> bool:
        """Los lados del polígono (o segmentos del círculo) tecleados."""
        clave = getattr(tool, "clave", None)
        if clave not in LIMITES_LADOS:
            return False
        try:
            n = int(round(float(str(texto).replace(",", ".").strip())))
        except ValueError:
            return False
        lo, hi = LIMITES_LADOS[clave]
        tool.sides = min(hi, max(lo, n))
        viewport.flash_status(_tr("{0}: {1}", ETIQUETA_LADOS[clave], tool.sides), 2000)
        viewport.update()
        self._sincronizar()
        return True

    def _campos_edicion(self, viewport):
        """Desplazar, Rotar, Escalar y compañía, con su opción encendida: un
        renglón con el rótulo de su propio cuadro de medidas, tras el primer
        punto. Sin la opción siguen con lo tecleado en el visor."""
        if not _seleccion.opcion("dictado_edicion"):
            return None
        barra = self._barra_modificar()
        tool = viewport.active_tool
        if barra is None or not callable(getattr(tool, "on_value", None)):
            return None
        try:
            clave = barra._clave_activa(viewport)
        except Exception:  # noqa: BLE001
            return None
        if clave not in EDICION_CON_MEDIDA or not self._en_marcha(viewport):
            return None
        etiqueta = self._etiqueta_vcb(tool)
        rotulo = etiqueta.lower()
        sin_unidad = any(s in rotulo for s in ("ngulo", "grado", "escala", "factor", "angle", "scale"))

        def aplicar(textos):
            texto = textos[0] if textos else ""
            if not texto:
                return False
            if sin_unidad:
                from ._medidas import calcular
                try:
                    return self._aplicar_valor(viewport, tool, calcular(texto))
                except Exception:  # noqa: BLE001 — una cuenta mal escrita
                    return False
            v = self._parsear(texto)
            return v is not None and self._aplicar_valor(viewport, tool, v)
        return (EDICION_CON_MEDIDA[clave], [etiqueta], aplicar)

    def _campos(self, viewport, tecleando: bool = False):
        """``(título, renglones, aplicar)`` para lo que se está haciendo, o
        None si ahora no hay ninguna medida que pedir. ``tecleando``: se
        acaba de pulsar un número; con polígono o círculo sin empezar, son
        los lados."""
        tool = viewport.active_tool
        f = self._parsear

        def una(textos):
            v = f(textos[0]) if textos and textos[0] else None
            return v is not None and self._aplicar_valor(viewport, tool, v)

        if tool is self.push and self.push.dragging:
            return ("Altura (empujar / tirar)", ["Altura"], una)
        edicion = self._campos_edicion(viewport)
        if edicion is not None:
            return edicion
        clave_lados = getattr(tool, "clave", None)
        if (tecleando and self._es_base(tool) and not self.ocupada(tool)
                and clave_lados in LIMITES_LADOS):
            def lados(textos):
                return bool(textos and textos[0]) and self._poner_lados(viewport, tool, textos[0])
            return (f"{NOMBRES[clave_lados]} · {ETIQUETA_LADOS[clave_lados].lower()}",
                    [ETIQUETA_LADOS[clave_lados]], lados)
        if (not self._es_base(tool) or not self.ocupada(tool)
                or tool is self.bases["seleccionar"] or tool is self.bases["borrar"]):
            return None
        if tool is self.girado:
            if tool.base_point is None:
                return ("Rectángulo · longitud del lado", ["Lado"], una)
            if self.modo["rect"] == "lado":
                return ("Rectángulo · fondo", ["Fondo"], una)

            def girado(textos):
                w = f(textos[0]) if textos[0] else None
                a = f(textos[1]) if len(textos) > 1 and textos[1] else None
                if w is None:
                    return False
                return self._aplicar_valor(viewport, tool, (w, a) if a is not None else w)
            return ("Rectángulo girado · fondo", ["Fondo", "Ángulo"], girado)   # «°» lo pone la casilla
        clave = tool.clave
        if clave == "rect":
            def rect(textos):
                w = f(textos[0]) if textos[0] else None
                h = f(textos[1]) if len(textos) > 1 and textos[1] else None
                if w is None and h is None:
                    return False
                if (w is None or h is None) and tool.hover_point is not None:
                    du, dv = (abs(x) for x in tool._dimensions(*tool._span(tool.hover_point)))
                    w = w if w is not None else du
                    h = h if h is not None else dv
                if w is None or h is None:
                    return False
                return self._aplicar_valor(viewport, tool, (w, h))
            return ("Rectángulo", ["Ancho", "Alto"], rect)
        if clave in ("poly", "circle"):
            nombre = self._titulo_medida(tool)

            def medida_y_lados(textos):
                # El segundo renglón, si se rellena, son los lados.
                if len(textos) > 1 and textos[1]:
                    self._poner_lados(viewport, tool, textos[1])
                return una(textos)
            return (f"{NOMBRES[clave]} · {nombre.lower()}",
                    [nombre, ETIQUETA_LADOS[clave]], medida_y_lados)
        if tool is self.guia:
            return ("Línea guía", ["Distancia"], una)
        if tool is self.por_modo[("linea", "paralela")]:
            return ("Paralela", ["Distancia"], una)
        if tool is self.bases["linea"]:
            return ("Línea", ["Longitud"], una)
        # El resto (arcos, cota, cinta, equidistancia, redondeo): un renglón
        # con el rótulo del cuadro de medidas de la propia herramienta.
        titulo = f"{NOMBRES.get(clave, 'Rosco LT')} ·{self.modo.get(clave) or ''}".rstrip(" ·")
        return (titulo, [self._etiqueta_vcb(tool)], una)

    @staticmethod
    def _etiqueta_vcb(tool) -> str:
        """El rótulo que la herramienta pone al cuadro de medidas (Radio,
        Distancia…), traducido; «Medida» si no tiene."""
        texto = None
        for nombre in ("vcb_caption", "vcb_label"):
            v = getattr(tool, nombre, None)
            try:
                v = v() if callable(v) else v
            except Exception:  # noqa: BLE001
                v = None
            if isinstance(v, str) and v:
                texto = v
                break
        if not texto:
            return "Medida"
        try:
            from core.i18n import tr
            return tr(texto)
        except Exception:  # noqa: BLE001
            return texto

    def _actuales(self, viewport):
        """La medida que se está dibujando, para verla en gris en cada
        renglón de la ventanita."""
        tool = viewport.active_tool
        try:
            if tool is self.push:
                return [fmt_len(abs(self.push.extrusion))]
            if not self._es_base(tool):            # Desplazar, Rotar, Escalar…
                etiqueta_valor = tool.value_label() if hasattr(tool, "value_label") else None
                return [etiqueta_valor[0]] if etiqueta_valor else []
            if tool is self.por_modo[("linea", "paralela")]:
                return [fmt_len(abs(tool.distancia))]
            if getattr(tool, "clave", "") in ("arco", "medir") or tool in (
                    self.por_modo[("linea", "equidist.")],
                    self.por_modo[("linea", "redondear")]):
                etiqueta_valor = tool.value_label() if hasattr(tool, "value_label") else None
                return [etiqueta_valor[0]] if etiqueta_valor else []
            hover = getattr(tool, "hover_point", None)
            inicio = getattr(tool, "start_point", None)
            if hover is None or inicio is None:
                return []
            if tool is self.bases["rect"]:
                du, dv = tool._dimensions(*tool._span(hover))
                return [fmt_len(abs(du)), fmt_len(abs(dv))]
            if tool is self.girado:
                if tool.base_point is None:
                    return [fmt_len((hover - inicio).length())]
                w, ang = tool._width_and_angle(hover, getattr(tool, "_locked", None))
                return [fmt_len(w), f"{ang:.1f}"]
            if getattr(tool, "clave", "") in ("poly", "circle"):
                etiqueta_valor = tool.value_label()
                if etiqueta_valor:
                    return [etiqueta_valor[0].split("  ")[0].split(" ", 1)[-1]]
            return [fmt_len((hover - inicio).length())]
        except Exception:  # noqa: BLE001 — solo es una ayuda visual
            return []

    def _sincronizar_medidas(self, viewport) -> None:
        """La ventanita aparece sola en cada punto (mientras haya una medida
        que pedir), sigue al cursor y muestra la medida actual."""
        m = self.medidas
        if m is None:
            return
        plan = self._campos(viewport)
        if plan is None:
            self._dictado_llave = None
            if m.dictando:
                m.terminar_dictado()
            elif m.isVisible() and not m.isActiveWindow():
                m.hide()
                m.clave = None
            return
        titulo, campos, aplicar = plan
        if not m.isVisible() or m.clave != (titulo, tuple(campos)):
            m.abrir(titulo, campos, "", aplicar)
        else:
            m._aplicar = aplicar
        m.poner_actuales(self._actuales(viewport))
        self._dictado_tras_punto(viewport, m)
        m.seguir()

    def _dictado_tras_punto(self, viewport, m) -> None:
        """Con la opción encendida, cada punto nuevo (o medida aplicada) deja
        el teclado en la casilla y el dictado escuchando. Solo una vez por
        punto: tras Esc no vuelve hasta el siguiente."""
        tool = viewport.active_tool
        opcion = ("dictado_dibujo" if self._es_base(tool) or tool is self.push
                  else "dictado_edicion")
        if not _seleccion.opcion(opcion):
            if m.dictando and m.dictado_auto:
                m.terminar_dictado()
            return
        llave = (id(tool), self._clics_orden, m.aplicadas)
        if llave == self._dictado_llave:
            return
        otro_punto = (self._dictado_llave is not None and self._dictado_llave[0] == llave[0]
                      and self._dictado_llave[1] != llave[1])
        self._dictado_llave = llave
        m.al_aplicar = lambda: (self._sincronizar_medidas(viewport), self._sincronizar())
        # Fuera del clic que se está atendiendo, para quedarse con el foco.
        QTimer.singleShot(0, lambda: m.a_dictado(vaciar=otro_punto))

    # -- geometría del anillo (según el tema) --
    def _r_ext(self) -> float:
        """Del cursor al borde de fuera del anillo."""
        return self.tema.r_ext

    def _medio_arcos(self) -> float:
        """Media anchura del anillo."""
        return self.tema.r_ext

    def _bandas(self) -> tuple:
        """Las cuatro bandas: botones, radios, ángulo de arranque y tamaño
        de los iconos."""
        # Las bandas se recorren de a0 + barrido a a0: arriba eso es de
        # izquierda a derecha; abajo, al revés, así que se les da la vuelta.
        T = self.tema
        if T.rueda:
            return tuple(b[1:] for b in self.bandas_de(T))
        arriba_int = T.arriba_int or BASES
        arriba_ext = T.arriba_ext or HERRAMIENTAS
        abajo_int = tuple(reversed(T.abajo_int or _seleccion.SEMI))
        abajo_ext = tuple(reversed(T.abajo_ext or _seleccion.BANDA))
        return ((arriba_int, T.r1[0], T.r1[1], T.a_arriba, T.tam1),
                (arriba_ext, T.r2[0], T.r2[1], T.a_arriba, T.tam2),
                (abajo_int, T.r1[0], T.r1[1], T.a_abajo, T.tam1),
                (abajo_ext, T.r2[0], T.r2[1], T.a_abajo, T.tam_abajo_ext or T.tam2))

    # -- los huecos configurables (el gestor de barras ▸ Barra Rosco LT) --
    def bandas_de(self, T) -> tuple:
        """Las bandas configuradas con la geometría del tema ``T``: ``(grupo,
        claves, r_int, r_ext, a0, tam)``; las de abajo, del revés (como se
        recorren). El icono se achica si hay muchos huecos."""
        h = self.huecos
        filas = (("ai", T.r1, T.a_arriba, T.tam1), ("ae", T.r2, T.a_arriba, T.tam2),
                 ("bi", T.r1, T.a_abajo, T.tam1), ("be", T.r2, T.a_abajo, T.tam_abajo_ext or T.tam2))
        bandas = []
        for g, r, a0, tam in filas:
            claves = h.banda(g)
            if g in ("bi", "be"):
                claves = tuple(reversed(claves))
            paso = math.radians(T.barrido / max(1, len(claves)))
            bandas.append((g, claves, r[0], r[1], a0, min(tam, 0.85 * (r[0] + r[1]) / 2.0 * paso)))
        return tuple(bandas)

    def lados_de(self, T) -> tuple:
        """Los siete huecos de los lados con la geometría del tema ``T``:
        ``(índice, clave, r_int, r_ext, a0, barrido, tam)``, también los
        vacíos. Solo con ojos (en los demás temas el hueco es estrecho)."""
        if not T.rueda:
            return ()
        h = T.hueco
        salida = []
        lista = self.huecos.lista("lados")
        partido = len(lista) > 6 and bool(lista[6])   # sin nada abajo, el de arriba va entero
        for j, (sitio, clave) in enumerate(zip(LADOS, lista)):
            lado, donde, *mitad = sitio.split("_")
            if lado == "izq" and donde == "dentro" and partido:
                # Partido en dos: arriba (el primero) y abajo.
                (r0, r1), a, b = T.r1, 0.0 if not mitad else -(h - 1.5), h - 1.5
            elif donde == "dentro":
                (r0, r1), a, b = T.r1, -(h - 1.5), 2.0 * (h - 1.5)
            else:
                (r0, r1), b = T.r2, h - 1.0 - LADO_OJO
                a = LADO_OJO if donde == "arriba" else -(h - 1.0)
            if lado == "izq":                # el de la izquierda, en espejo
                a = 180.0 - a - b
            medio = (r0 + r1) / 2.0
            tam = min(T.tam2, 0.8 * medio * math.radians(b), 0.7 * (r1 - r0))
            salida.append((j, clave, r0, r1, a, b, tam))
        return tuple(salida)

    def _lados(self) -> tuple:
        """Los huecos de los lados con algo puesto (los de la barra)."""
        if self._sin_arcos():
            return ()
        return tuple(x for x in self.lados_de(self.tema) if x[1])

    def _huecos_defecto(self) -> dict:
        """El reparto de siempre (el del tema)."""
        T = self.tema
        return {"ai": list(T.arriba_int or BASES), "ae": list(T.arriba_ext or HERRAMIENTAS),
                "bi": list(T.abajo_int or _huecos.BANDA_BI),
                "be": list(T.abajo_ext or _seleccion.BANDA),
                # Notas y el reloj van ahora en los huecos de los lados.
                "chicos": [_huecos.VACIO if k in LADOS_DEF else k for k in CHICOS_F],
                "lados": list(LADOS_DEF),
                "aro": list(_diana.ARO_DEF),
                "gajos": list(_diana.GAJOS_DEF), "tri": list(_diana.TRI_DEF),
                "centro": list(_diana.CENTRO_DEF),
                "ojos": {"arriba": "rueda", "derecha": "ayuda", "abajo": "ocultar_resto",
                         "izquierda": "historial"}}

    def _huecos_cambiados(self) -> None:
        """Tras cambiar lo que va en un hueco: se repinta todo."""
        self._poner_rueda()
        _iconos.olvidar_externos()
        self._etiqueta_w = None
        if self.panel in ("vistas", *PANELES_OJO):
            self.panel = None
        self._rehacer_dibujo()
        self._sincronizar()
        enlace = getattr(self, "enlace", None)
        if enlace is not None:
            enlace.repintar()

    def _poner_rueda(self) -> None:
        """Lo configurado dentro de la rueda y en su aro."""
        h = self.huecos
        _diana.poner_aro(h.aro())
        _diana.poner_rueda(h.lista("gajos"), h.lista("tri"), h.lista("centro"))

    def _ojo_de(self, funcion):
        """El ojo que lleva ``funcion`` («rueda», «historial», «ayuda»), o None."""
        if not self.tema.rueda:
            return "arriba" if funcion == "rueda" else None
        return self.huecos.ojo_de(funcion)

    def _ojo_orden_en(self, p):
        """La orden del ojo bajo ``p`` (los que no abren rueda ni historial
        ejecutan su orden con un clic), o None."""
        if not self.tema.rueda or self._sin_arcos():
            return None
        for cual, clave in self.huecos.ojos().items():
            if clave and clave not in _huecos.SOLO_OJOS and self._ojo_en(p, cual):
                return clave
        return None

    def _centro_clave(self, c, clave) -> QPointF:
        """Dónde está el botón ``clave`` (para sacar su menú o panel debajo):
        botoncito, banda, aro de la rueda u ojo; si no, el centro."""
        if clave in self._chicos():
            return self._centro_chico(c, clave)
        barrido = self.tema.barrido
        for claves, r_int, r_ext, a0, _tam in self._bandas():
            if clave in claves:
                return centro_boton(c, r_int, r_ext, claves.index(clave), len(claves), a0, barrido)
        for _j, k, r_int, r_ext, a0, b, _tam in self._lados():
            if k == clave:
                return centro_boton(c, r_int, r_ext, 0, 1, a0, b)
        if self._rueda_abierta() and clave in _diana.RUEDA_BOTONES:
            return _diana.rueda_centro_boton(self._diana_centro(c), clave)
        if self.tema.rueda:
            for cual, k in self.huecos.ojos().items():
                if k == clave:
                    return self._centro_ojo(c, cual)
        return QPointF(c)

    def _ejecutar_externo(self, viewport, clave) -> None:
        """Un comando del gestor de barras puesto en un hueco."""
        gestor = gestor_barras(self.app.window)
        if gestor is None or not callable(getattr(gestor, "ejecutar", None)):
            viewport.flash_status(_tr("Ese botón es un comando del gestor de barras, que no está instalado."), 5000)
            return
        gestor.ejecutar(clave[len(_huecos.EXTERNO):])

    def _pulsar(self, viewport, clave) -> bool:
        """Lo que hace el botón ``clave`` esté donde esté (banda, botoncito,
        aro de la rueda u ojo)."""
        if not clave:
            return False
        if _huecos.externo(clave):
            self.panel = None
            QTimer.singleShot(0, lambda: self._ejecutar_externo(viewport, clave))
            self._sincronizar()
            return True
        if clave == "flip":                  # la Simetría propia (no la de la barra de modificar), con su submenú
            abierta = self.panel == "flip" and viewport.active_tool is getattr(self, "simetria", None)
            QTimer.singleShot(0, lambda: self._activar_simetria(viewport, not abierta))
            return True
        if clave == "empujar":               # lo mismo que Desplazar ▸ empujar/tirar
            QTimer.singleShot(0, lambda: self._accion_empujar(viewport))
            return True
        if clave in _seleccion.SEMI:
            QTimer.singleShot(0, lambda: self._accion_semi(viewport, clave))
            return True
        if clave == "agrupar":               # Crear: abre su submenú
            self.panel = None if self.panel == "agrupar" else "agrupar"
            self._sincronizar()
            return True
        if clave in ACCIONES_SEL:            # actúan ya sobre la selección
            self.panel = None
            QTimer.singleShot(0, lambda: self._accion_sel(viewport, clave))
            self._sincronizar()
            return True
        if clave in PEGADOS:
            self.panel = None
            QTimer.singleShot(0, lambda: self._accion_chico(viewport, clave))
            self._sincronizar()
            return True
        if clave == "cerrar_app":
            QTimer.singleShot(0, self._cerrar_ingetrazo)
            return True
        if clave in ORDENES_CHICAS:
            QTimer.singleShot(0, lambda: self._accion_chico(viewport, clave))
            return True
        if clave in _diana.PROPIAS or clave in ("volver", "cerrar_rueda"):
            QTimer.singleShot(0, lambda: self._usar_diana(viewport, clave))
            return True
        if clave in self.bases or clave in MODOS or clave == "pintar":
            # Una herramienta de la barra de dibujo (también desde Seleccionar o la barra de modificar)
            # y su submenú; Pintar es la nativa.
            self.panel = clave if clave in MODOS else None
            if clave == "pintar":
                QTimer.singleShot(0, lambda: self._pintar(viewport, self.modo["pintar"]))
            elif clave == "seleccionar" and viewport.active_tool is self._select_nativo():
                # Ya se está seleccionando con el de IngeTrazo: basta con el
                # submenú (cambiar de herramienta lo soltaría).
                self.base = clave
                viewport.flash_status(_tr(self._mensaje_base()), 6000)
            else:
                self.base = clave
                QTimer.singleShot(0, lambda: self._activar_base(viewport))
            self._sincronizar()
            return True
        viewport.flash_status(_tr("El botón «{0}» no hace nada aquí.", clave), 3000)
        return True

    def _capa_bajo(self) -> float:
        """«Abajo»: del cursor al tope de la pastilla de la capa."""
        return self.tema.abajo_anillo + CAPA_HUECO

    def _con_props(self) -> bool:
        """El extracto de propiedades va en su rectángulo (con los cajetines
        plegados es un botoncito)."""
        return self._es_sel and not self.tema.cajetines_plegados

    # -- la diana (vistas, zoom, deshacer / rehacer y buscador) --
    # Encima del anillo, a la escala del tema; o, plegada, debajo de él
    # cuando se abre con el botón «vistas» del hueco izquierdo. Las funciones
    # de ``_diana`` trabajan sin escala: los puntos se pasan por
    # ``_con_escala`` / ``_sin_escala``.
    def _e(self) -> float:
        return self.tema.escala_diana

    def _diana_dy(self) -> float:
        return self._r_ext() + DIANA_HUECO + self._e() * _diana.ABAJO

    def _diana_viva(self) -> bool:
        return not self.tema.diana_plegada or self.panel == "vistas"

    def _diana_centro(self, c) -> QPointF:
        if not self.tema.diana_plegada:
            return QPointF(c.x(), c.y() - self._diana_dy())
        if self.tema.rueda:                  # la rueda, centrada en el ojo (dentro del visor)
            q = self._centro_ojo(c)
            r = _diana.RUEDA_R + 12.0
            dx, dy = self._meter_dentro(c, QRectF(q.x() - r, q.y() - r, 2.0 * r, 2.0 * r))
            return QPointF(q.x() + dx, q.y() + dy)
        return QPointF(c.x(), self._y_panel(c) + 8.0 + self._e() * _diana.ARRIBA)

    def _rueda_abierta(self) -> bool:
        """La rueda está abierta (temas A y B): el anillo y sus botoncitos no están."""
        return self.tema.rueda and self.panel == "vistas"

    def _submenu_centrado(self) -> bool:
        """El submenú de una herramienta (o de Escalar / Rotar) sale a la
        derecha del cursor (temas A y B): se esconde todo menos el ojo azul."""
        return self.tema.submenu_centrado and (self.panel in MODOS or self.panel in CON_CAJETINES)

    def _centrado_con_cajetines(self) -> bool:
        """Todos los submenús llevan encima el recuadro de lo seleccionado
        (debajo va la línea de órdenes; la capa y el navegador no salen)."""
        return self._submenu_centrado()

    def _cajetines_visibles(self) -> bool:
        return not self._sin_arcos()

    def _sin_arcos(self) -> bool:
        return self._rueda_abierta() or self._submenu_centrado() or self._camara_abierta()

    def _camara_abierta(self) -> bool:
        """El subrosco de la Cámara (en lugar de la rueda)."""
        return self.tema.rueda and self.panel == "camara"

    # -- los ojos (temas A y B): pasar por el de arriba abre la rueda --
    def _centro_ojo(self, c, cual: str | None = None) -> QPointF:
        """El ojo ``cual``; sin decir cuál, el de la rueda (que con el
        submenú en rosco va centrado encima de él)."""
        if cual is None:
            q = self._ojo_sobre_rosco(c)
            if q is not None:
                return q
            cual = self._ojo_de("rueda") or "arriba"
        angulo, donde, _color = OJOS[cual]
        T = self.tema
        r = T.r_ext + OJO_R + 2.0 if donde == "borde" else (T.r2[0] + T.r2[1]) / 2.0
        a = math.radians(angulo)
        return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))

    def _ojo_sobre_rosco(self, c):
        """El ojo de la rueda encima del submenú en rosco, o None. Al abrir la
        rueda desde él, la rueda sale en ese mismo sitio."""
        if not (self.tema.rueda and self.submenus_radiales):
            return None
        if self._submenu_centrado():
            g = self._panel(c)
            if g is None or not g.get("radial"):
                return None
            q = QPointF(g["ojo"])
            self._ojo_rosco = q - c
            return q
        desde = getattr(self, "_ojo_rosco", None)
        if self.panel == "vistas" and desde is not None:
            return c + desde
        return None

    def _sigue_rosco(self) -> bool:
        """El submenú en rosco (temas con el submenú al centro) va con el
        ratón: fuera de él lo acompaña, dentro (o en su ojo) se queda quieto."""
        return (self.submenus_radiales and self._submenu_centrado() and self.fijo
                and not self.anclada and self.ancla is not None)

    def _llevar_rosco(self, p) -> bool:
        """El rosco se queda quieto dentro de él, en el hueco hasta el puntero
        o rodeándolo (a ``ROSCO_MARGEN`` por arriba, abajo y los lados). Si
        el ratón sale de esa zona, la arrastra con él lo justo, en cada
        movimiento (sin saltos). True = movido."""
        if not self._sigue_rosco() or self._zona_quieta(p):
            return False
        g = self._panel()
        if g is not None:
            m = g["marco"]
            hueco = 0.0 if self.sitio_submenu == "centro" else self.distancia_submenu + 6.0
            zona = QRectF(QPointF(m.left() - hueco - ROSCO_MARGEN,
                                  m.top() - ROSCO_MARGEN),
                          QPointF(m.right() + ROSCO_MARGEN, m.bottom() + ROSCO_MARGEN))
            if zona.contains(p):
                return False
            dx = p.x() - min(max(p.x(), zona.left()), zona.right())
            dy = p.y() - min(max(p.y(), zona.top()), zona.bottom())
            self.ancla = QPointF(self.ancla.x() + dx, self.ancla.y() + dy)
            return True
        self.ancla = QPointF(p)
        self._panel_raton = QPointF(0.0, 0.0)
        return True

    def _ojo_en(self, p, cual: str | None = None) -> bool:
        if self.ancla is None or p is None:
            return False
        q = self._centro_ojo(self.ancla, cual)
        r = self._r_ojo_centrado() if cual is None and self._submenu_centrado() else OJO_R
        return math.hypot(p.x() - q.x(), (p.y() - q.y()) * 1.4) <= r + 1.0

    def _r_ojo_centrado(self) -> float:
        """El ojo azul con el submenú al centro: en rosco crece con él."""
        return OJO_R * (self.escala_rosco / 100.0 if self.submenus_radiales else 1.0)

    @staticmethod
    def _pintar_ojo(painter, q, color, con_sombra: bool = True, r: float = OJO_R) -> None:
        """Un ojo con el iris de ``color`` (``r``: medio ancho)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        x, y = q.x(), q.y()
        ojo = QPainterPath()
        ojo.moveTo(x - r, y)
        ojo.quadTo(x, y - r * 0.95, x + r, y)
        ojo.quadTo(x, y + r * 0.95, x - r, y)
        ojo.closeSubpath()
        if con_sombra:
            sombra(painter, ojo, 1.5, 2.0)
        painter.setPen(QPen(_flotante.color_linea(painter, q), 1.5))   # temas C a N: su color
        painter.setBrush(QBrush(BLANCO))
        painter.drawPath(ojo)
        painter.setPen(QPen(QColor(color).darker(140), 1.2))
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(q, r * 0.5, r * 0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(11, 42, 20)))
        painter.drawEllipse(q, r * 0.22, r * 0.22)
        painter.setBrush(QBrush(BLANCO))
        painter.drawEllipse(QPointF(x - r * 0.16, y - r * 0.2), r * 0.1, r * 0.1)
        painter.restore()

    def _gesto_diana(self, p) -> None:
        """Tema F: pasar con el ratón por el ojo abre la rueda, centrada en
        él; salir de la rueda la cierra y vuelven los arcos."""
        if not self.tema.rueda or self.ancla is None or p is None:
            return
        if self.panel == "vistas":
            dc = self._diana_centro(self.ancla)
            if (math.hypot(p.x() - dc.x(), p.y() - dc.y()) > _diana.RUEDA_R + 12.0
                    and not _diana.en_zona_abanico(dc, p)):
                self._salir_de_rueda()
            return
        if self._ojo_de("rueda") is None:
            return                           # ningún ojo abre la rueda
        if (self.panel is None or self._submenu_centrado()) and self._ojo_en(p):
            self.panel = "vistas"

    def _salir_de_rueda(self) -> None:
        """Cierra la rueda: vuelve al submenú desde el que se abrió (en el
        mismo sitio) o, si no había, al anillo entero."""
        _diana.cerrar_abanico()
        antes, self._antes_rueda = getattr(self, "_antes_rueda", None), None
        if antes is None:
            self.panel = None
            return
        clave, d = antes
        self.panel = clave
        self._panel_raton = QPointF(d)

    def _con_escala(self, cc, q) -> QPointF:
        """Un punto de la diana sin escala, llevado a la pantalla."""
        e = self._e()
        return QPointF(cc.x() + (q.x() - cc.x()) * e, cc.y() + (q.y() - cc.y()) * e)

    def _sin_escala(self, cc, p) -> QPointF:
        e = self._e()
        return QPointF(cc.x() + (p.x() - cc.x()) / e, cc.y() + (p.y() - cc.y()) / e)

    def _transformar_diana(self, painter, cc) -> None:
        e = self._e()
        if e != 1.0:
            painter.translate(cc)
            painter.scale(e, e)
            painter.translate(-cc)

    def _pintar_diana(self, painter, cc, bajo, para_clic, buscador) -> None:
        painter.save()
        self._transformar_diana(painter, cc)
        self.diana.pintar(painter, cc, bajo, para_clic, buscador=buscador)
        painter.restore()

    def _pintar_diana_bajo(self, painter, cc, bajo, buscador) -> None:
        painter.save()
        self._transformar_diana(painter, cc)
        self.diana.pintar_bajo(painter, cc, bajo, buscador=buscador)
        painter.restore()

    def _mascara_diana(self, cc, buscador) -> QPainterPath:
        path = self.diana.mascara(cc, buscador=buscador)
        e = self._e()
        if e == 1.0:
            return path
        t = QTransform().translate(cc.x(), cc.y()).scale(e, e).translate(-cc.x(), -cc.y())
        return t.map(path)

    def _fila_y(self, c) -> float:
        """Con la diana plegada: la fila de la lupa, encima de los botoncitos."""
        return c.y() - self.tema.abajo_anillo - 6.0 - _diana.FILA_R

    def _cc_fila(self, c) -> QPointF:
        """Un centro de diana (sin escala) cuya fila de la lupa cae donde se
        dibuja: así valen ``centro_fila`` y el buscador de ``_diana``."""
        desde_centro = _diana.ARRIBA_BUSCA - _diana.BUSCA_H / 2.0
        if self.tema.diana_plegada:
            return QPointF(c.x(), self._fila_y(c) + desde_centro)
        cc = self._diana_centro(c)
        return QPointF(cc.x(), cc.y() + (1.0 - self._e()) * desde_centro)

    def _centro_fila(self, c, cual) -> QPointF:
        """Un botón de la fila de la lupa, en pantalla."""
        if self.tema.diana_plegada:
            return _diana.centro_fila(self._cc_fila(c), cual)
        cc = self._diana_centro(c)
        return self._con_escala(cc, _diana.centro_fila(cc, cual))

    def _chincheta_dxs(self) -> tuple:
        e = 1.0 if self.tema.diana_plegada else self._e()
        return tuple(x * e for x in _diana.CHINCHETA_X)

    def _centro_vistas(self, c) -> QPointF:
        """El botón de las vistas (diana plegada): en el hueco izquierdo."""
        return QPointF(c.x() - self.tema.cerrar_r, c.y())

    def _vistas_en(self, p) -> bool:
        T = self.tema
        if not T.diana_plegada or T.rueda or self.ancla is None or p is None:
            return False
        q = self._centro_vistas(self.ancla)
        return math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHINCHETA_R + 1.5

    def _diana_en(self, p):
        if self.ancla is None or p is None:
            return None
        c = self.ancla
        if self.tema.rueda:
            if not self._rueda_abierta():
                return None
            return _diana.rueda_parte_en(self._diana_centro(c), p)
        if self.tema.diana_plegada:
            for cual in _diana.FILA:
                q = self._centro_fila(c, cual)
                if math.hypot(p.x() - q.x(), p.y() - q.y()) <= _diana.FILA_R + 1.5:
                    return cual
            if self.panel != "vistas":
                return None
            cc = self._diana_centro(c)
            return self.diana.parte_en(cc, self._sin_escala(cc, p), buscador=False)
        # En la barra de selección el buscador lo sustituyen las propiedades.
        cc = self._diana_centro(c)
        return self.diana.parte_en(cc, self._sin_escala(cc, p), buscador=not self._es_sel)

    # -- los botoncitos pegados al anillo (encima: dibujar; debajo: selección) --
    def _chicos(self) -> dict:
        T = self.tema
        if T.rueda:
            # Lo configurado en cada uno de los doce sitios (los vacíos no se ven).
            chicos = {}
            for clave, angulo in zip(self.huecos.chicos(), self.huecos.angulos_chicos):
                if clave and clave not in chicos:
                    chicos[clave] = angulo
            return chicos
        chicos = dict(CHICOS_BARRA_DIBUJO)
        if T.diana_plegada:
            chicos.update(CHICOS_DIANA)
        chicos.update(_seleccion.CHICOS)
        if T.cajetines_plegados:
            chicos["nav"] = CHICOS_CAJETINES["nav"]
            if self._es_sel:
                chicos["propiedades"] = CHICOS_CAJETINES["propiedades"]
        return chicos

    def _centro_chico(self, c, clave) -> QPointF:
        a = math.radians(self._chicos()[clave])
        r = self._r_ext() + CHICO_R + 3.0
        return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))

    def _chico_en(self, p):
        if self.ancla is None or p is None or self._sin_arcos():
            return None
        for clave in self._chicos():
            q = self._centro_chico(self.ancla, clave)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHICO_R + 1.5:
                return clave
        return None

    def _pintar_chicos(self, painter, c, bajo, para_clic) -> None:
        relieve = self.tema.relieve
        transparente = self.tema.glifos
        for clave in self._chicos():
            q = self._centro_chico(c, clave)
            marcado = clave == "chincheta" and self.anclada
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            if relieve and para_clic:
                bola = QPainterPath()
                bola.addEllipse(q, CHICO_R, CHICO_R)
                sombra(painter, bola, 1.5, 2.0)
            if transparente:
                # Temas B a N: solo el aro, con su halo blanco.
                painter.setPen(QPen(HALO, 3.2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(q, CHICO_R, CHICO_R)
            painter.setPen(_flotante.pluma_borde(painter, 2.0 if marcado else 1.4))
            if clave == bajo:
                painter.setBrush(QBrush(_flotante.relleno_redondo(True)))
            elif marcado:
                painter.setBrush(QBrush(_flotante.relleno_redondo(False)))
            elif relieve:
                painter.setBrush(relieve_redondo(q, CHICO_R))
            elif transparente:
                # En la ventanita, un relleno casi invisible para que reciba
                # el clic; en el cursor nada (Windows lo pintaría negro).
                painter.setBrush(QBrush(QColor(255, 255, 255, 3)) if para_clic else Qt.NoBrush)
            else:
                painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(q, CHICO_R, CHICO_R)
            painter.translate(q)
            painter.scale(0.6, 0.6)
            glifo(painter, "chincheta_clavada" if marcado else clave, QPointF(0.0, 0.0),
                  ROJO_OSCURO if clave == bajo else NEGRO)
            painter.restore()

    def _bajo_chico(self, viewport, clave) -> QPoint:
        """Posición global justo debajo del botón (para su menú/panel)."""
        q = self._centro_clave(self.ancla, clave)
        return viewport.mapToGlobal(QPoint(round(q.x() - CHICO_R), round(q.y() + CHICO_R + 2)))

    def _accion_chico(self, viewport, clave) -> None:
        win = self.app.window
        try:
            if clave == "pegar":
                win._on_paste()                               # interno de 0.5.8
                self._orden_hecha(viewport)
            elif clave == "pegar_sitio":
                win._on_paste_in_place()
                self._orden_hecha(viewport)
            elif clave == "notas":
                self._abrir_tareas(viewport)
            elif clave == "tiempo":
                self._abrir_tiempo(viewport)
            elif clave == "calc":
                self._abrir_calculadora(viewport)
            elif clave == "guardar":
                self._guardar_dibujo(viewport)
            elif clave == "copia":
                from ._copia import VentanaCopia
                VentanaCopia(self.app).mostrar()
            elif clave == "texto":
                self._activar_texto(viewport)
            elif clave == "limpia":
                self._menu_limpia(viewport, self._bajo_chico(viewport, clave))
            elif clave in CHICOS_DIANA:
                self.diana.usar(viewport, clave)
            elif clave in ("chincheta", "limpia"):
                self._pulsar_chincheta(viewport, clave)
            elif clave == "preferencias":
                self._menu_preferencias(viewport, self._bajo_chico(viewport, clave))
            elif clave == "apagar":
                self._menu_apagar(viewport, self._bajo_chico(viewport, clave))
            elif clave in _diana.FILA:
                self._usar_diana(viewport, clave)
            elif clave == "nav":
                self._abrir_navegador(viewport)
            elif clave == "propiedades":
                _seleccion.abrir_info(self)
            else:
                self._accion_chico_sel(viewport, clave)
        except Exception:  # noqa: BLE001
            log.exception("fallo en el botoncito %s", clave)
            viewport.flash_status(_tr("Rosco LT: no se pudo {0}.", NOMBRES_CHICOS.get(clave, clave).lower()), 4000)
        self._sincronizar()

    def _abrir_tareas(self, viewport) -> None:
        """Las Tareas (pieza ``_notas``), como su botón: la ventana
        en la última pestaña usada (tareas del modelo o de IngeTrazo)."""
        listas = getattr(self.app.window, "_rosco_lt_tareas", None)
        if listas is None or not callable(getattr(listas, "ventana", None)):
            viewport.flash_status(_tr("Las tareas no se pudieron cargar (mira el registro)."), 5000)
            return
        listas.ventana().mostrar()

    def _menu_preferencias(self, viewport, pos) -> None:
        """Preferencias de IngeTrazo e Info del modelo (sus órdenes de menú)."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self.app.window)
        prefs = m.addAction(_tr("Preferencias de IngeTrazo…"))
        info = m.addAction(_tr("Información del dibujo"))
        elegida = m.exec(pos)
        self.tragar_clic()
        if elegida is None:
            return
        textos = PREFERENCIAS if elegida is prefs else INFO_MODELO
        if not _seleccion.disparar_menu(self.app.window, textos):
            viewport.flash_status(_tr("No encontré la orden «{0}» de IngeTrazo.", textos[0]), 4000)

    def _cerrar_ingetrazo(self) -> None:
        """El botón de cerrar IngeTrazo: como cerrar la ventana (pregunta si
        hay cambios sin guardar)."""
        try:
            self.app.window.close()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo cerrar IngeTrazo")

    def _guardar_dibujo(self, viewport) -> None:
        """Guardar de IngeTrazo (si aún no tiene nombre, pide dónde)."""
        win = self.app.window
        guardar = getattr(win, "_on_save", None)                 # interno de 0.5.8
        if callable(guardar):
            guardar()
        elif not _seleccion.disparar_menu(win, ("Guardar", "Save")):
            viewport.flash_status(_tr("No encontré la orden Guardar de IngeTrazo."), 4000)

    def _activar_texto(self, viewport) -> None:
        """El Texto propio (``_texto``): bloques de texto editables; la barra
        se esconde mientras dura (queda su ventanita de opciones)."""
        try:
            if getattr(self, "texto", None) is None:
                from ._texto import Texto
                self.texto = Texto(self)
            self.panel = None
            viewport.set_active_tool(self.texto)
            viewport.setFocus()
            self.escondida = True
            self._tool_escondida = self._ultima_tool = viewport.active_tool
            self._sincronizar()
            return
        except Exception:  # noqa: BLE001 — queda el Texto de IngeTrazo
            log.exception("no se pudo abrir el Texto propio")
        win = self.app.window
        accion = (getattr(win, "_tool_actions", None) or {}).get("text")
        if accion is not None:
            accion.trigger()
            viewport.setFocus()
        elif not _seleccion.disparar_menu(win, ("Texto", "Text")):
            viewport.flash_status(_tr("No encontré la herramienta Texto de IngeTrazo."), 4000)

    def _junto_a_diana(self, viewport, tam: QSize) -> QPoint:
        """Dónde sale un panel de tamaño ``tam`` (el Control de tiempo, la
        calculadora): al lado de la diana, sin salirse de la zona de dibujo."""
        from ._tiempo import junto_a
        zona = QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())
        c = self.ancla
        if c is None:
            return junto_a(QCursor.pos(), 0.0, tam, zona)
        # Por fuera de los botoncitos (ver ``_centro_chico``), con un poco de aire.
        radio = self._r_ext() + 2.0 * CHICO_R + 3.0 + 10.0
        centro = viewport.mapToGlobal(QPoint(round(c.x()), round(c.y())))
        return junto_a(centro, radio, tam, zona)

    def _panel_de_tiempo(self):
        if self.panel_tiempo is None:
            from ._tiempo import PanelTiempo
            self.panel_tiempo = PanelTiempo(self.app, self.crono, alcerrar=self.tragar_clic)
        return self.panel_tiempo

    def abrir_tiempo_junto(self, ventana) -> None:
        """El Reloj desde las Tareas: el panel de siempre, pegado a la derecha
        de su ventana (a la izquierda si no cabe). Otro clic lo cierra."""
        from PySide6.QtGui import QGuiApplication
        panel = self._panel_de_tiempo()
        if panel.isVisible():
            panel.hide()
            return
        if panel.recien_cerrado():
            return
        panel.adjustSize()
        g = ventana.frameGeometry()
        pos = QPoint(g.right() + 6, g.top() + 60)
        pantalla = QGuiApplication.screenAt(g.center())
        if pantalla is not None and pos.x() + panel.width() > pantalla.availableGeometry().right():
            pos = QPoint(max(0, g.left() - panel.width() - 6), g.top() + 60)
        panel.mostrar(pos)

    def _abrir_tiempo(self, viewport) -> None:
        panel = self._panel_de_tiempo()
        # Interruptor: abierto (también con la chincheta), otro clic lo cierra;
        # el clic que acaba de cerrar el desplegable no lo vuelve a abrir.
        if panel.isVisible():
            panel.hide()
            return
        if panel.recien_cerrado():
            return
        panel.adjustSize()
        panel.mostrar(self._junto_a_diana(viewport, panel.size()))

    def _abrir_calculadora(self, viewport) -> None:
        if self.calculadora is None:
            from ._calculadora import Calculadora
            self.calculadora = Calculadora(self.app.window)
        calc = self.calculadora
        if calc.isVisible():
            calc.raise_()
            calc.activateWindow()
            return
        calc.mostrar(self._junto_a_diana(viewport, calc.size()))

    def _menu_limpia(self, viewport, pos) -> None:
        """Pantalla limpia por partes (``_limpia``): cada cosa se marca al
        quitarla; «Quitar todo» pasa a «Mostrar todo» con todo quitado."""
        from PySide6.QtWidgets import QMenu
        from ._limpia import PARTES, Limpieza, icono_interruptor
        if self.limpieza is None:
            self.limpieza = Limpieza(self.app.window)
        limpia = self.limpieza
        m = QMenu(self.app.window)
        for parte, texto in PARTES:
            a = m.addAction(_tr(texto))
            a.setCheckable(True)
            a.setChecked(limpia.esta_quitado(parte))
            a.setData(parte)
        m.addSeparator()
        todo = limpia.todo_quitado()
        interruptor = m.addAction(icono_interruptor(todo), _tr("Mostrar todo" if todo else "Quitar todo"))
        f = interruptor.font()
        f.setBold(True)
        interruptor.setFont(f)
        elegida = m.exec(pos)
        self.tragar_clic()
        if elegida is None:
            return
        if elegida is interruptor:
            limpia.todo(not todo)
        else:
            limpia.poner(elegida.data(), elegida.isChecked())
        self._sincronizar()

    def _accion_chico_sel(self, viewport, clave) -> None:
        if clave == "opciones":
            q = self._centro_clave(self.ancla, clave)
            pos = viewport.mapToGlobal(QPoint(round(q.x()), round(q.y() + CHICO_R + 2)))
            try:
                from . import _panel_opciones
                _panel_opciones.abrir(self, pos)
            except Exception:  # noqa: BLE001 — si el panel falla, el menú de siempre
                log.exception("no se pudo abrir el panel de opciones")
                try:
                    _seleccion.menu_opciones(self, pos)
                except Exception:  # noqa: BLE001
                    log.exception("fallo en las opciones de Seleccionar")
            self._sincronizar()
            return
        self._accion_sel(viewport, clave)

    # -- el extracto de propiedades (barra de selección) --
    def _rect_props(self, c) -> QRectF:
        """Encima de todo (donde en la barra de dibujo va el buscador); con el submenú al
        centro, encima del submenú y centrado con él."""
        if self._centrado_con_cajetines():
            g = self._panel(c)
            if g is not None:
                m = g["marco"]
                cx = g["centro"].x() if g.get("radial") else m.center().x()
                return QRectF(cx - PROPS_W / 2.0, m.top() - CAJETIN_HUECO - PROPS_H,
                              PROPS_W, PROPS_H)
        return QRectF(c.x() - PROPS_W / 2.0, c.y() - self._arriba_todo(), PROPS_W, PROPS_H)

    def _props_en(self, p) -> bool:
        visible = self._centrado_con_cajetines() or (self._con_props() and self._cajetines_visibles())
        return (visible and self.ancla is not None and p is not None
                and self._rect_props(self.ancla).adjusted(-2, -2, 2, 2).contains(p))

    @staticmethod
    def _firma_sel(viewport):
        """Lo que, si no cambia, deja igual el extracto y la capa."""
        try:
            scene = viewport.scene
            return (id(scene), frozenset(id(e) for e in scene.selection),
                    len(viewport.history.undo_stack))
        except Exception:  # noqa: BLE001
            return None

    def _datos_sel(self) -> tuple:
        """``(resumen, capa)`` de la selección. Recorrer la selección (medidas,
        áreas, capas) en cada movimiento del ratón era lento con muchas
        entidades: se guarda y solo se rehace cuando cambia algo."""
        vp = self.app.viewport
        firma = self._firma_sel(vp)
        if (firma is not None and self._cache_sel is not None
                and self._cache_sel[0] == firma):
            return self._cache_sel[1], self._cache_sel[2]
        try:
            resumen = _seleccion.resumen(vp)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo resumir la selección")
            resumen = ("Selección", "—")
        try:
            capa = _capas.capa_de_seleccion(vp.scene)
        except Exception:  # noqa: BLE001
            capa = None
        self._cache_sel = (firma, resumen, capa)
        return resumen, capa

    def _texto_props(self) -> tuple:
        if not self.app.viewport.scene.selection:
            return ("Nada seleccionado", "Selecciona algo para ver sus datos")
        return self._datos_sel()[0]

    def _pintar_props(self, painter, c, encima: bool) -> None:
        r = self._rect_props(c)
        linea, medidas = self._texto_props()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ROJO, 1.4))
        painter.setBrush(QBrush(QColor(255, 240, 240, 245) if encima
                                else QColor(255, 255, 255, 240)))
        painter.drawRoundedRect(r, 8.0, 8.0)
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        painter.setFont(f)
        fm = QFontMetricsF(f)
        caja = r.adjusted(10.0, 3.0, -10.0, -3.0)
        alto = caja.height() / 2.0
        painter.setPen(TINTA)
        painter.drawText(QRectF(caja.left(), caja.top(), caja.width(), alto),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         fm.elidedText(_tr(linea), Qt.ElideRight, caja.width()))
        painter.setPen(QColor(95, 94, 90))
        painter.drawText(QRectF(caja.left(), caja.top() + alto, caja.width(), alto),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         fm.elidedText(_tr(medidas), Qt.ElideRight, caja.width()))
        painter.restore()

    def _usar_diana(self, viewport, parte) -> None:
        if parte == "cerrar_rueda":
            self._pulsar_chincheta(viewport, "cerrar")
            return
        if parte == "volver":                # de la rueda al anillo entero (o a su submenú)
            self._salir_de_rueda()
            self._sincronizar()
            return
        # La lupa lleva también los menús: el clic abre el árbol de menús de
        # IngeTrazo bajo ella; el buscador sale al teclear con la barra quieta
        # (``_buscar``), no con el clic.
        if parte == "buscar" and self.ancla is not None:
            q = (self._centro_clave(self.ancla, "buscar") if self.tema.rueda
                 else self._centro_fila(self.ancla, "buscar"))
            self._abrir_menus(viewport, q)
            return
        if parte == "camara":                # su subrosco, en lugar de la rueda
            _diana.cerrar_abanico()
            self.panel = "camara"
            self._sincronizar()
            return
        if parte == "seccion":
            # Al poner el plano, pasa a Desplazarlo (``_vigilar_seccion``).
            self._seccion_vigila = self._n_secciones(viewport)
            self._tras_seccion = False
        # El centro solo sirve para colocar el buscador: el que tiene la
        # fila de la lupa donde se dibuja.
        cc = self._cc_fila(self.ancla) if self.ancla is not None else None
        self.diana.usar(viewport, parte, cc)

    # -- plano de sección: puesto el plano, Desplazar; el derecho en vacío repite --
    @staticmethod
    def _n_secciones(vp) -> int:
        try:
            return len(vp.scene.section_planes)
        except Exception:  # noqa: BLE001
            return 0

    def _tool_seccion(self):
        return (getattr(self.app.window, "_tools", None) or {}).get("section")

    def _vigilar_seccion(self) -> None:
        """Del reloj: con el plano de sección pedido desde el rosco, en cuanto
        aparece el plano nuevo se selecciona y se activa Desplazar."""
        vp = self.app.viewport
        antes = getattr(self, "_seccion_vigila", None)
        tool = vp.active_tool
        if antes is not None:
            if self._n_secciones(vp) <= antes:
                # IngeTrazo pasa a Seleccionar un momento antes de pedir el
                # nombre del plano: solo se da por dejada pasados 2 s fuera
                # de la orden y sin el cuadro abierto.
                if tool is self._tool_seccion() or self._nombrando_seccion():
                    self._seccion_fuera = None
                elif getattr(self, "_seccion_fuera", None) is None:
                    self._seccion_fuera = time.monotonic()
                elif time.monotonic() - self._seccion_fuera > 2.0:
                    self._seccion_vigila = None   # se cambió de orden sin poner plano
                    self._seccion_fuera = None
                return
            self._seccion_fuera = None
            if self._nombrando_seccion():
                return       # el plano ya está, pero falta su nombre (luego pone Seleccionar)
            # Plano nuevo (IngeTrazo pasa solo a Seleccionar con él elegido).
            self._seccion_vigila = None
            try:
                nuevo = list(vp.scene.section_planes)[-1]
                vp.scene.select([nuevo], mode="replace")
                vp.notify_scene_changed()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo seleccionar el plano de sección nuevo")
            self._tras_seccion = True
            self._accion_semi(vp, "move")
            vp.flash_status(_tr("Plano de sección puesto: desplázalo. Clic derecho en vacío: otro plano."), 5000)
            return
        if getattr(self, "_tras_seccion", False) and self._semi_activa(vp) != "move":
            self._tras_seccion = False            # se dejó Desplazar

    @staticmethod
    def _nombrando_seccion() -> bool:
        """Hay un cuadro abierto (el que pide el nombre del plano, en el
        idioma que sea): todavía no se ha puesto."""
        return QApplication.activeModalWidget() is not None

    def _repetir_seccion(self, vp) -> None:
        """Clic derecho en vacío tras poner un plano: otra vez Plano de sección."""
        self._tras_seccion = False
        if self._cancelable(vp) and self._en_marcha(vp):
            self._cancelar(vp)
        try:
            vp.scene.select([], mode="replace")
            vp.notify_scene_changed()
        except Exception:  # noqa: BLE001
            pass
        self.panel = None
        self._usar_diana(vp, "seccion")
        self._sincronizar()

    # -- los menús de IngeTrazo en árbol --
    def _centro_menus_sel(self, c) -> QPointF:
        """En la barra de selección: a la izquierda de la chincheta."""
        return QPointF(c.x() + MENUS_SEL_X, self._y_chincheta(c))

    def _menus_sel_en(self, p) -> bool:
        if (not self._es_sel or self.tema.diana_plegada or self.ancla is None
                or p is None):
            return False
        q = self._centro_menus_sel(self.ancla)
        return math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHINCHETA_R + 1.5

    def _pintar_menus_sel(self, painter, c, bajo=None) -> None:
        from . import _iconos
        q = self._centro_menus_sel(c)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ROJO, 1.3))
        painter.setBrush(QBrush(QColor(245, 185, 185) if bajo == "menus"
                                else QColor(255, 255, 255, 235)))
        painter.drawEllipse(q, CHINCHETA_R, CHINCHETA_R)
        _iconos.pintar(painter, "menus", q, 13.0)
        painter.restore()

    def _abrir_menus(self, viewport, q) -> None:
        """El árbol de menús, desplegado bajo el botón (``q``, px del visor)."""
        try:
            if self.menus_arbol is None:
                from ._menus import MenusArbol
                self.menus_arbol = MenusArbol(self)
            pos = viewport.mapToGlobal(QPoint(round(q.x() - 12.0), round(q.y() + 12.0)))
            self.menus_arbol.abrir(pos)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo abrir el árbol de menús")
            viewport.flash_status(_tr("Rosco LT: no se pudo abrir el árbol de menús."), 4000)

    def _encuadre(self, viewport) -> None:
        tool = viewport.active_tool
        if not (self._es_base(tool) or self._es_sel):
            return
        self._tras_encuadre = tool
        self._soltar()
        viewport.set_nav_mode("pan")
        viewport.flash_status(_tr("Encuadre: arrastra con el botón izquierdo; al "
                              "soltar vuelves a la barra."), 6000)

    def _buscar(self, viewport, texto: str) -> None:
        """Una letra con la barra fija: el buscador de órdenes, ya escrito."""
        cc = self._cc_fila(self.ancla) if self.ancla is not None else None
        try:
            self.diana.buscar(viewport, texto, cc)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo abrir el buscador de órdenes")

    def _salir_encuadre(self) -> None:
        vp = self.app.viewport
        tool, self._tras_encuadre = self._tras_encuadre, None
        if tool is None or getattr(vp, "nav_mode", None) != "pan":
            return
        vp.set_nav_mode(None)
        vp.set_active_tool(tool)
        self._soltar()
        vp.flash_status(_tr(self._mensaje_base()), 4000)
        self._sincronizar()

    # -- cursor y búfer --
    def anotar_cursor(self, screen) -> None:
        self.cursor_px = QPointF(screen)

    def cursor_movido(self, screen, tool) -> None:
        # La barra la mueve el filtro de eventos (sin esperar al snap);
        # aquí solo se anota el cursor para la ventanita de medidas.
        self.anotar_cursor(screen)

    def _buffer_cambiado(self, texto: str) -> None:
        self.buffer = texto or ""

    def _buffer(self, viewport) -> str:
        interno = getattr(viewport, "_value_buffer", None)
        return interno if isinstance(interno, str) else self.buffer

    # -- el selector: cuándo se ve --
    def _select_nativo(self):
        return (getattr(self.app.window, "_tools", None) or {}).get("select")

    def _semi_activa(self, viewport):
        """El botón del arco de dentro (Desplazar, Escalar, Simetría, Rotar)
        de la herramienta activa, o None (Alinear es de la barra de modificar)."""
        barra = self._barra_modificar()
        if barra is None:
            return None
        try:
            clave = barra._clave_activa(viewport)
        except Exception:  # noqa: BLE001
            return None
        boton = barra._boton_de(clave)
        return boton if clave != "align" and boton in _seleccion.SEMI else None

    def _estado_semi(self, viewport):
        """Lo que cambia el dibujo del arco de dentro (botón activo y modos)."""
        barra = self._barra_modificar()
        if barra is None:
            return None
        return (self._semi_activa(viewport), tuple(sorted(barra.modo.items())))

    def _accion_semi(self, viewport, clave) -> None:
        """Un botón del arco de dentro: la herramienta de la barra de modificar (con su
        modo); si ya era la activa, vuelve a Seleccionar. Desplazar, Escalar
        y Rotar dejan abierto su submenú."""
        barra = self._barra_modificar()
        if barra is None:
            viewport.flash_status(_tr("La barra de modificar no está disponible."), 4000)
            return
        antes = self._semi_activa(viewport)
        if clave == "move" and barra.modo.get("move") in ("alinear", "empujar/tirar"):
            barra.modo["move"] = "mover"     # esos tienen su propio sitio
        # Empujar tiene botón propio: desde él, Desplazar cambia de orden.
        desde_empujar = clave == "move" and barra._clave_activa(viewport) == "pushpull"
        if desde_empujar:
            antes = None
        try:
            barra.activar(clave, cambiar=desde_empujar)
        except Exception:  # noqa: BLE001
            log.exception("La barra de modificar no pudo activar %s", clave)
        from ._arco import MODOS as MODOS_SEMI
        self.panel = clave if clave != antes and clave in MODOS_SEMI else None
        if clave == "flip" and antes != "flip":
            # Simetría no tiene submenú: se esconde todo hasta que termine.
            self.escondida = True
            self._tool_escondida = self._ultima_tool = viewport.active_tool
        self._sincronizar()

    def _accion_empujar(self, viewport) -> None:
        """El botón de Empujar/Tirar: con su submenú (el de Desplazar), hasta el
        primer punto; pulsarlo otra vez vuelve a Seleccionar."""
        barra = self._barra_modificar()
        if barra is None:
            viewport.flash_status(_tr("La barra de modificar no está disponible."), 4000)
            return
        if barra._clave_activa(viewport) == "pushpull":
            self.panel = None
            barra._seleccionar()
            self._sincronizar()
            return
        barra.modo["move"] = "empujar/tirar"
        barra._activar_empujar()
        self.panel = "move"
        self._sincronizar()

    def _dibujar_piezas(self, viewport, painter) -> None:
        """Overlay de la Simetría y el Texto propios, solo con su orden activa."""
        for pieza in (getattr(self, "simetria", None), getattr(self, "texto", None)):
            if pieza is not None and viewport.active_tool is pieza:
                pieza.dibujar(viewport, painter)

    def _activar_simetria(self, viewport, con_submenu: bool = True) -> None:
        """La Simetría propia (``_simetria``) con su submenú (modo del plano,
        hotspots, copia y eje), que sigue a la vista hasta el primer clic en
        el dibujo, como el de las demás órdenes. Pulsar otra vez su botón con
        el submenú abierto lo cierra."""
        if getattr(self, "simetria", None) is None:
            from ._simetria import Simetria
            self.simetria = Simetria(self)
        if viewport.active_tool is not self.simetria:
            viewport.set_active_tool(self.simetria)
        viewport.setFocus()
        self.panel = "flip" if con_submenu else None
        self.escondida = False
        self._sincronizar()

    def _modo_sel(self, viewport) -> bool:
        """El anillo en modo selección: Seleccionar (el de IngeTrazo o el de
        la barra de dibujo) con algo seleccionado, o una herramienta de la barra de modificar (con o
        sin selección) esperando su primer punto; salvo que la barra de modificar esté
        abierto suelto."""
        tool = viewport.active_tool
        if tool is None:
            return False
        seleccionar = tool is self.bases["seleccionar"] or tool is self._select_nativo()
        semi = not seleccionar and self._semi_activa(viewport) is not None
        if not (seleccionar or semi):
            return False
        if self._lazo is not None or (seleccionar and not viewport.scene.selection):
            return False
        barra = self._barra_modificar()
        if semi:
            from ._arco import _ocupada
            if _ocupada(tool) or getattr(barra, "_forzada", False) or getattr(barra, "anclada", False):
                return False
            return True
        return not (barra is not None and getattr(barra, "_forzada", False)
                    and tool is self._select_nativo())

    def _en_juego(self, viewport) -> bool:
        if self.escondida:                   # Simetría: todo oculto hasta terminar
            return False
        if self.dormida:                     # tras una orden, hasta que se la llame
            return False
        if self.anclada:
            # Anclada: siempre a la vista, salvo mientras la barra de modificar (suelto)
            # está abierto (sale donde se pulsó su botón, encima de esta).
            barra = self._barra_modificar()
            return not (barra is not None and not getattr(barra, "anclada", False)
                        and barra._en_juego(viewport))
        if (getattr(viewport, "nav_mode", None) is not None
                or getattr(viewport, "_box_active", False)):
            return False
        tool = viewport.active_tool
        if (self.panel == "seleccionar" and self.arco_visible
                and (tool is self._select_nativo() or tool is self.bases["seleccionar"])):
            # El submenú de Seleccionar sigue a la vista aunque IngeTrazo haya
            # puesto su Seleccionar nativo y no haya nada seleccionado.
            return True
        if self._modo_sel(viewport):
            return True
        if self.arco_visible and self._pintando(viewport):
            return True
        simetria = getattr(self, "simetria", None)
        if simetria is not None and tool is simetria:
            # Como una base: a la vista mientras no hay un punto A a medias;
            # haciendo copias, oculta hasta que se acaba con Esc.
            return self.arco_visible and simetria.a is None and not simetria.copiando
        ctl = self._alinear()
        if ctl is not None and tool is ctl.tool:
            # Alinear, como las demás: a la vista hasta su primer punto.
            return self.arco_visible and not ctl.tool.puntos
        return self.arco_visible and self._es_base(tool) and not self.ocupada(tool)

    def _arco_activo(self, viewport) -> bool:
        """La barra está fija (ventanita) y se le puede hacer clic."""
        return self.fijo and self.ancla is not None and self._en_juego(viewport)

    def _sincronizar(self) -> None:
        """Al moverse, la barra es el cursor; parada, la ventanita fija."""
        self._pendiente = False
        if self.win is None or not _interruptor.ENCENDIDA:
            if self.linea is not None:
                self.linea.hide()
            return
        vp = self.app.viewport
        try:
            self._sincronizar_linea(vp)
        except Exception:  # noqa: BLE001 — la línea nunca rompe la barra
            log.exception("fallo en la línea de órdenes")
        if self._pulso_espera is not None:
            if QApplication.mouseButtons() & Qt.LeftButton:
                return                       # pulsando en vacío: nada cambia hasta soltar
            # El soltar se perdió (fuera de la ventana, por ejemplo).
            self._fin_pulso_espera(QPointF(vp.mapFromGlobal(QCursor.pos())))
        try:
            self._sincronizar_medidas(vp)
        except Exception:  # noqa: BLE001 — la ventanita nunca rompe la barra
            log.exception("fallo en la ventanita de medidas")
        try:                                 # Desplazar · copia: copias seguidas hasta Esc
            barra = self._barra_modificar()
            if barra is not None:
                barra.vigilar_copias(vp)
        except Exception:  # noqa: BLE001
            log.exception("fallo vigilando la copia múltiple")
        if (self._tras_encuadre is not None
                and getattr(vp, "nav_mode", None) != "pan"):
            self._tras_encuadre = None       # el usuario salió del encuadre a mano
        sel = self._modo_sel(vp)
        if sel and self._semi_activa(vp) is not None:
            # Lo que hace la barra de modificar al repasar: en modo copia, la copia de la
            # nativa vuelve a quedar armada tras cada operación.
            try:
                self._barra_modificar()._rearmar_copia(vp)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo rearmar la copia")
        # Dibujar ↔ selección: el anillo es el mismo, así que sigue donde
        # está (con su submenú); solo cambian el buscador y la capa.
        self._es_sel = sel
        if self.cancelar is not None:
            self.cancelar.vigilar(vp)
            self.cancelar.win.vigilar_pulsacion()
        self.win.vigilar_pulsacion()
        if self.win.pulsando:
            # Clic sostenido sobre la barra: ni se suelta ni vuelve hasta
            # soltar el botón, aunque el ratón salga de ella.
            return
        # El historial: la herramienta que cambia y, de vez en cuando, las
        # órdenes nuevas (extensiones cargadas después).
        tool = vp.active_tool
        if tool is not self._ultima_tool:
            self._ultima_tool = tool
            # La foto de la nativa recién activada (para notar su orden a medias).
            self._foto_tool0 = {id(tool): _foto_tool(tool)} if tool is not None else {}
            try:
                self._apuntar_herramienta(vp, tool)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo apuntar la herramienta")
        self._tic_acciones += 1
        if self._tic_acciones % 40 == 0:
            self._enganchar_acciones()
        if self.aplicar_capa:
            self._aplicar_capa_a_nuevos(vp)
        # Al terminar una operación (o cambiar de herramienta) vuelve el
        # anillo entero: sin submenú y sin el escondite de Simetría.
        marcha = self._en_marcha(vp)
        # Lo que entra en el historial con una herramienta de la barra es una
        # orden hecha (con el tope del historial no crece: se mira también
        # cuál es el último paso).
        pila = getattr(vp.history, "undo_stack", None)
        vista = (len(pila), id(pila[-1]) if pila else None) if pila is not None else None
        if (vista is not None and self._pila_vista is not None
                and (vista[0] > self._pila_vista[0]
                     or vista[0] == self._pila_vista[0] and vista[1] != self._pila_vista[1])
                and self._de_la_barra(vp)):
            self._orden_hecha(vp)
        self._pila_vista = vista
        if self.dormida:
            # Dormida: una selección nueva (Seleccionar) la despierta; con una
            # orden que sigue, no (Desplazar coge lo que pinchas).
            ids = self._ids_sel(vp)
            if ids != self._sel_dormida:
                self._sel_dormida = ids
                if ids and not self._seguir_orden(vp):
                    self.dormida = False
        ident = self.herramienta if tool is self.push else tool
        if ident is not self._tool_orden0:   # otra orden: «un paso atrás» empieza de cero
            self._tool_orden0 = ident
            self._pila_orden0 = None
        if self._estaba_en_marcha and not marcha:
            self.panel = None
            self.escondida = False
            self._pila_ultima = self._pila_al_empezar
            self._pila_al_empezar = None
            if self._obra:
                self._orden_hecha(vp)        # la línea y demás, al acabar
        elif marcha and not self._estaba_en_marcha:
            # Empieza una orden: lo que haya en el historial ahora.
            try:
                self._pila_al_empezar = len(vp.history.undo_stack)
            except Exception:  # noqa: BLE001
                self._pila_al_empezar = None
        self._estaba_en_marcha = marcha
        if self.escondida and tool is not self._tool_escondida:
            self.escondida = False
        en_juego = self._en_juego(vp)
        # Anclada con la chincheta se queda aunque otra aplicación tenga el
        # foco; solo se va con la ventana minimizada.
        ver = (en_juego and (app_activa() or self.anclada) and vp.isVisible()
               and not self.app.window.isMinimized())
        if not ver:
            if self.win.isVisible():
                self.win.hide()
            self._quitar_cursor(vp)
            if not en_juego:
                self._soltar()
            return
        if self.fijo and not self.anclada and not self._raton_en_zona(vp):
            # El ratón se ha ido a los menús, las barras o la barra de estado:
            # la barra fija no se queda fuera del visor (anclada, sí).
            self._soltar()
            if self.win.isVisible():
                self.win.hide()
            return
        if self.fijo and self.ancla is not None:
            self._quitar_cursor(vp)
            self._cursor_sobre_barra(vp)
            self.win.colocar(self.ancla)
            self._fijar_mascara()
            estado = self._estado_fondo() + (self.ancla.x(), self.ancla.y(), self._bajo)
            if not self.win.isVisible():
                self.win.show()
                self.win.update()
            elif estado != self._estado_pintado:
                self.win.update()
            self._estado_pintado = estado
            self._anima_vigilar()
        else:
            if self.win.isVisible():
                self.win.hide()
            self._poner_cursor(vp)
        self._traza_rotar(vp)

    def _traza_rotar(self, vp) -> None:
        """TEMPORAL (2.39.0): si el rosco aparece con Rotar como herramienta,
        se anota el estado en %APPDATA%/IngeTrazo/rosco_lt_rotar.log, para ver por
        qué sale al volver al visor con el giro en marcha."""
        try:
            tool = vp.active_tool
            visible = bool(self.win.isVisible() or self._cursor_puesto)
            antes, self._traza_visible = getattr(self, "_traza_visible", False), visible
            if not visible or antes or type(tool).__name__ != "RotateTool":
                return
            import os
            import traceback
            from ._arco import _ocupada
            local = vp.mapFromGlobal(QCursor.pos())
            linea = (f"{time.strftime('%H:%M:%S')} start={getattr(tool, 'start_point', None) is not None} "
                     f"ocupada={_ocupada(tool)} marcha={self._en_marcha(vp)} modo_sel={self._modo_sel(vp)} "
                     f"dormida={self.dormida} escondida={self.escondida} panel={self.panel} fijo={self.fijo} "
                     f"anclada={self.anclada} win={self.win.isVisible()} cursor={self._cursor_puesto} "
                     f"sel={len(vp.scene.selection)} raton=({local.x()},{local.y()}) "
                     f"en_visor={vp.rect().contains(local)} activa={type(QApplication.activeWindow()).__name__}\n")
            pila = "".join(traceback.format_stack(limit=9)[:-1])
            ruta = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "IngeTrazo", "rosco_lt_rotar.log")
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(linea + pila + "\n")
        except Exception:  # noqa: BLE001 — la traza nunca molesta
            pass

    # -- la línea de órdenes --
    def _texto_linea(self, vp) -> tuple | None:
        """``(título, texto)`` del paso en que va la orden activa, o None."""
        from . import _linea
        tool = vp.active_tool
        n = self._clics_orden
        ctl = self._alinear()
        if ctl is not None and tool is ctl.tool:
            from ._alinear import PASOS as PASOS_ALINEAR
            k = min(len(tool.puntos), 3)
            texto = PASOS_ALINEAR[k]
            return _tr("Alinear · paso {0} de 4", k + 1), texto[:1].upper() + texto[1:] + "."
        s = getattr(self, "simetria", None)
        if s is not None and tool is s:
            if not vp.scene.selection:
                texto = "Clic en lo que quieras reflejar (o selecciónalo antes)."
            elif s.copiando:
                texto = "Cada clic deja otra copia reflejada. Esc termina."
            elif s.editor:
                texto = "Clic pone un hotspot; clic sobre uno lo quita. H sale."
            elif s.modo == "puntos":
                texto = ("Clic en el punto B: el plano queda en medio de los dos."
                         if s.a is not None else "Clic en el punto A.")
            else:
                texto = "Mueve el ratón hasta el plano y haz clic para reflejar."
            return "Simetría", texto
        texto_tool = getattr(self, "texto", None)
        if texto_tool is not None and tool is texto_tool:
            texto = _tr(texto_tool._ayuda()).replace(_tr("Texto: "), "", 1)
            return "Texto", texto[:1].upper() + texto[1:]
        if tool is self.push:
            texto = _tr(MSG_ALTURA).replace(_tr("Altura: "), "", 1)
            return "Altura", texto[:1].upper() + texto[1:]
        clave = modo = None
        if tool is self.bases["seleccionar"] or tool is self._select_nativo():
            clave, modo = "seleccionar", self.modo.get("seleccionar")
        elif self._es_base(tool) and tool is not self.espera:
            clave, modo = tool.clave, self.modo.get(tool.clave)
        else:
            boton = self._semi_activa(vp)
            barra = self._barra_modificar()
            if boton is not None and barra is not None:
                clave, modo = boton, barra.modo.get(boton)
                if clave == "move" and modo == "copia" and getattr(barra, "_multicopia", None) and n:
                    return "Desplazar · copia", "Cada clic deja otra copia. Esc termina."
            elif self._pintando(vp):
                clave, modo = "pintar", self.modo.get("pintar")
        if clave is not None:
            nombre = NOMBRES.get(clave, clave).split(":")[0]
            paso = _linea.paso(clave, modo, n, nombre)
            if paso is not None:
                return paso
        # Una orden sin tabla (de IngeTrazo o de otra extensión).
        nombre = str(getattr(tool, "name", "") or "Orden")
        try:
            texto = str(tool.status_clause() or "")
        except Exception:  # noqa: BLE001
            texto = ""
        return nombre, texto or "Esc cancela."

    def _sincronizar_linea(self, vp) -> None:
        """Se ve con cualquier orden elegida y con un submenú abierto: debajo
        del submenú y, sin él, centrada y pegada al borde de abajo del visor."""
        from . import _linea
        tool = vp.active_tool
        if tool is not self._linea_tool:
            self._linea_tool = tool
            self._clics_orden = 0
        elif (self._clics_orden and not self._en_marcha(vp)
              and not (QApplication.mouseButtons() & Qt.LeftButton)):
            self._clics_orden = 0            # acabó: otra vez el primer paso
        submenu = self._submenu_centrado() and self.panel is not None
        ver = ((self._cancelable(vp) and tool is not self.espera) or submenu)
        if (not ver or not vp.isVisible() or self.app.window.isMinimized()
                or not (app_activa() or self.anclada)):
            if self.linea is not None:
                self.linea.hide()
            return
        datos = self._texto_linea(vp)
        if datos is None:
            if self.linea is not None:
                self.linea.hide()
            return
        if self.linea is None:
            self.linea = _linea.LineaOrden(self.app.window)
        g = self._panel() if submenu and self.fijo and self.ancla is not None else None
        if g is not None:
            m = g["marco"]
            cx = g["centro"].x() if g.get("radial") else m.center().x()
            medio = _linea.ANCHO / 2.0
            x = max(medio + 4.0, min(cx, vp.width() - medio - 4.0))
            y = max(4.0, min(m.bottom() + CAJETIN_HUECO, vp.height() - _linea.ALTO_RESERVA - 4.0))
            self.linea.poner(datos[0], datos[1], vp.mapToGlobal(QPoint(round(x), round(y))))
        else:
            abajo = vp.mapToGlobal(QPoint(vp.width() // 2, vp.height()))
            self.linea.poner(datos[0], datos[1], abajo, pegada=True)

    def _cursor_sobre_barra(self, vp) -> None:
        """Sobre los botones, el mismo cursor que en el visor (el lápiz o el de
        la orden), no la flecha de Windows."""
        cursor = vp.cursor()
        mapa = cursor.pixmap()
        clave = (int(cursor.shape().value), 0 if mapa.isNull() else mapa.cacheKey())
        if clave != self._cursor_barra:
            self._cursor_barra = clave
            self.win.setCursor(cursor)
            if self.cancelar is not None:
                self.cancelar.win.setCursor(cursor)

    def _raton_en_zona(self, viewport) -> bool:
        """El ratón está en el visor o sobre la propia barra (que puede
        asomar fuera de él); con un desplegable abierto, también vale."""
        if QApplication.activePopupWidget() is not None:
            return True
        pos = QCursor.pos()
        if viewport.rect().contains(viewport.mapFromGlobal(pos)):
            return True
        if self.win is not None and self.win.isVisible():
            local = self.win.mapFromGlobal(pos)
            mascara = self.win.mask()
            if mascara.isEmpty():
                return self.win.rect().contains(local)
            return mascara.contains(local)
        return False

    def _poner_cursor(self, viewport) -> None:
        """Los arcos como cursor del visor (los hace el sistema: sin retraso)."""
        tool = viewport.active_tool
        T = self.tema
        forma = None if self._es_sel else self._forma_lapiz(viewport)
        clave = (T.clave, self.escala, self._es_sel, self.diana.proyeccion_actual(),
                 getattr(tool, "icon", None), self.base, self._pintando(viewport), forma,
                 self._barra_modificar() is None, round(viewport.devicePixelRatioF(), 2),
                 self._estado_semi(viewport))
        if self._cursor is None or clave != self._cursor_clave:
            if T.cursor_ligero:
                # Solo el anillo: cabe en el cursor por hardware de Windows.
                arriba = abajo = medio = T.r_ext + 6.0
                dibujar = lambda p, c: self._pintar_banda(p, c, completo=False)  # noqa: E731
            else:
                abajo = T.abajo_anillo + 6.0
                dibujar = self._pintar_banda
                if T.diana_plegada:
                    arriba, medio = abajo, T.r_ext + 6.0
                else:
                    arriba = self._diana_dy() + self._e() * _diana.ARRIBA + 6.0
                    medio = max(self._medio_arcos(), self._e() * _diana.MEDIO) + 6.0
            # En la barra de dibujo el puntero del centro es el lápiz de la herramienta.
            puntero = None if forma is None else self._lapiz(viewport, forma)
            self._cursor = cursor_compuesto(viewport, tool, dibujar, medio, arriba, abajo,
                                            puntero=puntero)
            self._cursor_clave = clave
        viewport.setCursor(self._cursor)
        self._cursor_puesto = True

    # -- el cursor lápiz de la barra de dibujo --
    def _forma_lapiz(self, viewport):
        """La forma junto al lápiz para la herramienta activa de la barra de dibujo, o
        None si la activa no es de la barra de dibujo."""
        tool = viewport.active_tool
        if tool is self.push:
            return "altura"
        if not self._es_base(tool):
            return None
        if tool is self.espera:
            return ""
        return FORMA_LAPIZ.get(self.base, "")

    @staticmethod
    def _lapiz(viewport, forma):
        from ._lapiz import cursor
        return cursor(forma, max(1.0, float(viewport.devicePixelRatioF())))

    def _instalar_lapiz(self, viewport) -> None:
        """El cursor de las herramientas de la barra de dibujo es el lápiz: el visor pone
        el cursor de la herramienta con ``_apply_tool_cursor`` (cambio de
        herramienta, Ctrl, al confirmar…); se envuelve para que en la barra de dibujo sea
        el lápiz (y, si la barra es el cursor, la barra)."""
        original = getattr(viewport, "_apply_tool_cursor", None)    # interno de 0.5.8
        if not callable(original) or getattr(viewport, "_rosco_lt_lapiz", False):
            return

        def aplicar(*args, **kwargs):
            if not _interruptor.ENCENDIDA:
                return original(*args, **kwargs)
            try:
                if self._cursor_puesto and self._cursor is not None:
                    viewport.setCursor(self._cursor)
                    return None
                forma = self._forma_lapiz(viewport)
                if forma is not None:
                    viewport.setCursor(self._lapiz(viewport, forma))
                    return None
            except Exception:  # noqa: BLE001 — queda el cursor nativo
                log.exception("no se pudo poner el cursor lápiz")
            return original(*args, **kwargs)

        viewport._apply_tool_cursor = aplicar
        viewport._rosco_lt_lapiz = True

    def _quitar_cursor(self, viewport) -> None:
        if self._cursor_puesto:
            self._cursor_puesto = False
            restaurar_cursor(viewport)

    def _fijar(self) -> None:
        """El ratón se ha parado: la barra se queda fija donde está."""
        vp = self.app.viewport
        if (self.fijo or self.cursor_px is None or not self._en_juego(vp)
                or not vp.underMouse()):
            return
        self.fijo = True
        self.ancla = QPointF(self.cursor_px)
        # Cerca del borde del visor, el anillo entra lo justo para verse entero.
        try:
            dx, dy = self._meter_dentro(self.ancla, self._mascara_path(self.ancla).boundingRect())
            self.ancla = QPointF(self.ancla.x() + dx, self.ancla.y() + dy)
        except Exception:  # noqa: BLE001 — se queda donde el ratón
            log.exception("no se pudo meter la barra en el visor")
        self._bajo = None
        self._sincronizar()

    def _soltar(self) -> None:
        """Vuelve al modo cursor (la barra acompaña al ratón). Anclada se
        queda donde está: solo se cierra el submenú."""
        self.panel = None
        self._bajo = None
        self._estado_pintado = None
        if self.anclada:
            return
        self.fijo = False
        self.ancla = None

    # -- la chincheta --
    def _y_chincheta(self, c) -> float:
        """En la fila de la lupa (con la diana plegada, encima de los
        botoncitos; si no, encima de cónica y paralela); con el extracto de
        propiedades, encima de él."""
        if self.tema.rueda:                  # sin fila: lo más alto que haya
            return c.y() - self._arriba_todo()
        if self.tema.diana_plegada:
            return self._fila_y(c)
        if not self._con_props():
            return self._centro_fila(c, "buscar").y()
        arriba = self._arriba_todo()
        if self.pos_capa == "arriba":
            arriba += CAPA_HUECO + self.tema.capa_h
        return c.y() - arriba - 15.0

    def _tope(self, c) -> float:
        """Lo más alto de la barra (px del visor)."""
        arriba = self._arriba_todo()
        if self.pos_capa == "arriba":
            arriba += CAPA_HUECO + self.tema.capa_h
        return min(c.y() - arriba, self._y_chincheta(c) - CHINCHETA_R)

    def _chincheta_en(self, p):
        """«chincheta», «limpia» (su fila) o «cerrar» (junto al cursor)."""
        if self.ancla is None:
            return None
        if self._cerrar_en(p):
            return "cerrar"
        if self.tema.rueda:                  # chincheta y limpia son botoncitos
            return None
        return chincheta_en(self.ancla.x(), self._y_chincheta(self.ancla), p,
                            self._chincheta_dxs(), segundo="limpia")

    def _centro_cerrar(self, c) -> QPointF:
        """El ✕: en el hueco de la derecha entre las dos mitades del anillo."""
        return QPointF(c.x() + self.tema.cerrar_r, c.y())

    def _cerrar_en(self, p) -> bool:
        if self.ancla is None or p is None or self.tema.rueda or self._submenu_centrado():
            return False                     # en los temas A y B no hay ✕ (doble clic o Esc)
        q = self._centro_cerrar(self.ancla)
        return math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHINCHETA_R + 1.5

    def _pulsar_chincheta(self, viewport, clave) -> None:
        if clave == "limpia":
            # Temas sin rueda: el botón va en la fila de la chincheta.
            q = centros_chincheta(self.ancla.x(), self._y_chincheta(self.ancla),
                                  self._chincheta_dxs(), "limpia")["limpia"]
            self._menu_limpia(viewport, viewport.mapToGlobal(
                QPoint(round(q.x() - CHICO_R), round(q.y() + CHICO_R + 2))))
            return
        if clave == "cerrar":
            self.anclada = False
            self._soltar()
            self.cerrar_barra_dibujo()
            if viewport.scene.selection:
                # La barra de selección: cerrarla es dejar de seleccionar.
                limpiar = getattr(viewport.scene, "clear_selection", None)
                if callable(limpiar):
                    limpiar()
                    viewport.update()
            viewport.flash_status(_tr("Rosco LT: barra cerrada."), 2500)
            self._sincronizar()
            return
        self.anclada = not self.anclada
        viewport.flash_status(
            _tr("Rosco LT: barra anclada aquí (la chincheta la suelta; ✕ la cierra)."
            if self.anclada else "Rosco LT: barra suelta: vuelve a seguir al ratón."), 4000)
        self._sincronizar()

    def _mascara_path(self, c) -> QPainterPath:
        """Lo que acepta clics con el anillo centrado en ``c`` (px del visor)."""
        T = self.tema
        path = QPainterPath()
        if self._rueda_abierta():
            # Solo la rueda (y la etiqueta): el anillo y lo demás se esconden.
            path.addPath(_diana.rueda_mascara(self._diana_centro(c)))
        elif self._camara_abierta():
            pass                                 # solo el subrosco (su marco, abajo)
        elif self._submenu_centrado():
            # El ojo azul (el submenú entra con el panel) y lo seleccionado.
            r = self._r_ojo_centrado()
            path.addEllipse(self._centro_ojo(c), r + 2.0, r * 0.75 + 2.0)
            path.addRect(self._rect_props(c))
        else:
            path.addPath(sector(c, T.r1[0], T.r2[1], T.a_arriba, T.barrido))
            path.addPath(sector(c, T.r1[0], T.r2[1], T.a_abajo, T.barrido))
            for _j, _k, r_int, r_ext, a0, b, _tam in self._lados():
                path.addPath(sector(c, r_int, r_ext, a0, b))
            if T.rueda:
                for cual in OJOS:
                    path.addEllipse(self._centro_ojo(c, cual), OJO_R + 2.0, OJO_R * 0.75 + 2.0)
            else:
                path.addEllipse(self._centro_cerrar(c), CHINCHETA_R + 1.0, CHINCHETA_R + 1.0)
            if T.rueda:
                pass
            elif T.diana_plegada:
                path.addEllipse(self._centro_vistas(c), CHINCHETA_R + 1.0, CHINCHETA_R + 1.0)
                for cual in _diana.FILA:
                    path.addEllipse(self._centro_fila(c, cual), _diana.FILA_R + 1.0, _diana.FILA_R + 1.0)
            if self._diana_viva():
                path.addPath(self._mascara_diana(self._diana_centro(c),
                                                 buscador=not T.diana_plegada and not self._es_sel))
            path.addRect(self._rect_capa(c))
            if not T.cajetines_plegados:
                path.addRect(self._rect_nav(c))
            for clave in self._chicos():
                path.addEllipse(self._centro_chico(c, clave), CHICO_R + 1.0, CHICO_R + 1.0)
            if not T.rueda:
                mascara_chincheta(path, c.x(), self._y_chincheta(c), self._chincheta_dxs(), "limpia")
            if self._es_sel and not T.diana_plegada:
                path.addEllipse(self._centro_menus_sel(c), CHINCHETA_R + 1.0, CHINCHETA_R + 1.0)
            if self._con_props():
                path.addRect(self._rect_props(c))
        g = self._panel(c)
        if g is not None:
            path.addRect(g["marco"])
        # Sitio para la etiqueta más ancha, siempre: así la máscara no cambia
        # (ni se recalcula) cada vez que el ratón pasa a otro botón.
        alto = rect_etiqueta(self.win.font(), "", self._pos_etiqueta(c))
        ancho = self._ancho_etiqueta()
        path.addRect(QRectF(c.x() - ancho / 2.0, alto.top(), ancho, alto.height()))
        return path

    def _fijar_mascara(self) -> None:
        self.win.fijar_mascara(self._mascara_path(self.ancla),
                               clave=(self.tema.clave, self.escala, self._es_sel, self.pos_capa,
                                      self.panel, len(self.historial), self._sitio_submenu()))

    def _ancho_etiqueta(self) -> float:
        if self._etiqueta_w is None:
            textos = [*NOMBRES.values(), *NOMBRES_CHICOS.values(),
                      "Navegador: grupos y componentes del modelo",
                      "Pasar la selección a otra capa", "Capa donde va lo que dibujas",
                      *(texto_chincheta(k, b) for k in ("chincheta", "cerrar", "limpia")
                        for b in (False, True)),
                      *(_tr("{0} (falta la barra de modificar)", _tr(NOMBRES[k].split(':')[0]))
                        for k in _seleccion.SEMI),
                      *(self._texto_icono(k) for k in self.huecos.todas()
                        if k not in _huecos.SOLO_OJOS)]
            f = self.win.font()
            self._etiqueta_w = max(rect_etiqueta(f, t, QPointF(0.0, 0.0)).width()
                                   for t in textos)
        return self._etiqueta_w

    def _arriba_todo(self) -> float:
        """Del ancla al tope del buscador (o de la fila de la lupa, con la
        diana plegada; o del extracto de propiedades, si lo hay)."""
        T, e = self.tema, self._e()
        if T.rueda:                          # sin fila: justo encima de los botoncitos
            arriba = T.abajo_anillo + 6.0
        elif T.diana_plegada:
            arriba = T.abajo_anillo + 6.0 + 2.0 * _diana.FILA_R
        elif self._con_props():
            arriba = self._diana_dy() + e * _diana.ARRIBA
        else:
            return self._diana_dy() + e * _diana.ARRIBA_BUSCA
        if self._con_props():
            arriba += _diana.BUSCA_HUECO + PROPS_H
        return arriba

    def _pos_etiqueta(self, c) -> QPointF:
        # Por encima de todo (buscador, chincheta y, si va arriba, la capa):
        # el submenú va debajo del anillo. Con la rueda abierta, encima de ella.
        if self._rueda_abierta():
            dc = self._diana_centro(c)
            return QPointF(dc.x(), dc.y() - _diana.RUEDA_R - 20.0)
        return QPointF(c.x(), self._tope(c) - 14.0)

    # -- la pastilla de la capa --
    def _rect_capa(self, c) -> QRectF:
        """Bajo el anillo («abajo»: a la izquierda de la vertical, o
        centrada si los cajetines van plegados), encima del buscador
        («arriba») o a la izquierda del anillo, a la altura del cursor
        («izquierda»). Con el submenú al centro (Seleccionar, Desplazar,
        Escalar…), debajo del submenú y centrada con él."""
        T = self.tema
        w, h = T.capa_w, T.capa_h
        if self._centrado_con_cajetines():
            g = self._panel(c)
            if g is not None:
                m = g["marco"]
                cx = g["centro"].x() if g.get("radial") else m.center().x()
                x = cx - w / 2.0 if T.cajetines_plegados else cx - CAPA_HUECO / 2.0 - w
                return QRectF(x, m.bottom() + CAJETIN_HUECO, w, h)
        if self.pos_capa == "izquierda":
            derecha = c.x() - self._r_ext() - CAPA_HUECO
            return QRectF(derecha - w, c.y() - h - 2.0, w, h)
        if self.pos_capa == "abajo":
            if T.cajetines_plegados:
                return QRectF(c.x() - w / 2.0, c.y() + self._capa_bajo(), w, h)
            return QRectF(c.x() - CAPA_HUECO / 2.0 - w, c.y() + self._capa_bajo(), w, h)
        tope = c.y() - self._arriba_todo()
        return QRectF(c.x() - w / 2.0, tope - CAPA_HUECO - h, w, h)

    def _rect_nav(self, c) -> QRectF:
        """La pastilla del Navegador: a la derecha de la de la capa,
        simétricas respecto de la vertical del cursor (con los cajetines
        plegados no hay pastilla: es un botoncito)."""
        if self.tema.cajetines_plegados:
            return QRectF()
        return self._rect_capa(c).translated(self.tema.capa_w + CAPA_HUECO, 0.0)

    def _capa_en(self, p) -> bool:
        return (self.ancla is not None and p is not None and self._cajetines_visibles()
                and self._rect_capa(self.ancla).adjusted(-2, -2, 2, 2).contains(p))

    def _nav_en(self, p) -> bool:
        return (not self.tema.cajetines_plegados and self.ancla is not None and p is not None
                and self._cajetines_visibles()
                and self._rect_nav(self.ancla).adjusted(-2, -2, 2, 2).contains(p))

    def tragar_clic(self) -> None:
        """Un desplegable de la barra se acaba de cerrar: el clic que lo
        cerró (Windows lo entrega también al visor) se descarta."""
        self._tragar_hasta = time.monotonic() + 0.4

    def _abrir_navegador(self, viewport) -> None:
        if self.ancla is None:
            return
        if self.tema.cajetines_plegados:          # bajo su botoncito
            q = self._centro_clave(self.ancla, "nav")
            derecha, abajo = q.x() + CHICO_R, q.y() + CHICO_R + 2.0
        else:
            r = self._rect_nav(self.ancla)
            derecha, abajo = r.right(), r.bottom() + 2.0
        # Alineado por la derecha: se abre hacia dentro.
        pos = viewport.mapToGlobal(QPoint(round(derecha), round(abajo)))
        try:
            from ._navegador import ANCHO
            self.navegador.abrir(viewport, QPoint(pos.x() - ANCHO, pos.y()))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo abrir el navegador")
            viewport.flash_status(_tr("Rosco LT: no se pudo abrir el Navegador."), 4000)

    def _texto_capa(self) -> str:
        if self._es_sel:
            nombre = self._datos_sel()[1] or _tr("varias")
        else:
            nombre = self.capas.actual(self.app.viewport.scene)
        return _tr("Capa: {0}", _tr(nombre))

    def _pintar_capa(self, painter, c, encima: bool) -> None:
        r = self._rect_capa(c)
        self._pastilla(painter, r, self._texto_capa(), encima, "capas")
        if self.aplicar_capa:
            # Aplicar capa en marcha: un punto rojo sobre el icono.
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(BLANCO, 1.0))
            painter.setBrush(QBrush(ROJO))
            painter.drawEllipse(QPointF(r.left() + 23.0, r.top() + 5.0), 3.5, 3.5)
            painter.restore()

    def _pintar_nav(self, painter, c, encima: bool) -> None:
        self._pastilla(painter, self._rect_nav(c), "Navegador", encima, "arbol")

    @staticmethod
    def _pastilla(painter, r, texto_pastilla, encima: bool, icono: str) -> None:
        """Un desplegable de la barra: icono, texto y ▾."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ROJO, 1.4))
        painter.setBrush(QBrush(QColor(255, 240, 240, 240) if encima
                                else QColor(255, 255, 255, 235)))
        painter.drawRoundedRect(r, r.height() / 2.0, r.height() / 2.0)
        x, y = r.left() + 14.0, r.center().y()
        painter.setPen(QPen(NEGRO, 1.3))
        from . import _iconos
        if _iconos.pintar(painter, icono, QPointF(x, y), 17.0):
            pass
        elif icono == "capas":
            # Tres hojas apiladas.
            for dy, relleno in ((3.0, NEGRO), (0.0, QColor(255, 255, 255)),
                                (-3.0, QColor(255, 255, 255))):
                painter.setBrush(QBrush(relleno))
                painter.drawPolygon(QPolygonF([QPointF(x - 6.0, y + dy), QPointF(x, y + dy - 3.0),
                                               QPointF(x + 6.0, y + dy), QPointF(x, y + dy + 3.0)]))
        else:
            # Un árbol: la raíz y dos ramas.
            painter.setBrush(QBrush(NEGRO))
            painter.drawRect(QRectF(x - 6.0, y - 6.5, 4.5, 4.5))
            painter.drawLine(QPointF(x - 3.75, y - 2.0), QPointF(x - 3.75, y + 4.0))
            painter.drawLine(QPointF(x - 3.75, y), QPointF(x, y))
            painter.drawLine(QPointF(x - 3.75, y + 4.0), QPointF(x, y + 4.0))
            painter.drawRect(QRectF(x + 0.5, y - 2.0, 4.0, 4.0))
            painter.drawRect(QRectF(x + 0.5, y + 2.0, 4.0, 4.0))
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        painter.setFont(f)
        painter.setPen(TINTA)
        caja = QRectF(r.left() + 26.0, r.top(), r.width() - 44.0, r.height())
        painter.drawText(caja, Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetricsF(f).elidedText(_tr(texto_pastilla), Qt.ElideRight, caja.width()))
        painter.setPen(ROJO)
        painter.drawText(QRectF(r.right() - 18.0, r.top(), 12.0, r.height()),
                         Qt.AlignCenter, "▾")
        painter.restore()

    def _menu_capas(self, viewport) -> None:
        if self.ancla is None:
            return
        r = self._rect_capa(self.ancla)
        pos = viewport.mapToGlobal(QPoint(round(r.left()), round(r.bottom()) + 2))
        try:
            self.capas.menu(viewport, pos, seleccion=self._es_sel)
        except Exception:  # noqa: BLE001
            log.exception("fallo en el desplegable de capas")
        self._sincronizar()

    def _zona_quieta(self, p) -> bool:
        """Con la barra fija: el cursor está eligiendo (dentro del anillo,
        de la diana o del submenú), así que la barra no se mueve."""
        if self.ancla is None or p is None:
            return False
        d = p - self.ancla
        if self._rueda_abierta():
            dc = self._diana_centro(self.ancla)
            return math.hypot(p.x() - dc.x(), p.y() - dc.y()) <= _diana.RUEDA_R + 16.0
        if self._submenu_centrado():
            # El submenú, el ojo azul y el camino entre los dos.
            g = self._panel()
            if g is not None and g["marco"].adjusted(-10.0, -10.0, 10.0, 10.0).contains(p):
                return True
            q = self._centro_ojo(self.ancla)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= OJO_R + 10.0:
                return True
            if g is not None and g.get("radial"):
                return False                 # el ojo va encima del rosco, dentro de su marco
            return abs(d.x()) <= 40.0 and q.y() - 10.0 <= p.y() <= self.ancla.y()
        zona_r = self._r_ext() + 6.0
        if math.hypot(d.x(), d.y()) <= zona_r:
            return True
        # La columna que sube hasta el buscador (diana, deshacer y rehacer) o
        # hasta la fila de la lupa.
        e = self._e()
        ancho_col = max(zona_r, e * _diana.MEDIO + 8.0, e * _diana.BUSCA_W / 2.0 + 6.0,
                        max(abs(x) for x in _diana.FILA.values()) + _diana.FILA_R + 8.0)
        tope = self._tope(self.ancla) - self.ancla.y() - 6.0       # con la chincheta
        if abs(d.x()) <= ancho_col and tope <= d.y() <= 0.0:
            return True
        # Los botoncitos de encima del arco (y el hueco hasta ellos).
        for clave in self._chicos():
            q = self._centro_chico(self.ancla, clave)
            if math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHICO_R + 8.0:
                return True
        # La pastilla de la capa y el hueco hasta ella (bajando hacia ella la
        # barra no se suelta; un clic en el hueco sigue siendo del dibujo).
        capa = self._rect_capa(self.ancla)
        nav = self._rect_nav(self.ancla)
        if not nav.isNull():
            capa = capa.united(nav)
        if capa.adjusted(-10.0, -10.0, CAPA_HUECO + 10.0, 10.0).contains(p):
            return True
        medio_capa = (self.tema.capa_w / 2.0 if self.tema.cajetines_plegados
                      else self.tema.capa_w + CAPA_HUECO / 2.0)
        if (self.pos_capa == "abajo" and abs(d.x()) <= medio_capa + 10.0
                and 0.0 <= d.y() <= capa.bottom() - self.ancla.y()):
            return True
        g = self._panel()
        if g is None:
            return False
        if self.panel in PANELES_OJO:
            return self._en_historial(p)     # el panel de un ojo (historial, ayuda), al lado
        # El submenú (o la diana plegada) y todo el hueco entre el anillo y
        # él, a lo ancho del submenú o del anillo (lo que sea mayor): pasar
        # de un botón al submenú nunca lo cierra.
        ancho = max(g["marco"].width() / 2.0, self._r_ext()) + 10.0
        return (abs(d.x()) <= ancho and 0.0 <= d.y() <= g["marco"].bottom() - self.ancla.y() + 10.0)

    def _icono_en(self, p):
        if self._sin_arcos():
            return None
        for claves, r_int, r_ext, a0, _tam in self._bandas():
            clave = boton_en(self.ancla, p, r_int, r_ext, claves, TOLERANCIA, a0,
                             self.tema.barrido)
            if clave is not None:
                return clave or None         # un hueco vacío no es un botón
        for _j, k, r_int, r_ext, a0, b, _tam in self._lados():
            if boton_en(self.ancla, p, r_int, r_ext, (k,), 0.0, a0, b) is not None:
                return k
        return None

    def _sector_de(self, c, clave):
        """El trozo de banda del botón ``clave`` (para teñirlo), o None."""
        barrido = self.tema.barrido
        for claves, r_int, r_ext, a0, _tam in self._bandas():
            if clave in claves:
                paso = barrido / len(claves)
                return sector(c, r_int, r_ext, a0 + barrido - paso * (claves.index(clave) + 1), paso)
        for _j, k, r_int, r_ext, a0, b, _tam in self._lados():
            if k == clave:
                return sector(c, r_int, r_ext, a0, b)
        return None

    def _circulo_de(self, c, clave):
        """``(centro, radio)`` del botoncito redondo ``clave``, o None."""
        if clave in self._chicos():
            return self._centro_chico(c, clave), CHICO_R
        if clave == "cerrar":
            return self._centro_cerrar(c), CHINCHETA_R
        if clave == "vistas":
            return self._centro_vistas(c), CHINCHETA_R
        if clave in ("chincheta", "limpia"):
            centros = centros_chincheta(c.x(), self._y_chincheta(c), self._chincheta_dxs(), "limpia")
            return centros[clave], CHINCHETA_R
        if clave == "menus" and self._es_sel and not self.tema.diana_plegada:
            return self._centro_menus_sel(c), CHINCHETA_R
        return None

    def _opciones(self, clave):
        """Las opciones del submenú de ``clave`` (Agrupar es de la mitad de
        selección: sus opciones son acciones, no modos; Desplazar, Escalar y
        Rotar, los modos de la barra de modificar)."""
        if clave == "agrupar":
            return _seleccion.AGRUPAR
        if clave == "flip":
            return MODOS_FLIP
        if clave == "align":
            return MODOS_ALINEAR
        if clave in _seleccion.SEMI:
            from ._arco import MODOS as MODOS_SEMI
            return MODOS_SEMI.get(clave)
        return MODOS.get(clave)

    def _limites(self, c) -> QRectF:
        """Dónde cabe lo de la barra centrada en ``c``: la ventanita y la
        zona de dibujo (el visor), en las mismas coordenadas que ``c``."""
        caja = QRectF(c.x() - ANCLA_LOCAL.x() + 4.0, c.y() - ANCLA_LOCAL.y() + 4.0,
                      VENTANA_W - 8.0, VENTANA_H - 8.0)
        if self.ancla is not None:
            vp = self.app.viewport
            visor = QRectF(c.x() - self.ancla.x() + BORDE_VISOR, c.y() - self.ancla.y() + BORDE_VISOR,
                           vp.width() - 2.0 * BORDE_VISOR, vp.height() - 2.0 * BORDE_VISOR)
            caja = caja.intersected(visor)
        return caja

    def _meter_dentro(self, c, caja: QRectF) -> tuple:
        """Cuánto mover ``caja`` para que quepa en ``_limites`` (si es más
        grande, pegada arriba a la izquierda)."""
        L = self._limites(c)
        dx = dy = 0.0
        if caja.right() > L.right():
            dx = L.right() - caja.right()
        if caja.left() + dx < L.left():
            dx = L.left() - caja.left()
        if caja.bottom() > L.bottom():
            dy = L.bottom() - caja.bottom()
        if caja.top() + dy < L.top():
            dy = L.top() - caja.top()
        return dx, dy

    def _y_panel(self, c) -> float:
        """Donde empieza el submenú: bajo los botoncitos de abajo o, si la
        capa va «abajo», bajo la capa."""
        if self.pos_capa == "abajo":
            return c.y() + self._capa_bajo() + self.tema.capa_h + CAPA_HUECO
        return c.y() + self.tema.abajo_anillo + PANEL_HUECO

    def _panel(self, c=None):
        """Rectángulos del submenú abierto (debajo del anillo centrado en
        ``c``, el ancla si no se da), o None. «vistas» es la diana plegada:
        solo su marco (sus partes las resuelve ``_diana_en``)."""
        clave = self.panel
        c = self.ancla if c is None else c
        if c is None:
            return None
        if clave == "ayuda":
            if not self.tema.rueda:
                return None
            # Lo que se ve: la ventanita, recortada al monitor. Si la ayuda
            # no cabe entera, se acorta y se desplaza con la rueda del ratón.
            zona = self._zona_visible(c)
            total = self._ayuda_maqueta()[0]
            alto = max(120.0, min(AYUDA_MAX_H, total, zona.height()))
            self._ayuda_sobra = max(0.0, total - alto)
            self._ayuda_scroll = min(getattr(self, "_ayuda_scroll", 0.0), self._ayuda_sobra)
            # Al lado de su ojo (de serie, el verde de la derecha); si por ese
            # lado no cabe, al otro.
            cual = self._ojo_de("ayuda") or "derecha"
            q = self._centro_ojo(c, cual)
            der = c.x() + self.tema.r_ext + 14.0
            izq = c.x() - self.tema.r_ext - 14.0 - AYUDA_W
            if cual == "derecha":
                x0, y0 = der if der + AYUDA_W <= zona.right() else izq, c.y() - alto / 2.0
            elif cual == "izquierda":
                x0, y0 = izq if izq >= zona.left() else der, c.y() - alto / 2.0
            elif cual == "arriba":
                x0, y0 = q.x() - AYUDA_W / 2.0, q.y() - OJO_R - 12.0 - alto
            else:
                x0, y0 = q.x() - AYUDA_W / 2.0, q.y() + OJO_R + 12.0
            x0 = max(zona.left(), min(x0, zona.right() - AYUDA_W))
            y0 = max(zona.top(), min(y0, zona.bottom() - alto))
            fm = QFontMetricsF(self.win.font())
            pestanas, x = [], x0 + 10.0
            for i, nombre in enumerate(AYUDA_PESTANAS):
                w = fm.horizontalAdvance(_tr(nombre)) * 1.12 + 18.0
                pestanas.append((i, QRectF(x, y0 + 25.0, w, 20.0)))
                x += w + 4.0
            return {"marco": QRectF(x0, y0, AYUDA_W, alto), "chips": [], "pestanas": pestanas,
                    "titulo": QRectF(x0 + 10.0, y0 + 4.0, AYUDA_W - 44.0, 18.0),
                    "volver": QRectF(x0 + AYUDA_W - 28.0, y0 + 4.0, 18.0, 18.0)}
        if clave == "historial":
            if not self.tema.rueda:
                return None
            n = len(self.historial)
            alto = 26.0 + max(1, n) * 22.0 + 6.0
            # Al lado de su ojo (de serie, el amarillo de la izquierda).
            cual = self._ojo_de("historial") or "izquierda"
            q = self._centro_ojo(c, cual)
            if cual == "derecha":
                x0, y0 = c.x() + self.tema.r_ext + 14.0, c.y() - alto / 2.0
            elif cual == "arriba":
                x0, y0 = q.x() - HIST_W / 2.0, q.y() - OJO_R - 12.0 - alto
            elif cual == "abajo":
                x0, y0 = q.x() - HIST_W / 2.0, q.y() + OJO_R + 12.0
            else:
                x0, y0 = c.x() - self.tema.r_ext - 14.0 - HIST_W, c.y() - alto / 2.0
            return {"marco": QRectF(x0, y0, HIST_W, alto), "chips": [],
                    "titulo": QRectF(x0 + 8.0, y0 + 4.0, HIST_W / 2.0 - 20.0, 18.0),
                    "volver": QRectF(x0 + HIST_W / 2.0 - 9.0, y0 + 4.0, 18.0, 18.0),
                    "entradas": [(i, QRectF(x0 + 6.0, y0 + 26.0 + i * 22.0, HIST_W - 12.0, 19.0))
                                 for i in range(n)]}
        if clave == "vistas":
            if not self.tema.diana_plegada:
                return None
            if self.tema.rueda:
                dc, rr = self._diana_centro(c), _diana.RUEDA_R + 10.0
                return {"marco": QRectF(dc.x() - rr, dc.y() - rr, 2.0 * rr, 2.0 * rr), "chips": []}
            e = self._e()
            w = 2.0 * (e * _diana.MEDIO + 10.0)
            h = e * (_diana.ARRIBA + _diana.ABAJO) + 16.0
            return {"marco": QRectF(c.x() - w / 2.0, self._y_panel(c), w, h), "chips": []}
        if clave == "camara":
            # El subrosco de la Cámara: en lugar de la rueda, en su mismo centro.
            from . import _rosco
            e = self.escala_rosco / 100.0
            f = self.tema.panel_w / 320.0 * e
            n = len(CAMARA_OPCIONES)
            cero = _rosco.geometria(0.0, 0.0, n, False, False, f)["centro"]
            dc = self._diana_centro(c)
            g = _rosco.geometria(dc.x() - cero.x(), dc.y() - cero.y(), n, False, False, f)
            g["e"] = e
            g["chips"] = list(zip(CAMARA_OPCIONES, g["chips"]))
            return g
        if self._opciones(clave) is None:
            return None
        ancho_panel = self.tema.panel_w
        con_lados = clave in LIMITES_LADOS
        con_final = clave in CONSTRUYEN or clave == "flip"   # «al terminar» (Simetría: copia y ejes)
        fins = EXTRAS_FLIP if clave == "flip" else FINALES
        alto = 6.0 + 20.0 + (26.0 if con_lados else 0.0) + CHIP_H + 6.0 \
            + (16.0 + CHIP_H + 6.0 if con_final else 0.0) + 2.0
        radial = self.submenus_radiales
        if radial:
            # En rosco (``_rosco``): su caja, en el mismo sitio que el rectángulo.
            from . import _rosco
            e = self.escala_rosco / 100.0     # Opciones ▸ tamaño del rosco
            f = self.tema.panel_w / 320.0 * e
            _rh, r1, r3, izquierda, alto = _rosco.radios(con_lados, con_final, f)
            ancho_panel = izquierda + r1
        if self._submenu_centrado():
            # Temas A y B: a la derecha de donde estaba el ratón al abrirlo,
            # para no tapar el dibujo; con lo seleccionado encima y la línea de
            # órdenes debajo, centrados con él, sin salirse de la ventanita ni
            # de la zona de dibujo.
            from ._linea import ALTO_RESERVA, ANCHO as ANCHO_LINEA
            d = getattr(self, "_panel_raton", QPointF(0.0, 0.0))
            if self.sitio_submenu == "centro":
                # Centrado bajo el cursor (Opciones ▸ Aspecto ▸ Sitio).
                x0 = c.x() + d.x() - (izquierda if radial else ancho_panel / 2.0)
                y0 = c.y() + d.y() - ((alto - r3) if radial else alto / 2.0)
            else:
                x0 = c.x() + d.x() + self.distancia_submenu
                y0 = c.y() + d.y() + SUBMENU_DY
            cx = x0 + (izquierda if radial else ancho_panel / 2.0)
            grupo = QRectF(x0, y0, ancho_panel, alto)
            arriba = CAJETIN_HUECO + PROPS_H
            fila = max(PROPS_W, float(ANCHO_LINEA))
            grupo = grupo.united(QRectF(cx - fila / 2.0, y0 - arriba, fila,
                                        alto + arriba + CAJETIN_HUECO + ALTO_RESERVA))
            dx, dy = self._meter_dentro(c, grupo)
            x0, y0 = x0 + dx, y0 + dy
        else:
            x0, y0 = c.x() - ancho_panel / 2.0, self._y_panel(c)   # debajo del anillo
        if radial:
            modos = self._opciones(clave)
            g = _rosco.geometria(x0, y0, len(modos), con_lados, con_final, f)
            g["e"] = e
            g["chips"] = list(zip(modos, g["chips"]))
            if con_final:
                if clave == "flip":
                    # Los huecos de fuera van 100° · 180° · 220° · 140°: así
                    # quedan de arriba abajo copia, eje X, eje Y, eje Z.
                    fins = ("copia", "y", "z", "x")
                g["finales"] = list(zip(fins, g["finales"]))
            return g
        g = {"marco": QRectF(x0, y0, ancho_panel, alto),
             "titulo": QRectF(x0 + 10.0, y0 + 4.0, ancho_panel / 2.0 - 24.0, 18.0),
             "volver": QRectF(x0 + ancho_panel / 2.0 - 9.0, y0 + 4.0, 18.0, 18.0)}
        y = y0 + 26.0
        if con_lados:
            g["etiqueta"] = QRectF(x0 + 10.0, y, 120.0, 20.0)
            g["menos"] = QRectF(x0 + ancho_panel - 82.0, y + 1.0, 18.0, 18.0)
            g["mas"] = QRectF(x0 + ancho_panel - 28.0, y + 1.0, 18.0, 18.0)
            y += 26.0
        modos = self._opciones(clave)
        n = len(modos)
        ancho = (ancho_panel - 12.0 - 4.0 * (n - 1)) / n
        g["chips"] = [(m, QRectF(x0 + 6.0 + i * (ancho + 4.0), y, ancho, CHIP_H))
                      for i, m in enumerate(modos)]
        y += CHIP_H + 6.0
        if con_final:
            g["final_titulo"] = QRectF(x0 + 10.0, y, ancho_panel - 20.0, 16.0)
            y += 16.0
            n = len(fins)
            ancho = (ancho_panel - 12.0 - 4.0 * (n - 1)) / n
            g["finales"] = [(f, QRectF(x0 + 6.0 + i * (ancho + 4.0), y, ancho, CHIP_H))
                            for i, f in enumerate(fins)]
        return g

    # -- el selector: ratón --
    def evento(self, obj, ev) -> bool:
        """Filtro del visor: la barra (cursor o fija), el lazo y la pieza."""
        if not _interruptor.ENCENDIDA:
            return False
        t = ev.type()
        vp = self.app.viewport
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                 QEvent.Type.MouseButtonDblClick) and time.monotonic() < self._tragar_hasta:
            # El clic que cerró un desplegable (capas, navegador): no es del
            # dibujo. Se descarta hasta que se suelta el botón.
            if t == QEvent.Type.MouseButtonRelease:
                self._tragar_hasta = 0.0
            return True
        if not self._pasar_clic and self._evento_espera(vp, t, ev):
            return True
        if self._evento_derecho(vp, t, ev):
            return True
        if t == QEvent.Type.ShortcutOverride:
            # Qt lanza los atajos (R = rectángulo…) antes de que la tecla
            # llegue al visor: aceptar aquí la reclama para la ventanita de
            # medidas (unidades) o para el buscador.
            if self._tecla_propia(vp, ev):
                ev.accept()
                return True
            return False
        if t == QEvent.Type.KeyPress:
            texto = ev.text()
            if self.medidas is not None and self.medidas.isVisible():
                # Teclas que llegan al visor mientras la ventanita aún toma
                # el teclado (se teclea deprisa): son de la ventanita.
                if self.medidas.recibir_tecla(ev):
                    return True
                return False
            if self._letra_para_buscar(vp, ev):
                QTimer.singleShot(0, lambda: self._buscar(vp, texto))
                return True
            # Un número con una herramienta de la barra de dibujo en marcha: la ventanita
            # de medidas, con un renglón por medida (en vez del cuadro nativo).
            if (texto and (texto.isdigit() or texto in ",.-")
                    and not (ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier))
                    and self.medidas is not None):
                plan = self._campos(vp, tecleando=True)
                if plan is not None:
                    titulo, campos, aplicar = plan
                    self.medidas.abrir(titulo, campos, texto, aplicar)
                    return True
            return False
        if t == QEvent.Type.MouseButtonRelease:
            # Tras cada clic (un punto nuevo), la ventanita de la medida que
            # toca ahora, sin esperar a mover el ratón; y el repaso, que ve
            # al momento si la orden acabó (la barra se duerme sin esperar).
            QTimer.singleShot(0, lambda: self._sincronizar_medidas(vp))
            QTimer.singleShot(0, self._sincronizar)
        if (t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.LeftButton
                and self._tras_encuadre is not None):
            QTimer.singleShot(0, self._salir_encuadre)    # fin del encuadre
            return False
        if t == QEvent.Type.MouseButtonDblClick and ev.button() == Qt.LeftButton:
            if self._seguir_orden(vp):
                antes = self._pila_al_pulsar
                self.tragar_clic()
                QTimer.singleShot(0, lambda: self._cancelar_seguida(vp, antes))
                return True
            # Doble clic rápido: con una orden a medias, la cancela (como
            # Esc); con la barra a la vista y nada en marcha, cierra la barra.
            a_la_vista, a_medias = self._antes_clic
            if a_medias:
                self.tragar_clic()
                QTimer.singleShot(0, lambda: self._cancelar_y_deshacer(vp))
                return True
            vacio = getattr(vp.active_tool, "_rosco_lt_vacio", None)
            if vacio is not None and vacio.doble():
                # En el vacío con Seleccionar (haya o no selección): repite la
                # última orden, aunque se vea la barra de selección.
                return True
            if _seleccion.opcion("doble_cierra") and a_la_vista:
                self.tragar_clic()
                QTimer.singleShot(0, lambda: self._cerrar_doble(vp))
                return True
            if self.dormida and self._cancelable(vp):
                # Una orden repetida va sin la barra (dormida): el doble clic
                # también la cancela y deja Seleccionar. El primer clic ya
                # puede haber puesto un punto: de ahí las dos veces.
                self.tragar_clic()
                QTimer.singleShot(0, lambda: self._cancelar_repetida(vp))
                return True
        if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.LeftButton:
            tool = vp.active_tool
            if self._cancelable(vp):
                self._clics_orden += 1       # el paso de la línea de órdenes
            self._elegir_bajo_cursor(vp, ev)
            self._antes_clic = (self._en_juego(vp) or self.win.isVisible(),
                                self._en_marcha(vp))
            try:
                self._pila_al_pulsar = len(vp.history.undo_stack)
            except Exception:  # noqa: BLE001
                self._pila_al_pulsar = None
            if self._submenu_centrado() and self.panel == "seleccionar":
                # Seleccionar no «termina»: el clic en el modelo cierra su
                # submenú y vuelve el anillo.
                self.panel = None
                QTimer.singleShot(0, self._sincronizar)
            if self._es_base(tool) and not self.ocupada(tool):
                if tool.clave in CONSTRUYEN and tool is not self.guia:
                    self._recordar_antes(vp)       # para agrupar lo nuevo
                if (tool is self.bases["seleccionar"]
                        and self.modo["seleccionar"] == "lazo"):
                    self._lazo = [QPointF(ev.position())]
                    self._lazo_mods = ev.modifiers()
            return False
        if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.LeftButton:
            if self._lazo is not None:
                puntos, self._lazo = self._lazo, None
                self._cerrar_lazo(vp, puntos)
            return False
        if t == QEvent.Type.MouseMove:
            p = QPointF(ev.position())
            self.cursor_px = p
            self._sincronizar_medidas(vp)    # la ventanita sigue al cursor
            if self.cancelar is not None:
                self.cancelar.seguir(vp, p)  # y el botoncito de cancelar
            if self._lazo is not None:
                if ev.buttons() & Qt.LeftButton:
                    ultimo = self._lazo[-1]
                    if math.hypot(p.x() - ultimo.x(), p.y() - ultimo.y()) >= 3.0:
                        self._lazo.append(p)
                        vp.update()
                else:
                    self._lazo = None
            if not self._en_juego(vp):
                if self._cursor_puesto or self.win.isVisible():
                    self._sincronizar()
                return False
            if self.fijo:
                self._gesto_diana(p)         # temas A y B: la diana al centro
                self._gesto_historial(p)     # … y el historial por el ojo amarillo
            self._llevar_rosco(p)            # el rosco acompaña al ratón
            if (self.fijo and not self.anclada and not self._submenu_centrado()
                    and not self._zona_quieta(p)):
                self._soltar()               # sale de la barra: vuelve a ser cursor
            if not self.fijo:
                self._reposo.start()         # si se para, la barra se fija
            self._bajo = None                # sobre el visor, no sobre un botón
            self._sincronizar()
        elif t == QEvent.Type.Leave:
            self._reposo.stop()
            QTimer.singleShot(0, self._sincronizar)   # fuera del visor: la barra se va
        return False                         # el visor sigue viendo el evento

    @staticmethod
    def _sin_modificador(ev) -> bool:
        return not (ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier
                                      | Qt.MetaModifier))

    def _letra_para_buscar(self, vp, ev) -> bool:
        """Una letra con la barra fija (ratón parado sobre ella): el buscador
        de órdenes. Con el ratón en marcha, las letras siguen siendo los
        atajos de IngeTrazo."""
        texto = ev.text()
        if texto.lower() == "h" and vp.active_tool is getattr(self, "simetria", None):
            return False                     # H: el editor de hotspots de la Simetría
        return bool(texto and texto.isalpha() and self._sin_modificador(ev)
                    and self._arco_activo(vp) and not self._buffer(vp))

    def _tecla_propia(self, vp, ev) -> bool:
        """La tecla es de la barra de dibujo (no debe disparar un atajo de IngeTrazo)."""
        # Tecleando o dictando una medida: las letras son de la casilla.
        if (self.medidas is not None and self.medidas.isVisible()
                and (self.medidas.hay_texto() or self.medidas.dictando)
                and ev.text().isalpha() and self._sin_modificador(ev)):
            return True
        return self._letra_para_buscar(vp, ev)

    def raton_movido(self, p: QPointF) -> None:
        """Sobre la ventanita fija (el visor no recibe estos movimientos)."""
        self.cursor_px = QPointF(p)
        if not self._en_juego(self.app.viewport):
            return
        if not self.anclada and not self._submenu_centrado() and not self._zona_quieta(p):
            self._soltar()
            self._sincronizar()
            return
        if self._llevar_rosco(p):
            self._sincronizar()
            return
        self._gesto_diana(p)                 # temas A y B: la diana al centro
        self._gesto_historial(p)             # … y el historial por el ojo amarillo
        self._anima_raton(p)
        self._bajo = (self._chincheta_en(p) or ("menus" if self._menus_sel_en(p) else None)
                      or self._icono_en(p) or self._diana_en(p) or self._chico_en(p)
                      or self._ojo_orden_en(p)
                      or ("capa" if self._capa_en(p) else None)
                      or ("nav" if self._nav_en(p) else None)
                      or ("propiedades" if self._props_en(p) else None))
        self._sincronizar()

    def raton_clic(self, p: QPointF) -> None:
        self.clic_en_selector(self.app.viewport, p)

    # -- el rosco en espera: pulsar en vacío (el hueco del centro, fuera del anillo) --
    # -- el botón derecho --
    def _evento_derecho(self, vp, t, ev) -> bool:
        """Ver el comentario de ``CON_ASPA``. Un clic derecho se retiene lo que
        dura un doble clic, para saber si viene otro. True = se queda aquí."""
        if t == QEvent.Type.ContextMenu:
            if self._tragar_menu:
                self._tragar_menu = False
                return True
            return False
        if t not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
                     QEvent.Type.MouseButtonRelease) or ev.button() != Qt.RightButton:
            return False
        if t == QEvent.Type.MouseButtonRelease:
            return self._tragar_menu         # la pulsación fue nuestra: el visor no la ve
        if ev.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier):
            return False
        tool = vp.active_tool
        con_orden = self._cancelable(vp) and tool is not self.espera
        if not con_orden and not self._derecho_en_vacio(vp, ev):
            return False                     # sobre un objeto: el menú de IngeTrazo
        if con_orden and self._editando(vp) and not self._derecho_en_vacio(vp, ev):
            # Orden de editar, encima de un objeto: termina y deja pasar el clic
            # para que salga el menú de IngeTrazo de ese objeto.
            if self._reloj_derecho is not None and self._reloj_derecho.isActive():
                self._reloj_derecho.stop()
                self._derecho = None
            if self._en_marcha(vp):
                self._cancelar(vp)
            if self._cancelable(vp):
                self._terminar_orden(vp)
            self._tragar_menu = False
            return False
        self._tragar_menu = True
        if self._reloj_derecho is None:
            self._reloj_derecho = QTimer(self.app.window)
            self._reloj_derecho.setSingleShot(True)
            self._reloj_derecho.timeout.connect(self._derecho_solo)
        if self._reloj_derecho.isActive():   # el segundo clic: doble clic derecho
            self._reloj_derecho.stop()
            que, self._derecho = self._derecho, None
            QTimer.singleShot(0, lambda: self._derecho_doble(vp, que))
            return True
        # Paso a paso hacia atrás: con una orden, termina y abre su subrosco;
        # en el subrosco (o la rueda), al rosco principal; en el rosco
        # principal, Seleccionar y el rosco se esconde. Sin orden y sin rosco,
        # el menú de IngeTrazo (pasado el tiempo del doble, que deshace).
        if con_orden and getattr(self, "_tras_seccion", False):
            self._derecho = "seccion"        # desplazando el plano: otro plano
        elif con_orden:
            self._derecho = "atras" if self._recien_subrosco(vp) else "orden"
        elif self._rosco_lt_a_la_vista(vp):
            self._derecho = "atras" if self.panel is not None else "seleccionar"
        else:
            self._derecho = "menu"
        self._derecho_pos = QPoint(ev.position().toPoint())
        self._reloj_derecho.start(QApplication.doubleClickInterval())
        return True

    def _rosco_lt_a_la_vista(self, vp) -> bool:
        """El rosco se ve: fijo en su ventanita o siendo el cursor."""
        return self._en_juego(vp) and self.win is not None and (self.win.isVisible()
                                                                or self._cursor_puesto)

    def _derecho_en_vacio(self, vp, ev) -> bool:
        """Sin orden: el clic derecho es nuestro solo en el vacío (con el rosco
        llamado sin orden, en cualquier sitio: lo cierra). Sobre un objeto,
        también con el anillo de selección, es el menú de IngeTrazo."""
        if vp.active_tool is self.espera and self._rosco_lt_a_la_vista(vp):
            return True
        sel = self._select_nativo()
        if sel is None or not callable(getattr(sel, "_pick", None)):
            return False
        try:
            p = ev.position()
            return sel._pick(vp, p.x(), p.y()) is None
        except Exception:  # noqa: BLE001
            return False

    def _derecho_solo(self) -> None:
        """Pasó el tiempo del doble clic: era un clic derecho solo."""
        que, self._derecho = self._derecho, None
        vp = self.app.viewport
        if que == "orden":
            if self._cancelable(vp):
                seguir = self._seguir_orden(vp)
                clave = self._clave_de_orden(vp)
                self._cancelar(vp)           # como Esc: termina aceptando lo hecho
                if seguir and self._cancelable(vp):
                    # La orden que sigue no se queda: termina y vuelve Seleccionar.
                    self._terminar_orden(vp)
                    vp.flash_status(_tr("Orden terminada: vuelve Seleccionar."), 2500)
                if not self._cancelable(vp):
                    self.activar()           # y sale el rosco, en el cursor…
                    if clave is not None:    # …con el submenú desde el que se eligió
                        self._pulsar(vp, clave)
                        self._marcar_subrosco(vp, clave)
        elif que == "menu":
            self._menu_ingetrazo(vp)
        elif que == "atras":
            self._subrosco_derecho = None
            if self.panel in PANELES_OJO or self.panel == "vistas":
                if self.panel == "vistas":
                    self._salir_de_rueda()
                self.panel = None
                self._sincronizar()
            else:
                self._volver_al_anillo(vp)   # del subrosco al rosco principal
        elif que == "seleccionar":
            self._derecho_a_seleccionar(vp)
        elif que == "seccion":
            self._repetir_seccion(vp)

    def _marcar_subrosco(self, vp, clave) -> None:
        """Se abrió el subrosco con el clic derecho: si el siguiente llega sin
        haber hecho nada con la orden, va al rosco principal."""
        try:
            n = len(vp.history.undo_stack)
        except Exception:  # noqa: BLE001
            n = None
        self._subrosco_derecho = (clave, n)

    def _recien_subrosco(self, vp) -> bool:
        marca = getattr(self, "_subrosco_derecho", None)
        if marca is None:
            return False
        clave, n = marca
        try:
            ahora = len(vp.history.undo_stack)
        except Exception:  # noqa: BLE001
            ahora = None
        if self.panel != clave or ahora != n or self._en_marcha(vp):
            self._subrosco_derecho = None    # ya se usó la orden: vuelve a terminarla
            return False
        return True

    def _derecho_a_seleccionar(self, vp) -> None:
        """Desde el rosco principal: Seleccionar y el rosco se esconde hasta
        que se le vuelva a llamar."""
        self._subrosco_derecho = None
        if self._cancelable(vp) and self._en_marcha(vp):
            self._cancelar(vp)
        self._dormir(vp)
        vp.flash_status(_tr("Seleccionar (el rosco se ha escondido)."), 2500)

    def _clave_de_orden(self, vp):
        """El botón del rosco con submenú desde el que se eligió la orden
        activa (para volver a abrirlo al terminarla), o None."""
        tool = vp.active_tool
        if tool is self.push or self._es_base(tool):
            return self.base if self.base in MODOS else None
        if tool is getattr(self, "simetria", None):
            return "flip"
        if self._pintando(vp):
            return "pintar" if "pintar" in MODOS else None
        barra = self._barra_modificar()
        if barra is None:
            return None
        try:
            clave = barra._clave_activa(vp)
        except Exception:  # noqa: BLE001
            return None
        if clave == "pushpull":
            return "empujar"
        from ._arco import MODOS as MODOS_SEMI
        boton = barra._boton_de(clave) if clave else None
        return boton if boton in MODOS_SEMI else None

    def _menu_ingetrazo(self, vp) -> None:
        """El menú contextual de IngeTrazo donde se hizo el clic derecho."""
        pos = getattr(self, "_derecho_pos", None) or vp.mapFromGlobal(QCursor.pos())
        self._tragar_menu = False
        try:
            from PySide6.QtGui import QContextMenuEvent
            QApplication.sendEvent(vp, QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                                                         pos, vp.mapToGlobal(pos)))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo abrir el menú de IngeTrazo")

    def raton_derecho(self, p: QPointF) -> None:
        """Clic derecho sobre el rosco: un paso atrás. En un submenú o la rueda,
        vuelve al rosco principal; en el rosco principal, Seleccionar y el
        rosco se esconde."""
        vp = self.app.viewport
        self._subrosco_derecho = None
        if self.panel is not None:
            if self.panel in PANELES_OJO or self.panel == "vistas":
                if self.panel == "vistas":
                    self._salir_de_rueda()
                self.panel = None
                self._sincronizar()
            else:
                QTimer.singleShot(0, lambda: self._volver_al_anillo(vp))
            return
        QTimer.singleShot(0, lambda: self._derecho_a_seleccionar(vp))

    def _en_centro(self, p) -> bool:
        """``p`` cae en el hueco del centro del anillo (sin botón ni diana)."""
        if self.ancla is None or p is None or self._sin_arcos():
            return False
        if (self._icono_en(p) is not None or self._chico_en(p) is not None
                or self._diana_en(p) is not None):
            return False
        bandas = self._bandas()
        if not bandas:
            return False
        r = min(b[1] for b in bandas)
        return math.hypot(p.x() - self.ancla.x(), p.y() - self.ancla.y()) < r

    def raton_doble(self, p: QPointF) -> bool:
        """Doble clic en el centro del rosco: repite la última orden."""
        if self._en_centro(p):
            QTimer.singleShot(0, self.repetir_ultima)
            return True
        return False

    def _derecho_doble(self, vp, que) -> None:
        if que == "orden":
            self._atras_paso(vp)
        elif que in ("rosco", "menu", "atras", "seleccionar"):
            self.diana.usar(vp, "deshacer")

    def _atras_paso(self, vp) -> None:
        """Doble clic derecho con una orden: lo que cuelga del ratón se suelta
        y, si la orden ya había creado algo, se deshace lo último; la orden
        sigue activa para continuar."""
        if not self._cancelable(vp):
            return
        tool = vp.active_tool
        antes = self._pila_al_empezar
        if self._seguir_orden(vp) and self._pila_orden0 is not None:
            antes = self._pila_orden0        # orden que sigue: desde su primer uso
        self._obra = False                   # que no se duerma: la orden sigue
        if self._en_marcha(vp):
            fn = getattr(tool, "on_cancel", None)
            if callable(fn):
                self._cancelando = True
                try:
                    fn(vp)
                except Exception:  # noqa: BLE001
                    log.exception("la herramienta no pudo soltar el punto")
                finally:
                    self._cancelando = False
            self._foto_tool0 = {id(tool): _foto_tool(tool)}
        try:
            ahora = len(vp.history.undo_stack)
        except Exception:  # noqa: BLE001
            ahora = None
        if antes is not None and ahora is not None and ahora > antes:
            self.diana.usar(vp, "deshacer")
            vp.flash_status(_tr("Un paso atrás: deshecho lo último; la orden sigue."), 3000)
        else:
            vp.flash_status(_tr("Un paso atrás: la orden sigue desde el principio."), 3000)
        self._clics_orden = max(0, self._clics_orden - 1)
        if vp.active_tool is not tool:
            try:
                vp.set_active_tool(tool)     # deshacer no cambia de orden
            except Exception:  # noqa: BLE001
                log.exception("no se pudo seguir con la orden")
        vp.update()
        self._sincronizar()
        self._obra = False
        self._pila_al_empezar = antes        # la orden sigue siendo la misma

    def _evento_espera(self, vp, t, ev) -> bool:
        """Con el rosco llamado y sin orden, IngeTrazo cierra el rosco al pulsar
        en vacío. Aquí se retiene esa pulsación hasta saber qué es: un clic
        rápido lo cierra como siempre; mantener pulsado o arrastrar es el
        interruptor (se ve el modelo y, al soltar, vuelve en el cursor).
        True = el evento se queda aquí."""
        from ._flotante import ARRASTRE_PX, PULSACION_MS
        if self._pulso_espera is None:
            if not (t == QEvent.Type.MouseButtonPress and ev.button() == Qt.LeftButton
                    and vp.active_tool is self.espera and self.fijo and not self.anclada
                    and self.win.isVisible() and _seleccion.opcion("pulsacion_ver")):
                return False
            self._pulso_espera = (QPointF(ev.position()), QPointF(ev.globalPosition()), ev.modifiers())
            self._pulso_largo = False
            if self._reloj_espera is None:
                self._reloj_espera = QTimer(self.app.window)
                self._reloj_espera.setSingleShot(True)
                self._reloj_espera.timeout.connect(self._espera_larga)
            self._reloj_espera.start(PULSACION_MS)
            return True
        if t == QEvent.Type.MouseMove:
            p = QPointF(ev.position())
            self.cursor_px = p
            o = self._pulso_espera[0]
            if not self._pulso_largo and math.hypot(p.x() - o.x(), p.y() - o.y()) > ARRASTRE_PX:
                self._espera_larga()         # arrastrar también es «ver el modelo»
            return True
        if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.LeftButton:
            self._fin_pulso_espera(QPointF(ev.position()))
            return True
        return t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)

    def _espera_larga(self) -> None:
        if self._pulso_espera is None:
            return
        self._pulso_largo = True
        self._reloj_espera.stop()
        self.win.ver_modelo(True)

    def _fin_pulso_espera(self, p: QPointF) -> None:
        pulso, self._pulso_espera = self._pulso_espera, None
        largo, self._pulso_largo = self._pulso_largo, False
        if self._reloj_espera is not None:
            self._reloj_espera.stop()
        if largo:
            self.win.ver_modelo(False)
            self.pulsacion_soltada(p)
        elif pulso is not None:
            QTimer.singleShot(0, lambda: self._repetir_clic(pulso))

    def _repetir_clic(self, pulso) -> None:
        """El clic rápido retenido: cierra el rosco y le llega a Seleccionar,
        que selecciona lo que haya debajo; ese clic no cuenta como «clic en el
        vacío» (volvería a abrir el rosco)."""
        from PySide6.QtGui import QMouseEvent
        vp = self.app.viewport
        pos, glob, teclas = pulso
        self.cerrar_barra_dibujo()
        sel = vp.active_tool
        original = getattr(sel, "_clic_original", None)
        propio = sel.__dict__.get("on_click") if hasattr(sel, "__dict__") else None
        if original is not None:
            sel.on_click = original
        self._pasar_clic = True
        try:
            for tipo, botones in ((QEvent.Type.MouseButtonPress, Qt.LeftButton),
                                  (QEvent.Type.MouseButtonRelease, Qt.NoButton)):
                QApplication.sendEvent(vp, QMouseEvent(tipo, pos, glob, Qt.LeftButton, botones, teclas))
        finally:
            self._pasar_clic = False
            if original is not None:
                if propio is not None:
                    sel.on_click = propio
                else:
                    del sel.on_click

    def pulsacion_soltada(self, p: QPointF) -> None:
        """Se suelta la pulsación larga (la barra estaba transparente): vuelve
        a verse, centrada donde esté ahora el cursor. Con la chincheta se
        queda en su sitio."""
        vp = self.app.viewport
        self.cursor_px = QPointF(p)
        if self.anclada or not self._en_juego(vp):
            self._sincronizar()
            return
        self.fijo = True
        self.ancla = QPointF(p)
        # Cerca del borde del visor, el anillo entra lo justo para verse entero.
        try:
            dx, dy = self._meter_dentro(self.ancla, self._mascara_path(self.ancla).boundingRect())
            self.ancla = QPointF(self.ancla.x() + dx, self.ancla.y() + dy)
        except Exception:  # noqa: BLE001 — se queda donde el ratón
            log.exception("no se pudo meter la barra en el visor")
        self._bajo = None
        self._estado_pintado = None
        self._sincronizar()
        self.win.update()

    def raton_fuera(self) -> None:
        self._anima_raton(None)              # la pantallita vuelve a su bucle
        if self._bajo is not None:
            self._bajo = None
            self._sincronizar()

    def clic_en_selector(self, viewport, screen) -> bool:
        """Clic en un botón: elige la herramienta y abre su submenú (la barra
        sigue fija para elegir las opciones antes del primer punto)."""
        if not self._arco_activo(viewport):
            return False
        p = QPointF(screen)
        pin = self._chincheta_en(p)
        if pin is not None:
            QTimer.singleShot(0, lambda: self._pulsar_chincheta(viewport, pin))
            return True
        if self._vistas_en(p):
            # La diana plegada: se abre o se cierra debajo del anillo.
            self.panel = None if self.panel == "vistas" else "vistas"
            self._sincronizar()
            return True
        if self._menus_sel_en(p):
            q = self._centro_menus_sel(self.ancla)
            QTimer.singleShot(0, lambda: self._abrir_menus(viewport, q))
            return True
        if self._capa_icono_en(p):
            QTimer.singleShot(0, lambda: self._menu_aplicar_capa(viewport))
            return True
        if self._capa_en(p):
            QTimer.singleShot(0, lambda: self._menu_capas(viewport))
            return True
        if self._nav_en(p):
            QTimer.singleShot(0, lambda: self._abrir_navegador(viewport))
            return True
        if self._props_en(p):
            QTimer.singleShot(0, lambda: _seleccion.abrir_info(self))
            return True
        ojo = self._ojo_orden_en(p)
        if ojo is not None:                  # un ojo con una orden puesta
            return self._pulsar(viewport, ojo)
        chico = self._chico_en(p)
        if chico is not None:
            return self._pulsar(viewport, chico)
        parte = self._diana_en(p)
        if parte is not None:
            if parte not in _diana.PROPIAS and parte not in ("volver", "cerrar_rueda"):
                return self._pulsar(viewport, parte)     # lo puesto en la rueda
            QTimer.singleShot(0, lambda: self._usar_diana(viewport, parte))
            return True
        clave = self._icono_en(p)
        if clave is not None:
            return self._pulsar(viewport, clave)
        g = self._panel()
        if g is not None and g["marco"].contains(p):
            if "volver" in g and g["volver"].adjusted(-3, -3, 3, 3).contains(p):
                QTimer.singleShot(0, lambda: self._volver_al_anillo(viewport))
            else:
                self._accion_panel(viewport, g, p)
            self._sincronizar()
            return True
        return False

    def _volver_al_anillo(self, viewport) -> None:
        """La flecha ‹ del submenú: al rosco principal. Si había una orden, se
        cancela y queda el lápiz, como en Seleccionar. Desde el subrosco de
        la Cámara, a la rueda."""
        if self.panel == "camara":
            self.panel = "vistas"
            self._sincronizar()
            return
        self.panel = None
        if self._cancelable(viewport):
            if self._en_marcha(viewport):
                self._cancelar(viewport)     # lo que tuviera a medias
            self.base = None
            self.dormida = False
            self.arco_visible = True
            self._obra = False
            if viewport.scene.selection:
                self._a_seleccionar(viewport)   # el anillo de selección
            else:
                self._activar_base(viewport)    # sin orden: el lápiz gris
            viewport.setFocus()
        self._sincronizar()

    def _activar_base(self, viewport) -> None:
        if viewport.active_tool is not self.herramienta:
            self.arco_visible = True
            viewport.set_active_tool(self.herramienta)
            viewport.setFocus()              # lo tecleado (medidas) va al visor
        viewport.flash_status(_tr(self._mensaje_base()), 6000)
        self._sincronizar()

    def _accion_sel(self, viewport, clave, modo=None) -> None:
        """Una acción de la barra de selección (o una opción de Agrupar)."""
        habia = bool(viewport.scene.selection)
        try:
            if clave == "agrupar":
                _seleccion.agrupar(self.app, viewport, modo)
            else:
                _seleccion.accion(self.app, viewport, clave)
        except Exception:  # noqa: BLE001
            log.exception("fallo en la barra de selección (%s %s)", clave, modo)
            viewport.flash_status(_tr("Rosco LT: no se pudo {0}.", clave), 4000)
        else:
            if habia:
                self._orden_hecha(viewport)  # borrar, copiar, crear…: se duerme
        self._sincronizar()

    def _accion_panel(self, viewport, g, p) -> None:
        clave = self.panel
        if clave == "camara":
            for k, r in g["chips"]:
                if r.contains(p):
                    self.panel = None
                    QTimer.singleShot(0, lambda k=k: self.diana._herramienta(
                        viewport, _diana.CAMARA_HERR[k], _diana.NOMBRES[k]))
                    return
            return
        if clave == "ayuda":
            for i, r in g.get("pestanas", ()):
                if r.contains(p) and i != self._ayuda_pagina:
                    self._ayuda_pagina = i
                    self._ayuda_scroll = 0.0
                    self._sincronizar()
            return                           # lo demás, solo para leer
        if clave == "historial":
            for i, r in g.get("entradas", ()):
                if r.contains(p):
                    QTimer.singleShot(0, lambda i=i: self._usar_historial(i))
                    return
            return
        if clave == "flip":
            simetria = getattr(self, "simetria", None)
            for k, r in list(g["chips"]) + list(g.get("finales", ())):
                if r.contains(p) and simetria is not None:
                    QTimer.singleShot(0, lambda k=k: (simetria.elegir(viewport, k), self._sincronizar()))
                    return
            return
        if clave == "align":
            ctl = self._alinear()
            for k, r in g["chips"]:
                if r.contains(p) and ctl is not None:
                    if k == "escalar" or (k == "copiar") != bool(ctl.copiar):
                        ctl.alternar("escalar" if k == "escalar" else "copiar", viewport)
                        self._sincronizar()
                    return
            return
        if clave in _seleccion.SEMI:
            barra = self._barra_modificar()
            for modo, r in g["chips"]:
                if r.contains(p) and barra is not None:
                    def elegir(modo=modo):
                        barra.elegir_modo(clave, modo)
                        if modo == "alinear" and viewport.active_tool is getattr(self._alinear(), "tool", None):
                            self.panel = "align"     # Alinear, con su propio submenú
                        self._sincronizar()
                    QTimer.singleShot(0, elegir)
                    return
            return
        if clave == "agrupar":
            for modo, r in g["chips"]:
                if r.contains(p):
                    self.panel = None
                    QTimer.singleShot(0, lambda: self._accion_sel(viewport, "agrupar", modo))
                    return
            return
        if "menos" in g and g["menos"].contains(p) or "mas" in g and g["mas"].contains(p):
            lo, hi = LIMITES_LADOS[clave]
            tool = self.bases[clave]
            paso = -1 if g["menos"].contains(p) else 1
            tool.sides = min(hi, max(lo, int(tool.sides) + paso))
            viewport.flash_status(_tr("{0}: {1}", ETIQUETA_LADOS[clave], tool.sides), 2000)
            return
        for fin, r in g.get("finales", ()):
            if r.contains(p):
                self._poner_final(viewport, fin)
                return
        for modo, r in g["chips"]:
            if not r.contains(p):
                continue
            self.modo[clave] = modo
            if clave == "pintar":
                QTimer.singleShot(0, lambda: self._pintar(viewport, modo))
                return
            if clave == "rect" and modo in ("esquina", "centro"):
                self.bases["rect"]._set_from_center(viewport, modo == "centro")
            if clave == self.base:
                # Cambiar de modo puede cambiar de herramienta (rect. girado,
                # guía): se activa diferido, como al elegir un botón.
                QTimer.singleShot(0, lambda: self._activar_base(viewport))
            return

    # -- el lazo de selección --
    def _cerrar_lazo(self, viewport, puntos) -> None:
        largo = sum(math.hypot(b.x() - a.x(), b.y() - a.y())
                    for a, b in zip(puntos, puntos[1:]))
        if len(puntos) < 3 or largo < 12.0:
            viewport.update()
            return                           # fue un clic: ya lo hizo Seleccionar
        try:
            self._seleccionar_lazo(viewport, [(q.x(), q.y()) for q in puntos])
        except Exception:  # noqa: BLE001
            log.exception("fallo en la selección por lazo")
        viewport.update()

    def _seleccionar_lazo(self, viewport, poli) -> None:
        """Como la ventana (todo dentro), pero con el contorno del lazo."""
        scene = viewport.scene
        w2p = viewport._world_to_pixel

        def dentro(q):
            return q is not None and _en_poligono(q[0], q[1], poli)

        elegidos = []
        for e in list(scene.edges):
            if scene.entity_selectable(e) and dentro(w2p(e.a)) and dentro(w2p(e.b)):
                elegidos.append(e)
        for f in list(scene.faces):
            if scene.entity_selectable(f) and all(dentro(w2p(v)) for v in f.vertices):
                elegidos.append(f)
        abierto = scene.edit_group
        grupos = (list(getattr(abierto, "children", None) or []) if abierto is not None
                  else list(scene.groups))
        obb = getattr(viewport, "_group_obb", None)
        if obb is not None:
            from core.group import oriented_box_corners
            for g in grupos:
                if not scene.entity_selectable(g):
                    continue
                try:
                    esquinas = oriented_box_corners(*obb(g))
                except Exception:  # noqa: BLE001
                    continue
                if esquinas and all(dentro(w2p(q)) for q in esquinas):
                    elegidos.append(g)
        scene.select(elegidos, mode=_seleccion.modo_lazo(self._lazo_mods))
        viewport.flash_status(_tr("Lazo: {0} elemento(s).", len(elegidos)), 2500)

    # -- enlace con la barra de modificar (sus herramientas van en la mitad de abajo) --
    def _barra_modificar(self):
        """La barra de modificar (``window._rosco_lt_barra_modificar``), si está."""
        barras = getattr(self.app.window, "_rosco_lt_barra_modificar", None) or {}
        return next((b for b in barras.values()
                     if callable(getattr(b, "activar", None))), None)

    # -- cancelar la orden en marcha (el botoncito junto al cursor) --
    def _en_marcha(self, viewport) -> bool:
        """Una orden a medias: una base de la barra de dibujo con su primer punto puesto,
        Empujar/Tirar arrastrando o cualquier otra herramienta con su punto
        base, su tirador o su arrastre en curso (nunca Seleccionar)."""
        tool = viewport.active_tool
        if tool is None or tool is self._select_nativo() or tool is self.bases["seleccionar"]:
            return False
        if tool is self.push:
            return bool(self.push.dragging)
        if self._es_base(tool):
            return self.ocupada(tool)
        if tool is getattr(self, "simetria", None):
            return tool.a is not None            # el plano y el fantasma cambian solos con el ratón
        if hasattr(tool, "start_point") or hasattr(tool, "_grip"):
            # Desplazar, Rotar, Escalar…: dicen claro si están a medias. Mirar lo
            # demás confundiría lo que cambia solo con pasar el ratón por un
            # objeto, y al salir de él se cerraría el submenú.
            return _con_senas(tool)
        return _con_senas(tool) or self._cambio_estado(tool)

    def _cancelable(self, viewport) -> bool:
        """El botoncito de cancelar va con cualquier orden elegida (de la
        barra o de IngeTrazo), desde que se pincha: nunca con Seleccionar ni
        con la espera (el rosco llamado sin orden: no hay nada que cancelar;
        se cierra con un clic en vacío o Esc)."""
        tool = viewport.active_tool
        return (tool is not None and tool is not self._select_nativo()
                and tool is not self.bases["seleccionar"] and tool is not self.espera)

    def _sobre_la_barra(self, p) -> bool:
        """El ratón está eligiendo en la barra fija (o en su submenú): el
        botoncito de cancelar no la tapa."""
        return (self.fijo and self.win is not None and self.win.isVisible()
                and p is not None and self._zona_quieta(p))

    def _cambio_estado(self, tool) -> bool:
        """Una nativa sin señas conocidas (Simetría…): está a medias si algún
        atributo que estaba vacío al activarla tiene ahora algo."""
        foto0 = self._foto_tool0.get(id(tool))
        if foto0 is None:
            return False
        ahora = _foto_tool(tool)
        return any(puesto and not foto0.get(nombre, False) for nombre, puesto in ahora.items())

    def _cerrar_doble(self, viewport) -> None:
        """El doble clic: si el primer clic empezó algo (un punto de una
        base), se deshace; y se cierra la barra."""
        if self._en_marcha(viewport):
            self._cancelar(viewport)
        self._pulsar_chincheta(viewport, "cerrar")

    def _cancelar_repetida(self, viewport) -> None:
        self._cancelar_y_deshacer(viewport)
        if self._cancelable(viewport):
            self._cancelar(viewport)

    def _cancelar_y_deshacer(self, viewport) -> None:
        """El doble clic con una orden en marcha: la cancela y, si la orden
        había llegado a crear algo (hay más en el historial que cuando
        empezó), deshace ese último paso (como Ctrl+Z)."""
        antes = self._pila_al_empezar
        self._cancelar(viewport)

        def deshacer_si_creo():
            try:
                ahora = len(viewport.history.undo_stack)
            except Exception:  # noqa: BLE001
                return
            if antes is not None and ahora > antes:
                self.diana.usar(viewport, "deshacer")
        QTimer.singleShot(0, deshacer_si_creo)

    def _terminar_orden(self, viewport) -> None:
        """Deja la orden y vuelve Seleccionar (con la barra dormida si se
        esconde tras cada orden)."""
        self._obra = False
        if _seleccion.opcion("esconder_tras"):
            self._dormir(viewport)
        else:
            self.panel = None
            self._a_seleccionar(viewport)
            self._sincronizar()

    def _elegir_bajo_cursor(self, vp, ev) -> None:
        """Rotar sin selección (al seguir tras un giro): el clic coge lo que
        haya bajo el cursor, como hacen Desplazar y Simetría."""
        if (self._semi_activa(vp) != "rotate" or vp.scene.selection
                or self._en_marcha(vp)):
            return
        x, y = ev.position().x(), ev.position().y()
        try:
            elegido = vp.pick_group(x, y)
            if elegido is None:
                elegido, _grupo = vp.pick_face_any(x, y)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo coger lo que hay bajo el cursor")
            return
        if elegido is not None:
            vp.scene.select([elegido], mode="replace")
            vp.notify_scene_changed()

    def _cancelar(self, viewport) -> None:
        """Como Esc: la herramienta activa deshace lo que tenga a medias. Con
        la orden elegida pero sin empezar, se deja y se vuelve a Seleccionar
        (como al terminar una orden)."""
        tool = viewport.active_tool
        if self.cancelar is not None:
            self.cancelar.esconder()
        if not self._en_marcha(viewport):
            self._terminar_orden(viewport)
            viewport.flash_status(_tr("Orden cancelada: vuelve Seleccionar."), 2500)
            return
        fn = getattr(tool, "on_cancel", None)
        if callable(fn):
            # El Esc de las herramientas de la barra de dibujo, sin nada en curso, apaga el
            # selector; aquí no: solo se cancela la orden.
            self._cancelando = True
            try:
                fn(viewport)
            except Exception:  # noqa: BLE001
                log.exception("la herramienta no pudo cancelar")
            finally:
                self._cancelando = False
        self._obra = False                   # cancelada: no cuenta como hecha
        # Tras cancelar, la herramienta vuelve a estar «recién activada».
        if tool is not None:
            self._foto_tool0 = {id(tool): _foto_tool(tool)}
        viewport.flash_status(_tr("Orden cancelada."), 2500)
        viewport.update()
        self._sincronizar()

    def alternar_arco(self, viewport) -> None:
        """Esc sin nada en curso: cierra el submenú si lo hay (el anillo
        vuelve); si no, oculta o vuelve a mostrar el selector."""
        if self._cancelando:
            return                           # el ✕ o el doble clic: solo cancelar
        if self.panel is not None or self.escondida:
            self.escondida = False
            self._soltar()
            self._sincronizar()
            return
        self.arco_visible = not self.arco_visible
        self._soltar()
        viewport.flash_status(_tr("Rosco LT: selector visible (Esc o clic derecho en vacío lo oculta)."
                              if self.arco_visible else
                              "Rosco LT: selector oculto (Esc o clic derecho en vacío lo muestra)."), 3000)
        self._sincronizar()

    # -- dibujo --
    def dibujar(self, viewport, painter) -> None:
        """Overlay del visor: el lazo y la ventanita de medidas. El selector
        va como cursor o en su ventana; aquí solo se programa un repaso."""
        if not _interruptor.ENCENDIDA:
            return
        if not self._pendiente:
            self._pendiente = True
            QTimer.singleShot(0, self._sincronizar)
        if self._lazo is not None and len(self._lazo) > 1:
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(ROJO, 1.4, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(214, 34, 34, 25)))
            painter.drawPolygon(QPolygonF(self._lazo))
        if self.medidas is not None and self.medidas.isVisible():
            return                           # la ventanita de medidas ya está
        tool = viewport.active_tool
        tecleado = self._buffer(viewport)
        if tool is self.push and self.push.dragging:
            titulo = ("Altura · tirar ↑" if self.push.extrusion >= 0.0
                      else "Altura · empujar ↓")
            valor = tecleado or fmt_len(abs(self.push.extrusion))
        elif self._es_base(tool):
            if getattr(tool, "start_point", None) is None or not tecleado:
                return
            titulo, valor = self._titulo_medida(tool), tecleado
        else:
            return
        if self.cursor_px is None:
            return
        pista = ("Enter = aplicar · Esc = borrar" if tecleado
                 else "Teclea la medida o haz clic")
        _ventanita(painter, viewport, self.cursor_px, titulo, valor, pista,
                   escribiendo=bool(tecleado))

    def _titulo_medida(self, tool) -> str:
        clave = tool.clave
        if tool is self.girado:
            return "Longitud del lado" if tool.base_point is None else "Fondo"
        if clave == "rect":
            return "Dimensiones (ancho;alto)"
        if clave in ("line", "linea"):
            return "Longitud"
        if self.modo.get(clave) not in (None, "centro"):
            return "Diámetro" if clave == "circle" else "Lado"
        return "Radio"

    def _texto_icono(self, clave) -> str:
        if clave in ("chincheta", "cerrar", "limpia"):
            return texto_chincheta(clave, self.anclada)
        if clave == "capa":
            return ("Pasar la selección a otra capa" if self._es_sel
                    else "Capa donde va lo que dibujas")
        if clave == "nav":
            return "Navegador: grupos y componentes del modelo"
        if clave in _seleccion.SEMI and self._barra_modificar() is None:
            return _tr("{0} (falta la barra de modificar)", _tr(NOMBRES[clave].split(':')[0]))
        if clave in NOMBRES_CHICOS:
            return NOMBRES_CHICOS[clave]
        if _huecos.externo(clave):
            return self._nombre_externo(clave)
        return NOMBRES.get(clave, clave)

    def _nombre_externo(self, clave) -> str:
        """El nombre de un comando del gestor de barras puesto en un hueco."""
        key = clave[len(_huecos.EXTERNO):]
        gestor = gestor_barras(self.app.window)
        try:
            if gestor is not None:
                return gestor.nombre(key) or key
        except Exception:  # noqa: BLE001
            log.exception("el gestor de barras no dio el nombre de %s", key)
        return key.split(":", 1)[-1]

    def _pintar_banda(self, painter, c, bajo=None, para_clic=False, completo=True) -> None:
        """El anillo centrado en ``c`` (también el del cursor): arriba
        dibujar, abajo modificar y, si ``completo``, la diana encima y los
        botoncitos (el cursor ligero lleva solo el anillo)."""
        vp = self.app.viewport
        T = self.tema
        _flotante.fijar_centro(painter, c, T.abajo_anillo)   # el degradado del tema N
        # La herramienta de la barra de dibujo se marca solo mientras es la activa.
        base = self.base if self._es_base(vp.active_tool) else None
        semi = self._semi_activa(vp)
        # Lo que se marca en cualquier banda: la herramienta activa (de la barra de dibujo,
        # Pintar o una de la barra de modificar) y el botón con el submenú abierto.
        encendidas = {k for k in (base, semi, self.panel) if k is not None}
        if self._pintando(vp):
            encendidas.add("pintar")
        sin_barra_modificar = set(_seleccion.SEMI) if self._barra_modificar() is None else set()
        # Con la rueda abierta o el submenú a la derecha (temas A y B) los arcos
        # se esconden.
        bandas = () if self._sin_arcos() else self._bandas()
        for claves, r_int, r_ext, a0, tam in bandas:
            dibujar_banda(painter, c, r_int, r_ext, claves, activa=encendidas & set(claves),
                          bajo=bajo, apagadas=sin_barra_modificar & set(claves), para_clic=para_clic,
                          a0=a0, barrido=T.barrido, tam=tam, relieve=T.relieve)
        # Los huecos de los lados: cada uno, un trozo de banda suelto.
        for _j, clave, r_int, r_ext, a0, b, tam in self._lados():
            dibujar_banda(painter, c, r_int, r_ext, (clave,), activa=encendidas & {clave},
                          bajo=bajo, para_clic=para_clic, a0=a0, barrido=b, tam=tam,
                          relieve=T.relieve)
        if not completo or self._sin_arcos():
            return
        # El buscador solo con la barra fija (es cuando se teclea en él); con
        # algo seleccionado, en su sitio va el extracto de propiedades.
        if not T.diana_plegada:
            self._pintar_diana(painter, self._diana_centro(c), bajo if bajo in DIANA else None,
                               para_clic, buscador=para_clic and not self._es_sel)
        self._pintar_chicos(painter, c, bajo, para_clic)

    def pintar(self, painter) -> None:
        """La barra fija, en coordenadas del visor (la ventanita traslada).
        Todo lo que no depende del ratón sale de una imagen guardada; encima
        va solo el tinte del botón bajo el ratón y su etiqueta."""
        c = self.ancla
        if c is None:
            return
        fondo = self._fondo_pixmap()
        if fondo is not None:
            painter.drawPixmap(QPointF(self.win.origen), fondo)
        else:
            self._pintar_fondo(painter, c)
        self._pintar_encima(painter, c, self._bajo)
        if self.panel == "ayuda" and self._ayuda_pagina == 0:
            self._pintar_anima(painter, c)

    def _estado_fondo(self) -> tuple:
        """Todo lo que cambia el dibujo de la barra fija, salvo dónde está y
        qué hay bajo el ratón."""
        vp = self.app.viewport
        return (_idioma.actual(), self._ayuda_pagina, self.tema.clave, self.escala, self._es_sel, self.anclada, self.diana.proyeccion_actual(),
                self.diana._en_vista(vp, "bottom") if self.tema.rueda else None,
                self._texto_capa(), self.pos_capa,
                self._texto_props() if self._es_sel else None, self.panel,
                self.base, self._es_base(vp.active_tool), self._pintando(vp),
                self._historial_v, self.aplicar_capa,
                tuple(sorted(self.modo.items())),
                self.pedir_nombre, int(getattr(self.bases["poly"], "sides", 0) or 0),
                int(getattr(self.bases["circle"], "sides", 0) or 0), self._estado_semi(vp),
                self._barra_modificar() is None, round(float(self.win.devicePixelRatioF()), 2),
                self.submenus_radiales, self._sitio_submenu(), self._estado_simetria())

    def _estado_simetria(self) -> tuple | None:
        """Lo que se marca en el submenú de la Simetría (si no, el dibujo
        guardado de la barra no se rehace al elegir)."""
        s = getattr(self, "simetria", None)
        ctl = self._alinear()
        alinear = (ctl.copiar, ctl.escalar) if ctl is not None else None
        if s is None:
            return alinear
        return (s.modo, s.eje, s.copia, s.editor, getattr(s, "copiando", False), alinear)

    def _sitio_submenu(self) -> tuple:
        """Lo que mueve el submenú (o la rueda) dentro de la ventanita: dónde
        estaba el ratón al abrirlo (cambia cuando el rosco lo acompaña), la
        distancia, el tamaño y lo que se aparta del borde del visor."""
        d = getattr(self, "_panel_raton", None) or QPointF(0.0, 0.0)
        sitio = (round(d.x(), 1), round(d.y(), 1), self.distancia_submenu, self.escala_rosco,
                 self.sitio_submenu)
        if self.panel is not None and self.ancla is not None:
            try:
                g = self._panel(ANCLA_LOCAL)
                if g is not None:
                    sitio += (round(g["marco"].x(), 1), round(g["marco"].y(), 1))
                if self._rueda_abierta():
                    q = self._diana_centro(ANCLA_LOCAL)
                    sitio += (round(q.x(), 1), round(q.y(), 1))
            except Exception:  # noqa: BLE001
                log.exception("no se pudo situar el submenú")
        return sitio

    def _fondo_pixmap(self):
        """La barra sin el ratón, pintada una vez en coordenadas de la
        ventanita (vale aunque la barra se mueva) y guardada hasta que
        cambie algo de ``_estado_fondo``."""
        clave = self._estado_fondo()
        if self._fondo is not None and self._fondo[0] == clave:
            return self._fondo[1]
        try:
            dpr = max(1.0, float(self.win.devicePixelRatioF()))
            pm = QPixmap(int(math.ceil(VENTANA_W * dpr)), int(math.ceil(VENTANA_H * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.Antialiasing)
                self._pintar_fondo(p, QPointF(self.win.ancla_local))
            finally:
                p.end()
        except Exception:  # noqa: BLE001 — se pinta directo
            log.exception("no se pudo guardar el dibujo de la barra")
            self._fondo = None
            return None
        self._fondo = (clave, pm)
        return pm

    def _pintar_fondo(self, painter, c) -> None:
        """La barra entera, como si no hubiera nada bajo el ratón."""
        T = self.tema
        _flotante.fijar_centro(painter, c, T.abajo_anillo)
        if self._rueda_abierta():
            self._dibujar_panel(painter, c)  # solo la rueda
            return
        if self._submenu_centrado():
            # El ojo azul y el submenú en el centro; con Seleccionar, Escalar
            # o Rotar, también las propiedades, la capa y el navegador.
            self._pintar_ojo(painter, self._centro_ojo(c),
                             OJOS[self._ojo_de("rueda") or "arriba"][2], T.relieve,
                             self._r_ojo_centrado())
            self._pintar_props(painter, c, False)
            self._dibujar_panel(painter, c)
            return
        self._pintar_banda(painter, c, None, para_clic=True)
        self._pintar_capa(painter, c, False)
        if not T.cajetines_plegados:
            self._pintar_nav(painter, c, False)
        if self._con_props():
            self._pintar_props(painter, c, False)
        if not T.rueda:
            dibujar_chincheta(painter, c.x(), self._y_chincheta(c), self.anclada, None,
                              self._chincheta_dxs(), segundo="limpia", relieve=T.relieve)
        if T.rueda:
            for cual, (_a, _donde, color) in OJOS.items():
                self._pintar_ojo(painter, self._centro_ojo(c, cual), color, T.relieve)
        else:
            dibujar_boton_redondo(painter, "cerrar", self._centro_cerrar(c), None,
                                  relieve=T.relieve)
        if T.rueda:
            pass
        elif T.diana_plegada:
            dibujar_boton_redondo(painter, "vistas", self._centro_vistas(c), None,
                                  marcado=self.panel == "vistas", relieve=T.relieve)
            self.diana._pintar_buscador(painter, self._cc_fila(c), None)
        elif self._es_sel:
            self._pintar_menus_sel(painter, c)
        self._dibujar_panel(painter, c)

    # -- los temas (maquetaciones del anillo) --
    def poner_tema(self, clave: str) -> None:
        """Cambia la maquetación de la barra; se recuerda entre sesiones."""
        self.tema = _temas.escalar(_temas.tema(clave), self.escala)
        _temas.guardar(self.tema.clave)
        self._rehacer_dibujo()
        self.app.viewport.flash_status(_tr("Rosco LT: tema «{0}».", self.tema.nombre), 3000)
        self._sincronizar()

    def poner_escala(self, factor: float) -> None:
        """El tamaño de la barra (Configuración ▸ Tamaño); se recuerda."""
        self.escala = max(_temas.ESCALA_MIN, min(_temas.ESCALA_MAX, float(factor)))
        self.tema = _temas.escalar(_temas.tema(self.tema.clave), self.escala)
        _temas.guardar_escala(self.escala)
        self._rehacer_dibujo()
        self._sincronizar()

    def poner_distancia_submenu(self, px: int) -> None:
        """La distancia del cursor al submenú (Opciones); se recuerda."""
        self.distancia_submenu = max(_seleccion.DISTANCIA_MIN,
                                     min(_seleccion.DISTANCIA_MAX, int(px)))
        _seleccion.poner_distancia_submenu(self.distancia_submenu)
        self._sincronizar()

    def poner_sitio_submenu(self, sitio: str) -> None:
        """Dónde sale el submenú: «derecha» del cursor o «centro» bajo él."""
        self.sitio_submenu = sitio if sitio in dict(_seleccion.SITIOS_SUBMENU) else "derecha"
        _seleccion.poner_sitio_submenu(self.sitio_submenu)
        self._sincronizar()

    def poner_escala_rosco(self, pct: int) -> None:
        """El tamaño del rosco de submenús (Opciones), en %; se recuerda."""
        self.escala_rosco = max(_seleccion.ESCALA_ROSCO_MIN,
                                min(_seleccion.ESCALA_ROSCO_MAX, int(pct)))
        _seleccion.poner_escala_rosco(self.escala_rosco)
        self._sincronizar()

    def _rehacer_dibujo(self) -> None:
        """Tras cambiar de tema o de tamaño: nada guardado vale."""
        self._fondo = None
        self._cursor = None
        if self.win is not None:
            self.win._mascara_clave = None
        self._soltar()

    def previsualizar(self, clave: str, escala: float = 0.5) -> QPixmap:
        """Una imagen de la barra fija con el tema ``clave`` (la vista previa
        del menú de temas): se pinta con ese tema puesto un momento, en
        coordenadas de la ventanita, recortada a lo que ocupa."""
        guardado = (self.tema, self.panel, self._bajo, self._fondo)
        self.tema, self.panel, self._bajo = _temas.tema(clave), None, None
        try:
            c = QPointF(self.win.ancla_local)
            caja = self._mascara_path(c).boundingRect().adjusted(-16.0, -16.0, 16.0, 16.0)
            dpr = max(1.0, float(self.win.devicePixelRatioF()))
            pm = QPixmap(int(math.ceil(caja.width() * escala * dpr)),
                         int(math.ceil(caja.height() * escala * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(QColor(250, 250, 248))
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.Antialiasing)
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.scale(escala, escala)
                p.translate(-caja.left(), -caja.top())
                self._pintar_fondo(p, c)
                _flecha(p, c)
            finally:
                p.end()
        finally:
            self.tema, self._bajo, self._fondo = guardado[0], guardado[2], guardado[3]
            self._panel_abierto = guardado[1]    # sin tocar dónde sale su submenú
        return pm

    def _pintar_encima(self, painter, c, bajo) -> None:
        """Lo que depende del ratón: el tinte de lo que tiene debajo y la
        etiqueta."""
        if bajo is None:
            return
        tinte = QColor(ROJO)
        tinte.setAlphaF(0.14)
        fuerte = QColor(ROJO)
        fuerte.setAlphaF(0.30)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        # Con la rueda abierta (o el submenú en el centro) el anillo no está:
        # lo de debajo es de la rueda aunque esa clave también esté en una banda.
        sin_arcos = self._sin_arcos()
        forma = None if sin_arcos else self._sector_de(c, bajo)
        circulo = None if forma is not None or sin_arcos else self._circulo_de(c, bajo)
        if forma is not None:
            painter.fillPath(forma, QBrush(tinte))
        elif circulo is not None:
            painter.setBrush(QBrush(fuerte))
            painter.drawEllipse(circulo[0], circulo[1], circulo[1])
        elif self.tema.rueda:
            if self._rueda_abierta() and _diana.es_parte_rueda(bajo):
                _diana.rueda_pintar_bajo(painter, self._diana_centro(c), bajo,
                                         self.diana.proyeccion_actual())
        elif self.tema.diana_plegada and bajo in _diana.FILA:
            self.diana.pintar_bajo(painter, self._cc_fila(c), bajo, buscador=True)
        elif bajo in DIANA and self._diana_viva():
            self._pintar_diana_bajo(painter, self._diana_centro(c), bajo,
                                    buscador=not self.tema.diana_plegada and not self._es_sel)
        else:
            medio_capa = self.tema.capa_h / 2.0
            rects = {"capa": (self._rect_capa, medio_capa), "nav": (self._rect_nav, medio_capa),
                     "propiedades": (self._rect_props, 8.0)}
            if bajo in rects:
                suave = QColor(ROJO)
                suave.setAlphaF(0.07)
                painter.setBrush(QBrush(suave))
                rect, radio = rects[bajo]
                painter.drawRoundedRect(rect(c), radio, radio)
        painter.restore()
        etiqueta(painter, self._texto_icono(bajo), self._pos_etiqueta(c))

    def _dibujar_panel(self, painter, c=None) -> None:
        g = self._panel(c)
        if g is None:
            return
        clave = self.panel
        cc_panel = self.ancla if c is None else c
        if clave == "vistas" and self.tema.rueda:
            # La rueda, centrada en el ojo, sin marco.
            vp = self.app.viewport
            _flotante.fijar_centro(painter, self._diana_centro(cc_panel), self.tema.abajo_anillo)
            _diana.rueda_pintar(painter, self._diana_centro(cc_panel), None,
                                self.diana.proyeccion_actual(), self.diana._en_vista(vp, "bottom"))
            return
        if g.get("radial"):
            self._pintar_rosco(painter, g, clave)
            return
        f = QFont(painter.font())
        f.setPointSizeF(8.5)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(Qt.NoPen)
        # La ayuda es opaca: es mucho texto y tapa las pastillas de debajo.
        painter.setBrush(QBrush(QColor(255, 255, 255, 255 if clave == "ayuda" else 215)))
        painter.drawRoundedRect(g["marco"], 7.0, 7.0)
        for color, ancho in ((HALO, 3.4), (ROJO, 1.6)):
            painter.setPen(QPen(color, ancho))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(g["marco"], 7.0, 7.0)
        if "volver" in g:
            # Volver al anillo entero.
            dibujar_boton_redondo(painter, "volver", g["volver"].center(), None,
                                  relieve=self.tema.relieve)
        if clave == "vistas":
            # La diana plegada, abierta debajo del anillo.
            self._pintar_diana(painter, self._diana_centro(cc_panel), None, True, buscador=False)
            return

        from . import _iconos
        relieve = self.tema.relieve

        def boton(r, texto, activo, color=None, icono=None):
            color = QColor(color) if color is not None else QColor(ROJO)
            fondo = QColor(color)
            fondo.setAlpha(45)
            if relieve:
                # Con volumen: sombra, degradado de arriba abajo y, el
                # activo, rayado en verde.
                caja = QPainterPath()
                caja.addRoundedRect(r, 4.0, 4.0)
                sombra(painter, caja, 1.5, 2.0)
                g = QLinearGradient(r.topLeft(), r.bottomLeft())
                g.setColorAt(0.0, BLANCO)
                g.setColorAt(1.0, QColor(196, 196, 189))
                painter.setPen(QPen(color if activo else QColor(150, 148, 140), 1.0))
                painter.setBrush(QBrush(ROSA_CLARO) if activo else QBrush(g))
                painter.drawRoundedRect(r, 4.0, 4.0)
                if activo:
                    rayar(painter, caja)
                    if icono is not None and _iconos.tiene(icono):
                        # El rayado no pisa el icono.
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QBrush(BLANCO))
                        painter.drawEllipse(QPointF(r.center().x(), r.top() + 4.0 + CHIP_ICONO / 2.0),
                                            CHIP_ICONO * 0.7, CHIP_ICONO * 0.7)
            else:
                painter.setPen(QPen(color if activo else QColor(180, 178, 169), 1.0))
                painter.setBrush(QBrush(fondo if activo else QColor(255, 255, 255, 230)))
                painter.drawRoundedRect(r, 4.0, 4.0)
            painter.setPen(color.darker(140) if activo else QColor(68, 68, 65))
            if icono is not None and _iconos.tiene(icono):
                # Icono encima y etiqueta debajo.
                _iconos.pintar(painter, icono, QPointF(r.center().x(), r.top() + 4.0 + CHIP_ICONO / 2.0),
                               CHIP_ICONO)
                painter.drawText(QRectF(r.left(), r.top() + CHIP_ICONO + 5.0, r.width(),
                                        r.height() - CHIP_ICONO - 5.0),
                                 Qt.AlignHCenter | Qt.AlignVCenter, _tr(texto))
            else:
                painter.drawText(r, Qt.AlignCenter, _tr(texto))

        if clave == "ayuda":
            self._pintar_ayuda(painter, g)   # la del ojo verde
            return
        if clave == "historial":
            # La columna del ojo amarillo: lo último usado, arriba.
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(TINTA)
            painter.drawText(g["titulo"], Qt.AlignLeft | Qt.AlignVCenter, _tr("Últimos"))
            f.setBold(False)
            painter.setFont(f)
            if not self.historial:
                painter.setPen(QColor(120, 120, 114))
                painter.drawText(g["marco"].adjusted(8.0, 26.0, -8.0, -6.0),
                                 Qt.AlignLeft | Qt.AlignVCenter, _tr("Todavía nada"))
            fm = QFontMetricsF(f)
            for i, r in g["entradas"]:
                painter.setPen(QPen(QColor(180, 178, 169), 1.0))
                painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
                painter.drawRoundedRect(r, 4.0, 4.0)
                painter.setPen(QColor(68, 68, 65))
                painter.drawText(r.adjusted(6.0, 0.0, -4.0, 0.0), Qt.AlignLeft | Qt.AlignVCenter,
                                 fm.elidedText("{0}. {1}".format(i + 1, _tr(self.historial[i][0])), Qt.ElideRight,
                                               r.width() - 10.0))
            return
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(TINTA)
        titulo = NOMBRES[clave].split(":")[0]
        painter.drawText(g["titulo"], Qt.AlignLeft | Qt.AlignVCenter, _tr(titulo))
        f.setBold(False)
        painter.setFont(f)
        if "menos" in g:
            painter.setPen(QColor(68, 68, 65))
            painter.drawText(g["etiqueta"], Qt.AlignLeft | Qt.AlignVCenter,
                             _tr(ETIQUETA_LADOS[clave]))
            boton(g["menos"], "−", False)
            boton(g["mas"], "+", False)
            valor = QRectF(g["menos"].right(), g["menos"].top(),
                           g["mas"].left() - g["menos"].right(), g["menos"].height())
            painter.setPen(TINTA)
            painter.drawText(valor, Qt.AlignCenter, _tr(str(int(self.bases[clave].sides))))
        simetria = getattr(self, "simetria", None)
        if clave == "flip" and simetria is not None:
            for k, r in g["chips"]:
                boton(r, TEXTO_FLIP[k], simetria.marcado(k), None, ICONO_FLIP.get(k))
            painter.setPen(QColor(68, 68, 65))
            painter.drawText(g["final_titulo"], Qt.AlignLeft | Qt.AlignVCenter,
                             _tr("Copia y eje fijo (pulsa otra vez para soltar):"))
            for k, r in g.get("finales", ()):
                boton(r, TEXTO_FLIP[k], simetria.marcado(k), COLOR_FLIP.get(k), ICONO_FLIP.get(k))
            return
        if clave == "align":
            for k, r in g["chips"]:
                boton(r, TEXTO_ALINEAR[k], self._marcado_alinear(k), None, ICONO_ALINEAR.get(k))
            return
        actual = self.modo.get(clave)          # Agrupar: acciones, ninguna marcada
        if clave in _seleccion.SEMI and self._barra_modificar() is not None:
            actual = self._barra_modificar().modo.get(clave)
        for modo, r in g["chips"]:
            boton(r, modo, modo == actual,
                  COLOR_GRUPO.get(modo) if clave == "grupo" else None,
                  ICONO_MODO.get((clave, modo)))
        if "finales" in g:
            # Al terminar lo dibujado: nada, grupo, componente o con nombre.
            painter.setPen(QColor(68, 68, 65))
            painter.drawText(g["final_titulo"], Qt.AlignLeft | Qt.AlignVCenter,
                             _tr("Al terminar, lo dibujado será:"))
            actual = self._final_actual()
            for fin, r in g["finales"]:
                boton(r, fin, fin == actual, COLOR_GRUPO.get(fin), ICONO_MODO.get(("fin", fin)))

    def _alinear(self):
        """El control de Alinear (o None)."""
        barra = self._barra_modificar()
        return barra._alinear() if barra is not None else None

    def _marcado_alinear(self, k: str) -> bool:
        ctl = self._alinear()
        if ctl is None:
            return False
        return {"mover": not ctl.copiar, "copiar": bool(ctl.copiar), "escalar": bool(ctl.escalar)}[k]

    def _pintar_rosco(self, painter, g, clave) -> None:
        """El submenú en rosco (Opciones ▸ Submenús ▸ Radiales)."""
        from . import _rosco
        if clave == "camara":
            herr = _diana.CAMARA_HERR
            tools = getattr(self.app.window, "_tools", None) or {}
            activa = self.app.viewport.active_tool
            modos = [(CAMARA_OPCIONES[k], tools.get(herr[k]) is activa, None, k)
                     for k, _r in g["chips"]]
            relieve = self.tema.relieve
            _rosco.pintar(painter, g, _tr("Cámara"), modos, [], None, relieve, TINTA,
                          lambda p, q: dibujar_boton_redondo(p, "volver", q, None, relieve=relieve))
            return
        simetria = getattr(self, "simetria", None)
        if clave == "flip" and simetria is not None:
            modos = [(TEXTO_FLIP_ROSCO[k], simetria.marcado(k), None, ICONO_FLIP.get(k))
                     for k, _r in g["chips"]]
            finales = [(TEXTO_FLIP_ROSCO[k], simetria.marcado(k), COLOR_FLIP.get(k), ICONO_FLIP.get(k))
                       for k, _r in g.get("finales", ())]
            relieve = self.tema.relieve
            _rosco.pintar(painter, g, NOMBRES[clave].split(":")[0], modos, finales, None,
                          relieve, TINTA,
                          lambda p, q: dibujar_boton_redondo(p, "volver", q, None, relieve=relieve))
            return
        if clave == "align":
            modos = [(TEXTO_ALINEAR[k], self._marcado_alinear(k), None, ICONO_ALINEAR.get(k))
                     for k, _r in g["chips"]]
            relieve = self.tema.relieve
            _rosco.pintar(painter, g, NOMBRES[clave], modos, [], None, relieve, TINTA,
                          lambda p, q: dibujar_boton_redondo(p, "volver", q, None, relieve=relieve))
            return
        actual = self.modo.get(clave)          # Agrupar: acciones, ninguna marcada
        if clave in _seleccion.SEMI and self._barra_modificar() is not None:
            actual = self._barra_modificar().modo.get(clave)
        modos = [(m, m == actual, COLOR_GRUPO.get(m) if clave == "grupo" else None,
                  ICONO_MODO.get((clave, m))) for m, _r in g["chips"]]
        fin = self._final_actual() if "finales" in g else None
        finales = [("grupo\ncon nombre" if k == "con nombre" else k, k == fin,
                    COLOR_GRUPO.get(k), ICONO_MODO.get(("fin", k)))
                   for k, _r in g.get("finales", ())]
        lados = int(self.bases[clave].sides) if clave in LIMITES_LADOS else None
        relieve = self.tema.relieve
        _rosco.pintar(painter, g, NOMBRES[clave].split(":")[0], modos, finales, lados,
                      relieve, TINTA,
                      lambda p, q: dibujar_boton_redondo(p, "volver", q, None, relieve=relieve))


class _Cancelar:
    """El botoncito ✕ que acompaña al cursor mientras una orden está en
    marcha, en su propia ventanita: se mueve con cada movimiento del ratón
    (sin esperar al repintado del visor) y, cuando el ratón va hacia él, se
    queda quieto para poder pulsarlo. Un clic cancela la orden como Esc."""

    W, H = 200, 56

    def __init__(self, cadena) -> None:
        self.cadena = cadena
        app = cadena.app
        self.win = Flotante(self, app.window, app.viewport, self.W, self.H,
                            QPointF(self.W / 2.0, self.H - 14.0))
        self.pos = None                       # el centro del botón (px del visor)
        self.sobre = False
        self._ultimo = None                   # dónde estaba el ratón en el movimiento anterior

    def _en(self, p) -> bool:
        q = self.pos
        return (q is not None and p is not None
                and math.hypot(p.x() - q.x(), p.y() - q.y()) <= CHINCHETA_R + 2.0)

    def _pos_etiqueta(self) -> QPointF:
        return QPointF(self.pos.x(), self.pos.y() - 22.0)

    def seguir(self, viewport, p) -> None:
        """El ratón se ha movido sobre el visor."""
        if (not CON_ASPA or not self.cadena._cancelable(viewport)
                or self.cadena._sobre_la_barra(p)):
            self.esconder()
            return
        q, antes = self.pos, self._ultimo
        self._ultimo = QPointF(p)
        if q is not None and antes is not None:
            d = math.hypot(p.x() - q.x(), p.y() - q.y())
            if d <= CANCELAR_QUIETO and d < math.hypot(antes.x() - q.x(), antes.y() - q.y()):
                return                       # va hacia él: quieto, para pulsarlo
        nuevo = q is None
        self.pos = QPointF(p.x() + CANCELAR_DX, p.y() + CANCELAR_DY)
        # Solo se mueve la ventanita: lo pintado (en sus coordenadas) es igual.
        self._mostrar(repintar=nuevo)

    def vigilar(self, viewport) -> None:
        """Del reloj: si la orden terminó sin mover el ratón, se va; si se
        acaba de elegir una (desde la barra), sale ya junto al cursor."""
        if self.pos is not None and not self.cadena._cancelable(viewport):
            self.esconder()
        elif CON_ASPA and self.pos is None and self.cadena._cancelable(viewport):
            p = viewport.mapFromGlobal(QCursor.pos())
            if viewport.rect().contains(p):
                self.seguir(viewport, QPointF(p))

    def _mostrar(self, repintar: bool = True) -> None:
        self.win.colocar(self.pos)
        path = QPainterPath()
        path.addEllipse(self.pos, CHINCHETA_R + 2.0, CHINCHETA_R + 2.0)
        if self.sobre:
            path.addRect(rect_etiqueta(self.win.font(), TEXTO_CANCELAR, self._pos_etiqueta()))
        # En coordenadas de la ventanita el botón no se mueve: la máscara
        # solo cambia con la etiqueta.
        self.win.fijar_mascara(path, clave=(self.sobre,))
        if not self.win.isVisible():
            self.win.show()
            repintar = True
        if repintar:
            self.win.update()

    def esconder(self) -> None:
        self.pos, self.sobre, self._ultimo = None, False, None
        if self.win.isVisible():
            self.win.hide()

    # -- lo que la ventanita pide --
    def pintar(self, painter) -> None:
        if self.pos is None:
            return
        dibujar_boton_redondo(painter, "cerrar", self.pos, "cerrar" if self.sobre else None,
                              relieve=self.cadena.tema.relieve)
        if self.sobre:
            etiqueta(painter, TEXTO_CANCELAR, self._pos_etiqueta())

    def raton_movido(self, p) -> None:
        sobre = self._en(p)
        if sobre != self.sobre:
            self.sobre = sobre
            self._mostrar()

    def raton_clic(self, p) -> None:
        if self._en(p):
            vp = self.cadena.app.viewport
            QTimer.singleShot(0, lambda: self.cadena._cancelar(vp))

    def raton_fuera(self) -> None:
        if self.sobre:
            self.sobre = False
            if self.pos is not None:
                self._mostrar()


class _Filtro(QObject):
    """Filtro de eventos del visor: le pasa el ratón al selector."""

    def __init__(self, cadena, parent) -> None:
        super().__init__(parent)
        self.cadena = cadena

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — nombre de Qt
        try:
            return self.cadena.evento(obj, ev)
        except Exception:  # noqa: BLE001 — un fallo nunca bloquea el ratón
            log.exception("fallo en el filtro de eventos")
            return False


def _ventanita(painter, viewport, pos, titulo, valor, pista, escribiendo) -> None:
    """Una cajita tipo campo de texto al lado del cursor (sin tapar el clic)."""
    chica = QFont(painter.font())
    chica.setPointSizeF(9.0)
    chica.setBold(False)
    grande = QFont(chica)
    grande.setPointSizeF(12.0)
    grande.setBold(True)
    fm, fg = QFontMetricsF(chica), QFontMetricsF(grande)
    texto = valor + ("|" if escribiendo else "")
    ancho = max(fm.horizontalAdvance(_tr(titulo)), fm.horizontalAdvance(_tr(pista)),
                fg.horizontalAdvance(_tr(texto)) + 12.0, 120.0) + 16.0
    alto = 6.0 + fm.height() + 3.0 + fg.height() + 6.0 + 3.0 + fm.height() + 6.0

    # A la derecha y abajo del cursor; si no cabe, al otro lado.
    x, y = pos.x() + 22.0, pos.y() + 22.0
    if x + ancho > viewport.width() - 4:
        x = pos.x() - 22.0 - ancho
    if y + alto > viewport.height() - 4:
        y = pos.y() - 22.0 - alto

    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(ACCENT, 1.5))
    painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
    painter.drawRoundedRect(QRectF(x, y, ancho, alto), 6.0, 6.0)

    painter.setFont(chica)
    painter.setPen(QColor(80, 80, 80))
    painter.drawText(QPointF(x + 8.0, y + 6.0 + fm.ascent()), _tr(titulo))

    campo = QRectF(x + 6.0, y + 6.0 + fm.height() + 3.0,
                   ancho - 12.0, fg.height() + 6.0)
    painter.setPen(QPen(ACCENT if escribiendo else QColor(185, 185, 185), 1.0))
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawRect(campo)
    painter.setFont(grande)
    painter.setPen(QColor(20, 20, 20) if escribiendo else QColor(110, 110, 110))
    painter.drawText(QPointF(campo.left() + 5.0, campo.top() + 3.0 + fg.ascent()),
                     _tr(texto))

    painter.setFont(chica)
    painter.setPen(QColor(110, 110, 110))
    painter.drawText(QPointF(x + 8.0, campo.bottom() + 3.0 + fm.ascent()), _tr(pista))


def _icono_barra(window) -> QIcon:
    """El botón de la barra «Rosco LT»: la diana roja y blanca con el
    arquitecto en negro, con sus colores, sobre la baldosa azul (``_baldosa``);
    si falla, el de siempre."""
    try:
        from . import _baldosa
        cuerpo = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                  + _iconos.SVG["barra_dibujo"] + "</svg>")
        return _baldosa.icono(lambda px: _baldosa.svg(cuerpo, px), colores=True)
    except Exception:  # noqa: BLE001 — queda el icono de siempre
        log.exception("no se pudo hacer el botón en baldosa")
        return _icono(window)


def _icono(window) -> QIcon:
    """El glifo de caja de ``icons/barra_dibujo.svg``, con sus trazos
    (``currentColor``) en el color de texto del tema, como los iconos nativos.
    Si el SVG no se puede leer, la misma caja dibujada a mano."""
    tinta = window.palette().windowText().color()
    try:
        # El arquitecto de colores, como en las barras.
        from . import _iconos
        icono = _iconos.qicono("barra_dibujo")
        if icono is not None:
            return icono
    except Exception:  # noqa: BLE001 — queda la caja monocroma
        log.exception("no se pudo crear el icono del arquitecto")
    try:
        from PySide6.QtSvg import QSvgRenderer
        with open(_ICONO_SVG, encoding="utf-8") as f:
            svg = f.read().replace("currentColor", tinta.name())
        render = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if render.isValid():
            icono = QIcon()
            for lado in (16, 24, 32, 48, 64):
                pm = QPixmap(lado, lado)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.Antialiasing)
                render.render(p, QRectF(0, 0, lado, lado))
                p.end()
                icono.addPixmap(pm)
            return icono
    except Exception:  # noqa: BLE001 — queda el dibujo a mano
        log.exception("no se pudo cargar icons/barra_dibujo.svg")
    return _icono_a_mano(tinta)


def _icono_a_mano(tinta) -> QIcon:
    """La caja del SVG con QPainter (viewBox 48 → 64 px)."""
    k = 64.0 / 48.0

    def pts(*xy):
        return QPolygonF([QPointF(x * k, y * k) for x, y in xy])

    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    for cara, alfa in ((pts((24, 5), (41, 14), (24, 23), (7, 14)), 0.85),
                       (pts((7, 14), (24, 23), (24, 43), (7, 34)), 0.35),
                       (pts((41, 14), (24, 23), (24, 43), (41, 34)), 0.15)):
        color = QColor(ACCENT)
        color.setAlphaF(alfa)
        p.setBrush(QBrush(color))
        p.drawPolygon(cara)
    p.setPen(QPen(tinta, 3 * k, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPolygon(pts((24, 5), (41, 14), (41, 34), (24, 43), (7, 34), (7, 14)))
    p.drawPolyline(pts((7, 14), (24, 23), (41, 14)))
    p.drawPolyline(pts((24, 23), (24, 43)))
    p.end()
    return QIcon(pm)

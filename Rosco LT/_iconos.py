# SPDX-License-Identifier: GPL-3.0-or-later
"""Los iconos de colores de las barras: objetos de dibujo reales, contorno
azul noche grueso, colores planos suaves y un brillo blanco. Sin fondo
(la barra sigue siendo transparente); solo un halo blanco fino para que se
lean sobre un modelo oscuro.

Se dibujan con QtSvg (viewBox 64) y se guardan ya rasterizados por tamaño.
Las claves son las mismas que las de ``_flotante.glifo``; lo que no tenga
icono se sigue dibujando con su silueta.
"""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

log = logging.getLogger("ingetrazo.plugins.rosco_lt.iconos")

# Trazo común: contorno azul noche, juntas y puntas redondas.
_G = '<g stroke="#2e3047" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">'
_GR = '<g stroke-linejoin="round" stroke-linecap="round">'


def _engranaje() -> str:
    puntos = []
    for i in range(32):
        a = i / 32.0 * 2.0 * math.pi - math.pi / 2.0
        r = 24.0 if i % 4 < 2 else 18.0
        puntos.append(f"{32 + r * math.cos(a):.1f} {32 + r * math.sin(a):.1f}")
    return "M" + " L".join(puntos) + " Z"


_LUPA = (_GR + '<line x1="40" y1="40" x2="57" y2="57" stroke="#2e3047" stroke-width="12"/>'
         '<line x1="40" y1="40" x2="57" y2="57" stroke="#e5534b" stroke-width="6"/>'
         '<g stroke="#2e3047" stroke-width="3"><circle cx="26" cy="26" r="19" fill="#b3dcf2"/>'
         '<circle cx="26" cy="26" r="13" fill="#d8eefa" stroke-width="2"/>'
         '<path d="M15 22 A12 12 0 0 1 22 14" fill="none" stroke="#fff" stroke-width="3"/>')

_PEGAR = (_G + '<rect x="9" y="10" width="46" height="51" rx="5" fill="#d9b47e"/>'
          '<rect x="16" y="19" width="32" height="36" rx="2" fill="#fff"/>'
          '<rect x="21" y="5" width="22" height="11" rx="3" fill="#b9c3d9"/>'
          '<g stroke="#8ec5e8" stroke-width="3"><line x1="22" y1="29" x2="42" y2="29"/>'
          '<line x1="22" y1="37" x2="42" y2="37"/><line x1="22" y1="45" x2="34" y2="45"/></g>')

# El contorno de la mano de la barra de modificar (índice arriba, pulgar abajo, dedos
# doblados detrás y la muñeca abajo a la derecha).
_MANO = ("M12.5 10.8 C15 8.5 19 7 24.8 6 C30 6 37 9.5 42.9 12.4 C47 14 51 16.5 52.5 19.3 "
         "C54.5 22 55 24 55.5 26.5 C57 31 58 35 58.6 38 C60 43 62 47 63.4 50.1 "
         "C63.5 53 63.3 55 62.8 56.1 C60 58 57.5 58.8 55 58.6 L42.9 57.4 L24.8 54.9 "
         "C21 54.8 18.5 54.8 16.3 54.7 C14 54.4 13.5 51 15.7 49.5 C18 49 20 49 22.3 48.9 "
         "C24.5 48.6 26 48.2 27.2 47.7 C30 46.8 32 46 33.2 44.7 C35.5 42.5 36.2 40 36.2 38 "
         "C36.8 35 36.8 33 36.6 30.2 C36.3 27 35.3 24.8 33.8 22.9 C32 20.5 30.5 19 28.4 18.1 "
         "C26 16.6 23.5 15.6 21.1 15.1 L12.7 14.8 C10.8 14.3 10.8 11.5 12.5 10.8 Z")

_DESHACER = (_GR + '<path d="M54 50 C54 26 38 20 20 24" fill="none" stroke="#2e3047" stroke-width="11"/>'
             '<path d="M54 50 C54 26 38 20 20 24" fill="none" stroke="#f6c54a" stroke-width="6"/>'
             '<polygon points="6,26 24,12 26,36" fill="#f6c54a" stroke="#2e3047" stroke-width="3"/></g>')

SVG = {
    # -- Barra de dibujo --
    "linea": _G + '<g transform="rotate(-45 36 30)">'
             '<path d="M6 30 L16 23 L16 37 Z" fill="#f3dcb2"/>'
             '<path d="M6 30 L10 27.2 L10 32.8 Z" fill="#2e3047"/>'
             '<rect x="16" y="23" width="32" height="14" fill="#f6c54a"/>'
             '<line x1="19" y1="27" x2="45" y2="27" stroke="#fff" stroke-width="2.5"/>'
             '<rect x="48" y="23" width="5" height="14" fill="#b9c3d9"/>'
             '<rect x="53" y="23" width="7" height="14" rx="3" fill="#f4a3a0"/></g>'
             '<polygon points="11.5,47.5 9.7,52.1 4.8,52.3 8.7,55.4 7.4,60.2 11.5,57.5 15.6,60.2 '
             '14.4,55.4 18.2,52.3 13.3,52.1" fill="#e5534b" stroke-width="2"/></g>',
    "rect": _G + '<rect x="9" y="15" width="46" height="34" fill="none" stroke-width="7"/>'
            '<rect x="9" y="15" width="46" height="34" fill="none" stroke="#8ec5e8" stroke-width="3"/>'
            '<circle cx="9" cy="15" r="4.5" fill="#e5534b"/><circle cx="55" cy="15" r="4.5" fill="#e5534b"/>'
            '<circle cx="9" cy="49" r="4.5" fill="#e5534b"/><circle cx="55" cy="49" r="4.5" fill="#e5534b"/></g>',
    "line": _G + '<polygon points="10,48 16,14 40,9 55,30 36,55" fill="none" stroke-width="7"/>'
            '<polygon points="10,48 16,14 40,9 55,30 36,55" fill="none" stroke="#8ec5e8" stroke-width="3"/>'
            '<circle cx="10" cy="48" r="4.5" fill="#e5534b"/><circle cx="16" cy="14" r="4.5" fill="#e5534b"/>'
            '<circle cx="40" cy="9" r="4.5" fill="#e5534b"/><circle cx="55" cy="30" r="4.5" fill="#e5534b"/>'
            '<circle cx="36" cy="55" r="4.5" fill="#e5534b"/></g>',
    "poly": _G + '<polygon points="32,7 53.6,19.5 53.6,44.5 32,57 10.4,44.5 10.4,19.5" fill="#b9c3d9"/>'
            '<polygon points="32,15 46.7,23.5 46.7,40.5 32,49 17.3,40.5 17.3,23.5" fill="#dde3ef" stroke-width="2"/>'
            '<circle cx="32" cy="32" r="8" fill="#fff"/>'
            '<path d="M15 23 L28 15.5" stroke="#fff" stroke-width="2.5"/></g>',
    "arco": _G + '<path d="M5 48 A27 27 0 0 1 59 48 Z" fill="#f6c54a"/>'
            '<path d="M22 48 A10 10 0 0 1 42 48 Z" fill="#fff"/>'
            '<g stroke-width="2.2"><line x1="50.2" y1="37.5" x2="54.5" y2="35"/>'
            '<line x1="42.5" y1="29.8" x2="45" y2="25.5"/><line x1="32" y1="27" x2="32" y2="22"/>'
            '<line x1="21.5" y1="29.8" x2="19" y2="25.5"/><line x1="13.8" y1="37.5" x2="9.5" y2="35"/></g>'
            '<line x1="32" y1="48" x2="48" y2="16" stroke="#e5534b" stroke-width="3.5"/>'
            '<circle cx="32" cy="48" r="3.5" fill="#e5534b"/></g>',
    "circle": _GR + '<circle cx="32" cy="39" r="20" fill="none" stroke="#e5534b" stroke-width="3" stroke-dasharray="5 5"/>'
              '<path d="M32 16 L19 55 M32 16 L45 55" fill="none" stroke="#2e3047" stroke-width="9"/>'
              '<path d="M32 16 L19 55 M32 16 L45 55" fill="none" stroke="#b9c3d9" stroke-width="4"/>'
              '<g stroke="#2e3047" stroke-width="3"><rect x="29" y="3" width="6" height="8" rx="2" fill="#2e3047"/>'
              '<circle cx="32" cy="15" r="6.5" fill="#f6c54a"/><circle cx="45" cy="55" r="2.5" fill="#e5534b"/></g></g>',
    "borrar": _G + '<line x1="6" y1="57" x2="58" y2="57" stroke="#e5534b" stroke-dasharray="5 5"/>'
              '<g transform="rotate(-30 32 32)">'
              '<rect x="8" y="21" width="48" height="22" rx="4" fill="#f4a3a0"/>'
              '<path d="M30 21 H52 a4 4 0 0 1 4 4 V39 a4 4 0 0 1 -4 4 H30 Z" fill="#8ec5e8"/>'
              '<line x1="13" y1="26" x2="24" y2="26" stroke="#fff" stroke-width="2.5"/></g></g>',
    "seleccionar": _G + '<rect x="5" y="5" width="40" height="34" fill="none" stroke-width="2.5" stroke-dasharray="5 4"/>'
                   '<path d="M25 17 L25 56 L34 47 L40 60 L47 57 L41 44 L53 44 Z" fill="#e5534b"/>'
                   '<line x1="29" y1="26" x2="29" y2="44" stroke="#fff" stroke-width="2.5"/></g>',
    "grupo": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z" fill="#f3dcb2"/>'
             '<path d="M8 20 L32 32 L32 58 L8 46 Z" fill="#d9b47e"/>'
             '<path d="M56 20 L32 32 L32 58 L56 46 Z" fill="#e8c793"/>'
             '<path d="M20 14 L44 26 L44 36" fill="none" stroke="#b9c3d9" stroke-width="5"/>'
             '<path d="M20 14 L44 26 L44 36" fill="none" stroke-width="1.2"/></g>',
    "medir": _G + '<path d="M34 40 H59 V51 H34 Z" fill="#f6c54a"/>'
             '<g stroke-width="2"><line x1="40" y1="40" x2="40" y2="45"/><line x1="46" y1="40" x2="46" y2="47"/>'
             '<line x1="52" y1="40" x2="52" y2="45"/></g>'
             '<rect x="58" y="37" width="3.5" height="17" fill="#2e3047"/>'
             '<rect x="5" y="11" width="38" height="40" rx="11" fill="#e5534b"/>'
             '<circle cx="24" cy="31" r="11" fill="#dde3ef"/><circle cx="24" cy="31" r="3.5" fill="#2e3047"/>'
             '<path d="M10 22 A12 12 0 0 1 16 15" fill="none" stroke="#fff" stroke-width="2.5"/></g>',
    # -- Barra de modificar --
    "move": _G + '<polygon points="32,4 43,15 36,15 36,28 49,28 49,21 60,32 49,43 49,36 36,36 36,49 '
            '43,49 32,60 21,49 28,49 28,36 15,36 15,43 4,32 15,21 15,28 28,28 28,15 21,15" fill="#e5534b"/>'
            '<circle cx="32" cy="32" r="6" fill="#fff"/></g>',
    "scale": _G + '<rect x="7" y="7" width="50" height="50" rx="3" fill="none" stroke-dasharray="6 5"/>'
             '<rect x="7" y="33" width="24" height="24" rx="3" fill="#8ec5e8"/>'
             '<line x1="11" y1="38" x2="20" y2="38" stroke="#fff" stroke-width="2.5"/>'
             '<line x1="28" y1="36" x2="48" y2="16" stroke-width="9"/>'
             '<line x1="28" y1="36" x2="48" y2="16" stroke="#e5534b" stroke-width="4"/>'
             '<polygon points="54,10 52,25 39,12" fill="#e5534b"/></g>',
    "flip": _G + '<polygon points="27,12 27,52 5,52" fill="#8ec5e8"/>'
            '<polygon points="37,12 37,52 59,52" fill="none" stroke-dasharray="5 4"/>'
            '<line x1="32" y1="4" x2="32" y2="60" stroke="#e5534b" stroke-dasharray="4 4"/>'
            '<path d="M14 8 Q32 -2 50 8" fill="none"/>'
            '<polygon points="50,8 43,9 47,3" fill="#2e3047"/></g>',
    "rotate": _GR + '<path d="M13 38 A19 19 0 1 1 30 53" fill="none" stroke="#2e3047" stroke-width="10"/>'
              '<path d="M13 38 A19 19 0 1 1 30 53" fill="none" stroke="#e5534b" stroke-width="5"/>'
              '<g stroke="#2e3047" stroke-width="3"><polygon points="21,55 33,45 34,61" fill="#e5534b"/>'
              '<rect x="25" y="25" width="14" height="14" rx="2" fill="#8ec5e8" transform="rotate(20 32 32)"/></g></g>',
    # Rosco LT: el arquitecto (casco y traje) en silueta negra con un
    # filo blanco, dentro de una diana de tiro roja y blanca, con la mira.
    "barra_dibujo": '<defs><clipPath id="diana_arq"><circle cx="32" cy="32" r="30"/></clipPath></defs>'
             + '<g stroke="#8a1414" stroke-width="1.2">'
             + "".join(f'<circle cx="32" cy="32" r="{30 - 6 * i}" fill="{c}"/>'
                       for i, c in enumerate(("#d62222", "#ffffff", "#d62222", "#ffffff", "#d62222")))
             + '</g><g clip-path="url(#diana_arq)"><g transform="translate(16.5 15) scale(0.66)" '
             'fill="#111111" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round">'
             '<path d="M2 63 C2 50 11 42 26 42 C41 42 50 50 50 63 Z"/>'
             '<rect x="21" y="33" width="10" height="10" stroke="none"/>'
             '<circle cx="14.5" cy="27" r="3.5"/><circle cx="37.5" cy="27" r="3.5"/>'
             '<circle cx="26" cy="26" r="11.5"/>'
             '<path d="M12 20 A14 14 0 0 1 40 20 Z"/>'
             '<rect x="7" y="18" width="38" height="6" rx="3"/>'
             '<rect x="22.5" y="6" width="7" height="12" rx="2"/>'
             '</g></g>'
             # La mira: blanca con borde rojo oscuro.
             + '<g stroke-linecap="round">'
             + "".join(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#8a1414" stroke-width="4.4"/>'
                       f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#ffffff" stroke-width="2"/>'
                       for a, b, c, d in ((32, 1, 32, 9), (32, 55, 32, 63), (1, 32, 9, 32), (55, 32, 63, 32)))
             + '</g>',
    # Rosco LT: la mano de la imagen de referencia (de canto, ligeramente
    # inclinada) que pellizca la cruz de flechas entre el índice y el pulgar.
    "barra_modificar": '<g transform="translate(32 32) scale(0.94) translate(-32 -32)" '
                'stroke-linejoin="round" stroke-linecap="round">'
                f'<path d="{_MANO}" fill="#fcd3a1"/>'
                '<path d="M52.5 19.3 C55 24 57 31 58.6 38 C60 43 62 47 63.4 50.1 C63.5 53 63.3 55 62.8 56.1 '
                'C60 58 57.5 58.8 55 58.6 L52 58.3 C55 55 57 51 56.5 46 C55.5 38 53 28 49 21 Z" fill="#efbd8c"/>'
                '<path d="M28.4 18.1 C32 20.5 36 26 36.6 30.2 C36.8 33 36.8 36 36.2 38 L39 37 '
                'C39.5 31 38 25 33 20 Z" fill="#efbd8c"/>'
                f'<path d="{_MANO}" fill="none" stroke="#2e3047" stroke-width="3"/>'
                '<path d="M33 9.5 C39 12 44 18 46.5 26 M44.7 13.3 C47.5 16 49.5 20 50.7 24" '
                'fill="none" stroke="#2e3047" stroke-width="2.4"/>'
                '<rect x="13" y="10.2" width="6.5" height="3.2" rx="1.6" fill="#fde8de" '
                'stroke="#2e3047" stroke-width="1.6"/>'
                '<rect x="16" y="50.3" width="6.5" height="3.4" rx="1.7" fill="#fde8de" '
                'stroke="#2e3047" stroke-width="1.6" transform="rotate(4 19 52)"/>'
                '<path d="M25 51 L31 50.2" stroke="#fff" stroke-width="2"/>'
                '<polygon points="17,18.6 23,25.2 20,25.2 20,29.6 26.4,29.6 26.4,26.6 33,32.6 26.4,38.6 '
                '26.4,35.6 20,35.6 20,40 23,40 17,46.6 11,40 14,40 14,35.6 7.6,35.6 7.6,38.6 1,32.6 '
                '7.6,26.6 7.6,29.6 14,29.6 14,25.2 11,25.2" fill="#f7cf6b" stroke="#2e3047" stroke-width="2.6"/>'
                '<path d="M4.5 31.6 L8 28.6 M16 21.6 L17.6 20.1" stroke="#fff" stroke-width="1.8"/></g>',
    "align": _G + '<line x1="4" y1="56" x2="60" y2="56" stroke="#e5534b" stroke-width="4"/>'
             '<rect x="8" y="30" width="20" height="24" fill="#8ec5e8"/>'
             '<rect x="36" y="10" width="20" height="18" fill="#f6c54a"/>'
             '<line x1="46" y1="32" x2="46" y2="43" stroke-width="3.5"/>'
             '<polygon points="40,42 52,42 46,51" fill="#2e3047"/></g>',
    # -- Barra de selección --
    "suprimir": _G + '<rect x="25" y="5" width="14" height="7" rx="2" fill="#dde3ef"/>'
                '<path d="M14 19 H50 L46 59 H18 Z" fill="#dde3ef"/>'
                '<rect x="9" y="12" width="46" height="8" rx="3" fill="#b9c3d9"/>'
                '<g stroke-width="2.5"><line x1="25" y1="27" x2="26" y2="52"/><line x1="32" y1="27" x2="32" y2="52"/>'
                '<line x1="39" y1="27" x2="38" y2="52"/></g></g>',
    "cortar": _GR + '<g stroke="#2e3047" stroke-width="3">'
              '<path d="M33 34 L19 5 L25 3 L37 31 Z" fill="#b9c3d9"/>'
              '<path d="M31 34 L45 5 L39 3 L27 31 Z" fill="#dde3ef"/></g>'
              '<path d="M32 33 L22 44 M32 33 L42 44" fill="none" stroke="#2e3047" stroke-width="9"/>'
              '<path d="M32 33 L22 44 M32 33 L42 44" fill="none" stroke="#e5534b" stroke-width="4"/>'
              '<g stroke="#2e3047" stroke-width="3"><circle cx="19" cy="50" r="9" fill="#e5534b"/>'
              '<circle cx="19" cy="50" r="4" fill="#fff"/><circle cx="45" cy="50" r="9" fill="#e5534b"/>'
              '<circle cx="45" cy="50" r="4" fill="#fff"/><circle cx="32" cy="32" r="2.5" fill="#f6c54a"/></g></g>',
    "copiar": _G + '<rect x="7" y="5" width="32" height="40" rx="4" fill="none" stroke-dasharray="5 4"/>'
              '<rect x="24" y="19" width="33" height="40" rx="4" fill="#fff"/>'
              '<g stroke="#8ec5e8"><line x1="31" y1="30" x2="50" y2="30"/><line x1="31" y1="38" x2="50" y2="38"/>'
              '<line x1="31" y1="46" x2="43" y2="46"/></g></g>',
    # Un ojo cerrado: el párpado y las pestañas hacia abajo.
    "ocultar": _GR + '<path d="M6 24 Q32 50 58 24" fill="none" stroke="#2e3047" stroke-width="7"/>'
               '<path d="M14 34 L8 45 M23 39 L19 52 M32 41 V56 M41 39 L45 52 M50 34 L56 45" fill="none"'
               ' stroke="#2e3047" stroke-width="5"/></g>',
    "bloquear": _GR + '<path d="M20 30 V21 A12 12 0 0 1 44 21 V30" fill="none" stroke="#2e3047" stroke-width="11"/>'
                '<path d="M20 30 V21 A12 12 0 0 1 44 21 V30" fill="none" stroke="#b9c3d9" stroke-width="5"/>'
                '<g stroke="#2e3047" stroke-width="3"><rect x="11" y="28" width="42" height="31" rx="6" fill="#f6c54a"/>'
                '<circle cx="32" cy="41" r="4.5" fill="#2e3047"/><rect x="30.5" y="41" width="3" height="10" rx="1" fill="#2e3047"/>'
                '<line x1="17" y1="34" x2="17" y2="52" stroke="#fff" stroke-width="2.5"/></g></g>',
    "orientar": _G + '<path d="M26 16 L48 27 L26 38 L4 27 Z" fill="#dde3ef"/>'
                '<path d="M4 27 L26 38 L26 61 L4 50 Z" fill="#e5534b"/>'
                '<path d="M48 27 L26 38 L26 61 L48 50 Z" fill="#8ec5e8"/>'
                '<path d="M38 8 A14 14 0 0 1 58 20" fill="none" stroke-width="3.5"/>'
                '<polygon points="60,26 53,19 61,16" fill="#2e3047"/></g>',
    # Invertir cara: la cara (clara) y su dorso (rojo), con la flecha que la voltea.
    "invertir": _G + '<path d="M6 22 L28 14 L28 54 L6 62 Z" fill="#dde3ef"/>'
                '<path d="M36 14 L58 22 L58 62 L36 54 Z" fill="#e5534b"/>'
                '<line x1="11" y1="27" x2="11" y2="50" stroke="#fff" stroke-width="2.5"/>'
                '<path d="M14 10 A20 9 0 0 1 48 9" fill="none" stroke-width="3.5"/>'
                '<polygon points="54,10 45,15 46,4" fill="#2e3047"/></g>',
    "opciones": _G + f'<path d="{_engranaje()}" fill="#b9c3d9"/>'
                '<circle cx="32" cy="32" r="9" fill="#fff"/>'
                '<path d="M17 24 A17 17 0 0 1 24 16" fill="none" stroke="#fff" stroke-width="2.5"/></g>',
    # Crear (grupo, componente…): un puzle de cuatro piezas encajadas sin
    # hueco (azul, verde, amarillo, rojo), cada una con su cajita.
    "agrupar": _GR + '<defs>'
               '<linearGradient id="q_b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6db3f2"/><stop offset="1" stop-color="#2566ad"/></linearGradient>'
               '<linearGradient id="q_g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#66d694"/><stop offset="1" stop-color="#1b8f4b"/></linearGradient>'
               '<linearGradient id="q_y" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffdf5c"/><stop offset="1" stop-color="#d19e00"/></linearGradient>'
               '<linearGradient id="q_r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f6695f"/><stop offset="1" stop-color="#ad1f19"/></linearGradient>'
               '</defs>'
               # La sombra del botón y las cuatro piezas, con degradado.
               '<rect x="8" y="9" width="53" height="52" rx="6" fill="#000000" fill-opacity="0.22"/>'
               '<g stroke="#2e3047" stroke-width="2" stroke-linejoin="round">'
               '<path d="M6 10 a4 4 0 0 1 4 -4 H32 V16 a4 4 0 0 0 0 8 V34 H6 Z" fill="url(#q_b)"/>'
               '<path d="M32 6 H54 a4 4 0 0 1 4 4 V34 H32 V24 a4 4 0 0 1 0 -8 Z" fill="url(#q_g)"/>'
               '<path d="M6 34 H32 V58 H10 a4 4 0 0 1 -4 -4 Z" fill="url(#q_y)"/>'
               '<path d="M32 34 H58 V54 a4 4 0 0 1 -4 4 H32 Z" fill="url(#q_r)"/>'
               '<circle cx="32" cy="20" r="4" fill="url(#q_b)"/><circle cx="45" cy="34" r="4" fill="url(#q_g)"/>'
               '<circle cx="32" cy="46" r="4" fill="url(#q_r)"/><circle cx="19" cy="34" r="4" fill="url(#q_y)"/></g>'
               # El relieve, solo por fuera: brillo arriba e izquierda, sombra abajo y derecha.
               '<g fill="none" stroke="#ffffff" stroke-opacity="0.6" stroke-width="2" stroke-linecap="round">'
               '<path d="M9 31 V11 a2 2 0 0 1 2 -2 H30"/><path d="M34 9 H53"/><path d="M9 54 V37"/></g>'
               '<g fill="none" stroke="#000000" stroke-opacity="0.22" stroke-width="1.8" stroke-linecap="round">'
               '<path d="M55 11 V31"/><path d="M11 55 H30"/><path d="M34 55 H52 a3 3 0 0 0 3 -3 V37"/></g>'
               + "".join(
                   f'<g stroke="#2e3047" stroke-width="1.2" stroke-linejoin="round">'
                   f'<path d="M{x} {y - 7} L{x + 7} {y - 3.5} L{x} {y} L{x - 7} {y - 3.5} Z" fill="#ffffff"/>'
                   f'<path d="M{x - 7} {y - 3.5} L{x} {y} L{x} {y + 8} L{x - 7} {y + 4.5} Z" fill="#e4e8f0"/>'
                   f'<path d="M{x + 7} {y - 3.5} L{x} {y} L{x} {y + 8} L{x + 7} {y + 4.5} Z" fill="#c9d1de"/></g>'
                   for x, y in ((18, 20), (46, 20), (18, 46), (46, 46)))
               + '</g>',
    # -- Botones pequeños --
    "notas": _G + '<rect x="11" y="10" width="42" height="49" rx="4" fill="#fbe7a1"/>'
             '<g stroke="#e3a92b" stroke-width="2.5"><line x1="18" y1="26" x2="46" y2="26"/>'
             '<line x1="18" y1="34" x2="46" y2="34"/><line x1="18" y1="42" x2="46" y2="42"/>'
             '<line x1="18" y1="50" x2="36" y2="50"/></g>'
             '<g fill="#fff"><circle cx="20" cy="10" r="3.5"/><circle cx="29" cy="10" r="3.5"/>'
             '<circle cx="38" cy="10" r="3.5"/><circle cx="47" cy="10" r="3.5"/></g></g>',
    "tiempo": _G + '<rect x="27" y="3" width="10" height="7" rx="2" fill="#b9c3d9"/>'
              '<rect x="47" y="12" width="7" height="7" rx="2" fill="#b9c3d9" transform="rotate(45 50.5 15.5)"/>'
              '<circle cx="32" cy="37" r="23" fill="#e5534b"/><circle cx="32" cy="37" r="16" fill="#fff"/>'
              '<g stroke-width="2.2"><line x1="32" y1="23" x2="32" y2="26"/><line x1="46" y1="37" x2="43" y2="37"/>'
              '<line x1="32" y1="51" x2="32" y2="48"/><line x1="18" y1="37" x2="21" y2="37"/></g>'
              '<line x1="32" y1="37" x2="39" y2="27" stroke-width="3.5"/>'
              '<circle cx="32" cy="37" r="2.5" fill="#2e3047"/></g>',
    "guardar": _G + '<rect x="8" y="8" width="48" height="48" rx="6" fill="#4a8fd8"/>'
               '<rect x="19" y="8" width="26" height="16" fill="#dde3ef"/>'
               '<rect x="35" y="11" width="6" height="10" fill="#2e3047" stroke-width="0"/>'
               '<rect x="16" y="33" width="32" height="20" rx="2" fill="#fff"/></g>',
    "copia": _G + '<rect x="4" y="4" width="40" height="40" rx="5" fill="#b9a3e6"/>'
             '<rect x="18" y="18" width="42" height="42" rx="6" fill="#8e5bd6"/>'
             '<rect x="28" y="18" width="22" height="13" fill="#e8ddf7"/>'
             '<rect x="25" y="41" width="28" height="17" rx="2" fill="#fff"/></g>',
    "texto": _G + '<path d="M10 10 H54 V20 H48 V16 H37 V50 H43 V56 H21 V50 H27 V16 H16 V20 H10 Z" '
             'fill="#2fa36b"/></g>',
    "calc": _G + '<rect x="14" y="5" width="36" height="54" rx="6" fill="#2e3047"/>'
            '<rect x="20" y="11" width="24" height="12" rx="2" fill="#bfe3c8"/>'
            '<g fill="#fff" stroke-width="0"><rect x="20" y="29" width="6" height="6" rx="1.5"/>'
            '<rect x="29" y="29" width="6" height="6" rx="1.5"/><rect x="20" y="38" width="6" height="6" rx="1.5"/>'
            '<rect x="29" y="38" width="6" height="6" rx="1.5"/><rect x="20" y="47" width="6" height="6" rx="1.5"/>'
            '<rect x="29" y="47" width="6" height="6" rx="1.5"/></g>'
            '<g fill="#e5534b" stroke-width="0"><rect x="38" y="29" width="6" height="6" rx="1.5"/>'
            '<rect x="38" y="38" width="6" height="15" rx="1.5"/></g></g>',
    "pegar": _PEGAR + '</g>',
    "pegar_sitio": _PEGAR + '<circle cx="50" cy="51" r="10" fill="#fff"/>'
                   '<circle cx="50" cy="51" r="4.5" fill="#e5534b" stroke-width="2"/>'
                   '<g stroke-width="2.5"><line x1="50" y1="38" x2="50" y2="42"/><line x1="50" y1="60" x2="50" y2="64"/>'
                   '<line x1="37" y1="51" x2="41" y2="51"/><line x1="59" y1="51" x2="63" y2="51"/></g></g>',
    # -- Diana --
    "buscar": _LUPA + '</g></g>',
    "zoom_sel": _LUPA + '<rect x="19" y="19" width="14" height="14" rx="1.5" fill="#8ec5e8" stroke-width="2.5"/></g></g>',
    "zoom_previo": _LUPA + '<line x1="34" y1="26" x2="20" y2="26" stroke-width="3.5"/>'
                   '<polygon points="15,26 22,20 22,32" fill="#2e3047"/></g></g>',
    "centrar": _G + '<path d="M8 20 V8 H20 M44 8 H56 V20 M56 44 V56 H44 M20 56 H8 V44" fill="none" stroke-width="5"/>'
               '<path d="M32 17 L46 24 L32 31 L18 24 Z" fill="#dde3ef"/>'
               '<path d="M18 24 L32 31 L32 47 L18 40 Z" fill="#8ec5e8"/>'
               '<path d="M46 24 L32 31 L32 47 L46 40 Z" fill="#5fa6d6"/></g>',
    "encuadre": _G + '<path d="M18 34 V16 a4 4 0 0 1 8 0 V30 V10 a4 4 0 0 1 8 0 V30 V13 a4 4 0 0 1 8 0 V32 '
                'V20 a4 4 0 0 1 8 0 V40 C50 52 44 60 34 60 H30 C24 60 20 56 16 50 L8 38 a4 4 0 0 1 7 -5 Z" fill="#f3dcb2"/>'
                '<line x1="23" y1="18" x2="23" y2="26" stroke="#fff" stroke-width="2.5"/></g>',
    "deshacer": _DESHACER,
    "rehacer": '<g transform="translate(64 0) scale(-1 1)">' + _DESHACER + '</g>',
    "conica": _G + '<polygon points="8,50 56,50 43,14 21,14" fill="#8ec5e8" stroke-width="4"/>'
              '<line x1="16" y1="42" x2="22" y2="22" stroke="#fff" stroke-width="3"/></g>',
    "paralela": _G + '<polygon points="6,48 40,48 58,16 24,16" fill="#8ec5e8" stroke-width="4"/>'
                '<line x1="16" y1="41" x2="27" y2="22" stroke="#fff" stroke-width="3"/></g>',
    "reiniciar": _GR + '<path d="M47 16 A21 21 0 1 0 53 32" fill="none" stroke="#2e3047" stroke-width="11"/>'
                 '<path d="M47 16 A21 21 0 1 0 53 32" fill="none" stroke="#86cfc6" stroke-width="6"/>'
                 '<polygon points="55,6 56,24 39,19" fill="#86cfc6" stroke="#2e3047" stroke-width="3"/>'
                 '<circle cx="32" cy="34" r="6" fill="#e5534b" stroke="#2e3047" stroke-width="3"/></g>',
    "ext": _G + '<path d="M10 22 H25 A7 7 0 1 1 39 22 H54 V35 A7 7 0 1 0 54 47 V59 H10 Z" fill="#86cfc6"/>'
           '<line x1="16" y1="29" x2="16" y2="44" stroke="#fff" stroke-width="2.5"/></g>',
    # Los menús de IngeTrazo en árbol: una hoja de menú con sus ramas.
    "menus": _G + '<rect x="7" y="5" width="50" height="54" rx="6" fill="#fff"/>'
             '<path d="M7 17 V11 a6 6 0 0 1 6 -6 H51 a6 6 0 0 1 6 6 V17 Z" fill="#e5534b"/>'
             '<path d="M16 26 V48 M16 37 H23 M16 48 H23" fill="none" stroke-width="2.4"/>'
             '<circle cx="16" cy="26" r="3.6" fill="#f6c54a"/>'
             '<circle cx="27" cy="37" r="3.2" fill="#8ec5e8"/><circle cx="27" cy="48" r="3.2" fill="#8ec5e8"/>'
             '<g stroke="#b9c3d9" stroke-width="3.2"><line x1="23" y1="26" x2="49" y2="26"/>'
             '<line x1="34" y1="37" x2="49" y2="37"/><line x1="34" y1="48" x2="45" y2="48"/></g></g>',
    "bar": _G +'<rect x="6" y="8" width="52" height="13" rx="4" fill="none"/>'
           '<rect x="6" y="26" width="52" height="13" rx="4" fill="none"/>'
           '<rect x="6" y="44" width="40" height="13" rx="4" fill="none"/>'
           '<g stroke-width="2"><circle cx="14" cy="14.5" r="3" fill="#e5534b"/><circle cx="23" cy="14.5" r="3" fill="#f6c54a"/>'
           '<circle cx="32" cy="14.5" r="3" fill="#8ec5e8"/><circle cx="14" cy="32.5" r="3" fill="#86cfc6"/>'
           '<circle cx="23" cy="32.5" r="3" fill="#e5534b"/><circle cx="14" cy="50.5" r="3" fill="#f6c54a"/></g></g>',
    # -- Anclar la barra --
    "chincheta": _G + '<g transform="rotate(40 32 32)">'
                 '<line x1="32" y1="39" x2="32" y2="60" stroke-width="6"/>'
                 '<line x1="32" y1="39" x2="32" y2="59" stroke="#b9c3d9" stroke-width="2.5"/>'
                 '<rect x="16" y="32" width="32" height="8" rx="3" fill="#b9c3d9"/>'
                 '<polygon points="25,14 39,14 42,33 22,33" fill="#b9c3d9"/>'
                 '<rect x="21" y="5" width="22" height="10" rx="3" fill="#b9c3d9"/></g></g>',
    "chincheta_clavada": _G + '<line x1="32" y1="39" x2="32" y2="60" stroke-width="6"/>'
                         '<line x1="32" y1="39" x2="32" y2="59" stroke="#b9c3d9" stroke-width="2.5"/>'
                         '<rect x="16" y="32" width="32" height="8" rx="3" fill="#e5534b"/>'
                         '<polygon points="25,14 39,14 42,33 22,33" fill="#e5534b"/>'
                         '<rect x="21" y="5" width="22" height="10" rx="3" fill="#e5534b"/>'
                         '<line x1="29" y1="18" x2="27.5" y2="29" stroke="#fff" stroke-width="2.5"/></g>',
    "cerrar": '<g stroke-linecap="round">'
              '<path d="M17 17 L47 47 M47 17 L17 47" stroke="#2e3047" stroke-width="12"/>'
              '<path d="M17 17 L47 47 M47 17 L17 47" stroke="#e5534b" stroke-width="6"/></g>',
    # Las vistas (diana plegada): una diana pequeña con sus cuatro triángulos.
    "vistas": _G + '<circle cx="32" cy="32" r="19" fill="#fff"/>'
              '<path d="M18.5 18.5 L45.5 45.5 M45.5 18.5 L18.5 45.5" stroke-width="2.2"/>'
              '<circle cx="32" cy="32" r="7.5" fill="#8ec5e8"/>'
              '<path d="M32 3 L38.5 12 H25.5 Z M32 61 L25.5 52 H38.5 Z M3 32 L12 25.5 V38.5 Z '
              'M61 32 L52 38.5 V25.5 Z" fill="#e5534b"/></g>',
    # Las propiedades (Info de entidad): una «i» en su círculo.
    "propiedades": _G + '<circle cx="32" cy="32" r="26" fill="#f6c54a"/>'
                   '<circle cx="32" cy="19" r="4.5" fill="#2e3047" stroke="none"/>'
                   '<rect x="28" y="27" width="8" height="23" rx="2.5" fill="#2e3047" stroke="none"/></g>',
    # Pantalla limpia: la pantalla y cuatro esquinas que se abren.
    "limpia": _G + '<rect x="15" y="17" width="34" height="30" rx="3" fill="#8ec5e8"/>'
              '<line x1="21" y1="24" x2="31" y2="24" stroke="#fff" stroke-width="2.5"/>'
              '<path d="M5 16 V5 H16 M48 5 H59 V16 M59 48 V59 H48 M16 59 H5 V48" fill="none" stroke-width="5"/></g>',
    # Pintar: el cubo de pintura volcando, y el gotero de muestrear.
    "pintar": _G + '<path d="M12 26 L30 8 L52 30 L34 48 Z" fill="#8ec5e8"/>'
              '<path d="M12 26 L30 8 L52 30" fill="none" stroke-width="3.5"/>'
              '<path d="M8 30 C4 40 4 48 10 52 C16 48 16 40 12 32 Z" fill="#e5534b"/>'
              '<path d="M30 8 L30 2 L46 2" fill="none" stroke-width="3.5"/>'
              '<path d="M34 48 L52 30 L58 36 L40 54 Z" fill="#5fa6d6"/></g>',
    # El aro de la rueda: el ojo con una U (mostrar lo último) o una T (todo),
    # geometría y objetos ocultos, ejes.
    "mostrar_ultimo": _GR + '<path d="M1 32 Q32 -4 63 32 Q32 68 1 32 Z" fill="#fff" stroke="#2e3047" stroke-width="2.5"/>'
                      '<path d="M24 23 V36 Q24 43 32 43 Q40 43 40 36 V23" fill="none" stroke="#c62828" stroke-width="3.6"/></g>',
    "mostrar_todo": _GR + '<path d="M1 32 Q32 -4 63 32 Q32 68 1 32 Z" fill="#fff" stroke="#2e3047" stroke-width="2.5"/>'
                    '<path d="M23 24 H41 M32 24 V44" fill="none" stroke="#c62828" stroke-width="3.6"/></g>',
    "geometria_oculta": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z M8 20 V46 L32 58 L56 46 V20 M32 32 V58" fill="none"'
                        ' stroke-dasharray="4 3" stroke-width="2.5"/>'
                        '<path d="M32 8 L56 20 M8 20 L32 32" stroke="#e5534b" stroke-width="3"/></g>',
    "objetos_ocultos": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z" fill="#dde3ef" fill-opacity="0.5" stroke-dasharray="4 3"/>'
                       '<path d="M8 20 L32 32 L32 58 L8 46 Z" fill="#b9c3d9" fill-opacity="0.5" stroke-dasharray="4 3"/>'
                       '<path d="M56 20 L32 32 L32 58 L56 46 Z" fill="#8ec5e8" fill-opacity="0.5" stroke-dasharray="4 3"/></g>',
    "ejes": _GR + '<g stroke-width="4"><line x1="32" y1="36" x2="58" y2="36" stroke="#e5534b"/>'
            '<line x1="32" y1="36" x2="32" y2="6" stroke="#5fa6d6"/><line x1="32" y1="36" x2="10" y2="58" stroke="#3fae5a"/></g>'
            '<circle cx="32" cy="36" r="4" fill="#2e3047"/></g>',
    # Volver al anillo (desde un submenú o la rueda): una flecha que vuelve.
    "volver": _GR + '<path d="M56 32 H14 M28 16 L12 32 L28 48" fill="none" stroke="#2e3047" stroke-width="11"/>'
              '<path d="M56 32 H14 M28 16 L12 32 L28 48" fill="none" stroke="#8ec5e8" stroke-width="5"/></g>',
    # Cerrar IngeTrazo: el botón de apagar.
    "cerrar_app": _GR + '<circle cx="32" cy="34" r="24" fill="#e5534b" stroke="#2e3047" stroke-width="3"/>'
                  '<path d="M20 24 A17 17 0 1 0 44 24" fill="none" stroke="#fff" stroke-width="5"/>'
                  '<line x1="32" y1="12" x2="32" y2="34" stroke="#fff" stroke-width="5"/></g>',
    # Preferencias: tres deslizadores.
    "preferencias": _G + '<rect x="8" y="10" width="48" height="44" rx="6" fill="#fff"/>'
                    '<g stroke-width="3"><line x1="16" y1="22" x2="48" y2="22"/><line x1="16" y1="32" x2="48" y2="32"/>'
                    '<line x1="16" y1="42" x2="48" y2="42"/></g>'
                    '<circle cx="24" cy="22" r="4.5" fill="#e5534b"/><circle cx="40" cy="32" r="4.5" fill="#8ec5e8"/>'
                    '<circle cx="30" cy="42" r="4.5" fill="#f6c54a"/></g>',
    # Muestrear: un cuentagotas (goma, tubo de cristal con líquido y punta) y su gota.
    "muestrear": _G + '<g transform="rotate(45 32 32)">'
                 '<ellipse cx="32" cy="11" rx="9" ry="7" fill="#f4a3a0"/>'
                 '<rect x="25" y="17" width="14" height="5" rx="1.5" fill="#2e3047"/>'
                 '<rect x="27" y="22" width="10" height="24" rx="2" fill="#dde3ef"/>'
                 '<rect x="29.5" y="31" width="5" height="13" fill="#8ec5e8" stroke="none"/>'
                 '<path d="M27 46 L32 60 L37 46 Z" fill="#b9c3d9"/></g>'
                 '<path d="M10 50 C5 57 7 62 11 62 C15 62 17 57 12 50 Z" fill="#8ec5e8"/></g>',
    # -- Subopciones de los botones (los chips de los submenús) --
    "m_esquina": _G + '<rect x="12" y="14" width="40" height="36" fill="#dde3ef"/>'
                 '<circle cx="12" cy="14" r="6" fill="#e5534b"/><circle cx="52" cy="50" r="4" fill="#2e3047"/></g>',
    "m_centro_rect": _G + '<rect x="12" y="14" width="40" height="36" fill="#dde3ef"/>'
                     '<circle cx="32" cy="32" r="6" fill="#e5534b"/><circle cx="52" cy="50" r="4" fill="#2e3047"/></g>',
    "m_lado_rect": _G + '<rect x="12" y="14" width="40" height="36" fill="#dde3ef"/>'
                   '<line x1="12" y1="50" x2="52" y2="50" stroke="#e5534b" stroke-width="7"/>'
                   '<circle cx="12" cy="50" r="4" fill="#2e3047"/><circle cx="52" cy="50" r="4" fill="#2e3047"/></g>',
    "m_girado": _G + '<g transform="rotate(-25 32 32)"><rect x="12" y="16" width="40" height="32" fill="#dde3ef"/>'
                '<line x1="12" y1="48" x2="52" y2="48" stroke="#e5534b" stroke-width="6"/></g></g>',
    "m_centro_poly": _G + '<polygon points="32,8 53,20 53,44 32,56 11,44 11,20" fill="#dde3ef"/>'
                     '<circle cx="32" cy="32" r="6" fill="#e5534b"/></g>',
    "m_lado_poly": _G + '<polygon points="32,8 53,20 53,44 32,56 11,44 11,20" fill="#dde3ef"/>'
                   '<line x1="11" y1="44" x2="32" y2="56" stroke="#e5534b" stroke-width="7"/></g>',
    "m_arco3": _G + '<path d="M8 48 A24 24 0 0 1 56 48" fill="none" stroke-width="5"/>'
               '<circle cx="8" cy="48" r="5" fill="#e5534b"/><circle cx="32" cy="24" r="5" fill="#e5534b"/>'
               '<circle cx="56" cy="48" r="5" fill="#e5534b"/></g>',
    "m_arco_centro": _G + '<path d="M10 44 A24 24 0 0 1 54 44" fill="none" stroke-width="5"/>'
                     '<path d="M10 44 L32 52 L54 44" fill="none" stroke="#8ec5e8" stroke-width="3"/>'
                     '<circle cx="32" cy="52" r="5" fill="#e5534b"/></g>',
    "m_porcion": _G + '<path d="M32 50 L10 36 A26 26 0 0 1 54 36 Z" fill="#f6c54a"/>'
                 '<circle cx="32" cy="50" r="4" fill="#e5534b"/></g>',
    "m_centro_circ": _G + '<circle cx="32" cy="32" r="22" fill="#dde3ef"/><circle cx="32" cy="32" r="6" fill="#e5534b"/></g>',
    "m_diametro": _G + '<circle cx="32" cy="32" r="22" fill="#dde3ef"/>'
                  '<line x1="10" y1="32" x2="54" y2="32" stroke="#e5534b" stroke-width="5"/>'
                  '<circle cx="10" cy="32" r="5" fill="#2e3047"/><circle cx="54" cy="32" r="5" fill="#2e3047"/></g>',
    "m_guia": _G + '<line x1="4" y1="52" x2="60" y2="12" stroke="#8ec5e8" stroke-width="4" stroke-dasharray="7 5"/>'
              '<circle cx="18" cy="42" r="5" fill="#e5534b"/><circle cx="46" cy="22" r="5" fill="#e5534b"/></g>',
    "m_equidist": _G + '<rect x="8" y="8" width="48" height="48" fill="none" stroke-width="4"/>'
                  '<rect x="20" y="20" width="24" height="24" fill="#8ec5e8" stroke-width="3"/></g>',
    "m_paralela": _G + '<line x1="10" y1="20" x2="54" y2="20" stroke-width="5"/>'
                  '<line x1="10" y1="44" x2="54" y2="44" stroke="#e5534b" stroke-width="5"/>'
                  '<path d="M32 24 V40 M27 35 L32 40 L37 35" fill="none" stroke-width="3"/></g>',
    "m_redondear": _G + '<path d="M10 10 H30 M10 10 V30" fill="none" stroke="#b9c3d9" stroke-width="3" stroke-dasharray="4 3"/>'
                   '<path d="M10 56 V30 A20 20 0 0 1 30 10 H56" fill="none" stroke-width="6"/>'
                   '<path d="M10 56 V30 A20 20 0 0 1 30 10 H56" fill="none" stroke="#f6c54a" stroke-width="2.5"/></g>',
    "m_ventana": _G + '<rect x="8" y="10" width="46" height="36" fill="#dde3ef" stroke-dasharray="6 4" stroke-width="3"/>'
                 '<path d="M38 34 L38 58 L44 52 L50 60 L54 57 L48 49 L56 49 Z" fill="#e5534b"/></g>',
    "m_lazo": _G + '<path d="M14 36 C8 18 56 10 54 30 C52 44 24 50 22 40 C20 32 40 30 40 40" fill="none" stroke-width="4"/>'
              '<circle cx="40" cy="42" r="5" fill="#e5534b"/><line x1="40" y1="46" x2="36" y2="60" stroke-width="4"/></g>',
    "m_nada": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z M8 20 V46 L32 58 L56 46 V20 M32 32 V58" fill="none"'
              ' stroke-dasharray="5 4" stroke-width="2.5"/></g>',
    "m_componente": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z" fill="#b5d4f4"/>'
                    '<path d="M8 20 L32 32 L32 58 L8 46 Z" fill="#5fa6d6"/>'
                    '<path d="M56 20 L32 32 L32 58 L56 46 Z" fill="#8ec5e8"/></g>',
    "m_cota": _G + '<line x1="8" y1="26" x2="8" y2="52" stroke-width="3"/><line x1="56" y1="26" x2="56" y2="52" stroke-width="3"/>'
              '<line x1="8" y1="40" x2="56" y2="40" stroke-width="3"/>'
              '<path d="M8 40 L16 35 V45 Z M56 40 L48 35 V45 Z" fill="#e5534b"/>'
              '<rect x="22" y="12" width="20" height="12" rx="2" fill="#f6c54a"/></g>',
    "m_con_nombre": _G + '<path d="M26 10 L48 21 L26 32 L4 21 Z" fill="#f3dcb2"/>'
                    '<path d="M4 21 L26 32 L26 56 L4 45 Z" fill="#d9b47e"/>'
                    '<path d="M48 21 L26 32 L26 56 L48 45 Z" fill="#e8c793"/>'
                    '<path d="M38 36 H60 V52 H38 L32 44 Z" fill="#f6c54a"/><circle cx="41" cy="44" r="2.5" fill="#2e3047"/></g>',
    "m_desagrupar": _G + '<path d="M30 6 L52 17 L30 28 L8 17 Z" fill="#f3dcb2"/>'
                    '<path d="M6 26 L26 36 L26 58 L6 48 Z" fill="#d9b47e"/>'
                    '<path d="M58 26 L38 36 L38 58 L58 48 Z" fill="#e8c793"/></g>',
    "m_empujar": _G + '<path d="M8 44 L32 56 L56 44 L32 32 Z" fill="#dde3ef"/>'
                 '<path d="M32 36 V8 M22 18 L32 8 L42 18" fill="none" stroke="#e5534b" stroke-width="6"/></g>',
    # Vértices: un triángulo con un vértice cogido por el cuadradito verde.
    "m_vertices": _G + '<path d="M10 54 L16 14 L48 26 Z" fill="#dde3ef"/>'
                  '<circle cx="10" cy="54" r="4" fill="#2e3047"/><circle cx="16" cy="14" r="4" fill="#2e3047"/>'
                  '<rect x="39" y="17" width="18" height="18" fill="#30d75b" stroke="#0d461c"/></g>',
    "m_referencia": _G + '<rect x="6" y="36" width="52" height="14" rx="2" fill="#f6c54a"/>'
                    '<g stroke-width="2"><line x1="16" y1="36" x2="16" y2="42"/><line x1="26" y1="36" x2="26" y2="44"/>'
                    '<line x1="36" y1="36" x2="36" y2="42"/><line x1="46" y1="36" x2="46" y2="44"/></g>'
                    '<path d="M10 20 H54 M18 13 L10 20 L18 27 M46 13 L54 20 L46 27" fill="none" stroke="#e5534b" stroke-width="4"/></g>',
    "m_rotar_copia": _GR + '<path d="M14 36 A18 18 0 1 1 30 50" fill="none" stroke="#2e3047" stroke-width="9"/>'
                     '<path d="M14 36 A18 18 0 1 1 30 50" fill="none" stroke="#f6c54a" stroke-width="4"/>'
                     '<g stroke="#2e3047" stroke-width="3"><polygon points="26,58 36,46 40,58" fill="#f6c54a"/>'
                     '<rect x="40" y="6" width="18" height="22" rx="3" fill="#fff"/>'
                     '<rect x="34" y="12" width="18" height="22" rx="3" fill="#dde3ef"/></g></g>',
    # -- Desplegables --
    "capas": _G + '<path d="M32 32 L58 44 L32 56 L6 44 Z" fill="#f6c54a"/>'
             '<path d="M32 21 L58 33 L32 45 L6 33 Z" fill="#b9c3d9"/>'
             '<path d="M32 10 L58 22 L32 34 L6 22 Z" fill="#8ec5e8"/>'
             '<line x1="16" y1="22" x2="28" y2="16.5" stroke="#fff" stroke-width="2.5"/></g>',
    "arbol": _G + '<path d="M17 20 V50 M17 32 H34 M17 50 H34" fill="none" stroke-width="3.5"/>'
             '<rect x="8" y="6" width="18" height="14" rx="2" fill="#f6c54a"/>'
             '<rect x="34" y="25" width="22" height="14" rx="2" fill="#8ec5e8"/>'
             '<rect x="34" y="43" width="22" height="14" rx="2" fill="#8ec5e8"/></g>',
    # -- Rueda de vistas: la cámara (con su abanico) y el plano de sección --
    "camara": _G + '<rect x="6" y="20" width="52" height="34" rx="6" fill="#dde3ef"/>'
              '<path d="M22 20 L26 12 H38 L42 20" fill="#b9c3d9"/>'
              '<circle cx="32" cy="37" r="11" fill="#8ec5e8"/><circle cx="32" cy="37" r="4" fill="#2e3047"/>'
              '<circle cx="50" cy="27" r="2.5" fill="#e5534b" stroke="none"/></g>',
    "situar_camara": _G + '<rect x="4" y="26" width="34" height="24" rx="4" fill="#dde3ef"/>'
                     '<circle cx="21" cy="38" r="7" fill="#8ec5e8"/>'
                     '<path d="M50 6 C42 6 38 12 38 18 C38 28 50 38 50 38 C50 38 62 28 62 18 C62 12 58 6 50 6 Z" fill="#e5534b"/>'
                     '<circle cx="50" cy="18" r="4" fill="#fff"/></g>',
    "caminar": _G + '<path d="M18 8 C10 8 8 20 10 30 C12 38 24 38 25 30 C26 20 26 8 18 8 Z" fill="#2e3047"/>'
               '<ellipse cx="18" cy="42" rx="6" ry="5" fill="#2e3047"/>'
               '<path d="M44 22 C36 22 34 34 36 44 C38 52 50 52 51 44 C52 34 52 22 44 22 Z" fill="#e5534b"/>'
               '<ellipse cx="44" cy="56" rx="6" ry="5" fill="#e5534b"/></g>',
    "mirar_alrededor": _G + '<path d="M8 32 Q32 12 56 32 Q32 52 8 32 Z" fill="#fff"/>'
                       '<circle cx="32" cy="32" r="8" fill="#5fa6d6"/><circle cx="32" cy="32" r="3" fill="#2e3047"/>'
                       '<path d="M10 52 A28 28 0 0 0 54 52" fill="none" stroke="#e5534b" stroke-width="4"/>'
                       '<path d="M48 46 L55 53 L46 57" fill="none" stroke="#e5534b" stroke-width="4"/></g>',
    "primera_persona": _G + '<circle cx="32" cy="18" r="11" fill="#dde3ef"/>'
                       '<path d="M12 58 C12 40 52 40 52 58 Z" fill="#b9c3d9"/>'
                       '<path d="M4 18 H22 M42 18 H60" stroke="#e5534b" stroke-width="3" stroke-dasharray="4 3"/></g>',
    "seccion": _G + '<path d="M32 8 L56 20 L32 32 L8 20 Z M8 20 V46 L32 58 L56 46 V20 M32 32 V58" fill="#dde3ef"/>'
               '<path d="M4 30 L36 14 L60 28 L28 44 Z" fill="#e5534b" fill-opacity="0.45" stroke="#c62828" stroke-width="2.5"/></g>',
}
ALIAS = {"ocultar_resto": "ocultar", "ocultar_uno": "ocultar", "empujar": "m_empujar",
         "nav": "arbol", "apagar": "cerrar_app"}

_RENDER: dict = {}
_CACHE: dict = {}
# Tema B (``Tema.glifos``): todo en silueta negra. Va la de ``_flotante``
# si la hay y, si no, el icono de colores pasado a negro con sus blancos.
# Lo pone la barra al cambiar de tema. Los temas C a N también: la silueta
# va en líneas y sombreado (``_flotante.PALETA``).
SILUETAS = False
# Los comandos del gestor de barras puestos en un hueco («mh:<clave>»): su
# QIcon y su nombre los da el gestor de barras (lo pone la barra).
EXTERNO = "mh:"
ICONO_EXTERNO = None                    # callable(clave) -> QIcon | None
NOMBRE_EXTERNO = None                   # callable(clave) -> str


def externo(clave) -> bool:
    return isinstance(clave, str) and clave.startswith(EXTERNO)


_EXTERNOS: dict = {}                   # clave -> QIcon (o None si no tiene)


def olvidar_externos() -> None:
    """Tras cambiar los huecos (o los iconos del gestor de barras)."""
    _EXTERNOS.clear()
    for clave in [k for k in _CACHE if externo(k[0])]:
        del _CACHE[clave]


def _qicono_externo(clave):
    if clave in _EXTERNOS:
        return _EXTERNOS[clave]
    if not callable(ICONO_EXTERNO):
        return None                          # aún sin el gestor de barras: no se recuerda
    try:
        icono = ICONO_EXTERNO(clave)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo pedir el icono de %s", clave)
        icono = None
    icono = icono if icono is not None and not icono.isNull() else None
    _EXTERNOS[clave] = icono
    return icono


def letra(painter, clave, c: QPointF, tam: float, tinta: QColor | None = None) -> None:
    """Un comando sin icono: su inicial en un cuadrito."""
    nombre = ""
    if callable(NOMBRE_EXTERNO):
        try:
            nombre = NOMBRE_EXTERNO(clave) or ""
        except Exception:  # noqa: BLE001
            nombre = ""
    nombre = nombre or clave[len(EXTERNO):].split(":", 1)[-1]
    inicial = next((ch for ch in nombre if ch.isalnum()), "?").upper()
    lado = tam * 0.8
    caja = QRectF(c.x() - lado / 2.0, c.y() - lado / 2.0, lado, lado)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(tinta) if tinta is not None else QColor(40, 40, 38)
    painter.setPen(QPen(color, max(1.0, tam / 14.0)))
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRoundedRect(caja, lado * 0.2, lado * 0.2)
    f = QFont(painter.font())
    f.setPixelSize(max(6, int(lado * 0.62)))
    f.setBold(True)
    painter.setFont(f)
    painter.drawText(caja, Qt.AlignCenter, inicial)
    painter.restore()


def tiene(clave) -> bool:
    return ALIAS.get(clave, clave) in SVG


def _renderer(nombre):
    r = _RENDER.get(nombre)
    if r is None:
        from PySide6.QtSvg import QSvgRenderer
        texto = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                 + SVG[nombre] + '</svg>')
        r = _RENDER[nombre] = QSvgRenderer(QByteArray(texto.encode("utf-8")))
    return r


def _apagar(img: QImage) -> QImage:
    """El icono en gris claro (botón desactivado), con el mismo alfa."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            g = int(150 + 0.35 * (0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue()))
            img.setPixelColor(x, y, QColor(g, g, g, c.alpha()))
    return img


def _silueta(img: QImage, tinta: QColor) -> QImage:
    """El icono en silueta de ``tinta``: lo blanco sigue blanco y lo demás
    (contorno y colores) pasa a ``tinta``, con el mismo alfa."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            luz = 0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue()
            t = max(0.0, min(1.0, (luz - 235.0) / 15.0))   # 1: blanco
            img.setPixelColor(x, y, QColor(
                int(tinta.red() + (255 - tinta.red()) * t),
                int(tinta.green() + (255 - tinta.green()) * t),
                int(tinta.blue() + (255 - tinta.blue()) * t), c.alpha()))
    return img


def _imagen(nombre, px: int, apagado: bool, tinta: QColor | None = None) -> QImage:
    """El icono a ``px`` píxeles con su halo blanco alrededor (ya incluido);
    con ``tinta``, en silueta de ese color."""
    clave = (nombre, px, apagado, tinta.rgba() if tinta is not None else None)
    img = _CACHE.get(clave)
    if img is not None:
        return img
    icono = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    icono.fill(Qt.transparent)
    p = QPainter(icono)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if externo(nombre):
        # El icono de IngeTrazo (o de la extensión) con el estilo del anillo.
        fuente = _qicono_externo(nombre)
        if fuente is not None:
            p.drawImage(QRectF(0, 0, px, px), fuente.pixmap(px, px).toImage())
    else:
        _renderer(nombre).render(p, QRectF(0, 0, px, px))
    p.end()
    if tinta is not None:
        icono = _silueta(icono, tinta)
    elif apagado:
        icono = _apagar(icono)
    silueta = QImage(icono.convertToFormat(QImage.Format_ARGB32_Premultiplied))
    p = QPainter(silueta)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(silueta.rect(), QColor(255, 255, 255))
    p.end()
    halo = max(1.0, px * 0.055)
    borde = int(math.ceil(halo))
    img = QImage(px + 2 * borde, px + 2 * borde, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    for k in range(12):
        a = k / 12.0 * 2.0 * math.pi
        p.drawImage(QPointF(borde + halo * math.cos(a), borde + halo * math.sin(a)), silueta)
    p.drawImage(QPointF(borde, borde), icono)
    p.end()
    _CACHE[clave] = img
    return img


def qicono(clave):
    """Un QIcon de ``clave`` (para las barras de herramientas), o None."""
    nombre = ALIAS.get(clave, clave)
    if nombre not in SVG:
        return None
    from PySide6.QtGui import QIcon, QPixmap
    icono = QIcon()
    for lado in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(lado, lado)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _renderer(nombre).render(p, QRectF(0, 0, lado, lado))
        p.end()
        icono.addPixmap(pm)
    return icono


def pintar(painter, clave, c: QPointF, tam: float = 22.0, apagado: bool = False,
           tinta: QColor | None = None) -> bool:
    """Dibuja el icono ``clave`` centrado en ``c`` (``tam`` px del pintor).
    Devuelve False si no hay icono (o falla): entonces va la silueta. Con
    ``SILUETAS`` (tema B), en silueta de ``tinta`` (negro, o gris si está
    ``apagado``)."""
    nombre = ALIAS.get(clave, clave)
    if SILUETAS:
        from . import _flotante
        if tinta is None:
            tinta = _flotante.GRIS if apagado else _flotante.NEGRO
        if not externo(clave) and _flotante.silueta(painter, clave, c, tinta, tam / 24.0):
            return True
        if _flotante.PALETA is not None and QColor(tinta) == _flotante.NEGRO:
            # Temas de color: sin silueta propia, el icono pasado al color de
            # las líneas en vez de a negro.
            tinta = _flotante.color_linea(painter, c)
    else:
        tinta = None
    if externo(clave):
        if _qicono_externo(clave) is None:
            return False                     # sin icono: la inicial
    elif nombre not in SVG:
        return False
    try:
        t = painter.worldTransform()
        escala = math.hypot(t.m11(), t.m12()) or 1.0
        dev = painter.device()
        dpr = float(dev.devicePixelRatioF()) if dev is not None else 1.0
        px = max(8, int(round(tam * escala * dpr)))
        img = _imagen(nombre, px, apagado, tinta)
        lado = tam * img.width() / float(px)
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(QRectF(c.x() - lado / 2.0, c.y() - lado / 2.0, lado, lado), img)
        painter.restore()
        return True
    except Exception:  # noqa: BLE001 — nunca rompe la barra
        log.exception("no se pudo pintar el icono %s", clave)
        return False

# SPDX-License-Identifier: GPL-3.0-or-later
"""La mitad de abajo del anillo de Rosco LT: modificar lo seleccionado. Está
siempre a la vista, debajo del cursor (la de arriba es la de dibujar).

    arco de fuera ... Suprimir · Agrupar · Cortar · Copiar · Invertir cara
    arco de dentro .. Desplazar · Escalar · Simetría · Rotar (los de la barra de modificar)

Los del arco de dentro activan las herramientas como la barra de modificar, con sus
submenús (mover · copia · alinear · empujar/tirar; libre · por referencia;
sin copia · con copia); la barra sigue mientras la herramienta espera su
primer punto. Agrupar abre su submenú: grupo, con nombre, componente,
desagrupar.
Pegados debajo del arco, tres botoncitos: Opciones, Ocultar y Bloquear. Con
Seleccionar y algo seleccionado, en lugar del buscador, un extracto de las
propiedades de lo seleccionado (un clic abre Info de entidad).

La selección múltiple: un clic añade lo que hay debajo y, si ya estaba
seleccionado, lo quita; un clic en el vacío deja la selección vacía. La
ventana y el lazo añaden.

Y en el Seleccionar de IngeTrazo, sin nada seleccionado (Opciones): un clic
en el vacío abre la barra de dibujo y un doble clic repite el último comando.
"""
from __future__ import annotations

from ._idioma import _tr
import dataclasses
import logging

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog

from . import _interruptor

log = logging.getLogger("ingetrazo.plugins.rosco_lt.anillo")

# De izquierda a derecha, como se leen debajo del cursor.
BANDA = ("suprimir", "agrupar", "cortar", "copiar", "invertir")
SEMI = ("move", "scale", "flip", "rotate")
AGRUPAR = ("grupo", "con nombre", "componente", "desagrupar")
# Los botoncitos pegados debajo del arco: ángulo (0 = derecha, 270 = abajo).
CHICOS = {"opciones": 250.0, "ocultar": 270.0, "bloquear": 290.0}
NOMBRES = {"move": "Desplazar: mover · copia · alinear · empujar/tirar · vértices",
           "scale": "Escalar: libre · por referencia", "flip": "Simetría",
           "rotate": "Rotar: sin copia · con copia",
           "suprimir": "Suprimir la selección", "ocultar": "Ocultar la selección",
           "agrupar": "Crear: grupo · con nombre · componente · desagrupar",
           "invertir": "Invertir cara (las caras seleccionadas)",
           "cortar": "Cortar", "copiar": "Copiar",
           "bloquear": "Bloquear / desbloquear (grupos y componentes)",
           "opciones": "Opciones: clic y doble clic en vacío",
           "propiedades": "Abrir Info de entidad"}
OPCIONES = (("doble_repite", "Doble clic en vacío: repetir el último comando"),
            ("clic_barra_dibujo", "Clic en vacío: abrir la barra"),
            ("doble_cierra", "Doble clic rápido con la barra a la vista: cerrarla"))
# Tras cada orden de la barra (salvo Seleccionar) queda Seleccionar y la barra
# no vuelve hasta un clic en el vacío o una selección.
TRAS_ORDEN = (("esconder_tras", "Esconder la barra tras cada orden (salvo Seleccionar)"),)
# Mantener pulsado un botón de la barra (o arrastrar con él pulsado).
PULSACION = (("pulsacion_ver", "Esconder la barra para ver el modelo mientras se pulsa o se arrastra"),)
# Tras el primer punto, además de la ventanita de medidas, el dictado de Windows.
DICTADO = (("dictado_dibujo", "Órdenes de dibujo: dictar la medida tras el primer punto"),
           ("dictado_edicion", "Órdenes de edición (desplazar, rotar, escalar…): "
                               "dictar la medida tras el primer punto"))
APAGADAS_DE_SERIE = frozenset(clave for clave, _texto in DICTADO)
_TECLAS = Qt.ShiftModifier | Qt.ControlModifier


# ---- Opciones (se recuerdan) -----------------------------------------------------

def _ajustes() -> QSettings:
    from ._ajustes import ajustes
    return ajustes()


def opcion(clave: str) -> bool:
    valor = _ajustes().value(f"seleccionar/{clave}", clave not in APAGADAS_DE_SERIE)
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true")
    return bool(valor)


def poner_opcion(clave: str, activa: bool) -> None:
    _ajustes().setValue(f"seleccionar/{clave}", bool(activa))


# Cómo salen los submenús de las órdenes: rectángulo o rosco (``_rosco``).
SUBMENUS = (("rect", "Rectangulares"), ("radial", "Radiales (en rosco)"))


def forma_submenus() -> str:
    valor = str(_ajustes().value("anillo/submenus", "rect") or "rect")
    return valor if valor in dict(SUBMENUS) else "rect"


def poner_forma_submenus(forma: str) -> None:
    _ajustes().setValue("anillo/submenus", forma)


# Distancia en horizontal del puntero al submenú (rectángulo o rosco), en px.
DISTANCIA_DEF, DISTANCIA_MIN, DISTANCIA_MAX = 28, 0, 150


def distancia_submenu() -> int:
    try:
        valor = int(float(_ajustes().value("anillo/distancia_submenu", DISTANCIA_DEF)))
    except (TypeError, ValueError):
        valor = DISTANCIA_DEF
    return max(DISTANCIA_MIN, min(DISTANCIA_MAX, valor))


def poner_distancia_submenu(px: int) -> None:
    _ajustes().setValue("anillo/distancia_submenu", int(px))


# Dónde sale el submenú: a la derecha del puntero o centrado bajo él.
SITIOS_SUBMENU = (("derecha", "A la derecha"), ("centro", "Centrado bajo el cursor"))


def sitio_submenu() -> str:
    valor = str(_ajustes().value("anillo/sitio_submenu", "derecha") or "derecha")
    return valor if valor in dict(SITIOS_SUBMENU) else "derecha"


def poner_sitio_submenu(sitio: str) -> None:
    _ajustes().setValue("anillo/sitio_submenu", sitio)


# Tamaño del rosco de submenús (Radiales), en %.
ESCALA_ROSCO_DEF, ESCALA_ROSCO_MIN, ESCALA_ROSCO_MAX = 100, 60, 150


def escala_rosco() -> int:
    try:
        valor = int(float(_ajustes().value("anillo/escala_rosco", ESCALA_ROSCO_DEF)))
    except (TypeError, ValueError):
        valor = ESCALA_ROSCO_DEF
    return max(ESCALA_ROSCO_MIN, min(ESCALA_ROSCO_MAX, valor))


def poner_escala_rosco(pct: int) -> None:
    _ajustes().setValue("anillo/escala_rosco", int(pct))


class _VistaPrevia:
    """La vista previa de cada tema: una imagen de la barra con ese tema,
    al lado del menú, mientras el ratón está sobre su entrada."""

    def __init__(self, cadena, menu) -> None:
        from PySide6.QtWidgets import QLabel
        self.cadena = cadena
        self.menu = menu
        self.etiqueta = QLabel(_tr(None), Qt.ToolTip | Qt.FramelessWindowHint)
        self.etiqueta.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.etiqueta.setStyleSheet("QLabel { background: #fafaf8; border: 1px solid #d62222;"
                                    " border-radius: 6px; padding: 6px; }")
        self._imagenes: dict = {}

    def mostrar(self, accion) -> None:
        datos = accion.data() if accion is not None else None
        if not (isinstance(datos, tuple) and datos[0] == "tema"):
            self.etiqueta.hide()
            return
        clave = datos[1]
        pm = self._imagenes.get(clave)
        if pm is None:
            try:
                pm = self._imagenes[clave] = self.cadena.previsualizar(clave)
            except Exception:  # noqa: BLE001 — sin vista previa, el menú sigue
                log.exception("no se pudo previsualizar el tema %s", clave)
                self.etiqueta.hide()
                return
        self.etiqueta.setPixmap(pm)
        self.etiqueta.adjustSize()
        r = self.menu.actionGeometry(accion)
        pos = self.menu.mapToGlobal(r.topRight()) + QPoint(8, 0)
        pantalla = self.menu.screen().availableGeometry()
        if pos.x() + self.etiqueta.width() > pantalla.right():
            pos.setX(self.menu.mapToGlobal(r.topLeft()).x() - 8 - self.etiqueta.width())
        if pos.y() + self.etiqueta.height() > pantalla.bottom():
            pos.setY(max(pantalla.top(), pantalla.bottom() - self.etiqueta.height()))
        self.etiqueta.move(pos)
        self.etiqueta.show()

    def cerrar(self) -> None:
        self.etiqueta.hide()
        self.etiqueta.deleteLater()


def _accion_escala(cadena, menu):
    """Una barra deslizante dentro del menú: el tamaño de la barra (60–130 %).
    Se aplica al momento, con el menú abierto."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget, QWidgetAction
    from . import _temas
    caja = QWidget(menu)
    fila = QHBoxLayout(caja)
    fila.setContentsMargins(24, 4, 12, 4)
    etiqueta = QLabel("{0} %".format(round(cadena.escala * 100)))
    etiqueta.setMinimumWidth(40)
    barra = QSlider(Qt.Horizontal)
    barra.setRange(round(_temas.ESCALA_MIN * 100), round(_temas.ESCALA_MAX * 100))
    barra.setSingleStep(5)
    barra.setPageStep(10)
    barra.setValue(round(cadena.escala * 100))
    barra.setMinimumWidth(150)

    def cambiar(valor) -> None:
        etiqueta.setText("{0} %".format(valor))
        cadena.poner_escala(valor / 100.0)
    barra.valueChanged.connect(cambiar)
    fila.addWidget(barra, 1)
    fila.addWidget(etiqueta)
    accion = QWidgetAction(menu)
    accion.setDefaultWidget(caja)
    return accion


def _accion_distancia(cadena, menu):
    """La distancia del cursor al submenú (0–150 px), con su rótulo y una
    barra deslizante como la del tamaño; se aplica al momento."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget, QWidgetAction
    caja = QWidget(menu)
    columna = QVBoxLayout(caja)
    columna.setContentsMargins(24, 2, 12, 4)
    columna.setSpacing(2)
    columna.addWidget(QLabel(_tr("Distancia del cursor al submenú")))
    fila = QHBoxLayout()
    etiqueta = QLabel("{0} px".format(cadena.distancia_submenu))
    etiqueta.setMinimumWidth(40)
    barra = QSlider(Qt.Horizontal)
    barra.setRange(DISTANCIA_MIN, DISTANCIA_MAX)
    barra.setSingleStep(4)
    barra.setPageStep(10)
    barra.setValue(cadena.distancia_submenu)
    barra.setMinimumWidth(150)

    def cambiar(valor) -> None:
        etiqueta.setText("{0} px".format(valor))
        cadena.poner_distancia_submenu(valor)
    barra.valueChanged.connect(cambiar)
    fila.addWidget(barra, 1)
    fila.addWidget(etiqueta)
    columna.addLayout(fila)
    accion = QWidgetAction(menu)
    accion.setDefaultWidget(caja)
    return accion


def _accion_escala_rosco(cadena, menu):
    """El tamaño del rosco de submenús (60–150 %), con su rótulo; se aplica
    al momento. Con los submenús rectangulares sale en gris."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget, QWidgetAction
    caja = QWidget(menu)
    columna = QVBoxLayout(caja)
    columna.setContentsMargins(24, 2, 12, 4)
    columna.setSpacing(2)
    columna.addWidget(QLabel(_tr("Tamaño del rosco de submenús")))
    fila = QHBoxLayout()
    etiqueta = QLabel("{0} %".format(cadena.escala_rosco))
    etiqueta.setMinimumWidth(40)
    barra = QSlider(Qt.Horizontal)
    barra.setRange(ESCALA_ROSCO_MIN, ESCALA_ROSCO_MAX)
    barra.setSingleStep(5)
    barra.setPageStep(10)
    barra.setValue(cadena.escala_rosco)
    barra.setMinimumWidth(150)

    def cambiar(valor) -> None:
        valor = int(round(valor / 5.0)) * 5   # de 5 en 5
        etiqueta.setText("{0} %".format(valor))
        cadena.poner_escala_rosco(valor)
    barra.valueChanged.connect(cambiar)
    fila.addWidget(barra, 1)
    fila.addWidget(etiqueta)
    columna.addLayout(fila)
    caja.setEnabled(bool(getattr(cadena, "submenus_radiales", False)))
    accion = QWidgetAction(menu)
    accion.setDefaultWidget(caja)
    return accion


def menu_opciones(cadena, global_pos) -> None:
    from PySide6.QtGui import QActionGroup
    from PySide6.QtWidgets import QMenu
    from . import _temas
    m = QMenu(cadena.app.window)
    fijar = m.addAction(_tr("Fijar la barra aquí (chincheta)"))
    fijar.setCheckable(True)
    fijar.setChecked(bool(cadena.anclada))
    fijar.setData(("chincheta",))
    m.addSection(_tr("Con Seleccionar, sin nada seleccionado"))
    for clave, texto in OPCIONES:
        a = m.addAction(_tr(texto))
        a.setCheckable(True)
        a.setChecked(opcion(clave))
        a.setData(clave)
    m.addSection(_tr("Al terminar una orden"))
    for clave, texto in TRAS_ORDEN:
        a = m.addAction(_tr(texto))
        a.setCheckable(True)
        a.setChecked(opcion(clave))
        a.setData(clave)
    m.addSection(_tr("Mantener pulsado un botón"))
    for clave, texto in PULSACION:
        a = m.addAction(_tr(texto))
        a.setCheckable(True)
        a.setChecked(opcion(clave))
        a.setData(clave)
    m.addSection(_tr("Dictado de medidas"))
    for clave, texto in DICTADO:
        a = m.addAction(_tr(texto))
        a.setCheckable(True)
        a.setChecked(opcion(clave))
        a.setData(clave)
    m.addSection(_tr("Tamaño de la barra"))
    m.addAction(_tr(_accion_escala(cadena, m)))
    m.addSection(_tr("Submenús de las órdenes"))
    formas = QActionGroup(m)
    formas.setExclusive(True)
    actual = "radial" if getattr(cadena, "submenus_radiales", False) else "rect"
    for clave, texto in SUBMENUS:
        a = m.addAction(_tr(texto))
        a.setCheckable(True)
        a.setChecked(clave == actual)
        a.setData(("submenus", clave))
        formas.addAction(_tr(a))
    m.addAction(_tr(_accion_distancia(cadena, m)))
    m.addAction(_tr(_accion_escala_rosco(cadena, m)))
    # El tema, en un desplegable: una línea con el actual y, al pasar, la
    # lista de temas al lado (con la vista previa de cada uno).
    m.addSection(_tr("Aspecto"))
    temas = m.addMenu(_tr("Tema de la barra: {0}", _tr(cadena.tema.nombre)))
    temas.setToolTipsVisible(True)
    grupo = QActionGroup(temas)
    grupo.setExclusive(True)
    for t in _temas.TEMAS.values():
        a = temas.addAction(_tr(t.nombre))
        a.setCheckable(True)
        a.setChecked(t.clave == cadena.tema.clave)
        a.setToolTip(_tr(t.descripcion))
        a.setData(("tema", t.clave))
        grupo.addAction(_tr(a))
    # El idioma, cada uno en el suyo (para que se encuentre aunque no se entienda el actual).
    from . import _idioma
    nombres = dict(_idioma.IDIOMAS)
    lenguas = m.addMenu(_tr("Idioma: {0}", nombres[_idioma.actual()]))
    grupo_lengua = QActionGroup(lenguas)
    grupo_lengua.setExclusive(True)
    for codigo, nombre in _idioma.IDIOMAS:
        a = lenguas.addAction(nombre)
        a.setCheckable(True)
        a.setChecked(codigo == _idioma.actual())
        a.setData(("idioma", codigo))
        grupo_lengua.addAction(a)
    m.addSection(_tr("Configuración"))
    m.addAction(_tr("Exportar la configuración…")).setData(("exportar",))
    m.addAction(_tr("Importar una configuración…")).setData(("importar",))
    m.addSection("Rosco LT")
    apagar = m.addAction(_tr("Desactivar Rosco LT"))
    apagar.setToolTip(_tr("Lo apaga al momento. Para volver: el interruptor de la barra "
                      "«Rosco LT» o Extensiones ▸ Rosco LT."))
    apagar.setData(("desactivar",))
    vista = _VistaPrevia(cadena, temas)
    temas.hovered.connect(vista.mostrar)
    temas.aboutToHide.connect(lambda: vista.mostrar(None))
    m.aboutToHide.connect(vista.cerrar)
    elegida = m.exec(global_pos)
    cadena.tragar_clic()                    # el clic que la cerró no es del dibujo
    if elegida is None:
        return
    datos = elegida.data()
    if isinstance(datos, tuple) and datos[0] == "tema":
        cadena.poner_tema(datos[1])
    elif isinstance(datos, tuple) and datos[0] == "idioma":
        from . import _idioma
        _idioma.poner(datos[1])
        cadena.idioma_cambiado()
    elif isinstance(datos, tuple) and datos[0] == "submenus":
        poner_forma_submenus(datos[1])
        cadena.submenus_radiales = datos[1] == "radial"
        cadena.app.viewport.flash_status(_tr("Submenús: {0}.", elegida.text().lower()), 3000)
        cadena._sincronizar()
    elif isinstance(datos, tuple) and datos[0] == "chincheta":
        cadena._pulsar_chincheta(cadena.app.viewport, "chincheta")
    elif isinstance(datos, tuple) and datos[0] in ("exportar", "importar"):
        QTimer.singleShot(0, lambda: _configuracion(cadena, datos[0]))
    elif isinstance(datos, tuple) and datos[0] == "desactivar":
        interruptor = getattr(cadena.app.window, "_rosco_lt_interruptor", None)
        if interruptor is not None:
            # Fuera del clic de la barra, que aún se está atendiendo.
            QTimer.singleShot(0, interruptor.apagar)
    elif datos:
        poner_opcion(datos, elegida.isChecked())
        cadena.app.viewport.flash_status(
            _tr("{0}: {1}.", elegida.text(), _tr('sí') if elegida.isChecked() else _tr('no')), 3000)


def _configuracion(cadena, que: str) -> None:
    """Opciones ▸ Configuración: guardar todos los ajustes del rosco en un
    archivo, o cargarlos de uno (otro equipo, una copia)."""
    import os
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from . import _ajustes
    win = cadena.app.window
    carpeta = os.path.join(os.path.expanduser("~"), "Documents")
    filtro = _tr("Configuración de Rosco LT (*.json)")
    try:
        if que == "exportar":
            ruta, _f = QFileDialog.getSaveFileName(
                win, _tr("Exportar la configuración"),
                os.path.join(carpeta, "Rosco LT configuración.json"), filtro)
            if not ruta:
                return
            n = _ajustes.exportar(ruta)
            cadena.app.viewport.flash_status(_tr("Configuración exportada: {0} ajustes en {1}.", n, ruta), 6000)
        else:
            ruta, _f = QFileDialog.getOpenFileName(win, _tr("Importar una configuración"), carpeta, filtro)
            if not ruta:
                return
            n = _ajustes.importar(ruta)
            QMessageBox.information(
                win, _tr("Importar una configuración"),
                _tr("Configuración importada ({0} ajustes). Reinicia IngeTrazo para que se "
                    "aplique del todo.", n))
    except Exception as ex:  # noqa: BLE001
        log.exception("fallo al %s la configuración", que)
        QMessageBox.warning(win, _tr("Configuración"), _tr("No se pudo: {0}", ex))


# ---- Clic y doble clic en el vacío (Seleccionar de IngeTrazo) ------------------------

class ClicVacio:
    """Con el Seleccionar de IngeTrazo, un clic en el vacío (sin nada
    seleccionado) abre la barra de dibujo y un doble clic en el vacío (con o sin
    selección) repite el último comando. Para saber cuál de los dos es, el
    clic espera lo que dura un doble clic."""

    def __init__(self, cadena, tool) -> None:
        self.cadena = cadena
        self.tool = tool
        self.original = tool.on_click
        self._previa: list = []                 # la selección que quitó el primer clic
        self._dormida_al_clic = False           # la barra estaba dormida al hacer clic
        self.reloj = QTimer()
        self.reloj.setSingleShot(True)
        self.reloj.setInterval(QApplication.doubleClickInterval())
        self.reloj.timeout.connect(self._clic_solo)
        tool.on_click = self.on_click
        tool._clic_original = self.original    # sin esto (cerrar la barra de dibujo lo usa)

    def _vacio(self, ctx, con_seleccion=False) -> bool:
        vp = ctx.viewport
        scene = vp.scene
        if ctx.modifiers & (_TECLAS | Qt.AltModifier) or (scene.selection and not con_seleccion):
            return False
        x, y = ctx.screen.x(), ctx.screen.y()
        try:
            if self.tool._pick(vp, x, y) is not None:
                return False
            if scene.edit_group is not None:
                # Con un grupo abierto, dentro de su caja es «vacío» (abre el
                # rosco); fuera, el clic es el de IngeTrazo: cierra el grupo.
                dentro = getattr(vp, "edit_group_box_contains_pixel", None)
                return callable(dentro) and bool(dentro(x, y))
            return True
        except Exception:  # noqa: BLE001
            return False

    def on_click(self, ctx):
        if not _interruptor.ENCENDIDA:
            self.reloj.stop()
            return self.original(ctx)
        doble, clic = opcion("doble_repite"), opcion("clic_barra_dibujo")
        # Con algo seleccionado cuentan el doble clic (repetir) y, con la
        # barra dormida, el clic (la despierta con esa selección).
        self._dormida_al_clic = bool(getattr(self.cadena, "dormida", False))
        con_sel = doble or (clic and self._dormida_al_clic)
        if (doble or clic) and self._vacio(ctx, con_seleccion=con_sel):
            if self.reloj.isActive():            # el segundo clic: doble clic
                self.reloj.stop()
                if doble:
                    QTimer.singleShot(0, self._repetir)
                return None
            # El primer clic deselecciona, como siempre; si llega el segundo,
            # la selección vuelve antes de repetir (Mover otra vez lo mismo).
            self._previa = list(ctx.viewport.scene.selection)
            self.reloj.start()
        else:
            self.reloj.stop()
        return self.original(ctx)

    def doble(self) -> bool:
        """El doble clic, visto por el filtro del visor antes que nadie (el
        segundo clic puede no llegar a ``on_click``): si el primero fue en
        el vacío, repite la última orden y se traga el segundo."""
        if not self.reloj.isActive():
            return False
        self.reloj.stop()
        if opcion("doble_repite"):
            QTimer.singleShot(0, self._repetir)
        return True

    def _repetir(self) -> None:
        previa, self._previa = self._previa, []
        if previa:
            self.cadena.recuperar_seleccion(previa)
        if self.cadena.repetir_ultima():         # la última orden de la barra
            return
        repetir = getattr(self.cadena.app.window, "repeat_last_command", None)  # 0.5.8
        if callable(repetir):
            repetir()

    def _clic_solo(self) -> None:
        previa, self._previa = self._previa, []
        vp = self.cadena.app.viewport
        if previa:
            # Había selección: con la barra dormida, vuelve la barra con lo
            # seleccionado; con la barra a la vista, el clic solo deselecciona.
            if (_interruptor.ENCENDIDA and opcion("clic_barra_dibujo") and self._dormida_al_clic
                    and vp.active_tool is self.tool and not vp.scene.selection):
                self.cadena.despertar(previa)
            return
        if (_interruptor.ENCENDIDA and opcion("clic_barra_dibujo") and vp.active_tool is self.tool
                and not vp.scene.selection):
            self.cadena.activar()


def hacer_vacio(cadena, tool) -> None:
    if tool is None or getattr(tool, "_rosco_lt_vacio", None) is not None:
        return
    tool._rosco_lt_vacio = ClicVacio(cadena, tool)


# ---- El extracto de propiedades -------------------------------------------------

def resumen(viewport) -> tuple:
    """Dos renglones: qué es (y su capa) y sus medidas."""
    from core.units import fmt_len
    from ._capas import capa_de_seleccion
    scene = viewport.scene
    sel = list(scene.selection)
    grupos = [e for e in sel if callable(getattr(e, "is_component", None))]
    caras = [e for e in sel if hasattr(e, "vertices") and hasattr(e, "attrs")]
    aristas = [e for e in sel if hasattr(e, "a") and hasattr(e, "b")]
    if len(sel) == 1 and grupos:
        g = grupos[0]
        tipo = _tr("Componente" if g.is_component() else "Grupo")
        linea = "{0} «{1}»".format(tipo, getattr(g, "name", "") or _tr("sin nombre"))
    else:
        partes = []
        for n, uno, varios in ((len(grupos), "grupo", "grupos"), (len(caras), "cara", "caras"),
                               (len(aristas), "arista", "aristas")):
            if n:
                partes.append("{0} {1}".format(n, _tr(uno if n == 1 else varios)))
        otros = len(sel) - len(grupos) - len(caras) - len(aristas)
        if otros > 0:
            partes.append(_tr("{0} otros", otros))
        linea = " · ".join(partes) or _tr("Nada seleccionado")
    capa = capa_de_seleccion(scene)
    linea += " · " + (_tr("capa {0}", capa) if capa else _tr("varias capas"))
    medidas = ""
    try:
        lo, hi = scene.selection_bounds()
        if lo is not None:
            d = hi - lo
            medidas = " × ".join(fmt_len(abs(v)) for v in (d.x(), d.y(), d.z()))
    except Exception:  # noqa: BLE001
        pass
    area = 0.0
    for f in caras:
        a = getattr(f, "area", None)
        try:
            area += float(a() if callable(a) else a or 0.0)
        except Exception:  # noqa: BLE001
            pass
    if area > 0.0:
        medidas += f" · {area:.2f} m²".replace(".", ",")
    return linea, medidas or "—"


def abrir_info(cadena) -> None:
    """Info de entidad: el panel Propiedades de IngeTrazo, al frente."""
    win = cadena.app.window
    tray = getattr(win, "tray", None)                  # interno de 0.5.8
    if tray is None:
        return
    mostrar = getattr(win, "set_tray_shown", None)
    if callable(mostrar):
        mostrar(tray, True)
    else:
        tray.show()
    tray.raise_()


# ---- Selección múltiple ------------------------------------------------------------

def clic_multiple(tool, original):
    """``on_click`` de Seleccionar: sin teclas, un clic sobre algo alterna
    (añade o quita, como Mayús); en el vacío, vacía la selección."""
    def on_click(ctx):
        if _interruptor.ENCENDIDA and not (ctx.modifiers & _TECLAS):
            try:
                debajo = tool._pick(ctx.viewport, ctx.screen.x(), ctx.screen.y())
            except Exception:  # noqa: BLE001
                debajo = None
            if debajo is not None:
                ctx = dataclasses.replace(ctx, modifiers=ctx.modifiers | Qt.ShiftModifier)
        return original(ctx)
    return on_click


def caja_multiple(original):
    """``on_box_select``: sin teclas, la ventana añade a lo seleccionado."""
    def on_box_select(viewport, rect, crossing, additive=False, mode=None):
        if _interruptor.ENCENDIDA and mode in (None, "replace"):
            mode, additive = "add", True
        return original(viewport, rect, crossing, additive, mode=mode)
    return on_box_select


def hacer_multiple(tool) -> None:
    """Pone la selección múltiple en ``tool`` (una sola vez)."""
    if tool is None or getattr(tool, "_barra_dibujo_multiple", False):
        return
    tool.on_click = clic_multiple(tool, tool.on_click)
    tool.on_box_select = caja_multiple(tool.on_box_select)
    tool._barra_dibujo_multiple = True


def modo_lazo(modificadores) -> str:
    """El lazo de la barra de dibujo, como la ventana: sin teclas, añade."""
    from tools.select import selection_mode
    modo = selection_mode(modificadores)
    return "add" if modo == "replace" else modo


# ---- Las acciones -------------------------------------------------------------------

def _llamar(win, nombre) -> bool:
    fn = getattr(win, nombre, None)                      # interno de 0.5.8
    if callable(fn):
        fn()
        return True
    return False


def disparar_menu(win, textos) -> bool:
    """Lanza la acción de menú de IngeTrazo cuyo texto (sin «&» ni el
    atajo) es uno de ``textos`` (en español o en inglés)."""
    from PySide6.QtGui import QAction

    def limpio(t):
        return t.split("\t")[0].replace("&", "").strip().rstrip("…").rstrip(".").strip().lower()
    buscados = {limpio(t) for t in textos}
    for a in win.findChildren(QAction):
        texto = limpio(a.text())
        if texto in buscados and a.isEnabled():
            a.trigger()
            return True
    return False


INVERTIR = ("Invertir caras", "Reverse Faces", "Invertir cara", "Reverse Face")


def accion(app, viewport, clave) -> None:
    win = app.window
    if clave != "bloquear" and not viewport.scene.selection:
        viewport.flash_status(_tr("Selecciona primero algo."), 3000)
        return
    if clave == "suprimir":
        _llamar(win, "_on_delete_selection")
    elif clave == "ocultar":
        _llamar(win, "_on_hide")
    elif clave == "invertir":
        if not (_llamar(win, "_on_reverse_faces") or disparar_menu(win, INVERTIR)):
            viewport.flash_status(_tr("Invertir cara: selecciona alguna cara (Invertir caras "
                                  "de IngeTrazo no está disponible)."), 4000)
    elif clave == "cortar":
        viewport.cut_selection()
        viewport.flash_status(_tr("Selección cortada: Ctrl+V la pega."), 3000)
    elif clave == "copiar":
        viewport.copy_selection()
        viewport.flash_status(_tr("Selección copiada: Ctrl+V la pega."), 3000)
    elif clave == "bloquear":
        _bloquear(viewport)
    viewport.update()


def _bloquear(viewport) -> None:
    """El candado de IngeTrazo: bloquea los grupos y componentes
    seleccionados o, si alguno ya lo está, los desbloquea (un paso)."""
    grupos = [e for e in viewport.scene.selection if callable(getattr(e, "is_component", None))]
    if not grupos:
        viewport.flash_status(_tr("Solo se bloquean grupos y componentes."), 4000)
        return
    from core.history import LockCommand                    # interno de 0.5.8
    bloquear = not any(getattr(g, "locked", False) for g in grupos)
    viewport.history.execute(LockCommand(grupos, bloquear))
    viewport.notify_scene_changed()
    viewport.flash_status(_tr("{0} objeto(s) {1}(s). Ctrl+Z lo deshace.", len(grupos), _tr('bloqueado') if bloquear else _tr('desbloqueado')), 4000)


def agrupar(app, viewport, modo) -> None:
    win = app.window
    if not viewport.scene.selection:
        viewport.flash_status(_tr("Selecciona primero lo que quieres agrupar."), 3000)
        return
    if modo == "grupo":
        _llamar(win, "_on_make_group")
    elif modo == "componente":
        _llamar(win, "_on_make_component")
    elif modo == "desagrupar":
        _llamar(win, "_on_explode_group")
    elif modo == "con nombre":
        _grupo_con_nombre(app, viewport)
    viewport.notify_scene_changed()
    viewport.update()


def _grupo_con_nombre(app, viewport) -> None:
    """Como Crear grupo de IngeTrazo, pidiendo antes el nombre."""
    scene = viewport.scene
    if not scene.selection:
        viewport.flash_status(_tr("Selecciona primero lo que quieres agrupar."), 4000)
        return
    n = len(scene.groups) + 1
    nombre, ok = QInputDialog.getText(app.window, _tr("Grupo con nombre"),
                                      _tr("Nombre del grupo:"), text=_tr("Grupo {0}", n))
    if not ok:
        return
    nombre = nombre.strip() or _tr("Grupo {0}", n)
    antes = {id(g) for g in scene.groups}
    _llamar(app.window, "_on_make_group")
    nuevos = [g for g in scene.groups if id(g) not in antes]
    if len(nuevos) == 1:
        nuevos[0].name = nombre
        viewport.flash_status(_tr("Grupo «{0}» creado.", nombre), 4000)

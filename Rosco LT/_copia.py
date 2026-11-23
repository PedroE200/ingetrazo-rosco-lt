# SPDX-License-Identifier: GPL-3.0-or-later
"""Guardar una copia del dibujo (botón «Copia» de la diana): una ventana con
el nombre ya puesto (el del dibujo + «copia» + fecha y hora), la carpeta y un
comentario opcional. La copia se escribe aparte: el dibujo abierto sigue
siendo el mismo archivo y no cambia.

El comentario va dentro de la copia (en los datos de Rosco del
documento); al abrirla, sale en un aviso abajo (``avisar_al_abrir``).
"""
from __future__ import annotations

from ._idioma import _tr
import datetime
import logging
import os
import re
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QToolButton, QVBoxLayout,
)

from ._tiempo import _ESTILO_BOTONES, _Arrastrable
from ._voz import con_microfono

from ._ajustes import registro

log = registro("anillo")
MORADO = "#8e5bd6"
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def carpeta_sin_titulo() -> Path:
    """Donde van las copias de un dibujo que aún no tiene nombre:
    Documentos\\IngeTrazo\\Copias."""
    from PySide6.QtCore import QStandardPaths
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(docs or os.path.expanduser("~")) / "IngeTrazo" / "Copias"


def nombre_propuesto(win) -> tuple[str, Path]:
    """(nombre sin extensión, carpeta) para la copia del dibujo abierto."""
    ruta = getattr(win, "_current_path", None)
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H.%M")
    if ruta:
        ruta = Path(ruta)
        return f"{ruta.stem} · copia {ahora}", ruta.parent
    doc = getattr(win, "_doc", None)
    nombre = getattr(doc, "display_name", None)
    try:
        nombre = nombre() if callable(nombre) else nombre
    except Exception:  # noqa: BLE001
        nombre = None
    base = _PROHIBIDOS.sub("", str(nombre or "Sin título")).rstrip(" *") or "Sin título"
    return f"{base} · copia {ahora}", carpeta_sin_titulo()


def guardar_copia(app, ruta: Path, comentario: str) -> dict:
    """Escribe la copia en ``ruta`` con el comentario dentro; el documento
    abierto queda como estaba."""
    import formats.igz as igz                                  # interno de 0.5.8
    from ._ajustes import CLAVE
    win, vp = app.window, app.viewport
    scene = vp.scene
    try:
        scene.camera_home = win._camera_dict(vp)               # como al Guardar
    except Exception:  # noqa: BLE001
        log.exception("no se pudo apuntar la cámara de la copia")
    datos = scene.plugin_data
    nada = object()
    antes = datos.get(CLAVE, nada)
    propio = dict(antes) if isinstance(antes, dict) else {}
    propio["copia"] = {"comentario": comentario,
                       "fecha": datetime.datetime.now().isoformat(timespec="minutes"),
                       "de": str(getattr(win, "_current_path", None) or "")}
    datos[CLAVE] = propio
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        return igz.save_scene(scene, ruta) or {}
    finally:
        if antes is nada:
            datos.pop(CLAVE, None)
        else:
            datos[CLAVE] = antes


def avisar_al_abrir(app) -> None:
    """Al abrir una copia con comentario, un aviso abajo (una vez por
    documento abierto)."""
    from ._ajustes import CLAVE
    visto = {"doc": None}

    def mirar():
        try:
            win = app.window
            doc = (id(app.viewport.scene), str(getattr(win, "_current_path", None)))
            if doc == visto["doc"]:
                return
            visto["doc"] = doc
            propio = app.viewport.scene.plugin_data.get(CLAVE)
            copia = propio.get("copia") if isinstance(propio, dict) else None
            texto = (copia or {}).get("comentario", "").strip()
            if texto:
                fecha = str(copia.get("fecha", "")).replace("T", " ")
                app.viewport.flash_status(_tr("Copia del {0}: {1}", fecha, texto), 15000)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo leer el comentario de la copia")
    app.on_document_changed(mirar)


class VentanaCopia(_Arrastrable, QDialog):
    def __init__(self, app) -> None:
        super().__init__(app.window, Qt.Dialog | Qt.FramelessWindowHint)
        self.app = app
        self.setObjectName("diana_copia")
        self.setStyleSheet(
            f"QDialog#diana_copia {{ background: #ffffff; border: 1.5px solid #d62222; "
            f"border-radius: 10px; }}"
            "QDialog#diana_copia QLabel { color: #111; background: transparent; }"
            "QLabel#rotulo { color: #5f5e5a; }"
            "QLabel#aviso { color: #c62828; }"
            "QLineEdit, QPlainTextEdit { background: #fff; color: #111; border: 1px solid #cfccc5; "
            "border-radius: 4px; padding: 4px 6px; }"
            "QLineEdit#carpeta { color: #555; }"
            + _ESTILO_BOTONES
            + f"QPushButton#prim {{ background: {MORADO}; border-color: #6d43b0; }}"
            + "QPushButton#prim:hover { background: #a174e0; }")
        nombre, self.carpeta = nombre_propuesto(app.window)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 14)
        lay.setSpacing(4)
        cabeza = QHBoxLayout()
        icono = QLabel("⧉")
        icono.setFixedSize(QSize(26, 26))
        icono.setAlignment(Qt.AlignCenter)
        icono.setStyleSheet(f"background: {MORADO}; color: #fff; border-radius: 6px; font-size: 14pt;")
        cabeza.addWidget(icono)
        titulo = QLabel(_tr("Guardar una copia del dibujo"))
        f = titulo.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1.0)
        titulo.setFont(f)
        cabeza.addWidget(titulo, 1)
        cerrar = QToolButton()
        cerrar.setText("✕")
        cerrar.setAutoRaise(True)
        cerrar.setStyleSheet("QToolButton { color: #111; border: none; } QToolButton:hover "
                             "{ background: #fadede; border-radius: 4px; }")
        cerrar.clicked.connect(self.reject)
        cabeza.addWidget(cerrar)
        lay.addLayout(cabeza)
        lay.addSpacing(6)
        lay.addWidget(self._rotulo(_tr("Nombre de la copia")))
        fila = QHBoxLayout()
        self.nombre = QLineEdit(nombre)
        self.nombre.textChanged.connect(lambda _t: self.aviso.setText(""))
        con_microfono(self.nombre)
        fila.addWidget(self.nombre, 1)
        fila.addWidget(self._rotulo(".igz"))
        lay.addLayout(fila)
        lay.addWidget(self._rotulo(_tr("Carpeta")))
        fila = QHBoxLayout()
        self.ruta = QLineEdit(str(self.carpeta))
        self.ruta.setObjectName("carpeta")
        self.ruta.setReadOnly(True)
        fila.addWidget(self.ruta, 1)
        cambiar = QPushButton(_tr("Cambiar…"))
        cambiar.clicked.connect(self._cambiar_carpeta)
        fila.addWidget(cambiar)
        lay.addLayout(fila)
        lay.addWidget(self._rotulo(_tr("Comentario (opcional)")))
        self.comentario = QPlainTextEdit()
        self.comentario.setPlaceholderText(_tr("Por qué guardas esta copia…"))
        self.comentario.setFixedHeight(64)
        con_microfono(self.comentario)
        lay.addWidget(self.comentario)
        self.aviso = QLabel("")
        self.aviso.setObjectName("aviso")
        self.aviso.setWordWrap(True)
        lay.addWidget(self.aviso)
        pie = QHBoxLayout()
        pie.addStretch(1)
        cancelar = QPushButton(_tr("Cancelar"))
        cancelar.clicked.connect(self.reject)
        pie.addWidget(cancelar)
        guardar = QPushButton(_tr("Guardar copia"))
        guardar.setObjectName("prim")
        guardar.setDefault(True)                 # Intro guarda (también desde el nombre)
        guardar.clicked.connect(self._guardar)
        pie.addWidget(guardar)
        lay.addLayout(pie)
        self.setFixedWidth(440)
        self.adjustSize()
        self.nombre.selectAll()

    @staticmethod
    def _rotulo(texto) -> QLabel:
        r = QLabel(texto)
        r.setObjectName("rotulo")
        return r

    def mostrar(self) -> None:
        centro = self.app.window.frameGeometry().center()
        self.move(centro - QPoint(self.width() // 2, self.height() // 2))
        self.nombre.setFocus()
        self.exec()

    def _cambiar_carpeta(self) -> None:
        nueva = QFileDialog.getExistingDirectory(self, _tr("Carpeta de la copia"), str(self.carpeta))
        if nueva:
            self.carpeta = Path(nueva)
            self.ruta.setText(str(self.carpeta))

    def _guardar(self) -> None:
        nombre = self.nombre.text().strip()
        if nombre.lower().endswith(".igz"):
            nombre = nombre[:-4].rstrip()
        if not nombre:
            self.aviso.setText(_tr("Ponle un nombre a la copia."))
            return
        if _PROHIBIDOS.search(nombre):
            self.aviso.setText(_tr('El nombre no puede llevar  < > : " / \\ | ? *'))
            return
        ruta = self.carpeta / f"{nombre}.igz"
        if ruta.exists():
            r = QMessageBox.question(self, _tr("Guardar una copia"),
                                     _tr("Ya hay un archivo «{0}» en esa carpeta.\n¿Reemplazarlo?", ruta.name))
            if r != QMessageBox.Yes:
                return
        abierto = getattr(self.app.window, "_current_path", None)
        if abierto and Path(abierto).resolve() == ruta.resolve():
            self.aviso.setText(_tr("Ese es el dibujo abierto: elige otro nombre para la copia."))
            return
        try:
            guardar_copia(self.app, ruta, self.comentario.toPlainText().strip())
        except Exception as exc:  # noqa: BLE001
            log.exception("no se pudo guardar la copia")
            self.aviso.setText(_tr("No se pudo guardar la copia: {0}", exc))
            return
        self.app.viewport.flash_status(_tr("Copia guardada: {0}", ruta.name), 6000)
        self.accept()

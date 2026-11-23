# SPDX-License-Identifier: GPL-3.0-or-later
"""Reiniciar (pieza de Rosco) — cierra y vuelve a abrir IngeTrazo con un
clic.

Pensado para desarrollar extensiones: IngeTrazo solo escanea los plugins al
arrancar, así que cada cambio pide un reinicio.

1. Cierra la ventana como el botón ✕: si hay cambios sin guardar, IngeTrazo
   pregunta si guardar; «Cancelar» anula el reinicio.
2. Un proceso auxiliar oculto espera a que este IngeTrazo termine del todo
   y lo vuelve a lanzar.
3. Si el documento tenía archivo (o se acaba de guardar), se reabre.

Se lanza desde la barra de herramientas «Rosco» (icono de flecha
circular), desde Extensiones ▸ Rosco ▸ Reiniciar IngeTrazo o con
Ctrl+Alt+R (si el atajo está libre).
"""
from __future__ import annotations

from ._ajustes import atributo

from ._idioma import _tr
import logging
import os
import subprocess
import sys

from PySide6.QtCore import QByteArray, QPointF, QProcess, QRectF, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

log = logging.getLogger("ingetrazo.plugins.reiniciar")

ACCENT = "#f37329"
_ICONO_SVG = os.path.join(os.path.dirname(__file__), "icons", "reiniciar.svg")

# ---- Idiomas --------------------------------------------------------------------

_TEXTS = {
    "es": {
        "Restart IngeTrazo": "Reiniciar IngeTrazo",
        "Close and reopen IngeTrazo (asks to save first).":
            "Cierra y vuelve a abrir IngeTrazo (antes pregunta si guardar).",
        "Restart cancelled.": "Reinicio cancelado.",
        "Could not restart: {err}": "No se pudo reiniciar: {err}",
    },
}


def _t(text: str, **kw) -> str:
    es = _TEXTS["es"].get(text, text)
    return _tr(es).format(**kw) if kw else _tr(es)


# ---- Reinicio ---------------------------------------------------------------------

# Espera a que termine el IngeTrazo actual (como mucho 60 s) y lo relanza.
# Todo llega por variables de entorno: así no hay que escapar rutas con espacios.
_AUXILIAR = (
    "Wait-Process -Id $env:IGZ_RESTART_PID -Timeout 60 -ErrorAction SilentlyContinue;"
    "Start-Sleep -Milliseconds 400;"
    "if ($env:IGZ_RESTART_ARGS) {"
    " Start-Process -FilePath $env:IGZ_RESTART_EXE -ArgumentList $env:IGZ_RESTART_ARGS"
    "} else { Start-Process -FilePath $env:IGZ_RESTART_EXE }"
)


def _orden(documento: str | None) -> tuple[str, list[str]]:
    """Ejecutable y argumentos para volver a abrir IngeTrazo."""
    if getattr(sys, "frozen", False):          # ingetrazo.exe (PyInstaller)
        exe, args = sys.executable, []
    else:                                      # desde el código fuente
        exe, args = sys.executable, [os.path.abspath(sys.argv[0])]
    if documento and os.path.isfile(documento):
        args.append(documento)                 # ingetrazo.exe "%1" abre el archivo
    return exe, args


def _entorno(exe: str, args: list[str]) -> dict:
    env = dict(os.environ)
    # Sin esto, el ejecutable de PyInstaller relanzado se creería hijo de este
    # proceso y reutilizaría su entorno de arranque.
    for clave in list(env):
        if clave.startswith("_PYI_") or clave == "_MEIPASS2":
            del env[clave]
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["IGZ_RESTART_PID"] = str(os.getpid())
    env["IGZ_RESTART_EXE"] = exe
    env["IGZ_RESTART_ARGS"] = subprocess.list2cmdline(args)
    return env


def _lanzar_auxiliar(exe: str, args: list[str]) -> None:
    env = _entorno(exe, args)
    if sys.platform == "win32":
        flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                 "-Command", _AUXILIAR],
                env=env, creationflags=flags, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return
        except OSError:
            log.exception("PowerShell no disponible; relanzo sin esperar")
    else:
        try:
            subprocess.Popen(
                ["/bin/sh", "-c",
                 'while kill -0 "$IGZ_RESTART_PID" 2>/dev/null; do sleep 0.2; done;'
                 ' exec "$IGZ_RESTART_EXE" "$@"', "reiniciar", *args],
                env=env, start_new_session=True, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return
        except OSError:
            log.exception("/bin/sh no disponible; relanzo sin esperar")
    # Último recurso: lanzarlo ya (puede abrirse antes de que este termine).
    if not QProcess.startDetached(exe, args):
        raise RuntimeError(exe)


def reiniciar(app) -> None:
    win = app.window
    # close() pasa por el closeEvent de IngeTrazo: pregunta si guardar y guarda
    # la posición de las barras. Devuelve False si el usuario cancela.
    if not win.close():
        app.viewport.flash_status(_tr(_t("Restart cancelled.")), 4000)
        return
    # Se lee después de cerrar: «Guardar como» en el aviso pudo darle ruta.
    documento = getattr(win, "_current_path", None)
    try:
        exe, args = _orden(str(documento) if documento else None)
        _lanzar_auxiliar(exe, args)
    except Exception as err:  # noqa: BLE001
        log.exception("no se pudo lanzar el reinicio")
        win.show()
        app.viewport.flash_status(_tr(_t("Could not restart: {err}", err=err)), 8000)
        return
    log.info("reiniciando IngeTrazo (documento: %s)", documento)
    QApplication.quit()


# ---- Icono y barra de herramientas ------------------------------------------------

def _icono_barra(window) -> QIcon:
    """El botón de la barra «Rosco»: la flecha en baldosa (``_baldosa``);
    si falla, la de siempre."""
    try:
        from . import _baldosa
        with open(_ICONO_SVG, encoding="utf-8") as f:
            texto = f.read().replace("currentColor", "#000000")
        return _baldosa.icono(lambda px: _baldosa.svg(texto, px))
    except Exception:  # noqa: BLE001 — queda el icono de siempre
        log.exception("no se pudo hacer el botón en baldosa")
        return _icono(window)


def _icono(window) -> QIcon:
    """La flecha de ``icons/reiniciar.svg``, con sus trazos (``currentColor``)
    en el color de texto del tema. Si el SVG falla, la misma dibujada a mano."""
    tinta = window.palette().windowText().color()
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
        log.exception("no se pudo cargar icons/reiniciar.svg")
    return _icono_a_mano(tinta)


def _icono_a_mano(tinta) -> QIcon:
    """La flecha del SVG con QPainter (viewBox 48 → 64 px)."""
    k = 64.0 / 48.0
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    disco = QColor(ACCENT)
    disco.setAlphaF(0.45)
    p.setBrush(QBrush(disco))
    p.drawEllipse(QPointF(24 * k, 25 * k), 9 * k, 9 * k)
    p.setPen(QPen(tinta, 3 * k, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    # Anillo de radio 14 abierto arriba a la derecha (de 90° a 40°, en grados Qt).
    p.drawArc(QRectF(10 * k, 11 * k, 28 * k, 28 * k), 90 * 16, 310 * 16)
    p.drawPolyline([QPointF(22 * k, 6 * k), QPointF(27 * k, 11 * k),
                    QPointF(22 * k, 16 * k)])
    p.end()
    return QIcon(pm)


# ---- Instalación (la llama el setup de Rosco) ----------------------------------

def instalar(app) -> None:
    from ._barra import anadir
    from ._interruptor import apuntar, entrada
    titulo = _t("Restart IngeTrazo")
    tip = _t("Close and reopen IngeTrazo (asks to save first).")

    apuntar(app, entrada(app, "reiniciar", titulo, lambda: reiniciar(app), tip,
                         shortcut="Ctrl+Alt+R"), titulo)

    try:
        accion = QAction(_icono_barra(app.window), _tr(titulo), app.window)
        accion.setToolTip(_tr(tip))
        accion.setStatusTip(_tr(tip))
        accion.triggered.connect(lambda _checked=False: reiniciar(app))
        setattr(accion, atributo("siempre"), True)   # sigue en la barra con Rosco apagado
        anadir(app, accion)
    except Exception:  # noqa: BLE001 — el menú sigue funcionando
        log.exception("no se pudo poner el botón en la barra")

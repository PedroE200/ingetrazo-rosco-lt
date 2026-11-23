# SPDX-License-Identifier: GPL-3.0-or-later
"""Qué va en cada hueco de la barra (temas con rueda): las cuatro bandas del
anillo, los seis huecos de los lados (entre las dos mitades), los doce
botoncitos de alrededor, los seis botones del aro de la rueda y los cuatro
ojos.

Cada hueco guarda una clave: la de un botón propio de la barra («rect»,
«deshacer», «ocultar_uno»…), ``EXTERNO`` + la clave de un comando de
el gestor de barras (menús, barras, extensiones, comandos personales) o «» si
está vacío. Los ojos, además, pueden llevar «rueda» o «historial»
(se abren al pasar el ratón) o «texturas» (con un clic). Se guarda en los ajustes
(``_ajustes``) → «huecos/config» (JSON); «Por defecto» vuelve a la barra de
siempre."""
from __future__ import annotations

import json
import logging
import re

from PySide6.QtCore import QSettings

from ._ajustes import registro

log = registro()
from ._gestor import CLAVE_TEXTURAS_ANTES, PREFIJO_EXTERNO

EXTERNO = PREFIJO_EXTERNO              # comando del gestor de barras
VACIO = ""
# Las bandas, de izquierda a derecha en pantalla.
BANDAS = ("ai", "ae", "bi", "be")      # arriba dentro / fuera, abajo dentro / fuera
NOMBRE_GRUPO = {"ai": "Arriba · dentro", "ae": "Arriba · fuera",
                "bi": "Abajo · dentro", "be": "Abajo · fuera",
                "chicos": "Botoncitos", "aro": "Aro de la rueda", "ojos": "Ojos",
                "gajos": "Gajo de la rueda", "tri": "Triángulo de la rueda",
                "centro": "Centro de la rueda", "lados": "Huecos de los lados"}
NOMBRE_TRI = ("arriba", "derecha", "abajo", "izquierda")
NOMBRE_CENTRO = ("disco", "circulito")
LIMITES = {"ai": (1, 6), "ae": (1, 10), "bi": (1, 6), "be": (1, 10)}
OJOS = ("arriba", "derecha", "abajo", "izquierda")
SOLO_OJOS = ("rueda", "historial")   # se abren al pasar por el ojo
SOLO_EN_OJO = (*SOLO_OJOS, "texturas", "ayuda")   # no tienen icono para otros huecos
ARO_ANGULOS = (30.0, 150.0, 210.0, 234.0, 306.0, 330.0)   # a 126° va siempre «volver»
# Lo de la rueda (gajos, triángulos, centro y aro): una clave solo una vez.
RUEDA = ("gajos", "tri", "centro", "aro")
FIJOS = {"aro": len(ARO_ANGULOS), "gajos": 5, "tri": 4, "centro": 2,
         "lados": 7}                   # izquierda y derecha: encima del ojo, dentro, debajo (y el 2.º de dentro)
CLAVE_AJUSTE = "huecos/config"
CLAVE_CALC = "huecos/calc_puesta"       # la calculadora ya se puso una vez bajo Apagar
CLAVE_ESCALA = "huecos/escala_primero"  # Escalar ya pasó una vez delante de Desplazar
CLAVE_RUEDA = "huecos/rueda_233"        # la rueda ya cambió una vez a su reparto de la 2.33.0
CLAVE_OJO_ROJO = "huecos/ojo_rojo"      # «ocultar el resto» ya se puso una vez en el ojo rojo
BANDA_BI = ("suprimir", "flip", "scale", "rotate")   # abajo · dentro, de serie (2.36.1)
CLAVE_BOTONES = "huecos/botones_2361"    # el reparto de botones ya cambió una vez
CLAVE_BOTONES_2392 = "huecos/botones_2392"
CLAVE_GRUPOS = "huecos/grupos"         # los grupos de huecos, salvo la disposición de General (JSON)
CLAVE_ACTIVO = "huecos/activo"         # el id del grupo activo
ID_GENERAL = 0                         # General guarda su disposición en CLAVE_AJUSTE
MAX_JUEGOS = 8
MAX_NOMBRE = 24
COLORES_JUEGO = ("#2b63c8", "#d7781e", "#2f8f4e", "#9b3fb5",
                 "#c8352b", "#148c8c", "#7a6a2a", "#4a4a4a")


def clave_ojo(clave: str) -> str:
    """Lo que va en un ojo, al día: la ayuda de antes y el nombre antiguo de
    las texturas pasan a «texturas» (si esta edición la lleva; si no, la
    ayuda se queda en su ojo, que abre Opciones ▸ Ayuda, y las texturas se
    quitan)."""
    from . import _edicion
    if clave in ("ayuda", CLAVE_TEXTURAS_ANTES):
        if _edicion.con("texturas"):
            return "texturas"
        return "ayuda" if _edicion.con("panel_ayuda") else VACIO
    if clave == "texturas" and not _edicion.con("texturas"):
        return VACIO
    return clave


def externo(clave) -> bool:
    return isinstance(clave, str) and clave.startswith(EXTERNO)


def _entero(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def contenedor_valido(obj) -> bool:
    """Si ``obj`` (el JSON de los grupos, ya decodificado) se puede usar. Lo
    demás de cada grupo (huecos, nombre, color) se tolera al leerlo."""
    if not isinstance(obj, dict):
        return False
    juegos = obj.get("juegos")
    if not isinstance(juegos, list) or not juegos or len(juegos) > MAX_JUEGOS:
        return False
    if not all(isinstance(j, dict) and _entero(j.get("id")) for j in juegos):
        return False
    ids = [j["id"] for j in juegos]
    return len(set(ids)) == len(ids) and ID_GENERAL in ids


class Huecos:
    """La configuración de los huecos. ``defecto``: el reparto de siempre
    (bandas, «chicos» y «aro» como listas; «ojos» como dict). Cada cambio
    se guarda y llama a ``al_cambiar``."""

    def __init__(self, defecto: dict, angulos_chicos: tuple, al_cambiar=None, al_activar=None) -> None:
        self.defecto = json.loads(json.dumps(defecto))
        self.angulos_chicos = tuple(angulos_chicos)
        self.al_cambiar = al_cambiar
        self.al_activar = al_activar
        self._cargar_todo()

    @property
    def datos(self) -> dict:
        """La disposición del grupo activo."""
        juego = self._juego(self._id_activo)
        if self._id_activo == ID_GENERAL or juego is None:
            return self._general
        return juego["huecos"]

    # ---- guardar / cargar ----------------------------------------------------------
    @staticmethod
    def _ajustes() -> QSettings:
        from ._ajustes import ajustes
        return ajustes()

    def _cargar_todo(self) -> None:
        self._general = self._cargar_general()
        self._contenedor = self._leer_contenedor()
        self._id_activo = self._leer_activo()

    def _leer_contenedor(self):
        """Los grupos guardados, o None si no hay o no se pueden usar (entonces
        la clave no se toca: solo se apunta en el registro)."""
        texto = self._ajustes().value(CLAVE_GRUPOS, "")
        if not texto:
            return None
        try:
            contenedor = json.loads(texto)
        except (TypeError, ValueError):
            contenedor = None
        if not contenedor_valido(contenedor):
            log.error("grupos de huecos no válidos, se usa General: %r", texto)
            return None
        for juego in contenedor["juegos"]:
            if juego["id"] != ID_GENERAL:
                juego["huecos"] = self._normalizar(juego.get("huecos"))
        return contenedor

    def _leer_activo(self) -> int:
        try:
            id_juego = int(self._ajustes().value(CLAVE_ACTIVO, ID_GENERAL))
        except (TypeError, ValueError):
            return ID_GENERAL
        return id_juego if self._juego(id_juego) is not None else ID_GENERAL

    def _normalizar(self, guardado) -> dict:
        """Una disposición completa: lo de ``guardado`` que sea válido y, en
        lo demás, lo de serie."""
        if not isinstance(guardado, dict):
            guardado = {}
        datos = json.loads(json.dumps(self.defecto))
        for g in BANDAS:
            lista = guardado.get(g)
            lo, hi = LIMITES[g]
            if isinstance(lista, list) and lo <= len(lista) <= hi and all(isinstance(k, str) for k in lista):
                datos[g] = list(lista)
        for g, n in (("chicos", len(self.angulos_chicos)), *FIJOS.items()):
            lista = guardado.get(g)
            if isinstance(lista, list) and all(isinstance(k, str) for k in lista):
                datos[g] = (list(lista) + [VACIO] * n)[:n]
        ojos = guardado.get("ojos")
        if isinstance(ojos, dict):
            datos["ojos"] = {o: str(ojos.get(o, VACIO) or VACIO) for o in OJOS}
            # La ayuda pasó a Opciones (2.42.0): su ojo abre la biblioteca de
            # texturas (``texturas``, guardada antes con otro nombre).
            datos["ojos"] = {o: clave_ojo(k) for o, k in datos["ojos"].items()}
        return self._de_esta_edicion(datos)

    @staticmethod
    def _de_esta_edicion(datos) -> dict:
        """Lo guardado con claves de partes que esta edición no lleva se queda
        en blanco (sin error); los ojos, al día (``clave_ojo``)."""
        from . import _edicion
        for g, valor in datos.items():
            if isinstance(valor, list):
                datos[g] = [k if _edicion.clave(k) else VACIO for k in valor]
            elif isinstance(valor, dict):
                datos[g] = {o: (clave_ojo(k) if _edicion.clave(clave_ojo(k)) else VACIO)
                            for o, k in valor.items()}
        return datos

    def _cargar_general(self) -> dict:
        try:
            texto = self._ajustes().value(CLAVE_AJUSTE, "")
            guardado = json.loads(texto) if texto else {}
        except Exception:  # noqa: BLE001 — una configuración rota no rompe la barra
            log.exception("configuración de huecos ilegible: se usa la de siempre")
            guardado = {}
        if not isinstance(guardado, dict):
            guardado = {}
        datos = self._normalizar(guardado)
        self._quitar_menus(datos)
        self._escala_primero(datos)
        self._rueda_233(datos)
        self._botones_2361(datos)
        self._botones_2392(datos)
        self._ojo_rojo(datos)
        if isinstance(guardado.get("chicos"), list):
            self._poner_calculadora(datos)
            if "lados" not in guardado:
                self._estrenar_lados(datos)
        return datos

    def _estrenar_lados(self, datos) -> None:
        """Los huecos de los lados llegan en la 2.28.0 con Notas y el Reloj,
        que hasta entonces iban en dos botoncitos de abajo: a quien ya tenía
        los botoncitos guardados se le quitan de ahí (una vez: luego ya hay
        «lados» guardados)."""
        chicos = datos["chicos"]
        for clave in self.defecto.get("lados", ()):
            if clave and clave in chicos:
                chicos[chicos.index(clave)] = VACIO
        try:
            self._ajustes().setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el estreno de los huecos de los lados")

    def _poner_calculadora(self, datos) -> None:
        """La calculadora va de serie debajo de Apagar (2.24.0). A quien ya
        tenía los botoncitos guardados se le pone una sola vez, si ese hueco
        estaba vacío; si luego la quita, no vuelve."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_CALC, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_CALC, True)
        chicos, de_serie = datos["chicos"], self.defecto["chicos"]
        i = de_serie.index("calc") if "calc" in de_serie else -1
        if i < 0 or "calc" in chicos or i >= len(chicos) or chicos[i]:
            return
        chicos[i] = "calc"
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar la calculadora en los botoncitos")

    def _escala_primero(self, datos) -> None:
        """Escalar y Desplazar cambian de sitio (2.32.0): una sola vez, en la
        banda donde estén los dos con Desplazar delante; si luego se vuelven
        a cambiar a mano, se respeta."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_ESCALA, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_ESCALA, True)
        for g in BANDAS:
            lista = datos.get(g)
            if isinstance(lista, list) and "move" in lista and "scale" in lista:
                i, j = lista.index("move"), lista.index("scale")
                if i < j:
                    lista[i], lista[j] = "scale", "move"
                    try:
                        ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
                    except Exception:  # noqa: BLE001
                        log.exception("no se pudo guardar el cambio de Escalar y Desplazar")
                    return

    def _botones_2361(self, datos) -> None:
        """El reparto nuevo (2.36.1), una sola vez: el hueco de Suprimir se parte
        en Empujar y Desplazar; Suprimir pasa al sitio de Escalar, Simetría al de
        Desplazar y Escalar al de Simetría. Si se tocaron a mano, se respeta."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_BOTONES, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_BOTONES, True)
        bi, lados = datos["bi"], datos["lados"]
        if lados[1] == "suprimir" and not lados[6] and "empujar" not in lados and "move" not in lados:
            lados[1], lados[6] = "empujar", "move"
            if list(bi) == ["scale", "move", "flip", "rotate"]:
                datos["bi"] = ["suprimir", "flip", "scale", "rotate"]
            elif "move" in bi:
                bi[bi.index("move")] = "suprimir"
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el nuevo reparto de botones")

    def _botones_2392(self, datos) -> None:
        """El reparto de la 2.39.2, una sola vez: Empujar ocupa entero el hueco
        de dentro de la izquierda, Texto sube al sitio de Notas, Notas baja al
        del Reloj (que pasa dentro de las Tareas) y Desplazar va al sitio de
        Texto. Si los huecos se tocaron a mano, se respeta."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_BOTONES_2392, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_BOTONES_2392, True)
        if datos["lados"] == ["notas", "empujar", "tiempo", "guardar", "texto", "copia", "move"]:
            datos["lados"] = ["texto", "empujar", "notas", "guardar", "move", "copia", ""]
        # La rueda: el aro estrena los ejes arriba a la derecha y la cámara
        # arriba a la izquierda; el gajo de objetos ocultos pasa a ser el plano
        # de sección (objetos ocultos sube al aro).
        aro, gajos = datos["aro"], datos["gajos"]
        viejos = {"mostrar_todo", "geometria_oculta", "mostrar_ultimo", "ejes", "objetos_ocultos"}
        if "camara" not in aro and {k for k in aro if k} <= viejos:
            datos["aro"] = ["ejes", "camara", "geometria_oculta", "objetos_ocultos",
                            "mostrar_ultimo", "mostrar_todo"]
        if "objetos_ocultos" in gajos and "seccion" not in gajos:
            gajos[gajos.index("objetos_ocultos")] = "seccion"
        if "objetos_ocultos" in datos["aro"] and "objetos_ocultos" in gajos:
            gajos[gajos.index("objetos_ocultos")] = VACIO
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el reparto de la 2.39.2")

    def _rueda_233(self, datos) -> None:
        """La rueda cambia (2.33.0), una sola vez: fuera «ocultar lo
        seleccionado»; el gajo de «ocultar resto» pasa a objetos ocultos, y
        «mostrar último» va al hueco del aro donde estaban estos."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_RUEDA, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_RUEDA, True)
        aro, gajos = datos["aro"], datos["gajos"]
        if "ocultar_uno" in aro:
            aro[aro.index("ocultar_uno")] = VACIO
        if "ocultar_resto" in gajos and "objetos_ocultos" not in gajos:
            gajos[gajos.index("ocultar_resto")] = "objetos_ocultos"
        if "objetos_ocultos" in gajos and "objetos_ocultos" in aro:
            i = aro.index("objetos_ocultos")
            aro[i] = VACIO
            if "mostrar_ultimo" in aro:
                aro[aro.index("mostrar_ultimo")] = VACIO
                aro[i] = "mostrar_ultimo"
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el nuevo reparto de la rueda")

    def _ojo_rojo(self, datos) -> None:
        """«Ocultar el resto del modelo» va de serie en el ojo rojo (2.33.0):
        una sola vez, si ese ojo estaba vacío; si luego se quita, no vuelve."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_OJO_ROJO, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_OJO_ROJO, True)
        ojos = datos["ojos"]
        if ojos.get("abajo") or "ocultar_resto" in ojos.values():
            return
        ojos["abajo"] = "ocultar_resto"
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el ojo rojo")

    def _quitar_menus(self, datos) -> None:
        """El botón de menús se fundió con el de buscar (2.22.0): en su hueco
        de los botoncitos pasa el gestor de extensiones (el sitio de este
        queda libre); en cualquier otro hueco, se vacía."""
        cambiado = False
        for g, lista in datos.items():
            if not isinstance(lista, list) or "menus" not in lista:
                continue
            i = lista.index("menus")
            if g == "chicos":
                if "ext" in lista:
                    lista[lista.index("ext")] = VACIO
                lista[i] = "ext"
            else:
                lista[i] = VACIO
            cambiado = True
        if cambiado:
            try:
                self._ajustes().setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                log.exception("no se pudo guardar el cambio del botón de menús")

    def _guardar(self) -> None:
        try:
            if self._id_activo == ID_GENERAL:
                self._ajustes().setValue(CLAVE_AJUSTE, json.dumps(self.datos, ensure_ascii=False))
            else:
                self._guardar_grupos()
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar la configuración de huecos")
        if callable(self.al_cambiar):
            try:
                self.al_cambiar()
            except Exception:  # noqa: BLE001
                log.exception("fallo al aplicar la configuración de huecos")

    def _guardar_grupos(self) -> None:
        self._ajustes().setValue(CLAVE_GRUPOS, json.dumps(self._contenedor, ensure_ascii=False))

    def _avisar_activo(self) -> None:
        if callable(self.al_activar):
            try:
                self.al_activar()
            except Exception:  # noqa: BLE001
                log.exception("fallo al aplicar el grupo de huecos")

    # ---- los grupos -------------------------------------------------------------------
    def _juego(self, id_juego):
        """La entrada del grupo ``id_juego``, o None. Sin grupos guardados
        solo existe General, que aún no tiene entrada."""
        if self._contenedor is None:
            return {"id": ID_GENERAL, "nombre": ""} if id_juego == ID_GENERAL else None
        return next((j for j in self._contenedor["juegos"] if j["id"] == id_juego), None)

    def _asegurar_contenedor(self) -> dict:
        if self._contenedor is None:
            self._contenedor = {"siguiente_id": 1, "juegos": [
                {"id": ID_GENERAL, "nombre": "", "color": COLORES_JUEGO[0]}]}
        return self._contenedor

    @staticmethod
    def _color_de(juego, posicion: int) -> str:
        color = juego.get("color")
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return color
        return COLORES_JUEGO[posicion % len(COLORES_JUEGO)]

    def _poner_activo(self, id_juego: int) -> None:
        self._id_activo = id_juego
        try:
            self._ajustes().setValue(CLAVE_ACTIVO, id_juego)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar el grupo activo")
        log.info("grupo de huecos activo: %s", id_juego)

    @property
    def id_activo(self) -> int:
        return self._id_activo

    def n_juegos(self) -> int:
        return 1 if self._contenedor is None else len(self._contenedor["juegos"])

    def nombre_visible(self, id_juego) -> str:
        """El nombre tal como se ve. El de un grupo no se traduce nunca; solo
        el de General mientras no se haya renombrado."""
        juego = self._juego(id_juego)
        nombre = juego.get("nombre") if juego is not None else ""
        if isinstance(nombre, str) and nombre:
            return nombre
        if id_juego == ID_GENERAL:
            from ._idioma import _tr
            return _tr("General")
        return ""

    def juegos(self) -> list:
        """``[(id, nombre visible, color)]`` en el orden de los puntos."""
        if self._contenedor is None:
            return [(ID_GENERAL, self.nombre_visible(ID_GENERAL), COLORES_JUEGO[0])]
        return [(j["id"], self.nombre_visible(j["id"]), self._color_de(j, i))
                for i, j in enumerate(self._contenedor["juegos"])]

    def validar_nombre(self, nombre, id_propio=None):
        """None si ``nombre`` vale; si no, ``(plantilla sin traducir, argumentos)``."""
        limpio = (nombre or "").strip()
        if not limpio:
            return ("Escribe un nombre.", ())
        if len(limpio) > MAX_NOMBRE:
            return ("El nombre admite hasta {0} caracteres.", (MAX_NOMBRE,))
        clave = limpio.casefold()
        for id_juego, visible, _color in self.juegos():
            if id_juego != id_propio and visible.casefold() == clave:
                return ("Ese nombre ya existe.", ())
        return None

    def activar(self, id_juego) -> bool:
        """Pasa al grupo ``id_juego``. False si ya era el activo o no existe."""
        if id_juego == self._id_activo or self._juego(id_juego) is None:
            return False
        self._poner_activo(id_juego)
        self._avisar_activo()
        return True

    def nuevo(self, nombre):
        """Crea un grupo, copia del activo, y lo deja activo. Devuelve un motivo o None."""
        motivo = self.validar_nombre(nombre)
        if motivo is not None:
            return motivo
        if self.n_juegos() >= MAX_JUEGOS:
            return ("Ya hay {0} grupos, el máximo.", (MAX_JUEGOS,))
        disposicion = json.loads(json.dumps(self.datos))
        contenedor = self._asegurar_contenedor()
        juegos = contenedor["juegos"]
        siguiente = contenedor.get("siguiente_id")
        id_juego = max(siguiente if _entero(siguiente) else 0, max(j["id"] for j in juegos) + 1)
        usados = {self._color_de(j, i) for i, j in enumerate(juegos)}
        color = next((c for c in COLORES_JUEGO if c not in usados), COLORES_JUEGO[0])
        juegos.append({"id": id_juego, "nombre": nombre.strip(), "color": color, "huecos": disposicion})
        contenedor["siguiente_id"] = id_juego + 1
        self._guardar_grupos()
        self._poner_activo(id_juego)
        self._avisar_activo()
        return None

    def renombrar(self, id_juego, nombre):
        """Cambia el nombre de un grupo. Devuelve un motivo o None."""
        motivo = self.validar_nombre(nombre, id_juego)
        if motivo is not None:
            return motivo
        limpio = nombre.strip()
        if id_juego == ID_GENERAL:
            from ._idioma import _tr
            if limpio == _tr("General"):
                limpio = ""
        self._asegurar_contenedor()
        juego = self._juego(id_juego)
        if juego is None:
            return ("Ese grupo ya no existe.", ())
        juego["nombre"] = limpio
        self._guardar_grupos()
        self._avisar_activo()
        return None

    def borrar(self, id_juego) -> bool:
        """Elimina un grupo (General no se puede). Si era el activo, pasa a General."""
        juego = self._juego(id_juego)
        if id_juego == ID_GENERAL or juego is None:
            return False
        self._contenedor["juegos"].remove(juego)
        self._guardar_grupos()
        if id_juego == self._id_activo:
            self._poner_activo(ID_GENERAL)
        self._avisar_activo()
        return True

    def recargar(self) -> None:
        """Vuelve a leerlo todo, sin volcar lo que había en memoria (tras importar)."""
        self._cargar_todo()
        self._avisar_activo()

    # ---- lectura ---------------------------------------------------------------------
    def banda(self, g) -> tuple:
        return tuple(self.datos[g])

    def chicos(self) -> list:
        return list(self.datos["chicos"])

    def aro(self) -> list:
        return list(self.datos["aro"])

    def lista(self, grupo) -> list:
        return list(self.datos[grupo])

    def ojos(self) -> dict:
        return dict(self.datos["ojos"])

    def ojo_de(self, funcion):
        """El ojo que lleva ``funcion`` («rueda», «historial»…), o None."""
        return next((o for o in OJOS if self.datos["ojos"].get(o) == funcion), None)

    def clave(self, grupo, i):
        if grupo == "ojos":
            return self.datos["ojos"].get(i, VACIO)
        lista = self.datos.get(grupo, [])
        return lista[i] if 0 <= i < len(lista) else VACIO

    def todas(self) -> list:
        """Todas las claves puestas (para medir textos, por ejemplo)."""
        claves = [k for g in (*BANDAS, "chicos", "lados", *RUEDA) for k in self.datos[g]]
        claves += list(self.datos["ojos"].values())
        return [k for k in claves if k]

    # ---- cambios ---------------------------------------------------------------------
    def admite(self, grupo, clave) -> str:
        """«» si ``clave`` puede ir en ``grupo``; si no, por qué."""
        if clave in SOLO_EN_OJO and grupo != "ojos":
            return "La rueda, el historial y las texturas solo pueden ir en un ojo."
        return ""

    def poner(self, grupo, i, clave) -> str:
        """Pone ``clave`` en el hueco (o «» si va bien, o por qué no). En
        un mismo grupo una clave solo está una vez: si ya estaba en otro
        hueco, ese se queda vacío (es como moverla)."""
        motivo = self.admite(grupo, clave)
        if motivo:
            return motivo
        if grupo == "ojos":
            ojos = self.datos["ojos"]
            if clave:
                for o in OJOS:
                    if o != i and ojos.get(o) == clave:
                        ojos[o] = VACIO
            ojos[i] = clave
        else:
            lista = self.datos[grupo]
            if not 0 <= i < len(lista):
                return "Ese hueco no existe."
            if clave:
                # En la rueda, una clave solo en un sitio (gajo, triángulo,
                # centro o aro); en los demás grupos, una vez por grupo.
                for g in (RUEDA if grupo in RUEDA else (grupo,)):
                    otra = self.datos[g]
                    for j, k in enumerate(otra):
                        if k == clave and (g, j) != (grupo, i):
                            otra[j] = VACIO
            lista[i] = clave
        self._guardar()
        return ""

    def vaciar(self, grupo, i) -> None:
        self.poner(grupo, i, VACIO)

    def intercambiar(self, g1, i1, g2, i2) -> str:
        """Cambia de sitio dos huecos (arrastrar uno encima de otro)."""
        k1, k2 = self.clave(g1, i1), self.clave(g2, i2)
        for g, k in ((g2, k1), (g1, k2)):
            motivo = self.admite(g, k)
            if motivo:
                return motivo
        if g1 == g2:
            if g1 == "ojos":
                self.datos["ojos"][i1], self.datos["ojos"][i2] = k2, k1
            else:
                lista = self.datos[g1]
                lista[i1], lista[i2] = k2, k1
        else:
            self._poner_sin_guardar(g1, i1, k2)
            self._poner_sin_guardar(g2, i2, k1)
        self._guardar()
        return ""

    def _poner_sin_guardar(self, grupo, i, clave) -> None:
        if grupo == "ojos":
            self.datos["ojos"][i] = clave
            return
        lista = self.datos[grupo]
        if clave:
            for j, k in enumerate(lista):
                if j != i and k == clave:
                    lista[j] = VACIO
        lista[i] = clave

    def mas(self, grupo, i=None) -> bool:
        """Un hueco vacío más en la banda (en ``i`` o al final)."""
        if grupo not in BANDAS or len(self.datos[grupo]) >= LIMITES[grupo][1]:
            return False
        lista = self.datos[grupo]
        lista.insert(len(lista) if i is None else max(0, min(i, len(lista))), VACIO)
        self._guardar()
        return True

    def menos(self, grupo, i=None) -> bool:
        """Un hueco menos en la banda (el ``i`` o, si no, el último vacío o
        el último)."""
        if grupo not in BANDAS or len(self.datos[grupo]) <= LIMITES[grupo][0]:
            return False
        lista = self.datos[grupo]
        if i is None:
            vacios = [j for j, k in enumerate(lista) if not k]
            i = vacios[-1] if vacios else len(lista) - 1
        del lista[i]
        self._guardar()
        return True

    def por_defecto(self) -> None:
        """Vuelve a poner de serie el grupo activo."""
        de_serie = json.loads(json.dumps(self.defecto))
        if self._id_activo == ID_GENERAL:
            self._general = de_serie
        else:
            self._juego(self._id_activo)["huecos"] = de_serie
        self._guardar()

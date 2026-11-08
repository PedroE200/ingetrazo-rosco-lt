# SPDX-License-Identifier: GPL-3.0-or-later
"""Qué va en cada hueco de la barra (temas con rueda): las cuatro bandas del
anillo, los seis huecos de los lados (entre las dos mitades), los doce
botoncitos de alrededor, los seis botones del aro de la rueda y los cuatro
ojos.

Cada hueco guarda una clave: la de un botón propio de la barra («rect»,
«deshacer», «ocultar_uno»…), ``EXTERNO`` + la clave de un comando de
el gestor de barras (menús, barras, extensiones, comandos personales) o «» si
está vacío. Los ojos, además, pueden llevar «rueda», «historial» o
«ayuda» (se abren al pasar el ratón). Se guarda en los ajustes
(``_ajustes``) → «huecos/config» (JSON); «Por defecto» vuelve a la barra de
siempre."""
from __future__ import annotations

import json
import logging

from PySide6.QtCore import QSettings

log = logging.getLogger("ingetrazo.plugins.rosco_lt")

EXTERNO = "mh:"                        # comando del gestor de barras
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
SOLO_OJOS = ("rueda", "historial", "ayuda")   # se abren al pasar por el ojo
ARO_ANGULOS = (30.0, 150.0, 210.0, 234.0, 306.0, 330.0)   # a 126° va siempre «volver»
# Lo de la rueda (gajos, triángulos, centro y aro): una clave solo una vez.
RUEDA = ("gajos", "tri", "centro", "aro")
FIJOS = {"aro": len(ARO_ANGULOS), "gajos": 5, "tri": 4, "centro": 2,
         "lados": 7}                   # izquierda y derecha: encima del ojo, dentro, debajo (y el 2.º de dentro)
CLAVE_AJUSTE = "huecos/config"
CLAVE_AYUDA = "huecos/ayuda_puesta"     # la ayuda ya se puso una vez en el ojo verde
CLAVE_CALC = "huecos/calc_puesta"       # la calculadora ya se puso una vez bajo Apagar
CLAVE_ESCALA = "huecos/escala_primero"  # Escalar ya pasó una vez delante de Desplazar
CLAVE_RUEDA = "huecos/rueda_233"        # la rueda ya cambió una vez a su reparto de la 2.33.0
CLAVE_OJO_ROJO = "huecos/ojo_rojo"      # «ocultar el resto» ya se puso una vez en el ojo rojo
BANDA_BI = ("suprimir", "flip", "scale", "rotate")   # abajo · dentro, de serie (2.36.1)
CLAVE_BOTONES = "huecos/botones_2361"    # el reparto de botones ya cambió una vez
CLAVE_BOTONES_2392 = "huecos/botones_2392"


def externo(clave) -> bool:
    return isinstance(clave, str) and clave.startswith(EXTERNO)


class Huecos:
    """La configuración de los huecos. ``defecto``: el reparto de siempre
    (bandas, «chicos» y «aro» como listas; «ojos» como dict). Cada cambio
    se guarda y llama a ``al_cambiar``."""

    def __init__(self, defecto: dict, angulos_chicos: tuple, al_cambiar=None) -> None:
        self.defecto = json.loads(json.dumps(defecto))
        self.angulos_chicos = tuple(angulos_chicos)
        self.al_cambiar = al_cambiar
        self.datos = self._cargar()

    # ---- guardar / cargar ----------------------------------------------------------
    @staticmethod
    def _ajustes() -> QSettings:
        from ._ajustes import ajustes
        return ajustes()

    def _cargar(self) -> dict:
        datos = json.loads(json.dumps(self.defecto))
        try:
            texto = self._ajustes().value(CLAVE_AJUSTE, "")
            guardado = json.loads(texto) if texto else {}
        except Exception:  # noqa: BLE001 — una configuración rota no rompe la barra
            log.exception("configuración de huecos ilegible: se usa la de siempre")
            guardado = {}
        if not isinstance(guardado, dict):
            guardado = {}
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
            self._poner_ayuda(datos)
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

    def _poner_ayuda(self, datos) -> None:
        """La ayuda va de serie en el ojo de la derecha (el verde). A quien ya
        tenía los ojos guardados se le pone una sola vez, si ese ojo estaba
        vacío; si luego la quita, no vuelve."""
        ajustes = self._ajustes()
        if str(ajustes.value(CLAVE_AYUDA, "")).lower() in ("1", "true"):
            return
        ajustes.setValue(CLAVE_AYUDA, True)
        ojos = datos["ojos"]
        if "ayuda" in ojos.values() or ojos.get("derecha"):
            return
        ojos["derecha"] = "ayuda"
        try:
            ajustes.setValue(CLAVE_AJUSTE, json.dumps(datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar la ayuda en el ojo verde")

    def _guardar(self) -> None:
        try:
            self._ajustes().setValue(CLAVE_AJUSTE, json.dumps(self.datos, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("no se pudo guardar la configuración de huecos")
        if callable(self.al_cambiar):
            try:
                self.al_cambiar()
            except Exception:  # noqa: BLE001
                log.exception("fallo al aplicar la configuración de huecos")

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
        if clave in SOLO_OJOS and grupo != "ojos":
            return "La rueda, el historial y la ayuda solo pueden ir en un ojo."
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
        self.datos = json.loads(json.dumps(self.defecto))
        self._guardar()

# Multiempuje — pieza de la extensión Rosco

Empujar/tirar **varias caras a la vez**: dar grosor a superficies, extruir conjuntos de caras,
levantar tejados siguiendo sus paredes, redondear esquinas o empujar cada cara por su cuenta.

- **Un botón «Multiempuje»** en la barra (y una entrada en Extensiones ▸ Multiempuje): activa
  la herramienta y abre la pestaña lateral **Multiempuje**, donde está todo.
- Cursor propio (un cubo) con una pequeña marca de estado: **+** se conserva la original, **✓** el
  siguiente clic confirma, **⧉** la cara está en un grupo cerrado, **▭** eligiendo el plano
  destino, **➚** eligiendo la dirección.
- Trabaja sobre la geometría suelta y sobre **grupos y componentes** sin abrirlos: se pueden
  elegir caras sueltas y de varios grupos o componentes a la vez (las de grupos cerrados se
  marcan con su contorno) y un solo arrastre, o la distancia tecleada en el cajetín, las
  empuja todas en un único paso de deshacer. Vale con componentes movidos o girados.
- Cada empuje es **un paso de deshacer** (Ctrl+Z o Retroceso).

## La pestaña: tres movimientos y pocas opciones

| Movimiento (tecla) | Qué hace |
|---|---|
| **Juntas** (1) | La superficie sigue unida: los vértices se mueven en inglete y cada cara queda exactamente a la distancia. |
| **Una dirección** (2) | Todas las caras se desplazan en la misma dirección: normal de la cara, media del conjunto, eje X/Y/Z o una personalizada. |
| **Cada cara** (3) | Cada cara se empuja por separado según su propia normal. |

Debajo del movimiento van la **distancia** y el **acabado**: *Empujar* borra la cara original
(empujar/tirar clásico; hacia dentro de un sólido recorta sus caras laterales y, si llega a la
cara opuesta, abre un hueco pasante) o *Engrosar* la conserva (sólido cerrado). **Ctrl**
mantenido invierte el acabado.

**Opciones de «Juntas»**
- *Borde exterior*: **en inglete** (cada cara a su distancia), **siguiendo las caras vecinas**
  (los vértices del contorno resbalan por las aristas de las caras no elegidas: un tejado que
  crece sin salirse de las paredes) o **promediado con las caras vecinas**.
- *Redondear las aristas salientes* (tiras cilíndricas y esquinas esféricas), con el ángulo
  mínimo y los segmentos por 90°.

**Opciones de «Una dirección»**
- *Dirección*: **Normal de la cara**, **Media del conjunto** (extrusión compacta), **X / Y / Z**,
  **Personalizada**. **Elegir en el dibujo…**: pasa el ratón por una **arista** (su dirección),
  una **cara** o un **plano de sección** (su normal), una **guía** o un **eje** (su dirección);
  se dibuja la dirección y un clic la fija. Vale con caras y aristas de grupos cerrados.
  También se puede **teclear** (x ; y ; z).
- *Ejes del grupo abierto (locales)*: dentro de un componente o grupo girado, X, Y y Z son sus
  propios ejes (Tab durante el arrastre lo cambia).
- *Cara superior plana*: las caras superiores quedan en un plano perpendicular a la dirección.

**Opciones de «Cada cara»**: mantener unidos los triángulos que forman un cuadrilátero.

**Más opciones** (plegado): bordes nuevos (contorno, cuadrícula o ninguno), modo de selección
(superficie, individual, mismo material, todas las unidas; **Tab** lo cambia), plano destino
(*Elegir en el dibujo…*: las caras llegan hasta ese plano, sea cual sea la distancia), crear el
resultado en un grupo, **rematado** (la cara superior al % indicado; Una dirección y Cada cara),
**desmoldeo** (bordes inclinados; no actúa con borde «siguiendo las vecinas» ni con redondeo) y
**aleatorio** (cada cara, o cada bloque de caras unidas, multiplica la distancia por un factor
al azar entre mín y máx; ◀ ▶ cambian el patrón).

### A qué equivalen los siete modos de la versión 1.1

| Antes | Ahora |
|---|---|
| Engrosar | Juntas · acabado Engrosar |
| Conjunto | Juntas · acabado Empujar · borde en inglete |
| Redondeo | Juntas · Engrosar · ☑ redondear las aristas salientes |
| Seguir | Juntas · borde exterior «siguiendo las caras vecinas» |
| Vector | Una dirección · normal / X / Y / Z / personalizada |
| Extruir | Una dirección · «media del conjunto» |
| Normal | Cada cara |

## Ayudas con imagen

Al dejar el ratón medio segundo sobre una opción de la pestaña aparece una tarjeta con una
ilustración 3D «antes → después» (gris: lo que había; naranja claro: las caras elegidas;
naranja: el resultado) y una frase. Con los desplegables salen todas sus opciones en columna.
Las imágenes se calculan con el propio motor del plugin sobre una geometría de muestra, así
que enseñan exactamente lo que hace cada opción. La casilla «Mostrar ayudas con imagen…» de
la sección *Uso* las apaga.

## Uso

1. Pulsa el botón **Multiempuje** (o elige el movimiento en la pestaña, o teclas 1, 2, 3).
2. **Pasa el ratón** por una cara: se resalta (ella sola, su superficie, su material o todo lo
   unido, según el modo de selección) y ya está lista para empujar.
3. **Clic y arrastra** sobre ella: se empuja; al soltar se genera la geometría. No hace falta
   hacer clic antes. **Clic largo** (sin mover) = arrastre libre: mueve el ratón y confirma con
   otro clic.
4. Para empujar **varias caras a la vez**: con **Mayús** pulsada, pasa el ratón por las caras y
   se van añadiendo (sin clic); **Mayús + clic** quita una. Después arrastra sobre cualquiera de
   ellas. Un clic suelto sobre una cara sigue eligiéndola o quitándola.
5. Mientras arrastras puedes **teclear la distancia** y Enter. Con las caras elegidas y sin
   arrastrar, teclear una distancia y Enter también empuja (o el botón **Comenzar**, arriba del panel).
6. Justo después de un empuje, **cambiar cualquier opción de la pestaña** (o teclear otra
   distancia) **lo rehace** con los valores nuevos. **Retroceso** lo deshace y deja otra vez
   elegidas las caras originales. **Doble clic** sobre una cara repite el último empuje.
7. **Esc**: cancela el arrastre o la elección; otro Esc quita la selección; otro sube un nivel
   si hay un grupo abierto; otro vuelve a Seleccionar.

Teclas en «Una dirección»: **→** X, **←** Y, **↑** Z, **↓** normal (la misma flecha otra vez vuelve
a Normal).

## Grupos y componentes

- Al pasar el ratón por una cara de un grupo o componente cerrado, el cursor muestra la marca
  **⧉**. Al hacer **clic** (o clic y arrastrar), el grupo se abre solo, igual que con doble clic
  en Seleccionar, y la cara queda lista para empujar. Los grupos anidados se abren de un golpe.
- **Esc** (sin selección) o un **clic fuera** del grupo sube un nivel.
- Si es un **componente**, todas sus copias reciben el cambio al salir de él (regla de IngeTrazo).
- Los grupos bloqueados no se abren.

Las caras nuevas heredan material, color, textura y capa de la original; los bordes que
quedan en el plano de una cara vecina toman su material y se funden con ella. Las aristas
suaves de la superficie original pasan a la nueva y los bordes casi alineados (menos de 30°)
se suavizan.

Todos los campos de texto llevan un micrófono: pone el cursor en el campo y abre el dictado
del sistema (Win+H).

## Archivos

| Archivo | Contenido |
|---|---|
| `__init__.py` | `setup(app)`: crea el controlador una sola vez. |
| `_algo.py` | Motor geométrico (Python puro): bloques, dirección de cada vértice por modo, rematado, desmoldeo, aleatorio, plano destino, redondeos, bordes y orientación. |
| `_bridge.py` | Traducción malla de IngeTrazo ↔ motor, vista previa, aplicación en un paso de deshacer (fusión de coplanarias, recorte de caras vecinas, huecos pasantes), grupo nuevo y selección ampliada. |
| `_tool.py` | Herramienta interactiva: selección con Mayús, arrastre, grupos, plano destino, elección de dirección, cursor. |
| `_settings.py` | Opciones (QSettings `IngeTrazo/multiempuje`): movimiento + opciones → modo del motor. Migra las preferencias de la 1.1. |
| `_panel.py`, `_extension.py` | Pestaña lateral, botón de la barra, menú y controlador. |
| `_ilustra.py`, `_ayuda.py` | Ilustraciones 3D de las opciones (renderizador isométrico sobre el motor) y popups de ayuda al pasar el ratón. |
| `_icons.py`, `_voz.py`, `_i18n.py` | Iconos de cubo y cursor, micrófono (Win+H) y textos (español; inglés si IngeTrazo está en inglés). |

Los iconos de los siete modos de la 1.1 siguen en `_icons.py` y, como PNG, en la carpeta
`_iconos` del proyecto.

## Límites conocidos

- Las copias de un componente se actualizan al salir de él, no mientras se empuja dentro.
- Con muchas caras la vista previa solo dibuja las superiores (más de 6000 caras nuevas).
- Si al empujar una cara no plana resultan caras superiores alabeadas, se dividen en
  triángulos con la diagonal suavizada.
- El recorte al empujar hacia dentro se hace con las caras vecinas coplanarias del borde; en
  geometrías muy enrevesadas puede quedar algún borde solapado que conviene revisar.
- Si otra extensión sustituye el cursor del visor (por ejemplo un cursor «lápiz»), ese manda.

Licencia: GPL-3.0-or-later (como IngeTrazo).

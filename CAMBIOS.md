# Historial de cambios

Versionado semántico: **MAYOR.MENOR.PARCHE**.
- MAYOR: cambia el formato de datos o de reportes.
- MENOR: funciones nuevas.
- PARCHE: arreglos y ajustes.

Los **datos** (`datos/`) llevan su propia versión en `datos/datos.json`. Cada entrega dice si es de **programa** (hay que actualizar `programa/`) o **solo datos** (basta con reemplazar `datos/`).

## Programa 3.2.7 · Datos 1.2.5 (2026-11-14)
Tipo: **programa** (arreglo de la corrección de distancia de la 3.2.3).
- **Corrección de distancia equivocada en Strawberry:** el lector del HUD se quedó pegado en 3,66 km unos 5 s a 90 km/h; la 3.2.3 contaba lo recorrido desde la última vuelta (no desde que apareció ese valor), así que cuando volvió a leer bien (3,34 km) lo tomó por mal leído y usó 3,63 km. Con esa distancia no frenó antes del separador de vías (llegó a 89 con límite 65). Ahora:
  - lo recorrido se cuenta desde la primera vez que el HUD mostró el valor (si se queda pegado, no se reinicia);
  - el margen crece con lo recorrido (150 m + 10 %);
  - el dígito cambiado puede quedar a 100 m de lo esperado (en el puente se leyó «5,00» con el camión en 5,67).
  Probado con las lecturas de los dos viajes: en Strawberry no corrige nada; en el puente sigue corrigiendo 5,09 y 5,00.

## Programa 3.2.6 · Datos 1.2.5 (2026-11-14)
Tipo: **programa** (solo la ventana). La conducción y los datos no cambian.
- **«Empezar en» sigue la etapa:** mientras el autopiloto anda, el selector muestra la etapa en que va; al terminar el trabajo vuelve solo a «0 - Ir a cargar».
- **Se recuerda dónde quedó:** al detener o cerrar el programa se guardan la etapa y el recorrido del momento (el elegido o el que se reconoció solo). Al abrir de nuevo, «Empezar en» y «Recorrido» quedan como estaban, así no hay que cambiarlos a mano. Al terminar el trabajo se guarda «0» y «Automático».

## Programa 3.2.5 · Datos 1.2.5 (2026-11-14)
Tipo: **programa** (ventana y cómo se elige el recorrido). Los datos no cambian.
- **Elegir el recorrido a mano:** nuevo selector **«Recorrido»** junto a «Empezar en» (Automático, Granja 1, Granja 2, Globe Oil; la lista sale de `datos/rutas/`). Si activas a mitad de camino el recorrido no se puede reconocer por la distancia (en el viaje de las 08:00 empezó a 1,90 km, quedó «desconocido» y no usó ninguna regla en la ida ni en la vuelta). Al elegirlo:
  - se usa desde ya, sin reconocer por la distancia, con sus reglas en la ida y en la vuelta;
  - vale hasta que termine el trabajo; al volver a «ir a cargar» el selector pasa solo a «Automático»;
  - si la distancia no puede ser de ese recorrido (más que su distancia inicial), sale un aviso, pero se respeta la elección;
  - la ventana y el panel muestran el recorrido con «(elegido)».
- El aviso «No reconozco el recorrido» ahora dice que se puede elegir en «Recorrido».

## Programa 3.2.4 · Datos 1.2.5 (2026-11-14)
Tipo: **programa** (cambia la lógica del control de velocidad). Los datos no cambian.
- **Sin sube y baja de velocidad** (experimental, encendida: «Velocidad sin sube y baja»). En Banning (5,51–5,36 km, límite 40) la velocidad iba y venía cada 5–6 s entre ~24 y ~48 km/h (el velocímetro del juego lo confirma; pasaba igual en la 2.6 y la 2.7). El ciclo: se pasaba un poco, soltaba el acelerador del todo y daba un toque de freno (en GTA eso baja ~20 km/h), volvía a acelerar despacio, caía a 24, aceleraba a tope (0,6) y se volvía a pasar. Ahora, con límites bajos (reglas, curvas, esquinas):
  - cerca del objetivo el acelerador queda acotado alrededor del que mantiene la velocidad (no sube a tope por estar 5 km/h abajo);
  - si se pasa por poco (hasta 8 km/h) baja el acelerador a la mitad del de mantener, en vez de soltarlo;
  - si tiene que frenar con poco exceso (menos de 15 km/h), el toque es suave (0,15 en vez de 0,35);
  - tras soltar o frenar vuelve enseguida al acelerador de mantener.
  En una simulación con la respuesta medida en el viaje (≈7 km/h/s al acelerar, velocímetro ~1 s tarde) el vaivén pasa de 21–48 a 33–47 km/h (36–43 con menos retraso). Se puede apagar en Experimental.

## Programa 3.2.3 · Datos 1.2.5 (2026-11-14)
Tipo: **programa y datos**. Cambia la lógica de la lectura de distancia; el resto son reglas.
- **Distancia mal leída tras cargar:** en el puente de Elysian Island el HUD mostraba 5,69 → 5,66 km y el programa leyó «5,09» y «5,00» durante 16 s (el 6 se confundía con 0 sobre el fondo claro). El recorrido se reconoció igual (desde la 2.7.2 se prueba cambiando un dígito), pero la distancia seguía mal: no se aplicó la regla de entrada al puente (20 km/h, a la izquierda), entró a 36 km/h y chocó el poste a 5,67 km. Ahora:
  - si el recorrido se reconoce cambiando un dígito, la distancia pasa a ser la de la ruta menos lo recorrido;
  - una lectura que no cuadra con lo que el camión anduvo (más de 150 m) y que con UN dígito cambiado sí cuadra se toma como mal leída y se usa la distancia esperada (aviso «Distancia mal leída»). Los saltos reales del GPS no se tocan.
- **Datos, camino a cargar:** la regla queda en dos: 270–150 m (−2,5, abrir el giro antes de la esquina) y **150–115 m sin desplazamiento** (con −2,5 rozaba el remolque y el contenedor de la izquierda al entrar al patio). Las dos a 25 km/h.
- **Datos, fin del puente (5,64–5,60 km de Granja 1; vale también para Granja 2):** desplazamiento de −0,5 a **0** (rozaba el bloque de concreto de la izquierda).
- **Datos, esquina a la salida del puente (5,60–5,56 km):** velocidad de esquina de 28 a **24 km/h** (a 30 se abría fuera de la calle).

## Programa 3.2.2 · Datos 1.2.4 (2026-11-14)
Tipo: **programa y datos** (ajuste de valores; la lógica es la de la 3.2.1).
- **Programa:** `esquinas.frente_flecha_px` de 4,5 a **7**. En el video de la esquina de carga, con la esquina ya en la flecha, el programa la medía a 6,3–7,5 px del centro (no usa los primeros 13 px de la línea, la prolonga desde más adelante), así que con 4,5 todavía dudaba 0,5–1 s antes de girar. Si tenías el 4,5 de la 3.2.1 guardado, pasa solo a 7.
- **Datos, camino a cargar (común, 270–120 m):** máximo **25 km/h**. Llegaba a la esquina a 33 km/h, abría el giro y rozaba la grúa del puerto (en la 2.x, que partía ahí mismo, llegaba a 13–25 km/h).
- **Datos, Granja 2 (ida, 2,30–2,18 km):** vuelve la regla «Autopista: un poco a la izquierda (evitar que el GPS cambie la ruta)», −1,5, solo en esta ruta. Se había borrado en la 2.5.0 al compartir el tramo con Granja 1, y en el primer viaje de Granja 2 desde entonces la ruta del GPS cambió ahí y el camión chocó a 71 km/h. Granja 1 no cambia.

## Programa 3.2.1 · Datos 1.2.3 (2026-11-14)
Tipo: **programa** (cambia la lógica de las esquinas cerradas). Los datos no cambian.
- **Esquinas de 90° (seguía de largo):** cuando la esquina ya está bajo la flecha, el programa sigue recto hasta tenerla a 3 px o menos (o lo que diga la regla). Pero la línea del GPS nace en la **punta** de la flecha, unos 4,5 px por delante de su centro, así que esa distancia nunca bajaba del margen: el camión seguía recto hasta casi detenerse y recién giraba («bloqueado frente a la esquina»). Se vio en el video del camino a cargar (165 → 145 m sin girar, con la ruta ya a 90°), en Banning y en Davis. Ahora esa distancia se mide desde la punta (`esquinas.frente_flecha_px` = 4,5). Las reglas no cambian: sus márgenes (3 px, 1,5 px…) vuelven a medir lo que medían.
- **Elegir la flecha con zoom:** en «Calibrar todo», la tecla **F** abre el minimapa ampliado alrededor de la flecha; clic para poner el centro (se puede repetir), flechas del teclado para moverlo de a 1 px, ENTER para aceptar, ESC para cancelar.

## Programa 3.2.0 · Datos 1.2.3 (2026-11-14)
Tipo: **programa** (cambia la lógica de la cámara de carril). Los datos no cambian. Hay que **volver a calibrar el carril** si el trapecio toca el tablero o el limpiaparabrisas (ver abajo).
- **La amarilla se reconoce por su color.** De noche, con las luces, la doble amarilla casi no es más clara que el asfalto (que se ve azulado), así que antes casi no se marcaba. Ahora se busca por cuánto más amarilla es que su entorno. También cuenta el **borde rojo** de la calzada (se puede apagar: `carril.bordillo_rojo`).
- **Solo cuentan las líneas rectas.** La vista desde arriba se divide en 4 franjas y una línea vale solo si aparece en casi todas, en la misma columna. Lo que va en diagonal (el limpiaparabrisas, basura, sombras) ya no se toma por una línea.
- **Una sola línea también sirve, con menos fuerza.** Antes, con una sola línea la confianza quedaba en 0,5 y la cámara no dirigía nunca. Ahora una línea recta y clara da hasta 0,65 (0,70 si es la amarilla) y la cámara corrige **a la mitad de fuerza** desde 0,55 (`conf_min_una_linea`, `peso_una_linea`). Con las dos líneas sigue igual que antes (desde 0,75, fuerza entera).
- **La vista desde arriba dice qué ve:** «izq: amarilla / línea / no se ve» y lo mismo a la derecha, en la calibración y en la pestaña Conducir. La amarilla se pinta amarilla y lo demás naranjo.
- **Cómo calibrar el carril:** en una recta, centrado, con los lados del trapecio **sobre** las líneas (izquierda sobre la amarilla, derecha sobre el borde de tu carril), el borde de abajo un poco por encima del tablero y sin que la esquina derecha toque el limpiaparabrisas. En la vista desde arriba las líneas deben caer sobre las verdes.

## Programa 3.1.0 · Datos 1.2.3 (2026-11-14)
Tipo: **solo programa** (interfaz, avisos y actualizaciones). No cambia la conducción, la calibración ni los datos.
- **Ventana reorganizada:** los botones de todos los días (Iniciar, Detener, Activar / desactivar, Saltar etapa, Ayuda de carril, Grabar, Hito) están siempre a la vista, en cualquier vista, bajo el estado del viaje (estado, recorrido, etapa, velocidad, distancia, condición, lugar y regla). Debajo van «Empezar en», la vista de depuración y guardar el viaje. Calibración, Ajustes y Experimental siguen en sus pestañas. La pestaña Conducir queda con los mandos, el minimapa y la cámara.
- **Panel flotante** (para jugar con una sola pantalla): una tira chica y semitransparente arriba al centro de la pantalla del juego con estado, velocidad, distancia, condición y el aviso o la regla del momento. No roba el foco, no recibe clics y va donde el programa no lee nada (el minimapa, el velocímetro y la condición están abajo). Se prende solo si el PC tiene **una sola pantalla**, o siempre, o solo con la tecla **F6** (Ajustes → Panel flotante; la tecla se cambia en «Cambiar teclas»). F6 lo prende y lo apaga a mano en cualquier modo.
- **Avisos visibles de problemas de base:** una franja amarilla/roja bajo el estado (y en el panel) cuando el programa detecta algo que lo hace andar mal, con qué hacer:
  - el **mando virtual no funciona** y está manejando con el teclado;
  - el **juego está en millas** (la distancia se lee como «0.9m» o no coincide con la velocidad);
  - **no se lee la distancia** del HUD (no cambia aunque el camión va rápido);
  - **no reconoce el recorrido** en la ida (sin reglas), por ejemplo si se activó a mitad de camino;
  - el camión **ya está cargado** pero el programa sigue en «ir a cargar» (usa «Saltar etapa»).
  Cada aviso sale también como notificación una sola vez. Probado con los viajes guardados: los dos viajes en millas del otro jugador se detectan; en el resto solo salen avisos que corresponden (activaciones con el camión ya cargado o recorridos nuevos).
- **Actualizaciones desde GitHub** (repositorio TKFjbn/autopiloto-camion): al abrir, el programa consulta cuál es la última versión publicada (solo lee un número, no envía nada tuyo). Si hay una nueva aparece «⬆ Versión X» arriba y una ventana con el texto de lo que cambia; tú decides: **Actualizar ahora**, **Más tarde** o **No avisar de esta versión**.
  - Al actualizar, baja el .zip, guarda antes una copia de lo que reemplaza en `mi_equipo/respaldos/actualizacion_…/` y cambia solo `programa/` y, si lo dejas marcado, `datos/` (sin borrar tus propias grabaciones ni reglas), más CAMBIOS.md, LEEME.md, PROMPT_CALIBRACION.md y PUBLICAR.md. **No toca `mi_equipo/`, `viajes/` ni los .bat.** Si el .zip trae errores, no instala nada.
  - **Ajustes → Versión y carpetas:** «Buscar actualizaciones» (a mano), «Actualizar desde .zip…» (sin internet: eliges un .zip que te pasaron) y la opción de buscar o no al abrir.
  - Tras actualizar hay que cerrar y volver a abrir el programa (la ventana ofrece cerrarlo).
  - Cómo publicar cada versión: ver `PUBLICAR.md`.
- **Textos legibles al calibrar:** los textos de la ventana de recuadros (Minimapa, Ruta, Distancia…) llevan ahora un fondo oscuro y ya no se mezclan con el chat del juego.
- Archivos nuevos: `programa/salud.py` (avisos), `programa/panel.py` (panel flotante), `programa/actualizar.py` y `programa/ventana_actualizar.py` (actualizaciones). Opción nueva de teclas: `panel` (F6).

## Programa 3.0.0 · Datos 1.2.3 (2026-11-14)
Tipo: **programa** (cambia el formato de la calibración: MAYOR). Los datos no cambian.
- **Calibración relativa a la ventana del juego:**
  - El programa busca la ventana de GTA (solo pregunta a Windows dónde está; no toca el juego) y guarda la calibración en `config.json` → `calibracion`: minimapa anclado abajo a la izquierda y velocímetro abajo a la derecha (en unidades del alto de la ventana), carril en fracciones de la ventana.
  - **Mover la ventana o cambiar la resolución ya no obliga a recalibrar:** las posiciones se recalculan al activar el autopiloto y cada 2 s si la ventana cambia. Si cambia mucho la proporción, avisa (la cámara de carril puede necesitar recalibrarse).
  - Tu calibración anterior se convierte sola la primera vez que activas el autopiloto con GTA abierto.
- **Calibración automática:** «Calibrar todo» encuentra el minimapa (por las barras de vida/armadura y la flecha del jugador), el velocímetro (texto amarillo) y las regiones de texto, y los muestra con recuadros y lo que leyó en la captura (ruta, distancia, punto cardinal, velocidad, condición). ENTER guarda; M / F / V / C para ajustar a mano el minimapa, la flecha, el velocímetro y el color de la ruta. La captura es solo de la ventana del juego.
- **Reglas independientes de la resolución:**
  - El minimapa se captura en su tamaño real y se lleva siempre a **272×180 px** (la unidad de las reglas). Todo lo que se mide en píxeles del minimapa (desplazamientos, `giro_tardio_px`, trazados, ajustes, radios de visión, la flecha del jugador) vale igual en cualquier resolución.
  - `jugador` y los radios de visión de tu `config.json` se convierten a esa unidad (en tu PC casi no cambian).
  - Los textos del HUD (distancia, zona) se llevan a la misma escala antes de leerlos, y las notificaciones ajustan sus mínimos al tamaño del HUD.
  - La condición del camión («NN%») se ubica respecto al velocímetro (abajo a la derecha) y no al minimapa, así vale con cualquier proporción de pantalla.
  - Las barras de carga/descarga y el menú se buscan dentro de la ventana del juego, no en toda la pantalla.
  - Los números del HUD aprendidos se guardan ahora en `mi_equipo/plantillas_hud_usuario_v3.npz` (los de antes se ignoran porque estaban a otra escala).
- **Comprobar instalación** muestra el estado de la calibración y si encuentra la ventana del juego.
- Probado: en tu escala el autopiloto simulado se comporta **exactamente igual** que en la 2.7.3; con minimapas un 15 % más chico y un 40 % más grande, prácticamente igual. Con la captura del otro jugador (ventana 1914×1171), la calibración automática encontró el minimapa y el velocímetro y leyó bien ruta, «5.39km», «NE», 14 km/h y 80 %.

## Programa 2.7.3 · Datos 1.2.3 (2026-11-14)
Tipo: **solo programa** (lectura de la distancia del HUD). No cambia la conducción ni los datos.
Motivo: en el viaje de otro jugador, «2,07 km» se leyó como «2,97» varias veces seguidas. La 2.7.2 lo aceptó como salto real, aplicó la regla de la barrera de Mirror Park 850 m antes de tiempo y el camión quedó atascado.
- **Más confusiones corregidas:** el 0 leído como 9, 8 o 6, y el 3 leído como 6, además de las de la 2.7.2. Si hay varias correcciones posibles, se usa la más cercana a la lectura anterior.
- **Un salto tiene que repetirse 5 lecturas seguidas** (`salto_lecturas`) para creerlo. La excepción es un salto hacia arriba justo al llegar a un punto (menos de 300 m, como al cargar o al descargar), que se acepta a la segunda lectura.
- **Aprende con más cuidado:**
  - solo aprende números leídos con mucha seguridad, cuando el segundo candidato queda claramente atrás;
  - no aprende durante los 15 s siguientes a un salto.
- Con el viaje del otro jugador: 8 lecturas corregidas (2970 → 2070, 2880 → 2080, 1090 → 1000…) y 7 descartadas.
- **Resolución:** el HUD se escala con el alto de la ventana. Para leer igual que en el PC donde se hicieron las plantillas (ventana de 1914×1051), conviene un alto parecido, como 1680×1050 en modo ventana. Después de cambiar la resolución hay que volver a calibrar y borrar `mi_equipo/plantillas_hud_usuario.npz`.

## Programa 2.7.2 · Datos 1.2.3 (2026-11-14)
Tipo: **solo programa** (lectura de la distancia del HUD). No cambia la conducción ni los datos.
Motivo: en otro PC, con otra resolución, el lector confundía números del HUD (sobre todo el **6 con el 0**): leía 5090 en vez de 5690, no reconocía el recorrido y aplicaba reglas de otro lugar.
- **Corrige dígitos mal leídos:** si una lectura no cuadra con la anterior pero cambiando un dígito confundible sí cuadra (5070 cuando venía de 5680), se usa la corregida.
- **Descarta lecturas imposibles:** la distancia baja de a poco; un salto suelto (5540 → 6640 → 5530, o 5540 → 500) se ignora. Si el salto se repite en la lectura siguiente, es real (punto nuevo, por ejemplo al cargar) y se acepta.
- **Reconoce el recorrido aunque falle un dígito:** si la distancia inicial no coincide con ninguna ruta, prueba cambiando un dígito (5090 → 5690 = Granja 1). Solo lo usa si calza una única ruta, y lo anota en el registro.
- **Aprende los números de cada PC:** las lecturas que cuadran con la anterior enseñan cómo se ven los números en esa pantalla. Se guardan en `mi_equipo/plantillas_hud_usuario.npz` y se usan junto a las de siempre, así cada vez se equivoca menos. Borrar ese archivo las olvida.
- Al detener se anota cuántas lecturas se corrigieron y cuántas se descartaron.
- Opciones nuevas en `hud_texto`: `filtrar_distancia`, `aprender_numeros` (ambas activas).
- **Importante para otros jugadores:** el juego tiene que estar en **sistema métrico** (Configuración → Pantalla → Sistema de medida). En millas las reglas no funcionan.

## Programa 2.7.1 · Datos 1.2.3 (2026-11-13)
Tipo: **solo programa** (arranque). No cambia la conducción ni los datos.
- **Revisión de librerías al abrir** (`programa/arranque.py`): antes de abrir la interfaz comprueba que estén instaladas OpenCV, numpy, mss y pillow (necesarias), y vgamepad y el OCR de Windows (recomendadas). Si falta alguna, pregunta «¿Instalarlas ahora?» y las instala con pip en una ventana que muestra el avance. Si `winsdk` no se instala, prueba con los paquetes `winrt-*`.
- **Aviso de versión de Python:** si es muy vieja (menos de 3.9) no abre y dice qué instalar; si es más nueva que la probada (3.13), avisa por si alguna librería falla.
- **Los errores ya no son silenciosos:** si el programa no puede arrancar, muestra una ventana con el error y lo guarda en `mi_equipo/error_inicio.txt`, para mandarlo.
- **`Autopiloto.bat`:** busca `pythonw`, `pyw`, `python` o `py`. Si no hay Python, lo dice y abre la página de descarga.
- **`Autopiloto (administrador).bat`:** pide permisos de otra forma, que no se rompe con espacios, tildes, ñ, paréntesis o apóstrofos en la ruta.
- **Nuevo `Instalar librerias.bat`:** revisa e instala todo mostrando el avance en una consola (para instalar a mano o ver un error de pip).

## Programa 2.7.0 · Datos 1.2.3 (2026-11-11)
Tipo: **programa + datos**.
- **Tiempos de viaje.**
  - En la pestaña **Viajes**:
    - columna nueva **Duración**, con una «R» si fue en modo rápido;
    - al elegir un viaje, se ven la ida, la vuelta y el total, y el **promedio de ese recorrido**, separado entre modo normal y modo rápido.
  - En el panel principal: **«Último viaje»**, con su tiempo, ida, vuelta y modo.
  - Cómo se cuenta el tiempo de un trabajo: desde «camión CARGADO» hasta «TRABAJO COMPLETADO». La ida termina en «DESCARGADO».
  - Solo cuentan los trabajos completos, y si hay varios en un viaje se cuentan aparte.
  - Cada viaje se lee una sola vez, en segundo plano, y el resultado queda en `mi_equipo/tiempos_viajes.json`.
- **Reglas solo para el modo rápido:**
  - Campo nuevo **`solo_rapido`**, con la casilla «Solo en modo rápido» en el mapa de la ruta. Esas reglas valen solo con el modo rápido prendido. El modo rápido sigue usando también todas las reglas normales.
  - En la lista del mapa aparecen con la etiqueta «(rápido)».
  - El prompt para otras IA lo explica, junto con la columna `modo_lento` = 2.
- **Mapa de la ruta:** con el autopiloto andando, **cambia solo** al recorrido y tramo en que va el camión (camino a cargar, ida, vuelta). Se puede apagar con la casilla «Cambiar solo de tramo», y no cambia mientras estás editando una regla.
- **Modo rápido:** antes de una regla con límite empieza a bajar tan temprano como el modo normal. En el viaje de prueba, las frenadas al entrar a las reglas subieron de 23 a 59.
- **Datos:** Autopia Parkway (ida, tramo compartido, vale para Granja 1 y Granja 2) queda partida en dos:
  - 5,20–5,06 km: sigue en +1,0, porque al empezar la subida rozaba la barrera izquierda.
  - 5,06–4,96 km: **−0,5**, porque al terminar la curva iba 9–11 px a la derecha rozando la barrera derecha.
- **Pendiente (anotado):** mejorar la cámara de carril para que reconozca la calle entera y el camión se quede en el carril derecho, o como mucho al medio, enderezándose en vez de solo frenar. Pasa en la calle de Granja 1 desde Vinewood Park Drive, de ida y de vuelta, y en la curva de Señora Road.

## Programa 2.6.0 (2026-11-11)
Tipo: **programa** (lógica de velocidad, solo en el modo nuevo). Los datos no cambian.
- **Nuevo (Experimental): modo rápido.** Se prende y apaga mientras manejas, con el botón de Experimental o con su tecla (**F10**). Viene apagado y puede chocar más.
  - **Más velocidad:** recta 90 km/h (antes 80), recta larga 110 (antes 100), curvas +15 %, esquinas sin regla +5 y bifurcaciones 65/80.
  - **La recta larga es más fácil de alcanzar:** acepta pedazos de ruta que giran hasta 14° (antes 8), el camión hasta 10° torcido (antes 6) y 6 px de desvío (antes 4), con 1 s (antes 2). En modo normal pasaba muy poco: en el último viaje, el 0,7 % del tiempo, por las curvas suaves de las autopistas.
  - **Curva larga:** con 20° de giro deja ir a 90 (antes 80).
  - **Curvas más fluidas:** suelta el acelerador en vez de frenar hasta 18 km/h por encima (antes 12), ignora bajadas del objetivo de 4 cuadros (antes 2), mantiene el objetivo bajo 0,8 s después de una curva (antes 1,5) y recupera velocidad a 12 km/h por segundo (antes 8). Apaga el «suavizado en curvas lentas».
  - **Cuando sí hay que frenar, frena más fuerte:** freno máximo 0,55 (antes 0,35) y pausas más cortas entre pulsos. Sin esto, en la simulación llegaba a la esquina final a 110 km/h y se pasaba 12 m.
  - **No cambia:** el `max_kmh` y el `esquina_kmh` de las reglas, ni la llegada al destino.
  - **Simulación** (recta, curva a la derecha, curva a la izquierda y llegada): de 86,4 a **78,4 s** (9 % más rápido), desvío máximo de 6,1 a 5,6 m, frenadas de 14 a 13. En las curvas, igual que el modo normal. El modo normal da exactamente lo mismo que antes.
  - Valores en `config.json` → `modo_rapido`. En el viaje, la columna `modo_lento` vale 2 cuando está el modo rápido.
- **Modo lento → Experimental:** el botón salió de los controles principales y está en la pestaña Experimental, junto al modo rápido.
- **Cambiar teclas:** apartado nuevo **Experimental** con la tecla del modo lento (RE PÁG) y la del modo rápido (F10).
- Indicador «RÁPIDO» en el panel, junto a «LENTO».

## Programa 2.5.6 (2026-11-10)
Tipo: **solo el prompt** (`PROMPT_CALIBRACION.md`). No cambian ni la lógica ni los datos.
- La IA tiene que preguntar **hechos** (qué pasó, qué tocó, de qué lado, cuándo), **no pedirle al jugador que elija valores**. Los valores los propone ella.
- Los controles manuales y choques que el jugador atribuye al tráfico se listan aparte como "descartados por tráfico", no como problemas a calibrar.

## Programa 2.5.5 (2026-11-10)
Tipo: **solo programa**. Los datos no cambian.
- **Un paquete por trabajo:** si el viaje tiene varios trabajos, además de `para_ia.txt` se arman `para_ia_trabajo1.txt`, `para_ia_trabajo2.txt`… Cada uno trae el prompt, solo ese trabajo, sus observaciones y sus reglas. Con el viaje doble quedan en unos 118 y 103 KB. Gemini cortaba el archivo cerca de los 200 KB.
- **Resumen más compacto:** `zona`, `calle` y `regla` se escriben solo cuando cambian. `para_ia.txt` del viaje doble baja de 298 a 196 KB.
- **Versión de los datos:** si el viaje se hizo con otros datos que los de ahora, el paquete lo avisa. Lo que estaba activo en el viaje es la columna `regla`, y los archivos son lo de hoy. Esto confundió a ChatGPT con la regla de Mirror Park.
- **Prompt:** explica que una regla se comparte solo si su centro cae dentro del tramo compartido (±40 m), y que `entregar_control` y `solo_esta_ruta` nunca se comparten. También explica las columnas vacías del resumen.

## Programa 2.5.4 (2026-11-10)
Tipo: **solo programa**. Los datos no cambian.
- **Selecciones rápidas en las observaciones.** En cada punto y cada hito, además del texto, hay tres listas:
  - **Qué pasó:** barrera, poste o cartel, otro vehículo, giró antes o tarde, se abrió en la curva, se pegó a un lado, muy lento o muy rápido, se salió…
  - **Lado:** izquierda, derecha, los dos.
  - **Causa:** autopiloto, tráfico u otro jugador, lo hice yo, no sé.

  Quedan escritas en el viaje. Un hito con solo una selección, sin texto, ahora también se guarda.
- **`para_ia.txt` trae el prompt al principio:** basta con adjuntarlo y escribir «analiza y pregunta». La ventana del resumen ahora empieza **20 s** antes de cada punto o hito (antes 12).
- **Prompt:**
  - El hito se marca **después** de lo que pasó, así que hay que buscar el problema hasta 20 s antes. ChatGPT miró solo 5 s antes y no vio el choque real.
  - En el primer paso, **tabla obligatoria** con los valores de cada punto o hito.
  - **Preguntas con opciones de letras** («1C, 2A»).
  - **Opciones cerradas:** solo los campos de las reglas y los ajustes de trazado. Si algo no se puede hacer con eso, la IA tiene que decir que es del programa.
  - Si la causa es "tráfico" o "lo hice yo", ese punto no se calibra.

## Programa 2.5.3 (2026-11-10)
Tipo: **solo programa**. Los datos no cambian.
- **Paquete para otra IA en un solo archivo (`para_ia.txt`).** «Copiar prompt + archivos» arma, además de los archivos sueltos, un solo archivo chico con:
  - el viaje **resumido** y separado por trabajo, con todas las observaciones. Trae filas cada ~0,3 s desde 12 s antes hasta 3 s después de cada punto o hito, una cada 2 s en el resto, todas las filas con evento, y solo las columnas útiles;
  - las reglas del recorrido y de los que comparten tramo, `_comunes.json` y `compartidos.json`;
  - los trazados sin los datos crudos.

  Un viaje doble de 4,5 MB queda en unos 245 KB, y uno simple de 2,2 MB en unos 100 KB. ChatGPT gratis llegaba al límite de adjuntos, y Gemini no leía el CSV grande y se quedaba solo con las observaciones.
- **Prompt:**
  - Explica el archivo único y le pide a la IA que **confirme que leyó el viaje completo**, o que diga si leyó solo una parte.
  - **Los hitos y puntos críticos se analizan siempre.** Si el jugador dice que algo fue por tráfico, vale para los controles manuales, no para los hitos.
  - Cada conclusión tiene que **citar valores del CSV**.
- **Observaciones guiadas:** la ventana de observaciones y el tutorial sugieren qué anotar: qué tocó o qué hizo mal, de qué lado, desde dónde empezó y si fue por tráfico.

## Programa 2.5.2 · Datos 1.2.2 (2026-11-10)
Tipo: **programa + datos**.
- **Nuevo (Experimental, encendido): corrección de lado suave en autopista.** A 70 km/h o más, en recta, la corrección de lado usa la línea del GPS promediada en ~0,5 s, no la de cada cuadro.
  - En Mirror Park (3,16 km) la línea se corrió 7 px de lado sin que el camión se moviera, y el programa la siguió hasta chocar con la barrera. Repitiendo ese momento del viaje, el desvío que se corrige baja de 7 a ~4 px y llega más tarde.
  - Con curva por delante, o a menos velocidad, no cambia nada.
  - En la simulación a 80 km/h la recta queda igual o algo más estable (desvío medio de 0,54 a 0,47 m). Las curvas dan resultados dentro de la variación normal de la simulación.
  - Se ajusta en `config.json` → `lado_suave`.
  - Por qué no se hizo "ignorar saltos de lado": en cada viaje hay entre 26 y 41 saltos parecidos que no causan nada, así que no se pueden distinguir.
- **Datos:**
  - **Autopista de Mirror Park (ida, tramo compartido: vale para Granja 1 y Granja 2):** la regla empieza en 3,25 km (antes 3,20) y queda en −1,5 (antes −1,0).
  - **Salida a Vinewood Park Drive (Granja 1):** a la izquierda (−2,0) solo hasta 2,10 km. De 2,10 a 2,04 km va al centro, con los mismos límites de velocidad y de esquina.
  - **Autopista de Vinewood Hills (vuelta, Granja 2, 3,85–3,60 km):** de −1,75 a −1,25.
  - **Strawberry (vuelta):** el trazado común va sobre la línea de 1,49 a 1,24 km (antes hasta 1,34). Quita el zigzag que causó el roce de 1,25 km.

## Programa 2.5.1 · Datos 1.2.1 (2026-11-10)
Tipo: **programa + datos**. Los datos 1.2.1 necesitan el programa 2.5.1.
- **Arreglo de Strawberry (vuelta).** El cambio de la 2.5.0 (regla de +1,0 a 0) no movía el camión, porque ahí manda el trazado común grabado, que lo llevaba 2,5 px a la derecha justo donde rozaba los carteles. Ahora el trazado va **sobre la línea entre 1,49 y 1,34 km**. El máximo de 50 km/h de la regla sí funcionaba y se mantiene.
- **Nuevo en los trazados: «ajustes».** Fijan el lado en una parte de un trazado sin regrabarlo, por ejemplo `"ajustes": [{"desde": 1490, "hasta": 1340, "lado": 0}]`. Se aplican también si el trazado se reprocesa.
- **Prompt para otra IA:**
  - Arreglado el sentido de la columna `desplazamiento` del CSV: positivo es izquierda, igual que `desvio_cerca`. El prompt decía lo contrario, y por eso Gemini leyó el lado al revés.
  - Sección nueva sobre los trazados: mandan sobre el `desplazamiento_px` de las reglas, mientras que el `max_kmh` sigue valiendo. El lado se corrige con «ajustes» o regrabando.
- **«Copiar prompt + archivos»** ahora adjunta también los trazados del recorrido y los comunes, y no repite archivos.

## Programa 2.5.0 · Datos 1.2.0 (2026-11-10)
Tipo: **programa + datos**. Los datos 1.2.0 necesitan el programa 2.5.0: actualiza las dos carpetas.

**Nuevo: tramos compartidos entre recorridos** (pestaña Experimental):
- **Perfil de cada recorrido.** Con cada viaje hecho con rumbo exacto se guarda el rumbo del camión cada 10 m, por tramo, en `datos/perfiles/`. Se actualiza solo al detener el programa (si «Mapa de la ruta» está encendido) o con «Agregar viaje…».
- **Detección.** Se comparan los perfiles y se buscan partes de al menos 200 m, con curvas, donde dos recorridos tienen el mismo rumbo con una diferencia de metros constante (error medio menor a 5°). Quedan en `datos/compartidos.json`.
- **Confirmación manual.** Los tramos nuevos quedan **pendientes**. En Experimental → Tramos compartidos se confirman o se apagan, y en el mapa de la ruta se ven en amarillo (punteado si están sin confirmar).
- **Reglas compartidas.** En un tramo confirmado, una regla de un recorrido vale también para el otro, corrida con la diferencia de metros. Se guarda una sola vez, en el archivo de su recorrido.
  - En el mapa aparecen como «(de Granja 1, compartida)». Al editarlas, los metros se muestran en los del recorrido que estás viendo.
  - Opción nueva **«Solo en esta ruta»** para que una regla no se comparta.
  - Las reglas de «entregar el control» nunca se comparten.
- Al preparar archivos para la IA también va `compartidos.json` y el otro recorrido.

**Datos:**
- Tramos confirmados, revisados con el jugador:
  - **Ida:** Granja 1 de 5,69 a 2,21 km = Granja 2 de 5,53 a 2,05 km (160 m menos; error 2,9°).
  - **Vuelta:** de 3,48 km al final, iguales (error 2,5°).
- **Granja 2, ida:** se borraron sus 14 reglas de ese tramo. Ahora usa las de Granja 1, que daban mejores resultados, incluido el giro hacia Banning. Quedan solo sus reglas propias: la de 2,10–2,00 km (donde se separan los caminos, marcada «solo en esta ruta»), Vinewood Hills (1,85–1,40 km) y la entrada a la granja.
- **Vuelta:** la regla de la salida a la derecha de 2,82 km (de Granja 2) ahora vale también para Granja 1. La de 3,85–3,60 km sigue siendo solo de Granja 2, porque ahí los caminos todavía son distintos.
- **Strawberry Avenue (vuelta, común):** de +1,0 a **0** y máximo **50 km/h**. Rozaba los carteles de la derecha en 5 viajes.
- Perfiles de Granja 1 y Granja 2 armados con los viajes de las 05:39 y las 04:58.

## Programa 2.4.2 · Datos 1.1.8 (2026-11-10)
Tipo: **programa + datos**.
- **Protección contra saltos falsos de la ruta.** En Granja 2 (vuelta, ~2,6 km) la línea del GPS que lee el programa saltaba un instante a la derecha (+19 px, curva de +56°, fuera de la calle) y el camión daba un volantazo a 85 km/h. Pasó en 3 viajes en el mismo punto, y el rumbo exacto mostraba que el camión iba derecho. Ahora, yendo a 50 km/h o más, un salto así se ignora: se sigue con la última lectura buena hasta que la línea vuelva (máximo 1,5 s, o antes si el camión gira de verdad). Revisé todos los viajes guardados y esta firma solo aparece en ese punto. Se puede ajustar o apagar en `config.json` → `salto_ruta`.
- **Captura del minimapa en el salto:** cuando la protección actúa queda un punto crítico «Salto falso de la ruta ignorado» con el minimapa en tamaño real y «Lo que vio el programa», para ver qué lo confundió.
- **Capturas de los hitos más atrás:** como F9 se aprieta después de lo que pasó, ahora son de 3 s antes, 1,5 s antes y el momento.
- **Arreglo: mapa de la ruta.** Los recuadros de ayuda al pasar el mouse por las reglas quedaban pegados y se apilaban.
- Datos (Granja 2, vuelta): la regla de la autopista de Vinewood (3,85–3,60 km) pasa de −1,0 a **−1,75** (choque a la derecha en 3,72 km); regla nueva **2,85–2,75 km sin frenar por la bifurcación** (salida a la derecha a 2,82 km).

## Programa 2.4.1 · Datos 1.1.7 (2026-11-10)
Tipo: **programa + datos**.
- **Arreglo: la vuelta pasaba a "camino a cargar".** A 5,48 km, después de salir de la granja, la ruta del GPS desapareció unos 13 s. Al volver, el programa creyó que empezaba un trabajo nuevo, y toda la vuelta corrió sin sus reglas (árbol de Textile City, Banning). Ahora, si la ruta se pierde con más de 400 m al punto y vuelve la misma, sigue en la misma etapa ("La ruta volvió: sigo en el tramo 2").
- **Mapa de la ruta, más robusto:** las lecturas malas del HUD (por ejemplo 5610, 3040 o 1070 m durante 1–3 s) cortaban el recorrido. Ahora un salto de la distancia tiene que durar más de 4 s para contar, y si un tramo queda partido se usa la parte más larga.
- **Experimental → "Usar grabaciones de teclas":** apágalo para hacer a mano entradas, salidas y llegadas sin borrar las grabaciones. Vale al momento.
- Datos: **mapa de Granja 2** (ida, vuelta y camino a cargar), armado con el viaje de las 04:07.

## Programa 2.4.0 · Datos 1.1.6 (2026-11-10)
Tipo: **programa + datos**. Incluye lo que iba a ser la 2.3.4.

**Nuevo (pestaña Experimental):**
- **Rumbo exacto.** El programa busca la **N** que recorre el borde del minimapa y además mide cuánto gira el dibujo del minimapa de un cuadro al siguiente. Con eso sabe hacia dónde apunta el camión, en grados, en cada cuadro.
  - La N corrige el rumbo cuando se ve bien en un costado del minimapa. En las esquinas es menos precisa y a veces la tapa el ícono del destino: ahí sigue el giro medido.
  - En tus 10 capturas la N se encontró en 8, y en las 2 restantes estaba tapada. El ángulo coincide con el punto cardinal del HUD. El giro del mapa medido en pruebas tiene un error de menos de 1°.
  - Se guarda en el viaje (columnas nuevas `rumbo_abs` y `rumbo_fuente`, al final).
- **Mapa de la ruta** (botón «Abrir mapa de la ruta…» en Experimental):
  - **Cómo se arma:** con el rumbo y la velocidad, desde un viaje hecho con esta versión. Al detener el programa se arma solo si el recorrido aún no tiene mapa, y también se puede armar con «Construir desde viaje…». Se guarda en `datos/mapas/`, así que se comparte con la carpeta de datos.
  - **Qué muestra:** ida, vuelta o camino a cargar. Las reglas aparecen como tramos de color: naranja = velocidad, azul = lado de la calle, morado = esquina, rojo = entregar el control, gris punteado = apagada. También muestra los trazados (verde punteado) y las grabaciones (cuadro rojo).
  - **Editar reglas:** clic en una regla, en el mapa o en la lista. Se pueden editar todos sus valores, mover dónde empieza y termina, **desactivarla** (queda en el archivo con `"activa": false`), **borrarla** o crear una **nueva** con un clic en el mapa. Antes de guardar se hace una copia en `mi_equipo/respaldos/rutas/`, y con el programa en marcha los cambios se aplican al momento.
  - **En tiempo real:** el camión aparece como flecha, junto con la regla actual y la próxima ("Próxima en 120 m: …").
  - Las reglas también se pueden editar desde la lista aunque todavía no haya mapa.

**Arreglos y ajustes (los de la 2.3.4):**
- **Velocidad suave** (Experimental) también en curvas cerradas y esquinas con límite bajo. En la esquina de Maze Bank (vuelta) frenaba 4 veces y la velocidad iba entre 11 y 49 km/h.
- **Lecturas falsas del HUD:** una bajada brusca de la distancia (más de 150 m) necesita 3 lecturas seguidas, en vez de 2. A 0,87 km el HUD leyó «8 m» dos veces y se activó la regla del punto final.
- **Pestaña Viajes:** el recorrido de los viajes sin observaciones se lee bien también con las columnas nuevas.
- Datos, Granja 2:
  - vuelta, autopista de Vinewood Hills: −2,5 → −1,0 (se acercaba a la barrera, hito 1);
  - grabaciones de **entrada** (desde 113 m) y **salida** (después de DESCARGADO), que tienen que romper las vallas.

## Programa 2.3.3 · Datos 1.1.5 (2026-11-10)
Tipo: **programa + datos**.
- **Arreglo: llegada falsa lejos del punto.** A 4,78 km se detectó una "barra de progreso" que no existía. El programa creyó llegar a la granja y pasó la ida a vuelta: el resto de la ida fue con reglas y trazados de la vuelta (de ahí el choque de 1,05 km). Ahora el menú y la barra de carga no se toman en cuenta si faltan más de 400 m para el punto.
- **Trazados en esquinas:** durante una esquina el trazado se pausa y maneja la lógica de esquinas; después sigue. En Davis (4,68 km), el trazado corría el camión de lado en plena esquina, se salió de la calle y el GPS recalculó.
- Datos, Granja 1 (ida):
  - fin del puente: −2,0 → −0,5 (bloque de concreto a la izquierda);
  - esquina a la salida del puente: −2,0 → +0,5 y giro más tarde (giro_tardio 3 → 2): derecho y un poco a la derecha, pasar las rejas y recién girar;
  - subida de Autopia Parkway: 0 → +1,0 (rozaba la barrera izquierda);
  - trazado de Davis/Strawberry: el que grabaste de nuevo (4,76 → 4,07 km);
  - salida de la granja: la nueva, que se repite sola **después de DESCARGADO** (`grabaciones/drogas_granja_1_salida.json`). La anterior se retira a `mi_equipo/respaldos/datos_obsoletos/`.

## Programa 2.3.2 · Datos 1.1.4 (2026-11-10)
Tipo: **programa + datos**.
- **Pestaña nueva: Experimental.** Funciones en prueba, cada una con su interruptor. Los cambios se aplican al momento y se guardan en `config.json → "experimental"`. Cuando una función esté probada, pasa a fija y sale de la pestaña. Empieza con dos, encendidas:
  - **Velocidad suave en curvas y reglas lentas:** con límite de menos de 50 km/h acelera con menos fuerza y frena solo si se pasa más de 10 km/h. En la curva de Banning (hito 1) la velocidad subía y bajaba entre 19 y 51 km/h con límite 40, porque el velocímetro del HUD llega 1–2 s tarde. En la simulación pasa de 20–58 km/h (con 5 s de frenadas) a 28–44 km/h (sin frenar).
  - **Trazados comunes en la vuelta:** los trazados de la vuelta grabados desde 2,3 km (el final, igual para todos) valen para todos los recorridos. Los que grabes desde ahora en esa parte se marcan solos.
- **Limpieza automática de datos viejos:** `datos/obsoletos.json` lista archivos que ya no sirven. Al abrir el programa se **mueven** (no se borran) a `mi_equipo/respaldos/datos_obsoletos/`, solo si su contenido es exactamente el de la lista. El registro dice qué se movió.
- Datos, Granja 1:
  - autopista de Mirror Park (3,20–2,90 km): −2,5 → −1,0 (rozaba el muro izquierdo, hito 2);
  - Vinewood Hills, autopista (2,70–2,50 km): máximo 70 → 78 (hito 3);
  - curva en bajada: desde 1,25 km (antes 1,15), máximo 65, −2,5 (se abría a la derecha, hito 4);
  - vuelta, curva a la derecha: desde 5,15 km (antes 5,08), máximo 55.
- Datos, grabaciones y trazados (los tuyos, ordenados):
  - entrada a Granja 1: la nueva, desde 85 m;
  - salida de Granja 1: la que funcionó al 100% (5620 m);
  - trazado de Davis/Strawberry para Granja 1: el que grabaste (4,78 → 3,97 km), en vez de la copia corrida;
  - **vuelta común de Strawberry** (1,66 → 0,98 km): para todos los recorridos; reemplaza a la de Granja 2.
  - Se retiran solos: la entrada vieja, las dos salidas que fallaron o estaban repetidas, el trazado repetido y la vuelta vieja de Granja 2.

## Programa 2.3.1 · Datos 1.1.3 (2026-11-10)
Tipo: **programa + datos**.
- **Reconocimiento del recorrido más seguro.** En el viaje de las 00:00 (Granja 2), el HUD mostró 5630 m durante unos segundos y el programa lo tomó por Granja 1 (que empieza en 5690 m). Toda la ida fue con las reglas corridas 160 m. Ahora:
  - cada lectura de la distancia se corrige con lo que avanzó el camión, y el recorrido se reconoce con la mediana de varias lecturas;
  - durante los primeros 40 s, si 3 lecturas seguidas apuntan a otro recorrido, **se corrige solo** y avisa con la notificación «Recorrido corregido». En ese viaje se habría corregido a Granja 2 unos 3 s después de que el HUD mostrara 5530, antes de la esquina del puente.
- Datos: **trazado de Davis y Strawberry (ida) para Granja 2** (4,62 → 3,83 km), el que grabaste en ese viaje.
- Datos: **el mismo trazado para Granja 1, corrido +160 m** (4,78 → 3,99 km), porque Granja 1 pasa por la misma calle pero empieza 160 m más lejos. Está por confirmar en un viaje.

## Programa 2.3.0 · Datos 1.1.2 (2026-11-09)
Tipo: **programa**. Los datos no cambian.
- **Hitos:** pulsa **F9** en el juego (o «⚑ Marcar hito» en Conducir) para marcar un momento del viaje, por ejemplo cuando va muy lento. Guarda la distancia, el lugar, la velocidad, la regla activa y 3 capturas, y muestra la notificación «Hito N creado».
  - En las observaciones, los hitos aparecen junto a los puntos críticos, en orden de tiempo, con sus capturas y la pregunta «¿Por qué lo marcaste?».
  - **Un hito en blanco no se guarda.** Los puntos críticos se guardan siempre (sirven para ver problemas que se repiten en el mismo lugar).
  - En el CSV quedan como `# hito N: ... | observación: ...`. La pestaña Viajes tiene una columna Hitos.
  - La tecla se cambia en Ajustes → Cambiar teclas. Las notificaciones de hitos se pueden apagar en Ajustes.
- **Arreglo: el recorrido no se reconocía** (viaje de Granja 1 de las 23:22). Al parar a 8 m del punto de carga quedaba un pedacito de ruta en el minimapa, y el programa lo tomaba como una ruta nueva: pasaba a la ida antes de cargar, intentaba reconocer el recorrido con 11 m y, al cargar, el salto a 5690 m se interpretaba como «descargado no detectado». Así la ida y la vuelta iban sin reglas. Ahora:
  - un pedazo de ruta muy corto a menos de 60 m del punto no es una ruta nueva;
  - el recorrido no se reconoce con menos de 300 m: espera la distancia de la ruta nueva;
  - la notificación «camión CARGADO» siempre vuelve a reconocer el recorrido;
  - «descargado no detectado» no se activa si la ida lleva menos de 60 s o si cargaste hace menos de 90 s.
- El prompt para otros asistentes de IA explica los hitos y les pide revisarlos primero.

## Programa 2.2.0 · Datos 1.1.2 (2026-11-09)
Tipo: **programa** (funciones nuevas). Los datos no cambian.
- **Capturas en las observaciones.** Mientras el programa corre, guarda en memoria las últimas pantallas del juego. En cada punto crítico (choque, atasco, tomaste el control…) quedan 3 capturas de pantalla completa: 1,5 s antes, en el momento y 1 s después. En la ventana de observaciones se ven en miniatura; con clic, en grande.
  - **Guardar esta captura** la copia a `viajes/capturas/`, junto al CSV, y el punto del reporte anota qué capturas guardaste.
  - Las demás están en `mi_equipo/capturas_temp/` y **se borran al cerrar el programa** (y al abrirlo, por si se cerró a la fuerza).
  - Se ajustan en `config.json` → `"capturas"` (activo, cada_seg, ancho, calidad).
- **Ajustes → Cambiar teclas:** pulsa «Cambiar» y la tecla nueva. Avisa si la tecla ya se usa, si es del juego (W/A/S/D…) o si conviene evitarla (F7, F8, HOME). Hay «Restaurar por defecto» y también se elige si el camión se maneja con **teclado o mando virtual**. Solo cambia las teclas y el control en `config.json`: la calibración queda igual.
- **Ajustes → Comprobar instalación:** revisa Windows, Python, numpy, OpenCV, mss, Pillow, la captura de pantalla, los archivos del programa, el mando virtual (vgamepad y el driver ViGEmBus), el OCR con idioma español, la calibración, los datos, los permisos de carpetas, la ventana del juego y el modo administrador. Dice qué hacer con cada problema (con botón para copiar el comando `pip`). **No instala nada.** También tiene una prueba de 1 s del mando virtual.
- **Tutorial para usuarios nuevos:** 8 pasos (nombre, instalación, preparar el juego, calibrar, teclas, primer viaje, grabaciones y observaciones). Se abre solo la primera vez y se vuelve a ver en **Ajustes → Ver tutorial**.
- **Calibrar con otro asistente de IA:** `PROMPT_CALIBRACION.md` explica el programa, el CSV y las reglas a cualquier asistente (ChatGPT, Gemini, Claude…) y le dice que pregunte antes de cambiar y que entregue el JSON de la ruta corregido. En **Calibración → Copiar prompt + archivos** (o **Viajes → Calibrar con IA…** para un viaje elegido) se copia el prompt y se abre `mi_equipo/para_llm/` con el CSV, el JSON de la ruta, `_comunes.json` y las capturas guardadas de ese viaje.

## Programa 2.1.2 · Datos 1.1.2 (2026-11-09)
Tipo: **programa + datos**.
- **Trazado suavizado.** La posición del camión en el minimapa tiene bastante ruido, así que el trazado ya no copia cada metro: toma la mediana cada 2 m y luego promedia en ventanas de 25 m. Sigue el lado general de la calle cada 20–30 m (no farol por farol), con un máximo de ±2.5 px.
- **El trazado ya no se corta por lecturas viejas del HUD.** Si al empezar el HUD repetía una distancia equivocada varios segundos (por ejemplo 4040 en vez de 4640), antes se perdía casi todo el trazado. Ahora cada lectura se compara con lo recorrido según la velocidad y se descartan las que no cuadran.
- **Los trazados guardan los datos crudos** y se vuelven a procesar solos cuando cambia el filtro en una versión nueva.
- **Al terminar una grabación, por defecto el autopiloto sigue.** En la pestaña Grabaciones hay un botón "Al terminar: seguir / parar" para cambiarlo en las grabaciones que ya tienes.
- Datos: la esquina a la salida del puente (Granja 2 y Globe Oil) gira más tarde (giro_tardio 3) y entra más rápido (32 km/h).
- Datos: incluye el trazado de regreso por Strawberry (Granja 2, tramo 2) ya suavizado.

## Programa 2.1.1 · Datos 1.1.1 (2026-11-09)
Tipo: **programa + datos** (arreglos).
- **Parar para una grabación ya no retrocede.** Antes frenaba aunque el camión estuviera casi detenido, y en GTA eso es marcha atrás. Ahora frena solo por encima de 3 km/h; por debajo suelta todo y espera.
- **La grabación de teclas se repite por distancia recorrida.** Mientras tú ibas en movimiento, la repetición avanza al ritmo del camión: si va más lento que tú, la grabación también, y los volantazos caen en los mismos metros. Las partes en que estabas detenido o arrancando siguen yendo por tiempo. Ya no se interrumpe por ir más lento que tú, solo si va mucho más rápido o si se queda trabado.
- **Distancia más confiable para grabaciones y trazados:**
  - se usa la distancia filtrada, que descarta lecturas sueltas erróneas del HUD (por ejemplo 5630 en vez de 5050);
  - entre lecturas del HUD se descuenta lo recorrido, y cada lectura nueva lo corrige.
- **Las grabaciones que empiezan lejos del punto** (por ejemplo, la salida de la granja a 5,63 km) solo se disparan al activar el autopiloto con el camión detenido. Antes, una mala lectura del HUD hizo frenar al camión a 40 km/h en plena vuelta.
- **Trazados más limpios:**
  - se descartan los puntos fuera de la calle y los saltos de distancia;
  - se quitan los picos (mediana de 5 puntos);
  - el lado queda limitado a ±4 px;
  - si casi todo el tramo está fuera de la calle del GPS (por ejemplo, en la granja), no se guarda y se avisa que uses la grabación de teclas.
- **Datos 1.1.1 (Granja 1):** en la esquina a la salida del puente gira más tarde (`giro_tardio_px` 3). El fin del puente (5,64–5,60 km) vuelve a ir a la izquierda, ahora a 25 km/h.

## Programa 2.1.0 · Datos 1.1.0 (2026-11-09)
Tipo: **programa + datos**. Hay que actualizar `programa/` y `datos/rutas/`; tus grabaciones no se tocan.

**Programa 2.1.0**
- **Grabaciones "al llegar a X m":** ya funcionan siempre, aunque no haya regla de entregar el control. El camión va bajando la velocidad, se detiene justo en el punto donde empezaste a grabar y repite la grabación. En la ida solo valen las de menos de 1 km (la entrada a la granja), para que una grabación mal etiquetada no se dispare al salir de la carga.
- **Salida del punto A:** si activas el autopiloto (INSERT) detenido donde empieza una grabación de la vuelta (±60 m, por ejemplo la salida de la granja), primero repite la grabación y después sigue con el GPS.
- **Trazados grabados:** opción nueva al guardar una grabación. No repite tus teclas. Guarda, metro a metro, a qué lado de la línea del GPS ibas, y el autopiloto sigue ese lado (y tu velocidad + 5 km/h como máximo). Es para calles con farolas desordenadas. Se guardan en `datos/trazados/` y aparecen en la pestaña Grabaciones. La distancia del HUD se afina con lo recorrido, porque por encima de 1 km el HUD va de 10 en 10 m.
- **Recién descargado:** las reglas de la vuelta y la grabación del punto final esperan a que aparezca la distancia nueva. Antes, la distancia vieja (por ejemplo 17 m) activaba la regla del punto final dentro de la granja.
- **Opciones nuevas para las reglas:** `sin_reversa` (cerca del punto no retrocede y te deja el control) y `aprox_kmh` (velocidad de acercamiento al punto).
- Ajustes nuevos en `config.json` → `"trazado"`.

**Datos 1.1.0** (Granja 1 y reglas comunes)
- **Ida:**
  - Fin del puente (5,64–5,60 km): un poco a la derecha, por la barrera de hormigón de la izquierda.
  - Esquina a la salida del puente: gira más tarde (`giro_tardio_px` 6, antes 9).
  - Esquina de Maze Bank Arena: a 35 km/h (antes 28).
  - Davis (4,56–4,48 km): un poco a la derecha.
  - Autopista de Mirror Park: desde 3,20 km y más a la izquierda (−2,5).
  - Esquina en subida (2,30 km): a 40 km/h.
  - Salida a Vinewood Park Drive: esquina a 32 km/h.
  - Señora Road: hasta 70 km/h.
  - Recta de Señora Road: desde 1,56 km y más a la izquierda.
  - Curva en bajada: hasta 70 km/h.
- **Vuelta (Granja 1):**
  - Señora Road (4,75–4,45 km): a la izquierda.
  - Esquina muy cerrada: desde 3,76 km y a 32 km/h.
- **Vuelta (comunes):**
  - Strawberry (faroles y carteles): un poco a la **derecha**.
  - Poste de Maze Bank: hasta 50 km/h.
  - Punto final: sin marcha atrás y acercamiento a 25 km/h.

## Programa 2.0.0 · Datos 1.0.0 (2026-11-09)
Tipo: **programa**. Cambia la interfaz y el orden de carpetas. La conducción y las reglas son las mismas que en la v39.
- Carpetas nuevas: `programa/`, `datos/`, `mi_equipo/` y `viajes/`, con migración automática desde el orden anterior.
- Versión del programa y de los datos.
  - Cada archivo de `datos/rutas/` tiene `programa_minimo`, y el programa avisa si es más viejo.
  - Cada viaje empieza con `# programa`, `# datos` y `# usuario`.
  - Las grabaciones guardan la versión con la que se hicieron.
- Las reglas, antes todas en `rutas_base.json`, ahora van en un archivo por recorrido en `datos/rutas/`, más `_comunes.json` con las compartidas.
- Interfaz nueva:
  - tema oscuro y claro;
  - vistas completa, compacta y mini;
  - minimapa y cámara separables en ventanas aparte;
  - pestañas Conducir, Grabaciones, Viajes, Calibración y Ajustes;
  - ayuda al pasar el mouse.
- Notificaciones en pantalla encima del juego: no quitan el foco, se pueden configurar por tipo y tienen esquina, pantalla, duración, tamaño y sonido a elección.
- Copias de seguridad de `config.json` en `mi_equipo/respaldos/`.

## Antes de 2.0.0 (v1 a v39)
Las versiones se numeraban v1, v2… v39. El detalle de cada una está en `LEEME.md`, en las secciones "Cambios de la vXX". La última fue la v39: descargado no detectado, aviso "acción necesaria" solo tras completar el trabajo, selector de tramo en las grabaciones, reglas del camino a cargar, ajustes de Granja 2 y ruta Productos varios - Globe Oil.

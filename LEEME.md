# Autopiloto de camión (GTA V RP) · versión 3.1.0

Sigue la ruta roja del minimapa en las 3 partes en que se conduce y espera solo en las paradas.
No toca el launcher ni la carpeta del juego: lee la pantalla y simula teclas o un mando.

| Etapa | Qué pasa | Quién lo hace |
|---|---|---|
| 1. Contratar | Eliges el trabajo y pulsas **Y** junto al punto | Tú |
| 2. Ir a cargar | Sigue la ruta roja | Autopiloto (pulsa **F7** antes del puente) |
| 3. Cargar | La ruta desaparece y el autopiloto suelta todo y espera. Eliges la mercancía en el menú | Tú (menú) |
| 4. Ir al punto A | Aparece la nueva ruta y el autopiloto arranca solo | Autopiloto |
| 5. Descargar | "Descargando camión…": espera | — |
| 6. Volver a B | Ruta de vuelta | Autopiloto |
| 7. Terminar | Al desaparecer la ruta queda en TERMINADO | Tú |

## Ventana, panel y actualizaciones (3.1.0)
- **Botones de todos los días** siempre a la vista bajo el estado del viaje: Iniciar, Detener, Activar / desactivar (INSERT), Saltar etapa (AV PÁG), Ayuda de carril (SUPR), Grabar y Hito (F9).
- **Avisos de problemas:** si aparece una franja de color bajo el estado, léela: dice qué anda mal (mando virtual, juego en millas, distancia que no se lee, recorrido no reconocido, camión ya cargado en «ir a cargar») y qué hacer.
- **Panel flotante (F6):** tira chica arriba al centro del juego para jugar con una sola pantalla. Ajustes → Panel flotante elige cuándo se muestra (automático con una sola pantalla, siempre, o solo con la tecla).
- **Actualizar:** arriba aparece «⬆ Versión X» cuando hay una nueva. Ajustes → Versión y carpetas: «Buscar actualizaciones» y «Actualizar desde .zip…». Antes de cambiar nada se guarda una copia en `mi_equipo/respaldos/`; `mi_equipo/` y `viajes/` nunca se tocan. Quien publica las versiones: `PUBLICAR.md`.

## Calibración 3.0.0 (cualquier resolución)
- **Automática:** con GTA abierto, Calibración → «Calibrar todo», captura con F11 en el camión (en movimiento) y «Continuar ▶». El programa encuentra el minimapa (por las barras de vida y la flecha), el velocímetro y los textos, y muestra recuadros con lo que leyó. ENTER guarda; M / F / V / C ajustan a mano el minimapa, la flecha, el velocímetro y el color de la ruta.
- **Relativa a la ventana:** se guarda en `mi_equipo/config.json` → `calibracion` respecto a la ventana del juego (minimapa anclado abajo a la izquierda, velocímetro abajo a la derecha, carril en fracciones). Al activar el autopiloto se busca la ventana y se calculan las posiciones; si la mueves o cambias su tamaño, se ajusta solo.
- **Misma unidad para todos:** el minimapa se lleva siempre a 272×180 px antes de analizarlo, y los textos del HUD a esa misma escala. Por eso las reglas, trazados y radios valen igual en cualquier resolución.
- **Tu calibración anterior se convierte sola** la primera vez que activas el autopiloto con GTA abierto (queda una copia en `mi_equipo/respaldos/`).

## Primeros pasos (2.2.0)
La primera vez que abres el programa sale un **tutorial** con los pasos para empezar; se vuelve a ver en **Ajustes → Ver tutorial**. En Ajustes también están **Cambiar teclas** (y teclado o mando) y **Comprobar instalación**, que revisa si falta alguna librería o herramienta y dice cómo arreglarlo.

**Observaciones con capturas:** cada punto crítico del viaje trae 3 capturas de pantalla (antes, en el momento y después). Se borran al cerrar el programa, salvo las que guardes con «Guardar esta captura» (van a `viajes/capturas/`).

**Saltos falsos de la ruta (2.4.2):** si yendo rápido la línea del GPS salta de golpe hacia un lado por un error de lectura, el programa la ignora y sigue derecho. Queda un punto crítico con el minimapa en tamaño real y lo que vio el programa.

**Hitos (2.3.0):** si durante el viaje ves algo raro (va muy lento, pasa muy cerca de un poste…), pulsa **F9** en el juego o «⚑ Marcar hito». Al terminar aparece en las observaciones con sus capturas (3 s antes, 1,5 s antes y el momento, porque F9 se aprieta después de lo que pasó) para que expliques por qué lo marcaste. Si lo dejas en blanco, no se guarda.

**Mapa de la ruta (2.4.0, Experimental):** con «Rumbo exacto» encendido, el programa detecta la N del minimapa y guarda hacia dónde apunta el camión. Al detener el programa se arma solo el mapa del recorrido (`datos/mapas/`). En Experimental → **Abrir mapa de la ruta…** se ven las reglas sobre el camino y se pueden editar, apagar, borrar o crear con un clic, además del camión en tiempo real. Cada cambio guarda antes una copia en `mi_equipo/respaldos/rutas/`.

**Tiempos (2.7.0):** en la pestaña Viajes, la columna Duración y, al elegir un viaje, su ida, su vuelta y el promedio del recorrido (normal y rápido por separado). En el panel principal, «Último viaje».

**Tramos compartidos (2.5.0, Experimental):** el programa compara el rumbo de los viajes de cada recorrido y encuentra solo las partes donde dos recorridos van por las mismas calles (por ejemplo, la ida de Granja 1 y Granja 2 hasta Vinewood Park Drive). En un tramo **confirmado**, las reglas de un recorrido valen también para el otro: se ajusta una vez y sirve para los dos. Los tramos nuevos aparecen como **pendientes** en Experimental → Tramos compartidos y en el mapa (en amarillo) hasta que los confirmes. Si una regla tiene que valer solo para un recorrido, marca «Solo en esta ruta».

**Pestaña Experimental (2.3.2):** funciones en prueba con su interruptor. Si algo empeora, apágalo ahí; el cambio vale al momento.

**Calibrar con otro asistente de IA:** Calibración → **Copiar prompt + archivos** copia el texto de `PROMPT_CALIBRACION.md` y abre una carpeta con los archivos del último viaje para adjuntarlos. El asistente pregunta lo que no esté claro y devuelve el archivo de la ruta corregido, que va en `datos/rutas/`.

## Versión 2.0.0: lo nuevo
**Carpetas** (desde la 2.0.0):

| Carpeta | Qué tiene | ¿Se comparte? |
|---|---|---|
| `programa/` | El código. Al actualizar, se reemplaza entera. | Se manda completa cuando hay versión nueva del programa. |
| `datos/` | Reglas por recorrido (`rutas/`), grabaciones (`grabaciones/`) y trazados (`trazados/`). Su versión está en `datos/datos.json`. | **Sí.** Para pasarle tus datos a otro jugador, envía esta carpeta. |
| `mi_equipo/` | `config.json` (calibración de pantalla y ajustes), `interfaz.json` (tema, vista, notificaciones), `registro.txt`, `zonas/`, `respaldos/`. | No. La calibración es de tu PC (aunque desde la 3.0.0 sigue sola a la ventana del juego). |
| `viajes/` | Un CSV por viaje, `incidentes.csv` y las observaciones. | Es lo que me envías para analizar. |

La primera vez que abres la 2.0.0 sobre la carpeta de antes, el programa **mueve solo** tus archivos al lugar nuevo, sin borrar nada: `config.json` y `registro.txt` pasan a `mi_equipo/`, las grabaciones a `datos/grabaciones/`, y los `.py` viejos sueltos a `_version_anterior/`. Si tenías un `rutas.json` propio, queda en `mi_equipo/respaldos/`. El registro muestra lo que se movió.

**Versiones:** el programa usa versionado semántico, MAYOR.MENOR.PARCHE.
- MAYOR: cambia el formato de datos o de reportes.
- MENOR: funciones nuevas.
- PARCHE: arreglos.

Los datos tienen su propia versión. Cada archivo de `datos/rutas/` dice qué versión mínima del programa necesita (`programa_minimo`), y si tu programa es más viejo, el programa avisa. La versión del programa sale en el título de la ventana y en las primeras líneas de cada viaje (`# programa`, `# datos`, `# usuario`). El historial está en `CAMBIOS.md`.

**Interfaz**
- **Barra de estado** arriba: estado en color, recorrido, etapa, usuario y control (mando o teclado). A la derecha, los botones de vista: **Completa**, **Compacta** (sin minimapa ni cámara) y **Mini** (estado, tarjetas, 4 botones y registro).
- **Tarjetas:** velocidad / objetivo, distancia al punto, condición y motivo de la velocidad. Debajo van el lugar (zona / calle) y la regla activa.
- **Pestañas:**
  - **Conducir:** iniciar o detener, botones del autopiloto, barras del volante, acelerador y freno, y vistas. El minimapa y la cámara se pueden **separar** en ventanas aparte (botón ⧉); al cerrar esa ventana vuelven a la principal. El programa recuerda dónde las dejaste.
  - **Grabaciones:** lista, renombrar, borrar y abrir la carpeta. Los cambios se aplican aunque el programa esté corriendo.
  - **Viajes:** los últimos viajes con recorrido, usuario, versión, puntos críticos y si tienen observaciones. Doble clic para leerlas.
  - **Calibración:** lo que antes era "Calibración y pruebas".
  - **Ajustes:** usuario, tema **oscuro o claro**, vista, ayuda al pasar el mouse, notificaciones, versiones y carpetas.
- **Ayuda al pasar el mouse** por cualquier botón o dato. Se puede apagar en Ajustes.
- **Registro** con colores: verde para lo que sale bien, azul para información, amarillo para avisos y rojo para errores.

**Notificaciones en pantalla** (tipo Discord), encima del juego.
- No le quitan el foco al juego ni reciben clics.
- Se ven con el juego **en ventana o pantalla completa sin bordes**; en pantalla completa exclusiva Windows no deja dibujarlas.
- Tipos:
  - autopiloto activado o desactivado;
  - tomaste el control;
  - etapas (recorrido reconocido, cargado, descargado, completado, tramo manual);
  - grabaciones (grabando, terminada, repitiendo, guardada);
  - problemas (choque, atascado, bajó la condición, grabación interrumpida);
  - avisos (falso choque, descargado no detectado, juego sin foco);
  - reportes (observaciones pendientes, reporte guardado);
  - calibración.
- En **Ajustes** eliges qué tipos ver, la esquina, la pantalla ("pantalla del juego" busca la ventana del juego), la duración, el tamaño y el sonido (ninguno, solo problemas o todos). El botón **Probar notificación** muestra ejemplos.

## Grabaciones y trazados (2.1.0)
Hay dos formas de enseñarle al programa un tramo difícil. Las dos se graban con el botón **● Grabar recorrido**, y al terminar eliges el tipo en la ventana de guardar.

| | Grabación (repetir teclas) | Trazado (mismo lado de la calle) |
|---|---|---|
| Para qué | Donde **no hay GPS útil**: entrada a la granja, salida del punto, maniobras, punto final. | Calles **con GPS** pero llenas de obstáculos: farolas desordenadas, postes, carteles. |
| Qué guarda | Tus teclas W/A/S/D/espacio y tu velocidad, segundo a segundo. | A qué lado de la línea del GPS ibas y tu velocidad. Se suaviza: sigue el lado general cada 20–30 m, no farol por farol. |
| Cómo se repite | El camión se detiene donde empezaste a grabar y repite tus movimientos, al ritmo de la distancia recorrida (si va más lento que tú, la grabación también). | El autopiloto sigue manejando con el GPS, pero se corre a tu mismo lado, sin pasar tu velocidad + 5 km/h. |
| Depende de llegar igual | Sí: hay que llegar al mismo punto y con el mismo rumbo. | No: no depende del tiempo ni de la velocidad. |

**Cuándo se repite una grabación**
- *Al llegar a X m*: el camión baja la velocidad, se detiene donde empezaste a grabar y la repite.
  - En la **ida** solo valen las de menos de 1 km, como la entrada a la granja.
  - En la **vuelta**, si activas el autopiloto (INSERT) parado donde empieza la grabación (por ejemplo, la salida de la granja), la repite primero y después sigue con el GPS.
- *Después de cargado o descargado*: apenas el juego suelta el camión.
- *Punto final*: al acercarse al final de la vuelta.

**Grabar un trazado**
1. Llega antes de la calle difícil, por ejemplo unos 100 m antes de las farolas de Davis.
2. Pulsa Grabar y conduce tú la calle esquivando como siempre, a la velocidad que te parezca segura (mejor no muy rápido: a menor velocidad, el trazado sale más preciso). **Tiene que verse la ruta del GPS en el minimapa.** En la granja o en lugares sin calle el trazado no sirve: ahí usa la grabación de teclas.
3. Al pasar la calle, pulsa Grabar de nuevo y elige **"Trazado"**. Las distancias de inicio y fin salen solas.

Al terminar una grabación de teclas, por defecto el autopiloto sigue con el GPS. Para que te dé el control al terminar, usa el botón **"Al terminar: seguir / parar"** en la pestaña Grabaciones.

Las grabaciones y los trazados están en la pestaña **Grabaciones**, donde se pueden renombrar y borrar. Como van en `datos/`, se comparten con esa carpeta.

## Interfaz gráfica (antes de la 2.0.0)
Doble clic en **`Autopiloto.bat`**. Si el juego corre como administrador, usa **`Autopiloto (administrador).bat`**. La interfaz actual está descrita arriba ("Versión 2.0.0"). Los comandos de consola siguen funcionando desde la carpeta `programa/`: `python autopiloto.py ...`, `python calibrar.py ...`.

## Instalación (Windows)
1. Instala **Python 3.12** desde https://www.python.org/downloads/ y marca **«Add python.exe to PATH»**.
2. Doble clic en **`Autopiloto.bat`**. Si faltan librerías, el programa pregunta si instalarlas y lo hace solo (necesita internet). También puedes usar **`Instalar librerias.bat`**, que muestra el avance, o a mano: `pip install -r requirements.txt`.
3. Si el programa no abre, el error queda en `mi_equipo/error_inicio.txt`.
4. En GTA V pon **Configuración → Pantalla → Sistema de medida → Métrico** (el idioma da igual). Con millas el programa no puede ubicarse en la ruta y no aplica las reglas.
5. Calibra con **Calibración → Calibrar todo** (automático: revisas los recuadros y confirmas). Desde la 3.0.0 sirve cualquier resolución y puedes mover la ventana sin recalibrar.
6. Abre el autopiloto **antes de cargar el camión**. Si lo activas a mitad de camino, usa la tecla de saltar etapa (PAGEDOWN) para pasar a la ida o a la vuelta.
**Si actualizas desde una versión anterior:** copia los archivos `.py` nuevos encima de los viejos y **conserva tu `config.json`**. Al arrancar se actualiza solo: mantiene tu calibración del minimapa, el velocímetro, tus teclas y el backend, y guarda una copia en `config_vN_respaldo.json`. Si no tienes `config.json`, se crea uno con los valores por defecto (los de `config_ejemplo.json`).
- Pon GTA en **Ventana sin bordes** (borderless). En pantalla completa exclusiva la captura puede salir negra.
- Si el juego corre como administrador, abre la consola también **como administrador**. Si no, Windows bloquea las teclas simuladas.
- Usa la cámara en **primera persona** dentro del camión y **no muevas el ratón**, porque al mover la cámara gira el minimapa.

## 1) Calibrar (una vez por resolución)
```
python calibrar.py
```
Entra al juego (dentro del camión, primera persona, ruta visible) y pulsa **F11**. Se guarda `captura_calibracion.png`. Sal con **ALT+TAB**, pulsa ENTER en la consola y, ya con el ratón libre:
1. Marca el rectángulo del minimapa y pulsa ENTER.
2. Haz clic en la flecha del jugador y pulsa ENTER.
3. Haz 4 a 8 clics sobre la ruta roja. Lo que detecta se pinta en **verde**. Pulsa ENTER.
4. Marca el **velocímetro** amarillo ("50 KM/h"). Deja sitio a la izquierda para 3 cifras y pulsa ENTER. Si en la captura no se ve (camión parado), pulsa ESC para mantener la región por defecto, que está pensada para 1920x1080.

Para calibrar desde una captura guardada: `python calibrar.py --imagen captura.png`.

## 2) Probar sin conducir
```
python autopiloto.py --simular captura_calibracion.png
python autopiloto.py --simular grabacion.mp4
```
La línea **cian** apunta adonde va a girar y la **magenta** muestra la curva que viene.

## 3) Usarlo
```
python autopiloto.py --debug --log viaje.csv
```
| Tecla (por defecto) | Acción |
|---|---|
| INSERT | Activa o desactiva el autopiloto (suelta las teclas al instante) |
| RE PÁG | Modo lento ON/OFF (Experimental; para el puente estrecho) |
| F10 | Modo rápido ON/OFF (Experimental, 2.6.0: más velocidad y curvas más fluidas; puede chocar más) |
| AV PÁG | Pasa a la siguiente etapa si el programa se desfasó |
| FIN | Salir |
| **S** o **Espacio** | Tomas el control: el autopiloto se desactiva solo |
| F9 | Marca un hito para comentarlo en las observaciones (2.3.0) |

**Cambiar teclas:** desde la 2.2.0, en Ajustes → Cambiar teclas. También se puede editar `"teclas"` en `config.json`, por ejemplo `"activar": "F6"`. Nombres válidos: `F1`-`F12`, `A`-`Z`, `0`-`9`, `NUMPAD0`-`NUMPAD9`, `INSERT`, `DELETE`, `HOME`, `END`, `PAGEUP`, `PAGEDOWN`, `UP`/`DOWN`/`LEFT`/`RIGHT`, `PAUSE`, `NUMPAD_MAS`, `NUMPAD_MENOS`... Si escribes un nombre que no existe, la consola te dice cuál está mal. Evita F7 (oculta el HUD y con él el minimapa) y F8 (captura). HOME abre el overlay de Social Club.

Si reinicias a mitad de trabajo: `--tramo 1` (ir a A) o `--tramo 2` (volver a B).

## Ajuste fino (config.json)
La velocidad se controla leyendo el velocímetro, con objetivos de 80 km/h en recta (`objetivo_recta`), 40 en curvas normales (`objetivo_curva`), 24 en esquinas (`objetivo_curva_cerrada`) y 15 en modo lento; si ve dónde termina la ruta, va frenando hasta 20 (`objetivo_cerca_destino`). El HUD solo se actualiza cada ~0,6 s y con retraso, así que el programa **predice** la velocidad real. Si se pasa del objetivo **suelta el acelerador** en vez de frenar (en recta solo frena si va más de 12 km/h por encima). Antes de las curvas frena **a pulsos cortos** y espera a ver el efecto, porque los frenos de GTA son muy fuertes.

**Cómo dirige (v5):** parte del punto de la ruta más cercano al camión (fuera de la flecha blanca, que tapa la línea) y la recorre siguiendo su línea central (en `--debug` es la línea **cian** junto al camión y **naranja** más adelante). Mira dos cosas: hacia dónde apunta la ruta junto al camión (flecha magenta) y cuántos píxeles te has apartado de ella (`desvío`). La parte naranja solo sirve para frenar antes de las curvas. La consola muestra `rumbo`, `desvío` y `curva`.

| Síntoma | Qué cambiar (en config.json) |
|---|---|
| Zigzaguea en recta | Baja `control.kp` (0.016) o `cambio_max_por_seg` (1.8) |
| Se sale de la ruta / no gira lo suficiente a velocidad | Sube `control.kp` (0.024) o los últimos valores de `ganancia_por_velocidad` |
| Va siempre algo desplazado a un lado | `control.desplazamiento_carril_px`: −1.7 (por defecto, ≈1,3 m) = un poco a la izquierda de la línea; −2 más a la izquierda, −1 menos, 0 = sobre la línea |
| Se balancea de lado a lado lentamente | Baja `peso_desvio` (2.5) o sube `kd` (0.003) |
| Gira ANTES de la curva y roza el interior | Baja `vision.adelanto_giro_px` (12) |
| Gira tarde y se abre en la curva | Sube `vision.adelanto_giro_px` (20), sube `kp`, o baja `objetivo_curva` |
| Se acerca demasiado al centro de calles de doble sentido | Baja `calle.peso_correccion` (0.3) o `vision.calle_corr_max_px` (1.5) |
| Toma el mar u otras zonas grandes como calle | Baja `calle.ancho_max_calle_px` (12) |
| No detecta calles con el minimapa transparente | Baja `calle.claridad_sobre_fondo` (16) |
| Con remolque no alcanza a girar en esquinas | Baja `esquinas.objetivo_esquina_kmh` (8) o sube `abrir_antes_px` (3) |
| Detecta `FUERA DE CALLE` sin estarlo | Baja `calle.fuera_umbral` (0.2) o `calle.claridad_sobre_fondo` (20) |
| Frena por zigzags del GPS en rectas | Sube `vision.puntos_cuerda` (8) o `velocidad.curva_suave_grados` (25) |
| Rumbo raro en recta (consola muestra rumbo de ±10° yendo recto) | Sube `vision.radio_inicio` (16): la flecha tapa más ruta de lo previsto |
| Llega muy rápido a las curvas | Sube `vision.radio_anticipacion` (110) o baja `margen_sin_frenar_kmh` (3) |
| Se pasa de velocidad y luego frena | Sube `retraso_hud_seg` (0.5) o `soltar_antes_kmh` (6) |
| No llega a la velocidad objetivo / se queda corto | Sube `acelerador_crucero` (0.4) |
| Sigue acelerando por encima del objetivo en llano | Baja `acelerador_crucero` (0.2) |
| Entra rápido a las curvas | Baja `margen_sin_frenar_curva_kmh` (3) o sube `freno_max` (0.45) |
| Frena demasiado antes de las curvas | Sube `freno_espera_seg` (1.2) o baja `freno_pulso_seg` (0.2) |
| Va demasiado lento cuando hay curvas a lo lejos | Sube `kmh_extra_por_px` (0.6) |
| Frena demasiado tarde para curvas | Baja `kmh_extra_por_px` (0.3) |
| Va lento en rectas | Sube `objetivo_recta` |
| Gira al revés | `"invertir_direccion": true` |
| La velocidad de la consola no coincide con la del HUD (p. ej. 1 en vez de 17) | Pásame una captura con ese valor; prueba `--simular captura.png` |
| Velocidad en consola siempre 0 o rara | Recalibra la región del velocímetro (paso 4) o prueba `--simular captura.png` |
| No tienes velocímetro / falla | `"velocimetro": {"activo": false}`: usa acelerador fijo (`sin_velocimetro_*`) |

La consola y la ventana `--debug` muestran `velocidad actual/objetivo km/h (motivo)`. El motivo dice qué está limitando la velocidad: `recta`, `curva`, `curva cerrada`, `esquina`, `destino`, `fuera de calle`, `MODO LENTO`... El modo lento se apaga solo a los 90 s (`modo_lento_max_seg`). Con `--log viaje.csv` se guarda todo; si me lo pasas, lo ajusto.

**Mando virtual (recomendado):** instala `vgamepad` y pon `"backend": "mando"`. La dirección y el acelerador pasan a ser analógicos, y con un camión eso evita muchísimo los volantazos del teclado.
Con este modo, pulsar W/A/S/D o Espacio también te devuelve el control.

## Cambios de la v39
- **Descargado no detectado:** si en la ida la distancia salta de menos de 200 m a más de 1 km, el programa entiende que ya descargaste y pasa a la vuelta (tramo 2), aunque no haya visto la notificación. Antes la vuelta entera quedaba con las reglas de la ida.
- **Aviso "acción necesaria":** solo cuenta como trabajo nuevo después de "Trabajo completado". Si cancelas un trabajo a mitad, elige el tramo a mano en "Empezar en".
- **Grabaciones:** la ventana de guardar tiene un selector de **tramo** (camino a cargar, ida o vuelta). "Después de DESCARGADO" sirve para cualquier salida del punto A, hacia adelante o en reversa. Se pueden grabar en **tercera persona** (ver la sección de grabación).
- **Reglas del camino a cargar** (`inicio_comun`, tramo 0): esquina a la derecha a unos 150 m, más a la izquierda para abrir el giro.
- **Esquina a la salida del puente** (las tres rutas): sigue a la izquierda durante la esquina, en vez de volver a la línea, que lo hacía cortar por dentro.
- **Granja 2, ida:**
  - Farolas de Davis por la izquierda hasta 4,54 km; de 4,54 a 4,45 km, un poco a la derecha (55 km/h); hasta 4,30 km, 55 km/h.
  - Autopista: un poco a la izquierda en 2,96 km (muro) y en 2,24 km (cambio de ruta del GPS); un poco a la derecha en 2,05 km.
- **Granja 2, vuelta:** 3,68 km, a la izquierda y sin frenar por la bifurcación (cambio de carril).
- **Vuelta común:**
  - Árbol de Textile City: desde 2,30 km y más a la izquierda.
  - Strawberry (faroles y carteles): desde 1,48 km y algo más a la izquierda.
  - Esquina de Maze Bank: desde 1,06 km, un poco a la izquierda.
  - Punto final: un poco a la izquierda (postes) y 4 s recto antes de doblar (árboles).
- **Ruta nueva: Productos varios - Globe Oil** (3,26 km). Hasta 1,84 km usa las mismas reglas que Granja 2. A 64 m del punto A entrega el control. En la vuelta: esquina en bajada (1,66 km) a 28 km/h y curva de 1,47 km algo a la izquierda. Las reglas comunes de la vuelta valen desde 1,47 km (opción nueva `regreso_comun_desde`).

## Grabación de recorridos (v38)
Para los tramos donde el GPS no sirve: la entrada a las granjas sin caminos, la salida en reversa de Medicamentos y el punto final con árboles. Conduces tú una vez y el programa lo repite.

**Grabar**
1. Lleva el camión hasta donde quieres que empiece la repetición (por ejemplo, donde hoy te entrega el control, a unos 130 m de la granja) y detente.
2. Pulsa **● Grabar recorrido** en la interfaz. El estado pasa a **GRABANDO** (rojo). El programa no maneja: anota tus teclas W/A/S/D/espacio, la velocidad y la distancia, 12 veces por segundo.
3. Conduce el tramo como siempre. Para terminar, vuelve a pulsar Grabar o la tecla INSERT. Si llegas al punto y aparece la barra del juego, la grabación termina sola.
4. Sale una ventana para ponerle **nombre**, elegir **cuándo repetirla** y **qué hacer al terminar**:
   - *Al llegar a X m del punto*: donde empezaste a grabar. Es lo normal para la entrada a una granja. Reemplaza al "tramo manual" de la v37 si la distancia coincide (±60 m).
   - *Después de "camión CARGADO"*: reemplaza al retroceso automático.
   - *Después de "camión DESCARGADO"*: por ejemplo, la salida en reversa de Medicamentos.
   - *Punto final de la vuelta*: vale para todos los recorridos.
   - Al terminar: *parar y dejarme el control* o *seguir conduciendo con el GPS*.
5. Se guarda en la carpeta `grabaciones/` (un archivo JSON por grabación). Para borrar una, borra su archivo. Se cargan al iniciar el programa y también quedan disponibles al momento de guardarlas.

**Repetir**
- Cuando el camión llega al disparo, el estado pasa a **REPRODUCIENDO** (verde azulado). Mueve el volante como lo hiciste tú (con el mando virtual, subiendo de a poco como el teclado del juego) y ajusta el acelerador para ir a **la misma velocidad que ibas tú**.
- Se interrumpe sola, y te deja el control, si la velocidad se aleja más de 15 km/h de la grabada durante 3 s, o si el camión se queda parado 3 s cuando tú te movías (probable choque). También con S/espacio, como siempre.
- Si al grabar mirabas a otro punto cardinal que al repetir, avisa en el Registro: la repetición solo sirve si el camión llega igual que tú llegaste.
- Ajustes en `config.json` → `"grabacion"`: tope del volante (0,7), rapidez del volante, acelerador base y corrección por km/h, y los límites de seguridad.

**Tercera persona:** sí puedes grabar en tercera persona. La grabación solo anota tus teclas, la velocidad del HUD y la distancia; no usa la cámara. Dos cuidados:
- Antes de pulsar Grabar, deja la cámara detrás del camión y sin girarla, para que el punto cardinal que se guarda sea el del camión.
- Para **repetir**, sobre todo si al terminar sigue con el GPS, vuelve a la **primera persona**: el autopiloto necesita el minimapa como siempre.

**Consejos para grabar bien**
- Empieza y termina parado.
- Conduce despacio y con movimientos claros: la repetición sale mejor a 15–25 km/h que a 40.
- Haz una grabación por tramo (entrada de Granja 2, entrada de Granja 1, salida de Medicamentos, punto final) y nómbralas así.
- Si una repetición sale mal, bórrala y vuelve a grabar; no hace falta cambiar nada más.

## Cambios de la v37
- **Tramo manual en Granja 2:** a unos 130 m del punto A, que es la entrada a la granja sin caminos, el camión frena hasta parar y el autopiloto pasa a INACTIVO. En el Registro aparece "Tramo manual: llévalo tú". Para seguir, actívalo de nuevo cuando quieras. Si lo reactivas dentro de ese tramo, no vuelve a parar. En las reglas es la opción `entregar_control`.
- **Esquina a la salida del puente:** gira en un punto intermedio (`giro_tardio_px` 9, antes 12). Con 12 una vez giró demasiado pronto y chocó con las vallas.

## Cambios de la v36
Según las observaciones del viaje de las 05:57 (Granja 2, sin choques; solo un atasco por otro jugador):
- **Punto final (B):** antes de doblar hacia el punto avanza **3 segundos** recto, en vez de 10 m (`aprox_recto_seg`), y con más acelerador. Con la v35 casi se detenía en esa parte y después chocaba con los árboles.
- **Ida (Granja 2):**
  - Final de la subida de Autopia Parkway (4,88 km): un poco a la izquierda.
  - Separador de Strawberry (3,15 km): sin límite de velocidad. Lo sigue esquivando sobre la línea.
  - Vinewood Hills: la regla empieza antes, en 1,85 km (se salía a la derecha en 1,77 km), y lleva el camión más a la izquierda (−4 px).
- **Vuelta (Granja 2):** autopista de Vinewood Hills (3,85–3,60 km), un poco a la izquierda.
- **Vuelta (las dos granjas):**
  - Strawberry (1,37 km): un poco a la izquierda, por el cartel de la derecha.
  - Banning: la regla empieza en 740 m, justo después del poste de Maze Bank. Así cubre también la esquina a la derecha donde chocaba con los postes de madera, y ahí gira un poco más tarde.

## Cambios de la v35
Ajustes según las observaciones del viaje de las 05:33 (Granja 1, el primero sin ningún choque):
- **Ida:**
  - Curva de Banning: las esquinas se toman a 30 km/h (antes bajaba hasta 10–20) y sin el recorte extra "en bajada".
  - Esquina de Maze Bank Arena: a 28 km/h, en las dos granjas.
  - Separador de Strawberry: hasta 65 km/h.
  - Salida a Vinewood Park Drive (2,16–2,04 km): hasta 45 km/h, más a la izquierda y girando un poco más tarde. Antes llegaba a 75 km/h, frenaba de golpe y se pegaba a la derecha.
  - Recta de Señora Road (1,45–1,28 km): hasta 70 km/h y un poco a la izquierda.
  - Curva en bajada: hasta 65 km/h.
- **Vuelta (Granja 1):**
  - Señora Road (5,42 km) y Vinewood Hills (4,75 km): hasta 65 km/h.
  - Curva a la derecha de 5,08–4,90 km: hasta 60 km/h y un poco a la izquierda.
- **Vuelta (las dos granjas):**
  - Faroles de Strawberry: hasta 55 km/h y en un tramo más corto.
  - Curva de Banning con los postes de madera (660–500 m): hasta 45 km/h, bien a la izquierda y girando más tarde.
- **Punto final (B):** en los últimos 130 m avanza unos 10 m más en línea recta antes de doblar hacia el punto, por los árboles. Para esto hay una opción nueva en las reglas, `aprox_recto_m`.
- **Corrección:** se arregló un error de arranque en la detección de foco que solo aparecía en las pruebas.

## Cambios de la v34
- **Distancias como en el minimapa:** "1,70 km" desde 1 km y "740 m" por debajo. Así aparecen en el Registro, en la ventana de observaciones y en lo que se guarda al final del viaje. En el CSV (`dist_punto_m`) y en las reglas siguen en metros.
- **Banning (ida):** la regla de la curva sigue hasta su salida real (5,20 km en Granja 1 y 5,03 km en Granja 2). La subida "sin frenar" empieza recién ahí. Antes empezaba dentro de la curva, el camión salía demasiado rápido y se iba fuera de la calle. En la subida, si va torcido o hay una curva cerrada, puede frenar.
- **Ida, Granja 1:**
  - Autopista en Mirror Park (3,10–2,90 km): un poco a la izquierda.
  - Señora Road (1,85 km): hasta 60 km/h (antes 45).
  - Curva en bajada (1,15 km): hasta 60 km/h y un poco a la izquierda.
- **Vuelta:**
  - Paso sobre la autopista (3,97 km): hasta 60 km/h.
  - Esquinas muy cerradas de Señora Road (3,57 km) y Maze Bank (970 m): a 24–26 km/h en vez de 14–20.
  - Curva larga de Strawberry (1,70 km): al menos a 65 km/h.
  - Faroles y carteles de Strawberry (1,30 km): sobre la línea y hasta 50 km/h.
  - Poste de Maze Bank (780 m): hasta 40 km/h, siempre por la izquierda.
- **Opción nueva para las reglas:** `curva_larga_kmh`, la velocidad mínima para las curvas largas de ese tramo.

## Cambios de la v33
- **Usuario:** escribe tu nombre en el campo **Usuario** de la interfaz y queda guardado. Al final de cada archivo de viaje se anota quién lo hizo, con el recorrido y la hora (líneas que empiezan con `#`).
- **Observaciones:** cada vez que termina un trabajo, y también al detener o cerrar el programa, se pregunta **"¿Quieres hacer observaciones de este viaje?"**. Si respondes que sí, se abre una ventana con los **puntos críticos**: choques, atascos, tomas de control, bajadas de condición y falsos choques. Cada punto muestra:
  - la distancia, el lugar y la velocidad;
  - una **causa probable**, por ejemplo: "iba recto a 81 km/h: obstáculo que no sale en el minimapa", "iba unos 5 m a la derecha de la línea" o "atascado en una esquina".

  Puedes escribir lo que pasó en cada punto y una observación general. Todo se guarda al final del mismo archivo del viaje.
- **Otra ventana activa** (por ejemplo, el bloc de notas en la otra pantalla): con mando, el autopiloto **sigue manejando**, y ninguna tecla del programa cuenta mientras no vuelvas al juego. Eso incluye tomar el control, INSERT, Re Pág, Av Pág, Supr y Fin. Así puedes escribir sin que se desactive. Con control por teclado queda en pausa, porque las teclas irían a la otra ventana. El juego se reconoce por el título de su ventana (`"ventana_juego": "Grand Theft Auto"` en config.json).
- **Falsos choques:** si en ese momento no se ve el minimapa (por ejemplo, porque una ventana tapa el juego), una caída de la velocidad leída no cuenta como choque. Y si durante la marcha atrás el camión sigue avanzando a más de 20 km/h, la marcha atrás se cancela.
- **Esquina a la salida del puente:** en la v31 el valor estaba al revés y giraba aún más tarde. Ahora gira antes. Ojo: en `giro_tardio_px`, un número **mayor** hace que gire **antes**.
- **Subida de Autopia Parkway (ida, de Banning a Maze Bank Arena):** no pisa el freno ni frena por bifurcaciones, solo suelta el acelerador. Las reglas aceptan `sin_freno` y `sin_bifurcacion`.
- **Farolas de Davis Avenue:** en Granja 2 la regla estaba en la subida. Ahora está al comienzo de la avenida, en las dos rutas, a 40 km/h y por la izquierda.
- **Strawberry Avenue (ida):** se quitaron las reglas que frenaban sin obstáculo.
- **Vinewood Hills (Granja 2, 1.700–1.400 m):** más a la izquierda y sin el límite de 50 km/h. Ahí la ruta del minimapa se sale del camino y hay barreras y un cartel a la derecha.
- **Árbol de Textile City:** la regla ahora vale para la vuelta de las dos granjas.

## Cambios de la v32
- **Nombre del recorrido:** se ve en la interfaz ("Recorrido: Drogas - Granja 1"), en el Registro y en la columna `ruta` del CSV. El cargamento se lee del título de la barra ("Cargando drogas...") con el mismo lector de texto que la zona y la calle. Si la ruta no está guardada aparece, por ejemplo, "Medicamentos - desconocido (5.120 m)". Si no se pudo leer el cargamento, sale "(cargamento) - desconocido". Cada ruta de `rutas_base.json` tiene su `"cargamento"`, así no se confunden dos cargamentos con distancias parecidas.
- **Retroceso tras cargar:** sigue durando 1,8 s (en el último viaje fueron unos 0,5 m). Si la ruta sale torcida, retrocede con el volante hacia el otro lado para que la trompa quede apuntando a la ruta (`etapas_pantalla.retroceso_tras_cargar_volante`).
- **Puente:** las dos reglas lo llevan algo a la izquierda (−2 px), lejos de las farolas de la derecha. Antes se quedaba apuntando a la derecha sin corregir.
- **Banning (ida):** la curva cerrada sube de 30 a 40 km/h. El inicio ya no tenía límite.
- **Banning (vuelta):** la regla de la izquierda cubre de 700 a 230 m, toda la curva con los postes de madera de la derecha. Además ahí gira un poco más tarde.
- **Textile City (vuelta, Granja 1):** entre 2.250 y 2.080 m va algo a la izquierda por el árbol que sobresale, sin bajar la velocidad.

## Cambios de la v31
- **Rutas con nombre:** **Granja 1** (5.690 m: Circuito Redwood Lights, Vinewood Hills y la bajada) y **Granja 2** (5.530 m: autopista y camino de tierra hasta la granja del desierto). Así aparecen en el Registro y en el CSV.
- **Sobre la línea por defecto:** el desplazamiento normal vuelve a 0 (`control.desplazamiento_carril_px`). Solo va a la izquierda donde lo dice una regla:
  - el inicio de Banning y su curva, de ida y de vuelta;
  - las farolas de Davis y el poste de Maze Bank;
  - las autopistas con barreras a la derecha;
  - el paso sobre la autopista de Señora Road.

  En el separador entre Strawberry y la autopista va sobre la línea, y en el resto de Banning / Autopia Parkway, al centro.
- **Retroceso tras cargar:** 1,8 s (antes 0,9; casi no se notaba).
- **Esquina a la salida del puente:** se toma a 28 km/h y gira antes, en vez de seguir recto (ahí chocaba con el cartel). Las reglas pueden tener `esquina_kmh` y `giro_tardio_px` (menos = gira antes).
- **Ida por la ciudad más rápida:** Davis a 35 km/h y Strawberry a 55. Además, ahora empieza a bajar la velocidad unos 80 m antes de una regla con límite, sin frenar de golpe al entrar (`velocidad.regla_antes_m`, `regla_antes_kmh_por_m`).
- **Granja 2:** las distancias de las reglas están medidas en un viaje real (antes eran una estimación).
- **Aviso repetido del juego:** si tardas, el juego repite el aviso "acción necesaria" ("ahora tienes que regresarlo"). Ya no se toma como trabajo nuevo, salvo que el punto esté a menos de 600 m o el trabajo ya haya terminado (`etapas_pantalla.accion_inicio_max_m`).

## Cambios de la v30
- **Retroceso tras cargar:** con la notificación "camión CARGADO" y la ruta nueva, el camión retrocede recto un momento (0,9 s) antes de arrancar. Así tiene espacio para girar y enderezarse hacia el puente (`etapas_pantalla.retroceso_tras_cargar_seg`; 0 = no).
- **Más a la izquierda:** el desplazamiento normal pasa de −1,7 a −2,2 px (unos 1,7 m a la izquierda de la línea; `control.desplazamiento_carril_px`). Si lo habías cambiado tú, se mantiene tu valor.
- **Curvas largas más rápidas:** con 35° de giro total por delante va a unos 70 km/h, con 55° a unos 58 (`velocidad.objetivo_por_giro_total`).
- **Menos frena-acelera:** en GTA, soltar el acelerador ya frena unos 15 km/h por segundo. En curvas largas, reglas y rectas, el camión solo frena si el velocímetro **ya** marca más de 3 km/h sobre el objetivo, y en curvas largas tolera pasarse hasta 8 km/h soltando el acelerador. Antes frenaba solo por la predicción (por ejemplo, a 54 km/h con objetivo 56), y eso causaba los tirones. En esquinas, curvas cerradas y al llegar al punto sigue frenando por adelantado.
- **Autopista:** si la calle del HUD es una autopista, una bifurcación limita a 70 km/h en vez de 55 (`velocidad.objetivo_bifurcacion_autopista`).
- **Fin del trabajo:** solo con la notificación "Trabajo completado". Antes, si llegaba "descargado" con el autopiloto apagado, a veces lo daba por terminado al empezar la vuelta.
- **Reglas nuevas o cambiadas** (`rutas_base.json`):
  - Puente: despacio (20) solo al entrar; después hasta 40, casi al centro.
  - Inicio de Banning (GPS corrido a la derecha) y su curva cerrada: más a la izquierda.
  - Davis/Maze Bank: farolas por la **izquierda** (antes se pasaban por la derecha).
  - Separador de Strawberry: tramo más corto, a 55 km/h.
  - Autopista de Vinewood Hills: 70 km/h y más a la izquierda.
  - Vuelta, Señora Road (paso sobre la autopista, unos 3.960 m): 50 km/h, más a la izquierda y girando más tarde.
  - Vuelta, Davis/Banning/Autopia Parkway (650–200 m): más a la izquierda.
- **Reglas con `"anticipacion"`** (opcional, de 0,4 a 1,5): con menos de 1 el camión mira más cerca en ese tramo y gira más tarde.
- **Ojo:** si tienes un `rutas.json` propio, el programa usa ese archivo y no el nuevo `rutas_base.json`. Para usar las reglas nuevas, bórralo o cópiale los cambios.

## Rutas conocidas y reglas por lugar (v29)
Justo después de cargar, el programa **reconoce la ruta por la distancia inicial** que muestra el minimapa:

| Distancia inicial | Ruta |
|---|---|
| 5.690 m | Granja 1 (Droga → Circuito Redwood Lights) |
| 5.530 m | Granja 2 (Droga → Desierto de Grand Señora) |

El Registro dice "Ruta reconocida: …". Si la distancia no coincide con ninguna ruta conocida, dice "Ruta nueva (X m): todavía no hay reglas". Ese número sirve para añadirla.

Como la distancia al punto va bajando, sirve de "posición" en la ruta. Las **reglas** se aplican entre dos distancias: velocidad máxima y por dónde ir respecto a la línea (izquierda, derecha o encima). Cuando una regla empieza, el Registro lo dice ("Regla: Banning: curva cerrada a la izquierda (máx 30 km/h)") y la interfaz la muestra en "Lugar".

Reglas incluidas, sacadas de tus viajes:
- **Ida:** puente de Elysian Island (20 km/h, al centro); Banning, curva cerrada (30); Davis/Maze Bank, farolas en el centro (25, algo a la derecha); Strawberry Avenue y su separador (40–50, sobre la línea); Vinewood Este y Vinewood Hills (45–60).
- **Vuelta:** Señora Road y Vinewood Hills (55).
- **Final de la vuelta, igual para todas las rutas:** Strawberry (45) y el **poste gigante de Maze Bank** (30, por la izquierda).

**Editar o añadir reglas:** el programa trae `rutas_base.json`. Para tus propias reglas, copia ese archivo como **`rutas.json`** y edítalo. Si existe, se usa en su lugar y no se pisa al actualizar el programa. El formato está explicado en `rutas.py`. Cada regla es:
```
{"desde": 5500, "hasta": 5330, "max_kmh": 30, "desplazamiento_px": 0, "nota": "Banning: curva cerrada"}
```
(desde/hasta = metros al punto según el minimapa; desplazamiento: − izquierda, + derecha, 0 sobre la línea). Los incidentes de `viajes/incidentes.csv` dicen exactamente a cuántos metros pasó cada cosa.

## Correcciones generales (v29)
- **Curvas largas y suaves:** antes se tomaban a 80 km/h como si fueran "recta". Ahora frena según el giro total que se ve por delante (unos 65 km/h con 25°, 50 km/h con 45°; `velocidad.objetivo_por_giro_total`). En la interfaz aparece como "curva larga".
- **Volante a alta velocidad:** también gira con más fuerza cuando la curva ya se ve venir, no solo cuando el camión va torcido (`control.curva_rapida_peso_giro`).
- **Empuje hacia el centro de la calle gris:** limitado siempre, salvo que el camión esté fuera de la calle. En la Autopista de Los Santos, en Vinewood Hills, estaba al máximo hacia la derecha.
- **Menú y barra de progreso:** no se les hace caso si el camión va a más de 12 km/h (`etapas_pantalla.barra_max_kmh`). Una falsa "barra" en movimiento reiniciaba el trabajo a mitad de la vuelta.

## Notificaciones del trabajo y condición del camión (v28)
**Notificaciones:** el programa reconoce las notificaciones de "Trabajo de camionero" que aparecen encima del minimapa:

| Notificación | Qué hace el programa |
|---|---|
| Acción necesaria — "El camión ha sido **cargado**…" | etapa: ir al punto de entrega A |
| Acción necesaria — "El camión ha sido **descargado**…" | etapa: volver a la zona de trabajo B |
| Acción necesaria (sin palabra verde, al empezar) | etapa: ir a cargar |
| **Trabajo completado** | etapa 7: Terminado (suelta los controles) |

Se leen **también con el autopiloto desactivado**. Si llevas tú el camión un rato (por ejemplo, a la granja), la etapa no se desincroniza. Se reconocen por los colores (subtítulo naranja o verde, y el largo de la palabra verde "cargado" o "descargado"), sin instalar nada; si hay OCR, el texto lo confirma. Cada notificación queda anotada en el registro y en `incidentes.csv`. Se desactiva con `hud_texto.notificaciones: false`.

**Condición del camión:** se lee el "NN%" con el ícono del motor (abajo a la derecha). Aparece en la interfaz ("Lugar: … | condición 97%"), en cada fila del viaje (columna `condicion`) y en cada incidente ("choque … [cond 97%]"). Si baja 2 puntos o más (`hud_texto.condicion_aviso`), se anota como incidente: "condición 100->97%", con el lugar. Los valores por encima del 100 % (fallo del juego) se registran tal cual.

## Curvas en bajada y volante a alta velocidad (v28)
- **Bajada:** si el camión gana velocidad casi sin acelerar, o no la pierde aunque frene, el programa lo nota ("Bajada: curvas más despacio") y durante unos segundos va **10 km/h más despacio en curvas y esquinas** (`velocidad.bajada_reduccion_kmh`), sin subir a 100 en rectas largas.
- **Volante más decidido** a partir de 45 km/h cuando la carretera ya dobla: con 10° el giro es normal y con 25° es 1,6 veces más fuerte (`control.curva_rapida_kmh`, `curva_rapida_ganancia`). Antes, en las curvas de Señora Road y Vinewood Hills, el volante casi no se movía y el camión se salía.

## Llegada al punto y marcador de destino (v27)
- **La distancia del minimapa manda.** Si marca más de 8 m (`etapas_pantalla.llegada_m`), el camión nunca se da por llegado, aunque el marcador no se vea porque lo tapa la línea roja o parezca estar encima. Sigue avanzando despacio hasta que aparezca el menú o la barra.
- **Si se queda parado lejos del punto**, primero acelera fuerte 2,5 s (`empuje_seg`, `empuje_acelerador`) y solo después retrocede para otro intento. Antes retrocedía enseguida, incluso con el punto delante.
- **Marcador tapado por la ruta:** el marcador se reconoce también cuando la línea roja del GPS pasa por encima y tapa la V negra (círculo rojo "grueso" con borde oscuro). Los puntos lejanos dibujados en el borde del minimapa no cuentan.
- **En la vista del minimapa** (interfaz, modo depuración) el marcador detectado aparece con un **círculo morado** por encima de todo, con la palabra "destino" y los metros del HUD. Si el programa lo descartó por parecer falso, el círculo es gris y dice "descartado".

## Menos empuje hacia la derecha (v27)
El ajuste que acerca el camión al **centro de la calle gris** del minimapa ahora solo puede apartarlo 0,8 px de la línea del GPS (`calle.correccion_max_px`). En calles anchas y autopistas, ese "centro" quedaba a la derecha de la línea y llevaba el camión contra barandas, carteles y farolas (Vinewood Hills, el puente después del punto de carga). Si el GPS va fuera de la calle, se sigue usando la corrección completa.

Además, el desplazamiento a la izquierda se quita si la **curva total que se ve por delante** va hacia la izquierda desde 12°, no solo la de los primeros metros. Es lo que falló en Strawberry Avenue.

## Etapas confirmadas por pantalla (v26)
El tramo ya **no avanza solo porque la ruta desaparezca o reaparezca**. Solo avanza cuando el juego lo confirma: aparece el **menú de carga** o la **barra** "Cargando/Descargando", o la distancia del minimapa salta a un punto nuevo (por ejemplo, de 10 m a 5.690 m). Así no se salta etapas al llegar con la ruta todavía visible.

- Si llega al punto y el juego no reacciona, pero la ruta sigue indicando el mismo punto, el programa dice "Aún no llego al punto (X m): sigo" y continúa acercándose.
- Si se queda **parado junto al marcador**: con la distancia del minimapa en **8 m o menos** (`etapas_pantalla.llegada_m`) se considera en el punto y espera al juego. Si está más lejos, algo lo bloquea: retrocede y lo intenta otra vez, hasta 3 veces (`intentos_llegar`). Después te pide que lo lleves tú.
- **Mientras espera** (estado ESPERANDO_RUTA) puedes mover el camión con W/A/S/D sin que se desactive. En cuanto aparezca el menú o la barra y luego la ruta nueva, sigue solo.
- En el punto final (B): cuando termina la barra y no hay ruta nueva, da el trabajo por completado. Si aparece una ruta nueva lejana, empieza un trabajo nuevo desde el tramo 0.
- `etapas_pantalla.confirmar_etapas: false` vuelve al comportamiento anterior.

## Separadores de vías y bifurcaciones (v26)
- **Vuelve a la línea roja** (quita el desplazamiento a la izquierda) antes de cualquier curva hacia la izquierda desde **12°** (`control.desplazamiento_quitar_curva_grados`). Antes solo lo hacía desde 30°. Justo ahí suelen estar los separadores, como el del final de Strawberry Avenue.
- **Bifurcaciones:** si el minimapa muestra que la calle se abre en dos delante (una franja de calle que se separa poco a poco de la de la ruta), baja a **55 km/h** (`velocidad.objetivo_bifurcacion`, 0 = desactivado) y va sobre la línea hasta pasarla. En la interfaz aparece el motivo "bifurcación". Las calles laterales de un cruce no cuentan.
- El viaje (`viajes/*.csv`) guarda también `bifurcacion`, `desvio_cerca` y `desplazamiento`, para revisar estos puntos.

## Lugar: distancia, punto cardinal, zona y calle (v25)
El programa lee del HUD, sin tocar el juego:
- la **distancia al próximo punto** que muestra el minimapa ("→ 121m", "↑ 4.42km") y su flecha;
- el **punto cardinal** (N, NE, SO...) y el **nombre de la zona y la calle** de la caja junto al minimapa.

Se ve en la interfaz ("Lugar: → 121m | N | Desierto de Grand Señora | Autopista de Señora"), se guarda en cada fila del viaje (`viajes/*.csv`) y en **`viajes/incidentes.csv`**, un archivo acumulado con cada choque, atasco, maniobra, desactivación y llegada, con su lugar. Al cerrar el autopiloto se muestra en el Registro la lista de **lugares con más incidentes**. Sirve para encontrar los sitios conflictivos y, más adelante, crear rutas alternativas (atajos) para ellos.

La distancia y el punto cardinal se leen sin instalar nada. Para el **nombre de zona y calle** hace falta un lector de texto (OCR):
- recomendado: `pip install winsdk` (usa el OCR que trae Windows);
- si `winsdk` no se instala en tu versión de Python: `pip install winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Foundation`;
- o Tesseract-OCR + `pip install pytesseract`.

El Registro dice al arrancar cuál se usa. Sin OCR, cada zona/calle nueva se guarda como imagen en la carpeta `zonas/` con un código (p. ej. `[z1-7209]`), que es el que aparece en los registros.

Ajustes en `hud_texto`: `activo`, `cada_seg` (1), `registrar_incidentes`, `destino_lejos_m` (150: si el punto está más lejos, no frena "por destino" aunque la ruta se vea corta) y las regiones `region_distancia` / `region_zona` (relativas al minimapa calibrado; solo si cambias la interfaz del juego).

**Por qué se desactiva:** ahora cada desactivación queda escrita en el Registro y en `incidentes.csv` con su causa: tecla de activar, control manual (tecla S o ESPACIO pulsada), o "no consigue tomar el giro" (4 maniobras seguidas en 40 s).

## Llegar al punto (v25)
Al final del tramo va al marcador a **20 km/h** sin frenar (el juego detiene el camión al llegar). Si el camión se queda parado junto al marcador 2,5 s, lo da por llegado y espera al juego, en vez de quedarse acelerando. `etapas_pantalla.objetivo_aproximar_kmh` (20) y `parado_es_llegada_seg` (2.5). Cerca del destino ya no baja de 30 km/h (`velocidad.objetivo_cerca_destino`).

## Curvas a velocidad pareja (v25)
- El acelerador ahora es **proporcional y suave**: lleva el acelerador de crucero más una corrección, y **aprende** cuánto acelerador necesita de verdad el camión cargado (`ki_acelerador`). Antes alternaba entre 0,2 y 1,0 en las curvas, y el camión frenaba con el motor y volvía a acelerar.
- El acelerador baja como mucho 1,5 por segundo y sube 1,0 por segundo; tras frenar no vuelve a acelerar fuerte en 0,8 s.
- Un fotograma suelto de "curva" ya no baja el objetivo (`objetivo_ignorar_fotogramas`, 2).
- Curvas y esquinas algo más rápidas: curva 60, curva cerrada 40, esquina 20, esquina muy cerrada 14 km/h, y la tabla `objetivo_por_tasa_giro` un 5 % más alta.

Si en las curvas se abre demasiado, baja `objetivo_por_tasa_giro` o `objetivo_curva_cerrada`. Si aún oscila, baja `kp_acelerador` a 0.02.

## Velocidad más pareja (v24)
Los camiones frenan mucho con el motor cuando se suelta el acelerador, y el velocímetro del HUD llega con retraso; por eso antes iba acelerando y frenando (sobre todo a 15–30 km/h). Ahora:
- por encima del objetivo **suelta el acelerador poco a poco** (`soltar_progresivo_kmh`, 8) en vez de soltarlo de golpe;
- **anticipa** hacia dónde va la velocidad (`amortiguacion_seg`, 0.25): si sube rápido, acelera menos antes de llegar; si baja rápido, vuelve a acelerar antes;
- a velocidades bajas (≤30) no frena salvo que se pase más de 9 km/h (`margen_sin_frenar_lento_kmh`);
- el refuerzo de **subida** ya no se activa justo después de frenar ni mientras la velocidad va bajando (eso provocaba los acelerones a fondo), y tiene un tope (`subida_refuerzo_max`, 0.5).

Si aún da tirones, sube `amortiguacion_seg` a 0.35. Si tarda en llegar a la velocidad, bájalo a 0.15.

Además se ignoran los **falsos marcadores** que aparecen de golpe pegados al camión (sombras junto a la flecha), que podían frenarlo a 20 km/h sin motivo. El registro de viaje (`viajes/*.csv`) guarda ahora también la distancia al marcador y el fin de la ruta.

## Rectas largas: 100 km/h (v23)
En rectas largas y despejadas (la ruta sigue recta en todo el minimapa durante 2 s, sin curvas, esquinas ni destino a la vista) sube a **100 km/h** (`velocidad.objetivo_recta_larga`; pon 80 para desactivarlo). En el resto sigue el máximo de 80 (`objetivo_recta`). En cuanto aparece una curva baja de nuevo. Ajustes: `recta_larga_px` (90: largo de recta necesario), `recta_larga_giro_max` (8°) y `recta_larga_seg` (2).

## Calles del minimapa (v10; reactivado en v18)
El programa detecta las calles grises del minimapa (en `--debug` se ven en **azul**):
- **Calles estrechas** (más anchas que la línea roja pero menos de 12 px): se acerca un poco al centro de la calle, como máximo 2,5 px (punto blanco en `--debug`). Así no se sale por el lado.
- **Avenidas anchas:** sigue el GPS tal cual, para no meterse en el bandejón central.
- **GPS fuera de la calle:** si la línea roja va por fuera y hay una calle paralela al lado, se acerca a ella.
- **Fuera de calle:** si delante del camión no hay calle ni ruta, aparece `FUERA DE CALLE` en la consola, baja a 20 km/h y corrige con más fuerza para volver.
Se ajusta en `"calle"` de `config.json`. Con `"activo": false` se desactiva todo esto.

## Cómo gira (v15)
Por defecto usa el modo **persecución** (`control.modo_direccion: "persecucion"`): apunta a un punto de la ruta a unos 27 px por delante en el minimapa, más lejos cuanto más rápido va. Es la forma en que giras tú: lo medí en tu video de conducción manual, con una correlación de 0,79 frente a 0,68 del método anterior, que giraba ~1 s antes.
- Gira **antes de tiempo**: baja los valores de `persecucion_px_por_velocidad`, por ejemplo `[[0,17],[30,21],[60,24],[90,30]]`.
- Gira **tarde** o se abre: súbelos.
- Gira **poco** o **mucho**: ajusta `kp_persecucion` (0.009–0.014).
- Para volver al método anterior: `"modo_direccion": "rumbo"`.

**Ir un poco a la izquierda (v23):** el camión va unos 1,7 px (≈1,3 m) a la **izquierda** de la línea roja, donde suele haber menos postes y señales (`control.desplazamiento_carril_px`, −1.7). Antes de una curva o esquina **a la izquierda** vuelve solo a la línea, para no cortar por dentro; en las de la derecha se mantiene a la izquierda, lo que abre el giro y lo aleja de los postes de la esquina.

**Tendencia a ir hacia un lado (v22):** si en rectas el camión sigue desviado hacia el mismo lado, una corrección lenta lo va llevando a la línea (`control.integral_desvio_grados_px_seg`; 0 = desactivado).

**Mantenerse sobre la línea en curvas (v17):** además de apuntar al punto, corrige la distancia lateral a la línea de ruta, medida ajustando un círculo a la curva. En curvas cerradas también mira más cerca, para no cortar por dentro.
- Si en curvas **aún se mete hacia dentro**, sube `persecucion_desvio_grados_px` (1.2) o baja los factores de `persecucion_acortar_en_curva`, por ejemplo `[[0,1.0],[20,0.8],[40,0.6]]`.
- Si **se abre hacia fuera** o se balancea, baja `persecucion_desvio_grados_px` (0.5).

## Zona muerta del mando (v18) — importante para ir centrado
GTA **ignora los movimientos pequeños del stick**. Sin compensarlo, las correcciones finas del autopiloto no hacían nada: el camión se quedaba varios metros a un lado de la línea del GPS y serpenteaba. Ahora cada corrección se suma a la zona muerta (`control.mando_zona_muerta`, 0.20 por defecto).

**Medirla** (una vez): en la interfaz, pulsa **"Medir zona muerta (mando)"**.
1. Pon el camión **parado en un sitio abierto y llano**, como un estacionamiento grande, en primera persona.
2. Acepta y vuelve al juego en 5 s.
3. El camión avanza despacio unos 1–2 minutos haciendo giros pequeños a ambos lados, y guarda el valor en `config.json`.
4. Para cancelar, pulsa S o ESPACIO.

Si el camión **da pequeños volantazos** en recta, baja el valor (0.15); si **se queda desviado** de la línea, súbelo (0.25). Solo afecta al modo mando.

## Giro tardío en esquinas (v20)
En esquinas de 55° o más, el camión **sigue recto hasta llegar a la esquina y entonces gira a tope**, como un camionero, en lugar de empezar a girar antes. Calcula dónde está la esquina aunque la tape la flecha del minimapa.
- `esquinas.giro_tardio_px` (7) es la distancia a la que empieza a girar. **Más bajo = gira más tarde**; si se abre demasiado al salir, súbelo (9–10).
- `esquinas.giro_tardio_ganancia` (1.8) es la fuerza del volante en la esquina.
- **Subidas:** si el camión va lento y no gana velocidad, el acelerador sube poco a poco (`velocidad.subida_refuerzo_por_seg`). Solo da marcha atrás si con el acelerador casi a fondo no se mueve durante 3 s.
- **Velocidades en curva** (v21): curva normal 58 km/h, curva cerrada 38 km/h y esquina 18 km/h (12 si es de 110° o más).
- **Giro en esquinas** (v21): empieza a 6 px y con fuerza 1.4, para un giro más abierto que no se pegue a la berma. Para abrirlo más, baja `giro_tardio_ganancia` (1.2).
- **Esquinas muy cerradas, calles angostas** (v23): en esquinas de 80° a 110° avanza más antes de girar (empieza a 3 px: `giro_tardio_muy_cerrada_px`). Si aún choca la esquina, bájalo a 2; si se pasa de largo, súbelo a 4–5.

## Esquinas cerradas (v11)
Para camiones largos o con remolque:
- Antes de una esquina de 75° o más baja a **12 km/h** (8 km/h si es de 110° o más). Desde la v19 **no se abre hacia fuera**: sigue el centro de la ruta. Para volver a abrirse, pon `esquinas.abrir_antes_px` en 2.
- Si se pasa la esquina y la ruta le queda detrás o al lado (más de 110°) yendo despacio, hace una **maniobra**: marcha atrás girando al revés y vuelta a avanzar con el volante a tope, como un giro en tres puntos. Si tras 6 intentos en 40 s no lo consigue, se desactiva y avisa para que tomes el control.
Se ajusta en `"esquinas"` de `config.json` (`objetivo_esquina_kmh`, `abrir_antes_px`, `maniobra_reversa_seg`…).

## Carril (v13, experimental)
El programa puede mirar la carretera en la imagen del juego para **centrarse en el carril**, algo que el minimapa no permite. El minimapa sigue decidiendo hacia dónde ir; el carril solo hace la corrección fina.

**Calibrar** (una vez por cámara: primera persona y tercera persona dan trapecios distintos):
```
python calibrar.py --solo carril
```
1. Conduce por una **recta**, **centrado en tu carril**, y pulsa F11.
2. Haz clic en las líneas que limitan tu carril: **1** abajo-izquierda, **2** arriba-izquierda, **3** arriba-derecha y **4** abajo-derecha. "Abajo" es justo delante del capó; "arriba", unos metros más adelante, no en el horizonte.
3. Te muestra la vista desde arriba: las dos líneas deben quedar verticales y paralelas, con el desvío cerca de 0.

**Centro automático (v21):** el centro del carril se ajusta solo con la línea del GPS. Cuando el GPS indica que vas centrado en una recta, lo que mide la cámara en ese momento se toma como desplazamiento de calibración (`carril.sesgo`). El valor se guarda al detener el programa, así que da igual si al calibrar no ibas perfectamente centrado.

**Uso:**
- Con `--debug` se abre la ventana **"carril (debug)"** con la vista desde arriba.
- La consola muestra `CARRIL` cuando lo está usando para dirigir.
- Solo dirige con el carril si la confianza es alta (≥ 0,75), en rectas o curvas suaves, a más de 15 km/h y lejos de esquinas.
- **SUPR** (`teclas.carril`) lo activa y desactiva al momento.
- **Ventanas de depuración:** no las pongas encima de la carretera del juego, porque la captura las vería.
- **Probar sin conducir:** `python autopiloto.py --simular video.mp4` usa tus grabaciones.

| Síntoma | Qué cambiar (`"carril"` en config.json) |
|---|---|
| Casi nunca aparece `CARRIL` | Baja `conf_min` (0.6) o `ipm_pixeles_min` (12); recalibra el trapecio |
| Detecta líneas que no son (sombras, barreras) | Sube `contraste_min` (30) |
| Corrige poco o muy lento dentro del carril | Sube `peso_grados` (16) o baja `filtro_correccion` (0.88) |
| Zigzaguea dentro del carril | Baja `peso_grados` (8) o sube `filtro_correccion` (0.95) |

## Reconocimiento de etapas en pantalla (v22)
El programa mira la pantalla cada ~0,4 s y reconoce:
- el **menú "CARGAR CAMIÓN"**: suelta los controles y en el registro aparece "elige el cargamento";
- la **barra "Cargando…" / "Descargando camión…"**: espera mientras el juego tiene el control y la interfaz muestra el porcentaje;
- el **marcador de destino** del minimapa (círculo rojo con flecha negra): frena al acercarse.

**Llegar al marcador (v23):** al final de cada tramo, cuando la ruta roja se acaba, el camión **va directo al marcador** (desde v25 a 20 km/h) hasta entrar en él, y entonces para y espera al juego (menú de carga, barra o la nueva ruta). Si el marcador queda muy de lado o detrás, hace marcha atrás para encararlo. En el punto B termina el trabajo. Ajustes en `etapas_pantalla`: `aproximar_marcador` (true/false), `aproximar_px` (35), `llegar_px` (4: más alto = para antes), `objetivo_aproximar_kmh` (10).

Cuando la barra termina y aparece la nueva ruta, sigue con la siguiente etapa: cargar → ir al punto A → descargar → volver al punto B. Se desactiva con `"etapas_pantalla": {"activo": false}`.

## Atascos y choques
Si la velocidad cae de golpe sin haber frenado (choque) o acelera a fondo 3 s sin moverse, da **marcha atrás suave** durante 4 s (más si se repite), a unos 6 km/h como máximo (`atasco.reversa_kmh_max` y `reversa_fuerza`), girando hacia el lado contrario al que quiere ir, para que el morro apunte a la ruta. Si vuelve a atascarse en menos de 15 s, retrocede más tiempo y prueba girando hacia el otro lado. Se ajusta en `"atasco"` de `config.json`.
**Choque al doblar (v23):** si choca mientras gira (por ejemplo, contra un poste por dentro de la curva), retrocede girando hacia ese mismo lado para alejar el morro del obstáculo y luego **avanza casi recto unos 5 m** antes de volver a girar (8, 11 y 14 m si vuelve a chocar en el mismo sitio). Ajustes: `atasco.recto_tras_choque_m`, `recto_tras_choque_extra_m` y `recto_tras_choque_volante`.

Si va fuera de la ruta (más de 8 px de desvío) o muy torcido respecto a ella, baja a 30 km/h hasta volver a centrarse.

## Limitaciones de esta fase
- No ve obstáculos (otros jugadores, tráfico): para eso están F8 y S/Espacio.
- Si abres el mapa grande o se superpone algún menú sobre el minimapa, se pausa o se confunde.

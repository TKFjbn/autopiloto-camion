# Publicar una versión en GitHub (para quien mantiene el programa)

Repositorio público: **TKFjbn/autopiloto-camion**. El programa de cada jugador consulta ahí cuál es la última
versión y, si es más nueva que la suya, ofrece actualizar. Todo esto se hace en el navegador, en GitHub.

## Una sola vez: subir el programa al repositorio
1. En el repositorio, el contenido de la carpeta `Autopiloto/` va en la raíz: `programa/`, `datos/`,
   `Autopiloto.bat`, `Autopiloto (administrador).bat`, `Instalar librerias.bat`, `CAMBIOS.md`, `LEEME.md`,
   `PROMPT_CALIBRACION.md`, `PUBLICAR.md`.
2. **No subas** `mi_equipo/` (tu calibración y tus preferencias), `viajes/` ni las carpetas `__pycache__`.
   Con git, crea un archivo `.gitignore` en la raíz con estas líneas:
   ```
   mi_equipo/
   viajes/
   __pycache__/
   *.nuevo
   ```
3. Con git (desde la carpeta `Autopiloto`):
   ```
   git init
   git add .
   git commit -m "Programa 3.1.0"
   git branch -M main
   git remote add origin https://github.com/TKFjbn/autopiloto-camion.git
   git push -u origin main
   ```
   Sin git: en el repositorio, **Add file → Upload files** y arrastra el contenido de la carpeta (sin `mi_equipo/`
   ni `viajes/`).

## Cada versión nueva (lo que hace que a los demás les aparezca el aviso)
1. Recibe el .zip de la versión (`autopiloto_camion_X.Y.Z.zip`). Descomprímelo y sube los archivos nuevos al
   repositorio (o `git add .` / `git commit` / `git push`).
2. En GitHub: **Releases → Draft a new release** (o «Create a new release»).
3. **Choose a tag → escribe `vX.Y.Z`** (por ejemplo `v3.1.1`) → «Create new tag». El número tiene que ser el mismo
   que `VERSION` en `programa/version.py`.
4. **Title:** `Programa X.Y.Z`.
5. **Description:** pega la sección de esa versión de `CAMBIOS.md`. Es el texto que verá cada jugador en la ventana
   de actualización, así que escríbelo para quien juega, no para quien programa.
6. **Adjunta el .zip** (`autopiloto_camion_X.Y.Z.zip`) arrastrándolo a «Attach binaries». Es lo que el programa
   baja. Si no lo adjuntas, usa el zip automático de GitHub, que también sirve mientras `programa/` y `datos/`
   estén en la raíz del repositorio.
7. Deja marcado **Set as the latest release** y **no** marques «pre-release». Pulsa **Publish release**.
8. Comprueba: en un programa con una versión menor, Ajustes → Versión y carpetas → «Buscar actualizaciones».

## Cosas a tener en cuenta
- Solo cuenta la **última release publicada** (no borradores ni pre-releases).
- Una actualización **solo de datos** (rutas, grabaciones) también necesita subir el número del programa
  (por ejemplo de 3.1.0 a 3.1.1) y su release, porque el programa compara el número del programa. Si el código no
  cambió, el .zip lleva el mismo `programa/`.
- Al actualizar, el programa guarda una copia de lo que reemplaza en `mi_equipo/respaldos/actualizacion_…/`. Si algo
  sale mal, esa carpeta tiene el programa y los datos de antes.
- Quien no tenga internet puede usar «Actualizar desde .zip…» con el mismo .zip.

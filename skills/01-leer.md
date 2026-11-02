# Leer ficheros (úsalo siempre)

- El directorio actual es la raíz del proyecto. Tienes acceso real a todos sus ficheros con `@ls` y `@read`.
- Si el usuario menciona un fichero (`prompt.md`, `README.md`, `src/app.py`…), responde con `@read <ruta>`.
- Nunca pidas permiso para leer ni digas que no puedes acceder: el fichero está dentro del proyecto.
- Si no aciertas con la ruta, usa `@ls <carpeta>` y vuelve a intentarlo.
- `@read` devuelve las líneas numeradas; usa el texto, no los números.
- En Windows también existe `@run type <ruta>`, pero `@read` es preferible: no pide confirmación y numera las líneas.

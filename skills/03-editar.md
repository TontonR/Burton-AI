# Editar sin romper nada

- Antes de sobrescribir un fichero existente, léelo con `@read`. Para crear un fichero nuevo, no hace falta leerlo antes.
- Cambia solo lo que pide el usuario; conserva el resto tal cual.
- `@write` reescribe el fichero completo: incluye todo, sin vallas de código ni números de línea, y cierra con `@endwrite`.
- No escribas si el usuario solo pide información, un plan o una explicación.

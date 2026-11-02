# burton_ai

Agente de código mínimo sobre Ollama. Solo necesita Python 3.12+ y `prompt_toolkit` para la consola interactiva.

La idea es no repetir el problema de las herramientas grandes: prompt de ~200 tokens, sin JSON de herramientas y con streaming. El modelo responde con directivas de texto, el programa las ejecuta y le devuelve el resultado hasta que escribe `@done`.

## Instalación

```powershell
python -m pip install -r requirements.txt
```

Requiere Ollama arrancado (o lo arranca solo) y un modelo descargado:

```powershell
ollama pull qwen2.5-coder:14b
```

Si no está instalado: `winget install Ollama.Ollama` o `irm https://ollama.com/install.ps1 | iex`.

## Uso

```powershell
# desde cualquier carpeta, para trabajar sobre esa carpeta
burton

# desde la carpeta del proyecto en el que quieras trabajar
python C:\ruta\a\burton_ai\burton.py

# opciones
burton --root C:\otro\proyecto --model qwen2.5-coder:14b --plan

# automatización desde agentes (el turno corre en segundo plano)
burton --talk "Revisa los tests y corrige el fallo"
burton --status
burton --response
burton --wait
burton --stop
```

El comando `burton` usa Python 3.12 y toma como raíz el directorio actual; también acepta `--root` para elegir otra carpeta. La interfaz externa mantiene una conversación por carpeta y permite enviar un turno, consultar el estado/respuesta, esperar, compactar y detener. `--status` devuelve JSON; `--response` devuelve texto parcial o final, y `--wait` espera a que termine. Si el mismo proyecto se controla desde otra carpeta, pasa siempre la misma ruta con `--root`. Si Windows no encuentra el comando en una terminal que ya estaba abierta, abre una nueva para que actualice el `PATH`.

Operaciones externas disponibles: `--talk TEXTO`, `--response`, `--status`, `--wait [--timeout SEGUNDOS]`, `--compact`, `--stop`, `--new`, `--toggle-plan`, `--models [NOMBRE]`, `--sessions [ID|N]` y `--subagents [N]`. Para comandos que soliciten `@run`, `--status` muestra el comando y su motivo; responde con `--approve` o `--deny`. El worker no aprueba comandos por sí mismo.

## Consola

- Al escribir `/` aparece el autocompletado de comandos; Tab o Enter aceptan la sugerencia.
- `/compact` resume los objetivos, restricciones, decisiones y siguientes pasos y sustituye el historial por ese resumen. No altera archivos.
- Después de cada respuesta se muestra el número real de tokens de entrada que Ollama procesó y el porcentaje del contexto configurado; también se repite antes del siguiente mensaje.
- Antes de ejecutar un comando, Burton enseña qué hará, el comando y la tarea que lo motiva; tú decides si permitirlo.
- `Enter` envía. En la terminal integrada de VS Code, `Shift+Enter` y `Ctrl+J` insertan una línea nueva sin ocultar el panel.
- `Ctrl+Backspace` borra la palabra anterior. `Ctrl+S` abre el menú de subagentes.
- La respuesta se pinta como markdown básico: `**negrita**`, `` `código` ``, títulos con `#` y bloques de código con vallas de tres backticks.
- Historial persistente con las flechas arriba/abajo.

**Atajos en Windows Terminal**: la aplicación reconoce `Esc+Enter` como nueva línea y `Ctrl+W` como borrar palabra. Windows Terminal puede configurarlos en `settings.json` (dentro de `actions` unos ids, y sus teclas en `keybindings`):

```json
// actions
{
    "command": { "action": "sendInput", "input": "\u001b\r" },
    "id": "User.sendInput.ShiftEnter"
},
{
    "command": { "action": "sendInput", "input": "\u0017" },
    "id": "User.sendInput.CtrlBackspace"
}

// keybindings
{ "id": "User.sendInput.ShiftEnter", "keys": "shift+enter" },
{ "id": "User.sendInput.CtrlBackspace", "keys": "ctrl+backspace" }
```

`\u001b\r` es Alt+Enter (nueva línea) y `\u0017` es Ctrl+W (borrar palabra). Abre una pestaña nueva después de guardar. `Alt+Enter` a secas abre pantalla completa en Windows Terminal.

En la terminal integrada de VS Code o Cursor, `Shift+Enter` debe enviar `Esc+Enter` y `Ctrl+J` un salto de línea. Los atajos están en el archivo de preferencias del editor (`Preferences: Open Keyboard Shortcuts (JSON)`):

```json
{
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "when": "terminalFocus",
    "args": { "text": "\u001b\r" }
},
{
    "key": "ctrl+j",
    "command": "workbench.action.terminal.sendSequence",
    "when": "terminalFocus",
    "args": { "text": "\n" }
},
{
    "key": "ctrl+backspace",
    "command": "workbench.action.terminal.sendSequence",
    "when": "terminalFocus",
    "args": { "text": "\u0017" }
}
```

## Directivas

El modelo escribe, una por línea:

```
@ls <ruta>
@read <ruta> [inicio-fin]
@write <ruta>
contenido completo del fichero
@endwrite
@run <comando>
@agent <tarea>
@done
```

- `@read` limita a 200 líneas por lectura; el resto se pide con rangos.
- El programa ejecuta solo la **primera** directiva de cada respuesta y descarta las demás, para que el modelo vea el resultado de `@read` antes de escribir. Por eso el prompt le pide una directiva por turno.
- `@write` reescribe el fichero entero. El contenido va tal cual entre `@write` y `@endwrite`, sin vallas, así puede contener bloques ``` sin romper el parser. Antes de sobrescribir guarda una copia en `backups/`.
- `@run` ejecuta comandos en la carpeta del proyecto y pide confirmación antes de cada ejecución, mostrando el comando y la explicación de Burton. Timeout de 120 s.
- `@agent <tarea>` lanza un subagente de **solo lectura** con contexto propio: investiga con `@ls`/`@read` y devuelve un resumen. El padre no se llena con los ficheros que explora. No puede escribir ni ejecutar. Cada subagente se guarda en la sesión y puedes revisarlo con `/subagents` o `Ctrl+S`.
- Las rutas siempre se resuelven dentro del proyecto.
- Por defecto no se puede sobrescribir el código `.py` de `burton_ai`; `--allow-self-edit` lo permite.
- Peticiones claras como «hazme», «crea» o «implementa» autorizan a Burton a crear o editar archivos con `@write` sin pedir otro permiso. Las consultas, las instrucciones de solo lectura y las negaciones explícitas siguen bloqueadas.
- Si el modelo repite una directiva, Burton no la ejecuta de nuevo: le recuerda el resultado anterior y le pide continuar. Si insiste otra vez, corta el bucle.

## Contexto

Cada petición incluye el árbol del proyecto (máximo 80 entradas y 3 niveles), los primeros 2000 caracteres de `AGENTS.md` y todas las habilidades de `skills/*.md` (hasta 4000 caracteres). Todo lo demás se pide con `@read`, así el prompt se mantiene pequeño.

Las habilidades son instrucciones permanentes: leer ficheros, explorar, editar sin romper nada y estilo. Puedes añadir o editar `skills/*.md` y se cargan en el siguiente turno sin reiniciar.

Si solo saludas o conversas, responde en texto normal sin tocar ficheros.

## Comandos

| Comando | Qué hace |
|---|---|
| `/new` | Nueva conversación |
| `/clear` | Alias de `/new` (también escribiendo `clear`) |
| `/plan` | Alterna solo lectura: bloquea `@write` y `@run` |
| `/models` | Lista y cambia de modelo; no hace falta reiniciar Ollama |
| `/sessions` | Lista sesiones; `/sessions N` carga una |
| `/subagents` | Lista los subagentes de la sesión; `/subagents N` abre uno (o `Ctrl+S`) |
| `/help` | Ayuda |
| `/exit` | Salir |

## Estado

Todo vive en esta carpeta:

- `config.json`: modelo, `num_ctx`, pasos máximos y `num_predict` (límite de generación; `-1` permite generación sin límite de tokens). El contexto configurado es un límite del agente, no un límite fijo de Ollama; aumentarlo consume más memoria.
- `skills/`: instrucciones permanentes que se cargan en cada turno.
- `sessions/`: historial JSON, autoguardado tras cada turno.
- `backups/`: copias antes de sobrescribir.
- `history`: historial de líneas de la consola.

## Configuración

`config.json`:

```json
{
  "model": "qwen2.5-coder:14b",
  "num_ctx": 16384,
  "max_steps": 12,
  "temperature": 0,
  "num_predict": -1
}
```

En equipos con 8 GB de VRAM, `qwen2.5-coder:14b` puede necesitar descarga parcial a RAM en Q4 y ser más lento; `qwen2.5-coder:7b` usa menos memoria y `qwen2.5-coder:3b` suele ser más rápido, aunque puede equivocarse más. Ollama decide automáticamente cuánto cargar en GPU y RAM; no es conveniente forzar a llenar ambas. El contexto grande también aumenta el uso de memoria. Si Ollama informa de falta de memoria o el sistema se vuelve lento, baja `num_ctx` o cambia a un modelo menor.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Cubren el parser de directivas, el sandbox de rutas, el modo plan, las copias de seguridad, el autocompletado, el render de markdown, `Ctrl+Backspace` y los subagentes.

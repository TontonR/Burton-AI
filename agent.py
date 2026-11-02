import json
import os
import platform
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import ui
from tools import Tools, parse_directives, truncate

API = "http://127.0.0.1:11434"
WRITE_RE = re.compile(
    r"\b(escrib\w*|cre[ao]\w*|modific\w*|cambi\w*|arregl\w*|corrig\w*|corrij\w*|"
    r"a[ñn]ad\w*|agreg\w*|elimin\w*|borr\w*|renombr\w*|refactor\w*|implement\w*|"
    r"actualiz\w*|guard\w*|hazme|hazlo|hazla|haz|constru\w*|program\w*|"
    r"genera\w*|desarroll\w*|prepara\w*|monta\w*|aplic\w*|write|edit|fix|create|"
    r"add|remove|delete|update|make\s+me|build\s+me)\b",
    re.IGNORECASE,
)
BLOCK_PHRASES = (
    "no modifiques",
    "no modificar",
    "sin modificar",
    "no escribas",
    "no escribir",
    "sin escribir",
    "no cambies",
    "sin cambiar",
    "no toques",
    "no hagas cambios",
    "no hagas nada",
    "no edites",
    "no crear",
    "no crees",
    "no borres",
    "no elimines",
    "solo dime",
    "sólo dime",
    "solo leer",
    "sólo leer",
    "solo informa",
)
RESPONSE_ONLY_RE = re.compile(
    r"\bno\s+(?:escribas?|devuelvas?|respondas?)\b[^\n.!?]*"
    r"\b(?:como\s+respuesta|en\s+la\s+respuesta|como\s+texto)\b",
    re.IGNORECASE,
)


def allows_writes(text):
    lowered = RESPONSE_ONLY_RE.sub("", text.lower())
    if any(phrase in lowered for phrase in BLOCK_PHRASES):
        return False
    return bool(WRITE_RE.search(lowered))


def directive_explanation(text, directive_name):
    directive_line = re.search(
        rf"(?m)^\s*@{re.escape(directive_name)}\b", text, re.IGNORECASE
    )
    if not directive_line:
        return ""
    explanation = text[:directive_line.start()]
    lines = [
        re.sub(r"^\s*(?:[-*]\s+|\d+[.)]\s+)", "", line).strip()
        for line in explanation.splitlines()
    ]
    return "\n".join(line for line in lines if line)[-500:]
IGNORE = {
    ".git",
    ".venv",
    ".venv313",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
MAX_SKILLS_CHARS = 4000
REFUSAL_RE = re.compile(
    r"no (?:puedo|tengo) (?:acceder|leer|ejecutar)|fuera del directorio|"
    r"no tengo acceso|no puedo ver (?:el|los) (?:archivo|fichero)",
    re.IGNORECASE,
)
FILE_RE = re.compile(
    r"\b[\w./\\-]+\.(?:md|py|txt|json|toml|ya?ml|js|ts|jsx|tsx|css|html|sh|ps1|cfg|ini)\b",
    re.IGNORECASE,
)


def load_skills(limit=MAX_SKILLS_CHARS):
    if not SKILLS_DIR.is_dir():
        return ""
    parts = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            parts.append(text)
    return "\n\n".join(parts)[:limit]


def api_get(path, timeout=10):
    with urllib.request.urlopen(API + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def file_tree(root, max_entries=80, max_depth=3):
    root = Path(root)
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORE and not d.startswith(".")
        )
        if depth >= max_depth:
            dirnames[:] = []
            continue
        indent = "  " * depth
        if depth:
            lines.append(f"{'  ' * (depth - 1)}{rel.name}/")
        for name in sorted(filenames):
            if len(lines) >= max_entries:
                lines.append("... (árbol recortado)")
                return "\n".join(lines)
            lines.append(f"{indent}{name}")
    return "\n".join(lines) or "(proyecto vacío)"


def project_notes(root):
    path = Path(root) / "AGENTS.md"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return "\n\nInstrucciones del proyecto (AGENTS.md):\n" + text[:2000]


def build_system_prompt(root, plan=False):
    skills = load_skills()
    skills_note = f"\nHabilidades permanentes:\n{skills}\n" if skills else ""
    plan_note = ""
    if plan:
        plan_note = (
            "MODO PLAN ACTIVO: solo puedes usar @ls y @read. No escribas ni ejecutes nada. "
            "Entrega tu plan y termina con @done.\n"
        )
    return f"""Eres un agente de código en {root}.
Entorno: {platform.system()} · shell: {'cmd.exe' if os.name == 'nt' else 'sh'} · Python {platform.python_version()}

Directivas, una por línea:
@ls <ruta>
@read <ruta> [inicio-fin]
@write <ruta>
contenido COMPLETO del fichero, tal cual, sin vallas de código
@endwrite
@run <comando>
@agent <tarea>
@done

Ejemplo de @write:
@write saludo.py
def saludo():
    return "hola"
@endwrite

Reglas:
- Si el usuario te da una tarea concreta o una lista de pasos, ejecútala con las directivas y herramientas disponibles; no respondas con instrucciones para que el usuario haga el trabajo, salvo que pida instrucciones.
- Una petición como "hazme", "crea", "prepara" o "implementa" un programa o archivo autoriza a crearlo dentro del proyecto; no pidas permiso adicional para usar @write.
- Si no indica nombre o ruta para un archivo nuevo, elige un nombre claro y créalo en la raíz del proyecto.
- Si la tarea requiere inspeccionar, editar, probar o publicar el proyecto, no redactes el contenido solicitado como respuesta final: usa las directivas. Las modificaciones de archivos solo se aplican con @write y los comandos solo con @run.
- @run ejecuta un comando de terminal en la carpeta del proyecto. Puedes usarlo para probar archivos creados, ejecutar tests y comprobar resultados; la aplicación pedirá permiso antes de ejecutarlo.
- Antes de @run, escribe una explicación breve de qué hará el comando y por qué hace falta. Espera al resultado de @write antes de ejecutar el archivo que acabas de crear.
- Si @write o @run devuelve un error, usa ese resultado para corregir la causa; no repitas el mismo comando sin cambios ni afirmes que una acción tuvo éxito si falló.
- Tienes acceso REAL a los ficheros del proyecto con @ls y @read. Nunca digas que no puedes acceder o que están fuera del directorio.
- Si el usuario nombra un fichero, responde con @read de ese fichero.
- Si el usuario saluda o conversa, responde en texto normal, sin directivas ni @done. No explores ni modifiques nada sin una tarea.
- Escribe UNA sola directiva por respuesta y espera su resultado antes de la siguiente.
- Usa rutas relativas al proyecto, nunca absolutas.
- Tras @read, usa el contenido real que recibes en @write. No inventes, resumas ni describas el contenido.
- En @write copia el contenido sin los números de línea que añade @read.
- No uses ``` para delimitar @write: empieza el contenido en la línea siguiente y ciérralo con @endwrite.
- Lee con @read antes de sobrescribir un fichero existente; si el fichero es nuevo, créalo directamente con @write.
- No crees ni modifiques ficheros salvo que el usuario lo pida explícitamente. Si solo pide información, responde y termina; no "guardes" nada.
- El resultado de @agent es información para responder, no contenido para @write.
- @write reescribe el fichero entero: incluye todo el contenido, sin recortes.
- Antes de @run, explica en una frase qué hará el comando y por qué es necesario; después espera la confirmación interactiva del usuario.
- Usa @run para tests, builds y comandos.
- Usa @agent para delegar una investigación de solo lectura; el subagente no puede escribir ni ejecutar.
- No expliques lo que vas a hacer; hazlo. Respuestas cortas y en español.
- Si el usuario pide información, escribe la respuesta en texto claro (sin directivas) antes de @done.
- Si ya has terminado, escribe solo @done.
{skills_note}{plan_note}{project_notes(root)}
Árbol del proyecto:
{file_tree(root)}"""


def stream_chat(model, messages, cfg, on_chunk, cancel_event=None):
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": "30m",
        "options": {
            "num_ctx": cfg["num_ctx"],
            "temperature": cfg["temperature"],
            "num_predict": cfg["num_predict"],
        },
    }
    request = urllib.request.Request(
        API + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    chunks = []
    tokens = 0
    prompt_tokens = 0
    gen_seconds = 0.0
    monitor_stop = threading.Event()
    monitor = None
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            if cancel_event is not None:
                def close_on_cancel():
                    while not monitor_stop.wait(0.1):
                        if cancel_event.is_set():
                            try:
                                response.close()
                            except (OSError, ValueError):
                                pass
                            return

                monitor = threading.Thread(target=close_on_cancel, daemon=True)
                monitor.start()
            for raw in response:
                if cancel_event is not None and cancel_event.is_set():
                    break
                raw = raw.strip()
                if not raw:
                    continue
                data = json.loads(raw)
                if "error" in data:
                    raise RuntimeError(data["error"])
                piece = data.get("message", {}).get("content", "")
                if piece:
                    chunks.append(piece)
                    on_chunk(piece)
                if data.get("done"):
                    tokens = data.get("eval_count", 0)
                    prompt_tokens = data.get("prompt_eval_count", 0)
                    gen_seconds = data.get("eval_duration", 0) / 1e9
                    break
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        if cancel_event is not None and cancel_event.is_set():
            pass
        else:
            raise RuntimeError(
                f"no puedo conectar con Ollama en {API} ({exc.reason}). ¿Está arrancado?"
            ) from None
    except (OSError, ValueError, AttributeError):
        if cancel_event is None or not cancel_event.is_set():
            raise
    finally:
        monitor_stop.set()
        if monitor is not None:
            monitor.join(timeout=0.5)
    return "".join(chunks), {
        "tokens": tokens,
        "prompt_tokens": prompt_tokens,
        "seconds": gen_seconds,
    }


def stream_with_indicator(model, messages, cfg, on_chunk, cancel_event=None):
    indicator = ui.ThinkingIndicator()

    def receive(piece):
        indicator.stop()
        on_chunk(piece)

    indicator.start()
    try:
        if cancel_event is None:
            return stream_chat(model, messages, cfg, receive)
        return stream_chat(model, messages, cfg, receive, cancel_event)
    finally:
        indicator.stop()


def trim_history(messages, budget):
    if sum(len(m["content"]) for m in messages) <= budget:
        return list(messages)
    kept, used = [], 0
    for message in reversed(messages):
        size = len(message["content"])
        if kept and used + size > budget:
            break
        kept.append(message)
        used += size
    kept.reverse()
    return messages[-4:] if len(kept) < 4 else kept


def compact_session(session, cfg, cancel_event=None):
    messages = session.get("messages", [])
    if not messages:
        return False, "No hay conversación que compactar.", None

    transcript = "\n\n".join(
        f"{message['role'].upper()}:\n{message['content']}" for message in messages
    )
    max_chars = max(2000, (cfg["num_ctx"] - 2048) * 2)
    if len(transcript) > max_chars:
        first = messages[0]
        first_text = f"{first['role'].upper()}:\n{first['content']}"
        marker = "\n\n[...historial intermedio omitido...]\n\n"
        if len(first_text) + len(marker) >= max_chars:
            half = max_chars // 2
            transcript = first_text[:half] + marker + first_text[-half:]
        else:
            tail_size = max_chars - len(first_text) - len(marker)
            transcript = first_text + marker + transcript[-tail_size:]

    compact_cfg = dict(cfg)
    compact_cfg["num_predict"] = 1200
    compact_messages = [
        {
            "role": "system",
            "content": (
                "Resume el historial como memoria de trabajo para continuar la misma "
                "conversación. Conserva el objetivo original, requisitos y restricciones, "
                "hechos verificados, decisiones, archivos/cambios realizados, errores "
                "pendientes y siguiente paso. No inventes ni ejecutes acciones. Sé "
                "conciso pero suficiente; devuelve solo el resumen."
            ),
        },
        {"role": "user", "content": transcript},
    ]
    try:
        summary, stats = stream_with_indicator(
            cfg["model"],
            compact_messages,
            compact_cfg,
            lambda _piece: None,
            cancel_event,
        )
    except RuntimeError as exc:
        return False, f"No se compactó la conversación: {exc}", None
    if not summary.strip():
        return False, "El modelo devolvió un resumen vacío; conservé el historial.", None

    session["messages"] = [
        {
            "role": "user",
            "content": "Resumen compacto de la conversación anterior:\n\n"
            + summary.strip(),
        }
    ]
    session["last_context_tokens"] = stats.get("prompt_tokens", 0)
    session["last_context_limit"] = cfg["num_ctx"]
    return True, summary.strip(), stats


def clean_answer(text):
    lines = [line for line in text.splitlines() if not line.strip().startswith("@")]
    return "\n".join(lines).strip()


def build_subagent_prompt(root):
    skills = load_skills()
    skills_note = f"\nHabilidades permanentes:\n{skills}\n" if skills else ""
    return f"""Eres un subagente de solo lectura en {root}.
Investiga lo que te pide el usuario y devuelve una respuesta breve y concreta.

Directivas permitidas, una por línea:
@ls <ruta>
@read <ruta> [inicio-fin]
@done

Reglas:
- Tienes acceso real a los ficheros con @ls y @read. Nunca digas que no puedes acceder.
- Escribe UNA sola directiva por respuesta y espera el resultado.
- No modifiques ficheros ni ejecutes comandos.
- Cuando ya tengas la respuesta, escríbela en texto normal sin directivas y sin los números de línea de @read.
- Responde en español.
{skills_note}{project_notes(root)}
Árbol del proyecto:
{file_tree(root)}"""


def run_subagent(task, cfg, root, log=print, record=None, cancel_event=None):
    if not task.strip():
        return "ERROR: falta la tarea del subagente"
    tools = Tools(root, plan=True)
    messages = [{"role": "user", "content": task}]
    last = ""
    for _ in range(min(6, cfg["max_steps"])):
        if cancel_event is not None and cancel_event.is_set():
            return last or "[interrumpido]"
        context = [
            {"role": "system", "content": build_subagent_prompt(root)}
        ] + trim_history(messages, cfg["num_ctx"] * 2)
        try:
            text, _ = stream_with_indicator(
                cfg["model"], context, cfg, lambda piece: None, cancel_event
            )
        except RuntimeError as exc:
            return f"ERROR del subagente: {exc}"
        messages.append({"role": "assistant", "content": text})
        answer = clean_answer(text)
        if answer:
            last = answer
        directives = parse_directives(text)
        if not directives:
            return answer or "(sin respuesta)"
        if directives[0].name == "done":
            return answer or last or "(sin respuesta)"
        directive = directives[0]
        result = tools.execute(directive)
        step = f"@{directive.name} {directive.arg}".strip()
        log(ui.c(f"     subagente: {step}"[:120], ui.DIM))
        if record is not None:
            record.setdefault("steps", []).append(step[:200])
        messages.append(
            {
                "role": "user",
                "content": f"Resultado de @{directive.name} {directive.arg}:\n{result}",
            }
        )
    return (last or "(sin respuesta)") + "\n[subagente: límite de pasos]"


def run_turn(session, cfg, tools, on_chunk, log=print, cancel_event=None):
    messages = session["messages"]
    request_text = messages[-1]["content"] if messages else ""
    write_ok = allows_writes(request_text)
    retried = False
    started = time.perf_counter()
    tokens = 0
    gen_seconds = 0.0
    prompt_tokens = 0

    def finish(outcome):
        elapsed = time.perf_counter() - started
        parts = [f"{elapsed:.1f}s"]
        if tokens:
            parts.append(f"{tokens} tok")
        if gen_seconds:
            parts.append(f"{tokens / gen_seconds:.0f} tok/s")
        log(ui.c("  " + ui.glyph("✓", "ok") + " " + " · ".join(parts), ui.DIM))
        if prompt_tokens:
            limit = cfg["num_ctx"]
            percent = prompt_tokens * 100 / limit
            session["last_context_tokens"] = prompt_tokens
            session["last_context_limit"] = limit
            log(
                ui.c(
                    f"  Contexto: {prompt_tokens:,}/{limit:,} tokens "
                    f"({percent:.1f}%; medición de Ollama)",
                    ui.DIM,
                )
            )
        return outcome

    seen = set()
    repeated_directives = 0

    for step in range(cfg["max_steps"]):
        if cancel_event is not None and cancel_event.is_set():
            log(ui.c("  [interrumpido]", ui.YELLOW))
            return finish("cancelled")
        if step:
            log("")
        system = {"role": "system", "content": build_system_prompt(tools.root, tools.plan)}
        context = [system] + trim_history(messages, cfg["num_ctx"] * 3)
        try:
            text, stats = stream_with_indicator(
                cfg["model"], context, cfg, on_chunk, cancel_event
            )
        except RuntimeError as exc:
            log(ui.c(f"\n  ! {exc}", ui.RED))
            return finish("error")
        if hasattr(on_chunk, "flush"):
            on_chunk.flush()

        tokens += stats["tokens"]
        gen_seconds += stats["seconds"]
        prompt_tokens = max(prompt_tokens, stats.get("prompt_tokens", 0))
        messages.append({"role": "assistant", "content": text})
        log("")
        if cancel_event is not None and cancel_event.is_set():
            log(ui.c("  [interrumpido]", ui.YELLOW))
            return finish("cancelled")

        directives = parse_directives(text)
        if not directives:
            target = FILE_RE.search(request_text)
            if not retried and target and REFUSAL_RE.search(text):
                retried = True
                log(ui.c("  ! el modelo se ha bloqueado; le recuerdo que puede leer", ui.YELLOW))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"No estás fuera del proyecto: la raíz es {tools.root} y tienes acceso real. "
                            f"Responde SOLO con la directiva necesaria, por ejemplo: @read {target.group(0)}"
                        ),
                    }
                )
                continue
            return finish("text")

        directive = directives[0]
        if directive.name == "done":
            return finish("done")

        key = (directive.name, directive.arg, directive.body)
        if key in seen:
            repeated_directives += 1
            if repeated_directives > 1:
                repeated = f"@{directive.name} {directive.arg}".strip()
                log(
                    ui.c(
                        f"  ! bucle detenido: el modelo repitió {repeated[:80]}",
                        ui.YELLOW,
                    )
                )
                return finish("loop")
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Ya ejecutaste @{directive.name} {directive.arg}. "
                        "El resultado anterior está en la conversación: úsalo y continúa "
                        "con un paso distinto o termina con @done. No repitas la directiva."
                    ),
                }
            )
            continue
        seen.add(key)

        log(ui.c(f"  -> @{directive.name} {directive.arg}".rstrip(), ui.DIM))
        if directive.name == "agent":
            record = {"task": directive.arg, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
            result = truncate(
                run_subagent(
                    directive.arg, cfg, tools.root, log, record, cancel_event
                )
            )
            record["answer"] = result
            session.setdefault("subagents", []).append(record)
        elif directive.name == "write" and not write_ok:
            result = (
                "ERROR: el usuario no ha pedido modificar ficheros. "
                "Responde con la información en texto y termina con @done."
            )
        else:
            if directive.name == "run":
                explanation = directive_explanation(text, "run")
                tools.confirm_reason = explanation or (
                    "Burton no explicó el motivo. Tarea original: "
                    + request_text[:400]
                )
            else:
                tools.confirm_reason = request_text
            result = tools.execute(directive)

        if result.startswith("ERROR"):
            log(ui.c(f"     {result}", ui.RED))
        elif directive.name == "run":
            for line in result.splitlines()[:40]:
                log(f"     {line}")
        elif directive.name in ("write", "agent"):
            for line in result.splitlines()[:20]:
                log(ui.c(f"     {line}", ui.DIM))

        feedback = f"Resultado de @{directive.name} {directive.arg}:\n{result}"
        if len(directives) > 1:
            ignored = len(directives) - 1
            feedback += (
                f"\n\nHe ignorado {ignored} directiva(s) más de ese mensaje: "
                "escribe una sola directiva por respuesta y espera el resultado."
            )
        messages.append({"role": "user", "content": feedback})

    log(ui.c(f"  ! límite de {cfg['max_steps']} pasos", ui.YELLOW))
    return finish("max_steps")

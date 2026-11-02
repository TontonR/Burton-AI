import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import agent
import bridge
import store
import ui
from tools import Tools

YES = {"s", "si", "sí", "y", "yes"}

HELP = """Comandos:
  /new            nueva conversación
  /clear          alias de /new (también "clear")
  /plan           alterna modo solo lectura (sin escribir ni ejecutar)
  /models         lista y cambia de modelo (sin reiniciar)
  /sessions       lista sesiones guardadas; /sessions N carga una
  /subagents      lista los subagentes de esta sesión; /subagents N abre uno
  /compact        resume el historial para liberar contexto
  /help           esta ayuda
  /exit           salir

Interfaz externa (para scripts y agentes):
  burton --talk "mensaje"     inicia un turno en segundo plano
  burton --status             estado JSON, incluido si está pensando
  burton --response           respuesta parcial o final
  burton --wait               espera y devuelve la respuesta final
  burton --compact            compacta la conversación actual
  burton --stop               solicita interrumpir el turno
  burton --approve / --deny   resuelve un permiso pendiente de @run
  burton --new                inicia una sesión externa nueva
  burton --toggle-plan        activa/desactiva solo lectura
  burton --models [NOMBRE]    lista modelos o cambia el activo
  burton --sessions [ID|N]    lista sesiones o carga una
  burton --subagents [N]      lista los subagentes o muestra uno
  Añade --root RUTA para usar el mismo proyecto desde otra carpeta.

Atajos: Shift+Enter nueva línea · Ctrl+S abre la lista de subagentes · Ctrl+Backspace borra palabra"""


def ask(question):
    try:
        return input(f"{question} [s/N] ").strip().lower() in YES
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def find_ollama():
    found = shutil.which("ollama")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "Programs/Ollama/ollama.exe",
        local / "Ollama/ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def server_up():
    try:
        agent.api_get("/api/version", timeout=2)
        return True
    except Exception:
        return False


def ensure_server():
    if server_up():
        return True
    exe = find_ollama()
    if not exe:
        print(
            "Ollama no está instalado. Instálalo con:\n"
            "  winget install Ollama.Ollama\n"
            "  (o: irm https://ollama.com/install.ps1 | iex)"
        )
        return False
    print("Arrancando ollama serve...")
    subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(30):
        time.sleep(1)
        if server_up():
            print("Ollama listo.")
            return True
    print("Ollama no responde en 127.0.0.1:11434")
    return False


def model_names():
    return [m["name"] for m in agent.api_get("/api/tags").get("models", [])]


def ensure_model(model):
    names = model_names()
    if model in names or f"{model}:latest" in names:
        return True
    print(f"El modelo {model} no está descargado.")
    if not ask("¿Descargarlo ahora con ollama pull?"):
        return False
    exe = find_ollama() or "ollama"
    if subprocess.run([exe, "pull", model]).returncode != 0:
        print("La descarga ha fallado.")
        return False
    return True


def confirm_command(cmd, reason=""):
    print("\nSe solicita permiso para ejecutar un comando.")
    print("Qué hará: ejecutará el comando en cmd.exe dentro de la carpeta de trabajo.")
    print(f"Comando: {cmd}")
    if reason:
        print(f"Explicación de Burton: {reason[:500]}")
    else:
        print("Explicación: Burton no indicó por qué hace falta este comando.")
    print("Riesgo: el comando puede modificar archivos o tener otros efectos.")
    return ask("¿Permites esta ejecución?")


def show_models(cfg, session):
    names = model_names()
    if not names:
        print("No hay modelos. Descarga uno, por ejemplo: ollama pull qwen2.5-coder:7b")
        return
    for i, name in enumerate(names, 1):
        mark = ui.c("  (actual)", ui.GREEN) if name == cfg["model"] else ""
        print(f"  {i}. {name}{mark}")
    choice = input("Número o nombre (Enter para cancelar): ").strip()
    if not choice:
        return
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        model = names[int(choice) - 1]
    else:
        model = choice
    if not ensure_model(model):
        return
    cfg["model"] = model
    store.save_config(cfg)
    session["model"] = model
    print(f"Modelo activo: {model}")


def show_sessions(session, arg):
    if arg:
        sid = arg
        if arg.isdigit():
            items = store.list_sessions()
            index = int(arg) - 1
            if not 0 <= index < len(items):
                print("No existe esa sesión.")
                return session
            sid = items[index]["id"]
        try:
            loaded = store.load_session(sid)
        except (OSError, ValueError):
            print(f"No puedo cargar la sesión {sid}.")
            return session
        title = loaded.get("title") or "(sin título)"
        print(f"Cargada {loaded['id']}: {title} ({len(loaded['messages'])} mensajes)")
        return loaded

    items = store.list_sessions()
    if not items:
        print("(no hay sesiones guardadas)")
        return session
    for i, item in enumerate(items[:20], 1):
        print(
            f"  {i}. {item['created']}  {item['title'] or '(sin título)'}"
            f"  [{item['id']}]"
        )
    print("Usa /sessions N para cargar una.")
    return session


def print_subagent(item):
    print(ui.c("tarea: " + (item.get("task") or "(sin tarea)"), ui.BOLD))
    for step in item.get("steps") or []:
        print(ui.c("  " + step, ui.DIM))
    print()
    md = ui.Markdown()
    md.feed((item.get("answer") or "(sin respuesta)") + "\n")


def show_subagents(session, arg):
    items = session.get("subagents") or []
    if not items:
        print(ui.c("  (no hay subagentes en esta sesión)", ui.DIM))
        return
    if arg:
        index = int(arg) - 1 if arg.isdigit() else -1
        if not 0 <= index < len(items):
            print("No existe ese subagente.")
            return
        print_subagent(items[index])
        return
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('created', '')}  {(item.get('task') or '')[:60]}")
    print(ui.c("  /subagents N para ver su conversación.", ui.DIM))


def pick_subagent(session):
    items = session.get("subagents") or []
    if not items:
        print(ui.c("  (no hay subagentes en esta sesión)", ui.DIM))
        return
    try:
        from prompt_toolkit.shortcuts import radiolist_dialog
    except ImportError:
        show_subagents(session, "")
        return
    result = radiolist_dialog(
        title="subagentes",
        text="Elige uno para ver su conversación:",
        values=[
            (i, f"{item.get('created', '')}  {(item.get('task') or '')[:70]}")
            for i, item in enumerate(items)
        ],
    ).run()
    if result is not None:
        print_subagent(items[result])


def worker_main(root, request_id):
    root = Path(root).resolve()
    state = bridge.read_state(root)
    if state.get("request_id") != request_id:
        return 2

    paths = bridge.paths_for(root)
    stop_monitor = threading.Event()
    cancel_event = threading.Event()

    def monitor():
        while not stop_monitor.wait(0.25):
            paths["heartbeat"].touch()
            if bridge.cancel_requested(root, request_id):
                cancel_event.set()

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    raw_response = []
    last_response_write = 0.0
    session = None
    outcome = "error"
    try:
        if not ensure_server():
            raise RuntimeError("Ollama no responde.")
        cfg = store.load_config()
        cfg["model"] = state.get("model") or cfg["model"]
        names = model_names()
        if cfg["model"] not in names and f"{cfg['model']}:latest" not in names:
            raise RuntimeError(f"El modelo {cfg['model']} no está descargado.")

        try:
            session = store.load_session(state["session_id"])
        except (KeyError, OSError, ValueError):
            session = store.new_session(cfg["model"])
        session["model"] = cfg["model"]
        state["session_id"] = session["id"]
        state["status"] = "thinking"
        state["error"] = None
        state["approval"] = None
        bridge.write_state(root, state)

        def persist_response():
            state["response"] = bridge.visible_response("".join(raw_response))
            bridge.write_state(root, state)

        def on_chunk(piece):
            nonlocal last_response_write
            raw_response.append(piece)
            now = time.monotonic()
            if now - last_response_write >= 0.3:
                persist_response()
                last_response_write = now

        def log(message):
            state["last_event"] = str(message).strip()[:300]
            if state.get("status") != "awaiting_approval":
                state["status"] = "thinking"
            bridge.write_state(root, state)

        def confirm_external(command, reason=""):
            state["status"] = "awaiting_approval"
            state["approval"] = {
                "command": command,
                "reason": reason[:500],
            }
            bridge.write_state(root, state)
            while not cancel_event.wait(0.2):
                decision = bridge.consume_approval(root, request_id)
                if decision is not None:
                    state["approval"] = None
                    state["status"] = "thinking"
                    bridge.write_state(root, state)
                    return decision
            return False

        tools = Tools(
            root,
            plan=bool(state.get("plan")),
            confirm=confirm_external,
            allow_self_edit=bool(state.get("allow_self_edit")),
        )
        operation = state.get("operation", "talk")
        if operation == "compact":
            compacted, response, stats = agent.compact_session(
                session, cfg, cancel_event
            )
            outcome = "done" if compacted else "error"
            state["response"] = response
            if stats and stats.get("prompt_tokens"):
                state["last_context_tokens"] = stats["prompt_tokens"]
                state["last_context_limit"] = cfg["num_ctx"]
        else:
            prompt = state.get("prompt", "")
            session["messages"].append({"role": "user", "content": prompt})
            if not session.get("title"):
                session["title"] = prompt[:60]
            outcome = agent.run_turn(
                session,
                cfg,
                tools,
                on_chunk,
                log=log,
                cancel_event=cancel_event,
            )
            persist_response()

        if session.get("messages"):
            store.save_session(session)
        state["session_id"] = session["id"]
        if cancel_event.is_set() or outcome == "cancelled":
            state["status"] = "stopped"
        elif outcome == "error":
            state["status"] = "error"
            state["error"] = state.get("last_event") or "El turno terminó con error."
        else:
            state["status"] = "complete"
        state["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        state["status"] = "error"
        state["error"] = f"{type(exc).__name__}: {exc}"
        if session is not None and session.get("messages"):
            store.save_session(session)
    finally:
        stop_monitor.set()
        monitor_thread.join(timeout=1)
        if state.get("request_id") == request_id:
            cancel_file = paths["cancel"]
            try:
                if cancel_file.read_text(encoding="utf-8") == request_id:
                    cancel_file.unlink()
            except FileNotFoundError:
                pass
            state["busy"] = False
            bridge.write_state(root, state)
    return 0 if state.get("status") == "complete" else 1


def start_worker(root, request_id):
    paths = bridge.paths_for(root)
    log_path = paths["directory"] / "worker.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        request_id,
        "--root",
        str(root),
    ]
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": None,
        "stderr": None,
        "cwd": str(root),
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        options["start_new_session"] = True
    with log_path.open("ab") as log_file:
        options["stdout"] = log_file
        options["stderr"] = subprocess.STDOUT
        process = subprocess.Popen(command, **options)
    return process.pid


def begin_external(root, operation, prompt, args, cfg):
    descriptor = bridge.acquire_submit_lock(root)
    if descriptor is None:
        return None, "Hay otra solicitud externa iniciándose; inténtalo de nuevo."
    try:
        previous = bridge.read_state(root)
        if bridge.busy_state(root, previous):
            return None, "Burton ya está ocupado en esta carpeta."
        session_id = previous.get("session_id")
        if not session_id:
            new_session = store.new_session(cfg["model"])
            store.save_session(new_session)
            session_id = new_session["id"]
        request_id = uuid.uuid4().hex
        paths = bridge.paths_for(root)
        for marker in (paths["cancel"], paths["approval"]):
            try:
                marker.unlink()
            except FileNotFoundError:
                pass
        state = {
            "root": str(root),
            "request_id": request_id,
            "operation": operation,
            "prompt": prompt,
            "status": "queued",
            "session_id": session_id,
            "model": cfg["model"],
            "plan": bool(args.plan or previous.get("plan", False)),
            "allow_self_edit": bool(args.allow_self_edit),
            "response": "",
            "error": None,
            "approval": None,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        bridge.write_state(root, state)
        paths["heartbeat"].touch()
    finally:
        bridge.release_submit_lock(root, descriptor)

    try:
        start_worker(root, request_id)
    except OSError as exc:
        state["status"] = "error"
        state["error"] = f"No se pudo iniciar Burton en segundo plano: {exc}"
        bridge.write_state(root, state)
        return None, state["error"]
    return state, None


def update_idle_state(root, update):
    descriptor = bridge.acquire_submit_lock(root)
    if descriptor is None:
        return None, "Hay otra operación externa iniciándose; inténtalo de nuevo."
    try:
        state = bridge.read_state(root)
        if bridge.busy_state(root, state):
            return None, "Burton está ocupado; espera o detén el turno antes de cambiar la sesión."
        update(state)
        bridge.write_state(root, state)
        return state, None
    finally:
        bridge.release_submit_lock(root, descriptor)


def external_command(args, root, cfg):
    selected = [
        args.talk is not None,
        args.response,
        args.status,
        args.wait,
        args.compact,
        args.stop or args.exit,
        args.new,
        args.toggle_plan,
        args.models is not None,
        args.sessions is not None,
        args.subagents is not None,
        args.approve or args.deny,
    ]
    if sum(selected) > 1:
        print("Usa una sola operación externa por invocación.", file=sys.stderr)
        return 2

    state = bridge.read_state(root)
    if args.talk is not None or args.compact:
        if args.talk is not None and not args.talk.strip():
            print("--talk necesita un mensaje no vacío.", file=sys.stderr)
            return 2
        if args.model:
            cfg["model"] = args.model
            store.save_config(cfg)
        if args.steps:
            cfg["max_steps"] = args.steps
            store.save_config(cfg)
        operation = "talk" if args.talk is not None else "compact"
        state, error = begin_external(root, operation, args.talk or "", args, cfg)
        if error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps({
            "accepted": True,
            "status": state["status"],
            "request_id": state["request_id"],
            "session_id": state["session_id"],
        }, ensure_ascii=False))
        return 0

    if args.status:
        print(json.dumps(bridge.status_payload(root, state), ensure_ascii=False))
        return 0
    if args.response:
        response = state.get("response", "")
        if response:
            print(response)
        elif state.get("error"):
            print(state["error"], file=sys.stderr)
            return 1
        return 0
    if args.wait:
        started = time.monotonic()
        while bridge.busy_state(root):
            if args.timeout is not None and time.monotonic() - started >= args.timeout:
                print("Se agotó el tiempo de espera.", file=sys.stderr)
                return 124
            time.sleep(0.2)
        state = bridge.status_payload(root)
        if state.get("response"):
            print(state["response"])
        if state.get("status") in {"error", "stale"}:
            print(state.get("error") or "El trabajador terminó con error.", file=sys.stderr)
            return 1
        return 0
    if args.stop or args.exit:
        stopped = bridge.request_cancel(root)
        print(json.dumps({"stop_requested": stopped}, ensure_ascii=False))
        return 0 if stopped else 1
    if args.approve or args.deny:
        accepted = bridge.request_approval(root, state.get("request_id"), bool(args.approve))
        if not accepted:
            print("No hay ningún permiso pendiente.", file=sys.stderr)
            return 1
        print(json.dumps({"approval_submitted": bool(args.approve)}, ensure_ascii=False))
        return 0
    if args.new:
        def create_session(current):
            session = store.new_session(cfg["model"])
            store.save_session(session)
            plan = bool(current.get("plan"))
            current.clear()
            current.update(bridge.empty_state(root))
            current.update({
                "session_id": session["id"],
                "model": cfg["model"],
                "plan": plan,
            })

        state, error = update_idle_state(root, create_session)
        if error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps({"session_id": state["session_id"], "status": "idle"}))
        return 0
    if args.toggle_plan:
        state, error = update_idle_state(
            root, lambda current: current.update(
                {"plan": not bool(current.get("plan"))}
            )
        )
        if error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps({"plan": state["plan"]}))
        return 0
    if args.models is not None:
        try:
            names = model_names()
        except Exception as exc:
            print(f"No se pudo consultar Ollama: {exc}", file=sys.stderr)
            return 1
        if args.models:
            model = args.models
            if model not in names and f"{model}:latest" not in names:
                print(f"El modelo {model} no está descargado.", file=sys.stderr)
                return 1
            def set_model(current):
                cfg["model"] = model
                store.save_config(cfg)
                current["model"] = model

            state, error = update_idle_state(root, set_model)
            if error:
                print(error, file=sys.stderr)
                return 1
            print(json.dumps({"model": model}))
        else:
            print(json.dumps(names, ensure_ascii=False))
        return 0
    if args.sessions is not None:
        items = store.list_sessions()
        selected_session = args.sessions.strip()
        if selected_session:
            if selected_session.isdigit():
                index = int(selected_session) - 1
                if not 0 <= index < len(items):
                    print("No existe esa sesión.", file=sys.stderr)
                    return 1
                selected_session = items[index]["id"]
            try:
                loaded = store.load_session(selected_session)
            except (OSError, ValueError):
                print(f"No puedo cargar la sesión {selected_session}.", file=sys.stderr)
                return 1
            state, error = update_idle_state(
                root,
                lambda current: current.update({
                    "status": "idle",
                    "session_id": loaded["id"],
                    "model": loaded.get("model", cfg["model"]),
                    "response": "",
                    "error": None,
                    "approval": None,
                }),
            )
            if error:
                print(error, file=sys.stderr)
                return 1
            print(json.dumps({"session_id": loaded["id"], "title": loaded.get("title", "")}, ensure_ascii=False))
        else:
            print(json.dumps(items[:20], ensure_ascii=False))
        return 0
    if args.subagents is not None:
        if not state.get("session_id"):
            print("No hay una sesión externa activa.", file=sys.stderr)
            return 1
        try:
            session = store.load_session(state["session_id"])
        except (OSError, ValueError):
            print("No se pudo cargar la sesión externa.", file=sys.stderr)
            return 1
        items = session.get("subagents") or []
        if args.subagents.strip():
            index = int(args.subagents) - 1 if args.subagents.isdigit() else -1
            if not 0 <= index < len(items):
                print("No existe ese subagente.", file=sys.stderr)
                return 1
            print(json.dumps(items[index], ensure_ascii=False))
        else:
            print(json.dumps(items, ensure_ascii=False))
        return 0
    return None


def main():
    parser = argparse.ArgumentParser(description="Agente de código mínimo sobre Ollama")
    parser.add_argument("--root", help="directorio del proyecto (por defecto, el actual)")
    parser.add_argument("--model", help="modelo de Ollama")
    parser.add_argument("--steps", type=int, help="máximo de pasos por turno")
    parser.add_argument("--plan", action="store_true", help="empezar en modo solo lectura")
    parser.add_argument(
        "--allow-self-edit",
        action="store_true",
        help="permitir que la IA modifique el código de burton_ai",
    )
    parser.add_argument("--talk", metavar="TEXTO", help="envía un mensaje en segundo plano")
    parser.add_argument("--response", action="store_true", help="muestra la respuesta actual")
    parser.add_argument("--status", action="store_true", help="muestra el estado en JSON")
    parser.add_argument("--wait", action="store_true", help="espera al final y devuelve la respuesta")
    parser.add_argument("--timeout", type=float, help="límite en segundos para --wait")
    parser.add_argument("--compact", action="store_true", help="compacta la sesión externa")
    parser.add_argument("--stop", action="store_true", help="solicita detener el turno activo")
    parser.add_argument("--exit", action="store_true", help="alias externo de --stop")
    parser.add_argument("--new", "--clear", action="store_true", help="crea una sesión externa nueva")
    parser.add_argument("--toggle-plan", action="store_true", help="alterna el modo solo lectura externo")
    parser.add_argument("--models", nargs="?", const="", help="lista modelos o activa uno")
    parser.add_argument("--sessions", nargs="?", const="", help="lista sesiones o carga una por ID/número")
    parser.add_argument("--subagents", nargs="?", const="", help="lista subagentes o muestra uno")
    approvals = parser.add_mutually_exclusive_group()
    approvals.add_argument("--approve", action="store_true", help="permite el @run pendiente")
    approvals.add_argument("--deny", action="store_true", help="deniega el @run pendiente")
    parser.add_argument("--worker", metavar="REQUEST_ID", help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = store.load_config()
    if args.model:
        cfg["model"] = args.model
    if args.steps:
        cfg["max_steps"] = args.steps

    root = Path(args.root or ".").expanduser().resolve()
    if not root.is_dir():
        print(f"No existe el directorio: {root}")
        return 1
    if args.worker:
        return worker_main(root, args.worker)

    external_result = external_command(args, root, cfg)
    if external_result is not None:
        return external_result

    cfg.pop("root", None)
    store.save_config(cfg)

    if not ensure_server():
        return 1
    if not ensure_model(cfg["model"]):
        return 1

    session = store.new_session(cfg["model"])
    tools = Tools(
        root,
        plan=args.plan,
        confirm=confirm_command,
        allow_self_edit=args.allow_self_edit,
    )

    interactive = False
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            from input_ui import make_reader

            read = make_reader()
            interactive = True
        except ImportError:
            print(
                ui.c(
                    f"  aviso: falta prompt_toolkit en {sys.executable}",
                    ui.YELLOW,
                )
            )
            print(
                ui.c(
                    f'  instala: "{sys.executable}" -m pip install -r '
                    f'"{Path(__file__).with_name("requirements.txt")}"',
                    ui.DIM,
                )
            )
    if not interactive:
        prompt = ui.glyph("❯", ">") + " "
        read = lambda: input(ui.c(prompt, ui.MAGENTA, ui.BOLD))

    print(ui.banner(cfg["model"], root, args.plan))
    if interactive:
        print(ui.c(f"  Enter envía {ui.glyph('·', '-')} Shift+Enter nueva línea {ui.glyph('·', '-')} Ctrl+Backspace borra palabra {ui.glyph('·', '-')} Ctrl+S subagentes {ui.glyph('·', '-')} / comandos", ui.DIM))
    print()

    try:
        while True:
            context_tokens = session.get("last_context_tokens", 0)
            context_limit = session.get("last_context_limit", cfg["num_ctx"])
            if context_tokens and context_limit:
                print(
                    ui.c(
                        f"  Contexto último turno: {context_tokens:,}/{context_limit:,} "
                        f"tokens ({context_tokens * 100 / context_limit:.1f}%)",
                        ui.DIM,
                    )
                )
            try:
                line = read().strip()
            except EOFError:
                break
            if not line:
                continue

            if line == ui.SUBAGENTS_KEY:
                pick_subagent(session)
                continue

            if line.lower() in ("clear", "cls"):
                line = "/clear"

            if line.startswith("/"):
                command, _, arg = line.partition(" ")
                command = command.lower()
                if command in ("/exit", "/quit"):
                    break
                if command == "/help":
                    print(HELP)
                elif command in ("/new", "/clear"):
                    if session["messages"]:
                        store.save_session(session)
                    session = store.new_session(cfg["model"])
                    print(f"Nueva sesión {ui.c(session['id'], ui.DIM)}")
                elif command == "/plan":
                    tools.plan = not tools.plan
                    print(
                        ui.c("Modo plan ACTIVADO (solo lectura).", ui.YELLOW)
                        if tools.plan
                        else ui.c("Modo plan desactivado.", ui.DIM)
                    )
                elif command == "/models":
                    show_models(cfg, session)
                elif command == "/sessions":
                    session = show_sessions(session, arg.strip())
                elif command == "/subagents":
                    show_subagents(session, arg.strip())
                elif command == "/compact":
                    compacted, result, stats = agent.compact_session(session, cfg)
                    if compacted:
                        store.save_session(session)
                        print(
                            "Conversación compactada. "
                            f"Historial reducido a {len(session['messages'])} mensaje."
                        )
                        if stats and stats.get("prompt_tokens"):
                            count = stats["prompt_tokens"]
                            limit = cfg["num_ctx"]
                            print(
                                f"Contexto usado para resumir: {count:,}/{limit:,} "
                                f"tokens ({count * 100 / limit:.1f}%)."
                            )
                        print("Resumen:")
                        print(result[:1200])
                    else:
                        print(ui.c(result, ui.YELLOW))
                else:
                    print(ui.c("Comando desconocido. /help para la lista.", ui.RED))
                continue

            session["messages"].append({"role": "user", "content": line})
            if not session["title"]:
                session["title"] = line[:60]
            md = ui.Markdown()
            try:
                agent.run_turn(session, cfg, tools, md)
            except KeyboardInterrupt:
                print("\n[interrumpido]")
            finally:
                md.flush()
                store.save_session(session)
            print()
    except KeyboardInterrupt:
        print()
    finally:
        if session["messages"]:
            store.save_session(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

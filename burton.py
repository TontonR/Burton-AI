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
import skills
import store
import ui
from tools import Tools

YES = {"s", "si", "sí", "y", "yes"}

HELP = """Commands:
  /new            new conversation
  /clear          alias of /new (also "clear")
  /plan           toggle read-only mode (no writing or running)
  /models         list models and switch without restarting
  /sessions       list saved sessions; /sessions N loads one
  /skills         list skills; /skills on|off|only <id> toggles them
  /subagents      list this session's subagents; /subagents N opens one
  /compact        summarise the history to free context
  /help           this help
  /exit           quit

External interface (for scripts and agents):
  burton --talk "message"     start a turn in the background
  burton --status             JSON state, including whether it is thinking
  burton --response           partial or final response
  burton --wait               wait and return the final response
  burton --compact            compact the current conversation
  burton --stop               request cancelling the active turn
  burton --approve / --deny   resolve a pending @run permission
  burton --new                start a new external session
  burton --toggle-plan        toggle read-only mode
  burton --models [NAME]      list models or switch the active one
  burton --sessions [ID|N]    list sessions or load one
  burton --skills [ID,ID]     list skills; default | on:ID | off:ID | ID,ID
  burton --subagents [N]      list subagents or show one
  Add --root PATH to use the same project from another folder.

Shortcuts: Shift+Enter new line · Ctrl+S subagent list · Ctrl+Backspace delete word"""


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
            "Ollama is not installed. Install it with:\n"
            "  winget install Ollama.Ollama\n"
            "  (or: irm https://ollama.com/install.ps1 | iex)"
        )
        return False
    print("Starting ollama serve...")
    subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(30):
        time.sleep(1)
        if server_up():
            print("Ollama ready.")
            return True
    print("Ollama is not responding at 127.0.0.1:11434")
    return False


def model_names():
    return [m["name"] for m in agent.api_get("/api/tags").get("models", [])]


def ensure_model(model):
    names = model_names()
    if model in names or f"{model}:latest" in names:
        return True
    print(f"The model {model} is not downloaded.")
    if not ask("Download it now with ollama pull?"):
        return False
    exe = find_ollama() or "ollama"
    if subprocess.run([exe, "pull", model]).returncode != 0:
        print("The download failed.")
        return False
    return True


def confirm_command(cmd, reason=""):
    print("\nPermission required.")
    print("Reason: the command may install software, change the system or")
    print("touch files outside the project. Safe commands inside the project run")
    print("without asking.")
    print(f"Command: {ui.c(cmd, ui.BOLD)}")
    if reason:
        print(f"Burton's explanation: {reason[:500]}")
    else:
        print("Explanation: Burton did not say why this command is needed.")
    return ask("Allow this execution?")


def show_models(cfg, session):
    names = model_names()
    if not names:
        print("No models found. Download one, for example: ollama pull qwen2.5-coder:7b")
        return
    for i, name in enumerate(names, 1):
        mark = ui.c("  (current)", ui.GREEN) if name == cfg["model"] else ""
        print(f"  {i}. {name}{mark}")
    choice = input("Number or name (Enter to cancel): ").strip()
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
    print(f"Active model: {model}")


def show_sessions(session, arg):
    if arg:
        sid = arg
        if arg.isdigit():
            items = store.list_sessions()
            index = int(arg) - 1
            if not 0 <= index < len(items):
                print("That session does not exist.")
                return session
            sid = items[index]["id"]
        try:
            loaded = store.load_session(sid)
        except (OSError, ValueError):
            print(f"Cannot load session {sid}.")
            return session
        title = loaded.get("title") or "(untitled)"
        print(f"Loaded {loaded['id']}: {title} ({len(loaded['messages'])} messages)")
        return loaded

    items = store.list_sessions()
    if not items:
        print("(no saved sessions)")
        return session
    for i, item in enumerate(items[:20], 1):
        print(
            f"  {i}. {item['created']}  {item['title'] or '(untitled)'}"
            f"  [{item['id']}]"
        )
    print("Use /sessions N to load one.")
    return session


def print_subagent(item):
    print(ui.c("task: " + (item.get("task") or "(no task)"), ui.BOLD))
    for step in item.get("steps") or []:
        print(ui.c("  " + step, ui.DIM))
    print()
    md = ui.Markdown()
    md.feed((item.get("answer") or "(no answer)") + "\n")


def show_subagents(session, arg):
    items = session.get("subagents") or []
    if not items:
        print(ui.c("  (no subagents in this session)", ui.DIM))
        return
    if arg:
        index = int(arg) - 1 if arg.isdigit() else -1
        if not 0 <= index < len(items):
            print("That subagent does not exist.")
            return
        print_subagent(items[index])
        return
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('created', '')}  {(item.get('task') or '')[:60]}")
    print(ui.c("  /subagents N to see its conversation.", ui.DIM))


def pick_subagent(session):
    items = session.get("subagents") or []
    if not items:
        print(ui.c("  (no subagents in this session)", ui.DIM))
        return
    try:
        from prompt_toolkit.shortcuts import radiolist_dialog
    except ImportError:
        show_subagents(session, "")
        return
    result = radiolist_dialog(
        title="subagents",
        text="Choose one to see its conversation:",
        values=[
            (i, f"{item.get('created', '')}  {(item.get('task') or '')[:70]}")
            for i, item in enumerate(items)
        ],
    ).run()
    if result is not None:
        print_subagent(items[result])


def skill_rows(cfg):
    print("  core skills are always loaded and cannot be disabled:")
    for row in skills.status(cfg):
        if row["tier"] == "core":
            state = "loaded" if row["loaded"] else "over budget"
            print(f"    [core] {row['id']:<16} {state:<12} {row['desc']}")
    print("  optional skills:")
    for row in skills.status(cfg):
        if row["tier"] == "core":
            continue
        mark = "[x]" if row["active"] else "[ ]"
        state = "loaded" if row["loaded"] else ("over budget" if row["active"] else "off")
        print(f"    {mark:<6} {row['id']:<16} {state:<12} {row['desc']}")
    skipped = [row["id"] for row in skills.status(cfg) if row["active"] and not row["loaded"]]
    if skipped:
        print(ui.c(f"  ! over budget, not loaded: {', '.join(skipped)}", ui.YELLOW))
    print(ui.c("  /skills on|off <id> · /skills only <id...> · /skills (menu)", ui.DIM))


def pick_skills(cfg):
    try:
        from prompt_toolkit.shortcuts import checkboxlist_dialog
    except ImportError:
        print("prompt_toolkit is not available; use /skills on|off <id>.")
        return
    optional = [row for row in skills.status(cfg) if row["tier"] != "core"]
    if not optional:
        print("No optional skills found.")
        return
    selected = checkboxlist_dialog(
        title="skills",
        text="Space toggles. Enter saves. Core skills are always active.",
        values=[(row["id"], f"{row['id']} - {row['desc']}") for row in optional],
        default_values=[row["id"] for row in optional if row["active"]],
    ).run()
    if selected is not None:
        cfg["skills"] = sorted(selected)
        store.save_config(cfg)
        print(f"Enabled optional skills: {', '.join(cfg['skills']) or '(none)'}")
        skill_rows(cfg)


def show_skills(cfg, arg):
    parts = arg.split()
    if not parts:
        skill_rows(cfg)
        if sys.stdin.isatty():
            pick_skills(cfg)
        return
    action = parts[0].lower()
    ids = [item for chunk in parts[1:] for item in chunk.replace(",", " ").split()]
    try:
        if action == "on" and ids:
            for skill_id in ids:
                skills.set_enabled(cfg, skill_id, True)
        elif action == "off" and ids:
            for skill_id in ids:
                skills.set_enabled(cfg, skill_id, False)
        elif action == "only":
            skills.set_only(cfg, ids)
        else:
            print("Use /skills, /skills on <id>, /skills off <id> or /skills only <id...>")
            return
    except skills.SkillError as exc:
        print(ui.c(f"  ! {exc}", ui.RED))
        return
    store.save_config(cfg)
    skill_rows(cfg)


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
            raise RuntimeError("Ollama is not responding.")
        cfg = store.load_config()
        cfg["model"] = state.get("model") or cfg["model"]
        names = model_names()
        if cfg["model"] not in names and f"{cfg['model']}:latest" not in names:
            raise RuntimeError(f"The model {cfg['model']} is not downloaded.")

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
            state["last_context_tokens"] = session.get("last_context_tokens")
            state["last_context_limit"] = session.get("last_context_limit")

        if session.get("messages"):
            store.save_session(session)
        state["session_id"] = session["id"]
        if cancel_event.is_set() or outcome == "cancelled":
            state["status"] = "stopped"
        elif outcome == "error":
            state["status"] = "error"
            state["error"] = state.get("last_event") or "The turn ended with an error."
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
        return None, "Another external request is starting; try again."
    try:
        previous = bridge.read_state(root)
        if bridge.busy_state(root, previous):
            return None, "Burton is already busy in this folder."
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
        state["error"] = f"Could not start Burton in the background: {exc}"
        bridge.write_state(root, state)
        return None, state["error"]
    return state, None


def update_idle_state(root, update):
    descriptor = bridge.acquire_submit_lock(root)
    if descriptor is None:
        return None, "Another external operation is starting; try again."
    try:
        state = bridge.read_state(root)
        if bridge.busy_state(root, state):
            return None, "Burton is busy; wait or stop the turn before changing the session."
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
        getattr(args, "skills", None) is not None,
        args.approve or args.deny,
    ]
    if sum(selected) > 1:
        print("Use one external operation per invocation.", file=sys.stderr)
        return 2

    state = bridge.read_state(root)
    if args.talk is not None or args.compact:
        if args.talk is not None and not args.talk.strip():
            print("--talk needs a non-empty message.", file=sys.stderr)
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
                print("Timed out waiting.", file=sys.stderr)
                return 124
            time.sleep(0.2)
        state = bridge.status_payload(root)
        if state.get("response"):
            print(state["response"])
        if state.get("status") in {"error", "stale"}:
            print(state.get("error") or "The worker ended with an error.", file=sys.stderr)
            return 1
        return 0
    if args.stop or args.exit:
        stopped = bridge.request_cancel(root)
        print(json.dumps({"stop_requested": stopped}, ensure_ascii=False))
        return 0 if stopped else 1
    if args.approve or args.deny:
        accepted = bridge.request_approval(root, state.get("request_id"), bool(args.approve))
        if not accepted:
            print("There is no pending permission.", file=sys.stderr)
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
            print(f"Could not query Ollama: {exc}", file=sys.stderr)
            return 1
        if args.models:
            model = args.models
            if model not in names and f"{model}:latest" not in names:
                print(f"The model {model} is not downloaded.", file=sys.stderr)
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
                    print("That session does not exist.", file=sys.stderr)
                    return 1
                selected_session = items[index]["id"]
            try:
                loaded = store.load_session(selected_session)
            except (OSError, ValueError):
                print(f"Cannot load session {selected_session}.", file=sys.stderr)
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
    if getattr(args, "skills", None) is not None:
        selected_skills = args.skills.strip()
        try:
            if selected_skills.lower() in {"default", "auto"}:
                cfg.pop("skills", None)
            elif selected_skills:
                action, separator, rest = selected_skills.partition(":")
                ids = [item.strip() for item in rest.replace(",", " ").split() if item.strip()]
                if separator and action in {"on", "off"}:
                    for skill_id in ids:
                        skills.set_enabled(cfg, skill_id, action == "on")
                elif separator:
                    raise skills.SkillError(f"unknown action: {action}")
                else:
                    skills.set_only(cfg, selected_skills.replace(",", " ").split())
        except skills.SkillError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        store.save_config(cfg)
        print(json.dumps(skills.status(cfg), ensure_ascii=False))
        return 0
    if args.subagents is not None:
        if not state.get("session_id"):
            print("There is no active external session.", file=sys.stderr)
            return 1
        try:
            session = store.load_session(state["session_id"])
        except (OSError, ValueError):
            print("Could not load the external session.", file=sys.stderr)
            return 1
        items = session.get("subagents") or []
        if args.subagents.strip():
            index = int(args.subagents) - 1 if args.subagents.isdigit() else -1
            if not 0 <= index < len(items):
                print("That subagent does not exist.", file=sys.stderr)
                return 1
            print(json.dumps(items[index], ensure_ascii=False))
        else:
            print(json.dumps(items, ensure_ascii=False))
        return 0
    return None


def main():
    parser = argparse.ArgumentParser(description="Minimal coding agent on top of Ollama")
    parser.add_argument("--root", help="project directory (default: current)")
    parser.add_argument("--model", help="Ollama model")
    parser.add_argument("--steps", type=int, help="maximum steps per turn")
    parser.add_argument("--plan", action="store_true", help="start in read-only mode")
    parser.add_argument(
        "--allow-self-edit",
        action="store_true",
        help="allow the AI to modify burton_ai code",
    )
    parser.add_argument("--talk", metavar="TEXT", help="send a message in the background")
    parser.add_argument("--response", action="store_true", help="show the current response")
    parser.add_argument("--status", action="store_true", help="show state as JSON")
    parser.add_argument("--wait", action="store_true", help="wait for the end and return the response")
    parser.add_argument("--timeout", type=float, help="seconds to wait for --wait")
    parser.add_argument("--compact", action="store_true", help="compact the external session")
    parser.add_argument("--stop", action="store_true", help="request stopping the active turn")
    parser.add_argument("--exit", action="store_true", help="external alias of --stop")
    parser.add_argument("--new", "--clear", action="store_true", help="create a new external session")
    parser.add_argument("--toggle-plan", action="store_true", help="toggle external read-only mode")
    parser.add_argument("--models", nargs="?", const="", help="list models or activate one")
    parser.add_argument("--sessions", nargs="?", const="", help="list sessions or load one by ID/number")
    parser.add_argument("--skills", nargs="?", const="", help="list skills or enable only these ids")
    parser.add_argument("--subagents", nargs="?", const="", help="list subagents or show one")
    approvals = parser.add_mutually_exclusive_group()
    approvals.add_argument("--approve", action="store_true", help="allow the pending @run")
    approvals.add_argument("--deny", action="store_true", help="deny the pending @run")
    parser.add_argument("--worker", metavar="REQUEST_ID", help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = store.load_config()
    if args.model:
        cfg["model"] = args.model
    if args.steps:
        cfg["max_steps"] = args.steps

    root = Path(args.root or ".").expanduser().resolve()
    if not root.is_dir():
        print(f"Directory does not exist: {root}")
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
        print(ui.c(f"  Enter sends {ui.glyph('·', '-')} Shift+Enter new line {ui.glyph('·', '-')} Ctrl+Backspace delete word {ui.glyph('·', '-')} Ctrl+S subagents {ui.glyph('·', '-')} / commands", ui.DIM))
    print()

    try:
        while True:
            context_tokens = session.get("last_context_tokens", 0)
            context_limit = session.get("last_context_limit", cfg["num_ctx"])
            if context_tokens and context_limit:
                print(
                    ui.c(
                        f"  Last turn context: {context_tokens:,}/{context_limit:,} "
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
                    print(f"New session {ui.c(session['id'], ui.DIM)}")
                elif command == "/plan":
                    tools.plan = not tools.plan
                    print(
                        ui.c("Plan mode ON (read-only).", ui.YELLOW)
                        if tools.plan
                        else ui.c("Plan mode off.", ui.DIM)
                    )
                elif command == "/models":
                    show_models(cfg, session)
                elif command == "/sessions":
                    session = show_sessions(session, arg.strip())
                elif command == "/subagents":
                    show_subagents(session, arg.strip())
                elif command == "/skills":
                    show_skills(cfg, arg.strip())
                elif command == "/compact":
                    compacted, result, stats = agent.compact_session(session, cfg)
                    if compacted:
                        store.save_session(session)
                        print(
                            "Conversation compacted. "
                            f"History reduced to {len(session['messages'])} message."
                        )
                        if stats and stats.get("prompt_tokens"):
                            count = stats["prompt_tokens"]
                            limit = cfg["num_ctx"]
                            print(
                                f"Context used for the summary: {count:,}/{limit:,} "
                                f"tokens ({count * 100 / limit:.1f}%)."
                            )
                        print("Summary:")
                        print(result[:1200])
                    else:
                        print(ui.c(result, ui.YELLOW))
                else:
                    print(ui.c("Unknown command. /help for the list.", ui.RED))
                continue

            session["messages"].append({"role": "user", "content": line})
            if not session["title"]:
                session["title"] = line[:60]
            md = ui.Markdown()
            try:
                agent.run_turn(session, cfg, tools, md)
            except KeyboardInterrupt:
                print("\n[interrupted]")
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

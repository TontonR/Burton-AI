import json
import os
import platform
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import ui
import skills
from tools import Directive, ToolError, Tools, parse_directives, resolve, truncate

API = "http://127.0.0.1:11434"
WRITE_RE = re.compile(
    r"\b(escrib\w*|cre[ao]\w*|modific\w*|cambi\w*|arregl\w*|corrig\w*|corrij\w*|"
    r"a[ñn]ad\w*|agreg\w*|elimin\w*|borr\w*|renombr\w*|refactor\w*|implement\w*|"
    r"actualiz\w*|guard\w*|hazme|hazlo|hazla|haz|constru\w*|program\w*|"
    r"genera\w*|desarroll\w*|prepara\w*|monta\w*|aplic\w*|write|edit|fix|create|"
    r"add|remove|delete|update|make\s+me|build\s+me)\b",
    re.IGNORECASE,
)
CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)
CODE_EXTENSIONS = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "bash": "sh",
    "sh": "sh",
    "powershell": "ps1",
    "ps1": "ps1",
    "json": "json",
    "yaml": "yaml",
    "yml": "yml",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "rust": "rs",
    "go": "go",
}
FILE_CREATION_RE = re.compile(
    r"@write\b|\b(?:crea\w*|escrib\w*|genera\w*|hazme|implementa\w*|"
    r"create|make\s+me|build\s+me|"
    r"programa\w*|desarrolla\w*)\b.{0,120}\b(?:archivo|fichero|programa|"
    r"script|juego|aplicaci[oó]n|m[oó]dulo|clase|funci[oó]n|"
    r"\d+\s+en\s+raya|tres\s+en\s+raya|python|file|program|script|game|app)\b",
    re.IGNORECASE | re.DOTALL,
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
    "do not create",
    "don't create",
    "do not write",
    "don't write",
    "do not modify",
    "don't modify",
    "only tell me",
    "read only",
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


def requests_file_creation(text):
    lowered = text.lower()
    if any(phrase in lowered for phrase in BLOCK_PHRASES):
        return False
    return bool(FILE_CREATION_RE.search(text))


def extract_code_file(request_text, response_text):
    match = CODE_BLOCK_RE.search(response_text)
    if not match or not match.group(2).strip():
        return None
    language = match.group(1).lower()
    extension = CODE_EXTENSIONS.get(language)
    if extension is None:
        return None

    before_code = response_text[:match.start()]
    for source in (request_text, before_code):
        target = FILE_RE.search(source)
        if target:
            return target.group(0).rstrip(".,;:!?"), match.group(2).rstrip(), language

    normalized = unicodedata.normalize("NFKD", request_text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    if re.search(r"\b(?:3|tres)\s+en\s+raya\b", normalized):
        stem = "tres_en_raya"
    else:
        subject = re.search(
            r"\b(?:hazme|crea\w*|genera\w*|implementa\w*|programa\w*|"
            r"create|make\s+me|build\s+me)\s+(?:a\s+|an?\s+|un\s+|una\s+|"
            r"el\s+|la\s+)?(.{1,50}?)\s+(?:in\s+(?:python|javascript|"
            r"typescript)|en\s+(?:python|javascript|typescript)|for\s+"
            r"(?:terminal|console)|para\s+(?:terminal|consola)|por\s+terminal)\b",
            normalized,
        )
        stem = subject.group(1) if subject else "nuevo_archivo"
        stem = re.sub(r"\b(?:un|una|el|la|programa|archivo|fichero)\b", " ", stem)
        stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_") or "nuevo_archivo"
    return f"{stem}.{extension}", match.group(2).rstrip(), language


def write_code_file(request_text, response_text, tools):
    extracted = extract_code_file(request_text, response_text)
    if extracted is None:
        return None
    path, body, _language = extracted
    try:
        destination = resolve(tools.root, path)
        if destination.exists():
            return None
    except (OSError, ValueError, ToolError):
        return None
    result = tools.execute(Directive("write", path, body))
    if result.startswith("ERROR"):
        return None
    return path, body, result


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

REFUSAL_RE = re.compile(
    r"no (?:puedo|tengo) (?:acceder|leer|abrir|ejecutar)|fuera del directorio|"
    r"no tengo acceso|no puedo ver (?:el|los) (?:archivo|fichero)|"
    r"i (?:can't|cannot|am unable to) (?:access|read|open|see)|"
    r"outside (?:the )?(?:project|directory|workspace)|i don't have access",
    re.IGNORECASE,
)
FILE_RE = re.compile(
    r"\b[\w./\\-]+\.(?:md|py|txt|json|toml|ya?ml|js|ts|jsx|tsx|css|html|sh|ps1|cfg|ini)\b",
    re.IGNORECASE,
)


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
                lines.append("... (tree truncated)")
                return "\n".join(lines)
            lines.append(f"{indent}{name}")
    return "\n".join(lines) or "(empty project)"


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
    return "\n\nProject instructions (AGENTS.md):\n" + text[:2000]


def build_system_prompt(root, cfg, plan=False):
    skill_text = skills.load_text(cfg)
    skills_note = f"\nProject skills:\n{skill_text}\n" if skill_text else ""
    auto_note = ""
    auto_line = ""
    auto_rule = ""
    if skills.is_active(cfg, "auto-skills"):
        auto_line = "@skills <id,id>\n"
        auto_rule = (
            "- If the task needs an optional skill that is not [active], send "
            "`@skills id` as your first response.\n"
        )
        auto_note = (
            "\nOptional skills (activate with @skills id,id):\n"
            + skills.catalog(cfg)
            + "\n"
        )
    plan_note = ""
    if plan:
        plan_note = (
            "PLAN MODE: use only @ls and @read. Do not write or run anything. "
            "Deliver the plan and finish with @done.\n"
        )
    shell = "cmd.exe" if os.name == "nt" else "sh"
    return f"""You are a coding agent working in {root}.
Environment: {platform.system()} · shell: {shell} · Python {platform.python_version()}

Directives, one per line:
@ls <path>
@read <path> [start-end]
{auto_line}@write <path>
FULL file content, raw, no code fences
@endwrite
@run <command>
@agent <task>
@done

@write example:
@write hello.py
def hello():
    return "hi"
@endwrite

Rules:
- Execute the task with directives. Never ask the user to run them.
- Emit ONE directive per response and wait for its result.
- Use paths relative to the project root, never absolute paths.
- Never claim a file was written or a command succeeded without its result.
- If the user only asks for information, answer in text and do not modify files.
- If the user greets or chats, answer in text without directives.
- Use @agent only for read-only research.
{auto_rule}- When finished, write @done on its own line after any final answer.
{skills_note}{auto_note}{plan_note}{project_notes(root)}
Project tree:
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
                f"cannot connect to Ollama at {API} ({exc.reason}). Is it running?"
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
        return False, "There is no conversation to compact.", None

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
                "Summarise the history as working memory to continue the same "
                "conversation. Keep the original goal, requirements and constraints, "
                "verified facts, decisions, files/changes made, pending errors and the "
                "next step. Do not invent or execute actions. Be concise but complete; "
                "return only the summary."
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
        return False, f"Conversation was not compacted: {exc}", None
    if not summary.strip():
        return False, "The model returned an empty summary; history was kept.", None

    session["messages"] = [
        {
            "role": "user",
            "content": "Compact summary of the previous conversation:\n\n"
            + summary.strip(),
        }
    ]
    session["last_context_tokens"] = stats.get("prompt_tokens", 0)
    session["last_context_limit"] = cfg["num_ctx"]
    return True, summary.strip(), stats


def clean_answer(text):
    lines = [line for line in text.splitlines() if not line.strip().startswith("@")]
    return "\n".join(lines).strip()


def build_subagent_prompt(root, cfg):
    skill_text = skills.load_text(cfg)
    skills_note = f"\nProject skills:\n{skill_text}\n" if skill_text else ""
    return f"""You are a read-only subagent working in {root}.
Research the task and return a short, concrete answer.

Allowed directives, one per line:
@ls <path>
@read <path> [start-end]
@done

Rules:
- You have real file access with @ls and @read. Never claim otherwise.
- Emit ONE directive per response and wait for its result.
- Do not modify files or run commands.
- When you have the answer, write it as plain text without directives and without @read line numbers.
{skills_note}{project_notes(root)}
Project tree:
{file_tree(root)}"""


def run_subagent(task, cfg, root, log=print, record=None, cancel_event=None):
    if not task.strip():
        return "ERROR: missing subagent task"
    tools = Tools(root, plan=True)
    messages = [{"role": "user", "content": task}]
    last = ""
    for _ in range(min(6, cfg["max_steps"])):
        if cancel_event is not None and cancel_event.is_set():
            return last or "[interrupted]"
        context = [
            {"role": "system", "content": build_subagent_prompt(root, cfg)}
        ] + trim_history(messages, cfg["num_ctx"] * 2)
        try:
            text, _ = stream_with_indicator(
                cfg["model"], context, cfg, lambda piece: None, cancel_event
            )
        except RuntimeError as exc:
            return f"ERROR from subagent: {exc}"
        messages.append({"role": "assistant", "content": text})
        answer = clean_answer(text)
        if answer:
            last = answer
        directives = parse_directives(text)
        if not directives:
            return answer or "(no answer)"
        if directives[0].name == "done":
            return answer or last or "(no answer)"
        directive = directives[0]
        result = tools.execute(directive)
        step = f"@{directive.name} {directive.arg}".strip()
        log(ui.c(f"     subagent: {step}"[:120], ui.DIM))
        if record is not None:
            record.setdefault("steps", []).append(step[:200])
        messages.append(
            {
                "role": "user",
                "content": f"Result of @{directive.name} {directive.arg}:\n{result}",
            }
        )
    return (last or "(no answer)") + "\n[subagent: step limit]"


def run_turn(session, cfg, tools, on_chunk, log=print, cancel_event=None):
    messages = session["messages"]
    request_text = messages[-1]["content"] if messages else ""
    turn_cfg = dict(cfg)
    write_ok = allows_writes(request_text)
    hide_generation = write_ok and requests_file_creation(request_text)
    retried = False
    file_creation_retry = False
    file_created = False
    written_python = []
    model_ran = False
    review_asked = False
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
        log(
            ui.c("  " + ui.glyph("✓", "ok"), ui.GREEN)
            + " "
            + ui.c(" · ".join(parts), ui.DIM)
        )
        if prompt_tokens:
            limit = cfg["num_ctx"]
            percent = prompt_tokens * 100 / limit
            session["last_context_tokens"] = prompt_tokens
            session["last_context_limit"] = limit
            log(
                ui.c(
                    f"  Context: {prompt_tokens:,}/{limit:,} tokens "
                    f"({percent:.1f}%; Ollama measurement)",
                    ui.CYAN,
                )
            )
        return outcome

    def syntax_check(rel):
        """Auto-run py_compile after a Python file is written."""
        log(
            "  "
            + ui.c("->", ui.MAGENTA)
            + " "
            + ui.c("@run", ui.BOLD, ui.CYAN)
            + " "
            + ui.c(f"python -m py_compile {rel}", ui.DIM)
        )
        output = tools.execute(Directive("run", f'python -m py_compile "{rel}"'))
        if "exit 0" in output:
            log(ui.c("     syntax ok", ui.GREEN))
        else:
            log(ui.c("     syntax error", ui.RED))
            for line in output.splitlines()[:20]:
                log(ui.c(f"     {line}", ui.RED))
        return output

    seen = set()
    repeated_directives = 0

    for step in range(cfg["max_steps"]):
        if cancel_event is not None and cancel_event.is_set():
            log(ui.c("  [interrupted]", ui.YELLOW))
            return finish("cancelled")
        if step:
            log("")
        system = {"role": "system", "content": build_system_prompt(tools.root, turn_cfg, tools.plan)}
        context = [system] + trim_history(messages, cfg["num_ctx"] * 3)
        try:
            text, stats = stream_with_indicator(
                cfg["model"],
                context,
                cfg,
                on_chunk,
                cancel_event,
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
            log(ui.c("  [interrupted]", ui.YELLOW))
            return finish("cancelled")

        directives = parse_directives(text)
        if not directives:
            target = FILE_RE.search(request_text)
            if not retried and target and REFUSAL_RE.search(text):
                retried = True
                log(ui.c("  ! the model refused; reminding it that it can read", ui.YELLOW))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"You are not outside the project: the root is {tools.root} and you have real access. "
                            f"Reply with ONLY the needed directive, for example: @read {target.group(0)}"
                        ),
                    }
                )
                continue
            if hide_generation:
                if not file_created:
                    written = write_code_file(request_text, text, tools)
                    if written is not None:
                        path, body, result = written
                        file_created = True
                        file_creation_retry = True
                        log(ui.c(f"  -> @write {path}", ui.DIM))
                        log(ui.c(f"     {result}", ui.GREEN))
                        seen.add(("write", path, body))
                        check = ""
                        if path.lower().endswith(".py"):
                            written_python.append(path)
                            check = "\nAuto syntax check:\n" + syntax_check(path)
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Result of @write {path}:\n{result}{check}\n"
                                    "The previous code block was already saved. Do not show it "
                                    "or write it again. If it needs testing, propose a suitable "
                                    "@run command."
                                ),
                            }
                        )
                        continue
                if not file_creation_retry:
                    file_creation_retry = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You have not modified any file yet. Use a single @write "
                                "directive with a suitable filename and the full content. "
                                "If you already proposed code, turn it into the @write body; "
                                "do not show it again as the answer. Wait for the real result "
                                "and never claim the file exists before it is confirmed."
                            ),
                        }
                    )
                    continue
                if not file_created:
                    log(
                        ui.c(
                            "  ! no directive was executed; the file was not created",
                            ui.YELLOW,
                        )
                    )
            return finish("text")

        directive = directives[0]
        if directive.name == "done":
            if written_python and not model_ran and not review_asked:
                review_asked = True
                files = ", ".join(written_python[-3:])
                log(ui.c("  ! self-review before done", ui.YELLOW))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Before you finish, review your work against the original "
                            f"request:\n{request_text[:600]}\n"
                            f"Files written: {files}\n"
                            "Check every requirement, trace the real behaviour step by "
                            "step, and look for a missing menu, exit, validation or edge "
                            "case. Run a real check with @run if the program can be "
                            "tested non-interactively. If something is missing or wrong, "
                            "fix it with @write and verify again. If it is truly complete, "
                            "reply with @done."
                        ),
                    }
                )
                continue
            return finish("done")

        key = (directive.name, directive.arg, directive.body)
        if key in seen:
            repeated_directives += 1
            if repeated_directives > 1:
                repeated = f"@{directive.name} {directive.arg}".strip()
                log(
                    ui.c(
                        f"  ! loop stopped: the model repeated {repeated[:80]}",
                        ui.YELLOW,
                    )
                )
                return finish("loop")
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"You already ran @{directive.name} {directive.arg}. "
                        "The previous result is in the conversation: use it and continue "
                        "with a different step or finish with @done. Do not repeat the directive."
                    ),
                }
            )
            continue
        seen.add(key)

        log(
            "  "
            + ui.c("->", ui.MAGENTA)
            + " "
            + ui.c("@" + directive.name, ui.BOLD, ui.CYAN)
            + ((" " + ui.c(directive.arg, ui.DIM)) if directive.arg else "")
        )
        check = ""
        if directive.name == "skills":
            ids = directive.arg.replace(",", " ").split()
            try:
                if not ids:
                    raise skills.SkillError("missing skill id")
                added = [skills.set_enabled(turn_cfg, item, True).id for item in ids]
                result = "active skills: " + ", ".join(added)
            except skills.SkillError as exc:
                result = f"ERROR: {exc}"
        elif directive.name == "agent":
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
                "ERROR: the user did not ask to modify files. "
                "Answer with the information in text and finish with @done."
            )
        else:
            if directive.name == "run":
                explanation = directive_explanation(text, "run")
                tools.confirm_reason = explanation or (
                    "Burton did not explain why. Original task: "
                    + request_text[:400]
                )
            else:
                tools.confirm_reason = request_text
            indicator = None
            if directive.name == "run":
                indicator = ui.ThinkingIndicator("running command", delay=0.3)
                indicator.start()
            try:
                result = tools.execute(directive)
            finally:
                if indicator is not None:
                    indicator.stop()
            if directive.name == "write" and not result.startswith("ERROR"):
                file_created = True
                file_creation_retry = True
                if directive.arg.lower().endswith(".py"):
                    written_python.append(directive.arg)
            elif directive.name == "run" and not result.startswith("ERROR"):
                model_ran = True

        if result.startswith("ERROR"):
            log(ui.c(f"     {result}", ui.RED))
        elif directive.name == "run":
            for line in result.splitlines()[:40]:
                color = ui.GREEN if line.strip() == "exit 0" else None
                log(ui.c(f"     {line}", color) if color else f"     {line}")
        elif directive.name == "write":
            for line in result.splitlines()[:20]:
                log(ui.c(f"     {line}", ui.GREEN))
        elif directive.name == "skills":
            for line in result.splitlines()[:20]:
                log(ui.c(f"     {line}", ui.CYAN))
        elif directive.name == "agent":
            for line in result.splitlines()[:20]:
                log(ui.c(f"     {line}", ui.DIM))

        if (
            directive.name == "write"
            and not result.startswith("ERROR")
            and directive.arg.lower().endswith(".py")
        ):
            check = "\nAuto syntax check:\n" + syntax_check(directive.arg)

        feedback = f"Result of @{directive.name} {directive.arg}:\n{result}{check}"
        if len(directives) > 1:
            ignored = len(directives) - 1
            feedback += (
                f"\n\nI ignored {ignored} more directive(s) from that message: "
                "write one directive per response and wait for the result."
            )
        messages.append({"role": "user", "content": feedback})

    log(ui.c(f"  ! limit of {cfg['max_steps']} steps", ui.YELLOW))
    return finish("max_steps")

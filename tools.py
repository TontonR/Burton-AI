import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import store

DIRECTIVE_RE = re.compile(r"^@(\w+)\s*(.*)$")
RANGE_RE = re.compile(r"^\[?(\d+)[-:](\d+)\]?$")
BULLET_RE = re.compile(r"^[-*]\s+")
MAX_READ_LINES = 200
MAX_RESULT_CHARS = 4000


class ToolError(Exception):
    pass


@dataclass
class Directive:
    name: str
    arg: str
    body: str | None = None


def _clean(line):
    line = line.strip()
    line = BULLET_RE.sub("", line)
    return line.strip("`").strip()


def _strip_outer_fence(body_lines):
    first = next((i for i, line in enumerate(body_lines) if line.strip()), None)
    if first is None:
        return body_lines
    last = next(
        (i for i in range(len(body_lines) - 1, -1, -1) if body_lines[i].strip()),
        None,
    )
    if (
        first < last
        and body_lines[first].strip().startswith("```")
        and body_lines[last].strip().startswith("```")
    ):
        return body_lines[first + 1:last]
    return body_lines


def _body_end(lines, start):
    """Última valla que cierra el bloque: seguida de una directiva o del final.

    El contenido puede traer sus propios bloques ``` (Markdown, Python...), así que
    no vale con cortar en la primera valla.
    """
    candidate = None
    for i in range(start, len(lines)):
        if not lines[i].strip().startswith("```"):
            continue
        nxt = i + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        if nxt >= len(lines) or lines[nxt].strip().startswith("@"):
            candidate = i
    if candidate is not None:
        return candidate
    for i in range(len(lines) - 1, start - 1, -1):
        if lines[i].strip().startswith("```"):
            return i
    return None


def parse_directives(text):
    """Extrae directivas de una respuesta. Ignora todo lo que hay dentro de fences."""
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue

        line = _clean(lines[i])
        match = DIRECTIVE_RE.match(line)
        if not match:
            i += 1
            continue

        name = match.group(1).lower()
        arg = match.group(2).strip()
        body = None
        i += 1

        if name == "write":
            end_marker = next(
                (j for j in range(i, len(lines)) if lines[j].strip() == "@endwrite"),
                None,
            )
            if end_marker is not None:
                body = "\n".join(_strip_outer_fence(lines[i:end_marker]))
                i = end_marker + 1
            else:
                fence = i
                while fence < len(lines) and not lines[fence].strip().startswith("```"):
                    fence += 1
                if fence < len(lines):
                    end = _body_end(lines, fence + 1)
                    if end is not None:
                        body = "\n".join(lines[fence + 1:end])
                        i = end + 1

        out.append(Directive(name, arg, body))

    return out


def resolve(root, raw):
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        raise ToolError("falta la ruta")
    path = Path(raw)
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    root = root.resolve()
    if path != root and root not in path.parents:
        raise ToolError(f"ruta fuera del proyecto: {raw}")
    return path


def truncate(text, limit=MAX_RESULT_CHARS):
    if len(text) <= limit:
        return text
    half = (limit - 40) // 2
    return text[:half] + "\n...[truncado]...\n" + text[-half:]


class Tools:
    def __init__(self, root, plan=False, confirm=None, allow_self_edit=False):
        self.root = Path(root).resolve()
        self.plan = plan
        self.confirm = confirm or (lambda cmd, reason: True)
        self.confirm_reason = ""
        self.allow_self_edit = allow_self_edit
        self.app_root = Path(__file__).resolve().parent

    def execute(self, directive):
        handler = getattr(self, "do_" + directive.name, None)
        if not handler:
            return f"ERROR: directiva desconocida @{directive.name}. Usa @ls, @read, @write, @run o @done."
        try:
            return truncate(handler(directive))
        except ToolError as exc:
            return f"ERROR: {exc}"
        except Exception as exc:
            return f"ERROR: {type(exc).__name__}: {exc}"

    def do_done(self, directive):
        return "fin"

    def do_ls(self, directive):
        path = resolve(self.root, directive.arg or ".")
        if not path.exists():
            raise ToolError(f"no existe: {directive.arg}")
        if path.is_file():
            return path.relative_to(self.root).as_posix()
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [p.name + ("/" if p.is_dir() else "") for p in entries[:200]]
        rest = len(entries) - len(lines)
        if rest > 0:
            lines.append(f"... y {rest} más")
        return "\n".join(lines) or "(vacío)"

    def do_read(self, directive):
        parts = directive.arg.split()
        start, end = 1, None
        if parts and RANGE_RE.match(parts[-1]):
            start = int(RANGE_RE.match(parts[-1]).group(1))
            end = int(RANGE_RE.match(parts[-1]).group(2))
            parts = parts[:-1]
        if not parts:
            raise ToolError("falta la ruta")
        path = resolve(self.root, " ".join(parts))
        if path.is_dir():
            return self.do_ls(Directive("ls", directive.arg))
        if not path.exists():
            raise ToolError(f"no existe: {directive.arg}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return "(fichero vacío)"
        start = max(1, start)
        end = min(end or len(lines), len(lines))
        stop = min(end, start + MAX_READ_LINES - 1)
        chunk = lines[start - 1:stop]
        out = "\n".join(f"{n:>4}| {line}" for n, line in enumerate(chunk, start))
        if stop < end:
            out += f"\n...[quedan {end - stop} líneas; usa @read ruta {stop + 1}-{end}]"
        return out

    def do_write(self, directive):
        if self.plan:
            raise ToolError("modo plan: escritura bloqueada")
        if not directive.arg:
            raise ToolError("falta la ruta")
        if directive.body is None or not directive.body.strip():
            raise ToolError("falta el bloque ``` con el contenido completo")
        path = resolve(self.root, directive.arg)
        if path.is_dir():
            raise ToolError("la ruta es un directorio")
        content = directive.body.rstrip("\n") + "\n"
        if path.exists() and path.read_text(encoding="utf-8", errors="replace") == content:
            return f"sin cambios: {path.relative_to(self.root).as_posix()}"
        if (
            not self.allow_self_edit
            and path.parent == self.app_root
            and path.suffix == ".py"
        ):
            raise ToolError(
                "es código de burton_ai en ejecución; usa --allow-self-edit si de verdad quieres modificarlo"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        saved = store.backup(path) if path.exists() else None
        path.write_text(content, encoding="utf-8")
        rel = path.relative_to(self.root).as_posix()
        out = f"escrito {rel} ({len(directive.body.splitlines())} líneas)"
        if saved:
            out += f"; copia previa en backups/{saved.name}"
        return out

    def do_run(self, directive):
        if self.plan:
            raise ToolError("modo plan: ejecución bloqueada")
        cmd = directive.arg.strip()
        if not cmd:
            raise ToolError("falta el comando")
        if not self.confirm(cmd, self.confirm_reason):
            return "cancelado por el usuario"
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: timeout de 120s"
        out = (result.stdout or "").strip()
        if result.stderr:
            out += ("\n[stderr]\n" + result.stderr.strip())
        return f"exit {result.returncode}\n{out or '(sin salida)'}"

import os
import re
import shutil
import sys
import threading
import time

ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if ENABLED and os.name == "nt":
    os.system("")


def _can_encode(text):
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


UNICODE = _can_encode("╭─│╰❯·")

SUBAGENTS_KEY = "\x00subagents"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


def c(text, *codes):
    if not ENABLED or not codes:
        return text
    return "".join(codes) + text + RESET


def glyph(unicode_char, ascii_fallback):
    return unicode_char if UNICODE else ascii_fallback


class ThinkingIndicator:
    def __init__(self, label="thinking", delay=0.0):
        self.label = label
        self.delay = delay
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not sys.stdout.isatty() or (
            self._thread is not None and self._thread.is_alive()
        ):
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=1)
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()
        self._thread = None

    def _animate(self):
        if self.delay:
            self._stop_event.wait(self.delay)
        frames = "|/-\\"
        index = 0
        started = time.monotonic()
        while not self._stop_event.is_set():
            elapsed = time.monotonic() - started
            timer = c(f" {elapsed:.1f}s", YELLOW) if elapsed >= 0.5 else ""
            sys.stdout.write(
                "\r\033[2K  "
                + c(frames[index % len(frames)], CYAN)
                + " "
                + c(self.label, DIM)
                + timer
            )
            sys.stdout.flush()
            index += 1
            self._stop_event.wait(0.12)


BOLD_MD = re.compile(r"\*\*(.+?)\*\*")
CODE_MD = re.compile(r"`([^`]+)`")
HEAD_MD = re.compile(r"^(#{1,6})\s+(.*)$")
LINK_MD = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


class Markdown:
    """Render basic markdown line by line as the stream arrives."""

    def __init__(self):
        self.pending = ""
        self.fence = False
        self.writing = False

    def __call__(self, piece):
        self.feed(piece)

    def feed(self, piece):
        self.pending += piece
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self.emit(line)

    def flush(self):
        if self.pending:
            self.emit(self.pending)
            self.pending = ""

    def emit(self, line):
        stripped = line.lstrip()
        if stripped.startswith("@write"):
            self.writing = True
            path = stripped[6:].strip()
            print(
                c("  " + glyph("✎", "~") + " writing ", CYAN) + c(path, BOLD),
                flush=True,
            )
            return
        if stripped.startswith("@endwrite"):
            self.writing = False
            return
        if self.writing:
            print(c("    " + line, GREEN), flush=True)
            return
        if stripped.startswith("@"):
            return
        print(self.render(line), flush=True)

    def render(self, line):
        if line.lstrip().startswith("```"):
            self.fence = not self.fence
            return c(line, DIM)
        if self.fence:
            return c(line, GREEN)
        head = HEAD_MD.match(line)
        if head:
            level = len(head.group(1))
            title = head.group(2).strip()
            return c(title, BOLD, MAGENTA if level <= 2 else CYAN)
        line = LINK_MD.sub(lambda m: f"{m.group(1)} ({m.group(2)})", line)
        line = BOLD_MD.sub(lambda m: c(m.group(1), BOLD), line)
        line = CODE_MD.sub(lambda m: c(m.group(1), YELLOW), line)
        return line


def banner(model, root, plan):
    width = max(50, min(shutil.get_terminal_size().columns - 2, 78))
    inside = width - 4
    title = f"burton_ai  {glyph('·', '-')}  {model}"
    path = str(root)
    if len(path) > inside:
        path = "..." + path[-(inside - 3):]
    top = glyph("╭", "+") + glyph("─", "-") * (width - 2) + glyph("╮", "+")
    bottom = glyph("╰", "+") + glyph("─", "-") * (width - 2) + glyph("╯", "+")
    lines = [
        c(top, MAGENTA),
        c(glyph("│", "|") + " " + title.ljust(inside) + " " + glyph("│", "|"), BOLD),
        c(glyph("│", "|") + " " + path.ljust(inside) + " " + glyph("│", "|"), DIM),
        c(bottom, MAGENTA),
    ]
    if plan:
        lines.append(c("  plan mode: read-only", YELLOW))
    lines.append(
        c(
            "  /help  /plan  /models  /sessions  /skills  /new  /exit",
            DIM,
        )
    )
    return "\n".join(lines)

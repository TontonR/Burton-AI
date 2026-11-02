from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.named_commands import get_by_name
from prompt_toolkit.styles import Style

import store
import ui

COMMANDS = {
    "/new": "nueva conversación",
    "/clear": "nueva conversación (alias)",
    "/plan": "alternar solo lectura",
    "/models": "cambiar de modelo",
    "/sessions": "listar o cargar sesiones",
    "/subagents": "ver subagentes de esta sesión",
    "/compact": "resumir el historial",
    "/help": "ayuda",
    "/exit": "salir",
}

DRAFT = {"text": ""}


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text or "\n" in text:
            return
        for command, description in COMMANDS.items():
            if command.startswith(text):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display_meta=description,
                )


def make_bindings():
    bindings = KeyBindings()

    @bindings.add("enter")
    def _submit(event):
        buffer = event.current_buffer
        state = buffer.complete_state
        if state:
            completion = state.current_completion
            if (
                completion
                and completion.text != buffer.document.current_line_before_cursor
            ):
                buffer.apply_completion(completion)
                return
            buffer.cancel_completion()
        buffer.validate_and_handle()

    def _newline(event):
        event.current_buffer.cancel_completion()
        event.current_buffer.insert_text("\n")

    @bindings.add("c-i")
    def _accept_completion(event):
        buffer = event.current_buffer
        state = buffer.complete_state
        completion = state.current_completion if state else None
        if completion is None:
            completion = next(
                iter(SlashCompleter().get_completions(buffer.document, None)), None
            )
        if completion:
            buffer.apply_completion(completion)

    # VS Code sends a line feed for Shift+Enter/Ctrl+J; some terminals send Alt+Enter.
    bindings.add("escape", "enter")(_newline)
    bindings.add("c-j")(_newline)
    try:
        bindings.add("s-enter")(_newline)
    except ValueError:
        pass

    # Windows Terminal manda Ctrl+Backspace como ^W (c-w). Por defecto solo
    # borra la selección, así que aquí lo hacemos borrar la palabra anterior.
    bindings.add("c-w")(get_by_name("backward-kill-word"))
    bindings.add("c-delete")(get_by_name("kill-word"))

    @bindings.add("c-s")
    def _subagents(event):
        DRAFT["text"] = event.current_buffer.text
        event.app.exit(result=ui.SUBAGENTS_KEY)

    return bindings


def make_reader():
    session = PromptSession(
        multiline=True,
        key_bindings=make_bindings(),
        completer=SlashCompleter(),
        complete_while_typing=True,
        history=FileHistory(str(store.BASE / "history")),
        style=Style.from_dict(
            {
                "prompt": "ansibrightmagenta bold",
                "continuation": "ansibrightblack",
                "completion-menu.completion": "bg:#1c1c1c #cccccc",
                "completion-menu.completion.current": "bg:#5f00af #ffffff",
                "completion-menu.meta.completion": "bg:#1c1c1c #888888",
                "completion-menu.meta.completion.current": "bg:#5f00af #ffffff",
            }
        ),
        prompt_continuation=lambda width, line_number, is_soft_wrap: [
            ("class:continuation", "... ")
        ],
    )

    def read():
        default = DRAFT["text"]
        DRAFT["text"] = ""
        return session.prompt(
            [("class:prompt", ui.glyph("❯", ">") + " ")],
            default=default,
        )

    return read

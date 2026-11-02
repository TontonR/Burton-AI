import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.shortcuts import PromptSession

import input_ui
import ui
from input_ui import SlashCompleter


class CompleterTest(unittest.TestCase):
    def test_lists_matching_commands(self):
        completions = list(
            SlashCompleter().get_completions(Document("/pl"), None)
        )
        self.assertEqual([c.text for c in completions], ["/plan"])

    def test_no_completion_without_slash(self):
        completions = list(
            SlashCompleter().get_completions(Document("hola"), None)
        )
        self.assertEqual(completions, [])

    def test_lists_subagents_command(self):
        completions = list(
            SlashCompleter().get_completions(Document("/sub"), None)
        )
        self.assertEqual([c.text for c in completions], ["/subagents"])

    def test_lists_compact_command(self):
        completions = list(
            SlashCompleter().get_completions(Document("/comp"), None)
        )
        self.assertEqual([c.text for c in completions], ["/compact"])


class CtrlSTest(unittest.TestCase):
    def tearDown(self):
        input_ui.DRAFT["text"] = ""

    def test_ctrl_s_returns_sentinel_and_keeps_draft(self):
        input_ui.DRAFT["text"] = ""
        with create_pipe_input() as inp:
            inp.send_text("borrador\x13")
            session = PromptSession(
                multiline=True,
                key_bindings=input_ui.make_bindings(),
                completer=SlashCompleter(),
                complete_while_typing=True,
                input=inp,
                output=DummyOutput(),
            )
            result = session.prompt("> ")
        self.assertEqual(result, ui.SUBAGENTS_KEY)
        self.assertEqual(input_ui.DRAFT["text"], "borrador")


class EditingShortcutTest(unittest.TestCase):
    def prompt_with_input(self, text):
        with create_pipe_input() as inp:
            inp.send_text(text)
            session = PromptSession(
                multiline=True,
                key_bindings=input_ui.make_bindings(),
                completer=SlashCompleter(),
                input=inp,
                output=DummyOutput(),
            )
            return session.prompt("> ")

    def test_shift_enter_inserts_newline(self):
        result = self.prompt_with_input("primera\x1b\rsegunda\r")
        self.assertEqual(result, "primera\nsegunda")

    def test_ctrl_backspace_deletes_previous_word(self):
        result = self.prompt_with_input("hola mundo\x17x\r")
        self.assertEqual(result, "hola x")

    def test_tab_accepts_selected_slash_completion(self):
        result = self.prompt_with_input("/comp\t\r")
        self.assertEqual(result, "/compact")


if __name__ == "__main__":
    unittest.main()

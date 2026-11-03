import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.keys import Keys

from input_ui import make_bindings


class MarkdownTest(unittest.TestCase):
    def render(self, *pieces):
        md = ui.Markdown()
        buf = io.StringIO()
        with redirect_stdout(buf):
            for piece in pieces:
                md.feed(piece)
            md.flush()
        return buf.getvalue()

    def test_bold_and_code(self):
        self.assertEqual(self.render("Hola **mundo** y `x`\n"), "Hola mundo y x\n")

    def test_heading(self):
        self.assertEqual(self.render("## Título\n"), "Título\n")

    def test_fence_keeps_content(self):
        out = self.render("```python\n**no** tocar\n```\n**sí**\n")
        self.assertIn("**no** tocar", out)
        self.assertIn("sí", out)
        self.assertNotIn("**sí**", out)

    def test_split_chunk_renders_whole_line(self):
        self.assertEqual(self.render("Ho", "la **mun", "do**\n"), "Hola mundo\n")

    def test_partial_line_flushed(self):
        self.assertEqual(self.render("sin salto"), "sin salto\n")

    def test_directives_hidden_and_write_body_streamed(self):
        out = self.render(
            "Hola\n@read a.txt\n@write a.txt\nsecreto\n@endwrite\nAdiós\n"
        )
        self.assertIn("Hola", out)
        self.assertIn("Adiós", out)
        self.assertIn("writing a.txt", out)
        self.assertIn("secreto", out)
        self.assertNotIn("@read", out)
        self.assertNotIn("@write", out)


class BindingTest(unittest.TestCase):
    def test_ctrl_backspace_kills_word(self):
        binding = next(
            b for b in make_bindings().bindings if b.keys == (Keys.ControlW,)
        )
        buffer = Buffer(document=Document("hola mundo cruel", 16))
        output = type("O", (), {"bell": lambda self: None})()
        clipboard = type("C", (), {"set_text": lambda self, text: None})()
        app = type("A", (), {"output": output, "clipboard": clipboard})()
        event = type(
            "E",
            (),
            {"current_buffer": buffer, "arg": 1, "app": app, "is_repeat": False},
        )()
        binding.handler(event)
        self.assertEqual(buffer.text, "hola mundo ")


if __name__ == "__main__":
    unittest.main()

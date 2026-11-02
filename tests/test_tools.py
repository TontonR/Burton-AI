import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import store
from tools import Directive, Tools, parse_directives


class ParseTest(unittest.TestCase):
    def test_read_and_bullets(self):
        directives = parse_directives("- @read src/a.py\n* @ls src\n")
        self.assertEqual(
            [(d.name, d.arg) for d in directives],
            [("read", "src/a.py"), ("ls", "src")],
        )

    def test_write_body_and_inner_directive(self):
        text = "@write a.py\n```python\nprint('hola')\n@read falso\n```\n@done\n"
        directives = parse_directives(text)
        self.assertEqual(directives[0].name, "write")
        self.assertIn("@read falso", directives[0].body)
        self.assertEqual(directives[1].name, "done")

    def test_write_without_body(self):
        self.assertIsNone(parse_directives("@write a.py")[0].body)

    def test_write_endwrite_with_nested_fences(self):
        text = "@write a.md\n# T\n```py\nx\n```\n@endwrite\n@done\n"
        directives = parse_directives(text)
        self.assertEqual(directives[0].body, "# T\n```py\nx\n```")
        self.assertEqual(directives[1].name, "done")

    def test_write_endwrite_strips_outer_fence(self):
        text = "@write a.py\n```python\nx = 1\n```\n@endwrite\n"
        self.assertEqual(parse_directives(text)[0].body, "x = 1")

    def test_write_body_with_nested_fences(self):
        text = (
            "@write README.md\n"
            "```markdown\n"
            "# Título\n\n"
            "```python\nprint(1)\n```\n\n"
            "Fin.\n"
            "```\n"
            "@done\n"
        )
        directives = parse_directives(text)
        self.assertEqual(
            directives[0].body,
            "# Título\n\n```python\nprint(1)\n```\n\nFin.",
        )
        self.assertEqual(directives[1].name, "done")

    def test_fenced_block_ignored(self):
        directives = parse_directives("```\n@run rm -rf /\n```\n@done")
        self.assertEqual([d.name for d in directives], ["done"])


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_backups = store.BACKUPS_DIR
        store.BACKUPS_DIR = self.root / ".backups"
        self.tools = Tools(self.root)

    def tearDown(self):
        store.BACKUPS_DIR = self.old_backups
        self.tmp.cleanup()

    def write(self, name, body):
        return self.tools.execute(Directive("write", name, body))

    def test_write_and_read(self):
        out = self.write("sub/a.txt", "uno\ndos")
        self.assertIn("escrito sub/a.txt", out)
        read = self.tools.execute(Directive("read", "sub/a.txt"))
        self.assertIn("1| uno", read)
        self.assertIn("2| dos", read)

    def test_read_range(self):
        self.write("a.txt", "\n".join(str(i) for i in range(1, 301)))
        out = self.tools.execute(Directive("read", "a.txt 100-120"))
        self.assertIn("100| 100", out)
        self.assertIn("120| 120", out)
        self.assertNotIn("121|", out)

    def test_read_bracketed_range(self):
        self.write("a.txt", "\n".join(str(i) for i in range(1, 21)))
        out = self.tools.execute(Directive("read", "a.txt [5-7]"))
        self.assertIn("5| 5", out)
        self.assertIn("7| 7", out)
        self.assertNotIn("8|", out)

    def test_self_edit_blocked(self):
        app = Tools(Path(__file__).resolve().parent.parent)
        out = app.execute(Directive("write", "agent.py", "x"))
        self.assertIn("código de burton_ai", out)

    def test_sandbox_rejects_outside(self):
        out = self.tools.execute(Directive("read", "../secreto.txt"))
        self.assertTrue(out.startswith("ERROR: ruta fuera"))

    def test_plan_blocks_write_and_run(self):
        self.tools.plan = True
        self.assertIn("modo plan", self.write("a.txt", "x"))
        self.assertIn("modo plan", self.tools.execute(Directive("run", "echo hola")))

    def test_empty_write(self):
        self.assertTrue(self.write("a.txt", "  ").startswith("ERROR"))

    def test_same_content_is_noop(self):
        self.write("a.txt", "uno")
        self.assertIn("sin cambios", self.write("a.txt", "uno"))

    def test_unknown_directive(self):
        out = self.tools.execute(Directive("delete", "a.txt"))
        self.assertIn("desconocida", out)

    def test_backup_on_overwrite(self):
        self.write("a.txt", "v1")
        self.write("a.txt", "v2")
        backups = list((self.root / ".backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "v1\n")

    def test_ls(self):
        (self.root / "dir").mkdir()
        (self.root / "dir/one.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.tools.execute(Directive("ls", "dir")), "one.py")

    def test_run_executes(self):
        out = self.tools.execute(Directive("run", "echo hola"))
        self.assertIn("exit 0", out)
        self.assertIn("hola", out)

    def test_run_respects_confirmation(self):
        tools = Tools(self.root, confirm=lambda cmd, reason: False)
        out = tools.execute(Directive("run", "echo hola"))
        self.assertIn("cancelado", out)

    def test_run_passes_task_context_to_permission_prompt(self):
        calls = []
        tools = Tools(
            self.root,
            confirm=lambda cmd, reason: calls.append((cmd, reason)) or False,
        )
        tools.confirm_reason = "comprueba los tests"
        tools.execute(Directive("run", "python -m unittest"))
        self.assertEqual(
            calls, [("python -m unittest", "comprueba los tests")]
        )


if __name__ == "__main__":
    unittest.main()

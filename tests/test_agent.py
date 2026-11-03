import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent
import store


class SubagentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.txt").write_text("uno\ndos\n", encoding="utf-8")
        self.cfg = dict(store.DEFAULTS)
        self.cfg["max_steps"] = 6

    def tearDown(self):
        self.tmp.cleanup()

    def run_fake(self, responses, record=None):
        iterator = iter(responses)

        def fake_chat(model, messages, cfg, on_chunk):
            return next(iterator), {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            return agent.run_subagent(
                "¿qué contiene a.txt?",
                self.cfg,
                self.root,
                log=lambda *a: None,
                record=record,
            )

    def test_reads_and_returns_answer(self):
        out = self.run_fake(["@read a.txt", "Tiene dos líneas.\n@done"])
        self.assertIn("Tiene dos líneas.", out)

    def test_cannot_write(self):
        out = self.run_fake(
            ["@write b.txt\nno\n@endwrite", "No puedo escribir.\n@done"]
        )
        self.assertFalse((self.root / "b.txt").exists())
        self.assertIn("No puedo escribir.", out)

    def test_records_steps(self):
        record = {}
        self.run_fake(["@read a.txt", "Tiene dos líneas.\n@done"], record=record)
        self.assertEqual(record["steps"], ["@read a.txt"])


class WriteIntentTest(unittest.TestCase):
    def test_edit_request_allows_writes(self):
        self.assertTrue(agent.allows_writes("cambia 'adios' por 'hola' en a.txt"))

    def test_creation_requests_allow_writes(self):
        self.assertTrue(
            agent.allows_writes(
                "hazme un 3 en raya en Python que se juegue por terminal"
            )
        )
        self.assertTrue(agent.allows_writes("haz un script que ordene una lista"))
        self.assertTrue(agent.allows_writes("make me a Python game"))

    def test_question_blocks_writes(self):
        self.assertFalse(agent.allows_writes("dime qué contiene a.txt"))

    def test_explicit_negation_blocks_writes(self):
        self.assertFalse(agent.allows_writes("arregla a.txt pero no modifiques otros"))
        self.assertFalse(agent.allows_writes("solo dime qué contiene a.txt"))
        self.assertFalse(agent.allows_writes("no hagas cambios, solo dime qué harías"))

    def test_response_format_negation_does_not_block_requested_edit(self):
        self.assertTrue(
            agent.allows_writes(
                "Corrige BURTON.readme; no escribas el documento como respuesta normal"
            )
        )
        self.assertTrue(
            agent.allows_writes(
                "Actualiza README.md, no devuelvas el contenido como respuesta"
            )
        )

    def test_file_creation_request_is_detected(self):
        self.assertTrue(agent.requests_file_creation("hazme un 3 en raya en Python"))
        self.assertTrue(agent.requests_file_creation("crea el fichero"))
        self.assertTrue(agent.requests_file_creation("create a game in Python"))
        self.assertTrue(agent.requests_file_creation("make me a Python game"))
        self.assertTrue(
            agent.requests_file_creation("la directiva @write debes ejecutarla tú")
        )

    def test_extract_code_file_infers_filename_from_request(self):
        self.assertEqual(
            agent.extract_code_file(
                "hazme un 3 en raya en Python",
                "Aquí está:\n```python\nprint('juego')\n```",
            ),
            ("tres_en_raya.py", "print('juego')", "python"),
        )
        self.assertEqual(
            agent.extract_code_file(
                "hazme un juego sencillo en Python",
                "```python\nprint('listo')\n```",
            )[0],
            "juego_sencillo.py",
        )

    def test_explicit_no_create_request_is_not_detected(self):
        self.assertFalse(
            agent.requests_file_creation(
                "NO CREES EL TRES EN RAYA; ES PARA PONERLA A PRUEBA"
            )
        )
        self.assertFalse(agent.requests_file_creation("Do not create a game"))


class StreamChatTest(unittest.TestCase):
    def test_sends_unlimited_prediction_limit_to_ollama(self):
        response = io.BytesIO(
            b'{"message":{"content":"respuesta"}}\n'
            b'{"done":true,"eval_count":1,"prompt_eval_count":17,"eval_duration":1000000000}\n'
        )
        cfg = dict(store.DEFAULTS)
        cfg["num_predict"] = -1

        with mock.patch.object(agent.urllib.request, "urlopen", return_value=response) as urlopen:
            text, stats = agent.stream_chat("qwen2.5-coder:14b", [], cfg, lambda _: None)

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["options"]["num_predict"], -1)
        self.assertEqual(text, "respuesta")
        self.assertEqual(stats["tokens"], 1)
        self.assertEqual(stats["prompt_tokens"], 17)

    def test_cancelled_stream_handles_closed_response_iterator(self):
        class ClosedResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def __iter__(self):
                raise AttributeError("'NoneType' object has no attribute 'peek'")

            def close(self):
                return None

        cancel_event = threading.Event()
        cancel_event.set()
        with mock.patch.object(
            agent.urllib.request, "urlopen", return_value=ClosedResponse()
        ):
            text, stats = agent.stream_chat(
                "model", [], dict(store.DEFAULTS), lambda _piece: None, cancel_event
            )

        self.assertEqual(text, "")
        self.assertEqual(stats["tokens"], 0)


class TurnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.txt").write_text("uno\n", encoding="utf-8")
        self.cfg = dict(store.DEFAULTS)
        self.cfg["max_steps"] = 6
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_turn(self, responses):
        iterator = iter(responses)

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(iterator)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        session = {"messages": [{"role": "user", "content": "lee a.txt"}]}
        tools = agent.Tools(self.root, confirm=lambda cmd, reason: False)
        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda piece: None, log=self.logs.append
            )
        return outcome, session

    def test_repeated_directive_requests_recovery(self):
        outcome, session = self.run_turn(["@read a.txt", "@read a.txt", "@done"])
        self.assertEqual(outcome, "done")
        self.assertTrue(
            any(
                "Do not repeat the directive" in message["content"]
                for message in session["messages"]
            )
        )

    def test_skills_directive_activates_skill_for_next_step(self):
        prompts = []
        responses = iter(["@skills git", "@done"])

        def fake_chat(model, messages, cfg, on_chunk):
            prompts.append(messages[0]["content"])
            return next(responses), {"tokens": 1, "seconds": 0.1}

        session = {"messages": [{"role": "user", "content": "prepara el repo"}]}
        tools = agent.Tools(self.root, confirm=lambda cmd, reason: False)
        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(len(prompts), 2)
        self.assertIn("@skills <id,id>", prompts[0])
        self.assertIn("- git:", prompts[0])
        self.assertIn("Never run `git reset --hard`", prompts[1])
        self.assertNotIn("skills", self.cfg)

    def test_text_reply_ends_turn(self):
        outcome, _ = self.run_turn(["Tiene una línea."])
        self.assertEqual(outcome, "text")

    def test_cancelled_turn_does_not_call_model(self):
        session = {"messages": [{"role": "user", "content": "haz una tarea"}]}
        tools = agent.Tools(self.root, confirm=lambda cmd, reason: False)
        cancel_event = threading.Event()
        cancel_event.set()

        with mock.patch.object(agent, "stream_chat") as stream_chat:
            outcome = agent.run_turn(
                session,
                self.cfg,
                tools,
                lambda piece: None,
                log=self.logs.append,
                cancel_event=cancel_event,
            )

        self.assertEqual(outcome, "cancelled")
        stream_chat.assert_not_called()

    def test_context_usage_is_reported_from_ollama(self):
        def fake_chat(model, messages, cfg, on_chunk):
            return "respuesta", {
                "tokens": 1,
                "prompt_tokens": 4000,
                "seconds": 0.1,
            }

        session = {"messages": [{"role": "user", "content": "hola"}]}
        tools = agent.Tools(self.root, confirm=lambda cmd, reason: False)
        with mock.patch.object(agent, "stream_chat", fake_chat):
            agent.run_turn(
                session, self.cfg, tools, lambda piece: None, log=self.logs.append
            )
        self.assertIn("Context: 4,000/16,384 tokens (24.4%", self.logs[-1])
        self.assertEqual(session["last_context_tokens"], 4000)

    def test_duplicate_directive_is_not_executed_twice(self):
        outcome, _ = self.run_turn(["@read a.txt", "@read a.txt", "@done"])
        self.assertEqual(outcome, "done")
        self.assertEqual(
            sum("-> @read a.txt" in entry for entry in self.logs), 1
        )
        self.assertFalse(any("loop stopped" in entry for entry in self.logs))

    def test_repeated_directive_loop_logs_only_one_concise_warning(self):
        outcome, _ = self.run_turn(
            ["@read a.txt", "@read a.txt", "@read a.txt", "@done"]
        )
        warnings = [entry for entry in self.logs if "loop stopped" in entry]

        self.assertEqual(outcome, "loop")
        self.assertEqual(len(warnings), 1)
        self.assertIn("@read a.txt", warnings[0])
        self.assertFalse(any("ya se ejecutó esa directiva" in entry for entry in self.logs))
        self.assertFalse(any("el modelo sigue repitiéndola" in entry for entry in self.logs))

    def test_hazme_request_writes_requested_file(self):
        session = {
            "messages": [
                {
                    "role": "user",
                    "content": "hazme un juego sencillo en Python para terminal",
                }
            ]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "@write juego.py\nprint('listo')\n@endwrite",
            "@done",
            "@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(
            (self.root / "juego.py").read_text(encoding="utf-8"),
            "print('listo')\n",
        )

    def test_file_creation_directive_does_not_trigger_false_retry_after_write(self):
        session = {
            "messages": [
                {"role": "user", "content": "hazme un juego sencillo en Python"}
            ]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "@write juego.py\nprint('listo')\n@endwrite",
            "El archivo ya está creado.",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "text")
        self.assertTrue((self.root / "juego.py").exists())
        self.assertFalse(
            any("You have not modified any file yet" in item["content"]
                for item in session["messages"] if item["role"] == "user")
        )
        self.assertFalse(any("file was not created" in item for item in self.logs))

    def test_file_creation_code_block_is_saved_and_streamed(self):
        session = {
            "messages": [
                {"role": "user", "content": "hazme un juego sencillo en Python"}
            ]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "Aquí tienes el código:\n```python\nprint('listo')\n```",
            "@done",
            "@done",
        ])
        shown = []

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, shown.append, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(
            (self.root / "juego_sencillo.py").read_text(encoding="utf-8"),
            "print('listo')\n",
        )
        self.assertTrue(shown)
        self.assertTrue(any("wrote juego_sencillo.py" in entry for entry in self.logs))

    def test_file_creation_retry_saves_code_block_after_empty_block(self):
        session = {
            "messages": [
                {"role": "user", "content": "hazme un juego sencillo en Python"}
            ]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "Aquí tienes el código:\n```python\n\n```\nPuedo guardarlo.",
            "Código:\n```python\nprint('listo')\n```",
            "@done",
            "@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(
            (self.root / "juego_sencillo.py").read_text(encoding="utf-8"),
            "print('listo')\n",
        )
        self.assertTrue(any("wrote juego_sencillo.py" in entry for entry in self.logs))

    def test_auto_syntax_check_after_python_write(self):
        session = {
            "messages": [{"role": "user", "content": "hazme un juego en Python"}]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "@write juego.py\nprint('listo')\n@endwrite",
            "@done",
            "@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertTrue(any("syntax ok" in entry for entry in self.logs))
        self.assertTrue(
            any(
                "Auto syntax check" in item["content"]
                for item in session["messages"]
                if item["role"] == "user"
            )
        )

    def test_done_asks_for_one_self_review_after_python_write(self):
        session = {
            "messages": [{"role": "user", "content": "hazme un juego en Python"}]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        seen = []
        responses = iter([
            "@write juego.py\nprint('listo')\n@endwrite",
            "@done",
            "@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            seen.append([item["content"] for item in messages])
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(len(seen), 3)
        self.assertTrue(any("Before you finish, review your work" in text for text in seen[2]))
        self.assertTrue(any("self-review before done" in entry for entry in self.logs))

    def test_model_run_after_write_skips_the_review_nudge(self):
        session = {
            "messages": [{"role": "user", "content": "hazme un juego en Python"}]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        responses = iter([
            "@write juego.py\nprint('listo')\n@endwrite",
            "@run python juego.py",
            "@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertFalse(any("self-review before done" in entry for entry in self.logs))

    def test_code_fallback_does_not_overwrite_existing_file(self):
        (self.root / "juego.py").write_text("original\n", encoding="utf-8")
        extracted = agent.write_code_file(
            "hazme un juego en Python",
            "```python\nprint('nuevo')\n```",
            agent.Tools(self.root),
        )

        self.assertIsNone(extracted)
        self.assertEqual(
            (self.root / "juego.py").read_text(encoding="utf-8"), "original\n"
        )

    def test_no_create_request_never_retries_or_writes(self):
        session = {
            "messages": [
                {
                    "role": "user",
                    "content": "NO CREES EL TRES EN RAYA; ES PARA PONERLA A PRUEBA",
                }
            ]
        }
        tools = agent.Tools(self.root, confirm=lambda _cmd, _reason: False)
        calls = []

        def fake_chat(model, messages, cfg, on_chunk):
            calls.append(messages)
            text = "Entendido, no crearé el juego."
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "text")
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.root / "juego.py").exists())

    def test_run_permission_uses_model_explanation(self):
        session = {
            "messages": [{"role": "user", "content": "comprueba el script"}]
        }
        permission_requests = []
        tools = agent.Tools(
            self.root,
            confirm=lambda command, reason: (
                permission_requests.append((command, reason)) or False
            ),
        )
        responses = iter([
            "Voy a ejecutar el test para comprobar que el script arranca.\n"
            "@run npm install left-pad",
            "No se ejecutó porque se denegó el permiso.\n@done",
        ])

        def fake_chat(model, messages, cfg, on_chunk):
            text = next(responses)
            on_chunk(text)
            return text, {"tokens": 1, "seconds": 0.1}

        with mock.patch.object(agent, "stream_chat", fake_chat):
            outcome = agent.run_turn(
                session, self.cfg, tools, lambda _piece: None, log=self.logs.append
            )

        self.assertEqual(outcome, "done")
        self.assertEqual(
            permission_requests,
            [
                (
                    "npm install left-pad",
                    "Voy a ejecutar el test para comprobar que el script arranca.",
                )
            ],
        )

    def test_thinking_indicator_stops_before_first_chunk(self):
        indicator = mock.Mock()
        indicator_started_before_chunk = []
        original_run_turn = agent.run_turn

        def fake_chat(model, messages, cfg, on_chunk):
            on_chunk("respuesta")
            return "respuesta", {"tokens": 1, "seconds": 0.1}

        session = {"messages": [{"role": "user", "content": "hola"}]}
        tools = agent.Tools(self.root, confirm=lambda cmd, reason: False)

        def receive(piece):
            indicator_started_before_chunk.append(indicator.stop.called)

        with (
            mock.patch.object(agent.ui, "ThinkingIndicator", return_value=indicator),
            mock.patch.object(agent, "stream_chat", fake_chat),
        ):
            outcome = original_run_turn(
                session, self.cfg, tools, receive, log=self.logs.append
            )

        self.assertEqual(outcome, "text")
        indicator.start.assert_called_once()
        self.assertGreaterEqual(indicator.stop.call_count, 1)
        self.assertEqual(indicator_started_before_chunk, [True])

    def test_subagent_is_saved(self):
        with mock.patch.object(agent, "run_subagent", lambda *a, **k: "resumen"):
            outcome, session = self.run_turn(["@agent mira a.txt", "@done"])
        self.assertEqual(outcome, "done")
        self.assertEqual(session["subagents"][0]["task"], "mira a.txt")
        self.assertEqual(session["subagents"][0]["answer"], "resumen")

    def test_refusal_is_retried(self):
        outcome, session = self.run_turn(
            [
                "Lo siento, no puedo acceder a archivos fuera del directorio.",
                "@read a.txt",
                "uno\n@done",
            ]
        )
        self.assertEqual(outcome, "done")
        self.assertTrue(
            any("You are not outside the project" in m["content"] for m in session["messages"])
        )

    def test_skills_are_loaded(self):
        prompt = agent.build_system_prompt(self.root, self.cfg)
        self.assertIn("Project skills", prompt)
        self.assertIn("Real file access", prompt)
        self.assertIn("one directive", prompt.lower())
        self.assertIn("prompt.md", prompt)

    def test_compact_replaces_history_only_after_summary(self):
        session = {"messages": [{"role": "user", "content": "tarea"}]}
        cfg = dict(self.cfg)
        with mock.patch.object(
            agent,
            "stream_with_indicator",
            return_value=("Objetivo y siguiente paso.", {"prompt_tokens": 20}),
        ) as compact:
            success, summary, stats = agent.compact_session(session, cfg)
        self.assertTrue(success)
        self.assertEqual(summary, "Objetivo y siguiente paso.")
        self.assertEqual(len(session["messages"]), 1)
        self.assertIn("Objetivo y siguiente paso.", session["messages"][0]["content"])
        self.assertEqual(session["last_context_tokens"], 20)
        self.assertEqual(compact.call_args.args[2]["num_predict"], 1200)

    def test_compact_preserves_history_on_empty_summary(self):
        session = {"messages": [{"role": "user", "content": "tarea"}]}
        original = list(session["messages"])
        with mock.patch.object(
            agent, "stream_with_indicator", return_value=("  ", {})
        ):
            success, _, _ = agent.compact_session(session, self.cfg)
        self.assertFalse(success)
        self.assertEqual(session["messages"], original)


if __name__ == "__main__":
    unittest.main()

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

    def test_question_blocks_writes(self):
        self.assertFalse(agent.allows_writes("dime qué contiene a.txt"))

    def test_explicit_negation_blocks_writes(self):
        self.assertFalse(agent.allows_writes("arregla a.txt pero no modifiques otros"))
        self.assertFalse(agent.allows_writes("solo dime qué contiene a.txt"))

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
                "No repitas la directiva" in message["content"]
                for message in session["messages"]
            )
        )

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
        self.assertIn("Contexto: 4,000/16,384 tokens (24.4%", self.logs[-1])
        self.assertEqual(session["last_context_tokens"], 4000)

    def test_duplicate_directive_is_not_executed_twice(self):
        outcome, _ = self.run_turn(["@read a.txt", "@read a.txt", "@done"])
        self.assertEqual(outcome, "done")
        self.assertEqual(
            sum("-> @read a.txt" in entry for entry in self.logs), 1
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
            any("No estás fuera del proyecto" in m["content"] for m in session["messages"])
        )

    def test_skills_are_loaded(self):
        prompt = agent.build_system_prompt(self.root)
        self.assertIn("Leer ficheros", prompt)
        self.assertIn("prompt.md", prompt)
        self.assertIn("no respondas con instrucciones", prompt)
        self.assertIn("Las modificaciones de archivos solo se aplican con @write", prompt)

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

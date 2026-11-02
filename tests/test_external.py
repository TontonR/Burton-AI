import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent
import bridge
import burton
import store


class ExternalWorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.old_control_dir = bridge.CONTROL_DIR
        self.old_sessions_dir = store.SESSIONS_DIR
        bridge.CONTROL_DIR = Path(self.tmp.name) / "control"
        store.SESSIONS_DIR = Path(self.tmp.name) / "sessions"

    def tearDown(self):
        bridge.CONTROL_DIR = self.old_control_dir
        store.SESSIONS_DIR = self.old_sessions_dir
        self.tmp.cleanup()

    def test_external_request_starts_once_and_keeps_session(self):
        cfg = dict(store.DEFAULTS)
        args = SimpleNamespace(plan=False, allow_self_edit=False)
        start = mock.Mock(return_value=123)

        with mock.patch.object(burton, "start_worker", start):
            state, error = burton.begin_external(
                self.root, "talk", "hola", args, cfg
            )
            duplicate, duplicate_error = burton.begin_external(
                self.root, "talk", "otro mensaje", args, cfg
            )

        self.assertIsNone(error)
        self.assertEqual(state["status"], "queued")
        self.assertNotIn("pid", state)
        self.assertIsNone(duplicate)
        self.assertIn("ocupado", duplicate_error)
        self.assertEqual(start.call_count, 1)

    def test_worker_persists_response_and_session(self):
        session = store.new_session(store.DEFAULTS["model"])
        store.save_session(session)
        state = {
            "root": str(self.root),
            "request_id": "request-1",
            "operation": "talk",
            "prompt": "responde hola",
            "status": "queued",
            "session_id": session["id"],
            "model": store.DEFAULTS["model"],
            "plan": False,
            "allow_self_edit": False,
            "response": "",
        }
        bridge.write_state(self.root, state)

        def fake_run_turn(session, cfg, tools, on_chunk, log=print, cancel_event=None):
            text = "Hola, agente."
            session["messages"].append({"role": "assistant", "content": text})
            on_chunk(text)
            return "text"

        with (
            mock.patch.object(burton, "ensure_server", return_value=True),
            mock.patch.object(
                burton, "model_names", return_value=[store.DEFAULTS["model"]]
            ),
            mock.patch.object(agent, "run_turn", side_effect=fake_run_turn),
        ):
            result = burton.worker_main(self.root, "request-1")

        finished = bridge.read_state(self.root)
        saved = store.load_session(session["id"])
        self.assertEqual(result, 0)
        self.assertEqual(finished["status"], "complete")
        self.assertEqual(finished["response"], "Hola, agente.")
        self.assertEqual(saved["messages"][-1]["content"], "Hola, agente.")

    def test_new_command_resets_external_conversation_state(self):
        state = bridge.empty_state(self.root)
        state.update({
            "request_id": "old-request",
            "status": "complete",
            "response": "respuesta anterior",
            "plan": True,
        })
        bridge.write_state(self.root, state)
        args = SimpleNamespace(
            talk=None,
            response=False,
            status=False,
            wait=False,
            compact=False,
            stop=False,
            exit=False,
            new=True,
            toggle_plan=False,
            models=None,
            sessions=None,
            subagents=None,
            approve=False,
            deny=False,
            plan=False,
            allow_self_edit=False,
            model=None,
            steps=None,
        )

        with contextlib.redirect_stdout(io.StringIO()):
            result = burton.external_command(args, self.root, dict(store.DEFAULTS))

        updated = bridge.read_state(self.root)
        self.assertEqual(result, 0)
        self.assertEqual(updated["status"], "idle")
        self.assertEqual(updated["response"], "")
        self.assertIsNone(updated.get("request_id"))
        self.assertTrue(updated["plan"])


if __name__ == "__main__":
    unittest.main()

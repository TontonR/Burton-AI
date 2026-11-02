import concurrent.futures
import sys
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bridge


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.old_control_dir = bridge.CONTROL_DIR
        bridge.CONTROL_DIR = Path(self.tmp.name) / "control"

    def tearDown(self):
        bridge.CONTROL_DIR = self.old_control_dir
        self.tmp.cleanup()

    def test_state_round_trips_and_tracks_busy_status(self):
        state = bridge.empty_state(self.root)
        state.update({"request_id": "request-1", "status": "thinking"})
        bridge.write_state(self.root, state)
        paths = bridge.paths_for(self.root)
        paths["heartbeat"].touch()

        payload = bridge.status_payload(self.root)

        self.assertTrue(payload["busy"])
        self.assertTrue(payload["thinking"])
        self.assertEqual(payload["request_id"], "request-1")

    def test_concurrent_state_reads_and_writes_are_serialized(self):
        state = bridge.empty_state(self.root)
        state.update({"request_id": "request-1", "status": "thinking"})
        bridge.write_state(self.root, state)

        def writer(index):
            for value in range(30):
                current = bridge.read_state(self.root)
                current["sequence"] = (index, value)
                bridge.write_state(self.root, current)

        def reader(_index):
            for _ in range(60):
                bridge.read_state(self.root)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [
                pool.submit(writer, index) for index in range(3)
            ] + [
                pool.submit(reader, index) for index in range(3)
            ]
            for future in futures:
                future.result()

    def test_state_lock_serializes_writers_across_processes(self):
        project = Path(__file__).resolve().parent.parent
        script = (
            "import sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "import bridge; "
            "from pathlib import Path; "
            "bridge.CONTROL_DIR = Path(sys.argv[2]); "
            "bridge.write_state(sys.argv[3], {'status': 'child'})"
        )
        lock = bridge.acquire_state_lock(self.root)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(project),
                    str(bridge.CONTROL_DIR),
                    str(self.root),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.2)
            self.assertIsNone(process.poll())
        finally:
            bridge.release_state_lock(self.root, lock)

        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(bridge.read_state(self.root)["status"], "child")

    def test_approval_is_available_only_for_pending_command(self):
        state = bridge.empty_state(self.root)
        state.update({
            "request_id": "request-1",
            "status": "awaiting_approval",
            "approval": {"command": "python -m unittest"},
        })
        bridge.write_state(self.root, state)

        self.assertTrue(bridge.request_approval(self.root, "request-1", True))
        self.assertIs(bridge.consume_approval(self.root, "request-1"), True)
        self.assertIsNone(bridge.consume_approval(self.root, "request-1"))
        self.assertFalse(bridge.request_approval(self.root, "other", True))

    def test_stop_request_is_bound_to_current_request(self):
        state = bridge.empty_state(self.root)
        state.update({"request_id": "request-1", "status": "thinking"})
        bridge.write_state(self.root, state)
        bridge.paths_for(self.root)["heartbeat"].touch()

        self.assertTrue(bridge.request_cancel(self.root))
        self.assertTrue(bridge.cancel_requested(self.root, "request-1"))
        self.assertFalse(bridge.cancel_requested(self.root, "request-2"))

    def test_stale_worker_is_not_reported_as_thinking(self):
        state = bridge.empty_state(self.root)
        state.update({"request_id": "request-1", "status": "thinking"})
        bridge.write_state(self.root, state)
        heartbeat = bridge.paths_for(self.root)["heartbeat"]
        heartbeat.touch()
        old_time = time.time() - 31
        import os

        os.utime(heartbeat, (old_time, old_time))

        payload = bridge.status_payload(self.root)

        self.assertEqual(payload["status"], "stale")
        self.assertFalse(payload["busy"])
        self.assertFalse(payload["thinking"])

    def test_visible_response_hides_agent_directives_and_write_body(self):
        text = (
            "Voy a revisar el archivo.\n"
            "@read src/main.py\n"
            "@write src/main.py\n"
            "contenido privado\n"
            "@endwrite\n"
            "Terminado.\n"
            "@done"
        )

        self.assertEqual(
            bridge.visible_response(text),
            "Voy a revisar el archivo.\nTerminado.",
        )


if __name__ == "__main__":
    unittest.main()

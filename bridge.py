import hashlib
import errno
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import store

if os.name == "nt":
    import msvcrt
else:
    import fcntl

CONTROL_DIR = store.BASE / "control"
ACTIVE_STATUSES = {"queued", "thinking", "awaiting_approval"}
_state_locks_guard = threading.Lock()
_state_locks = {}


def paths_for(root):
    normalized = str(Path(root).expanduser().resolve())
    key = hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()[:24]
    directory = CONTROL_DIR / key
    return {
        "directory": directory,
        "state": directory / "state.json",
        "lock": directory / "submit.lock",
        "cancel": directory / "cancel",
        "approval": directory / "approval.json",
        "heartbeat": directory / "heartbeat",
    }


def empty_state(root):
    return {
        "root": str(Path(root).expanduser().resolve()),
        "status": "idle",
        "session_id": None,
        "response": "",
        "error": None,
        "approval": None,
    }


def acquire_state_lock(root):
    paths = paths_for(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    lock_path = paths["directory"] / "state.lock"
    key = str(paths["directory"]).casefold()
    with _state_locks_guard:
        thread_lock = _state_locks.setdefault(key, threading.Lock())
    deadline = time.monotonic() + 10
    if not thread_lock.acquire(timeout=10):
        raise TimeoutError("Timed out waiting for the local state lock.")
    handle = None
    while True:
        try:
            handle = lock_path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    if os.name == "nt":
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return handle, thread_lock
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Timed out waiting for the state lock."
                        ) from exc
                    time.sleep(0.01)
        except OSError as exc:
            if handle is not None:
                handle.close()
            thread_lock.release()
            raise


def release_state_lock(root, lock):
    handle, thread_lock = lock
    try:
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
        thread_lock.release()


def read_state(root):
    paths = paths_for(root)
    lock = acquire_state_lock(root)
    try:
        try:
            return json.loads(paths["state"].read_text(encoding="utf-8"))
        except FileNotFoundError:
            return empty_state(root)
    finally:
        release_state_lock(root, lock)


def write_state(root, state):
    paths = paths_for(root)
    lock = acquire_state_lock(root)
    temporary = paths["directory"] / f"state.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, paths["state"])
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        release_state_lock(root, lock)


def acquire_submit_lock(root):
    paths = paths_for(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    try:
        return os.open(
            paths["lock"],
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError:
        try:
            if time.time() - paths["lock"].stat().st_mtime > 30:
                paths["lock"].unlink()
                return os.open(
                    paths["lock"],
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
        except FileNotFoundError:
            return acquire_submit_lock(root)
        except OSError:
            pass
        return None


def release_submit_lock(root, descriptor):
    paths = paths_for(root)
    os.close(descriptor)
    try:
        paths["lock"].unlink()
    except FileNotFoundError:
        pass


def busy_state(root, state=None):
    current = state or read_state(root)
    if current.get("status") not in ACTIVE_STATUSES:
        return False
    paths = paths_for(root)
    try:
        return time.time() - paths["heartbeat"].stat().st_mtime <= 30
    except FileNotFoundError:
        return False


def status_payload(root, state=None):
    current = dict(state or read_state(root))
    paths = paths_for(root)
    is_busy = busy_state(root, current)
    if current.get("status") in ACTIVE_STATUSES and not is_busy:
        current["status"] = "stale"
        current["error"] = current.get("error") or "The process is not updating its state."
    current["thinking"] = current.get("status") in {"queued", "thinking"}
    current["busy"] = is_busy
    current["cancel_requested"] = paths["cancel"].exists()
    return current


def request_cancel(root):
    state = read_state(root)
    if not busy_state(root, state):
        return False
    paths = paths_for(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    paths["cancel"].write_text(state.get("request_id", ""), encoding="utf-8")
    return True


def cancel_requested(root, request_id):
    paths = paths_for(root)
    try:
        return paths["cancel"].read_text(encoding="utf-8") == request_id
    except FileNotFoundError:
        return False


def request_approval(root, request_id, allowed):
    state = read_state(root)
    approval = state.get("approval")
    if (
        state.get("request_id") != request_id
        or state.get("status") != "awaiting_approval"
        or not approval
    ):
        return False
    paths = paths_for(root)
    temporary = paths["directory"] / f"approval.{uuid.uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps({"request_id": request_id, "allowed": allowed}),
        encoding="utf-8",
    )
    os.replace(temporary, paths["approval"])
    return True


def consume_approval(root, request_id):
    paths = paths_for(root)
    try:
        decision = json.loads(paths["approval"].read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if decision.get("request_id") != request_id:
        return None
    try:
        paths["approval"].unlink()
    except FileNotFoundError:
        pass
    return bool(decision.get("allowed"))


def visible_response(text):
    text = re.sub(r"\n*@write\b.*?@endwrite\n*", "\n", text, flags=re.DOTALL)
    text = re.sub(r"\n*@write\b.*", "", text, flags=re.DOTALL)
    lines = [
        line for line in text.splitlines() if not line.lstrip().startswith("@")
    ]
    return "\n".join(lines).strip()

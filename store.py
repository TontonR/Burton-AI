import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
SESSIONS_DIR = BASE / "sessions"
BACKUPS_DIR = BASE / "backups"

DEFAULTS = {
    "model": "qwen2.5-coder:14b",
    "num_ctx": 16384,
    "max_steps": 12,
    "temperature": 0,
    "num_predict": -1,
}


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            print("aviso: config.json ilegible, uso valores por defecto")
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def new_session(model):
    now = datetime.now()
    return {
        "id": now.strftime("%Y%m%d-%H%M%S-%f"),
        "title": "",
        "created": now.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "messages": [],
    }


def save_session(session):
    SESSIONS_DIR.mkdir(exist_ok=True)
    (SESSIONS_DIR / f"{session['id']}.json").write_text(
        json.dumps(session, ensure_ascii=False), encoding="utf-8"
    )


def load_session(session_id):
    return json.loads(
        (SESSIONS_DIR / f"{session_id}.json").read_text(encoding="utf-8")
    )


def list_sessions():
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: data.get(k) for k in ("id", "title", "created", "model")})
    return sorted(out, key=lambda s: s["created"] or "", reverse=True)


def backup(path):
    if not path.exists():
        return None
    BACKUPS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = BACKUPS_DIR / f"{path.name}.{stamp}.bak"
    dest.write_bytes(path.read_bytes())
    return dest

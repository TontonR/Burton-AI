"""Skill discovery, activation and prompt budgeting."""

from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
MAX_SKILL_CHARS = 1200
DEFAULT_BUDGET = 7000
CORE = "core"
OPTIONAL = "optional"


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    desc: str
    tier: str
    default: bool
    priority: int
    body: str
    path: Path

    @property
    def locked(self):
        return self.tier == CORE

    @property
    def chars(self):
        return len(self.body)


def _parse(path):
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta = {}
    body = raw
    lines = raw.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() != "---":
                continue
            for line in lines[1:index]:
                key, separator, value = line.partition(":")
                if separator:
                    meta[key.strip().lower()] = value.strip()
            body = "\n".join(lines[index + 1:])
            break
    body = body.strip()
    if not body:
        return None
    tier = meta.get("tier", OPTIONAL).lower()
    if tier not in (CORE, OPTIONAL):
        tier = OPTIONAL
    try:
        priority = int(meta.get("priority", 50))
    except ValueError:
        priority = 50
    return Skill(
        id=meta.get("id") or path.stem,
        name=meta.get("name") or path.stem,
        desc=meta.get("desc", ""),
        tier=tier,
        default=meta.get("default", "false").lower() in {"true", "yes", "1"},
        priority=priority,
        body=body,
        path=path,
    )


def discover():
    if not SKILLS_DIR.is_dir():
        return []
    found = {}
    for path in sorted(SKILLS_DIR.glob("*.md")):
        skill = _parse(path)
        if skill is not None and skill.id not in found:
            found[skill.id] = skill
    return sorted(
        found.values(),
        key=lambda skill: (0 if skill.locked else 1, skill.priority, skill.id),
    )


def _clip(text, limit=MAX_SKILL_CHARS):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if "\n" in cut:
        cut = cut[: cut.rfind("\n")]
    return cut.rstrip() + "\n[skill truncated]"


def _active(skill, cfg):
    if skill.locked:
        return True
    configured = cfg.get("skills")
    if isinstance(configured, list):
        return skill.id in configured
    return skill.default


def _budget(cfg):
    try:
        return max(1000, int(cfg.get("skills_budget") or DEFAULT_BUDGET))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def selection(cfg):
    """Return (skill, text, active, loaded, reason) in prompt order."""
    used = 0
    budget = _budget(cfg)
    rows = []
    for skill in discover():
        text = _clip(skill.body)
        active = _active(skill, cfg)
        loaded = False
        reason = "disabled"
        if active:
            if skill.locked:
                loaded = True
                reason = "core"
            elif used + len(text) <= budget:
                loaded = True
                reason = "enabled"
            else:
                reason = "over budget"
        if loaded:
            if not skill.locked:
                used += len(text)
        rows.append((skill, text, active, loaded, reason))
    return rows


def load_text(cfg):
    return "\n\n".join(
        text for _skill, text, _active_, loaded, _reason in selection(cfg) if loaded
    )


def status(cfg):
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "desc": skill.desc,
            "tier": skill.tier,
            "default": skill.default,
            "chars": len(text),
            "active": active,
            "loaded": loaded,
            "reason": reason,
        }
        for skill, text, active, loaded, reason in selection(cfg)
    ]


def is_active(cfg, skill_id):
    skill = next((item for item in discover() if item.id == skill_id), None)
    return bool(skill and _active(skill, cfg))


def catalog(cfg):
    """Compact id/description list the model can choose from."""
    return "\n".join(
        f"- {skill.id}: {skill.desc}" + (" [active]" if loaded else "")
        for skill, _text, _active_, loaded, _reason in selection(cfg)
        if not skill.locked
    )


def _current_optional(cfg):
    return {skill.id for skill in discover() if not skill.locked and _active(skill, cfg)}


def set_enabled(cfg, skill_id, enabled):
    skill = next((item for item in discover() if item.id == skill_id), None)
    if skill is None:
        raise SkillError(f"unknown skill: {skill_id}")
    if skill.locked:
        if not enabled:
            raise SkillError(f"core skill cannot be disabled: {skill_id}")
        return skill
    current = _current_optional(cfg)
    if enabled:
        current.add(skill.id)
    else:
        current.discard(skill.id)
    cfg["skills"] = sorted(current)
    return skill


def set_only(cfg, ids):
    known = {skill.id: skill for skill in discover()}
    optional = set()
    for skill_id in ids:
        skill = known.get(skill_id)
        if skill is None:
            raise SkillError(f"unknown skill: {skill_id}")
        if skill.locked:
            raise SkillError(f"core skills are always active: {skill_id}")
        optional.add(skill_id)
    cfg["skills"] = sorted(optional)
    return optional

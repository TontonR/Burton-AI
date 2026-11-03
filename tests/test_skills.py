import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skills


class SkillTest(unittest.TestCase):
    def test_catalog_has_core_and_many_optional(self):
        rows = skills.discover()
        self.assertGreaterEqual(len(rows), 30)
        core = [row.id for row in rows if row.locked]
        optional = [row.id for row in rows if not row.locked]
        self.assertIn("core-access", core)
        self.assertGreaterEqual(len(core), 5)
        self.assertGreaterEqual(len(optional), 25)
        self.assertIn("git", optional)
        self.assertIn("spanish", optional)

    def test_core_is_always_loaded(self):
        text = skills.load_text({"skills": []})
        self.assertIn("Real file access", text)
        self.assertIn("Directive discipline", text)
        self.assertNotIn("Commit messages", text)

    def test_default_optional_skills_load(self):
        text = skills.load_text({})
        self.assertIn("Spanish conversation", text)
        self.assertIn("Clean code", text)
        self.assertIn("Self review before done", text)
        self.assertIn("Terminal apps", text)
        self.assertIn("Debugging", text)
        self.assertNotIn("Commit messages", text)

    def test_self_review_and_terminal_skills_are_default(self):
        for skill_id in ("self-review", "terminal-apps", "debugging"):
            self.assertTrue(skills.is_active({}, skill_id), skill_id)

    def test_toggle_updates_config(self):
        cfg = {}
        skills.set_enabled(cfg, "git", True)
        self.assertIn("git", cfg["skills"])
        self.assertIn("Spanish conversation", skills.load_text(cfg))
        skills.set_enabled(cfg, "git", False)
        self.assertNotIn("git", cfg["skills"])

    def test_core_cannot_be_disabled(self):
        with self.assertRaises(skills.SkillError):
            skills.set_enabled({}, "core-access", False)

    def test_enabling_core_is_a_noop(self):
        cfg = {}
        skills.set_enabled(cfg, "core-access", True)
        self.assertNotIn("skills", cfg)

    def test_unknown_skill_is_rejected(self):
        with self.assertRaises(skills.SkillError):
            skills.set_enabled({}, "does-not-exist", True)

    def test_only_replaces_the_optional_set(self):
        cfg = {"skills": ["git", "testing"]}
        skills.set_only(cfg, ["git", "testing"])
        self.assertEqual(cfg["skills"], ["git", "testing"])
        text = skills.load_text(cfg)
        self.assertIn("Real file access", text)
        self.assertIn("Never run `git reset --hard`", text)
        self.assertNotIn("Target Python 3.10+", text)

    def test_budget_skips_optional_but_keeps_core(self):
        cfg = {"skills": ["python", "git"], "skills_budget": 800}
        rows = {row["id"]: row for row in skills.status(cfg)}
        self.assertTrue(rows["core-access"]["loaded"])
        self.assertTrue(rows["python"]["loaded"])
        self.assertFalse(rows["git"]["loaded"])
        self.assertEqual(rows["git"]["reason"], "over budget")

    def test_auto_skill_is_default_and_catalog_lists_optional(self):
        self.assertTrue(skills.is_active({}, "auto-skills"))
        text = skills.catalog({})
        self.assertIn("- git:", text)
        self.assertIn("[active]", text)
        self.assertNotIn("core-access", text)

    def test_skill_text_is_english(self):
        text = skills.load_text({})
        self.assertIn("Always reply to the user in Spanish", text)
        self.assertIn("Think and reason internally in English", text)
        self.assertIn("Write code, identifiers, comments, docstrings", text)
        self.assertNotIn("Habilidades", text)


if __name__ == "__main__":
    unittest.main()

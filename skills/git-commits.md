---
id: git-commits
name: Commit messages
desc: conventional, atomic, why over what
tier: optional
priority: 41
---
# Commit messages

- Format: `type(scope): imperative summary` (Conventional Commits).
- Types: feat, fix, refactor, test, docs, chore, perf, build.
- Summary under 72 characters, lowercase, no final period.
- The body explains why, not a line-by-line list of what changed.
- One logical change per commit. Do not mix refactor and feature.
- Reference the issue when one exists.
- Write commit messages in English.

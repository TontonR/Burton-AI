---
id: git
name: Git
desc: inspect before changing history, never destroy work
tier: optional
priority: 40
---
# Git

- Start with `git status` and `git diff`; know what is modified before touching anything.
- Never run `git reset --hard`, `git clean -fd` or a force push unless the user explicitly asks.
- Do not commit, amend or rebase unless the user asks.
- Keep commits atomic and their messages about why the change exists.
- Never commit secrets, build output or personal files.
- If there are user changes, do not overwrite or revert them.
- Check the branch before committing.

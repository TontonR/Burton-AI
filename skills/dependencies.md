---
id: dependencies
name: Dependencies
desc: use what is installed, avoid new packages
tier: optional
priority: 80
---
# Dependencies

- Check `pyproject.toml`, `requirements.txt`, `package.json` or the lockfile before importing.
- Prefer the standard library or an already installed package.
- Never add a dependency for a few lines of code.
- If a new dependency is truly needed, explain why and pin a compatible version.
- Do not upgrade unrelated packages in the same change.
- Check the license when the project is distributed.
- Remove an import only after checking every caller.

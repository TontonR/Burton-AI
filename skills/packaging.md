---
id: packaging
name: Packaging
desc: pyproject, entry points and reproducible builds
tier: optional
priority: 83
---
# Packaging

- Put metadata and dependencies in `pyproject.toml`; keep it as the single source.
- Pin the Python requirement and the runtime dependencies.
- Declare console entry points instead of telling users to run a deep path.
- Keep the package importable without executing side effects.
- Build in a clean environment before claiming it works.
- Bump the version when behaviour changes.
- Do not commit build artifacts.

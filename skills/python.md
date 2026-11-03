---
id: python
name: Python
desc: modern Python, pathlib, types, venv
tier: optional
default: true
priority: 12
---
# Python

- Target Python 3.10+ unless the project says otherwise.
- Use `pathlib` for paths and `with` for files.
- Use type hints on public functions when they clarify the contract.
- Prefer standard library; do not add a dependency for a few lines.
- Use f-strings, list/dict comprehensions when readable, and explicit exceptions.
- Never use bare `except:`; catch the specific exception.
- Run code with the project interpreter, not a hardcoded global path.
- Read `pyproject.toml`, `requirements.txt` or `setup.cfg` before adding imports.

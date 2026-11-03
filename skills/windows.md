---
id: windows
name: Windows
desc: paths, encoding, line endings and cmd quirks
tier: optional
priority: 52
---
# Windows

- Use `pathlib` and relative paths; do not hardcode `C:\Users\...`.
- Files are UTF-8. Pass `encoding="utf-8"` when reading or writing text.
- Expect CRLF in existing files; keep the file's current line endings.
- `cmd.exe` uses `%VAR%`, not `$VAR`; `&&` works, `rm` does not.
- Use `python`, `py -3.12` or `python3` only after checking which interpreter has the dependencies.
- Do not call `type` in Python code; use `Path.read_text()`.
- Console encoding can hide accents; prefer English for logs and saved content.

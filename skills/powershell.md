---
id: powershell
name: PowerShell
desc: Windows shell quoting, paths and safe commands
tier: optional
priority: 50
---
# PowerShell

- The default shell on Windows is `cmd.exe` for `@run`; use commands that work there.
- Quote paths with spaces: `"C:\My Folder\file.py"`, not bare words.
- Prefer `python -m ...` over relying on a script being on PATH.
- Use `Get-Content`, `Get-ChildItem` and `Test-Path` only if the command runs in PowerShell.
- Never use `Remove-Item -Recurse -Force` on an unresolved path.
- Check `$LASTEXITCODE` when chaining native commands.
- Do not assume bash syntax (`&&`, `$VAR`, `rm`) in `cmd.exe`.

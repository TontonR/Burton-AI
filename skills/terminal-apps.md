---
id: terminal-apps
name: Terminal apps
desc: menus, input validation and loops that can always exit
tier: optional
default: true
priority: 16
---
# Terminal apps

- Use one clear entry point: show the menu, read a choice, act, then return to the menu until the user exits.
- Every menu has a visible exit option and a loop that really breaks on it. A game loop must draw the state each turn and stop on a condition or a key.
- Validate input: wrap `int(input(...))` in `try/except ValueError`, reject sizes outside a sensible range, and print a short message instead of crashing.
- Clear the screen only if the terminal supports it; keep output readable when clearing fails.
- Separate the logic (board, rules, state) from input/output so the rules can be tested without a keyboard.
- Never require interaction to start: ask for width/height/customization from the menu, not before it, unless the request says otherwise.
- `@run` has no stdin. Smoke-test with a non-interactive path (compile, import, or piped input) and say that the interactive part needs the user.
- Check real behaviour at 1x1, very small and very large sizes; draw characters that exist on Windows terminals.

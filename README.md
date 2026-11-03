# burton_ai

A minimal local coding agent on top of Ollama. It only needs Python 3.12+ and `prompt_toolkit` for the interactive console.

The model replies with text directives; the program executes them and feeds the real result back until the model writes `@done`. No tool-call JSON, no huge prompt.

## Install

```powershell
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
```

Ollama must be running (Burton starts it if needed). If Ollama is missing: `winget install Ollama.Ollama`.

## Usage

```powershell
# from the folder you want to work on
burton

# explicit root and model
python C:\path\to\burton_ai\burton.py --root C:\other\project --model qwen2.5-coder:7b

# automation from scripts or other agents
burton --talk "Review the tests and fix the failure"
burton --status
burton --response
burton --wait
burton --stop
```

The project root is the directory you launch from, or `--root`. It is not persisted between runs.

## Skills

Skills are small Markdown files in `skills/`. The catalog ships with 6 core skills and 36 optional ones. Each one has a header:

```markdown
---
id: python
name: Python
desc: modern Python, pathlib, types, venv
tier: optional
default: true
priority: 12
---
# Python
- ...
```

- `tier: core` skills are **always loaded** and cannot be disabled. They contain file access, directive discipline, safe editing, verification, style and safety.
- `tier: optional` skills can be enabled or disabled.
- `default: true` optional skills load out of the box.
- `priority` controls prompt order.
- Each skill is capped at 1200 characters. Optional skills share a 7000-character budget (`skills_budget`); if the budget is full, lower-priority skills are skipped and `/skills` marks them as `over budget`.

The default active set is: `auto-skills`, `explore`, `clean-code`, `python`, `testing`, `spanish`, `self-review`, `terminal-apps`, `debugging`.

`auto-skills` lets the model choose optional skills itself. The system prompt lists every optional skill with its id and description; the model sends `@skills id,id` before a task and those skills are loaded for the rest of that turn. Changes are per turn and are not written to `config.json`.

`spanish` makes Burton reply to you in Spanish while it thinks, writes code, comments, filenames, commits and saved files in English. Disable it to let the model answer in the user's language.

Commands:

```text
/skills                     list all skills and their state
/skills on <id>             enable one or more ids
/skills off <id>            disable one (core skills refuse)
/skills only <id,id>        enable only these optional skills
/skills                     with a TTY, opens a checkbox menu
```

Skill changes apply on the next turn; no restart. The external interface has `--skills` to list skills, `--skills default` to restore the defaults, `--skills on:ID` / `--skills off:ID` to toggle, and `--skills ID,ID` to keep only those optional skills.

## Console

- Typing `/` shows command autocomplete.
- `Enter` sends. `Ctrl+J` inserts a new line.
- A spinner shows while the model thinks and while a command runs, with elapsed time.
- `@write` streams the whole file body as it is generated, so edits appear live.
- `Ctrl+Backspace` deletes the previous word. `Ctrl+S` opens the subagent menu.
- Responses render basic markdown: bold, inline code, headings and fenced code.
- Persistent line history with the arrow keys.

### Windows Terminal shortcuts

Windows Terminal sends `Shift+Enter` as `Enter` and may send `Ctrl+Backspace` as `^W`. Add these ids inside `actions` and their keys inside `keybindings` in `settings.json`:

```json
// actions
{
    "command": { "action": "sendInput", "input": "\u001b\r" },
    "id": "User.sendInput.ShiftEnter"
},
{
    "command": { "action": "sendInput", "input": "\u0017" },
    "id": "User.sendInput.CtrlBackspace"
}

// keybindings
{ "id": "User.sendInput.ShiftEnter", "keys": "shift+enter" },
{ "id": "User.sendInput.CtrlBackspace", "keys": "ctrl+backspace" }
```

`\u001b\r` is Alt+Enter (new line) and `\u0017` is Ctrl+W (delete word). Open a new tab after saving.

## Directives

```text
@ls <path>
@read <path> [start-end]
@write <path>
full file content
@endwrite
@run <command>
@agent <task>
@skills <id,id>
@done
```

- `@read` returns at most 200 lines; use a range for more.
- Only the **first** directive of each response is executed, so the model sees its result before continuing.
- `@write` replaces the whole file. The body is raw text between `@write` and `@endwrite`, without code fences, so it can contain its own Markdown fences. A backup is saved in `backups/` before overwriting.
- `@run` runs without asking when the command stays inside the project and is not an installer or system change. Burton asks first for `pip`/`npm`/`winget`/`docker`/network commands, destructive commands and anything touching paths outside the project. The command has a 120 s timeout and no stdin, so interactive programs fail fast instead of hanging.
- After every successful `@write` of a `.py` file, Burton automatically runs `python -m py_compile` and feeds the result back to the model.
- Before `@done`, if a `.py` file was written and the model never ran anything, Burton asks for one self-review pass: re-read the request, check requirements, trace the behaviour and verify or fix it.
- For explicit file-creation requests, generation is hidden. If the model returns a code block instead of `@write`, Burton can save it to a new file with an inferred name; it never overwrites an existing file this way.
- `@agent` starts a read-only subagent with its own context. It can `@ls` and `@read`, not write or run. The parent receives a summary. Each subagent is saved in the session and can be reviewed with `/subagents` or `Ctrl+S`.
- `@skills` loads optional skills for the rest of the current turn. It is only listed when the `auto-skills` skill is active. Unknown ids return an error and core ids are ignored.
- Paths are always resolved inside the project root.
- `burton_ai`'s own `.py` files are protected unless you pass `--allow-self-edit`.
- If the model repeats a directive, Burton reminds it of the previous result and asks for a different step; a second repetition stops the loop.

## Context

Every request includes:

- the project tree (up to 80 entries, 3 levels),
- the first 2000 characters of `AGENTS.md`,
- the active skills, within the per-skill and total budget,
- when `auto-skills` is active, the id and description of every optional skill, so the model can choose.

Everything else is requested with `@read`, so the prompt stays small. After each response Burton prints the real input token count reported by Ollama and the percentage of `num_ctx`.

## Commands

| Command | What it does |
|---|---|
| `/new` | New conversation |
| `/clear` | Alias of `/new` (also `clear`) |
| `/plan` | Toggle read-only mode: blocks `@write` and `@run` |
| `/models` | List and switch model without restarting |
| `/sessions` | List sessions; `/sessions N` loads one |
| `/skills` | List skills; `/skills on\|off\|only <id>` toggles them |
| `/subagents` | List session subagents; `/subagents N` opens one |
| `/compact` | Summarise history into working memory |
| `/help` | Help |
| `/exit` | Quit |

## External interface

Each operation is a separate invocation with the same `--root`:

```powershell
burton --root C:\project --talk "Fix the failing test"
burton --root C:\project --status
burton --root C:\project --response
burton --root C:\project --wait --timeout 120
```

- `--talk TEXT` starts a background turn and returns JSON with its id.
- `--status` returns JSON state, pending approval and whether it is thinking.
- `--response` returns the text available so far.
- `--wait` waits for the final response.
- `--stop` cancels the active turn.
- `--compact` compacts the external conversation.
- `--approve` / `--deny` resolves a pending `@run`.
- `--new`, `--toggle-plan`, `--models [NAME]`, `--sessions [ID|N]`, `--skills [default|on:ID|off:ID|ID,ID]`, `--subagents [N]`.

Burton never runs a model-requested command without approval. Review the command and its reason before `--approve`.

## Local state

- `config.json`: model, `num_ctx`, `max_steps`, `temperature`, `num_predict`, `skills_budget`, and the selected optional skills.
- `skills/`: skill files.
- `sessions/`: JSON history, saved after every turn.
- `backups/`: copies before overwriting.
- `history`: console line history.
- `control/`: state of external workers.

Do not publish these files: they can contain project data and conversation history.

## Configuration

```json
{
  "model": "qwen2.5-coder:7b",
  "num_ctx": 16384,
  "max_steps": 12,
  "temperature": 0,
  "num_predict": -1,
  "skills_budget": 7000
}
```

`qwen2.5-coder:7b` is the recommended default: it is much faster than 14B and good enough for this loop. On 8 GB of VRAM, 14B may spill into RAM and slow down. A larger `num_ctx` also uses more memory; lower it if Ollama reports memory errors.

## Tests

```powershell
python -m unittest discover -s tests -v
```

They cover directive parsing, path sandboxing, plan mode, backups, autocomplete, markdown rendering, `Ctrl+Backspace`, subagents, skills and the external worker.

---
id: ollama
name: Ollama
desc: local models, context limits and deterministic settings
tier: optional
priority: 85
---
# Ollama

- The server is at `http://127.0.0.1:11434`; check `/api/tags` before using a model.
- A 7B model is much faster than a 14B model; use the smaller one for iteration.
- `num_ctx` is a hard limit: keep prompts and history below it.
- `temperature: 0` is best for code and tool directives.
- `num_predict: -1` means no output limit; set a cap for background work.
- `keep_alive` keeps the model loaded between turns.
- Do not assume tool calling or vision: this agent uses text directives.
- If a model refuses a valid file access, retry with the real root and a concrete directive.

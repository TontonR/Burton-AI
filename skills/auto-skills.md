---
id: auto-skills
name: Automatic skill selection
desc: pick the optional skills the task needs with @skills
tier: optional
default: true
priority: 6
---
# Automatic skill selection

- Check the "Optional skills" catalog in the system prompt before acting.
- If the task needs a skill that is not `[active]`, your FIRST response must be `@skills id,id` and nothing else.
- Wait for the result, then do the task. The new skills apply from the next response.
- Choose 1-3 focused skills, not everything. Core skills are already active and need no request.
- Use exact ids from the catalog. Example: a Dockerfile → `@skills docker`; a SQL migration → `@skills sql`.
- Skip `@skills` for greetings, short answers, one-file reads, and tasks already covered by the active skills.

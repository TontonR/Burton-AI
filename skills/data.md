---
id: data
name: Data formats
desc: JSON, YAML and CSV without corrupting values
tier: optional
priority: 61
---
# Data formats

- Parse JSON with `json.loads`; never build it by string concatenation.
- Use UTF-8 explicitly and `ensure_ascii=False` when the file should stay readable.
- Validate the shape before using it: required keys, types, empty lists.
- For YAML, preserve indentation and do not rewrite unrelated keys.
- For CSV, use the `csv` module and quote fields with commas or newlines.
- Round-trip a small sample before rewriting a whole data file.
- Keep a backup before overwriting data the user cares about.

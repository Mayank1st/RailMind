## Backend conventions

When writing or editing backend Python, **always** follow the conventions in
`.claude/skills/railmind-conventions` — before every change and before committing.
Apply them to all functions, DTOs, services, models, routers, and enums.

Enforcement: a `PostToolUse` hook in `.claude/settings.json` runs
`scripts/check_naming_conventions.py` on every edited `.py` file and blocks
non-compliant changes. This applies in every session — local and cloud — because
`.claude/`, the skill, and the checker are committed to the repo.
## Backend conventions

When writing or editing backend Python, **always** follow the conventions in
`.claude/skills/railmind-conventions` — before every change and before committing.
Apply them to all functions, DTOs, services, models, routers, and enums.

Enforcement: a `PostToolUse` hook in `.claude/settings.json` runs
`scripts/check_naming_conventions.py` on every edited `.py` file and blocks
non-compliant changes. This applies in every session — local and cloud — because
`.claude/`, the skill, and the checker are committed to the repo.

## Feature delivery

A feature is not done when the code runs. Whenever a feature is finished, or
before anything is pushed to dev or prod, read **§11 Feature delivery checklist**
in `.claude/skills/railmind-conventions` and deliver all three, in order:

1. **Test curls** in the chat — real values, failure cases included, each with
   its expected result, and an honest note on what was actually run.
2. **A Claude Design UI prompt** in the chat — self-contained, carrying the real
   payload and every state the screen must handle.
3. **`docs/<feature>-frontend.md`** — the FE integration doc, committed with the
   feature.

The naming hook cannot catch a missing deliverable, so this one is on you: run
the checklist even when the feature looks too small to need it.
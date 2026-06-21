# `.claude/` — Claude Code project setup

This folder makes the **RailMind backend conventions** travel with the repo and get
followed automatically in every Claude Code session — local, cloud, scheduled, or a
teammate's checkout. This README explains **what each piece is, where it lives, and how to
activate / extend it.**

---

## 1. What's here (file map)

```
RailMind/
├── CLAUDE.md                                  # auto-loaded into EVERY session (the entrypoint)
├── scripts/
│   └── check_naming_conventions.py            # the checker the hook runs
└── .claude/
    ├── README.md                              # this file
    ├── settings.json                          # the enforcement hook (+ permissions)
    └── skills/
        └── railmind-conventions/
            └── SKILL.md                        # the convention rules (the "skill")
```

Three moving parts:

| File | Role | Auto-loaded? |
|---|---|---|
| `CLAUDE.md` | Project instructions; **points at the skill**. | ✅ every session |
| `.claude/skills/railmind-conventions/SKILL.md` | The actual convention rules. | Available as a skill; applied when relevant |
| `.claude/settings.json` | `PostToolUse` hook that **hard-blocks** naming violations. | ✅ new sessions (see activation) |
| `scripts/check_naming_conventions.py` | Script the hook executes. | Run by the hook |

> ⚠️ **Cloud rule:** only files **committed to the repo** travel to cloud sessions.
> Your personal `~/.claude/` memory does **not**. So everything above must be committed
> (and merged into `develop`/`main`) for it to apply everywhere.

---

## 2. The skill — how to save / add one

A skill is a folder under `.claude/skills/` containing a `SKILL.md`.

**Position & naming (must match):**
```
.claude/skills/<skill-name>/SKILL.md
```
- The folder name **is** the skill name (kebab-case): `railmind-conventions`.
- `SKILL.md` must start with YAML frontmatter:

```markdown
---
name: railmind-conventions          # MUST equal the folder name
description: One-line summary of what it covers and WHEN to use it. Claude reads
  this to decide relevance — be specific (e.g. "...use whenever editing backend Python").
---

# Rules go here as plain markdown...
```

**To add a new skill:** create `.claude/skills/<new-name>/SKILL.md` with that frontmatter,
write the rules, then commit. To **edit** the existing one, just edit
`.claude/skills/railmind-conventions/SKILL.md`.

**To make a skill actually get followed** (not just exist), reference it from `CLAUDE.md`
— that file is auto-loaded into every session. Ours already does:
```
When writing or editing backend Python, always follow the conventions in
`.claude/skills/railmind-conventions` ...
```

---

## 3. The enforcement hook — how it works

`.claude/settings.json` defines a **`PostToolUse` hook**: after every `Edit`/`Write`/`MultiEdit`,
the harness (not the model) runs `scripts/check_naming_conventions.py` on the edited `.py`
file. If it finds a violation, the hook exits `2` and the failure is **fed back to the agent
to fix**. This is the deterministic backstop — it works even if the model "forgets."

```jsonc
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "jq -r '.tool_input.file_path // empty' | { read -r f; [ -n \"$f\" ] || exit 0; case \"$f\" in *.py) python3 \"${CLAUDE_PROJECT_DIR:-.}/scripts/check_naming_conventions.py\" \"$f\" >&2 || exit 2 ;; esac; }"
      }]
    }]
  }
}
```

**Scope:** the hook enforces what the script checks (function `snake_case`, DTO classes
ending in `DTO`). The broader rules — folder structure, `ConfigDict`, section headers,
UPPERCASE enum values — are **guidance** that the agent follows from `CLAUDE.md` + the skill
(always in context), not script-enforced.

---

## 4. How to ACTIVATE

### New local sessions & all cloud sessions
Automatic — the hook + skill + CLAUDE.md load from the committed files on session start.
**Nothing to do**, as long as the branch you're on contains them (see §5).

### The CURRENT session (right after creating/changing `settings.json`)
The settings watcher only tracks `.claude/` if a `settings.json` existed when the session
**started**. After first creating it, activate it one of two ways:
1. Open **`/hooks`** in the Claude Code prompt (this reloads config), **or**
2. **Restart** Claude Code.

Verify it's loaded: run `/hooks` and confirm the `PostToolUse` entry is listed.

---

## 5. How it reaches CLOUD / teammates

Committed-and-merged is the requirement:

```bash
# 1. commit the .claude/ files + the checker + CLAUDE.md
git add .claude CLAUDE.md scripts/check_naming_conventions.py
git commit -m "chore: enforce railmind conventions via hook"

# 2. push your branch
git push origin <your-branch>

# 3. merge into the mainline so EVERY branch/cloud session gets it
#    open a PR: <your-branch> -> develop -> main
```

Until the PR is merged, only **your branch** has the hook/skill. Sessions on `develop` or
`main` won't enforce it yet.

---

## 6. How to VERIFY the hook works

Pipe-test the command directly (simulates what the harness sends):

```bash
# compliant file -> exit 0, no output
echo '{"tool_input":{"file_path":"app/domain/train/train_router/train.py"}}' \
  | bash -c "$(jq -r '.hooks.PostToolUse[0].hooks[0].command' .claude/settings.json)"; echo "exit=$?"

# violation -> exit 2 + a [FAIL] message
printf 'def badName():\n  pass\n' > /tmp/bad.py
echo '{"tool_input":{"file_path":"/tmp/bad.py"}}' \
  | bash -c "$(jq -r '.hooks.PostToolUse[0].hooks[0].command' .claude/settings.json)"; echo "exit=$?"
rm /tmp/bad.py
```

You can also run the checker over the whole app any time:
```bash
python3 scripts/check_naming_conventions.py $(find app -name '*.py' -not -path '*/__pycache__/*')
```

Escape hatch: append `# naming: ignore` to a line the checker shouldn't flag
(e.g. fastapi-filter's inner `class Constants`).

---

## 7. How to EXTEND

- **More rules in the skill:** edit `.claude/skills/railmind-conventions/SKILL.md`. Pure
  guidance — no code needed. (See its §9/§10 for the module-folder structure and DTO rules.)
- **Hard-enforce more rules:** add checks to `scripts/check_naming_conventions.py` (it parses
  each file's AST). E.g. require `ConfigDict` on DTO classes, or the `# -- Name --` section
  headers. Anything you add there is automatically enforced by the existing hook.
- **More hooks:** add entries under `.claude/settings.json` → `hooks`. Use the `/hooks`
  menu or ask Claude (the `update-config` skill) to wire them up.

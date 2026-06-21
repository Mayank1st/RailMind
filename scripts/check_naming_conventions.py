#!/usr/bin/env python3
"""RailMind naming-convention checker. Receives .py paths, enforces naming rules."""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path

# --- CONFIG ---
DTO_FILE_SUFFIXES = ("dto.py", "_dto.py", "dtos.py")
DTO_PATH_MARKERS = ("/dto/", "/dtos/")
MODEL_FILE_SUFFIXES = ("models.py", "model.py")
MODEL_PATH_MARKERS = ("/models/",)

RULE_SNAKE_CASE_FUNCTIONS = True
RULE_DTO_SUFFIX = True
RULE_SINGULAR_MODELS = False  # models are PLURAL in RailMind -> rule off

SINGULAR_ALLOWLIST = {
    "Address",
    "Status",
    "Series",
    "News",
    "Class",
    "Access",
    "Business",
    "Process",
    "Bus",
    "Bonus",
    "Census",
}
# --- END CONFIG ---

_SNAKE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def is_snake_case(name: str) -> bool:
    return bool(_SNAKE_RE.match(name))


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def looks_plural(name: str) -> bool:
    if name in SINGULAR_ALLOWLIST:
        return False
    low = name.lower()
    if low.endswith(("ss", "us", "is", "sis", "ous")):
        return False
    return low.endswith("s")


def classify(path: Path) -> tuple[bool, bool]:
    p = path.as_posix()
    name = path.name
    is_dto = name.endswith(DTO_FILE_SUFFIXES) or any(m in p for m in DTO_PATH_MARKERS)
    is_model = name.endswith(MODEL_FILE_SUFFIXES) or any(
        m in p for m in MODEL_PATH_MARKERS
    )
    return is_dto, is_model


def line_has_ignore(src_lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(src_lines):
        return "# naming: ignore" in src_lines[lineno - 1]
    return False


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: syntax error ({e.msg})"]

    src_lines = src.splitlines()
    is_dto, is_model = classify(path)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if RULE_SNAKE_CASE_FUNCTIONS and not is_dunder(node.name):
                if not is_snake_case(node.name) and not line_has_ignore(
                    src_lines, node.lineno
                ):
                    errors.append(
                        f"{path}:{node.lineno}: function '{node.name}' must be snake_case"
                    )
        elif isinstance(node, ast.ClassDef):
            if is_dto and RULE_DTO_SUFFIX and not node.name.endswith("DTO"):
                if not line_has_ignore(src_lines, node.lineno):
                    errors.append(
                        f"{path}:{node.lineno}: class '{node.name}' in a DTO file must end with 'DTO'"
                    )
            if is_model and RULE_SINGULAR_MODELS and looks_plural(node.name):
                if not line_has_ignore(src_lines, node.lineno):
                    errors.append(
                        f"{path}:{node.lineno}: model '{node.name}' must be singular, not plural"
                    )
    return errors


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv if a.endswith(".py")]
    all_errors: list[str] = []
    for p in paths:
        all_errors.extend(check_file(p))
    if all_errors:
        print("RailMind naming check failed:\n", file=sys.stderr)
        for e in all_errors:
            print(f"  [FAIL] {e}", file=sys.stderr)
        print(
            "\nFix the names above, or add '# naming: ignore' for a deliberate exception.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

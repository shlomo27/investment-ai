#!/usr/bin/env python3
"""Structural checks on the scheduler, which no runtime path exercises.

create_scheduler spent nine days returning None. A function definition was
inserted into the middle of it, so seventeen of its eighteen add_job calls
and its `return` ended up inside the new function. Nothing caught it: the
file imported cleanly, every test that existed passed, and the only symptom
was `AttributeError: 'NoneType' object has no attribute 'start'` raised deep
inside a keeper loop that caught it, logged it, and retried every sixty
seconds for the rest of the week.

The scheduler only runs in one of four workers, behind an advisory lock, in
production. That is the worst possible place for a mistake to hide, so the
shape of it is checked here instead — statically, with no database, in under
a second.

    python scripts/check_scheduler.py
"""
import ast
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "app" / "workers" / "in_process_scheduler.py"

#: Jobs the system is not correct without. scheduled_ta_scan is the one that
#: produces user-facing alerts; the others are listed because losing any of
#: them silently is the failure this script exists to prevent.
REQUIRED_JOBS = {
    "scheduled_ta_scan",
    "scheduled_prescreener",
    "scheduled_weekly_full_scan",
    "scheduled_earnings_watcher",
    "scheduled_digest_sender",
    "scheduled_stale_recommendations",
    "scheduled_rec_levels",
    "scheduled_alert_outcomes",
}


def main() -> int:
    tree = ast.parse(SOURCE.read_text())
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "create_scheduler"),
        None,
    )
    if fn is None:
        print("✗ create_scheduler is not defined")
        return 1

    problems = []

    # Walking the function body reaches nested definitions too, which is
    # exactly how the bug hid: the add_job calls were still "inside"
    # create_scheduler textually while belonging to another function. Count
    # only what the function itself executes.
    own: list[ast.AST] = []
    def collect(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # a nested definition's body is not our body
            own.append(child)
            collect(child)
    collect(fn)

    nested = [c.name for c in ast.iter_child_nodes(fn)
              if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if nested:
        problems.append(
            f"create_scheduler contains nested definitions: {', '.join(nested)}. "
            "A function defined here swallows everything after it."
        )

    if not any(isinstance(n, ast.Return) for n in own):
        problems.append("create_scheduler never returns — callers get None")

    ids = set()
    for n in own:
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_job":
            for kw in n.keywords:
                if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                    ids.add(kw.value.value)

    missing = REQUIRED_JOBS - ids
    if missing:
        problems.append(f"jobs not registered: {', '.join(sorted(missing))}")

    if problems:
        print("✗ scheduler is not wired correctly:\n")
        for p in problems:
            print(f"    {p}")
        return 1

    print(f"✓ create_scheduler returns a scheduler with {len(ids)} jobs registered.")
    print(f"  Required jobs all present: {', '.join(sorted(REQUIRED_JOBS))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

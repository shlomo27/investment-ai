#!/usr/bin/env python3
"""The backend's static checks, in one command. No database, a few seconds.

    python scripts/check_backend.py

Two bugs in two days shipped because they were only reachable at runtime, in
production, behind a path nobody exercised before pushing:

  create_scheduler returned None for nine days — a function inserted into
  the middle of it swallowed seventeen add_job calls and the return. No
  scheduler, no technical scan, no alerts.

  auth.py called normalize() without importing it. The import was skipped
  because a function further down already imported *other* names from the
  same module, and a check for the module's name found that instead. Every
  profile save and every new registration raised NameError — the language
  could not be changed, notification settings did not persist, and nobody
  new could sign up.

Both are visible statically. This runs both checks.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def undefined_names() -> int:
    """Names used but never defined or imported — the auth.py class of bug."""
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        print("✗ pyflakes is not installed: pip install pyflakes")
        return 1
    out = subprocess.run(
        [sys.executable, "-m", "pyflakes", "app", "main.py", "startup.py"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    hits = [line for line in out.splitlines() if "undefined name" in line]
    if hits:
        print(f"✗ {len(hits)} undefined name(s) — each one raises NameError when reached:\n")
        for h in hits:
            print(f"    {h}")
        return 1
    print("✓ No undefined names.")
    return 0


def scheduler() -> int:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_scheduler.py")], cwd=ROOT
    ).returncode


if __name__ == "__main__":
    failed = undefined_names() | scheduler()
    sys.exit(1 if failed else 0)

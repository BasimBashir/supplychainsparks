"""Packaged entry point: windowed-mode stdio guard, then sparks.app.main.run()."""
import os
import sys

# PyInstaller console=False builds have no stdio: sys.stdout/stderr are None,
# which crashes uvicorn's logging formatter (.isatty()) and other libraries.
# All real output goes to the rotating log file set up in main._setup_logging.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from sparks.app.main import run

if __name__ == "__main__":
    raise SystemExit(run())

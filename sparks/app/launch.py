"""Packaged entry point: redirects straight to sparks.app.main.run()."""
from sparks.app.main import run

if __name__ == "__main__":
    raise SystemExit(run())

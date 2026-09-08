"""Mechanical publishability check: no links, no source names."""
from __future__ import annotations

import re

_URL_RE = re.compile(r"(https?://\S+|\bwww\.\S+)")


def assert_publishable(text: str, blocked_names: list[str]) -> list[str]:
    violations: list[str] = []
    violations += [f"contains URL: {m}" for m in _URL_RE.findall(text)]
    lowered = text.lower()
    for name in blocked_names:
        if name and name.lower() in lowered:
            violations.append(f"mentions source name: {name}")
    return violations

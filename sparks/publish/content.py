"""Content-repo file writer implementing the shared contract (see Plan 3)."""
from __future__ import annotations

import json
import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    ascii_title = (unicodedata.normalize("NFKD", title)
                   .encode("ascii", "ignore").decode("ascii"))
    slug = _SLUG_RE.sub("-", ascii_title.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "story"


def build_post_files(meta: dict, en_md: str, ar_md: str | None) -> dict[str, str]:
    base = f"content/posts/{meta['slug']}"
    files = {f"{base}/en.md": en_md,
             f"{base}/meta.json": json.dumps(meta, ensure_ascii=False, indent=2) + "\n"}
    if ar_md:
        files[f"{base}/ar.md"] = ar_md
    return files

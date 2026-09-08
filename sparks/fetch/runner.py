"""FetchRunner: polite, robots-respecting fetching of all sources -> raw files + DB."""
from __future__ import annotations

import hashlib
import pathlib
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from sparks.config import Settings
from sparks.db import Database
from sparks.fetch.html import parse_listing
from sparks.fetch.rss import parse_feed
from sparks.models import FetchedEntry, Source, SourceRun


def delay_needed(now: float, last_request: float, delay_s: float) -> float:
    """Seconds to wait before hitting the same domain again (pure function)."""
    return max(0.0, delay_s - (now - last_request))


def save_raw(raw_dir: pathlib.Path, url: str, content: bytes) -> pathlib.Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha1(f"{url}".encode("utf-8")).hexdigest()[:16]
    day_dir = raw_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{digest}.raw"
    path.write_bytes(content)
    return path


class _Politeness:
    """Shared per-domain rate limiting + robots.txt checking via httpx (mockable)."""

    def __init__(self, client_get, user_agent: str, delay_s: float):
        self._client_get = client_get
        self._user_agent = user_agent
        self._delay_s = delay_s
        self._domain_last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def wait(self, url: str) -> None:
        domain = urlsplit(url).netloc or url
        now = time.monotonic()
        delay = delay_needed(now, self._domain_last.get(domain, 0.0), self._delay_s)
        if delay > 0:
            time.sleep(delay)
        self._domain_last[domain] = time.monotonic()

    def robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self._client_get(host + "/robots.txt")  # through httpx -> mockable
                resp.raise_for_status()
                rp.parse(resp.text.splitlines())
                self._robots[host] = rp
            except Exception:
                self._robots[host] = None  # unreachable robots -> allow
        rp = self._robots[host]
        return rp is None or rp.can_fetch(self._user_agent, url)


class FetchRunner:
    def __init__(self, settings: Settings, db: Database, client: httpx.Client | None = None):
        self.settings = settings
        self.db = db
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.settings.fetch.user_agent,
                         "Accept-Language": "en, ar;q=0.8"},
                timeout=self.settings.fetch.timeout_seconds,
                follow_redirects=True)
        return self._client

    def run(self, sources: list[Source] | None = None) -> list[SourceRun]:
        sources = sources if sources is not None else self.db.all_sources(enabled_only=True)
        politeness = _Politeness(self.client.get, self.settings.fetch.user_agent,
                                 self.settings.fetch.per_domain_delay_seconds)
        runs: list[SourceRun] = []
        for source in sources:
            run = SourceRun(source_id=source.id or -1, source_name=source.name, status="ok")
            run_id = self.db.start_fetch_run(source.id or -1)
            try:
                if not politeness.robots_allows(source.url):
                    run.status = "skipped_robots"
                    self.db.finish_fetch_run(run_id, "skipped_robots", 0)
                    runs.append(run)
                    continue
                politeness.wait(source.url)
                response = self.client.get(source.url)
                response.raise_for_status()
                content = response.content
                if source.kind == "rss":
                    entries = parse_feed(content, self.settings.fetch.max_items_per_source)
                else:
                    html_text = content.decode("utf-8", errors="replace")
                    pattern = source.link_pattern or "press|news|article"
                    entries = parse_listing(html_text, source.url, pattern,
                                            self.settings.fetch.max_items_per_source)
                run.items_found = len(entries)
                for entry in entries:
                    if not entry.url:
                        continue
                    raw_path = save_raw(self.settings.raw_dir, entry.url, content)
                    new_id = self.db.insert_item(
                        source.id or -1, entry, raw_path=str(raw_path),
                        fetched_at=datetime.now(timezone.utc))
                    if new_id is not None:
                        run.items_new += 1
                self.db.mark_source_health(source.id or -1, healthy=True)
            except Exception as exc:  # per-source isolation (spec 11)
                run.status = "error"
                run.error = f"{type(exc).__name__}: {exc}"
                self.db.finish_fetch_run(run_id, "error", run.items_found, run.error)
                self.db.mark_source_health(source.id or -1, healthy=False)
            else:
                self.db.finish_fetch_run(run_id, "ok", run.items_found)
                self.db.set_source_fetched(source.id or -1)
            runs.append(run)
        return runs

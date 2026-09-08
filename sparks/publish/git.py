"""Git publisher: dulwich clone/commit/push of the content repo (no git binary)."""
from __future__ import annotations

import pathlib
from urllib.parse import urlsplit, urlunsplit

from dulwich import porcelain

from sparks.config import Settings


def authed_url(repo_url: str, token: str) -> str:
    if not token or not repo_url.startswith("http"):
        return repo_url
    parts = urlsplit(repo_url)
    netloc = f"x-access-token:{token}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class GitError(Exception):
    pass


class GitPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clone_dir = settings.data_dir / "content-repo"

    def _ensure_clone(self) -> None:
        url = authed_url(self.settings.publish.repo_url, self.settings.publish.token)
        if not (self.clone_dir / ".git").exists():
            self.clone_dir.parent.mkdir(parents=True, exist_ok=True)
            # clone without branch: empty remotes have no refs yet
            porcelain.clone(url, str(self.clone_dir))
        else:
            try:
                porcelain.pull(str(self.clone_dir), url,
                               refspecs=f"refs/heads/{self.settings.publish.branch}"
                                        .encode())
            except Exception:
                # remote has no refs yet (fresh empty repo) or already current
                pass

    def publish(self, files: dict[str, str], message: str) -> str:
        if not self.settings.publish.repo_url:
            raise GitError("publish.repo_url not configured")
        self._ensure_clone()
        for rel_path, content in files.items():
            path = self.clone_dir / pathlib.PurePosixPath(rel_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        branch = self.settings.publish.branch.encode()
        with porcelain.open_repo_closing(str(self.clone_dir)) as repo:
            repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/" + branch)
            for rel_path in files:
                porcelain.add(repo=repo, paths=[str(self.clone_dir / rel_path)])
            sha = porcelain.commit(repo=repo, message=message.encode())
            remote = authed_url(self.settings.publish.repo_url,
                                self.settings.publish.token)
            porcelain.push(repo, remote,
                           refspecs=b"refs/heads/" + branch)
        return sha.decode() if isinstance(sha, bytes) else str(sha)

    def build_url(self, slug: str) -> str:
        base = self.settings.publish.site_base_url.rstrip("/")
        return f"{base}/post/{slug}"

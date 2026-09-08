import pytest
from dulwich import porcelain
from dulwich.object_store import iter_tree_contents

from sparks.publish.git import GitPublisher, authed_url


def _tree_paths(repo, tree_id) -> set[str]:
    return {(p.decode() if isinstance(p, bytes) else str(p))
            for p, _, _ in iter_tree_contents(repo.object_store, tree_id)}


def test_authed_url_embeds_token():
    assert (authed_url("https://github.com/org/repo.git", "tk") ==
            "https://x-access-token:tk@github.com/org/repo.git")
    assert authed_url("https://github.com/org/repo.git", "") == "https://github.com/org/repo.git"


@pytest.fixture
def repo_pair(settings, tmp_path):
    """Local bare 'remote' + publisher pointed at it."""
    settings.publish.repo_url = str(tmp_path / "remote.git")
    settings.publish.branch = "main"
    settings.publish.token = ""
    porcelain.init(str(tmp_path / "remote.git"), bare=True)
    return GitPublisher(settings), tmp_path / "remote.git"


def test_publish_writes_files_and_pushes(repo_pair):
    publisher, remote = repo_pair
    sha = publisher.publish({
        "content/posts/saudi-port-expansion-2026/en.md": "# hello",
        "content/posts/saudi-port-expansion-2026/meta.json": '{"slug": "x"}',
    }, "publish: test post")
    assert len(sha) == 40
    with porcelain.open_repo_closing(str(remote)) as repo:
        assert b"refs/heads/main" in repo.refs
        tree = repo[repo[repo.refs[b"refs/heads/main"]].tree]
        paths = _tree_paths(repo, tree.id)
    assert "content/posts/saudi-port-expansion-2026/en.md" in paths


def test_second_publish_adds_file(repo_pair):
    publisher, remote = repo_pair
    publisher.publish({"content/posts/a/en.md": "one"}, "first")
    publisher.publish({"content/posts/b/en.md": "two"}, "second")
    with porcelain.open_repo_closing(str(remote)) as repo:
        commit = repo[repo.refs[b"refs/heads/main"]]
        paths = _tree_paths(repo, commit.tree)
    assert {"content/posts/a/en.md", "content/posts/b/en.md"} <= paths


def test_build_url(repo_pair):
    publisher, _ = repo_pair
    assert publisher.build_url("my-post") == "https://supplychainsparks.com/post/my-post"

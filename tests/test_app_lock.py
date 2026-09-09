from sparks.app.main import acquire_lock, release_lock


def test_lock_is_exclusive(settings):
    assert acquire_lock(settings.data_dir) is True
    assert acquire_lock(settings.data_dir) is False
    release_lock(settings.data_dir)
    assert acquire_lock(settings.data_dir) is True


def test_stale_lock_from_dead_pid_is_stolen(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "app.lock").write_text("4000000")  # pid beyond any real process
    assert acquire_lock(settings.data_dir) is True

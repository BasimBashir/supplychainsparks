from sparks.app.main import acquire_lock, release_lock


def test_lock_is_exclusive(settings):
    assert acquire_lock(settings.data_dir) is True
    assert acquire_lock(settings.data_dir) is False
    release_lock(settings.data_dir)
    assert acquire_lock(settings.data_dir) is True

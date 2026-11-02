import os

from bot.cache import RunCache


def test_disabled_cache_never_touches_disk(tmp_path):
    cache = RunCache()
    cache.put("prices", {"A": 1})
    assert cache.get("prices") == {"A": 1}
    assert list(tmp_path.iterdir()) == []


def test_saved_values_are_read_by_the_next_run(tmp_path):
    path = tmp_path / "c.pkl"
    RunCache(str(path)).put("contexts", {"INTC": {"sector": "Tech"}})
    assert RunCache(str(path)).get("contexts") == {"INTC": {"sector": "Tech"}}
    assert RunCache(str(path)).get("prices") is None


def test_expired_cache_is_ignored(tmp_path):
    path = tmp_path / "c.pkl"
    RunCache(str(path)).put("prices", {"A": 1})
    old = path.stat().st_mtime - 4 * 3600
    os.utime(path, (old, old))
    assert RunCache(str(path), ttl_minutes=180).get("prices") is None


def test_corrupt_cache_is_ignored(tmp_path, caplog):
    path = tmp_path / "c.pkl"
    path.write_bytes(b"no es un pickle")
    assert RunCache(str(path)).get("prices") is None
    assert "Caché ilegible" in caplog.text


def test_unwritable_path_only_warns(tmp_path, caplog):
    cache = RunCache(str(tmp_path / "no" / "existe" / "c.pkl"))
    cache.put("prices", {"A": 1})
    assert "No se pudo guardar" in caplog.text
    assert cache.get("prices") == {"A": 1}

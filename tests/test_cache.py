from civicpilot.cache import QueryCache


def test_set_and_get_roundtrip():
    cache = QueryCache()
    key = QueryCache.make_key("fr", "search", agency="epa")
    cache.set(key, {"count": 3})
    assert cache.get(key) == {"count": 3}


def test_missing_key_returns_none():
    cache = QueryCache()
    assert cache.get("nope") is None


def test_expired_entry_returns_none():
    fake_time = [0.0]
    cache = QueryCache(ttl_seconds=10, clock=lambda: fake_time[0])
    key = "k"
    cache.set(key, "v")
    fake_time[0] = 11.0
    assert cache.get(key) is None


def test_make_key_is_order_independent_for_kwargs():
    k1 = QueryCache.make_key("fr", agency="epa", type="rule")
    k2 = QueryCache.make_key("fr", type="rule", agency="epa")
    assert k1 == k2


def test_make_key_differs_for_different_args():
    k1 = QueryCache.make_key("fr", agency="epa")
    k2 = QueryCache.make_key("fr", agency="doe")
    assert k1 != k2


def test_set_evicts_oldest_entry_when_full():
    fake_time = [0.0]
    cache = QueryCache(maxsize=2, ttl_seconds=1000, clock=lambda: fake_time[0])
    cache.set("a", 1)
    fake_time[0] = 1.0
    cache.set("b", 2)
    fake_time[0] = 2.0
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3

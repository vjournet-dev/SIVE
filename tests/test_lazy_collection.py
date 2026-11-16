import logging
import threading

import pytest

from sive.infra.vector_store.lazy import LazyCollection


class _Collection:
    def count(self) -> int:
        return 3


def test_collection_is_opened_once_on_first_attribute_access():
    calls: list[int] = []

    def factory():
        calls.append(1)
        return _Collection()

    lazy = LazyCollection(factory)
    assert not lazy.is_open
    assert calls == []

    assert lazy.count() == 3
    assert lazy.count() == 3

    assert lazy.is_open
    assert calls == [1]


def test_failed_open_is_not_cached():
    attempts: list[int] = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("model not available yet")
        return _Collection()

    lazy = LazyCollection(factory)

    with pytest.raises(OSError):
        lazy.count()
    assert not lazy.is_open

    assert lazy.count() == 3
    assert len(attempts) == 2


def test_private_and_dunder_lookups_do_not_open_the_collection():
    def factory():
        raise AssertionError("must stay closed")

    lazy = LazyCollection(factory)

    assert not hasattr(lazy, "_missing")
    assert not hasattr(lazy, "__wrapped__")
    assert not lazy.is_open


def test_warm_up_opens_in_background_and_swallows_failures(caplog):
    opened = threading.Event()

    def factory():
        opened.set()
        return _Collection()

    warmed = LazyCollection(factory)
    warmed.warm_up().join(timeout=5)
    assert opened.is_set()
    assert warmed.is_open

    def broken_factory():
        raise RuntimeError("boom")

    broken = LazyCollection(broken_factory)
    with caplog.at_level(logging.WARNING, logger="sive.infra.vector_store.lazy"):
        broken.warm_up().join(timeout=5)
    assert not broken.is_open
    assert any("warm-up failed" in record.message for record in caplog.records)

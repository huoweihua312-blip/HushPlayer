"""音源健康度：计数、持久化与摘要文案。"""

from __future__ import annotations

from hushplayer.core import paths
from hushplayer.online import health


def test_counts_survive_reload(data_dir) -> None:
    health.reset()
    health.record_ok("src-a")
    health.record_ok("src-a")
    health.record_fail("src-a", "404")
    health.record_fail("src-b", "timeout")

    stats = health.stats("src-a")
    assert stats["ok"] == 2 and stats["fail"] == 1
    assert "67%" in health.summary("src-a")

    # A fresh read (simulating a restart) sees the same numbers.
    from importlib import reload

    reload(health)
    assert health.stats("src-a")["ok"] == 2
    assert health.summary("src-b") == "最近解析全部失败"


def test_success_clears_last_error(data_dir) -> None:
    health.reset()
    health.record_fail("src-c", "boom")
    assert health.stats("src-c")["last_error"] == "boom"
    health.record_ok("src-c")
    assert "last_error" not in health.stats("src-c")


def test_empty_summary_for_unknown_source(data_dir) -> None:
    health.reset()
    assert health.summary("nope") == ""
    assert health.stats("nope") == {}

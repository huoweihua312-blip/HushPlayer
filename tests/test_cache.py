"""缓存服务：容量统计、清理与索引修复（可恢复数据，不含用户收藏）。"""

from __future__ import annotations

import json
import os
import time

import pytest

from hushplayer.core import paths
from hushplayer.library.artwork import ArtworkStore
from hushplayer.online.proxy import AudioProxy
from hushplayer.services.cache import CacheService


def write(path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)


@pytest.fixture()
def service(data_dir, qapp):
    proxy = AudioProxy(cache_dir=paths.audio_cache_dir())
    artwork = ArtworkStore(paths.artwork_cache_dir())
    instance = CacheService(proxy, artwork)
    yield instance
    proxy.shutdown()


def test_stats_sums_known_folders(data_dir, service) -> None:
    write(paths.audio_cache_dir() / "a.mp3", 100)
    write(paths.artwork_cache_dir() / "b.png", 50)
    write(paths.lyrics_cache_dir() / "c.json", 10)
    stats = service.stats()
    assert stats.audio_bytes == 100
    assert stats.artwork_bytes == 50
    assert stats.lyrics_bytes == 10
    assert stats.total_bytes >= 160
    assert "缓存" in service.summary_text()


def test_clear_removes_cache_but_keeps_database(data_dir, service) -> None:
    write(paths.audio_cache_dir() / "a.mp3", 10)
    write(paths.artwork_cache_dir() / "b.png", 10)
    database = paths.database_file()
    write(database, 10)
    service.clear_all()
    assert not (paths.audio_cache_dir() / "a.mp3").exists()
    assert not (paths.artwork_cache_dir() / "b.png").exists()
    assert database.exists(), "清缓存不应删除音乐库数据库"


def test_repair_removes_orphan_and_mismatched(data_dir, service) -> None:
    audio = paths.audio_cache_dir()
    good = audio / "good.mp3"
    write(good, 20)
    (audio / "good.meta.json").write_text(
        json.dumps({"complete": True, "size": 20, "url": "http://x/good.mp3"}), encoding="utf-8"
    )

    bad = audio / "bad.mp3"
    write(bad, 20)
    (audio / "bad.meta.json").write_text(
        json.dumps({"complete": True, "size": 999, "url": "http://x/bad.mp3"}), encoding="utf-8"
    )

    orphan = audio / "orphan.mp3"
    write(orphan, 30)

    broken = audio / "broken.mp3"
    write(broken, 12)
    (audio / "broken.meta.json").write_text("{not json", encoding="utf-8")

    report = service.repair()
    assert good.exists(), "完整缓存必须保留"
    assert not bad.exists(), "大小不一致的缓存应删除"
    assert not orphan.exists(), "无索引的孤立文件应删除"
    assert not broken.exists(), "损坏索引对应的文件应删除"
    assert len(report.problems) >= 3


def test_proxy_prune_keeps_newest(data_dir, qapp) -> None:
    proxy = AudioProxy(cache_dir=paths.audio_cache_dir())
    audio = paths.audio_cache_dir()
    for index in range(4):
        file = audio / f"f{index}.mp3"
        write(file, 1000)
        (audio / f"f{index}.meta.json").write_text(json.dumps({"complete": True, "size": 1000}), encoding="utf-8")
        old = time.time() - (10 - index) * 60
        os.utime(file, (old, old))
    proxy.prune(max_bytes=1500)
    remaining = sorted(item.name for item in audio.iterdir() if item.suffix == ".mp3" and item.name.startswith("f"))
    assert remaining == ["f3.mp3"], "按时间从旧到新删除，直到不超预算"
    proxy.shutdown()


def test_audio_proxy_serves_cached_file(data_dir, qapp) -> None:
    """已完整缓存的音频应能通过本地 HTTP 代理播放，并支持 Range。"""
    import requests

    from hushplayer.online.proxy import token_for

    proxy = AudioProxy(cache_dir=paths.audio_cache_dir())
    cache_key = "test:track:standard"
    token = token_for(cache_key)
    audio = paths.audio_cache_dir() / f"{token}.mp3"
    write(audio, 2048)
    (paths.audio_cache_dir() / f"{token}.meta.json").write_text(
        json.dumps({"complete": True, "size": 2048}), encoding="utf-8"
    )
    url = proxy.register(cache_key, "http://example.invalid/x.mp3", {}, mime="audio/mpeg", ext=".mp3")
    response = requests.get(url, headers={"Range": "bytes=100-199"}, timeout=10)
    assert response.status_code == 206
    assert len(response.content) == 100
    assert response.headers["Content-Range"].startswith("bytes 100-199/2048")
    proxy.shutdown()

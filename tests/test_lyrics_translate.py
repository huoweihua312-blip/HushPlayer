"""歌词翻译与结构化搜索：纯逻辑 + 服务接线。"""

from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

from hushplayer.lyrics import service as service_module
from hushplayer.lyrics import translate as translate_module
from hushplayer.lyrics.parser import parse as parse_lyrics
from hushplayer.lyrics.service import (
    LyricsCandidate,
    LyricsService,
    _LyricsSearchJob,
    _rank_candidates,
    _translation_lrc,
)

LRC_TEXT = """[00:01.00]we were young
[00:04.00]chasing the light
[00:08.50]now the night is over
"""


def wait_for(predicate, timeout: float = 6.0) -> None:
    deadline = time.monotonic() + timeout
    app = QApplication.instance()
    while time.monotonic() < deadline:
        if predicate():
            return
        if app is not None:
            app.processEvents()  # 让线程池的排队信号回到主线程
        time.sleep(0.02)
    raise AssertionError("等待翻译回调超时")


def test_needs_translation_only_for_foreign_text() -> None:
    assert translate_module.needs_translation("we were young")
    assert translate_module.needs_translation("君の名前を呼ぶ")
    assert not translate_module.needs_translation("夜航信号")
    assert not translate_module.needs_translation("")


def test_translate_lines_caches_and_falls_back(monkeypatch) -> None:
    translate_module.clear_cache()
    calls: list[list[str]] = []
    monkeypatch.setattr(
        translate_module,
        "_translate_edge",
        lambda lines: calls.append(list(lines)) or [f"译{i}" for i, _ in enumerate(lines)],
    )
    first = translate_module.translate_lines(["hello", "world"])
    second = translate_module.translate_lines(["hello", "world"])
    assert first == second == ["译0", "译1"]
    assert len(calls) == 1, "同一行第二次应命中缓存，不再请求"

    translate_module.clear_cache()
    monkeypatch.setattr(translate_module, "_translate_edge", lambda lines: [])
    monkeypatch.setattr(
        translate_module, "_translate_google", lambda lines: [f"G{i}" for i, _ in enumerate(lines)]
    )
    assert translate_module.translate_lines(["fallback"]) == ["G0"]


def test_translation_lrc_keeps_timestamps() -> None:
    document = parse_lyrics(LRC_TEXT, source="lrclib", provider="LRCLIB")
    for line in document.lines:
        line.translation = "翻译" + line.text
    text = _translation_lrc(document)
    assert text.splitlines()[0].startswith("[00:01.00]")
    assert "翻译we were young" in text


def test_params_prefer_structured_fields() -> None:
    job = _LyricsSearchJob(
        None, "晴天 周杰伦", 1, title="晴天", artist="周杰伦", album="叶惠美", duration_ms=269000
    )
    assert job._params_sets() == [
        {"track_name": "晴天", "artist_name": "周杰伦", "album_name": "叶惠美"},
        {"track_name": "晴天"},
        {"q": "晴天 周杰伦"},
    ]
    only_title = _LyricsSearchJob(None, "", 1, title="晴天")
    assert only_title._params_sets() == [{"track_name": "晴天"}]


def test_rank_candidates_prefers_exact_title_and_artist() -> None:
    def candidate(cid: int, title: str, artist: str, duration: int) -> LyricsCandidate:
        return LyricsCandidate(
            id=cid,
            title=title,
            artist=artist,
            album="",
            duration_ms=duration,
            synced="[00:01.00]x",
            plain="",
        )

    items = [
        candidate(1, "晴天 (Live)", "其他歌手", 300000),
        candidate(2, "晴天", "周杰伦", 269000),
        candidate(3, "晴天", "周杰伦", 268500),
    ]
    ranked = _rank_candidates(items, "晴天", "周杰伦", 269000)
    assert [item.id for item in ranked][:2] == [2, 3]
    assert ranked[-1].id == 1


def test_service_translate_attaches_and_persists(library, qapp, data_dir, monkeypatch) -> None:
    from hushplayer.model.track import Track

    track = Track(id="online:translate", title="Night", artist="Aurora", kind="online")
    document = parse_lyrics(LRC_TEXT, source="lrclib", provider="LRCLIB")
    service = LyricsService(library.tracks, library.bindings, library.meta, client=None)
    service_module._write_cache(track.id, LRC_TEXT, provider="lrclib")

    monkeypatch.setattr(
        translate_module,
        "translate_lines",
        lambda lines: [f"中文{i}" for i, _ in enumerate(lines)],
    )
    ready: list[object] = []
    started: list[str] = []
    service.translation_ready.connect(ready.append)
    service.translation_started.connect(started.append)

    service.translate(track, document)
    wait_for(lambda: bool(ready))
    result = ready[0]
    assert result.document.has_translation
    assert [line.translation for line in document.lines][0] == "中文0"
    assert started == [track.id]
    cached = service_module._read_cache(track.id)
    assert cached is not None and "中文0" in cached[1]

"""封面持久化与播放栏点击行为。"""

from __future__ import annotations

from pathlib import Path


def _make_png(path: Path, color: str = "#c95770") -> str:
    from PySide6.QtGui import QColor, QImage

    image = QImage(24, 24, QImage.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return str(path)


def _online_track(library, artwork_url: str = "https://example.invalid/a.jpg"):
    from hushplayer.model.track import Track

    track = Track(
        id="online:cover",
        title="夜航信号",
        artist="Aurora Field",
        kind="online",
        source_id="custom_source_test",
        remote_id="cover-1",
        artwork_url=artwork_url,
    )
    library.tracks.upsert(track)
    return track


def test_cover_ready_persists_artwork_path(library, tmp_path) -> None:
    track = _online_track(library)
    path = _make_png(tmp_path / "cover.png")

    updates: list[str] = []
    library.track_updated.connect(updates.append)
    library.covers._resolved[track.id] = path  # 模拟下载线程刚写完
    library.covers.ready.emit(track.id)

    stored = library.tracks.get(track.id)
    assert stored is not None
    assert stored.artwork_path == path
    assert updates == [track.id]
    # 重启后应能只靠 artwork_path 找到封面，不再需要 URL。
    assert library.covers.key_for(stored) == path


def test_cover_widget_refreshes_when_download_finishes(library, qapp, monkeypatch) -> None:
    import hushplayer.ui.context as context_module
    from hushplayer.ui.widgets.cover import CoverWidget

    track = _online_track(library)
    path = _make_png(Path(library.db.path).parent / "late-cover.png")

    fake_ctx = type(
        "Ctx",
        (),
        {"covers": library.covers, "library": library, "player": None, "settings": None},
    )()
    monkeypatch.setattr(context_module, "ctx", lambda: fake_ctx)

    widget = CoverWidget(40, radius=6)
    widget.set_track(track)
    assert widget._pixmap is None  # 远端 URL 尚未下载

    library.covers._resolved[track.id] = path
    library.covers.ready.emit(track.id)
    qapp.processEvents()
    assert widget._pixmap is not None, "下载完成的封面应自动出现在播放栏"


def test_cover_click_is_separate_from_track_info(qapp) -> None:
    from hushplayer.ui.widgets.playerbar import PlayerBar

    bar = PlayerBar()
    cover_clicks: list[bool] = []
    info_clicks: list[bool] = []
    bar.cover_clicked.connect(lambda: cover_clicks.append(True))
    bar.track_info_clicked.connect(lambda: info_clicks.append(True))

    bar.cover.clicked.emit()
    assert cover_clicks == [True]
    assert info_clicks == [], "点封面不应再走「跳专辑」的旧逻辑"

    bar.info.clicked.emit()
    assert info_clicks == [True]

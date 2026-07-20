from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.services.lyrics_timing import (
    LYRICS_TIMING_OFFSETS_KEY,
    MAX_LYRICS_OFFSET_RECORDS,
    effective_lyrics_position_ms,
    lyrics_offset_for_settings,
    normalize_lyrics_offset_ms,
    normalize_lyrics_timing_offsets,
    update_lyrics_timing_offsets,
)
from app.ui.immersive_appearance import (
    ImmersiveAppearanceConfig,
    ImmersiveAppearanceDialog,
)
from app.ui.main_window import LyricsView, MainWindow


class FakePlayer:
    def __init__(self, position: int) -> None:
        self.current_position = int(position)

    def position(self) -> int:
        return self.current_position


class FakeImmersiveWindow:
    def __init__(self) -> None:
        self.positions: list[int] = []
        self.track_updates: list[tuple[str, int]] = []

    def update_position(
        self,
        position: int,
        _lyrics,
        _track_identity: str = "",
    ) -> None:
        self.positions.append(int(position))

    def update_track_timing(self, identity: str, offset_ms: int) -> None:
        self.track_updates.append((str(identity), int(offset_ms)))


class TimingHarness:
    get_lyrics_offset_ms = MainWindow.get_lyrics_offset_ms
    effective_lyrics_position_ms = MainWindow.effective_lyrics_position_ms
    set_lyrics_offset = MainWindow.set_lyrics_offset
    refresh_current_lyrics_position = MainWindow.refresh_current_lyrics_position

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.settings: dict = {}
        self.identity = ""
        self.current_media_item: MediaItem | None = None
        self.current_song_path = ""
        self.displayed_lyrics_song_path = ""
        self.displayed_lyrics_track_key = ""
        self.media_player = FakePlayer(750)
        self.current_lyrics = [
            (0, "第一行"),
            (1000, "Second line"),
            (2000, "翻译歌词"),
        ]
        self.lyrics_view = LyricsView()
        self.full_lyrics_view = LyricsView()
        self.lyrics_view.set_lyrics(self.current_lyrics)
        self.full_lyrics_view.set_lyrics(self.current_lyrics)
        self.immersive_lyrics_window = FakeImmersiveWindow()
        self.floating_sync_count = 0

    def get_hush_settings(self) -> dict:
        return deepcopy(self.settings)

    def save_hush_settings(self, updates: dict, *, immediate: bool = False) -> bool:
        _ = immediate
        before = deepcopy(self.settings)
        self.settings.update(deepcopy(updates))
        return before != self.settings

    def current_track_identity(self) -> str:
        return self.identity

    @staticmethod
    def normalize_song_path(value: str) -> str:
        return str(value or "").replace("/", "\\").casefold()

    def sync_floating_lyrics(self) -> None:
        self.floating_sync_count += 1

    def select_local(self, path: str) -> str:
        item = MediaItem.from_local({"path": path, "title": "Local"})
        self.identity = item.stable_identity
        self.current_media_item = item
        self.current_song_path = path
        self.displayed_lyrics_song_path = path
        self.displayed_lyrics_track_key = ""
        return self.identity

    def select_online(self) -> str:
        item = MediaItem.from_online(
            {
                "sourceId": "fixture",
                "id": "online-track",
                "title": "Online",
                "artist": "Fixture",
            }
        )
        self.identity = item.stable_identity
        self.current_media_item = item
        self.current_song_path = ""
        self.displayed_lyrics_song_path = ""
        self.displayed_lyrics_track_key = item.stable_identity
        return self.identity


def normalization_checks() -> None:
    assert normalize_lyrics_offset_ms(450) == 500
    assert normalize_lyrics_offset_ms(-550) == -600
    assert normalize_lyrics_offset_ms(50_000) == 10_000
    assert normalize_lyrics_offset_ms(-50_000) == -10_000
    assert normalize_lyrics_offset_ms(True) == 0
    assert normalize_lyrics_offset_ms("bad") == 0
    assert normalize_lyrics_offset_ms(float("nan")) == 0
    assert effective_lyrics_position_ms(1500, 500) == 2000
    assert effective_lyrics_position_ms(1500, -500) == 1000

    invalid = normalize_lyrics_timing_offsets(
        {"": 500, "bad": "no", "too-high": 99_000, "zero": 0}
    )
    assert invalid == {"too-high": 10_000}

    records = {f"track-{index}": 100 for index in range(MAX_LYRICS_OFFSET_RECORDS + 3)}
    bounded = normalize_lyrics_timing_offsets(records)
    assert len(bounded) == MAX_LYRICS_OFFSET_RECORDS
    assert "track-0" not in bounded
    assert f"track-{MAX_LYRICS_OFFSET_RECORDS + 2}" in bounded


def per_track_checks(app: QApplication) -> None:
    owner = TimingHarness(app)
    local_identity = owner.select_local("C:/Music/local-fixture.flac")
    original_player_position = owner.media_player.position()
    assert owner.set_lyrics_offset(local_identity, 500)
    assert owner.media_player.position() == original_player_position
    assert owner.settings[LYRICS_TIMING_OFFSETS_KEY][local_identity] == 500
    assert owner.lyrics_view.current_index == 1
    assert owner.full_lyrics_view.current_index == 1
    assert owner.immersive_lyrics_window.positions[-1] == 1250

    online_identity = owner.select_online()
    owner.media_player.current_position = 1500
    owner.lyrics_view.set_lyrics(owner.current_lyrics)
    owner.full_lyrics_view.set_lyrics(owner.current_lyrics)
    assert owner.get_lyrics_offset_ms() == 0
    assert owner.set_lyrics_offset(online_identity, -500)
    assert owner.media_player.position() == 1500
    assert owner.lyrics_view.current_index == 1
    assert owner.immersive_lyrics_window.positions[-1] == 1000
    assert owner.settings[LYRICS_TIMING_OFFSETS_KEY] == {
        local_identity: 500,
        online_identity: -500,
    }

    snapshot = deepcopy(owner.settings)
    assert lyrics_offset_for_settings(snapshot, local_identity) == 500
    assert lyrics_offset_for_settings(snapshot, online_identity) == -500
    assert not owner.set_lyrics_offset(local_identity, 900)
    assert owner.settings == snapshot

    assert owner.set_lyrics_offset(online_identity, 0)
    assert online_identity not in owner.settings[LYRICS_TIMING_OFFSETS_KEY]
    assert owner.settings[LYRICS_TIMING_OFFSETS_KEY] == {local_identity: 500}

    owner.select_local("C:/Music/local-fixture.flac")
    assert owner.get_lyrics_offset_ms() == 500
    owner.current_lyrics = []
    paused_position = owner.media_player.position()
    assert owner.set_lyrics_offset(local_identity, -1000)
    assert owner.media_player.position() == paused_position

    restarted_settings = deepcopy(owner.settings)
    assert lyrics_offset_for_settings(restarted_settings, local_identity) == -1000
    removed = update_lyrics_timing_offsets(
        restarted_settings[LYRICS_TIMING_OFFSETS_KEY], local_identity, 0
    )
    assert local_identity not in removed

    owner.lyrics_view.deleteLater()
    owner.full_lyrics_view.deleteLater()
    app.processEvents()


def dialog_checks(app: QApplication) -> None:
    config = ImmersiveAppearanceConfig.defaults()
    dialog = ImmersiveAppearanceDialog(
        config,
        track_identity="local:fixture",
        lyrics_offset_ms=500,
    )
    config_changes: list[ImmersiveAppearanceConfig] = []
    offset_changes: list[tuple[str, int]] = []
    dialog.configChanged.connect(config_changes.append)
    dialog.lyricsOffsetChanged.connect(
        lambda identity, offset: offset_changes.append((identity, offset))
    )
    dialog.offset_minus_button.click()
    assert offset_changes[-1] == ("local:fixture", 0)
    dialog.offset_plus_button.click()
    assert offset_changes[-1] == ("local:fixture", 500)
    dialog.offset_slider.setValue(-100)
    assert offset_changes[-1] == ("local:fixture", -10_000)
    dialog.offset_zero_button.click()
    assert offset_changes[-1] == ("local:fixture", 0)
    assert dialog.config == config
    assert config_changes == []

    dialog.set_track_timing("online:fixture", 1200)
    assert dialog.offset_slider.value() == 12
    assert dialog.offset_value.text() == "+1.2 秒"
    dialog.set_track_timing("", 0)
    assert not dialog.offset_slider.isEnabled()
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    normalization_checks()
    per_track_checks(app)
    dialog_checks(app)
    print("lyrics timing offset smoke: OK")


if __name__ == "__main__":
    main()

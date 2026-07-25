"""Deterministic mock songs that exercise list rendering states."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.ui_v2.models.track import Track


TITLES = (
    "雾中的海岸",
    "After the Rain",
    "夜航 Night Flight",
    "一封写给很久以后自己的信，关于那年夏天没有说完的故事",
    "Glass Cities",
    "纸月亮 Paper Moon",
    "Signal From Home",
    "慢慢靠近 Slowly Closer",
)
ARTISTS = (
    "林澈",
    "North Window",
    "陈默与 The Quiet Hours",
    "A Very Long Artist Name for Elision Coverage",
    "白昼电台",
    "Kite Harbor",
) + tuple(f"Mock Artist {index:02d}" for index in range(1, 59))
ALBUMS = (
    "冬日信箱",
    "Notes for an Unnamed City",
    "零点之后的蓝色房间",
    "A Deliberately Long Album Title for Responsive Layout Validation",
    "海风与旧磁带",
) + tuple(f"Mock Album Collection {index:02d}" for index in range(1, 92))
ONLINE_SOURCES = (
    ("open-catalog", "Open Catalog"),
    ("radio-archive", "Radio Archive"),
    ("creator-library", "Creator Library"),
)


def create_mock_tracks(count: int = 1000) -> list[Track]:
    """Create stable tracks without querying a real library or network service."""
    start = datetime(2024, 1, 1, 9, 30)
    tracks: list[Track] = []
    for index in range(max(0, count)):
        is_online = index % 4 != 0
        source_id, source_name = (
            ONLINE_SOURCES[index % len(ONLINE_SOURCES)]
            if is_online
            else ("local-library", "本地音乐")
        )
        duration_ms: int | None
        if index % 29 == 0:
            duration_ms = None
        elif index % 53 == 0:
            duration_ms = 3_721_000 + index * 10
        else:
            duration_ms = 150_000 + (index * 18_731) % 280_000
        title = TITLES[index % len(TITLES)]
        if index % 17 == 0:
            title = f"{title} ({index // 17 + 1})"
        artist = "" if index % 97 == 0 else ARTISTS[(index * 5) % len(ARTISTS)]
        album = "" if index % 89 == 0 else ALBUMS[index % len(ALBUMS)]
        tracks.append(
            Track(
                id=f"mock-{index:04d}",
                title=title,
                artist=artist,
                album=album,
                duration_ms=duration_ms,
                source_id=source_id,
                source_name=source_name,
                source_type="online" if is_online else "local",
                added_at=start + timedelta(hours=index * 7),
                is_favorite=index % 9 == 0,
                is_missing=index % 37 == 0,
                is_loading=index % 41 == 0,
                artwork_path=None,
                stable_identity=f"{source_id}:{index % 120}",
            )
        )
    return tracks

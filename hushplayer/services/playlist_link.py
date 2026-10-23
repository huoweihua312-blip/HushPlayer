"""Fetch playlists from sharing links (cross-platform import, step 1 of 3).

Only services with a documented, anonymous read endpoint are fetched for real.
Apple Music, QQ Music, Kugou and Kuwo all require a login cookie or a developer
token for playlist contents; those links are *recognised* so the UI can explain
what to do instead, but they never pretend to have imported anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable

import requests

from .playlist_import import PlaylistEntry

__all__ = [
    "PLATFORM_LABELS",
    "LinkPlaylist",
    "PlaylistLinkError",
    "detect_platform",
    "extract_playlist_id",
    "fetch_link",
]

PLATFORM_LABELS = {
    "netease": "网易云音乐",
    "qq": "QQ 音乐",
    "kugou": "酷狗音乐",
    "kuwo": "酷我音乐",
    "apple": "Apple Music",
    "unknown": "未知平台",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_NETEASE_TIMEOUT = 15


class PlaylistLinkError(RuntimeError):
    """Raised when a supported platform cannot be read (network/shape/limit)."""


@dataclass
class LinkPlaylist:
    platform: str
    supported: bool
    name: str = ""
    entries: list[PlaylistEntry] = field(default_factory=list)
    playlist_id: str = ""
    reason: str = ""

    @property
    def platform_label(self) -> str:
        return PLATFORM_LABELS.get(self.platform, self.platform)


# ------------------------------------------------------------------ detection
def detect_platform(url: str) -> str:
    text = (url or "").strip().lower()
    if "music.163.com" in text or "163cn.tv" in text or "y.music.163" in text:
        return "netease"
    if "y.qq.com" in text or "c.y.qq.com" in text or "qq.com/n/ryqq" in text:
        return "qq"
    if "kugou.com" in text:
        return "kugou"
    if "kuwo.cn" in text:
        return "kuwo"
    if "music.apple.com" in text or "itunes.apple.com" in text:
        return "apple"
    return "unknown"


def extract_playlist_id(url: str, platform: str | None = None) -> str:
    text = (url or "").strip()
    platform = platform or detect_platform(text)
    patterns = {
        "netease": (r"[?&#/]id=(\d{4,})", r"/playlist/(\d{4,})", r"\b(\d{6,})\b"),
        "qq": (r"/playlist/(\d{4,})", r"[?&]id=(\d{4,})"),
        "kugou": (r"/special/single/(\d{3,})", r"/special/(\d{3,})", r"\b(\d{4,})\b"),
        "kuwo": (r"/playlist_detail/(\d{3,})", r"\b(\d{6,})\b"),
        "apple": (r"/playlist/[^/]+/(pl\.[A-Za-z0-9._-]+)", r"(pl\.[A-Za-z0-9._-]+)"),
    }
    for pattern in patterns.get(platform, ()):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


# --------------------------------------------------------------------- fetch
def fetch_link(url: str, *, timeout: float = _NETEASE_TIMEOUT) -> LinkPlaylist:
    platform = detect_platform(url)
    playlist_id = extract_playlist_id(url, platform)
    if platform == "unknown":
        raise PlaylistLinkError("无法识别这个链接是哪个平台，请粘贴完整的歌单分享链接。")
    if platform == "netease":
        return _fetch_netease(playlist_id, timeout=timeout)
    if platform == "apple":
        return LinkPlaylist(
            platform=platform,
            supported=False,
            playlist_id=playlist_id,
            reason=(
                "Apple Music 的歌单内容只能通过 Apple Music API 读取，需要开发者令牌，"
                "本程序不内置任何授权凭据。\n"
                "可用替代方式：在 Mac 的「音乐」里选择 文件 → 资料库 → 导出资料库（Library.xml），"
                "或在 Windows 上用第三方工具把歌单导出为 .m3u8 / .csv 后再导入。"
            ),
        )
    if platform == "qq":
        return LinkPlaylist(
            platform=platform,
            supported=False,
            playlist_id=playlist_id,
            reason=(
                "QQ 音乐的歌单接口需要登录 Cookie（属于访问控制），本项目不绕过。\n"
                "可用替代方式：在 QQ 音乐里把歌单导出为 .m3u8 / .csv，或粘贴歌曲列表（歌手 - 歌名）用文本导入。"
            ),
        )
    if platform == "kugou":
        return LinkPlaylist(
            platform=platform,
            supported=False,
            playlist_id=playlist_id,
            reason=(
                "酷狗歌单详情接口带有签名校验，需要登录后才能读取，本项目不绕过。\n"
                "可用替代方式：把歌单导出为文件，或粘贴「歌手 - 歌名」列表导入。"
            ),
        )
    return LinkPlaylist(
        platform=platform,
        supported=False,
        playlist_id=playlist_id,
        reason=(
            "酷我歌单接口需要登录 Cookie，本项目不绕过。\n"
            "可用替代方式：把歌单导出为文件，或粘贴「歌手 - 歌名」列表导入。"
        ),
    )


def _netease_headers() -> dict[str, str]:
    return {"User-Agent": _USER_AGENT, "Referer": "https://music.163.com/"}


def _fetch_netease(playlist_id: str, *, timeout: float) -> LinkPlaylist:
    if not playlist_id:
        raise PlaylistLinkError("没有从链接里找到网易云歌单 ID。")
    try:
        response = requests.get(
            "https://music.163.com/api/v6/playlist/detail",
            params={"id": playlist_id, "n": 1000, "s": 0},
            headers=_netease_headers(),
            timeout=timeout,
        )
    except requests.RequestException as exc:  # pragma: no cover - network only
        raise PlaylistLinkError(f"网络请求失败：{exc}") from exc
    if response.status_code != 200:
        raise PlaylistLinkError(f"网易云返回 HTTP {response.status_code}。")
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlaylistLinkError("网易云返回的不是 JSON，接口可能已变化。") from exc
    playlist = payload.get("playlist") or {}
    if not playlist:
        raise PlaylistLinkError("这个歌单不存在，或者作者已将其设为私密。")

    name = str(playlist.get("name") or "").strip() or f"网易云歌单 {playlist_id}"
    raw_tracks: list[dict] = list(playlist.get("tracks") or [])
    track_ids = [int(item.get("id")) for item in (playlist.get("trackIds") or []) if item.get("id")]

    by_id = {int(track.get("id")): track for track in raw_tracks if track.get("id")}
    missing = [track_id for track_id in track_ids if track_id not in by_id]
    if missing:
        by_id.update(_netease_song_details(missing, timeout=timeout))

    ordered_ids: Iterable[int] = track_ids or list(by_id)
    entries: list[PlaylistEntry] = []
    for track_id in ordered_ids:
        track = by_id.get(int(track_id))
        if not track:
            continue
        entries.append(_netease_entry(track))

    if not entries:
        raise PlaylistLinkError("这个歌单里没有可读取的歌曲（可能全部为无版权/下架内容）。")
    return LinkPlaylist(
        platform="netease",
        supported=True,
        name=name,
        entries=entries,
        playlist_id=playlist_id,
    )


def _netease_song_details(ids: list[int], *, timeout: float) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        try:
            response = requests.get(
                "https://music.163.com/api/song/detail",
                params={"ids": json.dumps(batch)},
                headers=_netease_headers(),
                timeout=timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError):
            continue
        for song in payload.get("songs") or []:
            if song.get("id"):
                result[int(song["id"])] = song
    return result


def _netease_entry(track: dict) -> PlaylistEntry:
    artists = track.get("ar") or track.get("artists") or []
    artist = " / ".join(
        str(item.get("name") or "").strip() for item in artists if item.get("name")
    )
    album = track.get("al") or track.get("album") or {}
    duration = track.get("dt") or track.get("duration") or 0
    return PlaylistEntry(
        title=str(track.get("name") or "").strip(),
        artist=artist,
        album=str(album.get("name") or "").strip(),
        duration_ms=int(duration or 0),
    )

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class RemoteTrackStoreError(RuntimeError):
    pass


class RemoteTrackStore:
    VERSION = 1
    _TRANSIENT_URL_KEYS = {
        "url",
        "playurl",
        "playbackurl",
        "downloadurl",
        "mediaurl",
        "streamurl",
        "audiourl",
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load_tracks(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}

        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as error:
            raise RemoteTrackStoreError(f"读取远程歌曲记录失败：{error}") from error

        if not isinstance(document, dict) or not isinstance(document.get("tracks"), dict):
            raise RemoteTrackStoreError("远程歌曲记录必须包含 tracks 对象")

        tracks: dict[str, dict] = {}
        for stable_id, record in document["tracks"].items():
            if isinstance(stable_id, str) and stable_id and isinstance(record, dict):
                tracks[stable_id] = dict(record)
        return tracks

    def save_tracks(self, tracks: dict[str, dict]) -> None:
        if not isinstance(tracks, dict):
            raise RemoteTrackStoreError("远程歌曲记录必须是对象")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        document = {
            "version": self.VERSION,
            "tracks": tracks,
        }
        try:
            temporary_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except Exception as error:
            raise RemoteTrackStoreError(f"保存远程歌曲记录失败：{error}") from error

    @classmethod
    def stable_id_for_track(cls, track: dict) -> str:
        source_id = str(track.get("source_id") or track.get("sourceId") or "").strip()
        remote_id = str(
            track.get("remote_id")
            or track.get("id")
            or track.get("songmid")
            or ""
        ).strip()
        if remote_id:
            identity = remote_id
        else:
            identity = "\0".join(
                str(track.get(field) or "").strip().casefold()
                for field in ("title", "artist", "album")
            )
        digest = hashlib.sha256(f"{source_id}\0{identity}".encode("utf-8")).hexdigest()
        return f"remote_{digest[:24]}"

    @classmethod
    def build_record(
        cls,
        track: dict,
        source_url: str = "",
        existing: dict | None = None,
    ) -> tuple[str, dict]:
        source_id = str(
            track.get("source_id")
            or track.get("sourceId")
            or (existing or {}).get("source_id")
            or ""
        ).strip()
        if not source_id:
            raise RemoteTrackStoreError("远程歌曲缺少已注册的来源 ID")

        identity_track = dict(track)
        identity_track["sourceId"] = source_id
        stable_id = cls.stable_id_for_track(identity_track)
        previous = dict(existing or {})
        now = int(time.time())
        remote_id = str(
            track.get("remote_id")
            or track.get("id")
            or track.get("songmid")
            or previous.get("remote_id")
            or ""
        ).strip()
        raw = track.get("raw")
        sanitized_raw = cls._sanitize_raw(raw if isinstance(raw, (dict, list)) else {})
        try:
            duration = max(0, int(track.get("duration") or previous.get("duration") or 0))
        except (TypeError, ValueError):
            duration = 0

        record = {
            "remote_id": remote_id,
            "source_id": source_id,
            "source_url": str(
                source_url
                or track.get("source_url")
                or track.get("sourceUrl")
                or previous.get("source_url")
                or ""
            ).strip(),
            "title": str(track.get("title") or previous.get("title") or "未知歌曲"),
            "artist": str(track.get("artist") or previous.get("artist") or "未知艺术家"),
            "album": str(track.get("album") or previous.get("album") or "未知专辑"),
            "artwork": str(track.get("artwork") or previous.get("artwork") or ""),
            "duration": duration,
            "songmid": str(track.get("songmid") or previous.get("songmid") or ""),
            "raw": sanitized_raw,
            "local_path": str(previous.get("local_path") or ""),
            "downloaded_at": cls._safe_nonnegative_int(previous.get("downloaded_at")),
            "added_at": cls._safe_nonnegative_int(previous.get("added_at"), now),
        }
        return stable_id, record

    @classmethod
    def to_online_track(cls, stable_id: str, record: dict) -> dict:
        raw = record.get("raw")
        return {
            "remoteStableId": stable_id,
            "sourceId": str(record.get("source_id") or ""),
            "sourceUrl": str(record.get("source_url") or ""),
            "id": str(record.get("remote_id") or ""),
            "songmid": str(record.get("songmid") or ""),
            "title": str(record.get("title") or "未知歌曲"),
            "artist": str(record.get("artist") or "未知艺术家"),
            "album": str(record.get("album") or "未知专辑"),
            "artwork": str(record.get("artwork") or ""),
            "duration": cls._safe_nonnegative_int(record.get("duration")),
            "raw": dict(raw) if isinstance(raw, dict) else {},
        }

    @classmethod
    def to_song_data(
        cls,
        stable_id: str,
        record: dict,
        source_available: bool,
        resolving: bool = False,
    ) -> dict:
        local_path = str(record.get("local_path") or "").strip()
        local_exists = bool(local_path and Path(local_path).is_file())
        if local_exists:
            status = "已下载"
        elif resolving:
            status = "正在解析"
        elif source_available:
            status = "在线"
        else:
            status = "来源不可用"
        return {
            "recordKind": "remote",
            "remoteStableId": stable_id,
            "title": str(record.get("title") or "未知歌曲"),
            "artist": str(record.get("artist") or "未知艺术家"),
            "album": str(record.get("album") or "未知专辑"),
            "duration": cls._safe_nonnegative_int(record.get("duration")),
            "added_at": cls._safe_nonnegative_int(record.get("added_at")),
            "path": str(Path(local_path).resolve()) if local_exists else "",
            "onlineStatus": status,
            "demo": False,
        }

    @classmethod
    def _sanitize_raw(cls, value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                normalized_key = str(key).replace("_", "").replace("-", "").casefold()
                if normalized_key in cls._TRANSIENT_URL_KEYS:
                    continue
                cleaned[str(key)] = cls._sanitize_raw(item)
            return cleaned
        if isinstance(value, list):
            return [cls._sanitize_raw(item) for item in value[:200]]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _safe_nonnegative_int(value, default: int = 0) -> int:
        try:
            return max(0, int(value or default))
        except (TypeError, ValueError):
            return max(0, int(default))

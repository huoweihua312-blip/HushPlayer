"""Worker-side, read-only cover extraction into disposable image thumbnails."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import Picture
from mutagen.id3 import ID3
from PySide6.QtCore import QBuffer, QIODevice, QSaveFile, QSize, Qt
from PySide6.QtGui import QImage, QImageReader


MAX_ARTWORK_BYTES = 12 * 1024 * 1024
MAX_ARTWORK_PIXELS = 32 * 1024 * 1024
THUMBNAIL_SIZE = 768


class LocalArtworkResolver:
    """Used only by the existing snapshot worker, never by a paint callback."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir) / "local"
        self._resolved: dict[str, str | None] = {}

    def resolve(self, record: dict) -> str | None:
        audio = Path(str(record.get("path") or ""))
        for field in ("artwork_path", "local_cover_path", "cover_path"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            result = self._file_cover(Path(value))
            if result:
                return result

        audio_key = self._file_key(audio)
        if audio_key:
            key = "embedded:" + audio_key
            cached = self._cached_path(key)
            if cached:
                return cached
            if key not in self._resolved:
                self._resolved[key] = self._embedded_cover(audio, key)
            if self._resolved[key]:
                return self._resolved[key]

        # Only conventional album-cover names, never an arbitrary directory image.
        for name in ("cover", "folder", "front"):
            for extension in ("jpg", "jpeg", "png"):
                result = self._file_cover(audio.parent / f"{name}.{extension}")
                if result:
                    return result
        return None

    @staticmethod
    def _file_key(path: Path) -> str:
        try:
            stat = path.stat()
            if not path.is_file():
                return ""
            return f"{path.absolute()}:{stat.st_mtime_ns}:{stat.st_size}"
        except (OSError, ValueError):
            return ""

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.png"

    def _cached_path(self, key: str) -> str | None:
        path = self._cache_path(key)
        if self._file_key(path) and not self._read_image(path=path).isNull():
            return str(path)
        return None

    def _file_cover(self, path: Path) -> str | None:
        key = self._file_key(path)
        if not key:
            return None
        if key not in self._resolved:
            cached = self._cached_path(key)
            image = QImage() if cached else self._read_image(path=path)
            self._resolved[key] = cached or self._save(key, image)
            # A read-only cache must not hide an otherwise valid sidecar image.
            if not self._resolved[key] and not image.isNull():
                self._resolved[key] = str(path)
        return self._resolved[key]

    def _embedded_cover(self, path: Path, key: str) -> str | None:
        try:
            # ID3 does not require decoding an MP3 audio stream.
            if path.suffix.casefold() == ".mp3":
                tags = ID3(path)
                pictures = tags.getall("APIC")
                candidates = [
                    picture.data
                    for picture in sorted(pictures, key=lambda picture: picture.type != 3)
                ]
            else:
                audio = MutagenFile(path)
                tags = getattr(audio, "tags", None)
                pictures = list(getattr(audio, "pictures", ()) or ())
                if tags is not None and hasattr(tags, "getall"):
                    pictures.extend(tags.getall("APIC"))
                if tags is not None:
                    for raw in tags.get("metadata_block_picture", ()):
                        try:
                            if len(raw) <= MAX_ARTWORK_BYTES * 2:
                                pictures.append(Picture(base64.b64decode(raw)))
                        except (ValueError, TypeError):
                            continue
                candidates = [
                    picture.data
                    for picture in sorted(pictures, key=lambda picture: picture.type != 3)
                ]
                if tags is not None:
                    candidates.extend(tags.get("covr", ()))
            for data in candidates:
                image = self._read_image(data=bytes(data))
                if not image.isNull():
                    return self._save(key, image)
        except Exception:
            # Malformed optional metadata must not prevent the library loading.
            return None
        return None

    @staticmethod
    def _read_image(*, path: Path | None = None, data: bytes = b"") -> QImage:
        buffer = QBuffer()
        try:
            if path is not None:
                if path.stat().st_size > MAX_ARTWORK_BYTES:
                    return QImage()
                reader = QImageReader(str(path))
            else:
                if not data or len(data) > MAX_ARTWORK_BYTES:
                    return QImage()
                buffer.setData(data)
                buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                reader = QImageReader(buffer)
            size = reader.size()
            if not size.isValid() or size.width() * size.height() > MAX_ARTWORK_PIXELS:
                return QImage()
            if max(size.width(), size.height()) > THUMBNAIL_SIZE:
                reader.setScaledSize(
                    size.scaled(
                        QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE),
                        Qt.AspectRatioMode.KeepAspectRatio,
                    )
                )
            reader.setAutoTransform(True)
            return reader.read()
        except (OSError, ValueError):
            return QImage()

    def _save(self, key: str, image: QImage) -> str | None:
        if image.isNull():
            return None
        target = self._cache_path(key)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            output = QSaveFile(str(target))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                return None
            if not image.save(output, "PNG"):
                output.cancelWriting()
                return None
            return str(target) if output.commit() else None
        except OSError:
            return None

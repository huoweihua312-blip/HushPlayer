from __future__ import annotations

import json
import re
import time

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.models.media_item import MediaItem
from app.services.lyrics_cache import LyricsCache
from app.services.online_source_client import OnlineSourceClient


class OnlineLyricsService(QObject):
    """Load online lyrics without delaying playback or accepting stale results."""

    statusChanged = Signal(int, str, str)
    lyricsReady = Signal(int, str, dict)

    LRC_PATTERN = re.compile(r"\[\d{1,2}:\d{1,2}(?:[.:]\d{1,3})?\]")

    def __init__(
        self,
        client: OnlineSourceClient,
        cache: LyricsCache,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.cache = cache
        self.network = QNetworkAccessManager(self)
        self._generation = 0
        self._provider_request = 0
        self._provider_context: tuple[int, MediaItem] | None = None
        self._network_reply: QNetworkReply | None = None
        self._network_context: tuple[int, MediaItem] | None = None
        self.client.lyricFinished.connect(self._on_provider_lyrics)
        self.client.requestFailed.connect(self._on_provider_failed)

    @property
    def generation(self) -> int:
        return self._generation

    def request_lyrics(self, value: MediaItem | dict) -> int:
        item = MediaItem.from_mapping(value)
        self.cancel()
        self._generation += 1
        generation = self._generation
        track_key = item.stable_identity
        self.statusChanged.emit(generation, track_key, "正在获取歌词")

        cached = self.cache.get_memory(item)
        if cached is not None:
            payload = dict(cached)
            payload["source"] = f"内存缓存/{payload.get('source') or '未知'}"
            self.lyricsReady.emit(generation, track_key, payload)
            return generation

        cached = self.cache.get_persistent(item)
        if cached is not None:
            payload = dict(cached)
            payload["source"] = f"本地缓存/{payload.get('source') or '未知'}"
            self.lyricsReady.emit(generation, track_key, payload)
            return generation

        embedded = self._extract_lyrics(item.lyrics)
        if embedded:
            payload = self._payload(embedded, "播放信息")
            self.cache.put(item, payload)
            self.lyricsReady.emit(generation, track_key, payload)
            return generation

        if item.source_id and item.source_id != "local":
            self._provider_request = self.client.get_lyric(
                item.source_id,
                item.to_provider_payload(),
                timeout_ms=10000,
            )
            self._provider_context = (generation, item)
            self.statusChanged.emit(generation, track_key, "正在向歌曲来源请求歌词")
        elif item.media_type == "online":
            self._finish_not_found(generation, item, "当前来源没有歌词接口")
        else:
            self._start_lrclib(generation, item)
        return generation

    def cancel(self) -> None:
        provider_request = self._provider_request
        self._provider_request = 0
        self._provider_context = None
        if provider_request:
            self.client.cancel_request(provider_request)
        network_reply = self._network_reply
        self._network_reply = None
        self._network_context = None
        if network_reply is not None:
            network_reply.abort()
            network_reply.deleteLater()

    def _on_provider_lyrics(self, request_id: int, source_id: str, result: dict) -> None:
        if request_id != self._provider_request or self._provider_context is None:
            return
        generation, item = self._provider_context
        self._provider_request = 0
        self._provider_context = None
        if generation != self._generation or item.source_id != source_id:
            return
        text = self._extract_result_text(result)
        if text:
            payload = self._payload(text, item.source_name or "歌曲来源")
            self.cache.put(item, payload)
            self.lyricsReady.emit(generation, item.stable_identity, payload)
            return
        if item.media_type == "online":
            if isinstance(result, dict) and result.get("available") is False:
                self._finish_not_found(generation, item, "歌曲来源未提供歌词")
            else:
                self._finish_failed(generation, item, "歌曲来源返回的歌词格式异常")
            return
        self._start_lrclib(generation, item)

    def _on_provider_failed(self, request_id: int, action: str, message: str) -> None:
        if action != "getLyric" or request_id != self._provider_request:
            return
        context = self._provider_context
        self._provider_request = 0
        self._provider_context = None
        if context is None:
            return
        generation, item = context
        if generation == self._generation:
            if item.media_type == "online":
                self._finish_failed(generation, item, message or "歌词获取失败")
            else:
                self._start_lrclib(generation, item)

    def _start_lrclib(self, generation: int, item: MediaItem) -> None:
        if generation != self._generation:
            return
        if not item.title or item.title == "未知歌曲":
            self._finish_not_found(generation, item, "缺少歌曲名称")
            return
        query = QUrlQuery()
        query.addQueryItem("track_name", item.title)
        if item.artist and item.artist != "未知艺术家":
            query.addQueryItem("artist_name", item.artist)
        if item.album and item.album != "未知专辑":
            query.addQueryItem("album_name", item.album)
        url = QUrl("https://lrclib.net/api/search")
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"HushPlayer/0.8 (lyrics client)")
        request.setRawHeader(b"Accept", b"application/json")
        reply = self.network.get(request)
        reply.finished.connect(lambda current=reply: self._on_lrclib_finished(current))
        self._network_reply = reply
        self._network_context = (generation, item)
        self.statusChanged.emit(generation, item.stable_identity, "正在使用联网歌词匹配")

    def _on_lrclib_finished(self, reply: QNetworkReply) -> None:
        context = self._network_context if reply is self._network_reply else None
        if reply is self._network_reply:
            self._network_reply = None
            self._network_context = None
        if context is None:
            reply.deleteLater()
            return
        generation, item = context
        if generation != self._generation:
            reply.deleteLater()
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            self._finish_not_found(generation, item, "歌词加载失败", cache=False)
            return
        try:
            results = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except Exception:
            results = []
        reply.deleteLater()
        best = self._best_lrclib_result(item, results)
        if best is None:
            self._finish_not_found(generation, item, "暂无歌词")
            return
        text = str(best.get("syncedLyrics") or best.get("plainLyrics") or "").strip()
        if not text:
            self._finish_not_found(generation, item, "暂无歌词")
            return
        payload = self._payload(text, "LRCLIB")
        self.cache.put(item, payload)
        self.lyricsReady.emit(generation, item.stable_identity, payload)

    def _finish_not_found(
        self,
        generation: int,
        item: MediaItem,
        message: str,
        cache: bool = True,
    ) -> None:
        payload = {
            "text": "",
            "type": "none",
            "source": message,
            "fetched_at": int(time.time()),
            "not_found": True,
        }
        if cache:
            self.cache.put(item, payload)
        self.lyricsReady.emit(generation, item.stable_identity, payload)

    def _finish_failed(self, generation: int, item: MediaItem, message: str) -> None:
        payload = {
            "text": "",
            "type": "error",
            "source": str(message or "歌词获取失败"),
            "fetched_at": int(time.time()),
            "not_found": False,
            "error": True,
        }
        self.statusChanged.emit(generation, item.stable_identity, "歌词获取失败")
        self.lyricsReady.emit(generation, item.stable_identity, payload)

    @classmethod
    def _payload(cls, text: str, source: str) -> dict:
        normalized = str(text or "").strip()
        return {
            "text": normalized,
            "type": "lrc" if cls.LRC_PATTERN.search(normalized) else "plain",
            "source": source,
            "fetched_at": int(time.time()),
            "not_found": not bool(normalized),
        }

    @classmethod
    def _extract_lyrics(cls, value) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            lines = []
            for item in value:
                if isinstance(item, dict):
                    item = (
                        item.get("text")
                        or item.get("words")
                        or item.get("lyric")
                        or item.get("content")
                    )
                text = cls._extract_lyrics(item)
                if text:
                    lines.append(text)
            return "\n".join(lines).strip()
        return ""

    @classmethod
    def _extract_result_text(cls, result: dict) -> str:
        if not isinstance(result, dict):
            return ""
        for key in (
            "rawLrc",
            "syncedLyrics",
            "lrc",
            "lyric",
            "lyrics",
            "plainLyrics",
            "rawLrcTxt",
            "text",
            "content",
            "lines",
        ):
            text = cls._extract_lyrics(result.get(key))
            if text:
                return text
            nested = result.get(key)
            if isinstance(nested, dict):
                text = cls._extract_result_text(nested)
                if text:
                    return text
        for key in ("data", "raw", "result"):
            nested = result.get(key)
            if isinstance(nested, dict):
                text = cls._extract_result_text(nested)
                if text:
                    return text
        return ""

    @classmethod
    def _best_lrclib_result(cls, item: MediaItem, results) -> dict | None:
        if not isinstance(results, list):
            return None
        best: dict | None = None
        best_score = -1
        target_title = cls._normalize(item.title)
        target_artist = cls._normalize(item.artist)
        for result in results:
            if not isinstance(result, dict):
                continue
            if not result.get("syncedLyrics") and not result.get("plainLyrics"):
                continue
            score = 0
            result_title = cls._normalize(result.get("trackName"))
            result_artist = cls._normalize(result.get("artistName"))
            if target_title and target_title == result_title:
                score += 80
            elif target_title and (target_title in result_title or result_title in target_title):
                score += 35
            if target_artist and target_artist == result_artist:
                score += 50
            elif target_artist and (target_artist in result_artist or result_artist in target_artist):
                score += 20
            try:
                duration = int(float(result.get("duration") or 0))
            except (TypeError, ValueError):
                duration = 0
            if item.duration and duration:
                difference = abs(item.duration - duration)
                score += 25 if difference <= 3 else 10 if difference <= 8 else 0
            if result.get("syncedLyrics"):
                score += 20
            if score > best_score:
                best = result
                best_score = score
        return best if best_score >= 70 else None

    @staticmethod
    def _normalize(value) -> str:
        return "".join(str(value or "").casefold().split())

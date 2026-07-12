import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0441"


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, content.rstrip() + "\n\n" + marker, 1)


def add_name_to_import_line(text: str, module_line_start: str, name: str) -> str:
    pattern = rf"{re.escape(module_line_start)}([^\n]+)"
    match = re.search(pattern, text)

    if not match:
        raise RuntimeError(f"没有找到导入行：{module_line_start}")

    current_names = [part.strip() for part in match.group(1).split(",") if part.strip()]

    if name in current_names:
        return text

    current_names.append(name)
    current_names = sorted(set(current_names))

    new_line = module_line_start + ", ".join(current_names)
    return text[:match.start()] + new_line + text[match.end():]


def ensure_qtwidgets_name(text: str, name: str) -> str:
    target = f"    {name},\n"

    if target in text:
        return text

    if "from PySide6.QtWidgets import (\n" not in text:
        raise RuntimeError("没有找到 PySide6.QtWidgets 多行导入")

    return text.replace(
        "from PySide6.QtWidgets import (\n",
        f"from PySide6.QtWidgets import (\n    {name},\n",
        1,
    )


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.5" in text:
        print("当前文件看起来已经升级到 v0.4.5 了，不需要重复升级。")
        return

    if "def set_lyrics_status" not in text:
        raise RuntimeError("没有找到歌词状态函数。请先确认已经升级到 v0.4.4.1。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.4.1 (local music player prototype)",
        "HushPlayer/0.4.5 (local music player prototype)",
    )
    text = text.replace(
        "HushPlayer/0.4.4 (local music player prototype)",
        "HushPlayer/0.4.5 (local music player prototype)",
    )

    text = add_name_to_import_line(text, "from PySide6.QtCore import ", "QObject")
    text = add_name_to_import_line(text, "from PySide6.QtCore import ", "QThread")
    text = add_name_to_import_line(text, "from PySide6.QtCore import ", "Signal")
    text = ensure_qtwidgets_name(text, "QApplication")

    if "self.cover_request_id" not in text:
        if "        self.browsing_song_data: dict | None = None\n" in text:
            text = text.replace(
                "        self.browsing_song_data: dict | None = None\n",
                '''        self.browsing_song_data: dict | None = None

        self.cover_request_id = 0
        self.lyrics_request_id = 0
        self.active_cover_request_id = ""
        self.active_lyrics_request_id = ""
        self.cover_threads: list[QThread] = []
        self.lyrics_threads: list[QThread] = []
        self.displayed_lyrics_song_path: str | None = None
''',
                1,
            )
        else:
            text = text.replace(
                "        self.current_song_path: str | None = None\n",
                '''        self.current_song_path: str | None = None
        self.cover_request_id = 0
        self.lyrics_request_id = 0
        self.active_cover_request_id = ""
        self.active_lyrics_request_id = ""
        self.cover_threads: list[QThread] = []
        self.lyrics_threads: list[QThread] = []
        self.displayed_lyrics_song_path: str | None = None
''',
                1,
            )

    if "self.lyrics_cache_dir" not in text:
        text = text.replace(
            '        self.cover_cache_dir = self.project_root / "cache" / "covers"\n',
            '        self.cover_cache_dir = self.project_root / "cache" / "covers"\n'
            '        self.lyrics_cache_dir = self.project_root / "cache" / "lyrics"\n',
            1,
        )

    worker_classes = r'''class CoverSearchWorker(QObject):
    status_changed = Signal(str, str)
    finished = Signal(str, object)

    MISSING_CACHE_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        request_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: str,
        cover_cache_dir: str,
        http_headers: dict,
    ) -> None:
        super().__init__()

        self.request_id = request_id
        self.file_path = file_path
        self.title = title
        self.artist = artist
        self.album = album
        self.cover_cache_dir = Path(cover_cache_dir)
        self.http_headers = dict(http_headers)
        self.last_musicbrainz_request_time = 0.0

    def emit_status(self, message: str) -> None:
        self.status_changed.emit(self.request_id, message)

    def run(self) -> None:
        try:
            result = self.search_cover()
            self.finished.emit(self.request_id, result)
        except Exception as error:
            self.finished.emit(
                self.request_id,
                {
                    "ok": False,
                    "source": "error",
                    "message": str(error),
                    "song_path": self.file_path,
                },
            )

    def search_cover(self) -> dict:
        if not self.file_path:
            return {
                "ok": False,
                "source": "empty",
                "message": "没有歌曲路径",
                "song_path": self.file_path,
            }

        music_path = Path(self.file_path)
        cache_path = self.get_cover_cache_path(music_path)
        missing_path = cache_path.with_suffix(".missing")

        if cache_path.exists():
            self.emit_status("已加载缓存封面")
            return {
                "ok": True,
                "source": "cache",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        if self.is_missing_cache_valid(missing_path):
            self.emit_status("封面缓存记录：上次未找到")
            return {
                "ok": False,
                "source": "missing_cache",
                "message": "近期已经搜索过，未找到封面",
                "song_path": self.file_path,
            }

        self.emit_status("正在读取内嵌封面")
        cover_data = self.extract_album_cover(music_path)

        if cover_data:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(cover_data)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "embedded",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.emit_status("正在查找文件夹封面")
        folder_cover = self.find_folder_cover(music_path)

        if folder_cover:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder_cover, cache_path)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "folder",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.emit_status("正在联网搜索封面")
        online_cover = self.fetch_online_cover(self.title, self.artist, self.album)

        if online_cover:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(online_cover)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "online",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.write_missing_cache(missing_path, "cover not found")
        self.emit_status("未找到封面，已记录缓存")
        return {
            "ok": False,
            "source": "not_found",
            "message": "未找到封面",
            "song_path": self.file_path,
        }

    def get_cover_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.cover_cache_dir / f"{digest}.jpg"

    def is_missing_cache_valid(self, missing_path: Path) -> bool:
        if not missing_path.exists():
            return False

        try:
            age = time.time() - missing_path.stat().st_mtime
            return age < self.MISSING_CACHE_SECONDS
        except Exception:
            return False

    def write_missing_cache(self, missing_path: Path, message: str) -> None:
        try:
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.write_text(message, encoding="utf-8")
        except Exception:
            pass

    def remove_missing_cache(self, missing_path: Path) -> None:
        try:
            if missing_path.exists():
                missing_path.unlink()
        except Exception:
            pass

    def extract_album_cover(self, path: Path) -> bytes | None:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return None

            if hasattr(audio, "pictures") and audio.pictures:
                return audio.pictures[0].data

            if audio.tags is None:
                return None

            for key in audio.tags.keys():
                if str(key).startswith("APIC"):
                    tag = audio.tags[key]

                    if hasattr(tag, "data"):
                        return tag.data

            mp4_cover = audio.tags.get("covr")

            if mp4_cover:
                return bytes(mp4_cover[0])

        except Exception as error:
            print("后台读取内嵌封面失败：", path)
            print(error)

        return None

    def find_folder_cover(self, music_path: Path) -> Path | None:
        folder = music_path.parent

        possible_names = [
            "cover.jpg",
            "cover.jpeg",
            "cover.png",
            "folder.jpg",
            "folder.jpeg",
            "folder.png",
            "front.jpg",
            "front.jpeg",
            "front.png",
            "album.jpg",
            "album.jpeg",
            "album.png",
        ]

        for name in possible_names:
            candidate = folder / name

            if candidate.exists():
                return candidate

        return None

    def clean_search_text(self, text: str) -> str:
        text = str(text).strip()

        if text in {"未知歌曲", "未知艺术家", "未知专辑"}:
            return ""

        return text

    def wait_for_musicbrainz_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self.last_musicbrainz_request_time

        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        self.last_musicbrainz_request_time = time.time()

    def fetch_online_cover(self, title: str, artist: str, album: str) -> bytes | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_artist:
            return None

        if cleaned_album and cleaned_album not in {"未知专辑", "unknown album"}:
            queries = [
                f'release:"{cleaned_album}" AND artist:"{cleaned_artist}"',
                f'{cleaned_album} {cleaned_artist}',
            ]
        else:
            queries = [
                f'recording:"{cleaned_title}" AND artist:"{cleaned_artist}"',
                f'{cleaned_title} {cleaned_artist}',
            ]

        for query in queries:
            release_ids = self.search_musicbrainz_release_ids(query)

            for release_id in release_ids:
                cover_data = self.fetch_cover_art_archive(release_id)

                if cover_data:
                    return cover_data

        return None

    def search_musicbrainz_release_ids(self, query: str) -> list[str]:
        try:
            self.wait_for_musicbrainz_rate_limit()

            response = requests.get(
                "https://musicbrainz.org/ws/2/release/",
                params={
                    "query": query,
                    "fmt": "json",
                    "limit": 5,
                },
                headers=self.http_headers,
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

        except Exception as error:
            print("后台 MusicBrainz 搜索失败：", error)
            return []

        releases = data.get("releases", [])
        release_ids = []

        for release in releases:
            release_id = release.get("id")

            if release_id:
                release_ids.append(release_id)

        return release_ids

    def fetch_cover_art_archive(self, release_id: str) -> bytes | None:
        url = f"https://coverartarchive.org/release/{release_id}/front-500"

        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": self.http_headers.get("User-Agent", "HushPlayer"),
                    "Accept": "image/*",
                },
                timeout=15,
                allow_redirects=True,
            )

            if response.status_code != 200:
                return None

            content_type = response.headers.get("Content-Type", "")

            if "image" not in content_type.lower():
                return None

            return response.content

        except Exception as error:
            print("后台 Cover Art Archive 获取失败：", error)
            return None


class LyricsSearchWorker(QObject):
    status_changed = Signal(str, str)
    finished = Signal(str, object)

    MISSING_CACHE_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        request_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: str,
        lyrics_cache_dir: str,
        http_headers: dict,
    ) -> None:
        super().__init__()

        self.request_id = request_id
        self.file_path = file_path
        self.title = title
        self.artist = artist
        self.album = album
        self.lyrics_cache_dir = Path(lyrics_cache_dir)
        self.http_headers = dict(http_headers)

    def emit_status(self, message: str) -> None:
        self.status_changed.emit(self.request_id, message)

    def run(self) -> None:
        try:
            result = self.search_lyrics()
            self.finished.emit(self.request_id, result)
        except Exception as error:
            self.finished.emit(
                self.request_id,
                {
                    "ok": False,
                    "source": "error",
                    "message": str(error),
                    "song_path": self.file_path,
                },
            )

    def search_lyrics(self) -> dict:
        if not self.file_path:
            return {
                "ok": False,
                "source": "empty",
                "message": "没有歌曲路径",
                "song_path": self.file_path,
            }

        music_path = Path(self.file_path)
        cache_path = self.get_lyrics_cache_path(music_path)
        missing_path = cache_path.with_suffix(".missing")

        self.emit_status("正在查找本地歌词")
        local_lrc = self.find_lrc_file(music_path, self.title, self.artist)

        if local_lrc:
            self.remove_missing_cache(missing_path)
            return {
                "ok": True,
                "source": "local",
                "lyrics_path": str(local_lrc),
                "song_path": self.file_path,
            }

        self.emit_status("正在查找缓存歌词")

        if cache_path.exists():
            return {
                "ok": True,
                "source": "cache",
                "lyrics_path": str(cache_path),
                "song_path": self.file_path,
            }

        if self.is_missing_cache_valid(missing_path):
            self.emit_status("歌词缓存记录：上次未找到")
            return {
                "ok": False,
                "source": "missing_cache",
                "message": "近期已经搜索过，未找到同步歌词",
                "song_path": self.file_path,
            }

        self.emit_status("正在联网搜索 LRCLIB")
        duration_seconds = self.get_audio_duration_seconds(music_path)

        synced_lyrics = self.search_lrclib_synced_lyrics(
            title=self.title,
            artist=self.artist,
            album=self.album,
            duration_seconds=duration_seconds,
        )

        if not synced_lyrics:
            self.write_missing_cache(missing_path, "lyrics not found")
            self.emit_status("未找到歌词，已记录缓存")
            return {
                "ok": False,
                "source": "not_found",
                "message": "未找到同步歌词",
                "song_path": self.file_path,
            }

        self.lyrics_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(synced_lyrics, encoding="utf-8")
        self.remove_missing_cache(missing_path)

        return {
            "ok": True,
            "source": "online",
            "lyrics_path": str(cache_path),
            "song_path": self.file_path,
        }

    def get_lyrics_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.lyrics_cache_dir / f"{digest}.lrc"

    def is_missing_cache_valid(self, missing_path: Path) -> bool:
        if not missing_path.exists():
            return False

        try:
            age = time.time() - missing_path.stat().st_mtime
            return age < self.MISSING_CACHE_SECONDS
        except Exception:
            return False

    def write_missing_cache(self, missing_path: Path, message: str) -> None:
        try:
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.write_text(message, encoding="utf-8")
        except Exception:
            pass

    def remove_missing_cache(self, missing_path: Path) -> None:
        try:
            if missing_path.exists():
                missing_path.unlink()
        except Exception:
            pass

    def find_lrc_file(self, music_path: Path, title: str, artist: str) -> Path | None:
        folder = music_path.parent

        candidates = [
            music_path.with_suffix(".lrc"),
            folder / f"{music_path.stem}.lrc",
            folder / f"{title}.lrc",
            folder / f"{artist} - {title}.lrc",
            folder / f"{title} - {artist}.lrc",
        ]

        seen = set()

        for candidate in candidates:
            normalized = str(candidate).lower()

            if normalized in seen:
                continue

            seen.add(normalized)

            if candidate.exists():
                return candidate

        for candidate in folder.glob("*.lrc"):
            if candidate.stem.lower() == music_path.stem.lower():
                return candidate

        return None

    def get_audio_duration_seconds(self, path: Path) -> int:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return 0

            info = getattr(audio, "info", None)

            if info is None:
                return 0

            length = getattr(info, "length", 0)

            if not length:
                return 0

            return int(round(float(length)))

        except Exception as error:
            print("后台读取歌曲时长失败：", path)
            print(error)
            return 0

    def clean_search_text(self, text: str) -> str:
        text = str(text).strip()

        if text in {"未知歌曲", "未知艺术家", "未知专辑"}:
            return ""

        return text

    def normalize_match_text(self, text: str) -> str:
        text = self.clean_search_text(text).lower()
        text = re.sub(r"[\s\-_.,，。:：;；!！?？'\"“”‘’()\[\]{}【】<>《》/\\\\]+", "", text)
        return text

    def calculate_lyrics_result_score(
        self,
        result: dict,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> int:
        score = 0

        synced_lyrics = result.get("syncedLyrics")

        if not synced_lyrics:
            return -9999

        result_title = str(result.get("trackName", ""))
        result_artist = str(result.get("artistName", ""))
        result_album = str(result.get("albumName", ""))

        target_title = self.normalize_match_text(title)
        target_artist = self.normalize_match_text(artist)
        target_album = self.normalize_match_text(album)

        matched_title = self.normalize_match_text(result_title)
        matched_artist = self.normalize_match_text(result_artist)
        matched_album = self.normalize_match_text(result_album)

        if target_title and matched_title:
            if target_title == matched_title:
                score += 80
            elif target_title in matched_title or matched_title in target_title:
                score += 45

        if target_artist and matched_artist:
            if target_artist == matched_artist:
                score += 60
            elif target_artist in matched_artist or matched_artist in target_artist:
                score += 30

        if target_album and matched_album:
            if target_album == matched_album:
                score += 20
            elif target_album in matched_album or matched_album in target_album:
                score += 8

        result_duration = int(result.get("duration", 0) or 0)

        if duration_seconds > 0 and result_duration > 0:
            diff = abs(duration_seconds - result_duration)

            if diff <= 2:
                score += 30
            elif diff <= 5:
                score += 18
            elif diff <= 10:
                score += 8

        score += 40
        return score

    def search_lrclib_synced_lyrics(
        self,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> str | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_title:
            return None

        search_requests = []

        first_params = {
            "track_name": cleaned_title,
        }

        if cleaned_artist:
            first_params["artist_name"] = cleaned_artist

        if cleaned_album:
            first_params["album_name"] = cleaned_album

        search_requests.append(first_params)

        if cleaned_artist:
            search_requests.append(
                {
                    "q": f"{cleaned_title} {cleaned_artist}",
                }
            )

        search_requests.append(
            {
                "q": cleaned_title,
            }
        )

        best_result = None
        best_score = -9999

        for params in search_requests:
            try:
                response = requests.get(
                    "https://lrclib.net/api/search",
                    params=params,
                    headers=self.http_headers,
                    timeout=12,
                )

                response.raise_for_status()
                results = response.json()

                if not isinstance(results, list):
                    continue

            except Exception as error:
                print("后台 LRCLIB 搜索失败：", error)
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue

                score = self.calculate_lyrics_result_score(
                    result=result,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_seconds=duration_seconds,
                )

                if score > best_score:
                    best_score = score
                    best_result = result

            if best_result and best_score >= 110:
                break

        if not best_result:
            return None

        synced_lyrics = best_result.get("syncedLyrics")

        if not synced_lyrics:
            return None

        if best_score < 80:
            return None

        return str(synced_lyrics).strip()
'''

    if "class CoverSearchWorker(QObject):" not in text:
        text = insert_before(
            text,
            "class MainWindow(QMainWindow):",
            worker_classes,
            "插入后台封面/歌词 Worker 类",
        )

    async_methods = r'''    def cleanup_thread_reference(self, thread: QThread, kind: str) -> None:
        try:
            if kind == "cover" and thread in self.cover_threads:
                self.cover_threads.remove(thread)
            elif kind == "lyrics" and thread in self.lyrics_threads:
                self.lyrics_threads.remove(thread)
        except Exception:
            pass

    def start_cover_worker(
        self,
        file_path: str,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        self.cover_request_id += 1
        request_id = str(self.cover_request_id)
        self.active_cover_request_id = request_id

        worker = CoverSearchWorker(
            request_id=request_id,
            file_path=file_path,
            title=title,
            artist=artist,
            album=album,
            cover_cache_dir=str(self.cover_cache_dir),
            http_headers=self.http_headers,
        )

        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self.on_cover_worker_status)
        worker.finished.connect(self.on_cover_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self.cleanup_thread_reference(thread, "cover"))

        self.cover_threads.append(thread)
        thread.start()

    def on_cover_worker_status(self, request_id: str, message: str) -> None:
        if request_id != self.active_cover_request_id:
            return

        print("封面状态：", message)

        if not self.cover_label.pixmap() or self.cover_label.pixmap().isNull():
            self.cover_label.setText(message)

    def on_cover_worker_finished(self, request_id: str, result: object) -> None:
        if request_id != self.active_cover_request_id:
            print("已忽略过期封面结果：", request_id)
            return

        if not isinstance(result, dict):
            self.cover_label.setText("封面加载失败")
            return

        if result.get("ok"):
            cover_path = result.get("cover_path", "")

            if cover_path and self.show_cover_from_file(Path(cover_path)):
                print("已加载后台封面：", cover_path)
                return

        message = result.get("message", "未找到封面")
        print("封面搜索结束：", message)
        self.cover_label.clear()
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setText("无封面")

    def start_lyrics_worker(
        self,
        file_path: str,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        self.lyrics_request_id += 1
        request_id = str(self.lyrics_request_id)
        self.active_lyrics_request_id = request_id

        worker = LyricsSearchWorker(
            request_id=request_id,
            file_path=file_path,
            title=title,
            artist=artist,
            album=album,
            lyrics_cache_dir=str(self.lyrics_cache_dir),
            http_headers=self.http_headers,
        )

        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self.on_lyrics_worker_status)
        worker.finished.connect(self.on_lyrics_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self.cleanup_thread_reference(thread, "lyrics"))

        self.lyrics_threads.append(thread)
        thread.start()

    def on_lyrics_worker_status(self, request_id: str, message: str) -> None:
        if request_id != self.active_lyrics_request_id:
            return

        self.set_lyrics_status(message)

    def on_lyrics_worker_finished(self, request_id: str, result: object) -> None:
        if request_id != self.active_lyrics_request_id:
            print("已忽略过期歌词结果：", request_id)
            return

        if not isinstance(result, dict):
            self.lyrics_view.set_placeholder("歌词加载失败", "")
            self.set_lyrics_status("歌词加载失败")
            return

        if result.get("ok"):
            lyrics_path = result.get("lyrics_path", "")
            song_path = result.get("song_path", "")

            if not lyrics_path:
                self.lyrics_view.set_placeholder("歌词路径为空", "")
                self.set_lyrics_status("歌词加载失败")
                return

            lyrics = self.parse_lrc_file(Path(lyrics_path))

            if not lyrics:
                self.lyrics_view.set_placeholder("歌词格式无法解析", "可以换成本地 .lrc 歌词")
                self.set_lyrics_status("歌词解析失败")
                return

            self.current_lyrics = lyrics
            self.displayed_lyrics_song_path = self.normalize_song_path(song_path)
            self.lyrics_view.set_lyrics(self.current_lyrics)

            source = result.get("source", "")

            if source == "local":
                self.set_lyrics_status("已加载本地歌词")
            elif source == "cache":
                self.set_lyrics_status("已加载缓存歌词")
            elif source == "online":
                self.set_lyrics_status("已加载联网歌词")
            else:
                self.set_lyrics_status("已加载歌词")

            print("已加载后台歌词：", lyrics_path)
            print("歌词行数：", len(self.current_lyrics))
            return

        message = result.get("message", "未找到同步歌词")
        source = result.get("source", "")

        if source == "missing_cache":
            self.lyrics_view.set_placeholder("近期已搜索过，未找到同步歌词", "之后会自动隔几天再试")
            self.set_lyrics_status("近期已搜索过，未找到歌词")
        else:
            self.lyrics_view.set_placeholder("未找到同步歌词", "可以手动放一个同名 .lrc 文件到歌曲旁边")
            self.set_lyrics_status(str(message))

        self.current_lyrics = []
'''

    if "def start_cover_worker" not in text:
        text = insert_before(
            text,
            "    def update_cover(",
            async_methods,
            "插入后台任务启动和回调方法",
        )

    new_update_cover = r'''    def update_cover(
        self,
        file_path: str | None,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        self.reset_cover()

        if not file_path:
            return

        self.cover_label.setText("正在查找封面")
        self.start_cover_worker(
            file_path=self.normalize_song_path(file_path),
            title=title,
            artist=artist,
            album=album,
        )
'''

    new_load_lyrics_for_song = r'''    def load_lyrics_for_song(
        self,
        file_path: str | None,
        title: str,
        artist: str,
    ) -> None:
        self.current_lyrics = []
        self.displayed_lyrics_song_path = self.normalize_song_path(file_path)
        self.lyrics_view.set_placeholder("正在查找歌词", "优先本地歌词，没有就尝试联网搜索")
        self.set_lyrics_status("正在查找歌词")

        if not file_path:
            self.lyrics_view.set_placeholder("歌词功能还没有接入演示歌曲", "")
            self.set_lyrics_status("演示歌曲无歌词")
            return

        album = "未知专辑"
        current_item = self.song_list.currentItem()

        if current_item:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                album = song_data.get("album", "未知专辑")

        self.start_lyrics_worker(
            file_path=self.normalize_song_path(file_path),
            title=title,
            artist=artist,
            album=album,
        )
'''

    new_on_position_changed = r'''    def on_position_changed(self, position: int) -> None:
        if self.is_seeking or self.current_duration <= 0:
            return

        progress = int(position * 100 / self.current_duration)
        self.progress_slider.setValue(progress)

        self.record_listen_progress(position)

        current_playing_path = self.normalize_song_path(self.current_song_path)
        displayed_lyrics_path = self.normalize_song_path(self.displayed_lyrics_song_path)

        if current_playing_path and displayed_lyrics_path == current_playing_path:
            self.lyrics_view.update_by_position(position, self.current_lyrics)
'''

    text = replace_method(text, "update_cover", new_update_cover)
    text = replace_method(text, "load_lyrics_for_song", new_load_lyrics_for_song)
    text = replace_method(text, "on_position_changed", new_on_position_changed)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.5 后台搜索封面/歌词 + 未找到缓存 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()

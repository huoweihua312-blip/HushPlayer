import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v043"


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, content + marker, 1)


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.4" in text:
        print("当前文件看起来已经升级到 v0.4.4 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.3 (local music player prototype)",
        "HushPlayer/0.4.4 (local music player prototype)",
    )

    if "self.lyrics_cache_dir" not in text:
        text = replace_once(
            text,
            '''        self.cover_cache_dir = self.project_root / "cache" / "covers"
''',
            '''        self.cover_cache_dir = self.project_root / "cache" / "covers"
        self.lyrics_cache_dir = self.project_root / "cache" / "lyrics"
''',
            "添加歌词缓存目录",
        )

    if "歌词缓存位置" not in text:
        text = replace_once(
            text,
            '''        print("封面缓存位置：", self.cover_cache_dir)
''',
            '''        print("封面缓存位置：", self.cover_cache_dir)
        print("歌词缓存位置：", self.lyrics_cache_dir)
''',
            "打印歌词缓存目录",
        )

    lyric_methods = r'''    def get_lyrics_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.lyrics_cache_dir / f"{digest}.lrc"

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
            print("读取歌曲时长失败：", path)
            print(error)
            return 0

    def normalize_match_text(self, text: str) -> str:
        text = self.clean_search_text(text).lower()
        text = re.sub(r"[\s\\-_.,，。:：;；!！?？'\"“”‘’()\[\]{}【】<>《》/\\\\]+", "", text)
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

        if synced_lyrics:
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
            print("缺少歌曲名，跳过联网歌词搜索。")
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
                print("正在搜索 LRCLIB 歌词：", params)

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
                print("LRCLIB 搜索失败：", error)
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

                result_title = result.get("trackName", "")
                result_artist = result.get("artistName", "")
                result_duration = result.get("duration", "")

                print(
                    "歌词候选：",
                    result_title,
                    "-",
                    result_artist,
                    "duration=",
                    result_duration,
                    "score=",
                    score,
                )

                if score > best_score:
                    best_score = score
                    best_result = result

            if best_result and best_score >= 110:
                break

        if not best_result:
            print("没有找到合适的联网歌词。")
            return None

        synced_lyrics = best_result.get("syncedLyrics")

        if not synced_lyrics:
            print("最佳结果没有同步歌词。")
            return None

        if best_score < 80:
            print("联网歌词匹配分数过低，已放弃：", best_score)
            return None

        print(
            "已匹配联网歌词：",
            best_result.get("trackName", ""),
            "-",
            best_result.get("artistName", ""),
            "score=",
            best_score,
        )

        return str(synced_lyrics).strip()

    def write_lyrics_cache(self, cache_path: Path, lyrics_text: str) -> bool:
        try:
            self.lyrics_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(lyrics_text, encoding="utf-8")
            print("歌词已缓存：", cache_path)
            return True

        except Exception as error:
            print("写入歌词缓存失败：", error)
            return False

'''

    if "def search_lrclib_synced_lyrics" not in text:
        text = insert_before(
            text,
            '''    def load_lyrics_for_song(
''',
            lyric_methods,
            "插入联网歌词方法",
        )

    new_load_lyrics_for_song = r'''    def load_lyrics_for_song(
        self,
        file_path: str | None,
        title: str,
        artist: str,
    ) -> None:
        self.current_lyrics = []
        self.lyrics_view.set_placeholder("正在查找歌词", "优先本地歌词，没有就尝试联网搜索")

        if not file_path:
            self.lyrics_view.set_placeholder("歌词功能还没有接入演示歌曲", "")
            return

        music_path = Path(file_path)

        lyric_file = self.find_lrc_file(music_path, title, artist)

        if lyric_file:
            lyrics = self.parse_lrc_file(lyric_file)

            if lyrics:
                self.current_lyrics = lyrics
                self.lyrics_view.set_lyrics(self.current_lyrics)

                print(f"已加载本地歌词：{lyric_file}")
                print(f"歌词行数：{len(self.current_lyrics)}")
                return

            print("本地歌词解析失败：", lyric_file)

        cached_lyrics_file = self.get_lyrics_cache_path(music_path)

        if cached_lyrics_file.exists():
            lyrics = self.parse_lrc_file(cached_lyrics_file)

            if lyrics:
                self.current_lyrics = lyrics
                self.lyrics_view.set_lyrics(self.current_lyrics)

                print(f"已加载缓存歌词：{cached_lyrics_file}")
                print(f"歌词行数：{len(self.current_lyrics)}")
                return

            print("缓存歌词解析失败，准备重新联网搜索：", cached_lyrics_file)

            try:
                cached_lyrics_file.unlink()
            except Exception:
                pass

        self.lyrics_view.set_placeholder("正在联网搜索同步歌词", "第一次搜索可能会等几秒")

        album = "未知专辑"
        current_item = self.song_list.currentItem()

        if current_item:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                album = song_data.get("album", "未知专辑")

        duration_seconds = self.get_audio_duration_seconds(music_path)

        synced_lyrics = self.search_lrclib_synced_lyrics(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration_seconds,
        )

        if not synced_lyrics:
            self.lyrics_view.set_placeholder(
                "未找到同步歌词",
                "可以手动放一个同名 .lrc 文件到歌曲旁边",
            )
            print("未找到联网同步歌词：", title, artist)
            return

        self.write_lyrics_cache(cached_lyrics_file, synced_lyrics)

        lyrics = self.parse_lrc_file(cached_lyrics_file)

        if not lyrics:
            self.lyrics_view.set_placeholder(
                "联网歌词格式无法解析",
                "可以换成本地 .lrc 歌词",
            )
            print("联网歌词写入后解析失败：", cached_lyrics_file)
            return

        self.current_lyrics = lyrics
        self.lyrics_view.set_lyrics(self.current_lyrics)

        print(f"已加载联网歌词：{title} - {artist}")
        print(f"歌词行数：{len(self.current_lyrics)}")
'''

    text = replace_method(text, "load_lyrics_for_song", new_load_lyrics_for_song)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.4 联网歌词搜索和歌词缓存已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
    
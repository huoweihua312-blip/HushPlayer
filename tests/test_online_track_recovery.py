from __future__ import annotations

import unittest
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from app.services.online_track_recovery import OnlineTrackRecoveryService
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import Track


def _missing_track(**overrides) -> Track:
    values = {
        "id": "local:missing",
        "title": "123木头人",
        "artist": "黑Girl",
        "album": "美眉私密的一天",
        "duration_ms": 216_000,
        "source_id": "local",
        "source_name": "本地音乐",
        "source_type": "local",
        "added_at": datetime(2026, 1, 1, 12, 0),
        "is_favorite": True,
        "is_missing": True,
        "is_loading": False,
        "artwork_path": None,
        "stable_identity": "local:missing",
    }
    values.update(overrides)
    return Track(**values)


def _candidate(**overrides) -> OnlineTrack:
    values = {
        "id": "remote:123",
        "source_id": "catalog",
        "source_name": "开放目录",
        "title": "123木头人",
        "artist": "黑Girl",
        "album": "美眉私密的一天",
        "duration_ms": 216_000,
        "artwork_key": "remote:123",
        "quality": "标准",
        "stable_identity": "remote:123",
        "is_favorite": False,
        "is_downloaded": False,
        "is_cached": False,
        "availability": "not_resolved",
        "explicit": False,
        "result_rank": 0,
    }
    values.update(overrides)
    return OnlineTrack(**values)


class OnlineTrackRecoveryTests(unittest.TestCase):
    def test_async_search_emits_high_confidence_match(self) -> None:
        class FakeSearchService(QObject):
            resultsChanged = Signal(int, str, list, dict)

            def __init__(self) -> None:
                super().__init__()
                self.generation = 0
                self.keyword = ""

            def schedule_search(self, keyword: str) -> int:
                self.generation += 1
                self.keyword = keyword
                return self.generation

            def shutdown(self) -> None:
                return None

        search = FakeSearchService()
        service = OnlineTrackRecoveryService(search_service=search)
        matched = []
        service.match_found.connect(lambda _generation, track: matched.append(track))
        source = _missing_track()
        request_generation = service.request(source)
        self.assertEqual(search.keyword, "123木头人 黑Girl")
        search.resultsChanged.emit(
            search.generation,
            search.keyword,
            [
                {
                    "id": "remote:123",
                    "sourceId": "catalog",
                    "sourceName": "开放目录",
                    "title": source.title,
                    "artist": source.artist,
                    "duration": 216,
                    "capabilities": {"playback": True},
                }
            ],
            {"final": True},
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].title, source.title)
        self.assertEqual(service.generation, request_generation)

    def test_normalization_and_query_preserve_matching_identity(self) -> None:
        source = _missing_track(title=" １２３木头人！ ", artist="黑Girl")
        self.assertEqual(OnlineTrackRecoveryService.build_query(source), "１２３木头人！ 黑Girl")
        self.assertEqual(OnlineTrackRecoveryService.normalize_text("１２３木头人！"), "123木头人")

    def test_exact_title_artist_match_beats_wrong_artist(self) -> None:
        source = _missing_track()
        exact = _candidate()
        wrong_artist = _candidate(id="remote:wrong", stable_identity="remote:wrong", artist="另一位歌手")
        exact_score = OnlineTrackRecoveryService.score_match(source, exact)
        wrong_score = OnlineTrackRecoveryService.score_match(source, wrong_artist)
        self.assertGreaterEqual(exact_score, OnlineTrackRecoveryService.AUTO_MIN_SCORE)
        self.assertGreater(exact_score, wrong_score)

    def test_rank_candidates_ignores_sources_without_playback(self) -> None:
        service = OnlineTrackRecoveryService()
        source = _missing_track()
        raw = [
            {
                "id": "remote:no-playback",
                "sourceId": "archive",
                "sourceName": "归档",
                "title": source.title,
                "artist": source.artist,
                "capabilities": {"playback": False},
            },
            {
                "id": "remote:playback",
                "sourceId": "catalog",
                "sourceName": "开放目录",
                "title": source.title,
                "artist": source.artist,
                "duration": 216,
                "capabilities": {"playback": True},
            },
        ]
        ranked = service._rank_candidates(source, raw)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].track.remote_id, "remote:playback")


if __name__ == "__main__":
    unittest.main()

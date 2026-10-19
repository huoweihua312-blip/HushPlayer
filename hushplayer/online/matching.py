"""Title/artist matching for cross-source playback fallback.

Ported from the original HushPlayer's ``OnlineTrackRecoveryService`` scoring so
that "this source cannot play it" behaves like it always did: search the other
enabled sources by title + artist and pick the same recording, not just the
first search hit.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ..model.track import Track

__all__ = [
    "AUTO_MIN_SCORE",
    "AUTO_MARGIN",
    "CANDIDATE_MIN_SCORE",
    "MatchCandidate",
    "normalize_text",
    "score_match",
    "rank_candidates",
    "best_candidate",
]

#: Score at which a candidate may be played without asking the user.
AUTO_MIN_SCORE = 80
#: Required lead over the runner-up (avoids "same title, different artist").
AUTO_MARGIN = 15
#: Below this we do not consider the result to be the same song at all.
CANDIDATE_MIN_SCORE = 55


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    track: Track
    score: int

    @property
    def title(self) -> str:
        return self.track.display_title


def normalize_text(value: str | None) -> str:
    """NFKC + casefold, punctuation collapsed to spaces (matches the original)."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    cleaned = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in text
    )
    return " ".join(cleaned.split())


def _field_score(expected: str, actual: str, exact: int, contains: int, tokens: int) -> int:
    left = normalize_text(expected)
    right = normalize_text(actual)
    if not left or not right:
        return 0
    if left == right:
        return exact
    if left in right or right in left:
        return contains
    shared = set(left.split()) & set(right.split())
    if shared:
        return tokens
    return 0


def _artist_score(expected: str, actual: str) -> int:
    left = normalize_text(expected)
    if not left:
        return 0
    right = normalize_text(actual)
    if left == right:
        return 45
    if left in right or right in left:
        return 30
    # "A & B" vs "A / B": compare the individual names too.
    left_parts = {part.strip() for part in left.replace("&", "/").split("/") if part.strip()}
    right_parts = {part.strip() for part in right.replace("&", "/").split("/") if part.strip()}
    if left_parts & right_parts:
        return 30
    return -25


def _duration_score(expected: int | None, actual: int | None) -> int:
    if not expected or not actual or expected <= 0 or actual <= 0:
        return 0
    delta = abs(int(expected) - int(actual))
    if delta <= 8_000:
        return 8
    if delta <= 20_000:
        return 4
    return 0


def score_match(expected: Track, candidate: Track) -> int:
    title = _field_score(expected.title, candidate.title, 90, 60, 45)
    if title <= 0:
        return 0
    return (
        title
        + _artist_score(expected.artist, candidate.artist)
        + _field_score(expected.album, candidate.album, 10, 6, 0)
        + _duration_score(expected.duration_ms, candidate.duration_ms)
    )


def rank_candidates(expected: Track, candidates: list[Track]) -> list[MatchCandidate]:
    scored: list[MatchCandidate] = []
    for candidate in candidates:
        if candidate.id == expected.id:
            continue
        score = score_match(expected, candidate)
        if score >= CANDIDATE_MIN_SCORE:
            scored.append(MatchCandidate(candidate, score))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def best_candidate(
    expected: Track, candidates: list[Track], *, require_margin: bool = True
) -> MatchCandidate | None:
    ranked = rank_candidates(expected, candidates)
    if not ranked:
        return None
    best = ranked[0]
    if best.score < AUTO_MIN_SCORE:
        return None
    if require_margin and len(ranked) > 1 and best.score - ranked[1].score < AUTO_MARGIN:
        return None
    return best


def dedupe_tracks(tracks):
    """Drop duplicate search hits (same recording offered by several sources).

    Keeps the first occurrence; identity is normalised title + artist, so
    "晴天 (Live)" and "晴天" stay separate entries.
    """
    seen = set()
    result = []
    for track in tracks:
        key = (normalize_text(track.title or ""), normalize_text(track.artist or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(track)
    return result

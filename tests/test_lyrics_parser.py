"""歌词解析：时间轴、逐字/逐词、翻译、纯音乐与降级。"""

from __future__ import annotations

import pytest

from hushplayer.lyrics.parser import (
    attach_translation,
    parse,
    parse_klyric,
    parse_qrc,
    plain_document,
)

LRC = """[ti:夜航信号]
[ar:Aurora Field]
[offset:200]
[00:01.00]第一行歌词
[00:04.00]第二行歌词
[00:08.50]第三行歌词
"""

ENHANCED = "[00:01.00]<00:01.00>hello <00:01.60>world\n[00:03.00]<00:03.00>another <00:03.50>line\n"

YRC = "[1000,4000](0,600,0)你(600,600,0)好(1200,800,0)世界\n[5000,6000](0,500,0)再(500,500,0)见\n"

QRC = "[1000,4000]你(0,600)好(600,600)世界(1200,800)\n[5000,6000]再(0,500)见(500,500)\n"


def test_lrc_parses_lines_and_offset() -> None:
    document = parse(LRC)
    assert document.synced is True
    assert document.kind == "synced"
    assert len(document.lines) == 3
    assert document.offset_ms == 200
    assert document.lines[0].text == "第一行歌词"
    assert document.lines[0].start_ms == 1000
    assert document.lines[1].start_ms == 4000
    assert document.index_at(500) == -1
    assert document.index_at(1200) == 0
    assert document.index_at(4200) == 1
    assert document.title == "夜航信号"
    assert document.artist == "Aurora Field"


def test_lrc_line_progress() -> None:
    document = parse(LRC)
    assert document.line_progress(1, 4000) == pytest.approx(0.0)
    middle = document.line_progress(1, 6000)
    assert 0.3 < middle < 0.5, middle
    assert document.line_progress(1, 9000) == pytest.approx(1.0)


def test_enhanced_lrc_keeps_spaces_and_word_times() -> None:
    document = parse(ENHANCED)
    line = document.lines[0]
    assert line.text == "hello world"
    assert [(word.text, word.start_ms, word.end_ms) for word in line.words] == [
        ("hello", 1000, 1600),
        ("world", 1600, 3000),
    ]
    assert document.has_word_timing is True
    assert document.word_progress(0, 1000) == (0, pytest.approx(0.0))
    word_index, fraction = document.word_progress(0, 1300)
    assert word_index == 0 and fraction == pytest.approx(0.5, abs=0.05)
    word_index, fraction = document.word_progress(0, 1800)
    assert word_index == 1 and fraction == pytest.approx(0.14, abs=0.05)


def test_klyric_and_qrc_equivalent() -> None:
    from_yrc = parse_klyric(YRC)
    from_qrc = parse_qrc(QRC)
    for document in (from_yrc, from_qrc):
        assert document.has_word_timing is True
        first = document.lines[0]
        assert first.text == "你好世界"
        assert first.start_ms == 1000
        # 行尾由下一行起点钳制（[1000,4000] + 下一行 5000 → 5000）
        assert first.end_ms == 5000
        assert [word.text for word in first.words] == ["你", "好", "世界"]
    assert [word.start_ms for word in from_yrc.lines[0].words] == [1000, 1600, 2200]
    assert [word.start_ms for word in from_qrc.lines[0].words] == [1000, 1600, 2200]


def test_plain_text_fallback() -> None:
    document = parse("第一段\n\n第二段\n第三段")
    assert document.synced is False
    assert document.kind == "plain"
    assert [line.text for line in document.lines] == ["第一段", "第二段", "第三段"]
    assert document.lines[1].start_ms == 4000


def test_instrumental() -> None:
    document = parse("此歌曲为没有填词的纯音乐，请您静候")
    assert document.kind == "instrumental"
    assert document.lines


def test_empty() -> None:
    document = parse("   \n\n ")
    assert document.kind == "empty"
    assert document.is_empty()


def test_plain_document_directly() -> None:
    document = plain_document("a\nb", source="manual")
    assert document.kind == "plain"
    assert document.source == "manual"


def test_translation_attach() -> None:
    document = parse(ENHANCED)
    translated = attach_translation(document, "你好 世界\n另一行\n")
    assert translated.has_translation is True
    assert translated.lines[0].translation == "你好 世界"


def test_style_detection_prefers_word_timing() -> None:
    assert parse(YRC).kind == "synced"
    assert parse(QRC).kind == "synced"
    assert parse(YRC).raw


def test_parse_with_explicit_plain_flag() -> None:
    document = parse("[00:01.00]hello", plain=True)
    assert document.kind == "plain"


def test_parse_with_instrumental_flag() -> None:
    document = parse("", instrumental=True)
    assert document.kind == "instrumental"

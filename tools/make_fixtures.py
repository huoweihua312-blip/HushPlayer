"""Generate deterministic local audio fixtures for tests and UI screenshots.

The fixtures are synthetic (sine/chord tones) so they are licence free and
byte-stable enough for tests.  Everything is written to
``tests/fixtures/audio/`` which is git-ignored; run this script (or let
``tests/conftest.py`` do it) before the test-suite.

Usage:
    .venv\\Scripts\\python.exe tools\\make_fixtures.py [--force]
"""

from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_DIR = os.path.join(ROOT, "tests", "fixtures", "audio")

SAMPLE_RATE = 44100


def _tone(seconds: float, freqs: list[float], *, fade: float = 0.05):
    import numpy as np

    count = int(SAMPLE_RATE * seconds)
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    wave_data = np.zeros(count, dtype=np.float64)
    for index, freq in enumerate(freqs):
        # simple amplitude envelope so tracks do not click
        beat = 0.5 + 0.5 * np.sin(2 * math.pi * (0.35 + 0.12 * index) * time)
        wave_data += np.sin(2 * math.pi * freq * time) * (0.25 + 0.3 * beat)
    wave_data /= max(1.0, len(freqs)) * 1.6
    ramp = int(SAMPLE_RATE * fade)
    if ramp > 0 and count > 2 * ramp:
        envelope = np.ones(count)
        envelope[:ramp] = np.linspace(0, 1, ramp)
        envelope[-ramp:] = np.linspace(1, 0, ramp)
        wave_data *= envelope
    return np.stack([wave_data, wave_data], axis=1)


def _cover_png(seed: int, size: int = 600) -> bytes:
    from io import BytesIO

    from PIL import Image, ImageDraw

    palettes = [
        ((31, 33, 46), (201, 87, 112), (240, 214, 178)),
        ((18, 46, 44), (86, 170, 156), (232, 238, 224)),
        ((54, 32, 47), (168, 118, 196), (246, 226, 240)),
        ((38, 40, 44), (120, 144, 196), (222, 232, 246)),
    ]
    background, accent, highlight = palettes[seed % len(palettes)]
    image = Image.new("RGB", (size, size), background)
    draw = ImageDraw.Draw(image)
    for index in range(7):
        pad = 24 + index * size // 16
        color = accent if index % 2 else highlight
        alpha = 22 + index * 6
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse(
            (pad, pad, size - pad, size - pad),
            outline=color + (min(120, alpha),),
            width=max(2, size // 120),
        )
        image = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (size * 0.36, size * 0.36, size * 0.64, size * 0.64), fill=accent
    )
    draw.ellipse(
        (size * 0.47, size * 0.47, size * 0.53, size * 0.53), fill=background
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


ALBUM_SPECS = [
    {
        "album": "夜航信号",
        "albumartist": "Aurora Field",
        "artist": "Aurora Field",
        "year": 2024,
        "cover_seed": 0,
        "tracks": [
            ("01 - 夜航信号.mp3", "夜航信号", 12.0, [220.0, 277.18, 329.63]),
            ("02 - 凌晨四点的海.flac", "凌晨四点的海", 9.0, [196.0, 246.94]),
            ("03 - Static Bloom.wav", "Static Bloom", 7.0, [261.63, 392.0]),
        ],
    },
    {
        "album": "Long Way Home",
        "albumartist": "The Paper Lanterns",
        "artist": "The Paper Lanterns",
        "year": 2021,
        "cover_seed": 1,
        "tracks": [
            ("01 - Long Way Home.ogg", "Long Way Home", 10.0, [174.61, 220.0]),
            ("02 - Paper Lanterns.mp3", "Paper Lanterns", 8.0, [233.08, 311.13]),
        ],
    },
    {
        "album": "单人房 双人床 无限长的歌名用来测试省略号显示效果",
        "albumartist": "林间小径",
        "artist": "林间小径",
        "year": 2019,
        "cover_seed": 2,
        "tracks": [
            (
                "01 - 一首名字非常非常长的歌曲用来测试列表与播放栏的文本省略是否优雅.mp3",
                "一首名字非常非常长的歌曲用来测试列表与播放栏的文本省略是否优雅（现场版）",
                15.0,
                [207.65, 261.63, 311.13],
            ),
            ("02 - 无题.flac", "无题", 6.0, [293.66]),
        ],
    },
]


def _write_track(path: str, seconds: float, freqs: list[float], fmt: str) -> None:
    import soundfile as sf

    data = _tone(seconds, freqs)
    subtype = "PCM_16" if fmt in ("WAV", "AIFF") else None
    sf.write(path, data, SAMPLE_RATE, format=fmt, subtype=subtype)


def _tag(path: str, spec: dict, title: str, track_no: int, cover: bytes) -> None:
    from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.oggvorbis import OggVorbis
    from mutagen.wave import WAVE

    album = spec["album"]
    albumartist = spec["albumartist"]
    artist = spec["artist"]
    year = str(spec["year"])
    suffix = os.path.splitext(path)[1].lower()

    if suffix == ".flac":
        audio = FLAC(path)
        audio["title"] = title
        audio["artist"] = artist
        audio["album"] = album
        audio["albumartist"] = albumartist
        audio["date"] = year
        audio["tracknumber"] = str(track_no)
        audio["genre"] = "Electronic"
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png"
        picture.desc = "Cover"
        picture.data = cover
        audio.add_picture(picture)
        audio.save()
        return

    if suffix == ".ogg":
        audio = OggVorbis(path)
        audio["title"] = title
        audio["artist"] = artist
        audio["album"] = album
        audio["albumartist"] = albumartist
        audio["date"] = year
        audio["tracknumber"] = str(track_no)
        audio["genre"] = "Indie"
        audio.save()
        return

    if suffix == ".wav":
        audio = WAVE(path)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
    elif suffix == ".mp3":
        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
    else:
        raise SystemExit(f"unsupported fixture suffix: {suffix}")

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TPE2(encoding=3, text=albumartist))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TDRC(encoding=3, text=year))
    tags.add(TRCK(encoding=3, text=str(track_no)))
    tags.add(TCON(encoding=3, text="Pop"))
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=cover))
    audio.save()


def make(force: bool = False) -> str:
    from mutagen.flac import FLAC, Picture  # noqa: F401  (import check only)

    os.makedirs(FIXTURE_DIR, exist_ok=True)
    formats = {".mp3": "MP3", ".flac": "FLAC", ".wav": "WAV", ".ogg": "OGG"}
    for spec in ALBUM_SPECS:
        folder = os.path.join(FIXTURE_DIR, spec["album"])
        os.makedirs(folder, exist_ok=True)
        cover = _cover_png(spec["cover_seed"])
        with open(os.path.join(folder, "cover.png"), "wb") as handle:
            handle.write(cover)
        for index, (filename, title, seconds, freqs) in enumerate(spec["tracks"], start=1):
            path = os.path.join(folder, filename)
            suffix = os.path.splitext(filename)[1].lower()
            if force or not os.path.isfile(path):
                _write_track(path, seconds, freqs, formats[suffix])
                _tag(path, spec, title, index, cover)

    # A file without any tags, to exercise the filename fallback.
    loose = os.path.join(FIXTURE_DIR, "Loose Files")
    os.makedirs(loose, exist_ok=True)
    untagged = os.path.join(loose, "05 - 无名歌手 - 无名之歌.mp3")
    if force or not os.path.isfile(untagged):
        _write_track(untagged, 5.0, [329.63], "MP3")

    # A corrupt file that the scanner must skip without aborting the scan.
    broken = os.path.join(loose, "corrupt.mp3")
    if force or not os.path.isfile(broken):
        with open(broken, "wb") as handle:
            handle.write(b"ID3\x04\x00\x00\x00\x00\x00\x00this is not really an mp3")

    return FIXTURE_DIR


def main() -> int:
    force = "--force" in sys.argv
    folder = make(force=force)
    total = 0
    count = 0
    for base, _dirs, files in os.walk(folder):
        for name in files:
            count += 1
            total += os.path.getsize(os.path.join(base, name))
    print(f"fixtures ready: {folder}")
    print(f"{count} files, {total / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

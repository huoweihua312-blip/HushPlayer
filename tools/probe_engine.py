"""Generate local test audio fixtures (WAV) and exercise the playback engine.

Usage:  .venv\\Scripts\\python.exe tools\\probe_engine.py
"""

from __future__ import annotations

import math
import os
import struct
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.audio.engine import PlaybackEngine  # noqa: E402
from hushplayer.core import paths  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.library.metadata import read_track  # noqa: E402


def make_wav(path: str, seconds: float = 6.0, freq: float = 440.0) -> None:
    rate = 44100
    frames = int(rate * seconds)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        data = bytearray()
        for i in range(frames):
            value = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            data += struct.pack("<hh", value, value)
        handle.writeframes(bytes(data))


def tag_wav(path: str) -> None:
    from io import BytesIO

    from mutagen.id3 import APIC, TALB, TPE1, TIT2, ID3
    from mutagen.wave import WAVE
    from PIL import Image, ImageDraw

    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text="测试音轨"))
    audio.tags.add(TPE1(encoding=3, text="HushPlayer"))
    audio.tags.add(TALB(encoding=3, text="Engine Probe"))
    image = Image.new("RGB", (300, 300), (201, 87, 112))
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 80, 220, 220), fill=(24, 24, 30))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="cover", data=buffer.getvalue()))
    audio.save()


def main() -> int:
    paths.ensure_dirs()
    setup_logging(console=True)
    media_dir = os.path.join(str(paths.data_dir()), "probe_media")
    os.makedirs(media_dir, exist_ok=True)
    wav_path = os.path.join(media_dir, "engine_probe.wav")
    if not os.path.isfile(wav_path):
        make_wav(wav_path)
        tag_wav(wav_path)
    print("fixture:", wav_path, os.path.getsize(wav_path), "bytes")

    track, cover, ext = read_track(wav_path)
    print(f"metadata: {track.title} / {track.artist} / {track.album} / "
          f"{track.duration_ms}ms / cover={len(cover or b'')}B {ext}")

    app = QApplication(sys.argv)
    engine = PlaybackEngine()
    events: list[str] = []
    positions: list[tuple[float, int]] = []
    started = time.monotonic()

    def on_state(state: str) -> None:
        events.append(f"{time.monotonic()-started:5.2f}s state={state}")

    def on_pos(ms: int) -> None:
        positions.append((time.monotonic() - started, ms))

    def on_dur(ms: int) -> None:
        events.append(f"duration={ms}")

    def on_end() -> None:
        events.append(f"{time.monotonic()-started:5.2f}s END")

    def on_err(msg: str, fatal: bool) -> None:
        events.append(f"ERROR {msg} fatal={fatal}")

    engine.state_changed.connect(on_state)
    engine.position_changed.connect(on_pos)
    engine.duration_changed.connect(on_dur)
    engine.end_of_media.connect(on_end)
    engine.error_occurred.connect(on_err)

    engine.set_volume(0.5)
    engine.load(wav_path, duration_hint=track.duration_ms)
    print("output device:", engine.audio_device().description())

    def mid_checks() -> None:
        print("at 1.5s position:", engine.position(), "state:", engine.state)
        engine.pause()
        paused_at = engine.position()

        def after_pause() -> None:
            print("paused position stable:", paused_at, "->", engine.position())
            engine.seek(3000)
            engine.play()

        QTimer.singleShot(700, after_pause)

    QTimer.singleShot(1500, mid_checks)

    def finish() -> None:
        print("\n".join(events))
        print("positions samples:", positions[::max(1, len(positions) // 8)][:8])
        print(
            "played max position:",
            max((p[1] for p in positions), default=0),
            "duration:",
            engine.duration(),
        )
        engine.shutdown()
        app.quit()

    QTimer.singleShot(11000, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

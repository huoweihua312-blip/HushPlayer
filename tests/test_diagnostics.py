from __future__ import annotations

import zipfile

import json

from hushplayer.services import diagnostics


def test_export_bundle_writes_summary_and_readme(data_dir):
    bundle = diagnostics.export_bundle()

    assert bundle.exists()
    assert bundle.parent == data_dir / "exports"
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        summary = archive.read("summary.json").decode("utf-8")
        readme = archive.read("README.txt").decode("utf-8")

    assert "summary.json" in names
    assert "README.txt" in names
    assert '"version"' in summary
    assert "HushPlayer diagnostics" in readme


def test_export_bundle_hides_secrets(data_dir):
    import json

    (data_dir / "settings.json").write_text(
        json.dumps({"proxy": {"token": "super-secret"}, "ui": {"theme": "dark"}}),
        encoding="utf-8",
    )

    bundle = diagnostics.export_bundle()
    with zipfile.ZipFile(bundle) as archive:
        summary = archive.read("summary.json").decode("utf-8")

    assert "super-secret" not in summary
    assert '"theme": "dark"' in summary


def test_logs_are_redacted_in_bundle(data_dir):
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "hushplayer.log").write_text(
        "GET https://api.example.com/song?token=abcd1234\n"
        'headers={"Cookie": "sid=deadbeef", "Authorization": "Bearer xyz"}\n'
        "normal line stays\n",
        encoding="utf-8",
    )
    bundle = diagnostics.export_bundle()
    with zipfile.ZipFile(bundle) as archive:
        text = archive.read("logs/hushplayer.log").decode("utf-8")
    assert "abcd1234" not in text
    assert "deadbeef" not in text
    assert "Bearer xyz" not in text
    assert "normal line stays" in text


def test_summary_includes_session_and_cache_health(data_dir):
    (data_dir / "play_queue.json").write_text(
        json.dumps({"version": 1, "saved_at": 123.0, "position_ms": 5000,
                    "current_id": "local:abc", "items": ["local:abc"]}),
        encoding="utf-8",
    )
    cache = data_dir / "cache" / "audio"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "deadbeef.mp3").write_bytes(b"x" * 10)
    (cache / "deadbeef.meta.json").write_text(
        json.dumps({"complete": True, "size": 10}), encoding="utf-8"
    )
    bundle = diagnostics.export_bundle()
    with zipfile.ZipFile(bundle) as archive:
        summary = json.loads(archive.read("summary.json").decode("utf-8"))
    assert summary["session"]["current_id"] == "local:abc"
    assert summary["session"]["position_ms"] == 5000
    assert summary["audio_cache"]["files"] == 1
    assert summary["audio_cache"]["complete"] == 1

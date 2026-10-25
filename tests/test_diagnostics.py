from __future__ import annotations

import zipfile

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

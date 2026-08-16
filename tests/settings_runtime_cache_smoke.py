"""Smoke coverage for the UI V2 settings bridge and snapshot cache boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui_v2.adapters.legacy_settings_bridge import (
    LegacySettingsBridge,
    SettingsBridgeError,
)
from app.ui_v2.models.settings_snapshot import SettingsSnapshot


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hushplayer_settings_bridge_") as temp_dir:
        root = Path(temp_dir)
        settings_path = root / "data" / "settings.json"
        _write_json(
            settings_path,
            {
                "volume": "not-a-number",
                "play_mode": ["invalid"],
                "music_scan_folders": None,
                "immersive_background_alpha": {"bad": True},
                "unknown_future_field": {"nested": [1, 2, 3]},
            },
        )
        applied: list[dict] = []
        bridge = LegacySettingsBridge(
            settings_path,
            apply_callback=lambda values: applied.append(values),
            action_callbacks={"fixture_action": lambda value: f"done:{value}"},
        )

        snapshot = bridge.read_snapshot()
        assert bridge.value(snapshot, "volume") == 65
        assert bridge.value(snapshot, "play_mode") == "list_loop"
        assert bridge.value(snapshot, "music_scan_folders") == []
        assert bridge.value(snapshot, "unknown_future_field") == {
            "nested": [1, 2, 3]
        }
        isolated = bridge.value(snapshot, "unknown_future_field")
        isolated["nested"].append(4)
        assert bridge.value(snapshot, "unknown_future_field") == {"nested": [1, 2, 3]}

        updated = snapshot.with_updates(
            {
                "volume": 73,
                "play_mode": "shuffle",
                "music_scan_folders": [str(root / "music")],
            }
        )
        saved = bridge.save_snapshot(updated)
        assert isinstance(saved, SettingsSnapshot)
        assert applied[-1]["volume"] == 73
        assert applied[-1]["play_mode"] == "shuffle"
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["unknown_future_field"] == {"nested": [1, 2, 3]}
        assert persisted["music_scan_folders"] == [str(root / "music")]
        assert not settings_path.with_suffix(".json.tmp").exists()

        failed = updated.with_updates({"appearance_mode": "invalid"})
        try:
            bridge.save_snapshot(failed)
        except SettingsBridgeError as error:
            assert "主题" in str(error)
        else:
            raise AssertionError("invalid settings were accepted")
        assert bridge.has_action("fixture_action")
        assert bridge.run_action("fixture_action", "ok") == "done:ok"
        assert not bridge.has_action("missing_action")

    print("settings runtime bridge smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

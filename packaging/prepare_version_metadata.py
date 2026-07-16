from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NAME,
    APP_NUMERIC_VERSION,
    APP_NUMERIC_VERSION_TEXT,
    APP_VERSION,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
)


def build_version_info_text() -> str:
    version_tuple = repr(tuple(APP_NUMERIC_VERSION))
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '{APP_NAME}'),
          StringStruct('FileDescription', '{APP_NAME}'),
          StringStruct('FileVersion', '{APP_VERSION}'),
          StringStruct('InternalName', '{APP_NAME}'),
          StringStruct('LegalCopyright', '{APP_NAME} contributors'),
          StringStruct('OriginalFilename', '{APP_NAME}.exe'),
          StringStruct('ProductName', '{APP_NAME}'),
          StringStruct('ProductVersion', '{APP_VERSION}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def prepare_metadata(output_dir: Path) -> dict:
    resolved_output = output_dir.expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    version_info_file = resolved_output / "HushPlayer.version_info.txt"
    version_info_file.write_text(build_version_info_text(), encoding="utf-8")
    metadata = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "numeric_version": APP_NUMERIC_VERSION_TEXT,
        "numeric_version_parts": list(APP_NUMERIC_VERSION),
        "update_channel": UPDATE_CHANNEL,
        "architecture": UPDATE_ARCHITECTURE,
        "installer_filename": (
            f"{APP_NAME}-{APP_VERSION}-{UPDATE_ARCHITECTURE}-setup.exe"
        ),
        "version_info_file": str(version_info_file),
    }
    metadata_file = resolved_output / "version_metadata.json"
    metadata_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata["metadata_file"] = str(metadata_file)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    metadata = prepare_metadata(arguments.output_dir)
    print(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

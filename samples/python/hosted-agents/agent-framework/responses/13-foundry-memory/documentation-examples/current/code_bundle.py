# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Archive the three reviewed runtime files without copying local configuration."""

from pathlib import Path
import tempfile
import zipfile


def create_code_zip(source_dir: Path) -> Path:
    source_dir = source_dir.resolve(strict=True)
    names = ("main.py", "pyproject.toml", "uv.lock")
    for name in names:
        path = source_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"Expected a regular {name} in the approved runtime directory: {source_dir}"
            )
    with tempfile.NamedTemporaryFile(
        prefix="foundry-agent-", suffix=".zip", delete=False
    ) as temporary:
        archive_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name in names:
                archive.write(source_dir / name, name)
    except OSError:
        archive_path.unlink(missing_ok=True)
        raise
    return archive_path

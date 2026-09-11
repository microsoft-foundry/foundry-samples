"""Fetch the Schema-Guided Dialogue (SGD) dataset.

SGD is published by Google Research under CC BY-SA 4.0:
https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

    python download_sgd.py                 # train + dev + test into ./data/sgd
    python download_sgd.py --splits test   # just what steps 2-4 need
"""
from __future__ import annotations

import argparse
import io
import shutil
import urllib.request
import zipfile
from pathlib import Path

ARCHIVE_URL = (
    "https://github.com/google-research-datasets/"
    "dstc8-schema-guided-dialogue/archive/refs/heads/master.zip"
)
ARCHIVE_ROOT = "dstc8-schema-guided-dialogue-master"
DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "sgd"


def _wanted(member: str, splits: list[str]) -> str | None:
    """Return the destination path relative to OUT, or None to skip."""
    parts = Path(member).parts
    # Expect: <ARCHIVE_ROOT>/<split>/<file.json>
    if len(parts) != 3 or parts[0] != ARCHIVE_ROOT:
        return None
    split, name = parts[1], parts[2]
    if split not in splits or not name.endswith(".json"):
        return None
    if name != "schema.json" and not name.startswith("dialogues_"):
        return None
    return f"{split}/{name}"


def download(out_dir: Path, splits: list[str]) -> None:
    print(f"[get] {ARCHIVE_URL}")
    with urllib.request.urlopen(
        ARCHIVE_URL, timeout=300
    ) as resp:  # noqa: S310 - fixed https URL
        blob = resp.read()
    print(f"[get] {len(blob) / 1e6:.1f} MB")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            rel = _wanted(info.filename, splits)
            if rel is None:
                continue
            dest = out_dir / rel
            # Guard against zip-slip: the resolved path must stay under out_dir.
            if not dest.resolve().is_relative_to(out_dir.resolve()):
                raise RuntimeError(f"refusing unsafe archive member: {info.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            written += 1
    print(f"[ok] wrote {written} files to {out_dir}")

    for split in splits:
        d = out_dir / split
        n_dlg = len(list(d.glob("dialogues_*.json")))
        print(
            f"     {split}: {n_dlg} dialogue files, schema.json "
            f"{'present' if (d / 'schema.json').exists() else 'MISSING'}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--splits",
        nargs="+",
        default=["train", "dev", "test"],
        choices=["train", "dev", "test"],
    )
    args = ap.parse_args()
    download(args.out, args.splits)


if __name__ == "__main__":
    main()

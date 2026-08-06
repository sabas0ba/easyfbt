#!/usr/bin/env python3
"""Download the MediaPipe .task model files with sha256 verification.

Models are fetched from Google's versioned (immutable) model storage paths and
verified against the hashes pinned below before being moved into ``models/``.
Nothing in easyfbt downloads models implicitly at runtime.

Usage:
    python tools/fetch_models.py [--dest models]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

BASE = "https://storage.googleapis.com/mediapipe-models"

#: filename -> (versioned URL, pinned sha256)
MODELS: dict[str, tuple[str, str]] = {
    "pose_landmarker_full.task": (
        f"{BASE}/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
        "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1",
    ),
    "face_landmarker.task": (
        f"{BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    ),
}


def fetch(url: str, expected_sha256: str, dest: Path) -> None:
    if dest.is_file():
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if digest == expected_sha256:
            print(f"ok (cached): {dest}")
            return
        print(f"hash mismatch on existing {dest}; re-downloading", file=sys.stderr)
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https URL
        data = resp.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(
            f"sha256 mismatch for {dest.name}:\n  expected {expected_sha256}\n  got      {digest}"
        )
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        tmp.write(data)
    Path(tmp.name).replace(dest)
    print(f"ok: {dest} ({len(data)} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default="models", help="destination directory")
    args = parser.parse_args()
    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for filename, (url, sha) in MODELS.items():
        fetch(url, sha, dest_dir / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

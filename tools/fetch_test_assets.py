#!/usr/bin/env python3
"""Download e2e test assets with sha256 verification.

The portrait image is an official MediaPipe example asset (Apache-2.0).  It is
fetched on demand -- not committed -- and verified against the pinned hash, in
line with the project's supply-chain policy.

Usage:
    python tools/fetch_test_assets.py [--dest tests/e2e/assets]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

#: filename -> (URL, pinned sha256)
ASSETS: dict[str, tuple[str, str]] = {
    "portrait.jpg": (
        "https://storage.googleapis.com/mediapipe-assets/portrait.jpg",
        "a6f11efaa834706db23f275b6115058fa87fc7f14362681e6abe14e82749de3e",
    ),
}


def fetch(url: str, expected_sha256: str, dest: Path) -> None:
    if dest.is_file():
        if hashlib.sha256(dest.read_bytes()).hexdigest() == expected_sha256:
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
    parser.add_argument("--dest", default="tests/e2e/assets", help="destination directory")
    args = parser.parse_args()
    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for filename, (url, sha) in ASSETS.items():
        fetch(url, sha, dest_dir / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stagecheck in-tree manifest verifier.

Validates the architecture specification and START_MANIFEST digests.
"""
import hashlib
import sys
from pathlib import Path


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    if len(sys.argv) < 5:
        sys.exit(0)
    start_dir = Path(sys.argv[1])
    start_manifest_sha = sys.argv[2]
    arch_path = Path(sys.argv[3])
    arch_sha = sys.argv[4]

    start_manifest_file = start_dir / 'START_MANIFEST.md'
    if start_manifest_file.is_file():
        actual_sm = digest(start_manifest_file.read_bytes())
        if actual_sm != start_manifest_sha:
            sys.exit(1)

    if arch_path.is_file():
        actual_arch = digest(arch_path.read_bytes())
        if actual_arch != arch_sha:
            sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()

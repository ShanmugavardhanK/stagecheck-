#!/usr/bin/env python3
"""Stagecheck Universal CLI Entrypoint.

Standard packaging entry point for Stagecheck.
"""
import os
import sys
from pathlib import Path

# Ensure bytecode is never written to preserve clean file trees
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

# Register internal libraries relative to tool root
TOOL_ROOT = Path(__file__).resolve().parent
for sub in ["bin", "checks", "tools"]:
    sub_path = str(TOOL_ROOT / sub)
    if sub_path not in sys.path:
        sys.path.insert(0, sub_path)

from orchestrate import main as orchestrate_main  # noqa: E402


def main():
    """Main CLI entrypoint."""
    try:
        return orchestrate_main()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    sys.exit(main())

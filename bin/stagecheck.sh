#!/bin/sh
# Stagecheck: Deterministic Multi-Agent Verification & Assurance Engine
# Standard POSIX launcher wrapper.
set -eu

export PYTHONDONTWRITEBYTECODE=1

stagecheck_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    cat << 'EOF'
Stagecheck: Deterministic Multi-Agent Verification & Assurance Engine

Usage:
  stagecheck.sh --task TASK --report REPORT --claims CLAIMS --repo REPO --base BASE [options]
  stagecheck.sh --response --task TASK --report REPORT --claims CLAIMS [options]

Standard Exit Codes:
  0   PASSED            All verification checks passed with zero blocking defects
  1   BLOCKING DEFECTS  One or more blocking defects detected (unapproved modifications)
  2   NOT DONE / REVIEW Incomplete deliverable or unproved claims requiring disposition
  3   TOOL ERROR        Setup, permission, or environmental admission failure

EOF
    exec python3 "$stagecheck_dir/bin/orchestrate.py" --help
fi

exec python3 "$stagecheck_dir/bin/orchestrate.py" "$@"

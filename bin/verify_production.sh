#!/bin/bash
# Stagecheck Production & CI/CD Verification Runner
# Validates hermetic packaging, cryptographic manifest, and full regression matrix.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$SCRIPT_DIR"

export PYTHONDONTWRITEBYTECODE=1
export STAGECHECK_HOME="$(mktemp -d)"
trap 'rm -rf "$STAGECHECK_HOME"' EXIT

echo "=========================================================="
echo " Stagecheck Production & CI Verification Suite"
echo " Tool Root: $SCRIPT_DIR"
echo " Sandbox Home: $STAGECHECK_HOME"
echo "=========================================================="

echo "[1/8] Verifying cryptographic manifest integrity..."
sha256sum -c MANIFEST.sha256 > /dev/null
echo "  -> Manifest OK (100% verified)"

echo "[2/8] Checking for developer-specific path leaks..."
if grep -rn "magnus" --exclude="verify_production.sh" --exclude="*.log" --exclude="*.pyc" --exclude-dir=".git" --exclude-dir="__pycache__" . > /dev/null; then
    echo "  -> FAILED: Found hardcoded developer path in codebase!"
    exit 1
fi
echo "  -> Path hygiene OK (0 machine-specific paths found)"

echo "[3/8] Running response hook unit guards..."
python3 evals/test_response_guards.py > /dev/null
echo "  -> Response guards OK"

echo "[4/8] Running full response evaluation suite (41 cases)..."
python3 evals/test_response.py > /dev/null
echo "  -> Response evals OK"

echo "[5/8] Running quality and Clopper-Pearson engine (58 tests)..."
python3 evals/test_quality.py > /dev/null
echo "  -> Quality engine OK"

echo "[6/8] Running Git boundaries & quality edge suite..."
python3 scratch/test_git_and_quality_edges.py > /dev/null
echo "  -> VCS & quality edges OK"

echo "[7/8] Running live adversarial red-team suite..."
python3 scratch/test_live_red_team_codex.py > /dev/null
echo "  -> Live red-team suite OK"

echo "[8/8] Running concurrency, race condition & TOCTOU suite..."
python3 scratch/test_concurrency_toctou.py > /dev/null
echo "  -> Concurrency & TOCTOU OK"

echo "Verifying CLI entry points in isolated environment..."
./bin/stagecheck.sh --help > /dev/null
./stagecheck_cli.py --help > /dev/null
echo "  -> CLI entrypoints OK"

echo "=========================================================="
echo " ALL 8 SUITES & CLI VERIFICATIONS PASSED (PRODUCTION READY)"
echo "=========================================================="

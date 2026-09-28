#!/usr/bin/env bash
# Full test suite for OFLIT Child Activity Monitor (agent + extension).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
echo "== Python agent tests =="
python3 -m unittest discover -s "$here" -p 'test_*.py'
echo
echo "== Extension (Node) tests =="
node "$here/extension/run_extension_tests.js"

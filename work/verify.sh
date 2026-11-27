#!/usr/bin/env bash
# Run all local validation for the transcription integration kit.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

run_step() {
  local description="$1"
  shift
  printf '\n==> %s\n' "$description"
  if "$@"; then
    return 0
  else
    local status=$?
    fail "$description failed (exit code $status)"
  fi
}

# Confirm the kit is complete before attempting its tests.
for required_file in README.md SETUP.md EMAIL_TEMPLATE.md \
  work/examples/python/transcribe.py work/examples/python/test_transcribe.py \
  work/examples/node/transcribe.js work/examples/node/test_transcribe.test.js \
  work/examples/node/package.json; do
  [[ -f "$required_file" ]] || fail "Required file is missing: $required_file"
done
[[ -d work/examples/python ]] || fail 'Required examples directory is missing: work/examples/python'
[[ -d work/examples/node ]] || fail 'Required examples directory is missing: work/examples/node'
printf 'Required documentation and example files are present.\n'

run_step 'Python syntax check' python -m py_compile \
  work/examples/python/transcribe.py work/examples/python/test_transcribe.py
run_step 'Python tests' pytest work/examples/python/test_transcribe.py
run_step 'Node syntax check (example)' node --check work/examples/node/transcribe.js
run_step 'Node syntax check (tests)' node --check work/examples/node/test_transcribe.test.js
run_step 'Node tests' npm --prefix work/examples/node test

printf '\nAll validation checks passed.\n'

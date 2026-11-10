#!/usr/bin/env bash
# Stub harness (tests only).
set -euo pipefail
case "$1" in
  list) printf 'core\nphysics\nselftest:look\n' ;;
  core|scope:*|selftest:*) echo "$1: 3 tests ran, 0 failed" ;;
  *) echo "unknown scope $1" >&2; exit 2 ;;
esac

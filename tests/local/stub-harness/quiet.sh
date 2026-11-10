#!/usr/bin/env bash
# Stub harness (tests only): the machine is always fit; no lock.
if [ "${1:-}" = "--check" ]; then echo "fit (stub)"; exit 0; fi
exec "$@"

#!/usr/bin/env python3
"""timebox.py SECONDS CMD… — run CMD in its own process group; on timeout
kill the whole group (TERM, then KILL) and exit 124. macOS has no `timeout`.
Otherwise exits with CMD's status. Output passes through unchanged."""

import os
import signal
import subprocess
import sys
import time


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: timebox.py SECONDS CMD...")
    limit = float(sys.argv[1])
    proc = subprocess.Popen(sys.argv[2:], start_new_session=True)
    try:
        sys.exit(proc.wait(timeout=limit))
    except subprocess.TimeoutExpired:
        print(f"[timebox] {' '.join(sys.argv[2:])[:120]} timed out after {limit:.0f} s", file=sys.stderr)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                break
            time.sleep(5)
        proc.wait()
        sys.exit(124)
    except KeyboardInterrupt:
        os.killpg(proc.pid, signal.SIGTERM)
        raise


if __name__ == "__main__":
    main()

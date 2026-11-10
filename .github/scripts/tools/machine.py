#!/usr/bin/env python3
"""machine.py — is this Mac fit to measure? (trusted, read-only)

  machine.py check [--state FILE] [--record-display] [--quiet-check CMD] [--min-free-gb 25]

Checks, without changing anything: AC power, battery not charging, Low Power
Mode off, thermal pressure normal, Time Machine idle, free disk, screen
unlocked, the display setup (compared with the one recorded in --state at
Phase 6), and finally the target's own fit-to-measure check (--quiet-check,
e.g. `integration-test/quiet.sh --check`). Prints one line per item and a JSON
summary; exit 0 when everything is fit, 3 when not.
"""

import argparse
import hashlib
import json
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def sh(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def check_power():
    rc, out = sh(["pmset", "-g", "batt"])
    if rc != 0:
        return None, "pmset unavailable"
    on_ac = "AC Power" in out
    battery = re.search(r"(\d+)%; ([^;]+);", out)
    if not on_ac:
        return False, "on battery — plug in"
    if battery and battery.group(2).strip() in ("charging",):
        return False, f"battery charging ({battery.group(1)}%) — wait until charged"
    return True, "on AC power" + (f", battery {battery.group(1)}% {battery.group(2).strip()}" if battery else "")


def check_low_power():
    rc, out = sh(["pmset", "-g"])
    m = re.search(r"lowpowermode\s+(\d)", out)
    if not m:
        return True, "Low Power Mode not reported"
    return (m.group(1) == "0"), ("Low Power Mode off" if m.group(1) == "0" else "Low Power Mode is ON — turn it off")


def check_thermal():
    rc, out = sh(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"])
    try:
        level = int(out.split()[-1])
    except (ValueError, IndexError):
        return None, "thermal level unavailable"
    return (level == 0), f"thermal pressure level {level}" + ("" if level == 0 else " — let the Mac cool down")


def check_time_machine():
    rc, out = sh(["tmutil", "status"])
    if rc != 0:
        return None, "tmutil unavailable"
    running = re.search(r"Running = (\d)", out)
    if running and running.group(1) != "0":
        return False, "Time Machine backup running — wait or pause it"
    return True, "Time Machine idle"


def check_disk(path, min_gb):
    free = shutil.disk_usage(path).free / 1e9
    return free >= min_gb, f"{free:.0f} GB free (need {min_gb})"


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def check_screen_unlocked():
    try:
        raw = subprocess.run(["ioreg", "-n", "Root", "-d1", "-a"], capture_output=True, timeout=10).stdout
        locked = find_key(plistlib.loads(raw), "CGSSessionScreenIsLocked")
    except Exception:
        return None, "screen lock state unavailable"
    return (not locked), ("screen unlocked" if not locked else "screen is locked — unlock it")


def display_signature():
    rc, out = sh(["system_profiler", "SPDisplaysDataType", "-json"], timeout=60)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None, "unknown"
    shown = []
    for gpu in data.get("SPDisplaysDataType", []):
        for d in gpu.get("spdisplays_ndrvs", []):
            shown.append("{} {} {}{}".format(
                d.get("_name", "?"), d.get("_spdisplays_resolution") or d.get("_spdisplays_pixels", "?"),
                d.get("spdisplays_connection_type", ""),
                " main" if d.get("spdisplays_main") == "spdisplays_yes" else ""))
    text = "; ".join(sorted(shown))
    return hashlib.sha256(text.encode()).hexdigest()[:16], text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["check"])
    ap.add_argument("--state", help="state file with DISPLAY_SIGNATURE=… (Phase 6 records it)")
    ap.add_argument("--record-display", action="store_true",
                    help="store the current display signature in --state if none is stored")
    ap.add_argument("--quiet-check", help="the target's fit-to-measure command")
    ap.add_argument("--min-free-gb", type=float, default=25)
    ap.add_argument("--path", default=str(Path.home()))
    args = ap.parse_args()

    items = [("power", *check_power()), ("low power mode", *check_low_power()),
             ("thermal", *check_thermal()), ("time machine", *check_time_machine()),
             ("disk", *check_disk(args.path, args.min_free_gb)), ("screen", *check_screen_unlocked())]

    sig, text = display_signature()
    stored = None
    if args.state and Path(args.state).is_file():
        m = re.search(r"^DISPLAY_SIGNATURE=(\S+)", Path(args.state).read_text(), re.M)
        stored = m.group(1) if m else None
    if stored is None and args.record_display and args.state and sig:
        with open(args.state, "a") as f:
            f.write(f"DISPLAY_SIGNATURE={sig}\nDISPLAY_SETUP={shlex.quote(text)}\n")
        items.append(("display", True, f"recorded: {text}"))
    elif stored is None:
        items.append(("display", True, f"{text} (not yet recorded)"))
    else:
        items.append(("display", sig == stored,
                      f"{text}" + ("" if sig == stored else " — differs from the setup the baseline was measured on")))

    if args.quiet_check:
        rc, out = sh(["bash", "-c", args.quiet_check], timeout=300)
        last = (out.strip().splitlines() or [""])[-1][:200]
        items.append(("target quiet check", rc == 0, f"exit {rc}: {last}" if rc else "fit to measure"))

    ok = True
    for name, good, note in items:
        mark = "ok  " if good else ("??  " if good is None else "FAIL")
        print(f"  {mark} {name}: {note}")
        ok = ok and good is not False
    print(json.dumps({"fit": ok, "items": [{"item": n, "ok": g, "note": t} for n, g, t in items]}))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()

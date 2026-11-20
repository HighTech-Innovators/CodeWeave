# Harness contract (local Phases 5–8)

Phase 4 implements these files in `integration-test/` of the run workspace. The local
Phases 5–8 (`run-local.sh`) only ever call them as described here; everything else —
A/B order, records, statistics, verdicts, gates, integrity — is trusted CodeWeave code.
After review at Checkpoint 1 the files are frozen by checksum: any later change stops
the run. A target may supply its own versions in `~/codeweave-runs/<name>/harness/`.

All scripts run from the workspace root with `bash`, must work with macOS bash 3.2, and
receive these environment variables:

| Variable | Meaning |
|---|---|
| `CW_SRC` | the target tree being built and tested (`<workspace>/src`) |
| `CW_BASE` | a checkout of the frozen base commit (`<workspace>/base`, Phase 5+): **use the measuring tools from here**, so A and B are measured by identical code |
| `CW_MEASURE` | trusted data folder (do not write outside the `--out` folder you are given) |
| `CW_PY` | a Python 3 with scipy, numpy and Pillow |
| `APP_WINDOW` | requested window size (e.g. `1600x900`) for targets measured in a window; also set as `GAME_WINDOW`, its older name |
| `SOURCE_REPO_PATH` | the user's own checkout — **read-only** |

Never write into `SOURCE_REPO_PATH`. Never write to the agent-facing `integration-test/reports/`
from these scripts; write only to the `--out` folder.

## `build.sh --src DIR`

Build the target in `DIR`. Print **the artefact path as the last line of stdout** (an
app bundle, executable or folder). Exit 0 on success. May take minutes; no measuring.

## `test.sh SCOPE --src DIR [--artifact PATH]`

| SCOPE | Meaning |
|---|---|
| `list` | print every scope name this script accepts, one per line (always include `core`; end-to-end checks are named `selftest:<name>`) |
| `core` | the fast, broad correctness suite (unit tests that need no game build) |
| `scope:<a,b,…>` | the named test scopes |
| `selftest:<a,b,…>` | end-to-end checks with the built artefact given by `--artifact` |

Exit 0 only if every requested test passed **and at least one test ran** in each
requested scope (an empty selection is a failure). End the output with a summary line
`total: N tests (P passed, F failed)`, and print each failed test as a line
`FAIL <test name>[: message]` when the runner names it.

Phase 7 judges a failed gate against the same gate on the unchanged base (run once,
cached): it is accepted when the base fails it too, the change ran at least as many
tests, failed no more of them, and names no failed test the base passes. Tests that
already fail in the target therefore do not block every optimization, and the report
lists them. Without the summary line a failed gate cannot be compared and stays failed.

## `run.sh --artifact PATH --out DIR [--profile]`

One measurement launch of the given build. Write `DIR/metrics.json`:

```json
{
  "window": "1600x900",
  "views": {
    "<view>": {"frame_ms": 5.67, "cpu_ms": 3.11, "gpu_ms": 8.73, "pending": 0}
  },
  "noise": {"quiet": true, "reasons": []},
  "screens": {"<view>": "screens/<view>.png"}
}
```

- `views`: one entry per measured view (a fixed camera position/scene), each the
  median over the launch of frame, CPU (main thread) and GPU milliseconds; `pending`
  = work still loading in that view (non-zero makes the launch be repeated).
- `noise.quiet`: false when the target's own noise detection saw other load during the
  launch; list the reasons.
- `screens`: screenshot per view, relative to `DIR`, copied into `DIR`. Required when the
  rendered-output check is on (`VISUAL_CHECK=on`, the `rendering` profile's default): the
  pipeline compares B's screenshots with A's, and Phase 6 stops when the base build gives
  none. With the check off, `screens` may be left out.
- Copy the target's raw output for the launch into `DIR` too.
- Exit non-zero if the launch failed; then `metrics.json` may be absent.
- `--profile`: one diagnostic launch instead; write `DIR/profile.md` — a readable
  breakdown of where frame time goes (per view, per subsystem where the target can
  tell). Used once, to pick optimizations.

The launch must measure exactly the same way for any artefact: take the scenario,
camera positions, timings and measuring code from `CW_BASE`, never from `CW_SRC`.

## `bench.sh`

Benchmarks of engine-free code, compiled against a given source tree and run one
process per measurement.

| Call | Meaning |
|---|---|
| `bench.sh --build --src DIR --out BUILD` | compile all benchmarks against the sources in `DIR` into `BUILD` |
| `bench.sh --list --run BUILD` | print the benchmark names, one per line |
| `bench.sh --run BUILD --entry NAME --out DIR` | run one benchmark in a fresh process; write `DIR/metrics.json`: `{"median_ns": 123456, "samples": 30, "fingerprint": "<hash of the result>", "runtime": "<runtime>"}` |

The fingerprint is a hash of what the benchmark computed, so a faster but different
result is caught. Run on the runtime the product actually uses where that differs from
the development runtime. Benchmark sources live in `integration-test/bench/`.

## `quiet.sh`

| Call | Meaning |
|---|---|
| `quiet.sh --check` | is the machine fit to measure right now? Exit 0 yes, 3 no (print why). **No side effects**: do not close programs, take locks or wait. |
| `quiet.sh CMD…` | run `CMD` with the machine reserved for measuring (the target's own lock if it has one; nested target tools must not try to take it again). Exit 3 if the machine is not fit; otherwise `CMD`'s exit code. |

## `scope-map.tsv`

Which tests must run when which files change. One rule per line, tab-separated:
`<path glob relative to the target root><TAB><scope>[,<scope>…]`; `#` comments. Globs use
shell `case` matching (`*` crosses directories). A `*` rule applies to every change.
Scopes must be names printed by `test.sh list`.

## `base-patches/*.patch` (optional)

Measurement-only changes applied to the base before Phase 5 builds it, so A and every
B share them (for example a longer frame capture). `git apply`-able against the target.
They are listed for the user at Checkpoint 1 and must not change behaviour.

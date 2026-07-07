# Test Constraints

> **This file is optional.**
> Populate it with performance measurement constraints before running Phase 3.
> Phase 3 reads this file and incorporates its constraints into `integration-test/SOURCE-UNDER-INVESTIGATION.md`.
> Delete or comment out any section that does not apply to your codebase.

---

## Execution Environment

- CPU only — no GPU required; exclude all CUDA (`aten/src/ATen/cuda/`, `torch/cuda/`), MPS (`torch/mps/`), ROCm, and XPU backends from test scope
- Linux x86-64 (Ubuntu 22.04+ or equivalent CI runner)
- Python 3.11+ with a standard CPU-only PyTorch wheel (`pip install torch --index-url https://download.pytorch.org/whl/cpu`)
- No system-level dependencies beyond those bundled with the PyTorch wheel

---

## Benchmark Policy

- Each benchmark scenario must run for a minimum of **30 seconds wall-clock time** to yield stable CPU measurements (eliminates JIT warm-up and OS scheduling noise)
- Discard warm-up effects by one of two accepted methods: **(a)** an explicit warm-up phase of at least 5 iterations or 3 seconds (whichever is longer) before recording, or **(b)** reporting a warm-up-robust statistic — the **median** per-iteration latency (`p50`) over the full ≥ 30 s window, which absorbs the cold first iteration without a separate phase. The end-to-end baseline benchmark uses **(b)** (`median_iter_ms`); per-scenario tests may use either
- Report: mean, p50, p95, p99, and standard deviation over the measurement window
- Benchmarks must be isolated: no other benchmark may run concurrently in the same process
- Micro-benchmarks for dispatch-sensitive paths (< 1 μs per call) must use `timeit` or equivalent with ≥ 10,000 repetitions per measurement window

---

## Machine Isolation (measurement environment)

End-to-end timing is only trustworthy on a quiesced, frequency-stable host. The baseline gate records a high coefficient of variation but does **not** fail on it, so these rules are what keep `cv_iter` low enough for the end-to-end measurement path to be usable — otherwise verdicts fall back to the per-op microbench path.

**The harness must implement (in `run.sh` / the benchmark process):**

- Pin the benchmark to a fixed set of dedicated physical cores when a core list is provided: honour a `BENCH_CPUSET` environment variable (e.g. `BENCH_CPUSET=2,3`) by launching the measurement under `taskset -c "$BENCH_CPUSET"` (or `numactl --physcpubind`). When it is unset, run unpinned but print a clear warning that results may be noisy.
- Set the BLAS/OpenMP thread count to **match the pinned set, not the whole machine**: `OMP_NUM_THREADS` / `MKL_NUM_THREADS` and `torch.set_num_threads()` must equal the number of pinned cores. Default to a fixed value, not `$(nproc)`, so the thread count is reproducible across hosts.
- Lower scheduling contention: run the measurement at a favourable priority (`nice`/`ionice` to the extent permitted without root) and start no concurrent work during a measurement window.
- Record the observed CPU state per run alongside the metrics — at minimum the mean CPU frequency and the 1-minute load average during the window — so a contended or throttled run is **visible in the report rather than silent**.

**Environment preconditions (operator-provided; the harness cannot enforce these):**

- A dedicated, otherwise-idle host: no concurrent OS maintenance (on Windows hosts: Windows Update, Defender scans, search indexing, backup/sync), no other heavy processes, and no interactive use during collection.
- AC power, not battery — laptops drop to a power-saving frequency profile on battery.
- CPU governor set to `performance` and, for run-to-run consistency, turbo/boost disabled where permitted (`scaling_governor`, `intel_pstate/no_turbo`). Document it when the runner does not permit changing these.
- **Prefer native Linux or a dedicated cloud VM over WSL2 for any run whose end-to-end numbers are reported.** Under WSL2 the Windows host owns CPU frequency and thermals, so governor/turbo and core pinning cannot be fully enforced from inside the VM, and a laptop under sustained load will thermally throttle.

---

## Suite Time Budget

- Total test suite (non-benchmark) runtime: < 10 minutes on a 4-core / 8 GB RAM CI runner
- Per-test timeout: 60 seconds (tests exceeding this are treated as hangs and fail the suite)
- Benchmark tests are excluded from the 60-second per-test cap but must individually complete within 5 minutes

---

## Isolation Requirements

- No external network calls during test execution (no model downloads, registry lookups, or remote fixture fetches)
- Each test must restore any global state it modifies before returning:
  - `torch.set_default_dtype()` → restore original dtype
  - `torch.manual_seed()` → document that seeding is intentional if used
  - Registered hooks (forward hooks, backward hooks) → remove all hooks registered by the test
  - `torch.backends.*` flags → restore original values
- No shared mutable tensor or `nn.Module` fixtures between tests (construct in-process per test)
- No temporary files left on the filesystem after a test completes

---

## Test Invocation

- All tests must be discoverable and runnable via: `pytest integration-test/tests/`
- No manual setup steps beyond: `pip install torch --index-url https://download.pytorch.org/whl/cpu` in a clean Python virtual environment
- No `conftest.py` may perform network I/O or download model weights
- Benchmark tests must be skippable via a standard marker: `pytest -m "not benchmark"` must run the non-benchmark suite

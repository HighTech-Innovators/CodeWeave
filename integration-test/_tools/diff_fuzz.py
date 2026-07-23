"""Differential fuzz gate (correctness gate step 7f).

An optimization in CodeWeave is almost always a *narrow fast path* that falls
through to the original kernel for unhandled inputs (opt1: lambda==1.0,
contiguous, float/double, n>=16; opt2: k*64 <= dim_size). General correctness
is preserved by construction, but nothing in gates 7a-7e proves the fast path
itself is numerically faithful to the reference on inputs that *do* trigger it.
7e only diffs the harness's narrow input distribution, at the generated-text
level, and is advisory. This gate closes that hole.

It works by *paired A/B differencing of the same op*:

  1. CAPTURE (run on the BASE build, before the optimization is compiled in):
     run a battery of seeded fuzz cases whose inputs satisfy the optimization's
     declared fast-path trigger conditions, and save the outputs as golden.
  2. COMPARE (run on the VARIANT build): regenerate the identical cases (same
     seeds -> identical inputs, and for RNG ops the identical global RNG stream)
     and compare each output against golden under the spec's tolerance. It
     additionally reports max abs / rel / ULP diff per case so a sub-tolerance
     numerical drift (e.g. a vectorized log1p that is ~1 ULP off scalar log1p)
     is visible even when it passes.

The per-optimization fuzz spec is a small Python module authored by the
optimization agent (like the microbench setup/stmt it already authors); this
driver is fixed and trusted (pre-authored in the run repo, like ab_compare.py).

Spec module contract (integration-test/fuzz/opt<N>_fuzz.py):

    IS_RNG: bool            # True if the op fills via the GLOBAL RNG (exponential_, ...)
    DETERMINISTIC: bool     # optional, default False; wrap runs in
                            # torch.use_deterministic_algorithms(True)
    DTYPES: list[str]       # e.g. ["float32", "float64"]
    N_CASES: int            # cases per dtype (>= --min-cases, default 16)
    RTOL: float             # pass/fail tolerance for float outputs
    ATOL: float
    MAX_ULP: int | None     # optional hard ULP ceiling for float outputs
    SEED_BASE: int          # optional, default 0

    def make_case(gen: torch.Generator, dtype: torch.dtype, idx: int) -> dict:
        '''Build ONE fuzz case whose inputs satisfy the fast-path trigger
        conditions. Use `gen` for ALL input randomness so capture and compare
        build identical inputs. Vary shapes with idx to cover the fast-path
        space and its boundaries. Returns an opaque dict consumed by run().'''

    def triggers_fast_path(case: dict) -> bool:
        '''Return True iff `case` satisfies every fast-path trigger condition
        that is determined by the case dict (e.g. numel >= 16, dtype in the
        fast-path set). The driver calls this on EVERY generated case and aborts
        the gate if any returns False — so make_case cannot silently drift to
        non-triggering inputs, which would make the comparison vacuous. Encode
        the SAME conditions stated in the module docstring (derived from the
        source). Conditions only fixed inside run() (e.g. lambda==1.0,
        contiguity) cannot be checked here and remain run()'s responsibility.'''

    def run(case: dict):
        '''Invoke the target op and return the result tensor or tuple of
        tensors to compare. For IS_RNG ops the driver seeds the GLOBAL RNG
        immediately before calling run(), so construct/fill inside run().'''

Output tensors are compared by inferred kind: integer dtypes (e.g. topk
indices) must match EXACTLY; floating dtypes use allclose(RTOL, ATOL,
equal_nan=True) plus the ULP ceiling. Comparing indices exactly is only sound
under DETERMINISTIC=True (PyTorch's topk tie-break is gated behind
deterministic mode); a non-deterministic spec should return values only.

Usage:
    python _tools/diff_fuzz.py --spec integration-test/fuzz/opt1_fuzz.py \
        --mode capture --golden integration-test/reports/fuzz-golden-opt1.pt
    python _tools/diff_fuzz.py --spec integration-test/fuzz/opt1_fuzz.py \
        --mode compare --golden integration-test/reports/fuzz-golden-opt1.pt \
        --report integration-test/reports/fuzz-diff-opt1.json
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import torch


def build_fingerprint() -> str:
    """A cheap fingerprint of the *installed native build* that changes on an
    incremental rebuild. git_version is unusable here: it does not change for
    uncommitted optimization edits (the 7f compare runs before the opt branch
    is committed), so it would mark every legitimate variant run as vacuous.
    Stat (size+mtime) of the rebuilt shared objects does change."""
    parts = []
    libdir = Path(torch.__file__).parent / "lib"
    if libdir.is_dir():
        for so in sorted(libdir.glob("*.so*")):
            try:
                st = so.stat()
                parts.append(f"{so.name}:{st.st_size}:{st.st_mtime_ns}")
            except OSError:
                pass
    if not parts:
        f = getattr(torch._C, "__file__", None) or torch.__file__
        try:
            st = os.stat(f)
            parts.append(f"{f}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(getattr(torch.version, "git_version", "unknown"))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def spec_sha(spec_path: Path) -> str:
    return hashlib.sha1(spec_path.read_bytes()).hexdigest()


def load_spec(spec_path: Path):
    spec = importlib.util.spec_from_file_location("fuzz_spec", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    required = ["IS_RNG", "DTYPES", "N_CASES", "RTOL", "ATOL"]
    missing = [a for a in required if not hasattr(mod, a)]
    if missing:
        die(f"spec {spec_path} is missing required attributes: {missing}")
    for fn in ["make_case", "triggers_fast_path", "run"]:
        if not callable(getattr(mod, fn, None)):
            die(f"spec {spec_path} must define a callable {fn}()")
    if not mod.DTYPES:
        die(f"spec {spec_path}: DTYPES must be non-empty")
    return mod


def die(msg: str):
    print(f"diff_fuzz: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


DTYPE_MAP = {
    "float32": torch.float32, "float": torch.float32,
    "float64": torch.float64, "double": torch.float64,
    "float16": torch.float16, "half": torch.float16,
    "bfloat16": torch.bfloat16,
}


@contextmanager
def maybe_deterministic(enabled: bool):
    if not enabled:
        yield
        return
    prev = torch.are_deterministic_algorithms_enabled()
    torch.use_deterministic_algorithms(True)
    try:
        yield
    finally:
        torch.use_deterministic_algorithms(prev)


def as_tuple(out):
    if isinstance(out, (tuple, list)):
        return tuple(out)
    return (out,)


def run_one(mod, dtype, idx):
    """Build + run a single case deterministically. Returns a tuple of CPU
    tensors (detached, cloned) ready for storage or comparison."""
    gen = torch.Generator()
    gen.manual_seed(int(getattr(mod, "SEED_BASE", 0)) + idx)
    case = mod.make_case(gen, dtype, idx)
    # Every case MUST exercise the fast path, or the differential comparison is
    # vacuous (it would diff the slow path against itself). Enforce the spec's
    # own declared trigger predicate so make_case cannot drift to non-triggering
    # inputs (D7).
    if not bool(mod.triggers_fast_path(case)):
        die(f"make_case produced a case that does not satisfy triggers_fast_path "
            f"(dtype={dtype}, idx={idx}): {case!r}. Every fuzz case must hit the "
            f"fast path or the gate is vacuous.")
    if getattr(mod, "IS_RNG", False):
        # Seed the GLOBAL RNG so the op's internal draw stream is identical
        # across capture and compare — this is exactly what makes the gate a
        # valid test of RNG-stream preservation.
        torch.manual_seed(int(getattr(mod, "SEED_BASE", 0)) + idx)
    with maybe_deterministic(bool(getattr(mod, "DETERMINISTIC", False))):
        out = mod.run(case)
    return tuple(t.detach().to("cpu").clone() for t in as_tuple(out))


def capture(mod, golden_path: Path, spec_hash: str):
    dtypes = [DTYPE_MAP[d] for d in mod.DTYPES]
    cases = []
    for d in dtypes:
        for idx in range(int(mod.N_CASES)):
            cases.append(run_one(mod, d, idx))
    manifest = {
        "is_rng": bool(getattr(mod, "IS_RNG", False)),
        "deterministic": bool(getattr(mod, "DETERMINISTIC", False)),
        "dtypes": list(mod.DTYPES),
        "n_cases": int(mod.N_CASES),
        "rtol": float(mod.RTOL),
        "atol": float(mod.ATOL),
        "max_ulp": getattr(mod, "MAX_ULP", None),
        "seed_base": int(getattr(mod, "SEED_BASE", 0)),
        "torch_git_version": getattr(torch.version, "git_version", "unknown"),
        "build_fingerprint": build_fingerprint(),
        "spec_sha": spec_hash,
        "n_outputs_per_case": [len(c) for c in cases],
    }
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"manifest": manifest, "cases": cases}, golden_path)
    print(f"diff_fuzz capture: {len(cases)} cases "
          f"({len(dtypes)} dtypes x {mod.N_CASES}) -> {golden_path} "
          f"(git_version={manifest['torch_git_version']})")


_FLOAT_INT_VIEW = {
    torch.float16: (torch.int16, 16),
    torch.bfloat16: (torch.int16, 16),
    torch.float32: (torch.int32, 32),
    torch.float64: (torch.int64, 64),
}


def _ulp_max(a: torch.Tensor, b: torch.Tensor) -> float:
    """Max IEEE ULP distance over finite, equal-NaN-masked positions.

    ULP is computed in the tensors' NATIVE float width (int16 for half /
    bfloat16, int32 for float32, int64 for float64). Upcasting half precision
    to float32 first — as an earlier version did — measures the distance in the
    wrong representation: a 1-ULP fp16 difference becomes thousands of fp32
    ULPs, so the MAX_ULP ceiling would not constrain half-precision outputs at
    all (A8). Bitcasting in torch also sidesteps numpy's lack of a bfloat16
    dtype.
    """
    view = _FLOAT_INT_VIEW.get(a.dtype)
    if view is None or a.dtype != b.dtype:
        return 0.0
    int_dtype, bits = view
    af = a.detach().reshape(-1)
    bf = b.detach().reshape(-1)
    finite = torch.isfinite(af) & torch.isfinite(bf)
    if not bool(finite.any()):
        return 0.0
    # Boolean-mask indexing yields contiguous 1-D tensors safe to bitcast.
    ia = af[finite].view(int_dtype).to(torch.int64)
    ib = bf[finite].view(int_dtype).to(torch.int64)
    sign_min = -(1 << (bits - 1))
    ka = torch.where(ia < 0, sign_min - ia, ia)
    kb = torch.where(ib < 0, sign_min - ib, ib)
    return float((ka - kb).abs().max().item())


def compare_one(golden_outs, fresh_outs, rtol, atol, max_ulp):
    """Compare one case's output tuple. Returns (passed, per-output detail)."""
    detail = []
    passed = True
    if len(golden_outs) != len(fresh_outs):
        return False, [{"error": f"output count {len(fresh_outs)} != golden {len(golden_outs)}"}]
    for oi, (g, f) in enumerate(zip(golden_outs, fresh_outs)):
        d = {"output": oi, "dtype": str(f.dtype), "shape": list(f.shape)}
        if g.shape != f.shape or g.dtype != f.dtype:
            d.update({"passed": False, "error": f"shape/dtype {tuple(f.shape)}/{f.dtype} "
                      f"!= golden {tuple(g.shape)}/{g.dtype}"})
            passed = False
            detail.append(d)
            continue
        if not (f.is_floating_point() or f.dtype == torch.bfloat16):
            # integer / bool outputs (e.g. topk indices): exact match required
            ok = bool(torch.equal(g, f))
            mism = int((g != f).sum().item())
            d.update({"kind": "exact", "mismatches": mism, "passed": ok})
            passed = passed and ok
        else:
            gf = g.to(torch.float64)
            ff = f.to(torch.float64)
            allclose = bool(torch.allclose(gf, ff, rtol=rtol, atol=atol, equal_nan=True))
            diff = (gf - ff).abs()
            denom = gf.abs().clamp_min(1e-300)
            max_abs = float(diff.max().item()) if diff.numel() else 0.0
            max_rel = float((diff / denom).max().item()) if diff.numel() else 0.0
            ulp = _ulp_max(g, f)
            ulp_ok = (max_ulp is None) or (ulp <= max_ulp)
            ok = allclose and ulp_ok
            d.update({"kind": "float", "max_abs": max_abs, "max_rel": max_rel,
                      "max_ulp": ulp, "allclose": allclose, "ulp_ok": ulp_ok,
                      "passed": ok})
            passed = passed and ok
        detail.append(d)
    return passed, detail


def compare(mod, golden_path: Path, report_path: Path | None, spec_hash: str):
    if not golden_path.exists():
        die(f"golden file not found: {golden_path} (capture step did not run?)")
    blob = torch.load(golden_path, weights_only=False)
    manifest = blob["manifest"]
    golden = blob["cases"]

    # The spec must be frozen for the cycle: the golden was captured on the base
    # build with this exact spec, and a changed make_case() builds different
    # inputs, making the comparison meaningless. Refuse rather than mislead.
    if manifest.get("spec_sha") and manifest["spec_sha"] != spec_hash:
        die("fuzz spec changed since golden capture (spec_sha mismatch). The "
            "spec is frozen during the repair loop — revert spec edits and fix "
            "only src/. (The base build needed to re-capture golden is gone.)")

    cur_git = getattr(torch.version, "git_version", "unknown")
    cur_fp = build_fingerprint()
    golden_fp = manifest.get("build_fingerprint")
    vacuous = golden_fp is not None and cur_fp == golden_fp
    if vacuous:
        # Same native build on both sides (the .so was not rebuilt between
        # capture and compare): the gate cannot detect a regression because the
        # variant binary is not installed. This is a blocking gate — every case
        # would trivially match itself — so FAIL rather than pass quietly (A2).
        print("diff_fuzz compare: ERROR: build_fingerprint unchanged since "
              "capture — the variant build is not installed; this comparison is "
              "vacuous and FAILS the gate.", file=sys.stderr)

    rtol = float(manifest["rtol"])
    atol = float(manifest["atol"])
    max_ulp = manifest.get("max_ulp")
    dtypes = [DTYPE_MAP[d] for d in manifest["dtypes"]]
    n_cases = int(manifest["n_cases"])

    results = []
    overall_pass = True
    worst_ulp = 0.0
    ci = 0
    for d in dtypes:
        for idx in range(n_cases):
            fresh = run_one(mod, d, idx)
            ok, detail = compare_one(golden[ci], fresh, rtol, atol, max_ulp)
            for od in detail:
                if od.get("kind") == "float":
                    worst_ulp = max(worst_ulp, od.get("max_ulp", 0.0))
            results.append({"case": ci, "dtype": str(d), "idx": idx,
                            "passed": ok, "outputs": detail})
            overall_pass = overall_pass and ok
            ci += 1

    # A vacuous comparison (variant build not installed) cannot certify the
    # fast path: fail the gate regardless of per-case results (A2).
    overall_pass = overall_pass and not vacuous

    report = {
        "tool": "diff_fuzz",
        "overall_pass": overall_pass,
        "n_cases": len(results),
        "rtol": rtol, "atol": atol, "max_ulp": max_ulp,
        "worst_ulp": worst_ulp,
        "golden_git_version": manifest.get("torch_git_version"),
        "variant_git_version": cur_git,
        "golden_build_fingerprint": golden_fp,
        "variant_build_fingerprint": cur_fp,
        "vacuous": vacuous,
        "failures": [r for r in results if not r["passed"]][:20],
        "cases": results,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    n_fail = sum(1 for r in results if not r["passed"])
    print(f"diff_fuzz compare: {len(results) - n_fail}/{len(results)} cases pass, "
          f"worst_ulp={worst_ulp:.0f}, verdict={'PASS' if overall_pass else 'FAIL'}")
    for r in results:
        if not r["passed"]:
            print(f"  FAIL case {r['case']} (dtype={r['dtype']}, idx={r['idx']}): "
                  f"{r['outputs']}")
    sys.exit(0 if overall_pass else 1)


def main():
    p = argparse.ArgumentParser(description="Differential fuzz gate (7f)")
    p.add_argument("--spec", type=Path, required=True, help="fuzz spec module")
    p.add_argument("--mode", choices=["capture", "compare"], required=True)
    p.add_argument("--golden", type=Path, required=True, help="golden .pt path")
    p.add_argument("--report", type=Path, help="JSON report (compare mode)")
    p.add_argument("--min-cases", type=int, default=16,
                   help="reject specs with N_CASES below this (anti-undertest)")
    args = p.parse_args()

    if not args.spec.exists():
        die(f"spec not found: {args.spec}")
    mod = load_spec(args.spec)
    if int(mod.N_CASES) < args.min_cases:
        die(f"spec N_CASES={mod.N_CASES} < --min-cases={args.min_cases}; "
            f"too few cases to be a meaningful fuzz gate")

    sha = spec_sha(args.spec)
    torch.manual_seed(0)
    if args.mode == "capture":
        capture(mod, args.golden, sha)
    else:
        compare(mod, args.golden, args.report, sha)


if __name__ == "__main__":
    main()

# Constraints

**Constraint:** Use PyTorch with CPU only.

**Constraint (Python interpreter):** Build and run the harness against **Python 3.12**.
The venv MUST be created with the `python3.12` interpreter explicitly — never the ambient
`python3`. On this runner `python3` is a newer release (3.14) that has **no prebuilt PyPI
wheels** for several pinned harness dependencies (e.g. `tokenizers`), which forces source
builds that then fail against the runner's C23/GCC-15 toolchain (pyo3 ≤3.13, oniguruma
C). Python 3.12 is within PyTorch's supported range (`setup.py` `python_requires`) **and**
has full wheel coverage for the entire harness stack, so the install uses only prebuilt
wheels — no Rust/C compilation, and reproducible run-to-run. If `python3.12` is not on
PATH, the build script must **fail with the exact install command** (`apt-get install -y
python3.12 python3.12-venv python3.12-dev`) rather than silently using another interpreter.
> Adjust the version only to another PyTorch-supported release that also has full wheel
> coverage for the harness dependencies — confirm the interpreter is installed on the
> runner before changing.

**Constraint:** When building PyTorch from source (Phase 5), the Python development
headers for the build interpreter must be installed before building (not discoverable from
CONTRIBUTING.md): `python3.12-dev` (provides `Python.h`; without it CMake cannot build
`torch._C` even when `BUILD_PYTHON=1` is set — it silently falls back to `BUILD_PYTHON=OFF`).
Keep the `-dev` package version matched to the interpreter above.

**Constraint:** When building PyTorch from source (Phase 5), the following environment
variables must be set before running `pip install -e .`. These are not all discoverable
from CONTRIBUTING.md — apply them unconditionally:

| Variable | Value | Why |
|---|---|---|
| `BUILD_PYTHON` | `1` | CMake defaults this to OFF; without it `libtorch_python.so` and `torch._C` are not compiled, making the package unimportable |
| `BUILD_TEST` | `0` | Skip building test binaries (~30% of build time) |
| `USE_CUDA` | `0` | CPU-only build |
| `USE_DISTRIBUTED` | `0` | Not needed for inference harness |
| `USE_FBGEMM` | `0` | Quantisation backend not required |
| `USE_NNPACK` | `0` | Not required |
| `USE_QNNPACK` | `0` | Not required |
| `USE_XNNPACK` | `0` | Not required |
| `USE_FLASH_ATTENTION` | `0` | CUDA-only feature |
| `USE_MEM_EFF_ATTENTION` | `0` | CUDA-only feature |

**Constraint:** Do not perform any GIT commits. These will be handled externally.

**Constraint:** Use codecarbon for energy measurement in integration tests (`pip install codecarbon`; wrap benchmark runs with `EmissionsTracker`).

**Constraint (harness venv must be able to collect PyTorch's own test suite):**
`integration-test/requirements.txt` must include `expecttest` and `hypothesis`. The
Phase 7 correctness gates run PyTorch's own tests (`src/test/...`, and
`test/test_ops.py` for the OpInfo gate) with the harness venv interpreter, and
`torch.testing._internal.common_utils` unconditionally does `import expecttest`
(several suites also use `hypothesis`). These packages are listed in PyTorch's
`src/requirements.txt` under "Install / Development extra requirements" — they are
NOT in `requirements-build.txt`, so a build-requirements-only install leaves the venv
unable to even collect the test suite, and every optimization cycle fails its gates
with `ModuleNotFoundError: expecttest` regardless of the change under test (observed:
14 of 15 iteration failures in one run).

**Constraint (conftest must stub the uncompiled distributed modules):** because the
build uses `USE_DISTRIBUTED=0`, `transformers.integrations.fsdp.is_fsdp_managed_module()`
(called during `model.generate()`) triggers `import torch.distributed.fsdp` →
`torch.testing._internal.distributed.fake_pg` → `torch._C._distributed_c10d`, which is
not compiled — an `ImportError` at inference time. The harness `tests/conftest.py` MUST
insert `sys.modules` stubs **before anything imports torch**: (1) a stub module for
`torch._C._distributed_c10d` exposing no-op `FakeProcessGroup` and `FakeStore` classes;
(2) a stub module for `torch.distributed.fsdp` exposing a no-op
`FullyShardedDataParallel` class; then, after `import torch.distributed`, bind the fsdp
stub as an attribute of `torch.distributed`. Do NOT replace the whole
`torch.distributed` module — partial replacement breaks other attribute access (e.g.
`torch.distributed.Backend`). This fix has been rediscovered by repair loops in two
separate runs; generate it up front.

**Constraint (transformers version):** pin `transformers` to a release verified to
import and run `generate()` against this CPU-only, `USE_DISTRIBUTED=0` source build
with the conftest stubs above. `transformers==4.47.1` is verified (archived
`codeweave-run` branch); prefer it over nearby releases unless the chosen version has
been re-verified against the build.
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
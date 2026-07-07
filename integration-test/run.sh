#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Set environment variables for offline operation during tests
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"
export TOKENIZERS_PARALLELISM="false"
export GENAI_MODEL="${GENAI_MODEL:-distilgpt2}"
export GENAI_MAX_SECONDS="${GENAI_MAX_SECONDS:-30}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-$(nproc)}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-$(nproc)}"
export ENABLE_PROFILER="${ENABLE_PROFILER:-0}"
export BASELINE_RUN_ID="${BASELINE_RUN_ID:-1}"

# Create output directories
mkdir -p "$SCRIPT_DIR/reports/energy"
mkdir -p "$SCRIPT_DIR/observability/traces"
mkdir -p "$SCRIPT_DIR/observability/profiles"
mkdir -p "$SCRIPT_DIR/flamegraphs"

echo "=== Integration Test Run ==="
echo "Model: $GENAI_MODEL"
echo "Max seconds: $GENAI_MAX_SECONDS"
echo "Run ID: ${BASELINE_RUN_ID:-1}"
echo "Profiler: ${ENABLE_PROFILER:-0}"
echo ""

# --- Measurement mode ---
# Explicit ENABLE_PROFILER=0 keeps baseline timing clean even when run.sh is
# invoked with ENABLE_PROFILER=1 (e.g. from the Phase 5 tracing pass).
echo "=== Measurement Mode ==="
ENABLE_PROFILER=0 BASELINE_RUN_ID="${BASELINE_RUN_ID:-1}" \
pytest "$SCRIPT_DIR/tests/test_inference_baseline.py" -m benchmark --tb=short --timeout=300

# --- Tracing mode ---
# Only execute when ENABLE_PROFILER=1 is set; py-spy wraps pytest externally
# and writes flamegraphs/python_flamegraph.svg. BASELINE_RUN_ID=trace prevents
# the test from writing to run-records.json during this pass. The profiled
# pytest run inside py-spy also writes reports/profiler-summary.md via
# torch.profiler key_averages (CPU op timing only). There is NO Chrome trace
# export and NO post-trace conversion: export_chrome_trace produces 200MB+
# JSON files that hang the trace converter for hours.
if [ "${ENABLE_PROFILER:-0}" = "1" ]; then
    echo ""
    echo "=== Tracing Mode (py-spy) ==="
    mkdir -p "$SCRIPT_DIR/flamegraphs"
    if command -v py-spy &>/dev/null; then
        BASELINE_RUN_ID=trace \
        py-spy record \
            --output "$SCRIPT_DIR/flamegraphs/python_flamegraph.svg" \
            --format flamegraph \
            -- python3 -m pytest "$SCRIPT_DIR/tests/test_inference_baseline.py" \
                -m benchmark --tb=short --timeout=300 \
            || echo "py-spy recording failed (check ptrace permissions); skipping"
    else
        echo "py-spy not found — install with: pip install py-spy"
    fi
fi

# --- Write benchmark summary ---
echo ""
echo "=== Writing Benchmark Summary ==="
python3 -c "
import datetime
import os

summary = []
summary.append('# Benchmark Summary\n')
summary.append(f'- **Model**: {os.environ.get(\"GENAI_MODEL\", \"distilgpt2\")}')
summary.append(f'- **Run ID**: {os.environ.get(\"BASELINE_RUN_ID\", \"1\")}')
summary.append(f'- **Profiler enabled**: {os.environ.get(\"ENABLE_PROFILER\", \"0\")}')
summary.append(f'- **Timestamp**: {datetime.datetime.now().isoformat()}')
summary.append(f'- **Max seconds**: {os.environ.get(\"GENAI_MAX_SECONDS\", \"30\")}')
summary.append('')

report_path = os.path.join('$SCRIPT_DIR', 'reports', 'benchmark-summary.md')
with open(report_path, 'w') as f:
    f.write('\n'.join(summary))
print(f'Summary written to {report_path}')
"

echo "=== Run complete ==="

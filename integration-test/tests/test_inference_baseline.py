"""Primary integration test: CPU text-generation inference benchmark.

Concern category: Bottlenecks
Exercises: Operator dispatch, memory allocation, autograd overhead in the
standard inference forward pass.
"""

import contextlib
import json
import os
import statistics
import time
import tracemalloc
from pathlib import Path

import pytest
import torch
from torch.profiler import ProfilerActivity, record_function

# ---------------------------------------------------------------------------
# Configuration (loaded from environment and files, never hardcoded)
# ---------------------------------------------------------------------------

INTEGRATION_TEST_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = INTEGRATION_TEST_DIR / "reports"
OBSERVABILITY_DIR = INTEGRATION_TEST_DIR / "observability"

GENAI_MODEL = os.getenv("GENAI_MODEL", "distilgpt2")
GENAI_MAX_SECONDS = int(os.getenv("GENAI_MAX_SECONDS", "30"))
ENABLE_PROFILER = os.getenv("ENABLE_PROFILER", "0") == "1"

# Run ID handling: digit string → int, otherwise keep as string
_raw_run_id = os.getenv("BASELINE_RUN_ID", "1")
RUN_ID = int(_raw_run_id) if _raw_run_id.isdigit() else _raw_run_id


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_inference_baseline(model_and_tokenizer, prompts):
    """Run the representative text-generation inference scenario.

    Hot loop runs until GENAI_MAX_SECONDS wall-clock time, exercising:
    - Tokenization (Python/C++ boundary)
    - Forward pass (operator dispatch, BLAS kernels)
    - Autoregressive sampling (memory allocation per token)
    - Output decoding (token decode overhead)
    """
    model, tokenizer = model_and_tokenizer

    # Ensure output directories exist
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OBSERVABILITY_DIR.mkdir(parents=True, exist_ok=True)
    (OBSERVABILITY_DIR / "profiles").mkdir(parents=True, exist_ok=True)

    # Set reproducible seed
    torch.manual_seed(42)

    # Configure lightweight torch.profiler (CPU only, no stack/shapes/memory)
    if ENABLE_PROFILER:
        profiler_ctx = torch.profiler.profile(
            activities=[ProfilerActivity.CPU],
        )
    else:
        profiler_ctx = contextlib.nullcontext()

    # Start tracemalloc (lightweight, always-on)
    tracemalloc.start()

    iteration_count = 0
    iteration_timings = []
    generated_outputs = []

    start_time = time.perf_counter()

    with torch.inference_mode():
        with profiler_ctx as prof:
            while (time.perf_counter() - start_time) < GENAI_MAX_SECONDS:
                prompt = prompts[iteration_count % len(prompts)]

                with record_function("sampling_loop_iteration"):
                    # Tokenize
                    with record_function("tokenize_input"):
                        inputs = tokenizer(
                            prompt, return_tensors="pt", padding=False, truncation=True
                        )
                        input_ids = inputs["input_ids"]

                    # Generate
                    iter_start = time.perf_counter()
                    output_ids = model.generate(
                        input_ids,
                        max_new_tokens=60,
                        do_sample=True,
                        temperature=0.7,
                        top_k=50,
                        repetition_penalty=1.3,
                    )

                    # Decode only newly generated tokens
                    with record_function("token_decode"):
                        new_token_ids = output_ids[0, input_ids.shape[1]:]
                        decoded = tokenizer.decode(new_token_ids, skip_special_tokens=True)

                iter_end = time.perf_counter()
                iter_ms = (iter_end - iter_start) * 1000

                iteration_timings.append(iter_ms)
                generated_outputs.append({
                    "run_id": RUN_ID,
                    "iteration": iteration_count,
                    "prompt": prompt,
                    "response": decoded,
                })
                iteration_count += 1

    total_elapsed = time.perf_counter() - start_time

    # Stop tracemalloc
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # --- Write profiler summary via key_averages (only when profiler is active) ---
    if ENABLE_PROFILER and prof is not None:
        profiler_summary = prof.key_averages().table(
            sort_by="self_cpu_time_total", row_limit=20
        )
        summary_path = REPORTS_DIR / "profiler-summary.md"
        with open(summary_path, "w") as f:
            f.write("# Profiler Summary (Top 20 by self CPU time)\n\n")
            f.write(f"Model: {GENAI_MODEL}  \n")
            f.write(f"Iterations: {iteration_count}  \n")
            f.write(f"Total inference time: {total_elapsed * 1000:.0f} ms  \n\n")
            f.write("```\n")
            f.write(profiler_summary)
            f.write("\n```\n")

    # --- Write generated outputs ---
    if isinstance(RUN_ID, int):
        outputs_path = REPORTS_DIR / f"generated-outputs-run{RUN_ID}.jsonl"
        with open(outputs_path, "w") as f:
            for entry in generated_outputs:
                f.write(json.dumps(entry) + "\n")

    # --- Write run record (only for integer run IDs) ---
    if isinstance(RUN_ID, int):
        run_records_path = REPORTS_DIR / "run-records.json"
        if run_records_path.exists():
            with open(run_records_path, "r") as f:
                records = json.load(f)
        else:
            records = []

        # Read energy data if available
        energy_joules = 0.0
        co2_grams = 0.0
        energy_dir = REPORTS_DIR / "energy"
        for energy_file in energy_dir.glob("*.json"):
            try:
                with open(energy_file) as f:
                    edata = json.load(f)
                    energy_joules = edata.get("energy_joules", 0.0)
                    co2_grams = edata.get("co2_grams", 0.0)
            except (json.JSONDecodeError, KeyError):
                pass

        mean_iter_ms = sum(iteration_timings) / len(iteration_timings) if iteration_timings else 0
        # Median is the v2 primary comparison metric: robust to the
        # first-iteration warmup outlier (lazy MKL init, allocator growth)
        median_iter_ms = statistics.median(iteration_timings) if iteration_timings else 0
        records.append({
            "run_id": RUN_ID,
            "wall_clock_ms": total_elapsed * 1000,
            "iterations": iteration_count,
            "mean_iter_ms": mean_iter_ms,
            "median_iter_ms": median_iter_ms,
            "energy_joules": energy_joules,
            "co2_grams": co2_grams,
            "memory_peak_mb": peak / (1024 * 1024),
        })

        with open(run_records_path, "w") as f:
            json.dump(records, f, indent=2)

    # Basic assertions to confirm the test ran correctly
    assert iteration_count > 0, "No iterations completed"
    assert total_elapsed >= min(GENAI_MAX_SECONDS * 0.8, GENAI_MAX_SECONDS - 2), (
        f"Test ended too early: {total_elapsed:.1f}s < {GENAI_MAX_SECONDS}s"
    )

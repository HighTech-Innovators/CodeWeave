# Domain Context

> **This file is optional.**
> Populate it with target-specific knowledge that helps Phase 3 design a representative scenario and identify meaningful observability focus areas.
> This context supplements the book and ADRs — it does not override what the source code and ADRs actually show.
> Delete or comment out any section that does not apply.

---

## Codebase Purpose

PyTorch is a machine learning framework that provides tensor computation and automatic differentiation, primarily used for neural network training and inference. Its CPU inference path — tensor dispatch, operator kernels, autograd graph traversal, and BLAS-backed linear algebra — is the primary subject of this analysis.

The representative use case is text-generation inference: a transformer-based language model receives tokenised input, executes a forward pass through its layers, and produces output tokens in a sampling loop. This exercises PyTorch's dispatch stack, memory allocator, and linear algebra backends end-to-end on CPU.

---

## Observability Focus Areas

- **Operator dispatch**: routes Python-level tensor operations to C++ kernels — high call frequency, low latency budget; dominant source of per-token overhead for small tensors
- **Autograd engine**: builds and traverses the computation graph — relevant even in `torch.no_grad()` contexts due to graph teardown overhead
- **Memory allocator**: tensor allocation and deallocation patterns — allocation pressure increases with sequence length and batch size
- **BLAS/MKL-DNN threading**: controls parallelism for matrix multiplications — thread pool saturation or underutilisation shows up as CPU underutilisation on multi-core runners
- **Python/C++ boundary crossings**: the overhead of each sampling step includes Python dispatch overhead; repeated for every generated token

---

## Representative Scenario Guidance

The integration scenario is a **CPU text-generation inference loop**. Phase 4 must generate this test such that all scenario parameters are loaded from configuration — not hardcoded. This preserves CodeWeave's generic character: swapping to a different model or prompt set requires only a configuration change, not a code change.

### Configuration sources

| Parameter | Source | Default |
|-----------|--------|---------|
| Model name | `GENAI_MODEL` environment variable | `distilgpt2` |
| Prompts | `integration-test/scenarios/prompts.json` (JSON array of strings) | 8 prompts below |
| Time limit (seconds) | `GENAI_MAX_SECONDS` environment variable | `30` |
| Generation seed | Hardcoded `torch.manual_seed(42)` | — |

Phase 4 must generate the `integration-test/scenarios/prompts.json` file containing the default prompt set below. This file is the hand-off point between scenario configuration and test code.

### Hot loop structure

```
load model (from GENAI_MODEL) and tokenizer — outside profiled scope
start cProfile, torch.profiler, tracemalloc
while wall_clock < GENAI_MAX_SECONDS:
    prompt = prompts[iteration % len(prompts)]
    tokenize(prompt) → input_ids
    model.generate(input_ids, max_new_tokens=60, do_sample=True, temperature=0.7,
                   top_k=50, repetition_penalty=1.3)
    decode newly generated tokens only
    accumulate iteration count and output log
stop cProfile, torch.profiler, tracemalloc
export Chrome trace (torch.profiler)
write cProfile stats
```

Energy tracking is handled by the `conftest.py` CodeCarbon fixture (per benchmark-marked test invocation).

### Default prompt set

Phase 4 writes the following to `integration-test/scenarios/prompts.json`:

```json
[
  "Today a museum curator took the morning train from Amsterdam to Rotterdam. She carried a folder of restoration notes and a thermos of cold coffee.",
  "Meanwhile a student with very little money was backpacking through Belgium, sleeping in hostels and eating bread from supermarket shelves.",
  "A startup founder in Berlin was on her third cup of espresso, debugging a production incident that had started at 3 am.",
  "In a small fishing village on the coast of Portugal, an elderly fisherman repaired his nets by hand while his grandson watched silently.",
  "A software engineer in Tokyo was refactoring a legacy codebase, removing a comment that said 'fix this later' written six years ago.",
  "A nurse finishing a night shift in a London hospital sat in the break room, staring at a lukewarm cup of tea, thinking about nothing in particular.",
  "A journalist in Cairo was transcribing an interview, pausing every few seconds to replay a phrase she could not quite hear on the recording.",
  "A retired teacher in rural France was writing a letter by hand to her former student, now living in Canada, about the summer storms that had flattened her garden."
]
```

These prompts exercise: tokenization with varying lengths, multi-layer forward pass, autoregressive sampling, and output decoding. They are replaceable by editing `integration-test/scenarios/prompts.json` — no code change required.

---

## Known Performance Hotspots

- Kernel dispatch overhead for small tensors — every token step calls many aten ops with small shapes
- Memory allocation in the generation loop — a new tensor is allocated per output token
- Autograd graph overhead — `torch.no_grad()` suppresses gradient tracking but not all associated overhead
- BLAS thread pool utilisation — `torch.set_num_threads()` behaviour under sustained load affects throughput reproducibility

---

## Out-of-Scope Subsystems

- CUDA/GPU backends: excluded by `constraints/project.md` (CPU-only execution)
- Distributed training (`torch.distributed`): out of scope for single-process inference analysis
- Model loading and tokenizer initialisation: excluded from the profiled hot loop (one-time setup cost, not inference bottleneck)
- Third-party vendored code under `third_party/` in the source tree: not owned by this project

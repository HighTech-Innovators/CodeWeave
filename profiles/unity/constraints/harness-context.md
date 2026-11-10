# Harness context — performance in Unity projects

Background for designing measurements and picking optimizations. Ground every concrete
claim about the target in its own code, book and ADRs.

## Where frame time goes

- **Main thread (CPU)**: scripts' `Update`/`LateUpdate`/`FixedUpdate`, coroutines,
  physics, animation, UI, culling and render-command setup. A CPU-side code change shows
  in main-thread CPU time first; frame time only moves if the frame is CPU-bound.
- **Render thread / GPU**: draw calls, batching, shader cost, overdraw, shadows,
  post-processing, resolution. Frame time is roughly the slower of CPU and GPU.
- **Background work**: Jobs, Burst, `Task`/`Parallel.For`, dedicated threads (e.g.
  simulation workers). Their cost reaches the frame through main-thread waits, budgets
  ("apply at most N per frame") and memory bandwidth.
- **Hitches**: garbage collection (allocations in per-frame paths: `new`, LINQ, boxing,
  closures, string building), synchronous loading or generation, mesh rebuilds,
  physics mesh baking. Medians hide hitches; the per-launch median is still the
  decision metric — note hitch-prone changes separately.

## Typical optimization targets

- Per-frame allocations in hot paths (reuse buffers/lists, avoid LINQ and closures).
- Repeated work each frame that could be cached or done on change only.
- `GetComponent`/`Find`/reflection in per-frame code.
- Algorithmic cost in simulation, generation, meshing or visibility (e.g. O(N²) loops).
- Main-thread work that could move to existing worker threads — only where the target's
  threading model allows it and results stay deterministic.
- Draw-call and batching improvements — but anything that can change what is drawn is a
  visible change and needs the target owner's approval.

## Runtimes

The Unity editor and player differ from the .NET SDK used for tests and benchmarks:
players run Mono (Boehm or incremental GC) or IL2CPP. JIT, GC and allocation costs
differ a lot; an allocation-reducing change can matter far more in the player than
under .NET. Benchmark on the player's runtime where the target supports it.

## Noise

- Fanless laptops slow down as they heat (tens of percent over minutes of uncapped
  rendering); launches of the same build differ by milliseconds; the first launch after
  a build runs with cold caches. The pipeline handles heat-soak, warm-up and A/B order —
  your scripts must keep each launch identical.
- V-sync and frame caps hide differences: self-test/measurement modes usually disable
  them; keep it that way.
- Retina/HiDPI: the window's backing resolution depends on the display; the pipeline
  records the display setup and refuses to compare across changes.

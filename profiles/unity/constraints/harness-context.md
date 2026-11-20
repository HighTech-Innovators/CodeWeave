# Harness context — performance in Unity projects

Unity's terms for the background above.

## Where frame time goes

- **Main thread**: scripts' `Update`/`LateUpdate`/`FixedUpdate`, coroutines, physics,
  animation, UI, culling and render-command setup.
- **Background work**: Jobs (`IJob*`), Burst (`[BurstCompile]`), `Task`/`Parallel.For`,
  dedicated threads. Unity APIs are main-thread only.
- **Hitches**: garbage collection from allocations in per-frame paths (`new`, LINQ,
  boxing, closures, string building).

## Typical optimization targets

- Per-frame allocations (reuse buffers/lists, avoid LINQ and closures in hot paths).
- `GetComponent`/`Find`/reflection in per-frame code.
- Batching that gives the same picture: SRP Batcher compatibility, GPU instancing.

## Runtimes

The Unity editor and player differ from the .NET SDK used for tests and benchmarks:
players run Mono (Boehm or incremental GC) or IL2CPP. JIT, GC and allocation costs
differ a lot; an allocation-reducing change can matter far more in the player than
under .NET. Benchmark on the player's runtime where the target supports it.

# Harness context — performance in rendering applications

Background for designing measurements and picking optimizations. Ground every concrete
claim about the target in its own code, book and ADRs.

## Where frame time goes

- **Main thread (CPU)**: per-frame and fixed-step game logic, physics, animation, UI,
  culling and render-command setup. A CPU-side code change shows in main-thread CPU time
  first; frame time only moves if the frame is CPU-bound.
- **Render thread / GPU**: draw calls, batching, shader cost, overdraw, shadows,
  post-processing, resolution. Frame time is roughly the slower of CPU and GPU.
- **Background work**: job systems, thread pools, dedicated threads (e.g. simulation
  workers). Their cost reaches the frame through main-thread waits, budgets ("apply at
  most N per frame") and memory bandwidth.
- **Hitches**: garbage collection or heap churn (allocations in per-frame paths),
  synchronous loading or generation, mesh rebuilds, physics mesh baking, shader
  compilation on first use. Medians hide hitches: a loading view can report a high
  percentile (e.g. `frame_p99_ms`) as a measure of its own; otherwise note hitch-prone
  changes separately.

## Where loading time goes

When content reaches full detail late (pop-in, coarse terrain or blurry textures that
swap as the player moves), the time between "needed" and "shown" is spent in:

- **Deciding and ordering**: which pieces are requested, in which order (nearest and in
  view first, or in scan order), how often the request list is rebuilt, and work
  requested and then thrown away when the player moves on.
- **Producing**: generating or reading the data, building meshes, collision and
  lower detail levels; often on worker threads, sometimes needlessly serial or repeated.
- **Handing over**: per-frame budgets ("apply at most N per frame", time slices) that
  leave the frame idle while work waits, main-thread steps between finished work and
  the GPU (mesh and texture uploads, material set-up, collider baking).
- **Waiting on something else**: a single queue shared with other work, locks, disk.

A faster path brings the same final detail sooner. Showing less detail, shrinking a
detail range or skipping content is a picture change, not a loading optimization.

## Typical optimization targets

- Per-frame allocations in hot paths (reuse buffers and lists).
- Repeated work each frame that could be cached or done on change only.
- Lookups, searches and reflection in per-frame code.
- Algorithmic cost in simulation, generation, meshing or visibility (e.g. O(N²) loops).
- Main-thread work that could move to existing worker threads — only where the target's
  threading model allows it and results stay deterministic.
- Render work whose result cannot be seen: objects outside the view, fully hidden,
  fogged out or smaller than a pixel; shadow casters whose shadow cannot be seen (e.g.
  underground, inside other shadow, below the shadow map's resolution); passes or
  render targets nobody reads. Skipping it lowers GPU time without changing the picture.
- CPU work the render pipeline waits for: render-command setup, culling, mesh and
  buffer uploads, per-frame material or property changes, synchronous GPU read-backs.
- Draw-call and batching improvements (instancing, fewer state changes) that give the
  same picture. Anything that can change what is drawn is a visible change and needs the
  target owner's approval.

An application capped by v-sync or a frame-rate limit spends saved frame time idle: the
same frame rate at lower power and heat, rather than more frames. Measured uncapped (as
self-test modes usually are), the saving shows as frame time — CPU time in a CPU-bound
view, frame time in a GPU-bound one.

## Runtimes

Where the shipped build runs differently from the development set-up (another compiler
or optimisation level, another managed runtime or garbage collector), benchmark on the
shipped runtime where the target supports it: allocation and call costs can differ a lot.

## Noise

- Fanless laptops slow down as they heat (tens of percent over minutes of uncapped
  rendering); launches of the same build differ by milliseconds; the first launch after
  a build runs with cold caches. The pipeline handles heat-soak, warm-up and A/B order —
  your scripts must keep each launch identical.
- V-sync and frame caps hide differences: self-test/measurement modes usually disable
  them; keep it that way.
- Retina/HiDPI: the window's backing resolution depends on the display; the pipeline
  records the display setup and refuses to compare across changes.

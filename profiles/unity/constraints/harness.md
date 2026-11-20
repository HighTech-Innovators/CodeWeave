# Harness constraints — Unity project

Unity's specifics for the harness rules above; where the two differ, follow these.

- **One Unity per project.** The Unity editor locks the project it opens: never start
  Unity yourself on a project the target's scripts open, and never a second one. Build
  and test through the target's own scripts (batch mode), which manage that.
- **`Library/`**: the pipeline seeds the target tree's `Library/` (the import cache)
  from the user's checkout before the first build; the first build may still re-import
  part of the project and take long.
- **Player runtime**: Unity players typically run **Mono** (often with the Boehm
  collector) or IL2CPP, not the .NET used for development. Benchmark on Mono where the
  target has a set-up for it; an allocation-reducing change can matter far more in the
  player than under .NET.
- **Engine-free code** is usually an assembly with no `UnityEngine` references, compiled
  outside Unity for tests (e.g. with `dotnet`). That is the code `bench.sh` times and
  `test.sh core` covers.
- **Tests**: Unity Test Runner suites are EditMode and PlayMode (NUnit), run in batch
  mode through the target's scripts; engine-free tests run outside Unity.

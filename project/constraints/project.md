# Constraints

This file pins the hard requirements for optimizing **your** target. CodeWeave does not
assume a language, runtime, or package manager, so everything specific to your codebase
lives here and the pipeline reads it from the generated manifest rather than hardcoding
it. Replace every placeholder below with your target's real values, and delete any section
that does not apply.

Write each constraint as a single imperative statement prefixed with `**Constraint:**` so
the harness-design and build phases can parse them individually. Keep the "why" attached to
anything non-obvious; several of these categories exist because a repair loop rediscovered
the same fix more than once.

**Constraint (runtime and scope):** State the runtime, backend, and hardware scope the
analysis targets, and exclude everything out of scope. Example shape: "Target the CPU
inference path only; exclude GPU, distributed, and quantization backends." Keeping the
scope narrow makes the baseline reproducible and the hotspot search tractable.

**Constraint (interpreter or toolchain version):** Pin the exact interpreter, compiler, or
SDK version the harness builds and runs against, and say how to obtain it. Pin a version
that has full prebuilt-artifact coverage for your dependency stack so the install does not
fall back to source builds against an unexpected toolchain. If the required version is not
present, the build script should fail with the exact install command rather than silently
using whatever is on PATH.

**Constraint (build prerequisites):** List any development headers, system libraries, or
build tools that must be installed before the target builds, especially ones not documented
in the target's own contributing guide. Missing prerequisites often fail silently by
disabling a component rather than erroring, so name each one and the symptom of its absence.

**Constraint (build configuration):** If the target is built from source, list the exact
build flags or environment variables to set and why each one matters. Prefer a table so the
build phase applies them unconditionally:

| Variable | Value | Why |
|---|---|---|
| `EXAMPLE_FLAG` | `1` | What breaks or slows down if it is left at its default |

Favor flags that disable out-of-scope features (GPU, distributed, optional backends) to cut
build time and shrink the surface the harness has to stub.

**Constraint:** Do not perform any GIT commits. These will be handled externally.

**Constraint (energy measurement):** Name the energy or emissions measurement tool the
integration tests must use and how to wire it in, so every benchmark run is instrumented the
same way. This is the project's core signal; do not leave it implicit.

**Constraint (test dependencies):** If the correctness gates run the target's own test
suite, list every package that suite needs to even be collected, not just to pass. Test
harnesses frequently import helper libraries at module load time, so a
build-requirements-only install can leave the venv unable to collect the suite at all, which
fails every optimization cycle regardless of the change under test.

**Constraint (harness shims for disabled features):** If your build configuration disables a
feature that the target still imports at runtime, describe the shim the harness must install
before anything imports the target, and describe it precisely enough to generate up front.
Partial stubs are usually safer than replacing a whole module, because downstream code often
reaches for unrelated attributes on the same module. This kind of fix tends to be
rediscovered by repair loops, so writing it here once saves cycles.

**Constraint (dependency version pins):** Pin any surrounding dependency (framework, model
runner, data library) to a release verified to import and run against your build
configuration, and record where that verification happened. Prefer a version you have
confirmed over a newer one you have not.

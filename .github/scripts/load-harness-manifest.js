#!/usr/bin/env node
// Load the harness toolchain manifest for the GHA workflows. Reads
// integration-test/harness-manifest.json (or argv[2]) and surfaces the toolchain
// values so the workflows do not hardcode a Python/pytest/venv toolchain.
//
// THE DEFAULTS BELOW are the source of truth for an absent or partial manifest —
// every field the manifest omits falls back to the value used today.
//
// Output (both, so either consumption style works):
//   - stdout: `export KEY='value'` lines, shell-quoted, for `eval "$(node …)"`
//     (used inside a single bash step, e.g. the Phase 4 smoke gate).
//   - $GITHUB_ENV (when set): raw `KEY=value` lines, so the values persist to
//     later steps in the same job (used by phase-5-6 / phase-7).
'use strict';
const fs = require('fs');
const path = require('path');

const D = {
  language: 'python',
  venv: { dir: '.venv', python: '.venv/bin/python', activate: '.venv/bin/activate' },
  smoke: {
    source_glob_dirs: ['tests', '_tools'],
    source_ext: 'py',
    compile_cmd: 'python3 -m py_compile',
    scripts: ['setup.sh', 'run.sh'],
    script_syntax_cmd: 'bash -n',
    collect_cmd: 'python3 -m pytest {tests_dir} --collect-only -q --no-header',
    collect_error_pattern: '^ERROR|collection error',
    collect_import_error_pattern: 'ModuleNotFoundError|ImportError',
    // import + trivial op run after an incremental build (Phase 7 gate 7a).
    import_op_cmd: 'import torch; torch.mm(torch.randn(4,4), torch.randn(4,4))',
  },
  // Incremental from-source rebuild used by Phase 7 (NOT build-source.sh, whose
  // idempotency would skip a rebuild of an uncommitted edit). `{py}` is substituted
  // with the venv interpreter; env is applied wholesale before the command.
  build: {
    env: { BUILD_TEST: '0', USE_CUDA: '0', USE_DISTRIBUTED: '0' },
    incremental_cmd: '{py} -m pip install --no-build-isolation -v -e .',
    native_source_ext: ['cpp', 'cc', 'c', 'h', 'hpp', 'cu'],
  },
  // Framework op-test suite for Phase 7 gate 7d (run with a `-k` pattern).
  op_suite: { file: 'test/test_ops.py' },
  profiler: { enable_env: 'ENABLE_PROFILER' },
  hotspot_report: { path: 'reports/profiler-summary.md' },
};

const file = process.argv[2] || path.join('integration-test', 'harness-manifest.json');
let m = D;
if (fs.existsSync(file)) {
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf-8'));
    // Shallow-merge per top-level key — a partial manifest overrides only the
    // fields it sets; everything else falls back to the built-in default.
    m = {
      language:       raw.language ?? D.language,
      venv:           { ...D.venv, ...(raw.venv || {}) },
      smoke:          { ...D.smoke, ...(raw.smoke || {}) },
      build:          { ...D.build, ...(raw.build || {}) },
      op_suite:       { ...D.op_suite, ...(raw.op_suite || {}) },
      profiler:       { ...D.profiler, ...(raw.profiler || {}) },
      hotspot_report: { ...D.hotspot_report, ...(raw.hotspot_report || {}) },
    };
  } catch (e) {
    process.stderr.write(`harness-manifest.json present but unreadable (${String(e.message).slice(0, 120)}) — using built-in defaults\n`);
  }
}

// KEY -> value pairs surfaced to the workflows.
const pairs = [
  ['HARNESS_LANGUAGE', m.language],
  ['HARNESS_VENV_DIR', m.venv.dir],
  ['HARNESS_VENV_PYTHON', m.venv.python],
  ['HARNESS_VENV_ACTIVATE', m.venv.activate],
  ['HARNESS_SMOKE_SOURCE_DIRS', m.smoke.source_glob_dirs.join(' ')],
  ['HARNESS_SMOKE_SOURCE_EXT', m.smoke.source_ext],
  ['HARNESS_SMOKE_COMPILE_CMD', m.smoke.compile_cmd],
  ['HARNESS_SMOKE_SCRIPTS', m.smoke.scripts.join(' ')],
  ['HARNESS_SMOKE_SCRIPT_SYNTAX_CMD', m.smoke.script_syntax_cmd],
  ['HARNESS_SMOKE_COLLECT_CMD', m.smoke.collect_cmd],
  ['HARNESS_SMOKE_COLLECT_ERROR_PATTERN', m.smoke.collect_error_pattern],
  ['HARNESS_SMOKE_COLLECT_IMPORT_ERROR_PATTERN', m.smoke.collect_import_error_pattern],
  ['HARNESS_SMOKE_IMPORT_OP_CMD', m.smoke.import_op_cmd],
  ['HARNESS_BUILD_ENV', Object.entries(m.build.env).map(([k, v]) => `${k}=${v}`).join(' ')],
  ['HARNESS_BUILD_INCREMENTAL_CMD', m.build.incremental_cmd],
  ['HARNESS_BUILD_NATIVE_SOURCE_EXT', m.build.native_source_ext.join(' ')],
  ['HARNESS_OP_SUITE_FILE', m.op_suite.file],
  ['HARNESS_PROFILER_ENABLE_ENV', m.profiler.enable_env],
  ['HARNESS_HOTSPOT_PATH', m.hotspot_report.path],
];

// stdout: shell-quoted `export` lines for `eval`.
const shq = (v) => `'${String(v).replace(/'/g, `'\\''`)}'`;
process.stdout.write(pairs.map(([k, v]) => `export ${k}=${shq(v)}`).join('\n') + '\n');

// $GITHUB_ENV: raw KEY=value (no values here contain newlines).
if (process.env.GITHUB_ENV) {
  fs.appendFileSync(process.env.GITHUB_ENV, pairs.map(([k, v]) => `${k}=${v}`).join('\n') + '\n');
}

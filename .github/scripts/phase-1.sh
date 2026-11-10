#!/usr/bin/env bash
# Phase 1 — Book generation.
#
# One subcommand per workflow step, so GitHub Actions (phase-1-book.yml) and
# run-local.sh run the same code. Run from the outer repository root with
# .github/.env (plus any local overrides) loaded into the environment.
#
#   clone    clone the target into src/ and create the work branch
#   iterate  generate → validate loop       outputs: manuscript_complete, iterations_run
#   pdf      build book.pdf                 output:  pdf_generated
#   index    build book/BOOK-INDEX.md       output:  book_index_built
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"

step_clone() {
  rm -rf src tools
  clone_target "$EXTERNAL_REPO_BRANCH"
  configure_target
  git -C src checkout -b "$EXTERNAL_REPO_WORK_BRANCH"
  exclude_from_outer "src/" "tools/"
}

step_iterate() {
  mkdir -p proof

  local COPILOT_PROMPT="Work on the task described in work/1-generate-book.md and constraints/project.md. Analyze ./src and make improvements according to the outlined goals."
  local BOOK_VALIDATE_PROMPT="Validate the book manuscript as described in work/1-validate-book.md and constraints/project.md. Do not write new chapters or modify existing chapter content."

  local MANUSCRIPT_COMPLETE=0 i=0 CURRENT_MODEL gen val
  for i in $(seq 1 "$PHASE1_MAX_ITERATIONS"); do
    CURRENT_MODEL=$(agent_model "$(resolve_model "$PHASE1_MODEL_SCHEDULE" "$i")")
    gen="proof/1-book-generation-$i.md"
    val="proof/1-book-validation-$i.md"

    group "Iteration $i / ${PHASE1_MAX_ITERATIONS} — Generate"
    echo "## Run $i [generate]" | tee "$gen"
    echo "Agent: $AGENT_CLI · Model: $CURRENT_MODEL" | tee -a "$gen"
    if [ "${DRY_RUN}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI generate" | tee -a "$gen"
    else
      agent_pass "$COPILOT_PROMPT" "$CURRENT_MODEL" "$gen" "proof/1-book-generation-session-$i.md"
    fi

    git add -A
    if git diff --cached --quiet; then
      echo "No generation changes in run $i" | tee -a "$gen"
      git commit -m "Phase 1: record book generation run $i"
    else
      git commit -m "Phase 1: book generation run $i"
    fi
    endgroup

    group "Iteration $i / ${PHASE1_MAX_ITERATIONS} — Validate"
    echo "## Run $i [validate]" | tee "$val"
    echo "Agent: $AGENT_CLI · Model: $CURRENT_MODEL" | tee -a "$val"
    if [ "${DRY_RUN}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI validate" | tee -a "$val"
    else
      # A failing validate pass is not fatal: no marker means another iteration.
      agent_pass "$BOOK_VALIDATE_PROMPT" "$CURRENT_MODEL" "$val" "proof/1-book-validation-session-$i.md" \
        || echo "WARNING: validate pass exited non-zero" | tee -a "$val"
    fi

    if [ -f "book/BOOK-VALIDATION.md" ]; then
      cp "book/BOOK-VALIDATION.md" "proof/1-book-validation-report-$i.md"
    fi

    if [ "${DRY_RUN}" = "true" ] && [ "$i" -eq 1 ]; then
      mkdir -p book
      touch book/manuscript-complete.md
    fi

    git add -A
    if git diff --cached --quiet; then
      git commit -m "Phase 1: record book validation run $i"
    else
      git commit -m "Phase 1: book validation run $i"
    fi
    endgroup

    if [ -f "book/manuscript-complete.md" ]; then
      echo "Manuscript complete after run $i — stopping Phase 1" | tee -a "$val"
      MANUSCRIPT_COMPLETE=1
      break
    fi
  done

  set_output manuscript_complete "$MANUSCRIPT_COMPLETE"
  set_output iterations_run "$i"
}

step_pdf() {
  if [ "${DRY_RUN}" = "true" ]; then
    echo "DRY RUN: skipping PDF build"
    set_output pdf_generated 0
    return
  fi
  if [ ! -f "book/manuscript-complete.md" ]; then
    echo "Manuscript not complete — skipping PDF build"
    set_output pdf_generated 0
    return
  fi

  local log="proof/pdf-build.md" PDF_GENERATED=0 f
  mkdir -p proof
  echo "Building PDF from manuscript..." | tee "$log"
  ensure_pdf_tools "$log"

  local CHAPTERS=()
  while IFS= read -r f; do CHAPTERS+=("$f"); done < <(ls book/[0-9][0-9]-*.md 2>/dev/null | sort -V)

  if [ "${#CHAPTERS[@]}" -eq 0 ]; then
    echo "ERROR: No numbered chapter files found (book/[0-9][0-9]-*.md)" | tee -a "$log"
  else
    echo "Assembling ${#CHAPTERS[@]} chapters" | tee -a "$log"
    build_pdf book.pdf "${EXTERNAL_REPO_NAME} — Architecture and Implementation" "$log" "${CHAPTERS[@]}"
    if [ -f "book.pdf" ]; then
      echo "PDF built successfully (${#CHAPTERS[@]} chapters)" | tee -a "$log"
      PDF_GENERATED=1
    else
      echo "ERROR: PDF build failed — see $log" | tee -a "$log"
    fi
  fi

  git add -A
  git commit -m "Phase 1: build book PDF"
  set_output pdf_generated "$PDF_GENERATED"
}

step_index() {
  local BOOK_INDEX_BUILT=0
  node .github/scripts/generate-indexes.js --generate-book-index 2>&1 | tee "proof/book-index.md" || true
  if [ -f "book/BOOK-INDEX.md" ]; then
    git add book/BOOK-INDEX.md
    if ! git diff --cached --quiet; then
      git commit -m "Phase 1: generate BOOK-INDEX.md"
      BOOK_INDEX_BUILT=1
    fi
  fi
  set_output book_index_built "$BOOK_INDEX_BUILT"
}

case "${1:-}" in
  clone)   step_clone ;;
  iterate) step_iterate ;;
  pdf)     step_pdf ;;
  index)   step_index ;;
  *) echo "usage: $0 clone|iterate|pdf|index" >&2; exit 2 ;;
esac

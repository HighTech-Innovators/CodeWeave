#!/usr/bin/env bash
# Phase 2 — ADR generation.
#
# One subcommand per workflow step, so GitHub Actions (phase-2-adr.yml) and
# run-local.sh run the same code. Run from the outer repository root with
# .github/codeweave.config (plus any local overrides) loaded into the environment.
#
# Everything Phase 2 writes into the target goes under src/codeweave-results/:
#   adr/<source dir>/ADR.md   one ADR per architectural unit (mirrors the source tree)
#   adr-scope.md              coverage map
#   ADR-VALIDATION.md         latest validator report
#   adrs-complete.md          completion marker (validator only)
#   ADR-INDEX.md              navigation index (generate-indexes.js)
#   book/, book.pdf, adr.pdf  copies made by `publish`
#
#   prereq       require book.pdf from Phase 1
#   clone        clone the target (work branch if it exists) into src/
#   iterate      generate → validate loop    outputs: adr_complete, iterations_run
#   pdf          build adr.pdf               output:  adr_pdf_built
#   index        build ADR-INDEX.md          output:  adr_index_built
#   publish      copy book + PDFs into src/codeweave-results/ and commit
#   push-target  push the work branch to the target remote
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"

step_prereq() {
  if [ "${DRY_RUN}" = "true" ]; then
    echo "DRY RUN: creating stub book.pdf to satisfy prerequisite"
    touch book.pdf
  elif [ ! -f "book.pdf" ]; then
    echo "ERROR: book.pdf not found — Phase 1 must complete successfully before Phase 2"
    exit 1
  fi
  echo "Prerequisites satisfied: book.pdf found"
}

step_clone() {
  rm -rf src tools
  # Try the work branch first (resume scenario); fall back to the source branch.
  clone_target "$EXTERNAL_REPO_WORK_BRANCH" 2>/dev/null || clone_target "$EXTERNAL_REPO_BRANCH"
  configure_target
  git -C src checkout "$EXTERNAL_REPO_WORK_BRANCH" 2>/dev/null || git -C src checkout -b "$EXTERNAL_REPO_WORK_BRANCH"
  git -C src remote set-url origin "$(target_push_url)"
  exclude_from_outer "src/" "tools/"
}

step_iterate() {
  mkdir -p proof "$CW_RESULTS"

  local ADR_PROMPT="Work on the task described in work/2-generate-adrs.md and constraints/project.md. Generate ADRs for ./src using ./book as reference. Write every file you create in the target under ./src/${CW_RESULTS_DIR}/ only."
  local ADR_VALIDATE_PROMPT="Validate ADR coverage as described in work/2-validate-adrs.md and constraints/project.md. Do not write new ADRs or modify existing ADR content."

  local ADR_COMPLETE=0 j=0 CURRENT_MODEL gen val
  for j in $(seq 1 "$PHASE2_MAX_ITERATIONS"); do
    CURRENT_MODEL=$(agent_model "$(resolve_model "$PHASE2_MODEL_SCHEDULE" "$j")")
    gen="proof/2-adrs-generation-$j.md"
    val="proof/2-adrs-validation-$j.md"

    if [ -f "$CW_RESULTS/adrs-complete.md" ]; then
      rm "$CW_RESULTS/adrs-complete.md"
      echo "WARNING: Removed stale adrs-complete.md before run $j — only the validator may write this file" | tee -a "$gen"
    fi

    group "Iteration $j / ${PHASE2_MAX_ITERATIONS} — Generate"
    echo "## ADR Run $j [generate]" | tee "$gen"
    echo "Agent: $AGENT_CLI · Model: $CURRENT_MODEL" | tee -a "$gen"
    if [ "${DRY_RUN}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI ADR generate" | tee -a "$gen"
    else
      agent_pass "$ADR_PROMPT" "$CURRENT_MODEL" "$gen" "proof/2-adrs-generation-session-$j.md"
    fi
    keep_target_changes_in_results "$gen"

    git -C src add -A
    if git -C src diff --cached --quiet; then
      echo "No ADR changes in run $j" | tee -a "$gen"
    else
      git -C src commit -m "Phase 2: ADR generation run $j"
    fi
    git add proof/
    git commit -m "Phase 2: record ADR generation run $j"
    endgroup

    group "Iteration $j / ${PHASE2_MAX_ITERATIONS} — Validate"
    echo "## ADR Run $j [validate]" | tee "$val"
    echo "Agent: $AGENT_CLI · Model: $CURRENT_MODEL" | tee -a "$val"
    if [ "${DRY_RUN}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI ADR validate" | tee -a "$val"
    else
      # A failing validate pass is not fatal: no marker means another iteration.
      agent_pass "$ADR_VALIDATE_PROMPT" "$CURRENT_MODEL" "$val" "proof/2-adrs-validation-session-$j.md" \
        || echo "WARNING: validate pass exited non-zero" | tee -a "$val"
    fi
    keep_target_changes_in_results "$val"

    if [ -f "$CW_RESULTS/ADR-VALIDATION.md" ]; then
      cp "$CW_RESULTS/ADR-VALIDATION.md" "proof/2-adrs-validation-report-$j.md"
    fi

    if [ "${DRY_RUN}" = "true" ] && [ "$j" -eq 1 ]; then
      touch "$CW_RESULTS/adrs-complete.md"
    fi

    git -C src add -A
    if git -C src diff --cached --quiet; then
      echo "No validation changes in run $j" | tee -a "$val"
    else
      git -C src commit -m "Phase 2: ADR validation run $j"
    fi
    git add proof/
    git commit -m "Phase 2: record ADR validation run $j"
    endgroup

    if [ -f "$CW_RESULTS/adrs-complete.md" ]; then
      echo "ADR coverage complete after run $j — stopping Phase 2" | tee -a "$val"
      ADR_COMPLETE=1
      break
    fi
  done

  set_output adr_complete "$ADR_COMPLETE"
  set_output iterations_run "$j"
}

step_pdf() {
  if [ "${DRY_RUN}" = "true" ]; then
    echo "DRY RUN: skipping ADR PDF build"
    set_output adr_pdf_built 0
    return
  fi

  local log="proof/adr-pdf-build.md" ADR_PDF_BUILT=0 f
  local ADR_FILES=()
  mkdir -p proof
  if [ -d "$CW_RESULTS/adr" ]; then
    while IFS= read -r f; do ADR_FILES+=("$f"); done < <(find "$CW_RESULTS/adr" -name 'ADR.md' | sort)
  fi

  if [ "${#ADR_FILES[@]}" -eq 0 ]; then
    echo "No ADR.md files found under $CW_RESULTS/adr — skipping ADR PDF build" | tee "$log"
    set_output adr_pdf_built 0
    return
  fi

  echo "Building ADR PDF (${#ADR_FILES[@]} files)..." | tee "$log"
  ensure_pdf_tools "$log"
  build_pdf adr.pdf "${EXTERNAL_REPO_NAME} — Architecture Decision Records" "$log" "${ADR_FILES[@]}"

  if [ -f "adr.pdf" ]; then
    echo "ADR PDF built successfully (${#ADR_FILES[@]} ADRs)" | tee -a "$log"
    ADR_PDF_BUILT=1
  else
    echo "ERROR: ADR PDF build failed — see $log" | tee -a "$log"
  fi

  git add -A
  git commit -m "Phase 2: build ADR PDF"
  set_output adr_pdf_built "$ADR_PDF_BUILT"
}

step_index() {
  local ADR_INDEX_BUILT=0
  node .github/scripts/generate-indexes.js --generate-adr-index 2>&1 | tee "proof/adr-index.md" || true

  if [ "${DRY_RUN}" = "true" ] && [ ! -f "$CW_RESULTS/ADR-INDEX.md" ]; then
    echo "DRY RUN: creating stub $CW_RESULTS/ADR-INDEX.md" | tee -a "proof/adr-index.md"
    mkdir -p "$CW_RESULTS"
    echo "# ADR Index (dry-run stub)" > "$CW_RESULTS/ADR-INDEX.md"
  fi

  if [ -f "book/BOOK-INDEX.md" ]; then
    git add book/BOOK-INDEX.md
    if ! git diff --cached --quiet; then
      git commit -m "Phase 2: update BOOK-INDEX.md"
    fi
  fi

  if [ -f "$CW_RESULTS/ADR-INDEX.md" ]; then
    git -C src add "$CW_RESULTS_DIR/ADR-INDEX.md"
    if ! git -C src diff --cached --quiet; then
      git -C src commit -m "Phase 2: generate ADR-INDEX.md"
      ADR_INDEX_BUILT=1
    fi
  fi

  set_output adr_index_built "$ADR_INDEX_BUILT"
}

step_publish() {
  # The book and PDFs are built in the outer repository; copy them next to the
  # ADRs so the target's work branch carries every CodeWeave document.
  mkdir -p "$CW_RESULTS"
  # The target's own .gitattributes may treat unknown files as text
  # (`* text=auto`); PDFs must never get line-ending conversion or text diffs.
  printf '%s\n' '# CodeWeave output: PDFs are binary (overrides the repository'"'"'s text rules here).' \
    '*.pdf binary' > "$CW_RESULTS/.gitattributes"
  if [ -d book ]; then
    rm -rf "$CW_RESULTS/book"
    cp -R book "$CW_RESULTS/book"
    rm -rf "$CW_RESULTS/book/_tools"
  fi
  local pdf
  for pdf in book.pdf adr.pdf; do
    if [ -s "$pdf" ]; then cp "$pdf" "$CW_RESULTS/$pdf"; fi
  done

  cat > "$CW_RESULTS/README.md" <<EOF
# CodeWeave results

Generated by CodeWeave on $(date +%Y-%m-%d), analysing branch \`${EXTERNAL_REPO_BRANCH}\`.
CodeWeave writes only inside this folder; the rest of the repository is unchanged.

| Path | Contents |
|---|---|
| \`book/\` | Architecture book: numbered chapters, \`BOOK-INDEX.md\`, analysis maps in \`book/_generated/\` |
| \`book.pdf\` | The book as one PDF |
| \`adr/<folder>/ADR.md\` | One Architecture Decision Record per architectural unit; the path mirrors the source folder |
| \`ADR-INDEX.md\` | Index of every ADR with its role |
| \`adr.pdf\` | All ADRs as one PDF |
| \`adr-scope.md\` | Which folders are covered, passed through or excluded, and why |
| \`ADR-VALIDATION.md\` | The validator's latest report |
EOF

  git -C src add -A "$CW_RESULTS_DIR"
  if git -C src diff --cached --quiet; then
    echo "Nothing new to publish into $CW_RESULTS"
  else
    git -C src commit -m "CodeWeave: publish book and PDFs into ${CW_RESULTS_DIR}/"
  fi
}

step_push_target() {
  git -C src push origin "HEAD:${EXTERNAL_REPO_WORK_BRANCH}"
}

case "${1:-}" in
  prereq)      step_prereq ;;
  clone)       step_clone ;;
  iterate)     step_iterate ;;
  pdf)         step_pdf ;;
  index)       step_index ;;
  publish)     step_publish ;;
  push-target) step_push_target ;;
  *) echo "usage: $0 prereq|clone|iterate|pdf|index|publish|push-target" >&2; exit 2 ;;
esac

#!/usr/bin/env bash
# teardown.sh RUN_DIR SRC — stop anything CodeWeave started for this run and left
# behind: programs whose executable lives in the run folder (builds launched for
# measuring or self-tests, e.g. an app bundle's binary). Engine profiles replace this
# hook to also stop editors opened on the run's project (see profiles/unity/hooks/).
# Nothing outside RUN_DIR is touched; interpreters running scripts from the run folder
# (bash, python) are not matched, because their executable lives elsewhere.
RUN_DIR="$1"
pids=$(ps -axo pid=,command= | awk -v d="$RUN_DIR/" '
  { pid = $1; sub(/^[[:space:]]*[0-9]+[[:space:]]+/, ""); if (index($0, d) == 1) print pid }')
[ -n "$pids" ] || exit 0
echo "teardown: stopping $(echo "$pids" | wc -w | tr -d ' ') leftover process(es) from $RUN_DIR"
# shellcheck disable=SC2086
kill -TERM $pids 2> /dev/null || true
sleep 5
# shellcheck disable=SC2086
kill -KILL $pids 2> /dev/null || true
exit 0

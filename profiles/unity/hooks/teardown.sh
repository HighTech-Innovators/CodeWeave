#!/usr/bin/env bash
# teardown.sh RUN_DIR SRC — stop anything CodeWeave started for this run and left
# behind: players launched from the run folder, and Unity editors (e.g. a
# kept-open test Unity) whose project lives in the run folder. Nothing outside
# RUN_DIR is touched.
RUN_DIR="$1"
pids=$(ps -axo pid=,command= | awk -v d="$RUN_DIR/" '
  index($0, d) && ($0 ~ /\.app\/Contents\/MacOS\// || $0 ~ /-projectPath/) { print $1 }')
[ -n "$pids" ] || exit 0
echo "teardown: stopping $(echo "$pids" | wc -w | tr -d ' ') leftover process(es) from $RUN_DIR"
# shellcheck disable=SC2086
kill -TERM $pids 2> /dev/null || true
sleep 5
# shellcheck disable=SC2086
kill -KILL $pids 2> /dev/null || true
exit 0

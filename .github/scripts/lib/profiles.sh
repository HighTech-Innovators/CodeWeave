# Profile chains. Sourced by assemble-constraints.sh and run-local.sh. Bash 3.2 compatible.
#
# A profile (profiles/<name>/) may build on another one: its profile.env names it with
#   PROFILE_BASE=<name>
# e.g. unity builds on rendering. Every layer adds to the one below it and wins where the
# two differ: constraints are appended, prompts and hooks of the same name replace the
# base's, integrity patterns are added (and `-kind` lines remove one of the base's), and
# profile.env settings override the base's (a target's own target.env overrides them all).

# profile_setting DIR KEY — KEY's value in DIR/profile.env (empty if unset). Read, not sourced.
profile_setting() {
  [ -f "$1/profile.env" ] || return 0
  sed -n "s/^[[:space:]]*$2=//p" "$1/profile.env" | tail -1 | sed -e 's/[[:space:]]*#.*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

# profile_chain DIR — the profile folders from the deepest base up to DIR, one per line.
# Fails on an unknown base or a cycle.
profile_chain() {
  local dir="$1" root base chain="" n=0
  root="$(cd "$(dirname "$dir")" && pwd)"
  dir="$root/$(basename "$dir")"
  while :; do
    [ -d "$dir" ] || { echo "ERROR: no profile at $dir" >&2; return 1; }
    n=$((n + 1))
    [ $n -le 8 ] || { echo "ERROR: profile chain too deep or cyclic (at $(basename "$dir"))" >&2; return 1; }
    chain="$dir${chain:+
$chain}"
    base="$(profile_setting "$dir" PROFILE_BASE)"
    [ -n "$base" ] || break
    dir="$root/$base"
  done
  echo "$chain"
}

# profile_chain_names DIR — the same chain as names, e.g. "rendering+unity".
profile_chain_names() {
  profile_chain "$1" | while IFS= read -r d; do basename "$d"; done | paste -sd+ -
}

#!/bin/bash
# SessionStart hook. Whatever this prints on exit 0 is added to Claude's context, so it prints this
# side's hand-written handoff (see handoff-file.sh; both sides' on a branch of neither side) and then
# the auto-generated snapshot, each capped separately at 20 lines, saying so when a section is cut.
# If none of the files exists it prints nothing. Always exits 0.

exec 2>/dev/null  # a hook must never fail loudly
cat >/dev/null  # the hook JSON on stdin is not needed

project="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$project" ]; then
  project=$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)
fi
limit=20

section() {
  # $1: path relative to the project, $2: section title. Prints nothing for a missing or empty file.
  local relative=$1 title=$2 file total
  file="$project/$relative"
  [ -s "$file" ] || return 0
  total=$(awk 'END { print NR }' "$file" 2>/dev/null)
  echo "## $title ($relative)"
  head -n "$limit" "$file" 2>/dev/null
  # head leaves no newline if the file's last kept line had none; keep the next line separate.
  [ -n "$(tail -c 1 "$file" 2>/dev/null)" ] && [ "$total" -le "$limit" ] && echo
  if [ "$total" -gt "$limit" ]; then
    echo "… ($((total - limit)) more lines cut; see $relative)"
  fi
  echo
}

. "$(dirname "$0")/handoff-file.sh" || exit 0
handoff=$(handoff_file "$project")
if [ -n "$handoff" ]; then
  section "$handoff" "Handoff"
else
  section .claude/state/handoff-frontend.md "Frontend handoff (this branch is neither adit/ nor jayden/)"
  section .claude/state/handoff-backend.md "Backend handoff (this branch is neither adit/ nor jayden/)"
fi
section .claude/state/snapshot.md "Snapshot"

exit 0

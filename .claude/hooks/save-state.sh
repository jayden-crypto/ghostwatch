#!/bin/bash
# PreCompact hook. Writes .claude/state/snapshot.md (git-ignored, machine-local) and nothing else:
# it never touches .claude/state/handoff.md. Reads the hook JSON on stdin. Always exits 0, so a
# failure here can never block a compaction.

exec 2>/dev/null  # a hook must never fail loudly; errors here only mean a missing snapshot
input=$(cat)

project="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$project" ]; then
  project=$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)
fi
state="$project/.claude/state"
handoff="$state/handoff.md"
snapshot="$state/snapshot.md"
mkdir -p "$state" 2>/dev/null || exit 0

trigger=""
if command -v jq >/dev/null 2>&1; then
  trigger=$(printf '%s' "$input" | jq -r '.trigger // empty' 2>/dev/null)
else
  trigger=$(printf '%s' "$input" | sed -n 's/.*"trigger"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
fi
[ -n "$trigger" ] || trigger="unknown"

age() {
  # Seconds -> "just now", "5 minutes ago", "1 hour ago", "3 days ago".
  local seconds=$1 count unit
  if [ "$seconds" -lt 60 ]; then echo "just now"; return; fi
  if [ "$seconds" -lt 3600 ]; then count=$((seconds / 60)); unit=minute
  elif [ "$seconds" -lt 86400 ]; then count=$((seconds / 3600)); unit=hour
  else count=$((seconds / 86400)); unit=day
  fi
  [ "$count" -eq 1 ] && echo "1 $unit ago" || echo "$count ${unit}s ago"
}

if [ -f "$handoff" ]; then
  # GNU stat (Linux, Git Bash on Windows) first: there `stat -f` means "file system", prints several
  # lines and fails. BSD stat (macOS) rejects -c with no output, and then -f %m gives the mtime.
  mtime=$(stat -c %Y "$handoff" 2>/dev/null)
  case "$mtime" in '' | *[!0-9]*) mtime=$(stat -f %m "$handoff" 2>/dev/null) ;; esac
  case "$mtime" in '' | *[!0-9]*) mtime="" ;; esac
  if [ -n "$mtime" ]; then
    handoff_age=$(age $(( $(date +%s) - mtime )))
  else
    handoff_age="unknown"
  fi
else
  handoff_age="never (no .claude/state/handoff.md)"
fi

tmp="$snapshot.tmp.$$"
{
  if git -C "$project" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$project" rev-parse --abbrev-ref HEAD 2>/dev/null)
    status=$(git -C "$project" status --porcelain 2>/dev/null)
    tracked=$(printf '%s\n' "$status" | grep -v '^??' | grep -v '^$')
    tracked_count=$(printf '%s\n' "$tracked" | grep -c -v '^$')
    untracked_count=$(printf '%s\n' "$status" | grep -c '^??')

    echo "# Snapshot: $(date -u +%Y-%m-%dT%H:%MZ), trigger $trigger, branch $branch (auto-generated; do not edit)"
    echo "Handoff last updated: $handoff_age"
    if [ "$tracked_count" -eq 0 ]; then
      echo "## Tracked changes: none. Untracked files: $untracked_count"
    elif [ "$tracked_count" -gt 10 ]; then
      echo "## Tracked changes: $tracked_count, first 10 shown. Untracked files: $untracked_count"
      printf '%s\n' "$tracked" | head -n 10
    else
      echo "## Tracked changes: $tracked_count. Untracked files: $untracked_count"
      printf '%s\n' "$tracked"
    fi
    echo "## Recent commits"
    git -C "$project" log --oneline -5 2>/dev/null
  else
    echo "# Snapshot: $(date -u +%Y-%m-%dT%H:%MZ), trigger $trigger (auto-generated; do not edit)"
    echo "Handoff last updated: $handoff_age"
    echo "Not a git repository: $project"
  fi
} > "$tmp" 2>/dev/null && mv -f "$tmp" "$snapshot" 2>/dev/null
rm -f "$tmp" 2>/dev/null

exit 0

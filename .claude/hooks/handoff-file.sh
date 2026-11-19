#!/bin/bash
# Sourced by save-state.sh and rehydrate.sh. Each side keeps its own committed handoff, chosen from
# the branch: adit/* and feature/adit-* use handoff-frontend.md, jayden/* and feature/jayden-* use
# handoff-backend.md. Any other branch (main, contract/*, a detached HEAD) belongs to neither side.

# $1: project dir. Prints the handoff path relative to the project, or nothing for a branch of neither side.
handoff_file() {
  case "$(git -C "$1" rev-parse --abbrev-ref HEAD 2>/dev/null)" in
    adit/* | feature/adit-*) echo ".claude/state/handoff-frontend.md" ;;
    jayden/* | feature/jayden-*) echo ".claude/state/handoff-backend.md" ;;
  esac
}

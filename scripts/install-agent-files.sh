#!/usr/bin/env bash
# install-agent-files.sh — link finresearch's agent documentation into every
# supported coding agent's expected location, for THIS checkout.
#
# Convention matrix:
#   Codex (OpenAI)   -> AGENTS.md at repo root (reads it natively)
#   Grok Build       -> AGENTS.md at repo root (project rules)
#   pi               -> AGENTS.md at repo root
#   Hermes           -> AGENTS.md at repo root (cron/workdir context loading)
#   Claude Code      -> CLAUDE.md at repo root  (symlink -> AGENTS.md, keeps one source)
#                       + .claude/skills/finresearch (project skill -> skills/finresearch)
#   Cursor & friends -> .cursor/rules/finresearch.mdc (alwaysApply rule that
#                       points at AGENTS.md; agents.md ecosystem covers the rest)
#
# Idempotent: re-running repairs/refreshes links. Symlinks keep the docs
# single-sourced — edit AGENTS.md, every agent sees the update.
set -euo pipefail

cd "$(dirname "$0")/.."       # script lives in scripts/; go to repo root
if [ ! -f AGENTS.md ]; then   # fallback: derive from git in case of a rerun elsewhere
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" && cd "$ROOT" || true
fi

if [ ! -f AGENTS.md ]; then
  echo "error: AGENTS.md not found next to this script — run from the repo root" >&2
  exit 1
fi

linked=0
link() {  # link <target> <linkname>
  local target="$1" name="$2"
  if [ -e "$name" ] || [ -L "$name" ]; then
    rm -f "$name"                       # refresh (docs are in git; safe)
  fi
  ln -s "$target" "$name"
  echo "  linked $name -> $target"
  linked=$((linked + 1))
}

echo "Installing agent doc links for finresearch:"

# Codex / Grok / pi / Hermes read AGENTS.md directly at repo root — nothing to do.
echo "  AGENTS.md             read natively by: codex, grok, pi, hermes"

# Claude Code
link AGENTS.md CLAUDE.md
mkdir -p .claude/skills
link ../../skills/finresearch .claude/skills/finresearch

# Cursor (and other rule-loader agents that want a rules dir)
mkdir -p .cursor/rules
cat > .cursor/rules/finresearch.mdc <<'EOF'
---
description: finresearch agent guidance (canonical source: AGENTS.md)
alwaysApply: true
---
Read and follow AGENTS.md at the repository root: how to use the tool, project
overview, setup and verify commands, architecture map, unit contracts
(percent-coded scan filters, currency threading, EDGAR UA rule), the output
contract, commit and release conventions, and known weak spots. The complete
usage guide for the CLI is skills/finresearch/SKILL.md.
EOF
echo "  wrote   .cursor/rules/finresearch.mdc (points at AGENTS.md)"
linked=$((linked + 1))

echo "Done — $linked link/rule targets in place. Git tracks the symlinks."
echo "Note: AGENTS.md itself is committed; CLAUDE.md is a symlink committed as such."
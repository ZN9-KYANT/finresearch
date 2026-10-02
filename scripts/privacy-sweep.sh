#!/usr/bin/env bash
# privacy-sweep.sh — scan the finresearch tree (default) or full git history
# (--history) for personal/identifying tokens.
#
# Tokens are NEVER stored in the repo — that would embed identifiers in the
# very tool meant to scrub them. Supply them via, in order:
#   1. $FINRESEARCH_SWEEP_TOKENS   (whitespace/newline-separated)
#   2. ~/.config/finresearch/sweep-tokens.txt (one token per line; override
#      the location with FINRESEARCH_SWEEP_TOKEN_FILE)
#
# With no tokens configured the sweep cannot know what to look for, so a
# fresh clone passes with a loud SKIP. With tokens configured it must print
# SWEEP CLEAN or it exits 1 and blocks the commit/release.
#
# Usage:
#   ./scripts/privacy-sweep.sh             # working tree
#   ./scripts/privacy-sweep.sh --history   # every blob reachable from any ref,
#                                          # plus commit/tag identities + messages
#
# Scope note: --history sees LOCAL refs only. A hosting remote (GitHub) keeps
# force-pushed-over commits reachable by SHA after a history rewrite, so a
# CLEAN result here does not cover them: recreate the remote repo (or have
# the host purge it) after rewriting history that ever held personal data.
set -euo pipefail

cd "$(dirname "$0")/.."

load_tokens() {
  if [ -n "${FINRESEARCH_SWEEP_TOKENS:-}" ]; then
    printf '%s\n' $FINRESEARCH_SWEEP_TOKENS
    return 0
  fi
  local file="${FINRESEARCH_SWEEP_TOKEN_FILE:-$HOME/.config/finresearch/sweep-tokens.txt}"
  if [ -f "$file" ]; then
    grep -v '^#' "$file" | grep -v '^[[:space:]]*$'
    return 0
  fi
  return 1
}

if ! TOKENS=$(load_tokens); then
  echo "SWEEP SKIPPED — no tokens configured (FINRESEARCH_SWEEP_TOKENS or"
  echo "  ~/.config/finresearch/sweep-tokens.txt). Put your personal tokens"
  echo "  there; never commit them to the repo."
  exit 0
fi

clean=1
report() { echo "HIT [$1]: $2"; clean=0; }

if [ "${1:-}" = "--history" ]; then
  # commit + tag metadata: author/committer/tagger identities and messages
  META=$(git log --all --format='%H %an <%ae> | %cn <%ce> | %B' 2>/dev/null
         git for-each-ref refs/tags \
           --format='%(refname) %(taggername) %(taggeremail) %(contents)' 2>/dev/null)
  while IFS= read -r tok; do
    [ -z "$tok" ] && continue
    if printf '%s\n' "$META" | grep -iqF -- "$tok"; then
      report "$tok" "commit/tag metadata (author, committer, tagger or message)"
    fi
    while IFS= read -r c; do
      if git grep -IilFq "$tok" "$c" -- . 2>/dev/null; then
        report "$tok" "history commit $c"
      fi
    done < <(git rev-list --all)
  done <<EOF
$TOKENS
EOF
else
  EXCLUDES=(--exclude-dir=.venv --exclude-dir=.git --exclude-dir=dist
            --exclude-dir=build --exclude-dir=.ruff_cache --exclude-dir=.pytest_cache)
  while IFS= read -r tok; do
    [ -z "$tok" ] && continue
    while IFS= read -r f; do
      report "$tok" "$f"
    done < <(grep -rIliF "$tok" . "${EXCLUDES[@]}" 2>/dev/null || true)
  done <<EOF
$TOKENS
EOF
fi

if [ "$clean" -eq 1 ]; then
  echo "SWEEP CLEAN ($(printf '%s\n' "$TOKENS" | grep -c .) tokens, ${1:-tree} mode)"
  exit 0
else
  echo "SWEEP FAILED — fix hits above before proceeding"
  exit 1
fi
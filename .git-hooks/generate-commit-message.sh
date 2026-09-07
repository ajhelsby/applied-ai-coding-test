#!/bin/bash

set -euo pipefail

COMMIT_MSG_FILE="${1:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

DEBUG_LOG=".commit_msg_hook_debug.log"

MAX_DIFF_CHARS=12000
MAX_SUBJECT_CHARS=100

ALLOWED_TYPES="feat|fix|chore|perf|docs|build|deps|ci|refactor|style|test"

# Files that generally aren't useful when generating a
# commit message and can make the request unnecessarily large.
EXCLUDED_FILES=(
    ':(exclude).git-hooks/generate-commit-message.sh'
    ':(exclude)package-lock.json'
    ':(exclude)yarn.lock'
    ':(exclude)pnpm-lock.yaml'
    ':(exclude)*.snap'
    ':(exclude)*.min.js'
    ':(exclude)*.min.css'
    ':(exclude)*.map'
)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$DEBUG_LOG"
}

fail() {
    log "ERROR: $*"
    echo "❌ $*" >&2
    exit 1
}

# ------------------------------------------------------------
# Initial validation
# ------------------------------------------------------------

if [[ -z "$COMMIT_MSG_FILE" ]]; then
    fail "Commit message file was not provided."
fi

if [[ -z "$OPENAI_API_KEY" ]]; then
    fail "OPENAI_API_KEY environment variable is not set."
fi

if ! command -v jq >/dev/null 2>&1; then
    fail "jq is required. Install it with: brew install jq"
fi

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 is required."
fi

# ------------------------------------------------------------
# Initialise debug log
# ------------------------------------------------------------

: > "$DEBUG_LOG"

log "Starting commit message generation"

# ------------------------------------------------------------
# 1. Get current branch
# ------------------------------------------------------------

BRANCH=$(git branch --show-current)

if [[ -z "$BRANCH" ]]; then
    fail "Unable to determine current branch."
fi

log "Branch: $BRANCH"

# Expected formats:
#
#   feat/#123
#   feat/#123-add-export
#   fix/#456-fix-expiry-date
#   refactor/#789-simplify-authentication
#
# Allowed types:
#
#   feat
#   fix
#   chore
#   perf
#   docs
#   build
#   deps
#   ci
#   refactor
#   style
#   test

if [[ ! "$BRANCH" =~ ^($ALLOWED_TYPES)/#([0-9]+)(-.*)?$ ]]; then

    echo ""
    echo "❌ Invalid branch name: $BRANCH"
    echo ""
    echo "Expected format:"
    echo "  feat/#123-description"
    echo "  fix/#456-description"
    echo ""
    echo "Allowed types:"
    echo "  feat"
    echo "  fix"
    echo "  chore"
    echo "  perf"
    echo "  docs"
    echo "  build"
    echo "  deps"
    echo "  ci"
    echo "  refactor"
    echo "  style"
    echo "  test"
    echo ""

    exit 1
fi

COMMIT_TYPE="${BASH_REMATCH[1]}"
ISSUE_NUMBER="${BASH_REMATCH[2]}"
BRANCH_DESCRIPTION="${BASH_REMATCH[3]:-}"

# Remove leading "-" from branch description
BRANCH_DESCRIPTION="${BRANCH_DESCRIPTION#-}"

log "Commit type: $COMMIT_TYPE"
log "Issue number: #$ISSUE_NUMBER"
log "Branch description: $BRANCH_DESCRIPTION"

# ------------------------------------------------------------
# 2. Get staged diff
# ------------------------------------------------------------

RAW_DIFF=$(git diff --cached -- \
    . \
    "${EXCLUDED_FILES[@]}")

if [[ -z "$RAW_DIFF" ]]; then
    echo "No staged changes found."
    log "No staged changes detected."
    exit 0
fi

log "Raw diff size: ${#RAW_DIFF} characters"

# ------------------------------------------------------------
# 3. Get list of changed files
#
# This gives the AI useful context without requiring it to
# infer everything from the diff.
# ------------------------------------------------------------

CHANGED_FILES=$(git diff --cached --name-status -- \
    . \
    "${EXCLUDED_FILES[@]}" || true)

log "Changed files:"
log "$CHANGED_FILES"

# ------------------------------------------------------------
# 4. Limit very large diffs
#
# This keeps API costs predictable and prevents huge generated
# files from being sent to the model.
# ------------------------------------------------------------

if (( ${#RAW_DIFF} > MAX_DIFF_CHARS )); then

    DIFF="${RAW_DIFF:0:$MAX_DIFF_CHARS}

[Diff truncated after $MAX_DIFF_CHARS characters.]"

    log "Diff truncated from ${#RAW_DIFF} to ${#DIFF} characters."

else

    DIFF="$RAW_DIFF"

fi

# ------------------------------------------------------------
# 5. Build JSON payload
#
# Python is used here so we don't have to manually escape
# quotes, newlines, backslashes, etc.
# ------------------------------------------------------------

PAYLOAD=$(python3 - "$COMMIT_TYPE" "$ISSUE_NUMBER" "$BRANCH_DESCRIPTION" "$CHANGED_FILES" "$DIFF" <<'PY'
import json
import sys

commit_type = sys.argv[1]
issue_number = sys.argv[2]
branch_description = sys.argv[3]
changed_files = sys.argv[4]
diff = sys.argv[5]

system_prompt = """You write concise Git commit message descriptions.

Return ONLY the human-readable description of the change.

Rules:
- Do NOT include the commit type.
- Do NOT include the issue number.
- Do NOT include a scope.
- Do NOT include quotes.
- Do NOT include markdown.
- Do NOT include a trailing period.
- Use imperative wording where natural.
- Be specific about what changed.
- Keep it under 100 characters.
"""

user_prompt = f"""Generate a concise commit description for this change. Max 80 characters.

Branch description:
{branch_description or "(none)"}

Changed files:
{changed_files}

Git diff:
{diff}
"""

payload = {
    "model": "gpt-4.1-nano",
    "messages": [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_prompt
        }
    ],
    "max_tokens": 40,
    "temperature": 0
}

print(json.dumps(payload))
PY
)

log "OpenAI payload created."
log "Sending request to OpenAI."

# ------------------------------------------------------------
# 6. Call OpenAI
# ------------------------------------------------------------

RESPONSE=$(curl -sS \
    --fail \
    --max-time 30 \
    https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD") || fail "OpenAI API request failed."

log "OpenAI request completed."

# ------------------------------------------------------------
# 7. Extract AI response
# ------------------------------------------------------------

AI_MESSAGE=$(echo "$RESPONSE" | jq -r '.choices[0].message.content // empty')

if [[ -z "$AI_MESSAGE" ]]; then

    ERROR=$(echo "$RESPONSE" | jq -r '.error.message // "Unknown OpenAI error"')

    fail "OpenAI did not return a commit description: $ERROR"
fi

log "AI returned a commit description."

# ------------------------------------------------------------
# 8. Clean AI response
# ------------------------------------------------------------

# Remove carriage returns/newlines
AI_MESSAGE=$(echo "$AI_MESSAGE" | tr '\r\n' ' ')

# Collapse repeated whitespace
AI_MESSAGE=$(echo "$AI_MESSAGE" | sed 's/[[:space:]]\+/ /g')

# Trim leading/trailing whitespace
AI_MESSAGE=$(echo "$AI_MESSAGE" | sed 's/^ *//;s/ *$//')

# Remove accidental surrounding quotes
AI_MESSAGE="${AI_MESSAGE#\"}"
AI_MESSAGE="${AI_MESSAGE%\"}"

# Remove accidental trailing period
AI_MESSAGE="${AI_MESSAGE%.}"

if [[ -z "$AI_MESSAGE" ]]; then
    fail "AI returned an empty commit description."
fi

# ------------------------------------------------------------
# 9. Protect against AI returning a full conventional commit
#
# Ideally the AI won't do this, but if it does, strip the
# metadata rather than creating:
#
# feat(#123): feat(#123): add something
# ------------------------------------------------------------

if [[ "$AI_MESSAGE" =~ ^(feat|fix|chore|perf|docs|build|deps|ci|refactor|style|test)\(\#[0-9]+\):[[:space:]]* ]]; then

    AI_MESSAGE=$(echo "$AI_MESSAGE" | sed -E \
        's/^(feat|fix|chore|perf|docs|build|deps|ci|refactor|style|test)\(\#[0-9]+\):[[:space:]]*//')

fi

# ------------------------------------------------------------
# 10. Validate description length
# ------------------------------------------------------------

if (( ${#AI_MESSAGE} > MAX_SUBJECT_CHARS )); then
    fail "AI generated a description longer than ${MAX_SUBJECT_CHARS} characters."
fi

# ------------------------------------------------------------
# 11. Construct final commit message
#
# IMPORTANT:
#
# The # is deliberately retained because GitHub turns #123
# into a clickable issue reference.
# ------------------------------------------------------------

FINAL_MESSAGE="${COMMIT_TYPE}(#${ISSUE_NUMBER}): ${AI_MESSAGE}"

log "Final message: $FINAL_MESSAGE"

# ------------------------------------------------------------
# 12. Validate final commit message
# ------------------------------------------------------------

if [[ ! "$FINAL_MESSAGE" =~ ^(feat|fix|chore|perf|docs|build|deps|ci|refactor|style|test)\(\#[0-9]+\):\ .+ ]]; then
    fail "Generated commit message failed validation: $FINAL_MESSAGE"
fi

if (( ${#FINAL_MESSAGE} > 200 )); then
    fail "Generated commit message exceeds 200 characters."
fi

# ------------------------------------------------------------
# 13. Write final message
#
# This deliberately OVERWRITES anything that was supplied via
# git commit -m.
# ------------------------------------------------------------

printf '%s\n' "$FINAL_MESSAGE" > "$COMMIT_MSG_FILE"

log "Commit message written successfully."
log "SUCCESS: $FINAL_MESSAGE"

echo ""
echo "Generated commit message:"
echo "$FINAL_MESSAGE"
echo ""

exit 0
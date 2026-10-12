#!/usr/bin/env bash
# secret-sweep.sh — scan this repo (working tree + full git history) for
# secrets before flipping it public.
#
# Usage:
#   ./common/secret-sweep.sh            scan everything, exit 1 on HIGH findings
#   ./common/secret-sweep.sh --strict   exit 1 on REVIEW findings too
#   ./common/secret-sweep.sh <path>     scan only <path> (working tree only)
#
# Findings are split into:
#   HIGH   — keys, tokens, credentials. Fix before going public.
#   REVIEW — private IPs / internal hostnames. Common in homelab code;
#            decide case-by-case whether they belong in a public repo.
#
# NOTE: this scans the local clone. Before going public, make sure your local
# clone is up to date (git pull) and also eyeball `git log -p` for anything
# the patterns miss — no scanner catches everything.

set -u

STRICT=0
ONLY_PATH=""
for arg in "$@"; do
    case "$arg" in
        --strict) STRICT=1 ;;
        -h|--help)
            sed -n '2,24p' "$0"
            exit 0 ;;
        *) ONLY_PATH="$arg" ;;
    esac
done

# ---- patterns (extended regex) ----
HIGH_PATTERNS=(
    'AKIA[0-9A-Z]{16}'                                    # AWS access key
    'ghp_[A-Za-z0-9]{36,}'                               # GitHub classic token
    'gho_[A-Za-z0-9]{36,}'                               # GitHub OAuth token
    'github_pat_[A-Za-z0-9_]{22,}'                       # GitHub fine-grained PAT
    'xox[baprs]-[A-Za-z0-9-]{10,}'                       # Slack token
    'AIza[0-9A-Za-z_-]{35}'                              # Google API key
    'sk-(live|test)-[A-Za-z0-9]{16,}'                    # Stripe-style key
    '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY'     # private key material
    '[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd][^[:alnum:]_]{0,3}[:=][[:space:]]*[^[:space:]"'"'"']{3,}'
    '[Pp][Aa][Ss][Ss][Ww][Dd][^[:alnum:]_]{0,3}[:=][[:space:]]*[^[:space:]"'"'"']{3,}'
    '[Ss][Ee][Cc][Rr][Ee][Tt][^[:alnum:]_]{0,3}[:=][[:space:]]*[^[:space:]"'"'"']{3,}'
    '[Aa][Pp][Ii][_ ]?[Kk][Ee][Yy][^[:alnum:]_]{0,3}[:=][[:space:]]*[^[:space:]"'"'"']{6,}'
    '[Tt][Oo][Kk][Ee][Nn][^[:alnum:]_]{0,3}[:=][[:space:]]*[^[:space:]"'"'"']{6,}'
)
REVIEW_PATTERNS=(
    '\b192\.168\.[0-9]{1,3}\.[0-9]{1,3}\b'               # RFC1918
    '\b10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b'
    '\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}\b'
    '[A-Za-z0-9_.-]+\.(local|lan|home|internal)\b'        # internal hostnames
)

high_hits=0
review_hits=0

# Scan a byte stream from stdin; $1 = label for findings.
# grep -I skips binary data automatically.
scan_stream() {
    local label="$1" pat kind line
    for pat in "${HIGH_PATTERNS[@]}"; do
        kind="HIGH"
        while IFS= read -r line; do
            printf '  [%s] %s\n' "$kind" "$line"
            high_hits=$((high_hits + 1))
        done < <(grep -nE -I "$pat" 2>/dev/null | sed "s|^|$label:|")
    done
    for pat in "${REVIEW_PATTERNS[@]}"; do
        kind="REVIEW"
        while IFS= read -r line; do
            printf '  [%s] %s\n' "$kind" "$line"
            review_hits=$((review_hits + 1))
        done < <(grep -nE -I "$pat" 2>/dev/null | sed "s|^|$label:|")
    done
}

is_git_repo() { git rev-parse --git-dir >/dev/null 2>&1; }

echo "== secret-sweep =="

if [ -n "$ONLY_PATH" ]; then
    echo "-- scanning path: $ONLY_PATH (working tree only)"
    if [ -d "$ONLY_PATH" ]; then
        while IFS= read -r -d '' f; do
            scan_stream "worktree:$f" < "$f"
        done < <(grep -rIlZE --exclude-dir=.git -e '' "$ONLY_PATH" 2>/dev/null)
    elif [ -f "$ONLY_PATH" ]; then
        scan_stream "worktree:$ONLY_PATH" < "$ONLY_PATH"
    else
        echo "path not found: $ONLY_PATH" >&2; exit 2
    fi
else
    echo "-- scanning working tree"
    while IFS= read -r -d '' f; do
        scan_stream "worktree:$f" < "$f"
    done < <(grep -rIlZE --exclude-dir=.git -e '' . 2>/dev/null)

    if is_git_repo; then
        echo "-- scanning git history ($(git rev-list --count --all 2>/dev/null || echo 0) commits)"
        # Walk every blob reachable from history; fine for small repos.
        # (stdin comes from the process substitution, so the blob stream
        #  fed to scan_stream below cannot steal the loop's input.)
        while read -r sha rest; do
            [ -z "$rest" ] && continue
            case "$rest" in *.png|*.jpg|*.jpeg|*.gif|*.zip|*.tar*|*.gz) continue ;; esac
            scan_stream "history:$rest@$sha" < <(git cat-file -p "$sha" 2>/dev/null)
        done < <(git rev-list --objects --all 2>/dev/null)
    else
        echo "-- not a git repo; skipping history scan"
    fi
fi

echo
echo "Summary: $high_hits HIGH finding(s), $review_hits REVIEW finding(s)."
if [ "$high_hits" -gt 0 ]; then
    echo "Result: FAIL — fix HIGH findings before going public."
    exit 1
elif [ "$review_hits" -gt 0 ] && [ "$STRICT" -eq 1 ]; then
    echo "Result: FAIL (--strict: REVIEW findings treated as failures)."
    exit 1
elif [ "$review_hits" -gt 0 ]; then
    echo "Result: PASS with notes — review the REVIEW items."
    exit 0
else
    echo "Result: PASS — no findings."
    exit 0
fi

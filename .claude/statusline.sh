#!/bin/sh
# Claude Code statusline: profile, model, cwd, git branch/dirty count,
# context %, session usage %, and reset time — each with an icon + color.
#
# Session usage comes straight off the live statusLine JSON payload
# (rate_limits.five_hour), which Claude Code refreshes on every render —
# NOT from the cachedUsageUtilization blob in <config>/.claude.json, which
# only updates when something (e.g. /usage) explicitly refetches it and can
# sit stale for many minutes.

script_dir=$(dirname "$0")
input=$(cat)

RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
MAGENTA='\033[35m'
CYAN='\033[36m'
BLUE='\033[34m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
GRAY='\033[90m'

# --- gather values: one python pass over the live JSON payload ---
fields=$(printf '%s' "$input" | python "$script_dir/statusline_fields.py" 2>/dev/null)
IFS='	' read -r model ctx_raw sess reset_epoch <<EOF
$fields
EOF

branch=$(git --no-optional-locks rev-parse --abbrev-ref HEAD 2>/dev/null)
dirty=$(git --no-optional-locks status --porcelain 2>/dev/null | wc -l | tr -d ' ')
dir=$(basename "$PWD")

cfgdir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
profile=$(printf '%s' "$cfgdir" | sed 's#.*[\\/]##')
profile=${profile#config-}
[ -n "$profile" ] && profile="claude-$profile"

reset=""
[ -n "$reset_epoch" ] && reset=$(date -d "@$reset_epoch" +"%H:%M" 2>/dev/null)

# fallback for older Claude Code builds whose statusLine payload has no
# rate_limits block yet: fall back to the profile's cached usage snapshot,
# flagged with its age since that path really can be stale.
age_min=""
if [ -z "$sess" ]; then
  cfgfile="$cfgdir/.claude.json"
  if [ -f "$cfgfile" ]; then
    flat=$(tr -d '\n' < "$cfgfile")
    block=$(printf '%s' "$flat" | grep -o '"kind": "session"[^}]*}' | head -1)
    sess=$(printf '%s' "$block" | sed -n 's/.*"percent": *\([0-9]*\).*/\1/p')
    reset_raw=$(printf '%s' "$block" | sed -n 's/.*"resets_at": *"\([^"]*\)".*/\1/p')
    [ -n "$reset_raw" ] && reset=$(date -d "$reset_raw" +"%H:%M" 2>/dev/null)

    fetched_ms=$(printf '%s' "$flat" | sed -n 's/.*"fetchedAtMs": *\([0-9]*\).*/\1/p' | head -1)
    if [ -n "$fetched_ms" ]; then
      now_ms=$(date +%s%3N)
      age_min=$(awk -v now="$now_ms" -v fetched="$fetched_ms" 'BEGIN { printf "%.0f", (now - fetched) / 60000 }' 2>/dev/null)
    fi
  fi
fi

# round context % to 1 decimal place
ctx=""
[ -n "$ctx_raw" ] && ctx=$(printf '%.1f' "$ctx_raw" 2>/dev/null)

# --- color grading for percentages: green < 50, yellow < 80, red >= 80 ---
pct_color() {
  v=$(printf '%.0f' "$1" 2>/dev/null)
  [ -z "$v" ] && v=0
  if [ "$v" -ge 80 ]; then printf '%s' "$RED"
  elif [ "$v" -ge 50 ]; then printf '%s' "$YELLOW"
  else printf '%s' "$GREEN"
  fi
}

SEP="${DIM} |${RESET}"
out=""

if [ -n "$profile" ]; then
  out="${BOLD}${MAGENTA}\xf0\x9f\x91\xa4 ${profile}${RESET}"
fi

if [ -n "$model" ]; then
  seg="${CYAN}\xf0\x9f\xa4\x96 ${model}${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

seg="${BLUE}\xf0\x9f\x93\x81 ${dir}${RESET}"
out="${out}${out:+ $SEP }${seg}"

if [ -n "$branch" ]; then
  seg="${GREEN}\xf0\x9f\x8c\xbf ${branch}${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

if [ -n "$dirty" ] && [ "$dirty" != "0" ]; then
  seg="${YELLOW}\xe2\x9c\x8e +${dirty}${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

if [ -n "$ctx" ]; then
  c=$(pct_color "$ctx")
  seg="${c}\xf0\x9f\x93\x8a ctx ${ctx}%${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

if [ -n "$sess" ]; then
  c=$(pct_color "$sess")
  age_note=""
  if [ -n "$age_min" ]; then
    if [ "$age_min" -ge 10 ]; then
      c="$GRAY"
      age_note=" (${age_min}m stale)"
    elif [ "$age_min" -ge 1 ]; then
      age_note=" (${age_min}m ago)"
    fi
  fi
  seg="${c}\xe2\x8f\xb3 sess ${sess}%${age_note}${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

if [ -n "$reset" ]; then
  seg="${GRAY}\xf0\x9f\x95\x92 resets ${reset}${RESET}"
  out="${out}${out:+ $SEP }${seg}"
fi

printf "%b" "$out"

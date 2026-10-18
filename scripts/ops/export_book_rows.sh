#!/usr/bin/env bash
# v161 trade scout: the read-only book export. It runs ON THE VM, piped over
# stdin through ssh-hetzner.sh from the dev machine (Git Bash):
#   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" \
#       < scripts/ops/export_book_rows.sh > "$SCRATCH/rows.csv"
#   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rejections" \
#       < scripts/ops/export_book_rows.sh > "$SCRATCH/rejections.csv"
#
# rows:       one psql session, opened READ ONLY, one COPY ... TO STDOUT (CSV
#             with a header): every closed trade (journal x trades, left-joined
#             to its plan), then every plan not represented by those rows.
#             psql's \copy must fit on one line; COPY ... TO STDOUT sent from
#             psql is the same client-side stream, and it is a read.
# rejections: grep of the HOST logs for "plan rejected (", reduced to
#             date,reason,count. Each file's first timestamp goes to stderr so
#             the current-versus-rotated coverage is visible.
#
# Nothing here writes: no interpreter, no repository helper, no file on the VM.
# The output columns are fixed; tests/scout/test_export_script.py pins them.
# Everything sits in functions run by the last line, so bash has parsed the
# whole script before anything runs: this script arrives on stdin, and no
# child process may read the rest of it.
# SWING_BOT_DIR / BOOK_LOGS_DIR are test seams; a real run takes the defaults.
set -euo pipefail

export_rows() {
  docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1 <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
SET TIME ZONE 'UTC';
COPY (
  SELECT
    'trade'::text AS row_kind,
    j.trade_id AS trade_id,
    t.doc->>'plan_id' AS plan_id,
    t.ticker AS ticker,
    t.strategy AS strategy,
    t.horizon AS horizon,
    t.direction AS direction,
    p.created_at::text AS plan_created_at,
    (p.doc->'status_history'->0)->>'at' AS plan_first_status_at,
    p.status AS plan_status,
    (p.doc->'status_history'->(-1))->>'reason' AS plan_status_reason,
    p.doc->>'entry_type' AS entry_type,
    p.doc->>'expiry_bars' AS expiry_bars,
    p.valid_session AS valid_session,
    p.doc->>'trigger_price' AS planned_entry,
    t.opened_at::text AS opened_at,
    t.entry::text AS entry,
    t.stop_loss::text AS stop_loss,
    t.doc->>'take_profit' AS take_profit,
    t.doc->>'target2' AS target2,
    j.closed_at::text AS closed_at,
    t.doc->>'exit_price' AS exit_price,
    t.doc->>'close_reason' AS close_reason,
    (t.doc->'legs'->(-1))->>'reason' AS last_leg_reason,
    j.outcome AS outcome,
    j.doc->>'r_realized' AS r_realized,
    j.doc->>'mfe_r' AS mfe_r,
    j.doc->>'mae_r' AS mae_r,
    j.doc->>'exit_efficiency' AS exit_efficiency,
    j.doc->>'holding_days' AS holding_days,
    j.doc->'risk_features'->>'stop_width_atr' AS stop_width_atr,
    j.doc->'risk_features'->>'atr_pct' AS atr_pct,
    j.doc->'risk_features'->>'regime2_state' AS regime2_state,
    j.doc->'risk_features'->>'session_bucket' AS session_bucket,
    j.doc->'risk_features'->>'days_to_earnings' AS days_to_earnings,
    j.doc->'risk_features'->>'rs_percentile' AS rs_percentile
  FROM journal_entries j
  JOIN trades t ON t.trade_id = j.trade_id
  LEFT JOIN plans p ON p.plan_id = t.doc->>'plan_id'
  WHERE j.closed_at IS NOT NULL
  UNION ALL
  SELECT
    'plan'::text AS row_kind,
    NULL::text AS trade_id,
    p.plan_id AS plan_id,
    p.ticker AS ticker,
    p.strategy AS strategy,
    p.horizon_key AS horizon,
    p.doc->>'direction' AS direction,
    p.created_at::text AS plan_created_at,
    (p.doc->'status_history'->0)->>'at' AS plan_first_status_at,
    p.status AS plan_status,
    (p.doc->'status_history'->(-1))->>'reason' AS plan_status_reason,
    p.doc->>'entry_type' AS entry_type,
    p.doc->>'expiry_bars' AS expiry_bars,
    p.valid_session AS valid_session,
    p.doc->>'trigger_price' AS planned_entry,
    NULL::text AS opened_at,
    NULL::text AS entry,
    NULL::text AS stop_loss,
    NULL::text AS take_profit,
    NULL::text AS target2,
    NULL::text AS closed_at,
    NULL::text AS exit_price,
    NULL::text AS close_reason,
    NULL::text AS last_leg_reason,
    NULL::text AS outcome,
    NULL::text AS r_realized,
    NULL::text AS mfe_r,
    NULL::text AS mae_r,
    NULL::text AS exit_efficiency,
    NULL::text AS holding_days,
    NULL::text AS stop_width_atr,
    NULL::text AS atr_pct,
    NULL::text AS regime2_state,
    NULL::text AS session_bucket,
    NULL::text AS days_to_earnings,
    NULL::text AS rs_percentile
  FROM plans p
  WHERE NOT EXISTS (
    SELECT 1
    FROM trades t2
    JOIN journal_entries j2 ON j2.trade_id = t2.trade_id
    WHERE t2.doc->>'plan_id' = p.plan_id
      AND j2.closed_at IS NOT NULL
  )
  ORDER BY 1 DESC, 21, 8, 2, 3
) TO STDOUT WITH (FORMAT csv, HEADER true);
SQL
}

export_rejections() {
  local logs="${BOOK_LOGS_DIR:-/opt/swing-bot/logs}"
  local f first rc
  local -a files=()
  for f in "$logs"/*.log*; do
    [ -f "$f" ] || continue
    [ -r "$f" ] || { echo "export_book_rows: unreadable log $f" >&2; return 2; }
    first=$(head -c 19 "$f") || { echo "export_book_rows: cannot read log $f" >&2; return 2; }
    files+=("$f")
    echo "export_book_rows: $f starts $first" >&2
  done
  [ "${#files[@]}" -gt 0 ] || { echo "export_book_rows: no readable log files in $logs" >&2; return 2; }
  echo "date,reason,count"
  { grep -h "plan rejected (" "${files[@]}" || { rc=$?; [ "$rc" -eq 1 ] || return "$rc"; }; } \
    | sed -n 's/^\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\) .*plan rejected (\([^,)]*\).*/\1,\2/p' \
    | LC_ALL=C sort | uniq -c \
    | awk '{ n = $1; sub(/^ *[0-9]+ /, ""); print $0 "," n }'
}

main() {
  cd "${SWING_BOT_DIR:-/opt/swing-bot}"
  case "${1:-}" in
    rows) export_rows ;;
    rejections) export_rejections ;;
    *) echo "usage: bash -s -- rows|rejections" >&2; exit 2 ;;
  esac
}

main "$@"

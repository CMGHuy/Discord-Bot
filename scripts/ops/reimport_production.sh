#!/bin/bash
# Re-import every migrated store from JSON into PostgreSQL, then verify.
#
# Safe to re-run: every importer is an idempotent upsert and is read-only
# against its JSON source. DB_STORES is not touched, so nothing reads the
# database and JSON remains the source of truth throughout.
#
# Order is a correctness requirement: starred_plans.plan_id is a foreign key
# into plans (revision p2_006), and account's balance is derived from realised
# P&L in trades.
#
# Run it from WSL:
#   wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 bash -s' \
#     < scripts/ops/reimport_production.sh
#
# Every `docker compose exec -T` redirects stdin from /dev/null: this script
# arrives over stdin itself, and an exec that reads stdin eats the rest of it.
set +e
cd /opt/swing-bot || exit 1

failed=0
for name in watchlist state plans starred trades account journal; do
  echo "=== ${name} ==="
  docker compose exec -T bot python scripts/db/import_${name}.py </dev/null 2>&1 | tail -8
  rc=${PIPESTATUS[0]}
  echo "   exit=${rc}"
  [ "$rc" != "0" ] && failed=1
done

echo
echo "======== PARITY (authoritative) ========"
docker compose exec -T bot python scripts/db/parity_report.py --all </dev/null 2>&1 | tail -40
parity_rc=${PIPESTATUS[0]}
echo "   parity exit=${parity_rc}"

echo
echo "======== COUNTS ========"
docker compose exec -T db psql -U swingbot -d swingbot -tAc \
  "select 'trades='||(select count(*) from trades)
       ||' plans='||(select count(*) from plans)
       ||' journal='||(select count(*) from journal_entries)
       ||' signal_state='||(select count(*) from signal_state)
       ||' watchlist='||(select count(*) from watchlist)
       ||' starred='||(select count(*) from starred_plans)
       ||' acct_hist='||(select count(*) from account_balance_history);" \
  </dev/null 2>&1 | head -5

exit $(( failed || parity_rc ))

# Notification delivery loss evidence — 2026-10-28

Scope: source-level operational harvest headroom, not MFE, a backtest, production incident frequency or a pooled performance claim. No trading threshold changes are proposed.

At origin/main 8bc11d60 and v194 worktree 1694c92b, notification producer/consumer and queue paths match. trade_commands.py queues plan_transition snapshots with PlanStatus.CLOSED/CANCELLED (uppercase). loops.py drains all rows and forwards them to notify_closed_trades. lifecycle_embeds.py filters to lowercase win/loss/closed, so plan_transition rows cannot be delivered through this path. notify_queue.py uses DELETE RETURNING before network I/O; channel/send failures are swallowed in lifecycle_embeds.py and the caller logs Posted using the input count.

Reproduction by source trace: enqueue a plan_transition CLOSED snapshot; drain it; evaluate the consumer status predicate; it is rejected and no pending row remains. For a lowercase closed trade, raise during channel resolution/send after drain; no acknowledgement or requeue exists. These traces establish reachable delivery gaps, not measured real-world loss rates. The implementation must turn both into executable database-backed regression cases before claiming recovery.

This evidence supports restoring existing actionable notifications (Edge harvest), not changing exits or claiming an expectancy improvement. No MFE measurement applies to a delivery-contract repair; this applicability distinction must be reviewed by the spec panel rather than borrowing an unrelated trading result.

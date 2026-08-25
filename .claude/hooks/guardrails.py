"""PreToolUse guardrails -- enforce this repo's token rules at the moment of
the mistake rather than relying on CLAUDE.md having been recalled.

Rules encode what CLAUDE.md and .ignore already state. If a rule and
CLAUDE.md ever disagree, CLAUDE.md wins and the rule is what gets fixed.

Design: evaluate() is pure and does no I/O beyond os.path.getsize, so the
whole rule set is unit-tested in tests/hooks/test_guardrails.py without a
live session. Anything unrecognised returns None -- silent allow. A
guardrail that blocks legitimate work costs more than the habit it prevents.
"""
import json
import sys


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def _warn(message: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }, "additionalContext": message}


# Populated by Tasks 3 and 4: tool name -> list of rule callables.
# Each rule takes tool_input (dict) and returns a decision dict or None.
_RULES: dict = {}


def evaluate(payload: dict):
    """Return the JSON to emit, or None for a silent allow."""
    try:
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not tool or not isinstance(tool_input, dict):
            return None
        for rule in _RULES.get(tool, ()):
            decision = rule(tool_input)
            if decision is not None:
                return decision
        return None
    except Exception:
        return None      # fail open, always


def main() -> int:
    try:
        decision = evaluate(json.load(sys.stdin))
        if decision is not None:
            print(json.dumps(decision))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

import importlib.util
import json
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "guardrails",
    pathlib.Path(__file__).parent.parent.parent / ".claude" / "hooks" / "guardrails.py",
)
guardrails = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guardrails)

evaluate, _deny, _warn = guardrails.evaluate, guardrails._deny, guardrails._warn


def test_unknown_tool_is_silently_allowed():
    assert evaluate({"tool_name": "WebFetch", "tool_input": {"url": "x"}}) is None


def test_missing_tool_input_is_silently_allowed():
    assert evaluate({"tool_name": "Glob"}) is None


def test_empty_payload_is_silently_allowed():
    assert evaluate({}) is None


def test_deny_shape_matches_the_contract():
    out = _deny("because")
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"] == "because"


def test_warn_allows_and_carries_context():
    out = _warn("heads up")
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["additionalContext"] == "heads up"

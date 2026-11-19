"""v235: the guide's {{name}} whitelist.

A chapter may write {{name}} only for a name in PLACEHOLDERS, a read-only
mapping merged from the live tables. There are no expressions and no generic
config access: a name is looked up in the mapping and nowhere else, so a
secret (a Discord token, an eToro key) can never be rendered. resolve() checks
every {{...}} first and raises UnknownPlaceholder before substituting
anything, so a chapter is either fully resolved or not served at all.

Values are computed per call (live), never cached here. Any figure about
performance carries provenance_label(...) with it.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Callable, Mapping

from swingbot.admin.guide.live_risk import RISK_PLACEHOLDERS

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
_ANY_BRACES_RE = re.compile(r"\{\{(.*?)\}\}", re.S)


class UnknownPlaceholder(KeyError):
    """A {{name}} that is not in the whitelist (or not a plain name at all)."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"unknown guide placeholder: {self.name}"


def _merge(*tables: Mapping[str, Callable[[], str]]) -> Mapping[str, Callable[[], str]]:
    merged: dict[str, Callable[[], str]] = {}
    for table in tables:
        clash = merged.keys() & table.keys()
        if clash:
            raise ValueError(f"guide placeholder defined twice: {sorted(clash)}")
        merged.update(table)
    return MappingProxyType(merged)


PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(RISK_PLACEHOLDERS)


def names_in(markdown: str) -> list[str]:
    """Well-formed placeholder names in document order, repeats kept."""
    return [match.group(1) for match in PLACEHOLDER_RE.finditer(markdown)]


def resolve(markdown: str) -> str:
    """Fill every {{name}}; UnknownPlaceholder on the first name not whitelisted."""
    for match in _ANY_BRACES_RE.finditer(markdown):
        name = match.group(1).strip()
        if name not in PLACEHOLDERS:
            raise UnknownPlaceholder(name)
    return PLACEHOLDER_RE.sub(lambda match: PLACEHOLDERS[match.group(1)](), markdown)


def provenance_label(*, source: str, n: int, run_date: str, costs_included: bool) -> str:
    """Where a performance figure comes from; always ends with 'before tax'."""
    costs = "costs included" if costs_included else "costs not included"
    return f"Source: {source}; N = {n}; as of {run_date}; {costs}; before tax"

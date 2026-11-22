"""v237: strategy cards -- docs/guide/strategies/<slug>.md, one per registered key.

A card is prose about one strategy: its idea, entry rule and where the rule
fires. Its front matter names the exact registry key (`strategy:`), the code
it describes (`sources:`) and the bot version it was checked against
(`reviewed_for:`). The card body has no heading (the strategies.cards
placeholder adds `### <key>`) and no placeholder: every figure on a card
comes from the registry badge, never from prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swingbot.admin.guide import chapters
from swingbot.admin.guide.live_market import strategy_file_slug


@dataclass(frozen=True)
class StrategyCard:
    path: Path
    strategy: str
    reviewed_for: str
    sources: tuple[str, ...]
    body: str


def _is_card_sources(value) -> bool:
    return isinstance(value, list) and bool(value) and all(chapters._is_text(v) for v in value)


#: (key, check, what the key must be) -- one rule per row, as in chapters._FIELD_RULES.
_CARD_RULES = (
    ("strategy", chapters._is_text, "a non-empty string"),
    ("reviewed_for", chapters._is_version, "an X.Y.Z version string"),
    ("sources", _is_card_sources, "a non-empty list of non-empty strings"),
)


def cards_dir(root: Path | None = None) -> Path:
    """The strategies/ folder under the guide directory `root` (default guide_dir())."""
    return (Path(root) if root is not None else chapters.guide_dir()) / "strategies"


def _check_meta(meta: dict, path: Path) -> None:
    for key, check, wanted in _CARD_RULES:
        if key not in meta:
            raise chapters._fail(path, f"front matter lacks '{key}'")
        if not check(meta[key]):
            raise chapters._fail(path, f"'{key}' must be {wanted}, got {meta[key]!r}")
    expected = strategy_file_slug(meta["strategy"].strip())
    if path.stem != expected:
        raise chapters._fail(path, f"file name must be {expected}.md for strategy "
                                   f"{meta['strategy']!r}")


def _check_body(body: str, path: Path) -> None:
    if not body.strip():
        raise chapters._fail(path, "body is empty")
    for number, line in enumerate(body.splitlines(), start=1):
        if line.startswith("#"):
            raise chapters._fail(path, f"line {number} is a heading; the page adds "
                                       "'### <strategy>' itself")
    if "{{" in body:
        raise chapters._fail(path, "a card may not contain a placeholder; "
                                   "figures come from the registry badge")


def parse_card(path: Path) -> StrategyCard:
    """One card file -> StrategyCard; GuideFormatError names the file on any defect."""
    try:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise chapters._fail(path, f"unreadable ({exc})") from exc
    raw, body = chapters._split_front_matter(text, path)
    meta = chapters._load_meta(raw, path)
    _check_meta(meta, path)
    body = body.strip("\n")
    _check_body(body, path)
    return StrategyCard(path=path, strategy=meta["strategy"].strip(),
                        reviewed_for=meta["reviewed_for"],
                        sources=tuple(item.strip() for item in meta["sources"]), body=body)


def load_cards(root: Path | None = None) -> list[StrategyCard]:
    """Every strategies/*.md card under the guide directory, by file name; [] if none."""
    folder = cards_dir(root)
    if not folder.is_dir():
        return []
    return [parse_card(path) for path in sorted(folder.glob("*.md")) if path.is_file()]

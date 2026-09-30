"""Discord ANSI blocks with a hard, phone-safe visible-width cap."""

import re

from swingbot.core.presentation import tokens


FG: dict[str, int] = {
    "grey": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}

MAX_LINE_WIDTH = 32
_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def paint(text: str, colour: str, bold: bool = True) -> str:
    """Wrap one visible run in a Discord-supported foreground colour."""
    code = FG.get(colour, FG["white"])
    intensity = 1 if bold else 0
    return f"\x1b[{intensity};{code}m{text}\x1b[0m"


def visible_width(line: str) -> int:
    """Return the rendered width after removing ANSI escape sequences."""
    return len(_ESCAPE_RE.sub("", line))


def block(lines: list[str]) -> str:
    """Fence phone-safe lines as an ANSI Discord code block."""
    for line in lines:
        width = visible_width(line)
        if width > MAX_LINE_WIDTH:
            raise ValueError(f"ansi line exceeds {MAX_LINE_WIDTH} visible chars ({width})")
    body = "\n".join(lines)
    return f"```ansi\n{body}\n```"


_SIDE_WORDS = {"bullish": "LONG", "bearish": "SHORT"}
_SIDE_COLOURS = {"bullish": "green", "bearish": "red"}


def direction_line(direction: str) -> str:
    """``▲ LONG`` in green or ``▼ SHORT`` in red; an unknown direction is an unpainted dash."""
    side = _SIDE_WORDS.get(direction)
    if side is None:
        return tokens.ABSENT
    return paint(f"{tokens.direction_glyph(direction)} {side}", _SIDE_COLOURS[direction])


def r_multiple(entry: float | None, stop: float | None, target: float | None) -> float | None:
    """Reward over risk for one target; None when a level is missing or risk is zero."""
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    return abs(target - entry) / risk if risk else None


def plan_lines(*, direction: str, entry: float | None, target: float | None,
               stop: float | None, target_pct: float | None,
               stop_pct: float | None, r: float | None) -> list[str]:
    """Return the three-line, phone-safe plan headline: side, levels, magnitudes."""
    levels = (
        f"{paint(tokens.fmt_price(entry), 'cyan')} → "
        f"{paint(tokens.fmt_price(target), 'green')} / "
        f"{paint(tokens.fmt_price(stop), 'red')}"
    )
    magnitudes = (
        f"  {paint(tokens.fmt_pct(target_pct), 'green')} "
        f"{paint(tokens.fmt_pct(stop_pct), 'red')} "
        f"{paint(tokens.fmt_r(r), 'yellow')}"
    )
    return [direction_line(direction), levels, magnitudes]


def _target_line(name: str, target: float | None, entry: float | None,
                 stop: float | None) -> str:
    line = f"{name:<5} {paint(tokens.fmt_price(target), 'green')}"
    reward = r_multiple(entry, stop, target)
    return line if reward is None else f"{line} {paint(tokens.fmt_r(reward), 'yellow')}"


def levels_lines(*, direction: str, entry: float | None, stop: float | None,
                 tp1: float | None, tp2: float | None = None) -> list[str]:
    """The NEW SETUP / ENTRY price block: side, entry, stop, TP1 and TP2 with R."""
    lines = [
        direction_line(direction),
        f"{'entry':<5} {paint(tokens.fmt_price(entry), 'cyan')}",
        f"{'stop':<5} {paint(tokens.fmt_price(stop), 'red')}",
        _target_line("TP1", tp1, entry, stop),
    ]
    if tp2 is not None:
        lines.append(_target_line("TP2", tp2, entry, stop))
    return lines


def _realised_colour(r: float | None) -> str:
    if not r:
        return "white"
    return "green" if r > 0 else "red"


def result_lines(*, direction: str, entry: float | None, exit_price: float | None,
                 stop: float | None, pct: float | None, r: float | None) -> list[str]:
    """The RESULT price block: side, entry → exit / stop, and the realised move."""
    price_line = (f"{paint(tokens.fmt_price(entry), 'cyan')} → {tokens.fmt_price(exit_price)} / "
                  f"{paint(tokens.fmt_price(stop), 'red')}")
    if visible_width(price_line) > MAX_LINE_WIDTH:  # six-digit prices: drop the stop, never abort a send
        price_line = f"{paint(tokens.fmt_price(entry), 'cyan')} → {tokens.fmt_price(exit_price)}"
    return [
        direction_line(direction),
        price_line,
        f"  {tokens.fmt_pct(pct)} {paint(tokens.fmt_r(r), _realised_colour(r))}",
    ]

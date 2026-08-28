"""Discord ANSI blocks with a hard, phone-safe visible-width cap."""

import re


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

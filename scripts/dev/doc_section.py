"""Print named sections of a markdown doc instead of reading it whole.

    python scripts/dev/doc_section.py <doc> [<heading> ...]

No heading: one line per `##`/`###` heading, in doc order, as
`<bytes>  <heading line>` (the UTF-8 size of that heading's section).
With headings: those sections, in the order asked, one blank line apart.

A heading argument is a case-insensitive prefix of the heading title and must
select exactly one heading. A section runs to the next heading of the same or
a higher level, so a `##` section includes its `###` children. Lines inside
fenced code blocks are never headings.

Exit code 2, with a one-line reason on stdout (followed by the heading list
when there is one), when an argument selects no heading or several, when the
doc has no `##`/`###` heading, or when it cannot be read. The script never
prints a whole file and never prints nothing with exit code 0: on 2, read the
file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

USAGE = "doc_section: usage: python scripts/dev/doc_section.py <doc> [<heading> ...]"
HEADING_RE = re.compile(r"^(#{2,3}) (\S.*)$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


class Heading(NamedTuple):
    start: int  # index of the heading line
    end: int    # index one past the last line of its section
    title: str  # the text after the # marks
    line: str   # the heading line as written


def _heading_lines(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of every ##/### line outside fenced code."""
    found, in_fence = [], False
    for index, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2).strip()))
    return found


def find_headings(lines: list[str]) -> list[Heading]:
    raw = _heading_lines(lines)
    headings = []
    for position, (start, level, title) in enumerate(raw):
        later = (index for index, other, _ in raw[position + 1:] if other <= level)
        headings.append(Heading(start, next(later, len(lines)), title, lines[start].rstrip()))
    return headings


def section_size(lines: list[str], heading: Heading) -> int:
    """UTF-8 bytes of the section, one newline counted per line."""
    return sum(len(line.encode("utf-8")) + 1 for line in lines[heading.start:heading.end])


def section_text(lines: list[str], heading: Heading) -> str:
    return "\n".join(lines[heading.start:heading.end]).rstrip()


def listing(lines: list[str], headings: list[Heading]) -> str:
    sizes = [section_size(lines, heading) for heading in headings]
    width = len(str(max(sizes)))
    return "\n".join(f"{size:>{width}}  {heading.line}"
                     for size, heading in zip(sizes, headings))


def resolve(headings: list[Heading], argument: str) -> Heading | str:
    """The one heading `argument` selects, or the reason there is not one."""
    wanted = argument.strip().lower()
    hits = [heading for heading in headings if heading.title.lower().startswith(wanted)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return f"doc_section: no heading starts with '{argument}'"
    return f"doc_section: '{argument}' is ambiguous"


def run(doc: str, arguments: list[str]) -> tuple[int, str]:
    """(exit code, text to print) for one invocation."""
    try:
        text = Path(doc).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 2, f"doc_section: cannot read {doc}"
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    headings = find_headings(lines)
    if not headings:
        return 2, f"doc_section: {doc} has no ## or ### headings -- read the file"
    if not arguments:
        return 0, listing(lines, headings)
    picked = [resolve(headings, argument) for argument in arguments]
    reasons = [item for item in picked if isinstance(item, str)]
    if reasons:
        return 2, reasons[0] + "\n" + listing(lines, headings)
    return 0, "\n\n".join(section_text(lines, heading) for heading in picked)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE)
        return 2
    code, text = run(argv[1], argv[2:])
    # Bytes, not print(): the docs hold characters a Windows console code page
    # cannot encode, and the output must not depend on the terminal.
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))

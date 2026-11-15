"""v222 V222-5: splice stage1.md and forward.md into the spec's Results."""
import sys
from pathlib import Path

spec, stage1, forward = (Path(p) for p in sys.argv[1:4])
text = stage1.read_text(encoding="utf-8")
body, _, days = text.partition("## Stage 2 day list (frozen before any replay is built)")
body = "\n".join(l for l in body.split("\n") if not l.startswith("# v222 Stage 1")).strip()
body = body.replace("\n## ", "\n#### ")
if forward.exists():
    fwd = forward.read_text(encoding="utf-8").replace(
        "# v222 Stage 1 — forward long-book (descriptive only)",
        "#### Forward long-book (descriptive only)")
else:
    fwd = "#### Forward long-book (descriptive only)\n\nNot run: no winner, or the dump failed."
doc = spec.read_text(encoding="utf-8")
pending = "### Stage 1 — screen\n\nPending V222-5."
assert pending in doc, "Stage 1 heading is not pending"
doc = doc.replace(pending, "### Stage 1 — screen\n\n" + body + "\n\n" + fwd.strip())
list_line = "- List: pending (drawn by the Stage 1 run below)."
assert list_line in doc, "day-list line missing: Step 2 not done"
drawn = days.strip() or "Not drawn: no winner (NO-LIFT), or the frozen rule could not be met."
doc = doc.replace(list_line, "- Drawn by the Stage 1 run (`data/v222/stage2_days.json`):\n\n" + drawn)
spec.write_text(doc, encoding="utf-8")
print("results written")

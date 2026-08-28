"""
The one place the bot's Discord presentation is defined -- colours, glyphs,
number formats, and the embed parts built from them.

Three modules, smallest dependency first:

  tokens.py      pure values: the accent ramp, direction glyphs, the
                 confidence label, the follow meter, number formatters.
                 No discord.Embed anywhere; importable and testable on its
                 own.
  ansi.py        the ``` ansi ``` code block, which is one of exactly two
                 places Discord renders colour (the other being an embed's
                 4px accent bar). 8 foreground colours, hard 32-char line cap.
  components.py  whole embed PARTS -- a field, a headline, the chrome. Call
                 sites ask for a part rather than assembling one out of
                 tokens, which is what stops the kit being half-used.

It lives in core/ rather than in core/scanning/ (where embed_theme.py used
to) because swingbot command modules need it, and commands depending on
core.scanning for a colour would misdescribe that dependency.

tests/presentation/test_no_adhoc_color.py enforces that no module outside
this package touches discord.Color at all.
"""

from swingbot.core.presentation.components import (  # noqa: F401
    EmbedField, apply_chrome, blocked_by_field, confidence_field, follow_field,
    plan_headline,
)
from swingbot.core.presentation.tokens import (  # noqa: F401
    ABSENT, ACCENT_BLOCKED, ACCENT_RAMP, DISCLAIMER, SECTION_ORDER,
    accent_for_level, accent_for_outcome, confidence_label, direction_glyph,
    fmt_pct, fmt_price, fmt_r, follow_meter,
)

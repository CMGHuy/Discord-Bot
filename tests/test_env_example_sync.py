"""`.env.example` must list every setting the schema defines.

This file exists because the drift is recurring, not hypothetical. Commit
`7f971dc` resynced it after **54 of 115** settings had gone missing; by
2026-08-14 it had drifted again to **38 of 93** absent. Nothing checked it in
between, so each rediscovery was accidental.

**Presence is asserted; values are not.** `.env.example` legitimately differs
from the schema default in three ways, and pinning values would fight all
three:

* **Placeholders.** `DISCORD_TOKEN=your-bot-token-here` is more useful to
  someone filling the file in than the schema's empty string.
* **Deliberate example values.** The file is a working starting point, not a
  restatement of `config.py`.
* **Schema defaults that are themselves wrong.** `RISK_PER_TRADE_PCT` and
  `MAX_POSITION_SIZE_PCT` are documented as percentages -- their help text
  says "1% means..." and `MAX_POSITION_SIZE_PCT` is capped at `max=100` --
  but default to `0.01` and `0.1`, i.e. 0.01% and 0.1%. `account.py:466`'s
  own fallback is `1.0`, and `build_sizing_note` divides by 100. A test that
  forced the example to match the schema would push a nonsense risk setting
  onto every fresh install.

The reverse direction is checked too: a key in `.env.example` that the schema
does not define is silently ignored by the parser, so someone setting it gets
no error and no effect.
"""
import re

from swingbot import config

_ASSIGNMENT = re.compile(r"^([A-Z0-9_]+)=", re.MULTILINE)


def _example_keys() -> set[str]:
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / ".env.example"
    return set(_ASSIGNMENT.findall(path.read_text(encoding="utf-8")))


def test_every_setting_appears_in_env_example():
    missing = sorted({f.key for f in config.FIELDS} - _example_keys())
    assert not missing, (
        f"{len(missing)} setting(s) defined in swingbot/config.py but absent "
        f"from .env.example: {missing}. A setting nobody can discover is a "
        f"setting nobody uses -- add it with its default."
    )


def test_env_example_defines_no_setting_the_schema_does_not():
    unknown = sorted(_example_keys() - {f.key for f in config.FIELDS})
    assert not unknown, (
        f"{len(unknown)} key(s) in .env.example that swingbot/config.py does "
        f"not define: {unknown}. The parser ignores these, so anyone setting "
        f"one gets no error and no effect."
    )

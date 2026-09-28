# v110 — Distinct, colourful Discord notifications (one registry of kinds)

**Version:** ui 1.21.0 · bot 1.10.4
**Bump:** bot minor
**Edge:** none (integrity)
**Plan:** not yet written

`Bump: bot minor` because every message the bot pushes changes shape: a
reader who used the channels yesterday has to relearn what they are looking
at. `Edge: none (integrity)`: nothing here changes which plans are produced
or how they trade. The only integrity content is the three send fixes in
§6. It ranks below the live win-rate plans (v32–v36) on expectancy. It is
being done because the partner reads these messages every day and today
cannot tell kinds apart at a glance.

The companion spec, backend logging, is separate and comes after this one. It
logs notification kinds by the `Kind` names defined here.

## Why

A survey of the alert surface (2026-09-28) found:

- **Five accent colours carry everything.** One grey (`0x9EA2AD`) is shared
  by help, analytics, strategy signals, FILLED, break-even and expired. The same
  green means "confidence Lv5" *and* "win" *and* "approaching TP"; the
  same red means "Lv1" *and* "loss" *and* "approaching SL".
- **Direction has three spellings.** 🟢/🔴 on the full alert and ▲/▼ on the
  simple and execution feed, while 🟢/🔴 *also* means win/loss on plan events.
- **The strategy-signal embed has no icon**, is always grey, and shows a raw
  `bullish`.
- **Every embed carries the alert disclaimer footer** ("Technical signal
  only…"), including closed trades and system notices.
- **Emoji are scattered inline literals.** The only per-event registry is
  `PLAN_EVENT_STYLES` (local to `lifecycle_embeds.py`). The closed-trade icons
  are duplicated in `lifecycle_embeds.py` and `commands/trades.py`.
- **Phone push previews are vague.** A push shows the message `content`, not
  the embed title, and most pushed embeds have no content.
- **System messages are plain text**, visually unrelated to trade messages.

## Scope

**In:** every message the bot pushes unprompted:
- full scan alert
- strategy signal
- v2 simple ticket and the legacy simple mirror
- execution-feed lifecycle posts and their HISTORY copies
- plan-event status posts
- closed trade
- near close
- top-plans digest
- weekend deep scan
- scan summary
- health alert and recovered
- bot online
- config-change notices
- retrospective
- the per-tick healthcheck line

**Out:**
- Command replies (`!trade`, `!today`, `!plans`, stats, help, breakdown,
  command errors). They keep their current look. Where a pushed builder and a
  command share code (the closed-trade icons), the command reads the new
  registry, but its title shape is not redesigned.
- Chart images.
- The admin UI.
- Any change to what is sent, when, or to which channel.

## 1. Families

Each notification kind belongs to exactly one family. The family owns a
badge emoji, a label and a stripe colour. The specific event follows the
badge in the title.

| Family | Badge | Stripe | Kinds |
|---|---|---|---|
| NEW SETUP | 🆕 | blue ramp by confidence Lv1→Lv5; muted grey-blue when blocked / DO NOT PLACE | full alert, strategy signal, simple ticket (PLACE and DO NOT PLACE), legacy simple mirror, top-plans digest entries, weekend deep scan |
| ENTRY | 🎯 | teal | entry triggered, FILLED |
| MANAGE | 🛡️ break-even · 💰 TP1 / scale-out · ✂️ move stop · 🚫 cancel / risk-cap block | amber | BE moved, TP1 hit, MOVE STOP, CANCEL, risk cap |
| WATCH | 👀 | orange (nearing stop) / lime (nearing TP) | approaching SL, approaching TP |
| RESULT | 🏁 + outcome ✅ win · ❌ loss · ⚪ scratch · 🔒 manual · ⏹️ expired/invalidated | green or red ramp by abs(R); grey for scratch / manual / expired / invalidated | closed trade, stopped, win, scratched, EXITED, CLOSE AT MARKET, expired, invalidated |
| SYSTEM | 🩺 (🚨 health alert · ✅ recovered · ⚙️ config · 🤖 online · 📜 retrospective · 🔭 deep scan header) | slate; red for health alert, green for recovered | scan summary, health alert / recovered, bot online, config change, retrospective, weekend deep-scan header |

Expired and invalidated sit under RESULT (the plan ended), in grey so they
never read as a win or a loss.

**Glyph rules, everywhere in pushed messages:**
- ▲/▼ mean direction only.
- ✅/❌ mean outcome only.
- 🟢/🔴 are retired from pushed titles, because they meant both.
- A family badge is never reused as an outcome or direction mark.

## 2. The registry — `swingbot/core/presentation/kinds.py`

A new module, part of the existing `presentation` package.

- `Family` — enum of the six families: badge, label, base colour.
- `Kind` — enum with one member per event in the table above. Each member
  records its family, an optional event emoji that overrides the family badge,
  its short label, its stripe rule (`fixed`, `level_ramp`, `r_ramp`), and
  `disclaimer: bool`, which is true only for NEW SETUP kinds.
- Four pure helpers, and the only way a pushed builder styles a message:
  - `title(kind, ticker, direction=None, detail="") -> str`
  - `content_line(kind, ticker, direction=None, detail="") -> str`, the push
    preview line placed in the message `content`
  - `stripe(kind, level=None, r=None, blocked=False) -> int`
  - `footer(kind, plan_id=None) -> str`

`PLAN_EVENT_STYLES`, the duplicated closed-trade icon maps, and the inline
emoji literals in pushed builders are replaced by registry lookups. Existing
`tokens.py` confidence helpers (`ACCENT_RAMP`, `accent_for_level`,
`confidence_label`) stay because command replies still use them. The new
ramps are separate constants in `kinds.py`, so command replies do not change
colour as a side effect.

Every helper stays under cyclomatic complexity 15. The stripe rules and the
badge/label lookups are table-driven, not `if/elif` chains.

## 3. Colour

**Stripe ramps.** Exact hex values are chosen in the plan. They must be
distinguishable side by side in Discord's dark and light themes, with no ramp
step equal to another family's colour.
- NEW SETUP: five blues, Lv1 light → Lv5 deep, plus one muted grey-blue for
  blocked / DO NOT PLACE.
- RESULT: three greens and three reds by abs(R): `< 1R`, `1–2R`, `≥ 2R`.
  One grey for scratch / manual / expired / invalidated.
- Others: one fixed colour each, as in §1.

**ANSI price block.** NEW SETUP, ENTRY and RESULT embeds carry a fenced
`ansi` block built with the existing `presentation/ansi.py` (`paint`,
`block`, 32-visible-character phone-safe cap):
- the direction glyph and word: ▲ LONG in green, ▼ SHORT in red
- entry in cyan
- stop in red
- TP1 / TP2 in green
- R multiples in yellow
- on RESULT, the realised R in green (win) or red (loss)

ANSI renders on desktop and web only. On mobile it shows as aligned monospace,
so every line must stay readable without colour. Where the full alert already
has an ANSI plan headline, that headline is restyled to these colours rather
than a second block being added.

The partner asked for a coloured *background* behind ▲/▼ like the admin UI's
confidence chip. That is not possible here:
- Discord titles and push text cannot be coloured.
- Discord's ANSI background palette has no green or red.

Coloured triangle glyphs inside the ANSI block were chosen over image chips
and blue emoji tiles.

## 4. Push text and footer

- **Content line.** Every pushed embed is sent with
  `content=content_line(kind, …)`, for example `🏁 RESULT · ▲ AAPL ✅ WIN +1.8R`
  or `🆕 NEW SETUP · ▲ LONG AAPL · Lv4 ⭐`. Existing content headers (the
  closed-trade `✅ WIN — **TICK**`, the digest's `📌 **Top plans today**`) are
  replaced by the registry line. The digest keeps a single content line for
  the batch, not one per entry. The silent/notify flags of each send are
  unchanged.
- **Footer.** `apply_chrome` takes the kind:
  - NEW SETUP keeps the `DISCLAIMER` (plus `· plan xxxxxxxx`).
  - Every other family's footer is `<FAMILY> · plan xxxxxxxx`, or just
    `<FAMILY>` when there is no plan.
  - The timestamp is unchanged.

## 5. System messages become embeds

These become slate-striped SYSTEM embeds with a content line:
- scan summary
- health alert (red stripe, 🚨) and recovered (green stripe, ✅)
- bot online (🤖)
- config-change notices (⚙️)
- weekend deep-scan header (🔭)
- retrospective (📜)

The retrospective stays chunked, one embed per chunk, each description within
Discord's 4096-character embed limit (today's chunks are sized for the
2000-character message limit, so they fit). The per-tick healthcheck stays a
**plain text line** prefixed with 🩺, since it is silent and deleted hourly.
The manual `!check` progress edits are a command reply and are out of scope.

## 6. Send fixes folded in (integrity)

1. **Strategy-alert mirror.** `strategy_pass.py:163` passes a `str`
   (`simple_line(plan)`) as the simple-channel payload, and `alerts.py:234`
   sends it as `embed=`. It fails on every strategy alert, is logged as a
   warning, and the full alert pings instead of the mirror. Fix: build a real
   NEW SETUP simple embed through the registry.
2. **Per-message send isolation.** The main alert `send` in `alerts.py:254`
   is unguarded, so one failure aborts the rest of the batch. Each send in the
   batch gets its own guard. A failure is logged with `exc_info` and the
   batch continues.
3. **Unguarded pushes.** The bot-online post (`loops.py:961`) and the
   retrospective chunk sends (`recap.py:61-64,139`) get the same guard.
4. **Stale embed notes** in `docs/claude/known-traps.md`: the sizing and
   embed-building location, `embed_theme.SECTION_ORDER`, and the
   `scan_snapshots` write location. Refresh them to the current modules.

## Testing

- `tests/presentation/test_kinds.py`, table-driven over `Kind`:
  - every kind has a family
  - badge and label pairs are unique
  - only NEW SETUP kinds have `disclaimer=True`
  - `stripe` returns the ramp step for each level / R bucket, and no stripe
    colour is shared across families
  - `content_line` starts with the badge
  - titles never contain 🟢/🔴
- Every pushed builder: a test asserts it sets `content`, its family stripe and
  its family footer.
- ANSI block: every line ≤ 32 visible characters, direction painted
  green/red, and the text still readable with escapes stripped.
- Regression: a strategy alert produces an `Embed` for the simple channel,
  never a `str`.
- Regression: a batch where one send raises still sends the others.
- Existing tests asserting old titles, colours or footers are updated, not
  deleted:
  - `scanning/test_simple_alerts.py`
  - `scanning/test_embeds_v3.py`
  - `scanning/test_transition_embeds.py`
  - `scanning/test_execution_embeds.py`
  - `scanning/test_execution_feed_routing.py`
  - `presentation/test_tokens.py`
  - `presentation/test_components.py`
  - `tracking/test_near_tp_bypass.py`
  - `test_trades_display.py` (shared closed-trade icons only)
- Complexity: `radon cc -s -n C` over every touched file shows no new or
  worsened function ≥ 15.
- One full suite run, as the plan's final task.

## Acceptance

- Each pushed kind is identifiable from its push preview alone, and again
  from its stripe colour plus badge in the channel.
- No glyph carries two meanings across pushed messages.
- The strategy-alert mirror posts to the simple channel with no warning in
  `bot.log`.
- Full suite green: `0 failed`, `0 xfailed`.

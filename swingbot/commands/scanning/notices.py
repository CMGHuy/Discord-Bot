"""v110 §5-§6: SYSTEM notices as registry-styled embeds, and the guarded send.

The builders are pure (no bot import), so they are testable alone; loops.py and
recap.py only resolve channels and send. send_guarded is the one place an
unprompted push swallows its own failure: it is logged with its traceback,
never raised, so one bad send cannot abort a batch or a startup.
"""
import logging

from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

log = logging.getLogger(__name__)

#: The old 2000-char message chunk size. Each chunk is now an embed
#: description (4096 limit), so the same split still fits.
RETRO_CHUNK = 1990
HEALTHCHECK_BADGE = kinds.badge(Kind.HEALTHCHECK)

_FAIL_LABELS = (
    ("failed_min_confluence", "below min strategies"),
    ("failed_min_confidence", "below min confidence"),
    ("rs_blocked", "blocked by RS gate"),
)


def system_embed(kind: Kind, detail: str = "", description: str | None = None):
    """A SYSTEM PushEmbed: registry title, push line, stripe and footer."""
    embed = ui.push_embed(kind, "", None, detail, description=description)
    ui.apply_chrome(embed, kind=kind)
    return embed


async def send_guarded(channel, embed, *, what: str):
    """Send one pushed embed; a failure is logged with exc_info and swallowed."""
    try:
        return await channel.send(**ui.push_kwargs(embed))
    except Exception:
        log.warning("Could not post %s -- continuing", what, exc_info=True)
        return None


def health_alert_embed(failures: int, last_success: str, exc: Exception):
    return system_embed(Kind.HEALTH_ALERT, f"{failures} failed tick(s) in a row", (
        f"• Last successful tick: {last_success}\n"
        f"• Latest error: `{type(exc).__name__}: {str(exc)[:400]}`\n"
        "No alerts are being produced until this clears."))


def health_recovered_embed():
    return system_embed(Kind.HEALTH_RECOVERED, "scan tick healthy again",
                        "The scan tick completed successfully again.")


def pitr_notice_embed(notice):
    """v116: a PITR alarm or its recovery, in the existing HEALTH kinds."""
    kind = Kind.HEALTH_RECOVERED if notice.recovered else Kind.HEALTH_ALERT
    return system_embed(kind, notice.detail, notice.description)


def bot_online_embed(*, now_text: str, session_start: int, session_end: int, interval: int,
                     watchlist_size: int, open_count: int, min_level: int):
    return system_embed(Kind.BOT_ONLINE, now_text, (
        f"Session: {session_start:02d}:00–{session_end:02d}:00 Berlin · "
        f"scan every {interval} min\n"
        f"Watchlist: {watchlist_size} ticker(s) · open trades: {open_count} · "
        f"min confidence: Lv{min_level}"))


def config_notice_embed(detail: str, note: str = ""):
    return system_embed(Kind.CONFIG_CHANGE, detail, note or None)


def scan_gap_note(funnel: dict) -> str:
    """Why "qualifying" and "alerts posted" can differ: merged duplicates and
    tickers that already have an open trade."""
    parts = []
    qualifying = funnel.get("fully_qualifying", 0)
    merged = max(0, qualifying - funnel.get("deduped", qualifying))
    if merged:
        parts.append(f"{merged} merged as duplicate setup(s)")
    if funnel.get("skipped_already_open", 0):
        parts.append(f"{funnel['skipped_already_open']} already open")
    return f" ({', '.join(parts)})" if parts else ""


def has_priority(alerts: list) -> bool:
    """True when any posted alert's title carries the ⭐ priority mark."""
    return any("⭐" in (getattr(alert[0], "title", None) or "") for alert in alerts)


def scan_summary_embed(now_str: str, funnel: dict, alert_count: int,
                       gap_note: str = "", priority: bool = False):
    detail = f"{now_str} · {alert_count} new alert(s)" + (" ✨" if priority else "")
    return system_embed(Kind.SCAN_SUMMARY, detail, (
        f"📡 {funnel['tickers']} tickers, {funnel['checked']} combos checked\n"
        f"🧮 {funnel['scenarios_found']} scenario(s) found "
        f"(✔ {funnel['fully_qualifying']} qualifying)\n"
        f"**{alert_count} new alert(s) posted above**{gap_note}"))


def _fail_bits(funnel: dict) -> list[str]:
    return [f"{funnel[key]} {label}" for key, label in _FAIL_LABELS if funnel.get(key, 0)]


def healthcheck_text(now_str: str, funnel: dict | None, open_count: int,
                     confirmation_scans: int) -> str:
    """The per-tick healthcheck: a plain, silent text line (v110 §5), 🩺-prefixed.

    "qualifying" = passed every hard requirement; "awaiting confirmation" is
    a SUBSET of it (passed, but not yet seen SIGNAL_CONFIRMATION_SCANS scans in
    a row). The failure tallies are not a partition -- one scenario can fail
    more than one requirement, so they can sum past the scenario count."""
    if not funnel:
        return (f"{HEALTHCHECK_BADGE} **Healthcheck** ({now_str}) — scan complete, nothing new\n"
                f"• 📂 {open_count} open trade(s)")
    awaiting = funnel.get("awaiting_confirmation", 0)
    confirm_note = (f" (needs to reappear {confirmation_scans} scan(s) in a row before it posts)"
                    if awaiting else "")
    bullets = [
        f"📡 {funnel['tickers']} tickers scanned",
        f"🧮 {funnel['scenarios_found']} scenario(s) found",
        (f"✔ {funnel['fully_qualifying']} fully qualifying "
         f"(⏳ {awaiting} still awaiting confirmation{confirm_note})"),
    ]
    fail_bits = _fail_bits(funnel)
    if fail_bits:
        bullets.append(f"✖ failed a requirement: {', '.join(fail_bits)}")
    bullets.append(f"📂 {open_count} open trade(s)")
    return (f"{HEALTHCHECK_BADGE} **Healthcheck** ({now_str}) — nothing new this tick\n"
            + "\n".join(f"• {bullet}" for bullet in bullets))


def deep_scan_embed(report: str, count: int):
    return system_embed(Kind.DEEP_SCAN, f"{count} candidate(s)", report)


def chunk_text(text: str, limit: int = RETRO_CHUNK) -> list[str]:
    """Split at the last newline before ``limit`` (hard at ``limit`` when a
    line is longer), exactly as the pre-v110 retrospective loop did; blank
    chunks are dropped."""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    return [chunk for chunk in chunks if chunk.strip()]


def retrospective_embeds(messages: list[str]) -> list:
    """One RETROSPECTIVE embed per chunk, numbered ``i/n`` when there is more than one."""
    chunks = [chunk for message in messages for chunk in chunk_text(message)]
    total = len(chunks)
    return [system_embed(Kind.RETROSPECTIVE, f"{index}/{total}" if total > 1 else "", chunk)
            for index, chunk in enumerate(chunks, 1)]

"""
Secondary alert channels beyond Discord: SMTP email and push notifications
via ntfy.sh. Fires only for high-confidence, fully-qualifying setups when
the relevant channels are configured and enabled.

Email
-----
Standard SMTP with STARTTLS. Works with any provider -- Gmail, Outlook,
Fastmail, etc. For Gmail, use an App Password (myaccount.google.com/
apppasswords) rather than your real account password.

Push (ntfy.sh)
--------------
ntfy.sh is a free, no-account-required push notification service. Choose a
unique topic string (e.g. "swingbot-yourname-abc123"), set NTFY_TOPIC in
.env, and subscribe via the ntfy iOS/Android app at ntfy.sh/<topic>.
Priority is "max" for Level 5, "high" for Level 4, "default" for lower.
No API key needed; traffic is public -- pick a hard-to-guess topic name.

Both channels fire asynchronously in a background thread (same
asyncio.to_thread() pattern as the scan itself) so they never block the
Discord event loop. Each failure logs a warning and moves on -- a broken
SMTP config should never silence a Discord alert.
"""
import logging
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage

from swingbot import config

log = logging.getLogger("swing-bot.notifier")


def _send_email(subject: str, body: str) -> bool:
    """Send a plain-text alert email via SMTP STARTTLS. Returns True on success."""
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = config.SMTP_USER
        msg["To"] = config.ALERT_EMAIL_TO
        msg.set_content(body)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        log.info("Email alert sent to %s: %s", config.ALERT_EMAIL_TO, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        log.warning("Email alert: SMTP authentication failed -- check SMTP_USER / SMTP_PASSWORD "
                    "(Gmail users: use an App Password, not your account password)")
        return False
    except Exception as exc:
        log.warning("Email alert failed: %s", exc)
        return False


def _send_push(title: str, message: str, tags: str = "chart_with_upwards_trend",
               priority: str = "default") -> bool:
    """Send a push notification via ntfy.sh. Returns True on success."""
    try:
        topic = config.NTFY_TOPIC.strip()
        if not topic:
            log.warning("Push alert: NTFY_TOPIC is not configured")
            return False
        url = f"https://ntfy.sh/{topic}"
        data = message.encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Title", title)
        req.add_header("Priority", priority)
        req.add_header("Tags", tags)
        req.add_header("Content-Type", "text/plain; charset=utf-8")
        with urllib.request.urlopen(req, timeout=12) as resp:
            ok = resp.status == 200
            if ok:
                log.info("Push alert sent to ntfy.sh/%s: %s", topic, title)
            else:
                log.warning("Push alert: ntfy.sh returned status %d", resp.status)
            return ok
    except urllib.error.URLError as exc:
        log.warning("Push alert (ntfy.sh) network error: %s", exc)
        return False
    except Exception as exc:
        log.warning("Push alert (ntfy.sh) failed: %s", exc)
        return False


def _push_priority(conf_level: int) -> str:
    """Map confidence level 1-5 to ntfy priority string."""
    return {5: "max", 4: "high", 3: "default", 2: "low", 1: "min"}.get(conf_level, "default")


def _build_alert_texts(item, plan, conf) -> tuple[str, str]:
    """
    Build (subject, body) for the secondary alert.

    The body is intentionally concise -- it's read on a phone notification
    or in a plain-text email, so the most actionable numbers come first.
    """
    result = item.result
    is_bull = result.trend == "bullish"
    direction = "LONG" if is_bull else "SHORT"
    cur = config.CURRENCY_SYMBOL

    # Subject / push title: fits in a phone notification preview
    subject = (
        f"SwingBot {direction}: {result.ticker} "
        f"Lv{conf.level} {conf.label} ({result.horizon_label})"
    )

    # Compute pct distances (not stored on TradePlan — derive them here)
    stop_distance_pct = abs(plan.entry - plan.stop_loss) / plan.entry * 100
    target_distance_pct = abs(plan.take_profit - plan.entry) / plan.entry * 100
    stop_sign = "-" if is_bull else "+"

    # Target sources come from item.target_confluence = (count, [family, ...]) or None
    tc = item.target_confluence
    sources_str = ", ".join(list(dict.fromkeys(tc[1]))[:3]) if tc else "n/a"

    body_lines = [
        f"{'📈' if is_bull else '📉'} {direction} signal — {result.ticker}",
        f"Horizon  : {result.horizon_label}",
        f"Confidence: {conf.label} (Lv{conf.level}/5, {conf.score}/100)",
        "",
        f"Entry    : {cur}{plan.entry:.2f}",
        f"Stop-loss: {cur}{plan.stop_loss:.2f}  ({stop_sign}{stop_distance_pct:.1f}%)",
        f"Target 1 : {cur}{plan.take_profit:.2f}  (+{target_distance_pct:.1f}%)",
        f"R:R      : {plan.risk_reward_ratio}:1",
        "",
        f"Confirmed by: {sources_str}",
        "",
        "Technical signal only — not financial advice.",
    ]
    return subject, "\n".join(body_lines)


def notify_secondary(item, plan, conf) -> None:
    """
    Fire secondary alerts (email + push) for a qualifying scan item.

    Called synchronously from _sync_run_scan() in the background thread,
    so it can use blocking I/O (SMTP, urllib) without worrying about the
    event loop. Any failure is logged and swallowed -- secondary channels
    are best-effort and must never prevent a Discord embed from posting.

    Conditions for firing:
      - conf.level >= SECONDARY_ALERT_MIN_CONFIDENCE
      - item.all_requirements_met (same gate as logging a paper trade)
      - ALERT_EMAIL_ENABLED or ALERT_PUSH_ENABLED is True
    """
    if not item.all_requirements_met:
        return
    if conf.level < config.SECONDARY_ALERT_MIN_CONFIDENCE:
        return

    subject, body = _build_alert_texts(item, plan, conf)

    if config.ALERT_EMAIL_ENABLED:
        if config.ALERT_EMAIL_TO and config.SMTP_USER and config.SMTP_PASSWORD:
            _send_email(subject, body)
        else:
            log.warning("Email alerts enabled but ALERT_EMAIL_TO / SMTP_USER / SMTP_PASSWORD not fully configured")

    if config.ALERT_PUSH_ENABLED:
        if config.NTFY_TOPIC:
            _send_push(
                title=subject,
                message=body,
                tags="chart_with_upwards_trend" if item.result.trend == "bullish" else "chart_with_downwards_trend",
                priority=_push_priority(conf.level),
            )
        else:
            log.warning("Push alerts enabled but NTFY_TOPIC is not configured")

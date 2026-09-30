"""One INFO line per successfully pushed, ticker-bearing notification (v111 §3).

Called right after the awaited send returns, so a line exists only for a
message Discord accepted. The kind is v110's registry member, read off the
sent PushEmbed (or passed explicitly for an embed built without one, such as
the daily-digest entries). This module never imports the registry; it only
prints the member's .name, so it cannot create an import cycle with
presentation.
"""
import logging

log = logging.getLogger(__name__)


def _channel_name(destination) -> str:
    """A channel's name; a command Context's channel name; else its id."""
    name = getattr(destination, "name", None)
    if not name:
        name = getattr(getattr(destination, "channel", None), "name", None)
    return str(name) if name else str(getattr(destination, "id", "?"))


def log_posted(embed, ticker, destination, kind=None) -> None:
    """Never raises: a logging failure must not abort a send or a batch."""
    try:
        kind = kind or getattr(embed, "kind", None)
        log.info("alert posted kind=%s ticker=%s channel=%s",
                 getattr(kind, "name", "UNKNOWN"), ticker or "-", _channel_name(destination))
    except Exception:
        log.debug("could not write the alert-posted line", exc_info=True)

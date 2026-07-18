"""
All environment-driven configuration in one place.

FIELDS below is the single source of truth for every .env-driven
setting: name, type, default, which module-level global it populates,
and metadata the admin UI uses to render one input field per parameter
(section grouping, label, help text, min/max/step for numbers, options
for selects). Adding a new setting means adding one entry here -- the
admin UI picks it up automatically, nothing to change on that side.

Hot reload: `reload()` re-reads .env and updates this module's globals
in place (same module object, so every `config.XXX` reference anywhere
in the codebase sees the new value on its next read -- no re-import
needed). The bot process listens for SIGHUP (see bot_core.py) and calls
reload() when it receives one; the admin UI's "Update settings" button
saves .env and then asks the bot container to reload via the same
mechanism used for "Restart bot container" (needs the Docker socket
mount), just with a signal instead of a full restart.

Two settings can't actually hot-reload their real-world effect no
matter what:
  - DISCORD_TOKEN: changing it updates config.TOKEN in memory, but the
    bot's already-open Discord Gateway connection was made with the old
    token and won't reconnect using the new one until the process
    restarts.
  - ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_PORT: these configure the
    *admin* process itself, not the bot -- Flask can't rebind its own
    port live, and the admin UI only re-reads its own credentials at
    its own startup. Changing these needs the ADMIN container restarted,
    not the bot.
Both are flagged via `hot_reloadable=False` in FIELDS below so the UI
can say so accurately instead of over-promising.
"""
import logging
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Explicit path resolution: load .env from the PROJECT ROOT (one level up
# from this file -- config.py lives at swingbot/config.py, but .env lives
# next to bot.py/admin_ui.py/docker-compose.yml at the repo root) so
# `python bot.py` picks up its values no matter where it's launched from.
#
# override=True is required here: python-dotenv's default is to NOT
# overwrite a variable that's already set in the process environment.
# Without this, a value that got exported into your shell once (or set
# by whatever launched this process) would silently keep winning over
# .env forever, even after editing .env. override=True makes .env the
# actual source of truth every time it's (re)loaded, matching what
# you'd expect -- both at startup and on every reload() call.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_PACKAGE_DIR)
ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")

log = logging.getLogger("swing-bot.config")

# All runtime state (trades.json, state.json, account.json, watchlist.json)
# and generated chart images live under the project root, not inside the
# swingbot/ package -- so they survive `pip install`-style reorganization,
# are trivial to bind-mount as a single directory in Docker, and don't get
# bundled if the package is ever packaged up for distribution. Not
# .env-driven, so not part of FIELDS/reload().
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
EXPORT_DIR = os.path.join(_PROJECT_ROOT, "exports")
TRADE_CHART_DIR = os.path.join(EXPORT_DIR, "trade_charts")
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
ADMIN_LOG_FILE = os.path.join(LOG_DIR, "admin.log")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


@dataclass
class Field:
    key: str                      # .env variable name
    attr: str                     # module-level global this populates (config.<attr>)
    section: str                  # grouping used by the admin UI
    label: str
    type: str = "text"            # text | number | float | checkbox | select | password
    default: str = ""
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list = field(default_factory=list)   # for type="select" -- plain strings or (value, label) tuples
    sensitive: bool = False        # masked in logs / password input in the UI
    hot_reloadable: bool = True     # see module docstring

    def __post_init__(self):
        # Normalize plain-string options to (value, label) tuples so the
        # UI template only ever has to deal with one shape.
        self.options = [(o, o) if not isinstance(o, tuple) else o for o in self.options]


FIELDS: list[Field] = [
    # --- Discord connection ---
    Field("DISCORD_TOKEN", "TOKEN", "Discord Connection", "Bot token",
          type="password", sensitive=True, hot_reloadable=False,
          help="From the Discord Developer Portal. Changing this requires a full bot restart -- "
               "the Gateway connection can't be swapped to a new token live."),
    Field("DISCORD_CHANNEL_TRADES_ID", "DISCORD_CHANNEL_TRADES_ID", "Discord Connection", "Alerts channel ID",
          help="Channel where new trade alerts are posted."),
    Field("DISCORD_CHANNEL_TRADES_HISTORY_ID", "DISCORD_CHANNEL_TRADES_HISTORY_ID", "Discord Connection", "Closed-trades channel ID",
          help="Channel for WIN/LOSS and near-SL/TP notifications. Separate from the alerts channel so results don't get lost among new signals."),
    Field("DISCORD_CHANNEL_RETROSPECTIVE_ID", "DISCORD_CHANNEL_RETROSPECTIVE_ID", "Discord Connection", "Daily retrospective channel ID",
          help="Channel where the end-of-session retrospective is posted on weekdays. Leave blank to post to the closed-trades channel instead."),

    # --- Scanning & session ---
    Field("SESSION_START_HOUR", "SESSION_START_HOUR", "Scanning & Session", "Session start hour",
          type="number", default="8", min=0, max=23, step=1,
          help="Europe/Berlin, 24h clock. The bot only scans automatically inside this window."),
    Field("SESSION_END_HOUR", "SESSION_END_HOUR", "Scanning & Session", "Session end hour",
          type="number", default="23", min=0, max=23, step=1,
          help="Europe/Berlin, 24h clock. Automatic scanning stops for the day at this hour (exclusive)."),
    Field("SCAN_INTERVAL_MINUTES", "SCAN_INTERVAL_MINUTES", "Scanning & Session", "Scan interval (minutes)",
          type="number", default="5", min=1, max=120, step=1,
          help="Every scan both looks for new trades and checks all open trades for near-close proximity."),
    Field("SIGNAL_CONFIRMATION_SCANS", "SIGNAL_CONFIRMATION_SCANS", "Scanning & Session", "Confirmation scans",
          type="number", default="2", min=1, max=10, step=1,
          help="A signal must appear the same way this many consecutive scans before it's confirmed and alerted -- filters intraday flicker."),
    Field("LOG_LEVEL", "LOG_LEVEL", "Scanning & Session", "Log level",
          type="select", default="INFO", options=["DEBUG", "INFO", "WARNING", "ERROR"],
          help="DEBUG shows every signal/strategy combo evaluated; INFO shows per-scan progress and trade decisions."),

    # --- Trade filters & risk ---
    Field("MIN_REWARD_PCT", "MIN_REWARD_PCT", "Trade Filters & Risk", "Min reward %",
          type="float", default="3.0", min=0, step=0.5,
          help="Hard filter, enforced exactly as set: a scenario is dropped entirely (not shown, not scored) "
               "unless its target is at least this far from today's price. No exceptions for a close miss."),
    Field("MIN_STOP_DISTANCE_PCT", "MIN_STOP_DISTANCE_PCT", "Trade Filters & Risk", "Min stop distance %",
          type="float", default="2.0", min=0, step=0.5,
          help="Hard filter, enforced exactly as set: dropped entirely if the stop sits closer than this -- "
               "too exposed to ordinary daily noise. No exceptions for a close miss."),
    Field("MAX_STOP_LOSS_PCT", "MAX_STOP_LOSS_PCT", "Trade Filters & Risk", "Max stop-loss %",
          type="float", default="7.0", min=0, step=0.5,
          help="Hard filter, enforced exactly as set: dropped entirely if the stop sits further than this from "
               "entry -- disciplined cut-loss ceiling, keep in the 5-7% range. No exceptions for a close miss."),
    Field("MIN_RISK_REWARD_RATIO", "MIN_RISK_REWARD_RATIO", "Trade Filters & Risk", "Min reward:risk ratio",
          type="float", default="1.5", min=0, step=0.1,
          help="Hard filter, enforced exactly as set: dropped entirely unless the reward:risk to target 1 "
               "clears this bar. No exceptions for a close miss."),
    Field("CONFLUENCE_DEVIATION_PCT", "CONFLUENCE_DEVIATION_PCT", "Trade Filters & Risk", "Confluence deviation %",
          type="float", default="5.0", min=0.5, step=0.5,
          help="How close (as a %) an independent strategy's own predicted level has to land to the scenario's "
               "actual target/stop price to count as confirming it, for the 'min strategies confirmed' filter "
               "below. Independent of the (tighter) clustering tolerance levels.py uses internally to merge raw "
               "levels into one displayed price -- this is a looser, separate pass over EVERY supported "
               "strategy's own simulated level, counting distinct strategies (not raw sub-levels -- 5 Fibonacci "
               "ratios only ever count as one 'Fibonacci' vote) within this deviation of the final price."),
    Field("MIN_TARGET_CONFLUENCE_COUNT", "MIN_TARGET_CONFLUENCE_COUNT", "Trade Filters & Risk", "Min strategies confirmed",
          type="number", default="2", min=1, max=10, step=1,
          help="A scenario is dropped -- before its confidence level is even calculated -- unless at least this "
               "many DISTINCT strategies (EMA, VWAP, Fibonacci, rolling structure, zigzag pivots, Bollinger "
               "Bands, Donchian Channel, floor pivots, trendlines, Fair Value Gaps -- 10 total) land within "
               "'Confluence deviation %' of the target/stop price. 1 disables this filter (any single "
               "confirming strategy is enough). Can also be overridden per-run with `!check <horizon> <min_strategies>`."),
    Field("MIN_ALERT_CONFIDENCE_LEVEL", "MIN_ALERT_CONFIDENCE_LEVEL", "Trade Filters & Risk", "Min confidence level to alert",
          type="select", default="4", options=["1", "2", "3", "4", "5"],
          help="Only this level and above are shown as alerts (quality over quantity)."),
    Field("DEDUP_TOLERANCE_PCT", "DEDUP_TOLERANCE_PCT", "Trade Filters & Risk", "Dedup tolerance %",
          type="float", default="2.0", min=0, step=0.5,
          help="Two signals on the same ticker/direction are merged into one alert if entry/SL/TP are all within this % of each other."),
    Field("NEAR_CLOSE_ALERTS_ENABLED", "NEAR_CLOSE_ALERTS_ENABLED", "Trade Filters & Risk",
          "Approaching SL/TP notifications enabled",
          type="checkbox", default="false",
          help="Post a warning to the closed-trades channel when an open trade's price gets within "
               "'Near-close threshold %' (below) of its stop-loss or target. Turn off here to temporarily "
               "silence these without losing the threshold setting -- SL/TP hits themselves (and the trade "
               "actually closing) are unaffected either way; this only controls the early warning."),
    Field("NEAR_CLOSE_THRESHOLD_PCT", "NEAR_CLOSE_THRESHOLD_PCT", "Trade Filters & Risk", "Near-close threshold %",
          type="float", default="2.0", min=0, step=0.5,
          help="How close price must get to a trade's SL/TP before a near-close warning posts."),
    Field("NEAR_TP_TIMEOUT_ENABLED", "NEAR_TP_TIMEOUT_ENABLED", "Trade Filters & Risk", "Near-TP timeout exit enabled",
          type="checkbox", default="true",
          help="If a trade gets most of the way to its target and then goes sideways there instead of "
               "actually tapping it, close it early at the live price to lock in the profit already made "
               "rather than risk giving it all back waiting for the exact target price."),
    Field("NEAR_TP_TIMEOUT_THRESHOLD_PCT", "NEAR_TP_TIMEOUT_THRESHOLD_PCT", "Trade Filters & Risk",
          "Near-TP timeout progress threshold %",
          type="float", default="80.0", min=1, max=99, step=1,
          help="How far toward the target (as a % of entry -> target 1 distance) price has to have travelled "
               "before the timeout-exit clock (below) starts. 80% means price is most of the way there but "
               "hasn't actually touched the target yet. Dropping back below this threshold resets the clock."),
    Field("NEAR_TP_TIMEOUT_MINUTES", "NEAR_TP_TIMEOUT_MINUTES", "Trade Filters & Risk",
          "Near-TP timeout duration (minutes)",
          type="number", default="10", min=1, max=1440, step=1,
          help="Once price has been at or above the progress threshold continuously for this many minutes "
               "without actually reaching the target, the trade is closed at the live price as a win. Only "
               "checked by the 60s trade_monitor loop, so real-world timing is accurate to within about a minute."),
    Field("NEAR_TP_STALL_CHECK_MINUTES", "NEAR_TP_STALL_CHECK_MINUTES", "Trade Filters & Risk",
          "Near-TP stall check window (minutes)",
          type="number", default="5", min=1, max=1439, step=1,
          help="A faster exit than the full timeout above: once price has been at or above the progress "
               "threshold, check the trailing window of this many minutes -- if price hasn't moved by more "
               "than 'Near-TP stall max fluctuation %' (below) in that window, the trade is closed early as a "
               "stall instead of waiting out the full 'Near-TP timeout duration'. Must be less than the timeout "
               "duration (e.g. 5 minutes when the timeout is 15) since it's meant to catch a stall sooner, not "
               "replace the full timeout."),
    Field("NEAR_TP_STALL_MAX_FLUCTUATION_PCT", "NEAR_TP_STALL_MAX_FLUCTUATION_PCT", "Trade Filters & Risk",
          "Near-TP stall max fluctuation %",
          type="float", default="0.5", min=0, max=20, step=0.1,
          help="If price moves less than this % (relative to entry) over the trailing stall-check window "
               "while sitting near the target, it's considered 'stalled' and the trade closes early to lock "
               "in the profit rather than waiting out the full timeout."),
    Field("RETROSPECTIVE_HISTORY_DAYS", "RETROSPECTIVE_HISTORY_DAYS", "Trade Filters & Risk",
          "Retrospective memory window (days)",
          type="number", default="60", min=5, max=365, step=1,
          help="How many past trading days the daily retrospective remembers (data/retrospective_history.json) "
               "in order to notice repeating problems (e.g. 'this is the 3rd day in a row VWAP has lost') instead "
               "of re-stating the same observation from scratch every day with no memory of yesterday."),

    # --- Data & display ---
    Field("DEFAULT_HISTORY_PERIOD", "DEFAULT_HISTORY_PERIOD", "Data & Display", "History period",
          default="10y", help="How much daily history to pull for live scanning, e.g. 10y, 5y, 2y, 1y."),
    Field("CURRENCY_SYMBOL", "CURRENCY_SYMBOL", "Data & Display", "Fallback currency symbol",
          type="select", default="€",
          options=[("€", "EUR (€)"), ("$", "USD ($)"), ("£", "GBP (£)")],
          help="Used only when a ticker's real trading currency can't be detected."),
    Field("MARKET_REGIME_TICKER", "MARKET_REGIME_TICKER", "Data & Display", "Market regime benchmark ticker",
          default="SPY", help="Benchmark index used to gauge the overall market trend."),

    # --- Account (informational sizing defaults) ---
    Field("ACCOUNT_BALANCE", "ACCOUNT_BALANCE", "Account Defaults", "Account balance",
          type="float", default="1000000", min=0, step=100,
          help="Seed value the first time data/account.json is created. Edit anytime with !account balance -- not read from .env after that."),
    Field("RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT", "Account Defaults", "Risk per trade %",
          type="float", default="0.01", min=0, step=0.01,
          help="The % of account balance you're willing to lose on a single trade if its stop-loss is hit -- "
               "a classic position-sizing input (e.g. 1% means a full stop-out only costs 1% of the account). "
               "This is informational only: seeded into data/account.json and shown by !account, but nothing "
               "in the live alert/scan pipeline uses it to size a position -- how many shares to actually buy "
               "is left entirely up to you. Edit anytime with !account risk PCT."),
    Field("MAX_OPEN_POSITIONS", "MAX_OPEN_POSITIONS", "Account Defaults", "Max open positions",
          type="number", default="30", min=1, step=1,
          help="Informational only, same as the two fields above: once this many paper trades are open, "
               "new alerts still post but the Discord embed shows a position-limit warning."),
    Field("MAX_POSITION_SIZE_PCT", "MAX_POSITION_SIZE_PCT", "Account Defaults", "Max position size % of account",
          type="float", default="0.1", min=0.01, max=100, step=0.01,
          help="Position-size cap: the suggested share count is clipped so shares × entry never exceeds "
               "this % of the account balance. Prevents a very tight stop on a cheap stock from implying "
               "a position that's a large fraction of the account (e.g. at 1% risk, a 0.50 stop on a "
               "$5 stock suggests 10× as many shares as a $5 stop on a $50 stock). 20% is a sensible "
               "ceiling for a single position; lower if you want more diversification headroom."),
    Field("POSITION_SIZING_MODE", "POSITION_SIZING_MODE", "Account Defaults", "Position sizing mode",
          type="select", default="risk_pct", options=[("risk_pct", "Risk % (fixed-fractional)"), ("account_pct", "Account % (fixed allocation)")],
          help="<b>Risk %</b> (the original model): size so a full stop-out costs exactly Risk per trade % of "
               "the account -- position size varies with how tight the stop is. <b>Account %</b>: size so the "
               "position itself is always exactly Position size % of account (below) of the account balance, "
               "regardless of stop distance -- e.g. a €1,000,000 account at 0.1% always opens a €1,000 "
               "position. Live-editable per account via `!account sizing risk|account`, same as the other "
               "Account Defaults below -- this .env value only seeds a brand-new data/account.json."),
    Field("POSITION_SIZE_PCT_OF_ACCOUNT", "POSITION_SIZE_PCT_OF_ACCOUNT", "Account Defaults",
          "Position size % of account",
          type="float", default="0.1", min=0.001, max=100, step=0.01,
          help="Only used when Position sizing mode above is 'Account %'. The position's total value (shares "
               "× entry) is sized to exactly this % of the account balance -- e.g. 0.1% on a €1,000,000 "
               "account opens a €1,000 position on every trade. Live-editable with `!account positionpct PCT`."),
    Field("MAX_POSITION_VALUE_ABSOLUTE", "MAX_POSITION_VALUE_ABSOLUTE", "Account Defaults",
          "Max position size (absolute $)",
          type="float", default="1000", min=0, step=10,
          help="Hard currency cap: a trade's position value (shares × entry) never exceeds this many currency "
               "units, full stop -- applied ON TOP OF (and independent of) the %-based caps above. Unlike a "
               "%-only cap, this holds regardless of what the account balance grows or shrinks to, so \"every "
               "trade costs at most $1,000\" stays true even if the balance changes. Set to 0 to disable and "
               "rely on the %-based cap alone. Live-editable with `!account maxposition <amount>`."),
    Field("MAX_RISK_AMOUNT_ABSOLUTE", "MAX_RISK_AMOUNT_ABSOLUTE", "Account Defaults",
          "Max loss per trade (absolute $)",
          type="float", default="100", min=0, step=10,
          help="Hard currency cap: the REAL risk if a trade's stop-loss is hit (final shares × stop distance) "
               "never exceeds this many currency units, regardless of sizing mode, Risk per trade %, or account "
               "balance. This is what actually guarantees a fixed max loss per trade -- a %-only risk setting "
               "silently stops meaning that the moment the balance changes. Set to 0 to disable. Live-editable "
               "with `!account maxrisk <amount>`."),

    # --- Secondary alerts (email + push, fires only on high-confidence qualifying setups) ---
    Field("SECONDARY_ALERT_MIN_CONFIDENCE", "SECONDARY_ALERT_MIN_CONFIDENCE", "Secondary Alerts",
          "Min confidence level for secondary alerts",
          type="select", default="4", options=["1", "2", "3", "4", "5"],
          help="Secondary channels (email, push) only fire for setups at this confidence level or above. "
               "Default 4 (High) avoids spam on marginal signals -- you still see everything in Discord."),
    Field("ALERT_EMAIL_ENABLED", "ALERT_EMAIL_ENABLED", "Secondary Alerts", "Email alerts enabled",
          type="checkbox", default="false",
          help="Send an email for every qualifying alert above the min confidence level. "
               "Requires SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and ALERT_EMAIL_TO to be configured."),
    Field("ALERT_EMAIL_TO", "ALERT_EMAIL_TO", "Secondary Alerts", "Alert recipient email address",
          help="Where alert emails are sent. Can be the same as SMTP_USER (send to yourself) or different."),
    Field("SMTP_HOST", "SMTP_HOST", "Secondary Alerts", "SMTP server host",
          default="smtp.gmail.com",
          help="SMTP server for sending alert emails. Gmail: smtp.gmail.com. Outlook: smtp.office365.com."),
    Field("SMTP_PORT", "SMTP_PORT", "Secondary Alerts", "SMTP server port",
          type="number", default="587", min=1, max=65535, step=1,
          help="587 for STARTTLS (recommended). 465 for SSL. 25 for unencrypted (not recommended)."),
    Field("SMTP_USER", "SMTP_USER", "Secondary Alerts", "SMTP username / sender address",
          help="Email address the alerts are sent FROM. For Gmail use an App Password (not your account password)."),
    Field("SMTP_PASSWORD", "SMTP_PASSWORD", "Secondary Alerts", "SMTP password",
          type="password", sensitive=True,
          help="SMTP login password. For Gmail, create an App Password at myaccount.google.com/apppasswords "
               "(requires 2FA). Never use your real account password here."),
    Field("ALERT_PUSH_ENABLED", "ALERT_PUSH_ENABLED", "Secondary Alerts", "Push notifications enabled (ntfy.sh)",
          type="checkbox", default="false",
          help="Send a push notification via ntfy.sh for every qualifying alert. Free, no account needed -- "
               "pick a unique topic name, set it below, and subscribe via the ntfy app on iOS/Android."),
    Field("NTFY_TOPIC", "NTFY_TOPIC", "Secondary Alerts", "ntfy.sh topic name",
          help="Your unique ntfy.sh topic -- the URL will be https://ntfy.sh/<topic>. Choose something "
               "hard to guess (e.g. swingbot-yourname-abc123) since anyone who knows the topic can subscribe."),

    # --- Multi-timeframe confluence ---
    Field("HTF_CONFLUENCE_ENABLED", "HTF_CONFLUENCE_ENABLED", "Multi-Timeframe Confluence",
          "Higher-timeframe bias filter enabled",
          type="checkbox", default="true",
          help="Check each ticker's own higher-timeframe EMA bias (50-day for short horizons, 200-day for "
               "longer ones) before accepting a signal. Counter-trend signals are penalised by "
               "HTF_COUNTER_TREND_PENALTY confidence points and flagged in the embed. They still post -- "
               "the filter is informational, not a hard suppressor -- unless the penalty drops them below "
               "MIN_ALERT_CONFIDENCE_LEVEL after the reduction."),
    Field("HTF_COUNTER_TREND_PENALTY", "HTF_COUNTER_TREND_PENALTY", "Multi-Timeframe Confluence",
          "Counter-trend confidence score penalty",
          type="number", default="15", min=0, max=40, step=5,
          help="How many raw confidence score points are subtracted when a signal goes against its "
               "ticker's own higher-timeframe EMA trend. 15 is enough to drop a borderline Level 3 "
               "signal to Level 2 (and thus below the default MIN_ALERT_CONFIDENCE_LEVEL=3 gate). "
               "Set 0 to disable the penalty while keeping the counter-trend label visible."),

    # --- Plan Engine v2 (rollout flags, spec 2026-07-11-unified-plan-engine-design) ---
    Field("PLAN_ENGINE_V2", "PLAN_ENGINE_V2", "Plan Engine v2", "Plan engine v2 mode",
          type="select", default="on", options=["off", "shadow", "on"],
          help="off = legacy behavior. shadow = v2 plans are computed and logged to "
               "data/shadow_plans.jsonl during scans but NOT posted (parity evidence for cutover). "
               "on = scan alerts price and emit v2 plans (badges, TP1/TP2, entry triggers). "
               "Defaults to 'on' for immediate deployment; set to 'shadow' first if you'd rather "
               "compare against legacy numbers for a few sessions before trusting it live."),
    Field("SCALE_OUT_ENABLED", "SCALE_OUT_ENABLED", "Plan Engine v2", "Scale-out exits enabled",
          type="checkbox", default="true",
          help="At TP1, close 50% and move the stop to break-even; the runner rides toward TP2 "
               "with a chandelier ATR trail. Backtested under this exact exit model (see README's "
               "Plan Engine v2 section for the validated win-rate/expectancy numbers behind it)."),
    Field("INTRADAY_MANAGER_V2", "INTRADAY_MANAGER_V2", "Plan Engine v2", "Intraday plan manager enabled",
          type="checkbox", default="true",
          help="The 60s monitor manages the full plan lifecycle: pending entry triggers, break-even "
               "moves, TP1 partials, runner trail, invalidation - with a Discord alert per transition."),

    # --- Data sources (optional external market-data APIs) ---
    Field("FMP_API_KEY", "FMP_API_KEY", "Data Sources", "Financial Modeling Prep API key",
          type="password", sensitive=True, default="",
          help="Optional. API key for Financial Modeling Prep (financialmodelingprep.com), used by "
               "the FMP data crawler (scripts/fmp_crawl.py, core/fmp_client.py) to pull prices, "
               "fundamentals, earnings, transcripts, and more. Works on the free tier -- endpoints "
               "your tier can't reach are skipped, not fatal -- and on any paid tier with no code "
               "change. Leave blank to disable FMP crawling."),

    # --- Admin UI (affects the admin container, not the bot -- see docstring) ---
    Field("ADMIN_USERNAME", "ADMIN_USERNAME", "Admin UI", "Admin username",
          default="admin", hot_reloadable=False,
          help="Requires restarting the ADMIN container to take effect, not the bot."),
    Field("ADMIN_PASSWORD", "ADMIN_PASSWORD", "Admin UI", "Admin password",
          type="password", default="admin", sensitive=True, hot_reloadable=False,
          help="Requires restarting the ADMIN container to take effect, not the bot. Change this from the default."),
    Field("ADMIN_PORT", "ADMIN_PORT", "Admin UI", "Admin UI port",
          type="number", default="1234", min=1, max=65535, step=1, hot_reloadable=False,
          help="Requires restarting the ADMIN container (Flask can't rebind its own port live)."),
    Field("DASHBOARD_REFRESH_SECONDS", "DASHBOARD_REFRESH_SECONDS", "Admin UI", "Dashboard auto-refresh (seconds)",
          type="number", default="15", min=2, max=300, step=1,
          help="How often the Dashboard page's open-trades table auto-refreshes while the 'Auto-refresh' "
               "checkbox is on. Takes effect on your next Dashboard page load -- no restart needed."),
    Field("LOGS_REFRESH_SECONDS", "LOGS_REFRESH_SECONDS", "Admin UI", "Logs auto-refresh (seconds)",
          type="number", default="10", min=2, max=300, step=1,
          help="How often the Logs page auto-refreshes while its own 'Auto-refresh' checkbox is on. "
               "Takes effect on your next Logs page load -- no restart needed."),
]

_CASTERS = {
    "number": lambda v: int(v),
    "float": lambda v: float(v),
    "checkbox": lambda v: str(v).lower() == "true",
}


def _cast(f: Field, raw: str):
    # A couple of "select" fields need a specific underlying type rather
    # than the raw string the <select> posts back -- handled by attr name
    # so it doesn't matter whether the field is rendered as select/text/etc.
    if f.attr == "LOG_LEVEL":
        return raw.upper()
    if f.attr in ("MIN_ALERT_CONFIDENCE_LEVEL", "SECONDARY_ALERT_MIN_CONFIDENCE"):
        return int(raw)
    if f.attr == "PLAN_ENGINE_V2":
        v = str(raw).lower()
        if v not in ("off", "shadow", "on"):
            logging.getLogger("swingbot.config").warning(
                "invalid PLAN_ENGINE_V2=%r, falling back to 'off'", raw)
            return "off"
        return v
    caster = _CASTERS.get(f.type)
    return caster(raw) if caster else raw


def _apply_env() -> dict:
    """
    Reads every FIELDS entry from the current environment (after
    load_dotenv has populated os.environ) and sets the corresponding
    module global. Returns {attr: (old_value, new_value)} for anything
    that actually changed, so reload() can log what happened.
    """
    changed = {}
    g = globals()
    for f in FIELDS:
        raw = os.getenv(f.key, f.default)
        try:
            new_value = _cast(f, raw)
        except (ValueError, TypeError):
            # A malformed value in .env must not leave the global entirely
            # undefined -- on the very first load (module import time)
            # there IS no "previous value" to keep, so g.get(f.attr) would
            # be None and the `continue` below used to skip setting the
            # attribute at all, leaving any later `config.SOME_ATTR` access
            # raise AttributeError instead of falling back to the
            # documented default. Fall back to the field's own default
            # instead, which is guaranteed well-formed.
            log.warning("Could not parse %s=%r as %s -- falling back to default %r",
                        f.key, raw, f.type, f.default)
            try:
                new_value = _cast(f, f.default)
            except (ValueError, TypeError):
                log.error("Field %s has an invalid default %r; leaving unset", f.key, f.default)
                continue
        old_value = g.get(f.attr)
        g[f.attr] = new_value
        if old_value != new_value:
            changed[f.attr] = (old_value, new_value)
    return changed


def _load_dotenv_file() -> tuple:
    """
    Returns (loaded, used_canonical_path). Tries the project's own ENV_PATH
    first; if that file doesn't exist, falls back to python-dotenv's default
    upward search from the current working directory -- which can find a
    completely different, unrelated .env file. Callers need to know WHICH
    happened so startup logging doesn't claim the canonical path was used
    when it actually wasn't.
    """
    if load_dotenv(dotenv_path=ENV_PATH, override=True):
        return True, True
    if load_dotenv(override=True):
        return True, False
    return False, False


_DOTENV_LOADED, _DOTENV_FROM_CANONICAL_PATH = _load_dotenv_file()
_apply_env()
_ENV_MTIME: float = os.path.getmtime(ENV_PATH) if os.path.exists(ENV_PATH) else 0.0


def reload() -> dict:
    """
    Re-reads .env from disk and updates every FIELDS-backed global in
    place. Returns {attr: (old, new)} for whatever actually changed.
    Safe to call repeatedly (e.g. on every SIGHUP) -- a no-op env
    produces an empty dict.
    """
    global _DOTENV_LOADED, _DOTENV_FROM_CANONICAL_PATH, _ENV_MTIME
    _DOTENV_LOADED, _DOTENV_FROM_CANONICAL_PATH = _load_dotenv_file()
    _ENV_MTIME = os.path.getmtime(ENV_PATH) if os.path.exists(ENV_PATH) else 0.0
    changed = _apply_env()
    if changed:
        log.info("Config reloaded from %s -- %d value(s) changed:", ENV_PATH, len(changed))
        for attr, (old, new) in changed.items():
            f = next((f for f in FIELDS if f.attr == attr), None)
            display_old = "***" if f and f.sensitive else old
            display_new = "***" if f and f.sensitive else new
            log.info("  %s: %r -> %r", attr, display_old, display_new)
    else:
        log.debug("Config reloaded from %s -- no changes.", ENV_PATH)
    return changed


def auto_reload_if_changed() -> dict:
    """
    Checks if .env has been modified on disk since the last load/reload.
    If so, calls reload() and returns the changed values; otherwise a
    no-op that returns {}. Cheap enough to call at the start of every
    scan -- the mtime check is a single stat() call with no file I/O
    unless something actually changed.
    """
    if not os.path.exists(ENV_PATH):
        return {}
    try:
        current_mtime = os.path.getmtime(ENV_PATH)
    except OSError:
        return {}
    if current_mtime <= _ENV_MTIME:
        return {}
    log.info(".env modified on disk (mtime changed) -- auto-reloading config before this scan")
    return reload()


def _mask(value: str | None) -> str:
    """Shows just enough of a secret to confirm it loaded, never the full value."""
    if not value:
        return "NOT SET"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


def log_startup_config() -> None:
    """
    Logs exactly what config.py picked up from the environment, so a
    misconfigured or missing .env fails loudly at startup instead of
    silently falling back to defaults. Call this once, right after
    `import config`, before the bot connects to Discord.
    """
    if _DOTENV_LOADED and _DOTENV_FROM_CANONICAL_PATH:
        log.info("Loaded .env from %s", ENV_PATH)
    elif _DOTENV_LOADED:
        log.warning(
            "No .env found at the expected path %s -- loaded a DIFFERENT .env "
            "found via the current working directory instead. Settings below "
            "may not be what you expect; consider moving your .env to %s.",
            ENV_PATH, ENV_PATH,
        )
    else:
        log.warning(
            "No .env file found at %s (or the current directory) -- "
            "falling back to whatever is already in the process environment "
            "and the hardcoded defaults below.", ENV_PATH
        )

    log.info("---- Configuration in effect ----")
    g = globals()
    for f in FIELDS:
        value = g.get(f.attr)
        log.info("%s=%s", f.key, _mask(value) if f.sensitive else value)
    log.info("----------------------------------")

    # The admin web UI has no other authentication layer -- if it's still on
    # the documented default admin/admin (unlike DISCORD_TOKEN, there's no
    # SystemExit gate for this since the bot itself doesn't need it to run),
    # make sure that's loud and impossible to miss in the logs rather than a
    # silent security footgun.
    if g.get("ADMIN_USERNAME") == "admin" and g.get("ADMIN_PASSWORD") == "admin":
        log.warning(
            "SECURITY: the admin UI is using the DEFAULT credentials (admin/admin). "
            "Anyone who can reach it can view and control the bot. Set ADMIN_USERNAME "
            "and ADMIN_PASSWORD in .env before exposing it beyond localhost."
        )

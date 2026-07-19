"""Page-rendering blueprint for the cockpit's new sections: Plans,
Strategies, Calibration, Journal, Tuning. Split out of app.py (which keeps
Dashboard/Performance/Watchlist/Settings/Logs) purely to keep any one file
from growing unbounded -- same reasoning as api.py. Every view here uses
app.py's existing require_auth (HTML 401 challenge, not JSON) and _render
helper, since these are full pages a human loads in a browser, not fetch()
targets (those live in api.py).
"""
from flask import Blueprint

from .app import _render, require_auth

pages = Blueprint("pages", __name__)


@pages.route("/plans", methods=["GET"])
@require_auth
def plans_page():
    return _render("Plans", "plans", "plans.html")


@pages.route("/strategies", methods=["GET"])
@require_auth
def strategies_page():
    return _render("Strategies", "strategies", "strategies.html")


@pages.route("/calibration", methods=["GET"])
@require_auth
def calibration_page():
    return _render("Calibration", "calibration", "calibration.html")


@pages.route("/journal", methods=["GET"])
@require_auth
def journal_page():
    return _render("Journal", "journal", "journal.html")


@pages.route("/tuning", methods=["GET"])
@require_auth
def tuning_page():
    return _render("Tuning", "tuning", "tuning.html")

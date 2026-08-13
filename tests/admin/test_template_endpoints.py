"""Every `url_for()` in a template resolves to a registered endpoint.

A Jinja template naming an endpoint that does not exist raises
`BuildError` at RENDER time, not at import time — so it is invisible until
someone opens that page, which in this project can be days after the deploy
that broke it.

This replaces a hardcoded list of 23 endpoint names that lived in
`.github/workflows/deploy.yml`. That list had drifted: the templates actually
reference 44, and every `pages.*` endpoint was missing from it — so the check
was passing while covering barely half of what it claimed. Deriving the list
from the templates is what stops that happening again, and it belongs here
rather than in CI so it runs on every local `testrun.py` too.

NG19 TRIAGE: **delete with the templates.** This tests Jinja templates and
nothing else; when NG57 removes `swingbot/admin/templates/`, this file goes
with it. It is not testing the SPA, which has no `url_for`.
"""
import re

import pytest

from swingbot.admin.app import app

TEMPLATES = app.jinja_loader.searchpath[0] if app.jinja_loader.searchpath else None

#: Handles both quote styles and optional whitespace. Endpoint names are
#: identifiers plus the `blueprint.view` dot form.
_URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z_][A-Za-z0-9_.]*)['"]""")


def _referenced() -> dict[str, set[str]]:
    """{endpoint: {template names that reference it}}."""
    import os

    found: dict[str, set[str]] = {}
    for name in os.listdir(TEMPLATES):
        if not name.endswith(".html"):
            continue
        path = os.path.join(TEMPLATES, name)
        with open(path, encoding="utf-8") as fh:
            for endpoint in _URL_FOR.findall(fh.read()):
                found.setdefault(endpoint, set()).add(name)
    return found


def test_templates_exist_to_check():
    """Guards the guard: an empty scan would make every assertion below pass."""
    assert TEMPLATES is not None, "no Jinja template search path"
    assert _referenced(), "no url_for() calls found — is the scan looking in the right place?"


def test_every_endpoint_a_template_names_is_registered():
    registered = {rule.endpoint for rule in app.url_map.iter_rules()}
    missing = {
        endpoint: sorted(templates)
        for endpoint, templates in _referenced().items()
        if endpoint not in registered
    }
    assert not missing, (
        "Templates reference endpoints that are not registered. Each of these "
        "raises BuildError when the page is opened:\n"
        + "\n".join(f"  {e} — referenced by {', '.join(t)}" for e, t in sorted(missing.items()))
    )


@pytest.mark.parametrize("endpoint", sorted(_referenced()) if TEMPLATES else [])
def test_endpoint_is_registered(endpoint):
    """Same assertion, one test per endpoint, so a failure names the endpoint
    in its node id rather than only in a message."""
    assert endpoint in {rule.endpoint for rule in app.url_map.iter_rules()}

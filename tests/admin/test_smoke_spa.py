"""NG54 — the deploy smoke test's parsing.

`scripts/smoke_spa.py` is what stands between a broken bundle and production,
so the part of it that decides WHICH URLs to check is worth testing. The rest
of the script is HTTP orchestration, which this repo's convention leaves
untested (same reasoning as `test_run_backtest_range.py`).

The logic under test is two lines long and is exactly the logic that failed in
the product: take the asset URLs index.html declares, and resolve them the way
a browser does — against `<base href>`, not against the page's own path. A
smoke test that resolved them any other way would have passed on the broken
build.
"""
import urllib.parse

import pytest

from scripts.smoke_spa import _ASSET_RE

# The real shape of an Angular-built index.html, trimmed. Both the module
# script and the modulepreload links matter: the preloads are how the bundle's
# lazy chunks are named, and they 404ed too.
INDEX = """<!doctype html>
<html lang="en"><head>
  <base href="/app/">
  <link rel="icon" type="image/x-icon" href="favicon.ico">
  <link rel="stylesheet" href="styles-64JPVJE7.css" media="print">
  <noscript><link rel="stylesheet" href="styles-64JPVJE7.css"></noscript>
</head><body>
  <sb-root></sb-root>
  <link rel="modulepreload" href="chunk-IE4I2EOF.js">
  <script src="main-VYFJAEQU.js" type="module"></script>
</body></html>"""


def test_finds_every_asset_the_page_declares():
    assets = _ASSET_RE.findall(INDEX)
    assert "main-VYFJAEQU.js" in assets
    assert "chunk-IE4I2EOF.js" in assets
    assert "styles-64JPVJE7.css" in assets
    assert "favicon.ico" in assets


def test_resolves_through_base_href_not_the_page_path():
    """The whole point. `/cockpit` + `main-X.js` is NOT `/cockpit/main-X.js`.

    A browser resolves against <base href>, so the correct answer is
    `/app/main-X.js`. Getting this wrong in either direction makes the smoke
    test agree with a build that the browser rejects.
    """
    resolved = [urllib.parse.urljoin("/app/", a) for a in _ASSET_RE.findall(INDEX)]
    assert "/app/main-VYFJAEQU.js" in resolved
    assert "/app/chunk-IE4I2EOF.js" in resolved
    assert not any(r.startswith("/cockpit") for r in resolved)


def test_the_broken_build_resolves_to_root_which_is_what_404ed():
    """The regression, spelled out.

    With `<base href="/">` — Angular's default, and what shipped before NG54 —
    the same file resolves to `/main-X.js`. Flask serves the bundle at `/app/`,
    so every one of these 404s and the page renders black. This asserts the
    two really are different, which is the reason the check has to resolve
    rather than assume.
    """
    broken = [urllib.parse.urljoin("/", a) for a in _ASSET_RE.findall(INDEX)]
    correct = [urllib.parse.urljoin("/app/", a) for a in _ASSET_RE.findall(INDEX)]
    assert broken != correct
    assert "/main-VYFJAEQU.js" in broken


@pytest.mark.parametrize("absolute", [
    "https://cdn.example.com/x.js",
    "http://cdn.example.com/x.css",
])
def test_absolute_urls_are_filtered_out_by_the_caller(absolute):
    """The regex still matches them; the caller drops them.

    Pinned because this repo has a zero-CDN constraint: if an absolute URL
    ever appears in the built index.html, that is a defect to find in review,
    not something the deploy check should be fetching from a third party.
    """
    html = f'<script src="{absolute}"></script>'
    matched = _ASSET_RE.findall(html)
    assert matched == [absolute]
    assert all(a.startswith(("http://", "https://")) for a in matched)

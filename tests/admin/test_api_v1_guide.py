"""v235 V235-5: GET /api/v1/guide and /api/v1/guide/<slug>."""
import logging

import pytest

from swingbot import config
from swingbot.admin.guide import chapters as chapters_mod
from tests.admin.api_v1_contract import assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def guide_root(tmp_path, monkeypatch):
    """An empty docs/guide stand-in; the route module's cache is cleared around it."""
    from swingbot.admin.api_v1 import guide
    root = tmp_path / "guide"
    root.mkdir()
    monkeypatch.setattr(chapters_mod, "guide_dir", lambda: root)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    guide.clear_cache()
    yield root
    guide.clear_cache()


def _chapter(root, order: int, slug: str, body: str, title: str = "") -> None:
    (root / f"{order:02d}-{slug}.md").write_text(
        f"---\ntitle: {title or slug.title()}\nslug: {slug}\norder: {order}\n"
        f"reviewed_for: 2.19.2\nsources: []\n---\n{body}", encoding="utf-8")


# --- auth --------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/v1/guide", "/api/v1/guide/what-it-is"])
def test_requires_auth(client, guide_root, path):
    assert client.get(path).status_code == 401


# --- index -------------------------------------------------------------------

def test_index_lists_chapters_by_order_with_headings(logged_in, guide_root):
    _chapter(guide_root, 12, "glossary", "## Terms\n### R multiple\n", title="Glossary")
    _chapter(guide_root, 1, "what-it-is", "> **In plain words** paper only.\n\n## The notice\n",
             title="What the bot is (and isn't)")
    resp = logged_in.get("/api/v1/guide")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")
    body = resp.get_json()
    assert_shape(body, {"chapters": list})
    first, second = body["chapters"]
    assert_shape(first, {"slug": str, "title": str, "order": int, "reviewed_for": str,
                         "headings": list}, where="chapters[0]")
    assert [first["slug"], second["slug"]] == ["what-it-is", "glossary"]
    assert first["title"] == "What the bot is (and isn't)"
    assert first["reviewed_for"] == "2.19.2"
    assert first["headings"] == [{"level": 2, "text": "The notice", "anchor": "the-notice"}]
    assert second["headings"] == [
        {"level": 2, "text": "Terms", "anchor": "terms"},
        {"level": 3, "text": "R multiple", "anchor": "r-multiple"},
    ]


def test_index_is_empty_without_chapters(logged_in, guide_root):
    assert logged_in.get("/api/v1/guide").get_json() == {"chapters": []}


def test_index_headings_come_from_the_resolved_body(logged_in, guide_root):
    _chapter(guide_root, 8, "sizing-risk", "## Stops past {{MAX_STOP_LOSS_PCT}}\n")
    heading = logged_in.get("/api/v1/guide").get_json()["chapters"][0]["headings"][0]
    assert heading == {"level": 2, "text": "Stops past 2%", "anchor": "stops-past-2"}


# --- one chapter -------------------------------------------------------------

def test_chapter_returns_resolved_markdown(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "Stop cap {{ MAX_STOP_LOSS_PCT }}.\n", title="What")
    resp = logged_in.get("/api/v1/guide/what-it-is")
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, {"slug": str, "title": str, "reviewed_for": str, "markdown": str})
    assert body == {"slug": "what-it-is", "title": "What", "reviewed_for": "2.19.2",
                    "markdown": "Stop cap 2%.\n"}


def test_placeholders_resolve_per_request_while_files_stay_cached(logged_in, guide_root,
                                                                  monkeypatch):
    _chapter(guide_root, 1, "what-it-is", "Cap {{MAX_STOP_LOSS_PCT}}\n")
    assert logged_in.get("/api/v1/guide/what-it-is").get_json()["markdown"] == "Cap 2%\n"
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 1.5)          # a hot reload
    _chapter(guide_root, 3, "pipeline", "New file\n")               # not served until restart
    assert logged_in.get("/api/v1/guide/what-it-is").get_json()["markdown"] == "Cap 1.5%\n"
    assert [c["slug"] for c in logged_in.get("/api/v1/guide").get_json()["chapters"]] == [
        "what-it-is"]


def test_index_resolves_each_placeholder_once_across_chapters(logged_in, guide_root, monkeypatch):
    from swingbot.admin.guide import placeholders
    calls = []
    table = dict(placeholders.PLACEHOLDERS)
    table["version.bot"] = lambda: calls.append(1) or "9.9"
    monkeypatch.setattr(placeholders, "PLACEHOLDERS", table)
    _chapter(guide_root, 1, "what-it-is", "## One\nv {{version.bot}}\n")
    _chapter(guide_root, 3, "pipeline", "## Two\nv {{version.bot}}\n")
    assert len(logged_in.get("/api/v1/guide").get_json()["chapters"]) == 2
    assert len(calls) == 1


def test_unknown_slug_is_404(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "Text\n")
    assert_error(logged_in.get("/api/v1/guide/nope"), "not_found", 404)


# --- failures ----------------------------------------------------------------

def test_unknown_placeholder_is_500_and_logged_never_raw(logged_in, guide_root, caplog):
    _chapter(guide_root, 1, "what-it-is", "Secret {{DISCORD_TOKEN}}\n")
    caplog.set_level(logging.ERROR, logger="swingbot.admin.api_v1.guide")
    resp = logged_in.get("/api/v1/guide/what-it-is")
    assert_error(resp, "guide_placeholder", 500)
    assert "{{" not in resp.get_data(as_text=True)
    assert "DISCORD_TOKEN" in caplog.text and "what-it-is" in caplog.text


def test_unknown_placeholder_also_fails_the_index(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "## Heading\n\n{{nope}}\n")
    assert_error(logged_in.get("/api/v1/guide"), "guide_placeholder", 500)


def test_malformed_chapter_is_500_guide_invalid(logged_in, guide_root):
    (guide_root / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert_error(logged_in.get("/api/v1/guide"), "guide_invalid", 500)
    assert_error(logged_in.get("/api/v1/guide/what-it-is"), "guide_invalid", 500)


# --- access ------------------------------------------------------------------

def test_guide_is_not_admin_only():
    from swingbot.admin import access
    assert not any("/api/v1/guide".startswith(p) for p in access.ADMIN_ONLY_PREFIXES)

"""NG15 — /api/v1/system/settings, the highest-risk endpoint in the phase.

A bad write here takes the bot down silently: the container hot-reloads
whatever landed in .env. The tests that matter most are the ones asserting
what a save does NOT touch --
`test_omitted_keys_are_left_alone`, `test_an_echoed_mask_is_never_written`
and `test_an_unchecked_box_is_not_manufactured_from_absence`. Each pins a
way a plausible client could wipe real configuration while being told it
succeeded.

Isolation comes from `admin_app`: it patches `config.ENV_PATH` at a tmp_path
and reloads helpers.py, whose module-level `ENV_PATH` alias is what every
write below travels through. Without that reload these tests would rewrite
the developer's real .env.
"""
import pytest

from tests.admin.api_v1_contract import assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
MASK = "•••"


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def env_file(admin_app, tmp_path):
    """The isolated .env, writable and readable as a dict."""
    from swingbot.admin import helpers

    path = tmp_path / ".env"

    def _write(values):
        path.write_text(
            "\n".join(f"{k}={v}" for k, v in values.items()) + "\n",
            encoding="utf-8")

    def _read():
        from dotenv import dotenv_values
        return dict(dotenv_values(str(path)))

    _write.read = _read
    _write.path = path
    assert helpers.ENV_PATH == str(path), (
        "helpers.ENV_PATH did not follow the tmp .env -- a write here would "
        "hit the developer's real .env"
    )
    return _write


@pytest.fixture(autouse=True)
def no_docker(monkeypatch):
    """The hot-reload signal needs a Docker socket. Its absence is a normal
    outcome, not a failure, and every save test asserts against a known one."""
    monkeypatch.setattr("swingbot.admin.helpers._hot_reload_bot_container",
                        lambda: (True, "reloaded"))


def _fields(body):
    return {f["key"]: f for s in body["sections"] for f in s["fields"]}


# --- schema -------------------------------------------------------------

def test_requires_auth(client):
    assert_error(client.get("/api/v1/system/settings"), "auth", 401)


def test_document_shape(logged_in, env_file):
    body = logged_in.get("/api/v1/system/settings").get_json()
    assert_shape(body, {"sections": list, "audit": list, "restart_available": bool})
    assert_shape(body["sections"][0],
                 {"name": str, "icon": str, "description": str, "fields": list},
                 where="section")


def test_schema_and_values_travel_together(logged_in, env_file):
    """Spec v14 Decision 8: the form renders from the schema, so every field
    must carry what the widget needs AND what it currently holds. Two round
    trips for one form is what this avoids."""
    field = _fields(logged_in.get("/api/v1/system/settings").get_json())["SESSION_START_HOUR"]
    assert_shape(field, {
        "key": str, "label": str, "type": str, "value": object,
        "default": str, "help": str, "min": (int, float, type(None)),
        "max": (int, float, type(None)), "step": (int, float, type(None)),
        "options": list, "sensitive": bool, "hot_reloadable": bool,
    }, where="field")
    assert field["type"] == "number"
    assert field["min"] == 0 and field["max"] == 23


def test_every_configured_field_is_present(logged_in, env_file):
    from swingbot import config

    served = _fields(logged_in.get("/api/v1/system/settings").get_json())
    assert set(served) == {f.key for f in config.FIELDS}


def test_a_new_field_appears_with_no_endpoint_change(logged_in, env_file, monkeypatch):
    """The property the Jinja UI has today and the rebuild must not lose: a
    new Field in config.py reaches the UI with zero code change here or in the
    SPA. If this endpoint ever grows an explicit field list, this fails."""
    from swingbot import config
    from swingbot.admin import helpers

    invented = config.Field("NG15_INVENTED", "NG15_INVENTED", "Data & Display",
                            "Invented setting", type="number", default="7",
                            min=0, max=10, help="only exists inside this test")
    fields = list(config.FIELDS) + [invented]
    monkeypatch.setattr(config, "FIELDS", fields)
    monkeypatch.setattr(helpers, "FIELDS_BY_KEY", {f.key: f for f in fields})
    monkeypatch.setattr(helpers, "FIELDS_BY_SECTION",
                        helpers.FIELDS_BY_SECTION + [("Data & Display", [invented])])

    served = _fields(logged_in.get("/api/v1/system/settings").get_json())
    assert "NG15_INVENTED" in served
    assert served["NG15_INVENTED"]["max"] == 10

    logged_in.put("/api/v1/system/settings", json={"settings": {"NG15_INVENTED": "3"}})
    assert env_file.read()["NG15_INVENTED"] == "3"


def test_select_options_are_value_label_pairs(logged_in, env_file):
    options = _fields(logged_in.get("/api/v1/system/settings").get_json())["LOG_LEVEL"]["options"]
    assert {"value": "DEBUG", "label": "DEBUG"} in options


def test_checkbox_value_is_a_real_bool(logged_in, env_file):
    """Not the string "true". The SPA binds this straight to a checkbox, and
    every non-empty string is truthy in JavaScript."""
    env_file({"REVERSAL_ENABLED": "false"})
    value = _fields(logged_in.get("/api/v1/system/settings").get_json())["REVERSAL_ENABLED"]["value"]
    assert value is False


# --- masking ------------------------------------------------------------

def test_sensitive_values_are_masked_in_the_document(logged_in, env_file):
    env_file({"DISCORD_TOKEN": "a-real-token"})
    served = _fields(logged_in.get("/api/v1/system/settings").get_json())
    assert served["DISCORD_TOKEN"]["value"] == MASK
    assert "a-real-token" not in str(served)


def test_sensitive_values_are_masked_in_the_diff(logged_in, env_file):
    env_file({"DISCORD_TOKEN": "old-token"})
    diff = logged_in.post("/api/v1/system/settings/preview",
                          json={"settings": {"DISCORD_TOKEN": "new-token"}}).get_json()["diff"]
    row = next(d for d in diff if d["key"] == "DISCORD_TOKEN")
    assert row["old"] == MASK and row["new"] == MASK


def test_sensitive_values_are_masked_in_the_audit_log(logged_in, env_file):
    env_file({"DISCORD_TOKEN": "old-token"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"DISCORD_TOKEN": "new-token"}})

    audit = logged_in.get("/api/v1/system/settings").get_json()["audit"]
    assert audit, "a save must leave an audit entry"
    assert "new-token" not in str(audit) and "old-token" not in str(audit)


def test_an_echoed_mask_is_never_written(logged_in, env_file):
    """The failure this exists to prevent: a client PUTs back the object it
    was given, mask included, and saves ••• as the Discord token. The bot
    then cannot connect, and the .env looks plausible."""
    env_file({"DISCORD_TOKEN": "a-real-token"})
    logged_in.put("/api/v1/system/settings",
                  json={"settings": {"DISCORD_TOKEN": MASK, "LOG_LEVEL": "DEBUG"}})

    saved = env_file.read()
    assert saved["DISCORD_TOKEN"] == "a-real-token"
    assert saved["LOG_LEVEL"] == "DEBUG", "the rest of the save must still apply"


def test_a_blank_sensitive_value_is_no_change(logged_in, env_file):
    env_file({"DISCORD_TOKEN": "a-real-token"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"DISCORD_TOKEN": ""}})
    assert env_file.read()["DISCORD_TOKEN"] == "a-real-token"


def test_a_sensitive_value_can_still_be_deliberately_set(logged_in, env_file):
    env_file({"DISCORD_TOKEN": "old-token"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"DISCORD_TOKEN": "brand-new"}})
    assert env_file.read()["DISCORD_TOKEN"] == "brand-new"


# --- what a save must not touch ----------------------------------------

def test_omitted_keys_are_left_alone(logged_in, env_file):
    """_build_env_text rewrites the WHOLE file, so a partial body handed to it
    straight would write KEY= for every field the client did not mention.
    Omitted means unchanged, and this is the guard."""
    env_file({"LOG_LEVEL": "WARNING", "SESSION_START_HOUR": "9",
              "DISCORD_CHANNEL_TRADES_ID": "12345"})

    logged_in.put("/api/v1/system/settings", json={"settings": {"LOG_LEVEL": "DEBUG"}})

    saved = env_file.read()
    assert saved["LOG_LEVEL"] == "DEBUG"
    assert saved["SESSION_START_HOUR"] == "9"
    assert saved["DISCORD_CHANNEL_TRADES_ID"] == "12345"


def test_an_unchecked_box_is_not_manufactured_from_absence(logged_in, env_file):
    """A browser form posts an unchecked box by OMITTING it, so every helper
    downstream reads absence as false. A JSON client omitting a checkbox it
    never touched must not silently turn the feature off."""
    env_file({"REVERSAL_ENABLED": "true"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"LOG_LEVEL": "DEBUG"}})
    assert env_file.read()["REVERSAL_ENABLED"] == "true"


def test_a_checkbox_can_still_be_turned_off(logged_in, env_file):
    env_file({"REVERSAL_ENABLED": "true"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"REVERSAL_ENABLED": False}})
    assert env_file.read()["REVERSAL_ENABLED"] == "false"


def test_custom_variables_survive_a_save(logged_in, env_file):
    """A hand-added variable the structured UI knows nothing about is
    preserved at the bottom of the file -- _build_env_text's behaviour, kept
    by routing through it rather than reimplementing the writer."""
    env_file({"LOG_LEVEL": "INFO", "MY_OWN_VAR": "keep-me"})
    logged_in.put("/api/v1/system/settings", json={"settings": {"LOG_LEVEL": "DEBUG"}})
    assert env_file.read()["MY_OWN_VAR"] == "keep-me"


# --- validation ---------------------------------------------------------

def test_a_missing_settings_object_is_rejected(logged_in, env_file):
    assert_error(logged_in.put("/api/v1/system/settings", json={}), "invalid", 400)


def test_an_unknown_key_is_rejected(logged_in, env_file):
    """Strict where import is lenient: this body was assembled field by field
    from the endpoint's own schema, so an unknown key is a client bug."""
    assert_error(
        logged_in.put("/api/v1/system/settings", json={"settings": {"NOT_A_SETTING": "1"}}),
        "invalid", 400)


@pytest.mark.parametrize("value", ["not-a-number", "12abc"])
def test_a_non_numeric_value_is_rejected(logged_in, env_file, value):
    assert_error(
        logged_in.put("/api/v1/system/settings",
                      json={"settings": {"SESSION_START_HOUR": value}}),
        "invalid", 400)


@pytest.mark.parametrize("value", ["-1", "24"])
def test_a_numeric_value_outside_its_range_is_rejected(logged_in, env_file, value):
    """min/max are in the schema the SPA renders from; enforcing them only in
    the browser means a direct API call writes an hour of 25 and the scan
    window silently never opens."""
    assert_error(
        logged_in.put("/api/v1/system/settings",
                      json={"settings": {"SESSION_START_HOUR": value}}),
        "invalid", 400)


def test_an_invalid_select_option_is_rejected(logged_in, env_file):
    assert_error(
        logged_in.put("/api/v1/system/settings", json={"settings": {"LOG_LEVEL": "LOUD"}}),
        "invalid", 400)


def test_a_rejected_save_writes_nothing(logged_in, env_file):
    env_file({"LOG_LEVEL": "INFO"})
    logged_in.put("/api/v1/system/settings",
                  json={"settings": {"LOG_LEVEL": "DEBUG", "SESSION_START_HOUR": "99"}})
    assert env_file.read()["LOG_LEVEL"] == "INFO", (
        "validation must reject the whole body before any write"
    )


# --- preview / save reporting -------------------------------------------

def test_preview_shows_only_changed_fields(logged_in, env_file):
    env_file({"LOG_LEVEL": "INFO", "SESSION_START_HOUR": "9"})
    body = logged_in.post("/api/v1/system/settings/preview",
                          json={"settings": {"LOG_LEVEL": "DEBUG",
                                             "SESSION_START_HOUR": "9"}}).get_json()
    assert [d["key"] for d in body["diff"]] == ["LOG_LEVEL"]


def test_preview_does_not_write(logged_in, env_file):
    env_file({"LOG_LEVEL": "INFO"})
    logged_in.post("/api/v1/system/settings/preview",
                   json={"settings": {"LOG_LEVEL": "DEBUG"}})
    assert env_file.read()["LOG_LEVEL"] == "INFO"


def test_preview_and_save_agree_on_the_diff(logged_in, env_file):
    """The user approves the preview. If save computed its diff differently,
    they would be approving one change and getting another."""
    env_file({"LOG_LEVEL": "INFO", "SESSION_START_HOUR": "9"})
    settings = {"settings": {"LOG_LEVEL": "DEBUG", "SESSION_START_HOUR": "10"}}
    previewed = logged_in.post("/api/v1/system/settings/preview", json=settings).get_json()
    saved = logged_in.put("/api/v1/system/settings", json=settings).get_json()
    assert previewed["diff"] == saved["diff"]


def test_non_hot_reloadable_changes_are_flagged(logged_in, env_file):
    """ADMIN_PORT does not take effect on SIGHUP. Saying so is the difference
    between "it didn't work" and "restart the container"."""
    env_file({"ADMIN_PORT": "8080"})
    body = logged_in.put("/api/v1/system/settings",
                         json={"settings": {"ADMIN_PORT": "9090"}}).get_json()
    assert body["restart_required"], "a non-hot-reloadable change must be named"


def test_a_failed_hot_reload_is_reported_not_raised(logged_in, env_file, monkeypatch):
    """The write SUCCEEDED; only the signal telling the bot to re-read it
    failed, which is routine outside Docker. A 500 here would tell the user
    their settings did not save when they did."""
    monkeypatch.setattr("swingbot.admin.helpers._hot_reload_bot_container",
                        lambda: (False, "no docker socket"))
    env_file({"LOG_LEVEL": "INFO"})
    r = logged_in.put("/api/v1/system/settings", json={"settings": {"LOG_LEVEL": "DEBUG"}})
    assert r.status_code == 200
    assert r.get_json()["hot_reload"] == {"ok": False, "message": "no docker socket"}
    assert env_file.read()["LOG_LEVEL"] == "DEBUG"


# --- export / import ----------------------------------------------------

def test_export_is_a_file_download(logged_in, env_file):
    r = logged_in.get("/api/v1/system/settings/export")
    assert r.status_code == 200
    assert r.mimetype == "text/plain"
    assert "attachment" in r.headers["Content-Disposition"]


def test_export_omits_sensitive_fields_entirely(logged_in, env_file):
    """Omitted, not masked. A masked line re-imports as the literal mask and
    blanks a real secret -- and an export is exactly the file people
    re-import."""
    env_file({"DISCORD_TOKEN": "a-real-token", "LOG_LEVEL": "INFO"})
    text = logged_in.get("/api/v1/system/settings/export").get_data(as_text=True)
    assert "a-real-token" not in text
    assert "DISCORD_TOKEN" not in text and MASK not in text
    assert "LOG_LEVEL=INFO" in text


def test_export_import_round_trip_preserves_values(logged_in, env_file):
    env_file({"LOG_LEVEL": "WARNING", "SESSION_START_HOUR": "11"})
    text = logged_in.get("/api/v1/system/settings/export").get_data(as_text=True)

    logged_in.post("/api/v1/system/settings/import", json={"text": text})

    saved = env_file.read()
    assert saved["LOG_LEVEL"] == "WARNING"
    assert saved["SESSION_START_HOUR"] == "11"


def test_export_edit_import_applies_the_edit(logged_in, env_file):
    """NG15's acceptance walk, minus the container: export, edit, import, and
    the value on disk is the edited one -- which is what the bot re-reads on
    SIGHUP."""
    env_file({"LOG_LEVEL": "WARNING"})
    text = logged_in.get("/api/v1/system/settings/export").get_data(as_text=True)
    edited = text.replace("LOG_LEVEL=WARNING", "LOG_LEVEL=DEBUG")

    body = logged_in.post("/api/v1/system/settings/import", json={"text": edited}).get_json()
    assert body["applied"] >= 1
    assert env_file.read()["LOG_LEVEL"] == "DEBUG"


def test_import_skips_unknown_keys_and_names_them(logged_in, env_file):
    """Lenient where PUT is strict: this is a file someone pasted, quite
    possibly an export from an older build, and refusing the whole thing over
    one retired key would make every upgrade a manual edit."""
    body = logged_in.post("/api/v1/system/settings/import",
                          json={"text": "LOG_LEVEL=DEBUG\nRETIRED_SETTING=1\n"}).get_json()
    assert body["applied"] == 1
    assert body["unknown_keys"] == ["RETIRED_SETTING"]
    assert env_file.read()["LOG_LEVEL"] == "DEBUG"


def test_an_empty_import_is_rejected(logged_in, env_file):
    assert_error(logged_in.post("/api/v1/system/settings/import", json={"text": "   "}),
                 "invalid", 400)

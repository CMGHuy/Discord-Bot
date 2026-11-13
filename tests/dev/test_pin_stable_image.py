"""v221 (v220 spec Section 2): pin-stable-image.yml retags a stable point's two
images `stable-...` with the run's GITHUB_TOKEN (the VM's GHCR login is read
only), and registry-retention.yml never prunes a `stable-*` tag."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
PIN = WORKFLOWS / "pin-stable-image.yml"
RETENTION = WORKFLOWS / "registry-retention.yml"
NAME_RE = "^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$"


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(wf):
    return wf.get("on", wf.get(True))   # PyYAML reads a bare `on:` key as True


def _pin_job():
    return _load(PIN)["jobs"]["pin"]


def _runs():
    return [s["run"] for s in _pin_job()["steps"] if "run" in s]


def test_dispatch_only_with_three_required_inputs():
    wf = _load(PIN)
    on = _on(wf)
    assert set(on) == {"workflow_dispatch"}
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"name", "bot_image", "db_image"}
    assert all(i["required"] is True and i["type"] == "string" for i in inputs.values())
    assert wf["run-name"] == "pin ${{ inputs.name }}"


def test_token_scope_is_packages_write_and_contents_read():
    job = _pin_job()
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    login = next(s for s in job["steps"] if "docker/login-action" in s.get("uses", ""))
    assert login["with"]["registry"] == "ghcr.io"
    assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"


def test_inputs_never_reach_a_shell_script_by_interpolation():
    runs = _runs()
    assert runs
    for run in runs:
        assert "${{" not in run


def test_inputs_are_validated_before_any_retag():
    texts = [s.get("run", "") for s in _pin_job()["steps"]]
    validate = next(i for i, t in enumerate(texts) if NAME_RE in t)
    retag = next(i for i, t in enumerate(texts) if "imagetools create" in t)
    assert validate < retag
    v = texts[validate]
    assert "tr '[:upper:]' '[:lower:]'" in v
    assert '"$BASE:"*' in v and '"$BASE-db:"*' in v and "*@*" in v
    assert "^[A-Za-z0-9_.-]+$" in v


def test_retag_is_registry_side_for_both_images():
    run = next(t for t in _runs() if "imagetools create" in t)
    assert 'for SRC in "$BOT_IMAGE" "$DB_IMAGE"' in run
    assert 'DEST="${SRC%:*}:$NAME"' in run
    assert 'docker buildx imagetools create -t "$DEST" "$SRC"' in run
    assert "docker pull" not in run and "docker push" not in run


def _retention_step():
    return _load(RETENTION)["jobs"]["prune"]["steps"][0]


def test_retention_never_prunes_latest_or_stable_tags():
    tags = [t.strip() for t in _retention_step()["with"]["image-tags"].split(",")]
    assert tags == ["!latest", "!stable-*"]


def test_retention_exclusion_quotes_the_action_readme():
    text = RETENTION.read_text(encoding="utf-8")
    assert "snok/container-retention-policy v3.1.0 README:" in text

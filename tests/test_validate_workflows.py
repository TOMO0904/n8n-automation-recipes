import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from validate_workflows import validate_workflow  # noqa: E402

FILES = sorted((ROOT / "workflows").glob("*.json"))


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_three_workflows_exist():
    assert len(FILES) == 3


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_shipped_workflows_are_valid(path):
    assert validate_workflow(load(path)) == []


def test_detects_broken_connection():
    wf = copy.deepcopy(load(FILES[0]))
    wf["connections"]["Webhook"]["main"][0][0]["node"] = "Nope"
    assert any("target not found" in e for e in validate_workflow(wf))


def test_detects_missing_nodes_key():
    assert any("nodes" in e for e in validate_workflow({"name": "x", "connections": {}}))


def test_detects_real_credential_id():
    wf = copy.deepcopy(load(FILES[0]))
    for n in wf["nodes"]:
        if "credentials" in n:
            k = next(iter(n["credentials"]))
            n["credentials"][k]["id"] = "42"
    assert any("placeholder" in e for e in validate_workflow(wf))

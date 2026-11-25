#!/usr/bin/env python3
"""Validate n8n workflow JSON files.

Checks (no n8n instance required):
  * valid JSON with top-level "name", "nodes" and "connections"
  * every node has id, name, type, typeVersion, position, parameters
  * node names and ids are unique
  * every connection source/target refers to an existing node
  * at least one trigger node exists
  * credentials are placeholders only (no real-looking ids or secret fields)

Usage: python scripts/validate_workflows.py [path ...]   (default: workflows/)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_NODE_KEYS = ("id", "name", "type", "typeVersion", "position", "parameters")
TRIGGER_HINTS = ("trigger", "webhook")
SECRET_KEY_RE = re.compile(r"(password|secret|token|apikey|api_key|private_key)", re.I)
SECRET_VALUE_RE = re.compile(r"(xox[abp]-|ghp_|AKIA[0-9A-Z]{16}|-----BEGIN)")


def validate_workflow(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    for key in ("name", "nodes", "connections"):
        if key not in data:
            errors.append(f"missing top-level key: {key}")
    nodes = data.get("nodes")
    connections = data.get("connections")
    if not isinstance(nodes, list) or not nodes:
        errors.append("'nodes' must be a non-empty list")
        return errors
    if not isinstance(connections, dict):
        errors.append("'connections' must be an object")
        connections = {}

    names: set[str] = set()
    ids: set[str] = set()
    has_trigger = False
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] must be an object")
            continue
        for key in REQUIRED_NODE_KEYS:
            if key not in node:
                errors.append(f"nodes[{i}] ({node.get('name', '?')}): missing '{key}'")
        name, nid, ntype = node.get("name"), node.get("id"), str(node.get("type", ""))
        if name in names:
            errors.append(f"duplicate node name: {name}")
        if nid in ids:
            errors.append(f"duplicate node id: {nid}")
        names.add(name)
        ids.add(nid)
        if not ntype.startswith("n8n-nodes-base."):
            errors.append(f"{name}: unexpected node type '{ntype}'")
        if any(h in ntype.lower() for h in TRIGGER_HINTS):
            has_trigger = True
        pos = node.get("position")
        if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(p, (int, float)) for p in pos)):
            errors.append(f"{name}: position must be [x, y]")
        for cred_type, cred in (node.get("credentials") or {}).items():
            cid = str(cred.get("id", "")) if isinstance(cred, dict) else ""
            if not cid.startswith("REPLACE_"):
                errors.append(f"{name}: credential '{cred_type}' must use a REPLACE_ placeholder id")
        errors.extend(f"{name}: {m}" for m in _scan_secrets(node.get("parameters", {})))
    if not has_trigger:
        errors.append("workflow has no trigger node")

    for src, outputs in connections.items():
        if src not in names:
            errors.append(f"connection source not found: {src}")
        for branches in (outputs or {}).values():
            for branch in branches or []:
                for link in branch or []:
                    if link.get("node") not in names:
                        errors.append(f"connection {src} -> {link.get('node')}: target not found")
    return errors


def _scan_secrets(obj: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if SECRET_KEY_RE.search(k) and isinstance(v, str) and v and not v.startswith(("=", "REPLACE_")):
                found.append(f"possible secret in parameter '{path}{k}'")
            found.extend(_scan_secrets(v, f"{path}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_scan_secrets(v, f"{path}[{i}]."))
    elif isinstance(obj, str) and SECRET_VALUE_RE.search(obj):
        found.append(f"secret-looking value at '{path}'")
    return found


def validate_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse JSON: {exc}"]
    return validate_workflow(data)


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or [Path("workflows")]
    files: list[Path] = []
    for t in targets:
        files.extend(sorted(t.glob("*.json")) if t.is_dir() else [t])
    if not files:
        print("no workflow files found")
        return 1
    failed = 0
    for f in files:
        errs = validate_file(f)
        if errs:
            failed += 1
            print(f"FAIL {f}")
            for e in errs:
                print(f"   - {e}")
        else:
            print(f"OK   {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

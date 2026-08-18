#!/usr/bin/env python3
"""Export kernel contracts (pydantic source of truth) to schemas/v1 JSON Schema.

Single source of truth flow:

    contracts/*.py (pydantic)  -->  schemas/v1/*.schema.json  -->  TS zod (despacho)

* Nested models are rewritten as sibling ``$id`` references
  (``seasi/<slug>/v1``) and ``$defs`` are dropped, matching the handwritten
  schema style already present in ``schemas/v1``.
* ``MANIFEST.json`` records the sha256 of every managed file; the despacho
  generator verifies the same digests (drift gate on both sides).
* ``--check`` mode recomputes everything and exits non-zero on drift
  (CI gate: modifying a contract without exporting fails the build).

Only the contracts listed in ``MANAGED`` are managed by this tool; the
pre-existing v0.1 schemas remain authoritative as-is.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from seasi_core.contracts.artifacts import Artifact
from seasi_core.contracts.hitl import HitlPause
from seasi_core.contracts.session import AgentSession
from seasi_core.contracts.shell_api import ShellApiManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = REPO_ROOT / "schemas" / "v1"
MANIFEST_PATH = SCHEMAS_DIR / "MANIFEST.json"

MODEL_SLUGS: dict[str, str] = {
    "TenantScope": "tenant-scope",
    "AgentSession": "session",
    "Artifact": "artifact",
    "HitlPause": "hitl-pause",
    "ShellApiManifest": "shell-api",
}

MANAGED: list[tuple[type[BaseModel], str]] = [
    (AgentSession, "session.schema.json"),
    (Artifact, "artifact.schema.json"),
    (HitlPause, "hitl-pause.schema.json"),
    (ShellApiManifest, "shell-api.schema.json"),
]

MANIFEST_SCHEMA_VERSION = "seasi.schemas/v1"


def _rewrite_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively rewrite ``#/$defs/<X>`` refs.

    * Models with a slug become sibling ``$id`` refs (``seasi/<slug>/v1``).
    * Inline definitions (enums, literals) are embedded at the reference site.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                model_name = value.split("/")[-1]
                slug = MODEL_SLUGS.get(model_name)
                if slug is not None:
                    out[key] = f"seasi/{slug}/v1"
                elif model_name in defs:
                    out.update(_rewrite_refs(copy.deepcopy(defs[model_name]), defs))
                else:
                    msg = f"unknown $def {model_name!r}; add it to MODEL_SLUGS or its def"
                    raise SystemExit(msg)
            else:
                out[key] = _rewrite_refs(value, defs)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(item, defs) for item in node]
    return node


def build_document(model: type[BaseModel]) -> str:
    slug = MODEL_SLUGS[model.__name__]
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    schema = _rewrite_refs(schema, defs)
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": f"seasi/{slug}/v1",
        **schema,
    }
    return json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_all() -> dict[str, str]:
    return {filename: build_document(model) for model, filename in MANAGED}


def build_manifest_files(files: dict[str, str]) -> dict[str, str]:
    return {name: sha256_text(content) for name, content in sorted(files.items())}


def write_mode() -> int:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    files = build_all()
    for name, content in files.items():
        (SCHEMAS_DIR / name).write_text(content, encoding="utf-8")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "files": build_manifest_files(files),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"exported {len(files)} schemas + MANIFEST.json -> {SCHEMAS_DIR}")
    return 0


def check_mode() -> int:
    files = build_all()
    drift: list[str] = []
    for name, expected in files.items():
        path = SCHEMAS_DIR / name
        if not path.exists():
            drift.append(f"{name}: missing (run tools/export_schemas.py)")
            continue
        if sha256_text(path.read_text(encoding="utf-8")) != sha256_text(expected):
            drift.append(f"{name}: drifted (run tools/export_schemas.py)")
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if manifest.get("files") != build_manifest_files(files):
            drift.append("MANIFEST.json: drifted")
    else:
        drift.append("MANIFEST.json: missing")
    if drift:
        for line in drift:
            print(f"DRIFT: {line}", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} schemas in sync with contracts")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    args = parser.parse_args(argv)
    return check_mode() if args.check else write_mode()


if __name__ == "__main__":
    raise SystemExit(main())

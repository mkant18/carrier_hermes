#!/usr/bin/env python3
"""Validate specialist JSON against a schema. stdlib only (Draft-07 subset)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _type_ok(val, typ) -> bool:
    if isinstance(typ, list):
        return any(_type_ok(val, t) for t in typ)
    return {
        "object": isinstance(val, dict),
        "array": isinstance(val, list),
        "string": isinstance(val, str),
        "number": isinstance(val, (int, float)) and not isinstance(val, bool),
        "integer": isinstance(val, int) and not isinstance(val, bool),
        "boolean": isinstance(val, bool),
        "null": val is None,
    }.get(typ, True)


def validate(instance, schema, path="$") -> list[str]:
    errs: list[str] = []
    if not isinstance(schema, dict):
        return errs
    typ = schema.get("type")
    if typ and not _type_ok(instance, typ):
        errs.append(f"{path}: expected {typ}")
        return errs
    enum = schema.get("enum")
    if enum is not None and instance not in enum:
        errs.append(f"{path}: {instance!r} not in {enum}")
    if schema.get("minLength") and isinstance(instance, str):
        if len(instance) < int(schema["minLength"]):
            errs.append(f"{path}: too short")
    if isinstance(instance, dict) and schema.get("type") in (None, "object"):
        for key in schema.get("required", []):
            if key not in instance:
                errs.append(f"{path}: missing {key}")
        props = schema.get("properties") or {}
        for k, v in instance.items():
            if k in props:
                errs.extend(validate(v, props[k], f"{path}.{k}"))
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errs.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errs


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_specialist_json.py schema.json data.json", file=sys.stderr)
        return 2
    schema = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    errs = validate(data, schema)
    if errs:
        print("INVALID")
        print("\n".join(errs))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

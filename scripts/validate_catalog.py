#!/usr/bin/env python3
"""Validate the aelix marketplace catalog.

Three checks, in order (any failure exits non-zero):

1. Caps  -- catalog.json is under MAX_CATALOG_BYTES and carries at most
   MAX_CATALOG_ENTRIES entries. The caps are imported from the runtime module
   when aelix-coding-agent is installed, else fall back to the documented
   literals.

2. Schema -- catalog.json validates against catalog.schema.json (JSON Schema
   draft 2020-12). This is a contributor aid, not the runtime authority.

3. AUTHORITATIVE -- run the real parser,
   aelix_coding_agent.cli.extension_catalog.parse_catalog, over the exact bytes
   and assert the number of parsed entries EQUALS the number of items in the
   file's "extensions" array. parse_catalog is LENIENT: it silently drops an
   entry that is missing name/source, has control characters in its source, or
   is not a JSON object. This check turns that silent drop into a CI FAILURE, so
   a malformed entry cannot land unnoticed. This is what makes the published
   catalog authoritative-validated rather than merely schema-valid.

Usage:
    python scripts/validate_catalog.py [path/to/catalog.json]

Requires: jsonschema, and (for check 3) a pip-installed aelix-coding-agent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = REPO_ROOT / "catalog.json"
SCHEMA_PATH = REPO_ROOT / "catalog.schema.json"

# Documented fallbacks, used only if the runtime module cannot be imported for
# the caps (check 1). Check 3 REQUIRES the module and will not fall back.
FALLBACK_MAX_CATALOG_BYTES = 2 * 1024 * 1024
FALLBACK_MAX_CATALOG_ENTRIES = 5000


def _fail(message: str) -> "NoReturn":
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str]) -> int:
    catalog_path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_CATALOG

    # --- Load the raw bytes (byte-exact for the authoritative parse) ----------
    try:
        raw_bytes = catalog_path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read catalog {catalog_path}: {exc}")

    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        _fail(f"{catalog_path} is not valid UTF-8 JSON: {exc}")

    if not isinstance(document, dict):
        _fail(f"{catalog_path} root is not a JSON object")

    file_entries = document.get("extensions")
    if not isinstance(file_entries, list):
        _fail(f"{catalog_path} has no 'extensions' array")
    file_entry_count = len(file_entries)

    # --- Import the runtime module (authoritative caps + parser) --------------
    _import_error: Exception | None = None
    try:
        from aelix_coding_agent.cli.extension_catalog import (  # type: ignore[import-not-found]
            MAX_CATALOG_BYTES,
            MAX_CATALOG_ENTRIES,
            CatalogError,
            parse_catalog,
        )
    except Exception as exc:  # noqa: BLE001 -- any import failure
        parse_catalog = None  # type: ignore[assignment]
        CatalogError = Exception  # type: ignore[assignment,misc]
        MAX_CATALOG_BYTES = FALLBACK_MAX_CATALOG_BYTES
        MAX_CATALOG_ENTRIES = FALLBACK_MAX_CATALOG_ENTRIES
        _import_error = exc

    # --- Check 1: caps --------------------------------------------------------
    size = len(raw_bytes)
    if size > MAX_CATALOG_BYTES:
        _fail(
            f"catalog is {size} bytes, over the {MAX_CATALOG_BYTES} byte cap "
            f"({MAX_CATALOG_BYTES // (1024 * 1024)} MiB)"
        )
    if file_entry_count > MAX_CATALOG_ENTRIES:
        _fail(
            f"catalog has {file_entry_count} entries, over the "
            f"{MAX_CATALOG_ENTRIES} entry cap"
        )
    print(
        f"OK  caps: {size} bytes (<= {MAX_CATALOG_BYTES}), "
        f"{file_entry_count} entries (<= {MAX_CATALOG_ENTRIES})"
    )

    # --- Check 2: JSON Schema -------------------------------------------------
    try:
        import jsonschema
    except ImportError:
        _fail("jsonschema is not installed (pip install jsonschema)")

    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(f"cannot load schema {SCHEMA_PATH}: {exc}")

    try:
        jsonschema.validate(instance=document, schema=schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        _fail(f"schema validation failed at {location}: {exc.message}")
    except jsonschema.SchemaError as exc:
        _fail(f"catalog.schema.json is itself invalid: {exc.message}")
    print("OK  schema: catalog.json conforms to catalog.schema.json")

    # --- Check 3: AUTHORITATIVE parse (parity with the runtime parser) --------
    if parse_catalog is None:
        _fail(
            "aelix-coding-agent is not importable, so the AUTHORITATIVE parse "
            "check cannot run. Install it, e.g.:\n"
            "  pip install "
            '"git+https://github.com/handochan/aelix-ai.git'
            '#subdirectory=packages/aelix-coding-agent"\n'
            f"(import error: {_import_error})"
        )

    try:
        parsed = parse_catalog(raw_bytes, location=str(catalog_path))
    except CatalogError as exc:
        _fail(f"parse_catalog rejected the catalog: {exc}")

    parsed_count = len(parsed.entries)
    if parsed_count != file_entry_count:
        dropped = file_entry_count - parsed_count
        _fail(
            f"parse_catalog kept {parsed_count} of {file_entry_count} entries "
            f"({dropped} silently dropped). The runtime parser skips an entry "
            "that is missing name/source, has control characters in its source, "
            "or is not a JSON object. Fix or remove the offending entry so the "
            "published catalog matches what aelix will actually install."
        )
    print(
        f"OK  authoritative: parse_catalog kept all {parsed_count} entries "
        "(no silent drops)"
    )

    print("PASS: catalog is valid and authoritative-validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

<!--
Thanks for contributing to the aelix extension catalog.
This template is for adding or updating a catalog entry. For anything else,
delete it and describe your change.
-->

## What extension is this?

- **Name:**
- **Source (`source` spec):**
- **Homepage:**

## Checklist

### Entry format
- [ ] The entry has a non-empty `name` and a non-empty `source`.
- [ ] `source` is exactly one of the three supported forms:
  - a local path (`./ext` or `/abs/path`), **or**
  - a git URL, ideally pinned to a 40-hex commit SHA (`git+https://host/repo.git@<sha>`), **or**
  - a PyPI spec, ideally version-pinned (`pkg-name==1.2.3`).
- [ ] Any `sha256` I included is lowercase 64-hex, and I understand it is **advisory / display-only** (never a trust signal).
- [ ] `catalog.json` is still valid JSON and `python scripts/validate_catalog.py` passes locally.

### Curation / safety
- [ ] The `homepage` URL is reachable and points at the real project.
- [ ] The `name` is **not a typosquat** of an existing entry or a well-known package.
- [ ] The `source` points at the genuine upstream (correct owner/repo or PyPI project), not a look-alike.
- [ ] I have **actually installed** this extension from the listed `source` (`aelix extension install <source>`) and it works.

<!--
Reminder: listing here is NOT an endorsement of safety. Users still get the
install-time consent prompt (which shows the RESOLVED source spec), the
verify_and_pin integrity gate, and the optional Ed25519 signature check.
-->

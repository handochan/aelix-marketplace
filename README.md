<p align="center">
  <img src="https://raw.githubusercontent.com/handochan/aelix-ai/main/docs/assets/brand/lockup-stacked.png" width="300" alt="Aelix — the A×X mark above the Aelix wordmark">
</p>

# aelix-marketplace

The **official advisory catalog** for [aelix](https://github.com/handochan/aelix-ai)
extensions.

This repository publishes a single document, [`catalog.json`](catalog.json),
that lists extensions aelix users can discover and install. It is served as a
static file over GitHub Pages and consumed by aelix's `extension discover`
command.

It currently ships **empty** (`"extensions": []`) — the honest starting state.
No extensions have been curated yet. See [CONTRIBUTING.md](CONTRIBUTING.md) to
add one.

> **This catalog is advisory.** It chooses *what* a user might install, not
> whether it is safe. Being listed here is **not** an endorsement of safety.
> The real trust boundary is at install time — see
> [The trust model](#the-trust-model).

## What is in this repo

| File | Purpose |
| ---- | ------- |
| [`catalog.json`](catalog.json) | The catalog document itself. |
| [`catalog.schema.json`](catalog.schema.json) | JSON Schema (draft 2020-12) for the document — a contributor aid. |
| [`scripts/validate_catalog.py`](scripts/validate_catalog.py) | Validator run in CI; parses with the real aelix parser. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to add an entry; field reference; security model. |

The catalog format is:

```json
{
  "schemaVersion": 1,
  "name": "aelix official catalog",
  "updated": "2026-01-01T00:00:00Z",
  "extensions": []
}
```

Each entry in `extensions` requires a `name` and a `source`; the `source` is a
`path`, a `git+url[@40-hex-sha]`, or a `pypi-name[==version]` spec. See
[CONTRIBUTING.md](CONTRIBUTING.md#entry-fields) for the full field reference.

> The **runtime authority** for the format is aelix's
> `aelix_coding_agent.cli.extension_catalog.parse_catalog`, not the JSON Schema.
> The schema mirrors it as a convenience; where they differ, the parser wins.

## How aelix consumes it

aelix reads a catalog as an **advisory source** (`kind="catalog"`), separate
from an install *source*. There are two ways to point aelix at this catalog.

**1. Register it explicitly.** Any user can add a catalog by URL, file, or git
source:

```bash
aelix extension source add --catalog https://handochan.github.io/aelix-marketplace/catalog.json
aelix extension discover                 # browse
aelix extension discover install <name>  # resolve + install (with consent)
```

**2. Built-in default.** aelix has a dormant default-catalog slot,
`DEFAULT_CATALOG_URL`, overridable per-run by the `AELIX_DEFAULT_CATALOG`
environment variable. In the beta it is **empty (dormant)** — no first-party
catalog ships enabled. When the owner turns it on, it points here:

- Primary (Pages / CDN): `https://handochan.github.io/aelix-marketplace/catalog.json`
- Fallback (raw): `https://raw.githubusercontent.com/handochan/aelix-marketplace/main/catalog.json`

An enterprise can repoint the default at its own internal catalog with
`AELIX_DEFAULT_CATALOG=...`, or disable it for a run with
`aelix extension discover --no-default-catalog`.

## The trust model

The catalog is the **advisory** link in a chain. Listing is not verification.
The trust boundary is at **install time**:

- **Consent prompt.** `discover install` / `install` shows the **resolved**
  source spec and asks `y/N` before fetching anything — so a user always sees
  exactly what will be installed (a typosquatted name cannot disguise a
  look-alike source).
- **Integrity pin.** aelix records an integrity pin on first install and
  enforces it thereafter (trust-on-first-install).
- **Optional Ed25519 signature.** Extensions — and this catalog document itself
  — can be signed; users can require a valid signature from a trusted key.

An entry's optional `sha256` is **display-only**: it is never written to the pin
store and never means "verified".

This design follows aelix's advisory-catalog decision (ADR-0188) and its
transport-security hardening (ADR-0192): the catalog is fetched over TLS-only
`https` (or `file://` / git for air-gapped/intranet use), and a catalog can be
signed so its authenticity is independently checkable.

## Signing (maintainer)

The published `catalog.json` is **signed out-of-band** by the owner with an
Ed25519 key. The detached signature is a `catalog.json.aelixsig` sidecar served
at the same URL with the `.aelixsig` suffix, so aelix can fetch it over the same
transport and verify the document before trusting it.

```bash
# One-time: generate a signing key; prints the keyId.
aelix extension keygen --label "aelix official catalog"

# After every catalog change: re-sign the document (writes catalog.json.aelixsig).
aelix extension sign catalog.json --key <keyId> --kind catalog
```

Contributors never sign; the owner re-signs after merging a change. See
[CONTRIBUTING.md](CONTRIBUTING.md#maintainer-signing-the-catalog) for details.

## Web viewer

Any web page in this repo that displays the catalog fetches `./catalog.json`
**relatively**, so it works identically on the Pages URL and on a local clone
without hardcoding a host.

## Development

Validate the catalog locally exactly as CI does:

```bash
python -m pip install jsonschema
python -m pip install "git+https://github.com/handochan/aelix-ai.git#subdirectory=packages/aelix-coding-agent"
python scripts/validate_catalog.py
```

CI ([`.github/workflows/validate-catalog.yml`](.github/workflows/validate-catalog.yml))
runs the same validator on every push and pull request. Because it parses with
the **real** `parse_catalog` and asserts no entry is silently dropped, a merged
`catalog.json` is authoritative-validated, not merely schema-valid.

## License

[Apache-2.0](LICENSE) © handochan.

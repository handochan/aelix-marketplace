<p align="center">
  <img src="https://raw.githubusercontent.com/handochan/aelix-ai/main/docs/assets/brand/lockup-stacked.png" width="300" alt="Aelix — the A×X mark above the Aelix wordmark">
</p>

# Aelix Marketplace

The **official advisory catalog** for [Aelix](https://handochan.github.io/aelix-ai/)
extensions. Browse it at
**[handochan.github.io/aelix-marketplace](https://handochan.github.io/aelix-marketplace/)**;
the Aelix runtime itself lives at
[github.com/handochan/aelix-ai](https://github.com/handochan/aelix-ai).

This repository publishes a single document, [`catalog.json`](catalog.json),
that lists extensions Aelix users can discover and install. It is served as a
static file over GitHub Pages and consumed by Aelix's `extension discover`
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
| [`scripts/validate_catalog.py`](scripts/validate_catalog.py) | Validator run in CI; parses with the real Aelix parser. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to add an entry; field reference; security model. |

The catalog format is:

```json
{
  "schemaVersion": 1,
  "name": "Aelix official catalog",
  "updated": "2026-07-31T00:00:00Z",
  "extensions": []
}
```

Each entry in `extensions` requires a `name` and a `source`. In **this** catalog
the `source` is a `git+url[@40-hex-sha]` or a `pypi-name[==version]` spec; the
`path` form Aelix also accepts is [not listable
here](CONTRIBUTING.md#source-forms). A listed pack must additionally bind an
`aelix-plugin.toml` — CI installs every added or changed entry and rejects it
unless `aelix extension verify` reports `BOUND`. See
[CONTRIBUTING.md](CONTRIBUTING.md#entry-fields) for the full field reference.

> The **runtime authority** for the format is Aelix's
> `aelix_coding_agent.cli.extension_catalog.parse_catalog`, not the JSON Schema.
> The schema mirrors it as a convenience; where they differ, the parser wins.

## How Aelix consumes it

Aelix reads a catalog as an **advisory source** (`kind="catalog"`), separate
from an install *source*. There are two ways to point Aelix at this catalog.

**1. Register it explicitly.** Any user can add a catalog by URL, file, or git
source:

```bash
aelix extension source add --catalog https://handochan.github.io/aelix-marketplace/catalog.json
aelix extension discover --refresh       # fetch it into the local cache
aelix extension discover                 # browse the cached snapshot
aelix extension discover install <name>  # resolve + install (with consent)
```

**2. Built-in default.** Aelix ships with `DEFAULT_CATALOG_URL` **already pointing
at this catalog** — it is not an empty placeholder:

```
https://handochan.github.io/aelix-marketplace/catalog.json
```

Nothing is fetched implicitly, though. `aelix extension discover` reads the local
cache and never touches the network; the fetch happens only on an explicit
refresh:

```bash
aelix extension discover --refresh   # fetch every registered catalog + this default
aelix extension discover             # browse the cached snapshot (no network)
```

So the default is **opt-out at refresh time**: a user who refreshes without
configuring anything gets this catalog. Being listed here still means nothing
about safety (see [The trust model](#the-trust-model)); the default only decides
which document Aelix *reads*, never what it installs. An empty catalog is a
successful fetch, not a broken one.

Three independent ways to switch it off:

- `AELIX_DEFAULT_CATALOG=<url>` repoints the default — an enterprise aims it at
  an internal catalog. An **empty** value disables it for that run.
- `aelix extension discover --no-default-catalog` skips it for a single command.
- `aelix extension source remove <default>` writes a persistent tombstone.

`aelix extension discover --offline` skips it too, along with every other network
source. (Flags belong after the `extension` verb — `aelix --offline extension …`
is not dispatched as an extension command.)

The raw address
`https://raw.githubusercontent.com/handochan/aelix-marketplace/main/catalog.json`
serves the same document and can be registered by hand, but Aelix has no
automatic fallback to it — the default is the single Pages URL above.

## The trust model

The catalog is the **advisory** link in a chain. Listing is not verification.
The trust boundary is at **install time**:

- **Consent prompt.** `discover install` / `install` shows the **resolved**
  source spec and asks `y/N` before fetching anything — so a user always sees
  exactly what will be installed (a typosquatted name cannot disguise a
  look-alike source).
- **Integrity pin.** Aelix records an integrity pin on first install and
  enforces it thereafter (trust-on-first-install).
- **Optional Ed25519 signature.** Extensions — and this catalog document itself
  — can be signed; users can require a valid signature from a trusted key.

An entry's optional `sha256` is **display-only**: it is never written to the pin
store and never means "verified".

This design follows Aelix's advisory-catalog decision (ADR-0188) and its
transport-security hardening (ADR-0192): the catalog is fetched over TLS-only
`https` (or `file://` / git for air-gapped/intranet use), and a catalog can be
signed so its authenticity is independently checkable.

## Signing (maintainer)

> **Not yet in effect.** This catalog is **currently unsigned** — no
> `catalog.json.aelixsig` is published, and
> `https://handochan.github.io/aelix-marketplace/catalog.json.aelixsig` returns
> 404. Aelix admits an unsigned default catalog best-effort over TLS
> (`FIRST_PARTY_KEYS` ships empty), so nothing is broken; but do not read the
> procedure below as a guarantee that is already running. It is what the owner
> will do, not what has been done.

The intended scheme: `catalog.json` is **signed out-of-band** by the owner with
an Ed25519 key. The detached signature is a `catalog.json.aelixsig` sidecar
served at the same URL with the `.aelixsig` suffix, so Aelix can fetch it over
the same transport and verify the document before trusting it. Publishing the
key in `FIRST_PARTY_KEYS` upgrades the default from best-effort to fail-closed.

```bash
# One-time: generate a signing key; prints the keyId.
aelix extension keygen --label "Aelix official catalog"

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

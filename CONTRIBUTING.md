# Contributing to the Aelix extension catalog

This repository holds the **official advisory catalog** for [Aelix](https://handochan.github.io/aelix-ai/)
extensions: a single `catalog.json` document that lists extensions users can
discover and install. This guide explains how to add an entry, what each field
means, and the security model you are contributing into.

> **The catalog is advisory.** It only chooses *what* a user might install. It
> is **not** a safety verdict. Being listed here is **not an endorsement** that
> an extension is safe. See [Security model](#security-model) below.

## How to add an extension

1. **Fork** this repository.
2. **Add one entry** to the `extensions` array in [`catalog.json`](catalog.json).
3. Run the validator locally (see [Validate before you PR](#validate-before-you-pr)).
4. **Open a pull request.** The [PR template](.github/pull_request_template.md)
   is a checklist; fill it in. The owner (`@handochan`, see
   [CODEOWNERS](CODEOWNERS)) reviews every catalog change.

Keep the diff to your one entry. Do not reformat the whole file.

## Entry fields

Each entry is a JSON object. Only `name` and `source` are required; everything
else is optional. The authoritative parser
(`aelix_coding_agent.cli.extension_catalog.parse_catalog`) ignores unknown keys.

| Field         | Required | Meaning |
| ------------- | :------: | ------- |
| `name`        | yes      | Display name and the key users type to install. Non-empty, no control characters. |
| `source`      | yes      | The **only** field the installer consumes — see [Source forms](#source-forms). |
| `description` | no       | Short one-line description shown next to the name. |
| `version`     | no       | Display version (informational only). |
| `homepage`    | no       | Project/repository URL (https recommended). |
| `sha256`      | no       | **Advisory, display-only** lowercase 64-hex digest. **Not a trust signal** — see below. |

### Source forms

`source` is handed **unchanged** to `aelix extension install`, which classifies
it into exactly one of three forms:

1. **Local path** — resolves to a directory/file on the user's machine.
   ```json
   { "name": "my-local-ext", "source": "./extensions/my-local-ext" }
   ```
   (Absolute paths like `/opt/aelix/my-ext` also work. Local paths are mostly
   for private/intranet catalogs, not the public one.)

2. **Git URL** — a `git+…` VCS spec, ideally **pinned to a 40-hex commit SHA**
   so installs are reproducible:
   ```json
   {
     "name": "aelix-ext-example",
     "source": "git+https://github.com/acme/aelix-ext-example.git@0123456789abcdef0123456789abcdef01234567",
     "homepage": "https://github.com/acme/aelix-ext-example"
   }
   ```
   An unpinned `git+https://github.com/acme/aelix-ext-example.git` is accepted
   but is a *mutable* reference; a pinned SHA is strongly preferred.

3. **PyPI package** — a package spec, ideally **version-pinned**:
   ```json
   {
     "name": "aelix-ext-foo",
     "source": "aelix-ext-foo==1.2.3",
     "homepage": "https://pypi.org/project/aelix-ext-foo/"
   }
   ```
   A bare `aelix-ext-foo` (unpinned) is accepted but resolves to whatever is
   latest at install time.

> `sha256` is **display-only**. It is *never* written to Aelix's integrity pin
> store and *never* means "verified". Do not treat it as a checksum gate — it is
> shown to users purely as informational metadata. Real integrity comes from the
> install-time gate described below.

## Security model

The catalog is one link in a chain, and it is the **advisory** link. The trust
boundary is at **install time**, not at listing time:

- **Consent prompt.** `aelix extension install <source>` shows the **resolved**
  source spec and asks the user `y/N` before doing anything. A user always sees
  exactly what will be fetched. This is why `source` must point at the genuine
  upstream: a typosquatted `name` cannot hide a look-alike `source` — the user
  sees the real spec.
- **Integrity pin (`verify_and_pin`).** On first install Aelix records an
  integrity pin (trust-on-first-install) and enforces it on later installs, so a
  source that later serves different bytes is flagged.
- **Optional Ed25519 signature.** Extensions (and this catalog itself) can be
  signed; users can require a valid signature from a trusted key.

Because of this, **listing an extension here is not a promise it is safe.** Our
curation reduces obvious risk (typosquats, dead/hijacked sources, wrong
upstreams) but does not audit extension code. Users remain in control at install
time.

### Curation policy

- Every entry is **reviewed** by the owner before merge.
- We reject entries that appear to be **typosquats**, point at the **wrong or a
  look-alike upstream**, have an **unreachable homepage**, or that the submitter
  has not actually installed.
- **Review is not a safety endorsement.** We do not audit or vouch for the
  behavior of listed extension code.
- The owner may remove an entry at any time (e.g. a source is hijacked, an
  upstream disappears, or a report of malicious behavior).

## Validate before you PR

CI runs [`scripts/validate_catalog.py`](scripts/validate_catalog.py) on every
push and pull request. Run it locally first:

```bash
python -m pip install jsonschema
python -m pip install "git+https://github.com/handochan/aelix-ai.git#subdirectory=packages/aelix-coding-agent"
python scripts/validate_catalog.py
```

The validator does three things:

1. **Caps** — asserts `catalog.json` is under the 2 MiB / 5000-entry limits.
2. **Schema** — validates against [`catalog.schema.json`](catalog.schema.json)
   (a contributor aid; draft 2020-12).
3. **Authoritative** — runs the **real** `parse_catalog` over the exact bytes
   and asserts it keeps **every** entry. The runtime parser is *lenient*: it
   silently drops an entry that is missing `name`/`source`, has control
   characters in its `source`, or is not a JSON object. This check turns that
   silent drop into a **failure**, so a broken entry cannot land unnoticed.

## Maintainer: signing the catalog

The published `catalog.json` is **signed out-of-band** by the owner with an
Ed25519 key, producing a detached `catalog.json.aelixsig` sidecar served beside
it. This lets a user (or an enterprise) require a valid signature before trusting
the catalog document. Contributors do **not** sign; the owner re-signs after
merging.

```bash
# One-time: generate a signing key. Prints the keyId to sign with.
aelix extension keygen --label "Aelix official catalog"

# After merging a catalog change, sign the document with that key. This writes
# catalog.json.aelixsig next to catalog.json.
aelix extension sign catalog.json --key <keyId> --kind catalog
```

The `.aelixsig` sidecar is committed/published beside `catalog.json` (at the same
URL with the `.aelixsig` suffix) so Aelix can fetch it over the same transport.

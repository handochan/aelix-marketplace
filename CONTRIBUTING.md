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
it into one of three forms. **This catalog admits two of them.**

1. **Local path — NOT accepted here.** CI rejects an entry whose `source` is a
   path, and the reason is worth stating because it is not merely "it would not
   be useful". Aelix decides a source is a path by asking whether it **exists on
   the machine reading it**. On your machine `./extensions/my-ext` is that
   directory; on everyone else's — where it does not exist — the very same entry
   silently stops meaning a directory and starts meaning **a package name you
   never chose**, which is then fetched from PyPI ([aelix-ai
   #131](https://github.com/handochan/aelix-ai/issues/131)). It is also
   unverifiable: the submission gate cannot install a path that is not on the
   runner. Publish to PyPI or point at a git URL instead.

   This is a rule of *this document*, not of aelix. `aelix extension install
   ./my-ext` still works, a private or intranet catalog may still list paths,
   and none of aelix's four extension-discovery tiers involve a catalog at all.

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
- Every added or changed entry must also pass the **automated submission gate**:
  installed in a throwaway environment, `aelix extension verify` must report
  `BOUND`. This is machine-checked and not waivable by review — see
  [Validate before you PR](#validate-before-you-pr).
- We reject entries that appear to be **typosquats**, point at the **wrong or a
  look-alike upstream**, have an **unreachable homepage**, or that the submitter
  has not actually installed.
- **Review is not a safety endorsement.** We do not audit or vouch for the
  behavior of listed extension code.
- The owner may remove an entry at any time (e.g. a source is hijacked, an
  upstream disappears, or a report of malicious behavior).

## Your extension must bind a manifest

A listed pack must ship an `aelix-plugin.toml` that **binds** — that the host can
find and parse from your installed distribution. This is a hard requirement for
the official catalog ([ADR-0207](https://github.com/handochan/aelix-ai/blob/main/docs/decisions/0207-a-catalog-listed-pack-must-bind-a-manifest.md));
it is *optional* for a pack a user installs directly.

"Binds" does **not** mean "declares at least one contribution" — a manifest that
parses and declares nothing is fine. It means the file is actually **inside your
wheel**. The trap this exists to catch is quiet and common:

> A **setuptools build with default configuration packages `*.py` and DROPS
> `aelix-plugin.toml`.** Your pack then installs, `setup()` runs, the product
> reports success — and every theme, widget and command you declared is silently
> ignored, because the manifest is not there to read. Hatchling ships it by
> default; setuptools needs `include_package_data` + a `MANIFEST.in`, or an
> explicit `[tool.setuptools.package-data]`.

A copyable hatchling scaffold that gets this right ships inside aelix at
`aelix_coding_agent/examples/starter/`.

Check your own pack before you open a PR — this is the same verdict CI computes:

```bash
python -m venv /tmp/check && /tmp/check/bin/pip install "<your source spec>"
/tmp/check/bin/pip install "git+https://github.com/handochan/aelix-ai.git#subdirectory=packages/aelix-coding-agent"
/tmp/check/bin/aelix extension verify     # exit 0 = BOUND
```

`verify` **imports none of your code** — it reads installed metadata only.

## Validate before you PR

Two checks run on every pull request that touches `catalog.json`.

**1. Document validity** — [`scripts/validate_catalog.py`](scripts/validate_catalog.py).
Run it locally first:

```bash
python -m pip install jsonschema
python -m pip install "git+https://github.com/handochan/aelix-ai.git#subdirectory=packages/aelix-coding-agent"
python scripts/validate_catalog.py
```

It does three things:

1. **Caps** — asserts `catalog.json` is under the 2 MiB / 5000-entry limits.
2. **Schema** — validates against [`catalog.schema.json`](catalog.schema.json)
   (a contributor aid; draft 2020-12).
3. **Authoritative** — runs the **real** `parse_catalog` over the exact bytes
   and asserts it keeps **every** entry. The runtime parser is *lenient*: it
   silently drops an entry that is missing `name`/`source`, has control
   characters in its `source`, or is not a JSON object. This check turns that
   silent drop into a **failure**, so a broken entry cannot land unnoticed.

**2. The submission gate** — [`scripts/verify_candidates.py`](scripts/verify_candidates.py).
For every entry your PR **adds**, or whose `source` it **changes**, CI installs
the candidate into a throwaway virtualenv and runs `aelix extension verify`.
Anything but `BOUND` fails the PR, and the tool's own per-endpoint reason is
printed in the log. A description-only edit verifies nothing.

```bash
git show origin/main:catalog.json > /tmp/base-catalog.json
git clone --depth 1 https://github.com/handochan/aelix-ai.git /tmp/aelix-src
python scripts/verify_candidates.py --base-catalog /tmp/base-catalog.json --aelix-src /tmp/aelix-src
```

The same gate re-runs **weekly over every listed entry**. An unpinned `source`
can be `BOUND` the day it merges and rot when its upstream publishes again; a
PR-only check would never see that. Pinning your `source` is the way to avoid
being removed for someone else's release.

## Maintainer: signing the catalog

> **Not yet in effect.** This catalog is **currently unsigned** — no
> `catalog.json.aelixsig` is published and the sidecar URL returns 404. Aelix
> admits an unsigned default catalog best-effort over TLS (`FIRST_PARTY_KEYS`
> ships empty), so nothing is broken; but read the procedure below as intent,
> not as a guarantee already running.

The intended scheme: `catalog.json` is **signed out-of-band** by the owner with
an Ed25519 key, producing a detached `catalog.json.aelixsig` sidecar served
beside it. This lets a user (or an enterprise) require a valid signature before
trusting the catalog document. Contributors do **not** sign; the owner re-signs
after merging.

```bash
# One-time: generate a signing key. Prints the keyId to sign with.
aelix extension keygen --label "Aelix official catalog"

# After merging a catalog change, sign the document with that key. This writes
# catalog.json.aelixsig next to catalog.json.
aelix extension sign catalog.json --key <keyId> --kind catalog
```

The `.aelixsig` sidecar is committed/published beside `catalog.json` (at the same
URL with the `.aelixsig` suffix) so Aelix can fetch it over the same transport.

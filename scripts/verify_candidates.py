#!/usr/bin/env python3
"""Run the BOUND gate over catalog candidates (aelix-ai issue #145, ADR-0207).

`validate_catalog.py` answers "is this document well-formed and will aelix parse
every entry". It never installs anything, so it cannot answer the question a
listing actually makes: **if a user installs this entry, do they get the
contributions it advertises?** A pack whose `aelix-plugin.toml` was dropped from
its wheel -- what a setuptools build with default configuration does -- installs
fine, runs `setup()`, reports success, and contributes NOTHING. This script is
the check that catches that before the listing lands.

Per candidate, in a throwaway virtualenv:

1. Shape-check `source` (see `classify_source`). The official catalog admits git
   and PyPI sources only.
2. Install aelix, then the candidate, then run `aelix extension verify`. Exit 0
   means every installed `aelix.extensions` endpoint BOUND; non-zero means the
   loader would ignore that pack's declarative contributions, and `verify`'s own
   per-endpoint reason is echoed for the contributor.

`verify` imports no plugin code (asserted by an import-marker test in aelix), so
running it on an untrusted submission is safe. **`pip install` is a different
matter: it executes the candidate's build code.** That is why the workflow
driving this runs on `pull_request` and never `pull_request_target` -- a fork's
build code must never see a writable token or a repository secret.

Usage:
    # PR mode -- verify entries added or whose source changed vs the base
    python scripts/verify_candidates.py --base-catalog /tmp/base.json \
        --aelix-src /tmp/aelix-src

    # Sweep mode -- verify EVERY entry (the scheduled run; catches an entry
    # that was BOUND at merge and rotted when an unpinned source moved)
    python scripts/verify_candidates.py --all --aelix-src /tmp/aelix-src

Exit: 0 all candidates BOUND (or none to check); 1 at least one rejected;
2 the script could not get as far as verifying (usage/IO error).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = REPO_ROOT / "catalog.json"

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_DIDNT_RUN = 2

# Generous, because a candidate may build from source on a cold runner.
INSTALL_TIMEOUT_S = 900
VERIFY_TIMEOUT_S = 120

# PEP 508 name, optionally with extras and a version specifier. Anchored, so a
# path-shaped string ("./ext/foo", "/opt/foo", "../foo") cannot match: those
# carry separators and dots in positions a distribution name may not.
_PYPI_SPEC = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?"  # name
    r"(\[[A-Za-z0-9,._-]+\])?"  # optional extras
    r"\s*((==|!=|<=|>=|<|>|~=|===)\s*[^\s,]+"  # optional specifier
    r"(\s*,\s*(==|!=|<=|>=|<|>|~=|===)\s*[^\s,]+)*)?$"
)


def _fail(message: str) -> "int":
    print(f"FAIL: {message}", file=sys.stderr)
    return EXIT_DIDNT_RUN


def _http_url_path_is_git(low: str) -> bool:
    """An http(s) URL whose PATH -- never its host -- ends in ``.git``.

    Mirrors aelix's helper of the same name, including the trailing-only
    ``@<rev>`` strip: splitting on the FIRST ``@`` truncates an ordinary URL
    that merely contains one (``https://gitea.corp/team@eu/ext.git/``) and
    misroutes it. Anchoring on the parsed path is what keeps a ``*.github.io``
    HOST from reading as git.
    """

    if not low.startswith(("http://", "https://")):
        return False
    path = urlparse(low).path.rstrip("/")
    if path.endswith(".git"):
        return True
    head, sep, _rev = path.rpartition("@")
    return bool(sep) and head.rstrip("/").endswith(".git")


def classify_catalog_source(source: str) -> str:
    """Return ``"git"``, ``"pypi"`` or ``"path"`` from the STRING SHAPE alone.

    Named for the catalog rather than reusing aelix's ``classify_source``, which
    is a DIFFERENT contract (it classifies a ``source add`` target into
    path/git/index and calls a bare package name ``None``).

    This deliberately does NOT reuse aelix's ``classify_target`` either. That
    function returns ``"path"`` only when the string EXISTS on the filesystem it
    runs on (``extension_install.py``: ``if target.strip() and
    Path(target).expanduser().exists()``), so on a CI runner -- where a
    contributor's ``./extensions/my-ext`` does not exist -- it reports ``pypi``
    for the very sources this gate has to catch. Measured, not assumed.

    That environment-dependence is also why a path source has no place in a
    PUBLIC catalog: on any machine where the path is absent, the entry silently
    stops meaning "this directory" and starts meaning "a package name", which
    the entry's author never chose (aelix-ai #131). Private and intranet
    catalogs are unaffected -- aelix's runtime parser and
    ``aelix extension install <path>`` are untouched by this script.

    The git arm mirrors ``classify_target``'s, which is filesystem-independent,
    so a source aelix WOULD clone is never rejected here as unrecognised.
    """

    low = source.lower()
    if (
        source.startswith("git+")
        or low.startswith(("git://", "ssh://", "git@"))
        or low.endswith(".git")
        or _http_url_path_is_git(low)
    ):
        return "git"
    if _PYPI_SPEC.match(source.strip()):
        return "pypi"
    return "path"


@dataclass
class Candidate:
    name: str
    source: str
    reason: str  # why it is being verified ("added" / "source changed")


@dataclass
class Result:
    candidate: Candidate
    ok: bool
    verdict: str
    detail: str = ""


def _load_entries(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    entries = document.get("extensions")
    if not isinstance(entries, list):
        raise ValueError(f"{path} has no 'extensions' array")
    return [e for e in entries if isinstance(e, dict)]


def select_candidates(
    head: list[dict], base: list[dict] | None
) -> list[Candidate]:
    """Entries to verify: everything when ``base`` is None, else the delta.

    Identity is ``name``. A new name is a candidate; an existing name whose
    ``source`` moved is a candidate (it now points at different bytes). A
    description-only edit is not -- nothing about what gets installed changed.
    """

    if base is None:
        return [
            Candidate(str(e.get("name")), str(e.get("source")), "sweep")
            for e in head
            if e.get("name") and e.get("source")
        ]

    before = {
        str(e["name"]): str(e.get("source", ""))
        for e in base
        if e.get("name")
    }
    out: list[Candidate] = []
    for entry in head:
        name, source = entry.get("name"), entry.get("source")
        if not name or not source:
            continue  # validate_catalog.py is the authority on malformed entries
        name, source = str(name), str(source)
        if name not in before:
            out.append(Candidate(name, source, "added"))
        elif before[name] != source:
            out.append(Candidate(name, source, "source changed"))
    return out


def _run(
    argv: list[str], *, timeout: int
) -> tuple[int, str]:
    """Run ``argv``, returning ``(returncode, combined output)``."""

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as exc:
        return 125, f"could not execute: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def verify_candidate(
    candidate: Candidate, *, aelix_src: Path, workdir: Path
) -> Result:
    """Install ``candidate`` beside aelix in a fresh venv and run ``verify``."""

    kind = classify_catalog_source(candidate.source)
    if kind == "path":
        return Result(
            candidate,
            False,
            "REJECTED (path source)",
            "the official catalog admits git and PyPI sources only. A local "
            "path cannot be verified here and does not exist on the machine of "
            "anyone installing from this catalog; on such a machine the entry "
            "silently resolves as a PACKAGE NAME instead (aelix-ai #131). "
            "Publish the pack to PyPI, or point the entry at a git URL.",
        )

    env_dir = workdir / "venv"
    code, out = _run([sys.executable, "-m", "venv", str(env_dir)], timeout=300)
    if code != 0:
        return Result(candidate, False, "ERROR (venv)", out.strip())

    py = env_dir / "bin" / "python"
    if not py.exists():  # Windows layout, for a local run on that platform
        py = env_dir / "Scripts" / "python.exe"

    # aelix FIRST, candidate SECOND -- deliberately the reverse of the recipe
    # sketched in ADR-0207. That order is the one a real user is in (aelix is
    # already installed; they then install an extension), so a candidate that
    # only binds by dragging aelix's own dependencies to different versions is
    # caught here rather than by the user. It also lets the endpoint set be
    # attributed: aelix registers NO `aelix.extensions` entry points itself
    # (measured), so every endpoint `verify` reports below arrived with the
    # candidate.
    code, out = _run(
        [
            str(py), "-m", "pip", "install", "-q",
            str(aelix_src / "packages" / "aelix-ai"),
            str(aelix_src / "packages" / "aelix-agent-core"),
            str(aelix_src / "packages" / "aelix-coding-agent"),
        ],
        timeout=INSTALL_TIMEOUT_S,
    )
    if code != 0:
        return Result(candidate, False, "ERROR (aelix install)", out.strip())

    # THIS is the step that executes contributor-controlled build code.
    code, out = _run(
        [str(py), "-m", "pip", "install", "-q", candidate.source],
        timeout=INSTALL_TIMEOUT_S,
    )
    if code != 0:
        return Result(
            candidate,
            False,
            "REJECTED (install failed)",
            f"`pip install {candidate.source}` exited {code}:\n{out.strip()}",
        )

    aelix_bin = py.parent / "aelix"
    if not aelix_bin.exists():
        aelix_bin = py.parent / "aelix.exe"
    # No target name: in this venv the only `aelix.extensions` endpoints are the
    # ones the candidate install brought. Naming a target is impossible anyway
    # for a git source -- a repository name is not a distribution name.
    code, out = _run([str(aelix_bin), "extension", "verify"], timeout=VERIFY_TIMEOUT_S)
    if code == 0:
        return Result(candidate, True, "BOUND", out.strip())
    if code == 1:
        return Result(candidate, False, "REJECTED (not bound)", out.strip())
    return Result(candidate, False, f"ERROR (verify exit {code})", out.strip())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--base-catalog",
        type=Path,
        help="the catalog as it exists on the PR's base branch; candidates are "
        "the entries added or whose source changed relative to it",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="verify every entry (the scheduled sweep) instead of a delta",
    )
    parser.add_argument(
        "--aelix-src",
        type=Path,
        required=True,
        help="path to an aelix-ai checkout (its packages/ are installed into "
        "each throwaway venv)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the throwaway venvs for inspection",
    )
    args = parser.parse_args(argv[1:])

    if args.all == bool(args.base_catalog):
        return _fail("pass exactly one of --all or --base-catalog")
    if not (args.aelix_src / "packages" / "aelix-coding-agent").is_dir():
        return _fail(f"{args.aelix_src} does not look like an aelix-ai checkout")

    try:
        head = _load_entries(args.catalog)
        base = None if args.all else _load_entries(args.base_catalog)
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    candidates = select_candidates(head, base)
    mode = "sweep" if args.all else "delta vs base"
    if not candidates:
        print(
            "OK  the catalog lists no entries; nothing to verify"
            if args.all
            else "OK  no entry was added and no source changed; nothing to verify"
        )
        return EXIT_OK

    print(f"Verifying {len(candidates)} candidate(s) [{mode}]\n")

    results: list[Result] = []
    for candidate in candidates:
        print(f"--- {candidate.name}  ({candidate.reason})")
        print(f"    source: {candidate.source}")
        workdir = Path(tempfile.mkdtemp(prefix="aelix-verify-"))
        try:
            result = verify_candidate(
                candidate, aelix_src=args.aelix_src, workdir=workdir
            )
        finally:
            if not args.keep:
                shutil.rmtree(workdir, ignore_errors=True)
        results.append(result)
        print(f"    => {result.verdict}")
        if result.detail:
            print("\n".join(f"      {ln}" for ln in result.detail.splitlines()))
        print()

    rejected = [r for r in results if not r.ok]
    for result in results:
        print(f"{'PASS' if result.ok else 'FAIL'}  {result.candidate.name}: {result.verdict}")
    if rejected:
        print(
            f"\nFAIL: {len(rejected)} of {len(results)} candidate(s) rejected. "
            "A listing must yield a BOUND manifest (ADR-0207): otherwise the "
            "pack installs, its setup() runs, and every declarative "
            "contribution it advertises is silently ignored."
        )
        return EXIT_REJECTED
    print(f"\nPASS: all {len(results)} candidate(s) BOUND")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

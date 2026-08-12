#!/usr/bin/env python3
"""Tests for the catalog BOUND gate's two pure decisions.

stdlib `unittest` on purpose -- this repo has no test dependency and these need
none. Run: `python scripts/test_verify_candidates.py`

The classifier is the security-relevant half: it decides which submissions are
even eligible, and it must reach that decision from the string alone. aelix's
own `classify_target` cannot be reused for it -- that one calls
`Path(target).exists()`, so on a CI runner it reports `pypi` for exactly the
path sources this gate exists to reject.
"""

from __future__ import annotations

import unittest

from verify_candidates import (
    Candidate,
    classify_catalog_source,
    select_candidates,
)


class ClassifySourceTests(unittest.TestCase):
    def test_git_shapes(self) -> None:
        for source in (
            "git+https://github.com/acme/aelix-ext.git",
            "git+https://github.com/acme/aelix-ext.git@" + "0" * 40,
            "git+ssh://git@github.com/acme/ext.git",
            "https://github.com/acme/ext.git",
            "git://example.com/ext",
            "git@github.com:acme/ext.git",
        ):
            with self.subTest(source=source):
                self.assertEqual(classify_catalog_source(source), "git")

    def test_http_git_urls_whose_suffix_is_not_the_last_thing(self) -> None:
        """Regression: an earlier draft of this classifier tested only
        `endswith('.git')` and so REJECTED sources aelix would happily clone --
        a pinned revision, a trailing slash, a query, a fragment. A gate that
        turns away a valid submission is its own kind of failure."""

        sha = "0" * 40
        for source in (
            f"https://github.com/acme/ext.git@{sha}",
            "https://github.com/acme/ext.git/",
            "https://github.com/acme/ext.git?ref=main",
            "https://github.com/acme/ext.git#egg=ext",
            # An '@' inside the path must not eat the '.git' suffix.
            "https://gitea.corp/team@eu/ext.git/",
        ):
            with self.subTest(source=source):
                self.assertEqual(classify_catalog_source(source), "git")

    def test_a_github_io_host_is_not_git(self) -> None:
        """The host must never be read as the path -- the bug that made every
        `*.github.io` catalog unfetchable in aelix (#111 A-1)."""

        self.assertNotEqual(
            classify_catalog_source("https://handochan.github.io/aelix-marketplace/catalog.json"),
            "git",
        )

    def test_pypi_shapes(self) -> None:
        for source in (
            "aelix-ext-foo",
            "aelix-ext-foo==1.2.3",
            "aelix_ext_foo>=1.0",
            "aelix-ext-foo[extra]",
            "aelix-ext-foo[a,b]>=1.0,<2",
            "Aelix.Ext.Foo===1.0",
        ):
            with self.subTest(source=source):
                self.assertEqual(classify_catalog_source(source), "pypi")

    def test_path_shapes_are_never_pypi(self) -> None:
        """The whole point of the gate's eligibility rule.

        Each of these is what `aelix extension install` treats as a local path
        ON A MACHINE WHERE IT EXISTS, and silently as a package name on one
        where it does not.
        """

        for source in (
            "./extensions/my-local-ext",
            "../sibling-ext",
            "/opt/aelix/my-ext",
            "~/my-ext",
            "extensions/my-ext",
            r"C:\packs\my-ext",
            "file:///opt/aelix/my-ext",
        ):
            with self.subTest(source=source):
                self.assertEqual(classify_catalog_source(source), "path")

    def test_direct_reference_and_bare_urls_are_not_eligible(self) -> None:
        """Neither a PEP 508 direct reference nor a bare archive URL is one of
        the catalog's three documented source forms, so neither may slip in as
        `pypi`."""

        for source in (
            "my-ext @ https://example.com/my_ext-1.0-py3-none-any.whl",
            "https://example.com/my_ext-1.0.tar.gz",
        ):
            with self.subTest(source=source):
                self.assertEqual(classify_catalog_source(source), "path")

    def test_a_bare_name_is_a_package_name(self) -> None:
        """`my-ext` is a valid distribution name, so it classifies as pypi even
        though a directory could share the name. That ambiguity is inherent to
        the source grammar; the catalog's meaning is the package."""

        self.assertEqual(classify_catalog_source("my-ext"), "pypi")


class GitArmParityTests(unittest.TestCase):
    """`classify_catalog_source`'s git arm is a COPY of aelix's, and copies
    drift. Rather than assert the two agree, compare them.

    Skipped when aelix is not importable so the file still runs standalone; CI
    installs aelix before running this, so the comparison is not optional there.
    """

    def test_git_verdict_matches_aelix(self) -> None:
        try:
            from aelix_coding_agent.cli.extension_install import classify_target
        except ImportError:  # pragma: no cover -- standalone run
            self.skipTest("aelix-coding-agent not installed")

        import itertools
        import os
        import tempfile

        # classify_target's FIRST arm is `Path(target).exists()`. Run where
        # nothing exists, which is both the CI runner's situation and the only
        # way to compare the two git arms in isolation.
        cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp())
        try:
            cases = [
                scheme + host + path + suffix
                for scheme, host, path, suffix in itertools.product(
                    ("https://", "http://"),
                    ("github.com", "gitea.corp", "handochan.github.io"),
                    ("/a/ext.git", "/team@eu/ext.git", "/a/ext", "/catalog.json"),
                    ("", "@" + "0" * 40, "?ref=main", "#egg=x", "/"),
                )
            ] + [
                "git+https://github.com/a/b.git",
                "git://h/x",
                "ssh://git@h/x.git",
                "git@github.com:a/b.git",
                "a/b.git",
                "aelix-ext-foo==1.2.3",
                "my-ext",
            ]
            for source in cases:
                with self.subTest(source=source):
                    self.assertEqual(
                        classify_catalog_source(source) == "git",
                        classify_target(source) == "git",
                    )
        finally:
            os.chdir(cwd)


class SelectCandidatesTests(unittest.TestCase):
    @staticmethod
    def _entry(name: str, source: str, description: str = "") -> dict:
        return {"name": name, "source": source, "description": description}

    def test_added_entry_is_a_candidate(self) -> None:
        base = [self._entry("a", "a==1")]
        head = [self._entry("a", "a==1"), self._entry("b", "b==1")]
        got = select_candidates(head, base)
        self.assertEqual([(c.name, c.reason) for c in got], [("b", "added")])

    def test_changed_source_is_a_candidate(self) -> None:
        base = [self._entry("a", "a==1")]
        head = [self._entry("a", "a==2")]
        got = select_candidates(head, base)
        self.assertEqual(
            [(c.name, c.reason) for c in got], [("a", "source changed")]
        )

    def test_description_only_edit_is_not_a_candidate(self) -> None:
        base = [self._entry("a", "a==1", "old")]
        head = [self._entry("a", "a==1", "new")]
        self.assertEqual(select_candidates(head, base), [])

    def test_removal_is_not_a_candidate(self) -> None:
        base = [self._entry("a", "a==1"), self._entry("b", "b==1")]
        head = [self._entry("a", "a==1")]
        self.assertEqual(select_candidates(head, base), [])

    def test_sweep_takes_every_entry(self) -> None:
        head = [self._entry("a", "a==1"), self._entry("b", "b==1")]
        got = select_candidates(head, None)
        self.assertEqual([c.name for c in got], ["a", "b"])
        self.assertTrue(all(c.reason == "sweep" for c in got))

    def test_malformed_entries_are_left_to_validate_catalog(self) -> None:
        head = [{"name": "a"}, {"source": "b==1"}, self._entry("c", "c==1")]
        self.assertEqual(
            [c.name for c in select_candidates(head, [])], ["c"]
        )

    def test_candidate_is_comparable(self) -> None:
        self.assertEqual(
            Candidate("a", "a==1", "added"), Candidate("a", "a==1", "added")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

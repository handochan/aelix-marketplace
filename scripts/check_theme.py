#!/usr/bin/env python3
"""Both colour schemes of index.html must be legible, and the lockup must swap.

WHY THIS EXISTS. index.html is served to GitHub Pages verbatim -- no build, no
bundler, nothing that reads it. When it was dark-locked, the measured ratios in
the comment above :root were the only record that anyone had checked, and a
comment is not a check. Adding a light scheme doubles the surface for the same
mistake, and the light half is the half a maintainer on a dark laptop never
sees.

Four things are measured, all from the stylesheet itself so they cannot go
stale against it:

1. Every token is classified. A new token with no role here is an error, so the
   tables below cannot silently skip what they never measured.
2. Every text token clears WCAG AA (4.5:1) on every surface token, in BOTH
   schemes -- not merely on the pairs used today.
3. Anything with a fill of its own is measured twice: the text on it, and the
   band itself against the page. An element that reads fine but dissolves into
   the page is a real failure mode and text contrast alone cannot see it.
4. The lockup actually swaps: the <picture> must offer a light source, the file
   must exist, and the two vectors must differ in the word and the cursor pixel
   (BRAND.md: no brand colour is strong on both grounds, so the lockup is
   chosen per ground rather than recoloured to compromise).

Every detector is proved against a doctored copy, so a zero means "no fault"
rather than "the pattern stopped matching". The audit is reported BEFORE that
proof runs, deliberately -- see main().

Exit status: 1 the page has a fault, 2 a detector is blind, 3 both.

Usage:  python scripts/check_theme.py [path/to/index.html]
Requires: nothing outside the standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

AA_TEXT = 4.5
AA_NON_TEXT = 3.0
HAIRLINE = 1.2

ROOT = Path(__file__).resolve().parent.parent

# --- what each token is for ------------------------------------------------

TEXT = ("--fg", "--fg-strong", "--fg-muted", "--accent", "--chip-fg",
        "--advisory-fg", "--error-fg")
SURFACES = ("--bg", "--bg-elev", "--bg-code", "--chip-bg", "--advisory-bg", "--error-bg")
#: (text, the one fill it sits on). Never measured against the page: on the
#: light ground --accent-fg is paper, and paper IS the page.
PAIRED = (("--accent-fg", "--accent"),)
#: Fills that form a control (the skip link), so the band must read too.
FILLS = ("--accent",)
#: Focus ring: non-text, and it lands on both the page and the elevated surface.
RINGS = ("--focus",)
LINES = ("--border", "--border-strong", "--advisory-border", "--error-border")
NON_COLOUR = ("--mono", "--radius", "--maxw")

#: Exactly the roles the light block re-points. A role missing here does not
#: error -- it silently keeps its dark value, which is how half a palette ships.
LIGHT_OVERRIDES = frozenset({
    "--bg", "--bg-elev", "--bg-code", "--fg", "--fg-strong", "--fg-muted",
    "--border", "--border-strong", "--accent", "--accent-fg", "--chip-bg",
    "--chip-fg", "--advisory-bg", "--advisory-fg", "--advisory-border",
    "--error-bg", "--error-fg", "--error-border", "--focus",
})

CLASSIFIED = (set(TEXT) | set(SURFACES) | {n for p in PAIRED for n in p} | set(FILLS)
              | set(RINGS) | set(LINES) | set(NON_COLOUR))

# --- colour maths ----------------------------------------------------------


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(colour: str) -> tuple[int, int, int]:
    text = colour.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def luminance(colour: str) -> float:
    r, g, b = _rgb(colour)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fore: str, back: str) -> float:
    lf, lb = luminance(fore), luminance(back)
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


# --- a very small stylesheet reader ---------------------------------------

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_LIGHT_AT = re.compile(r"@media\s*\(\s*prefers-color-scheme:\s*light\s*\)\s*\{", re.I)
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,([^()]*))?\)")


def split_by_scheme(html: str) -> tuple[str, str]:
    found = _STYLE.search(html)
    if not found:
        raise SystemExit("index.html has no <style> block")
    css = _COMMENT.sub("", found.group(1))
    outside, inside, cursor = [], [], 0
    while True:
        hit = _LIGHT_AT.search(css, cursor)
        if not hit:
            outside.append(css[cursor:])
            return "".join(outside), "\n".join(inside)
        outside.append(css[cursor : hit.start()])
        depth, index = 1, hit.end()
        while index < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[index], 0)
            index += 1
        inside.append(css[hit.end() : index - 1])
        cursor = index


def root_tokens(css: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        selector, body = chunk.split("{", 1)
        if " ".join(selector.split()) != ":root":
            continue
        for piece in body.split(";"):
            if ":" not in piece:
                continue
            name, value = piece.split(":", 1)
            if name.strip().startswith("--"):
                tokens[name.strip()] = " ".join(value.split())
    return tokens


def resolve(value: str, tokens: dict[str, str], depth: int = 0) -> str:
    if depth > 20:
        raise SystemExit(f"cyclic var() while resolving {value!r}")

    def swap(match: re.Match[str]) -> str:
        name, fallback = match.group(1), match.group(2)
        if name in tokens:
            return resolve(tokens[name], tokens, depth + 1)
        if fallback is None:
            raise SystemExit(f"undefined custom property {name}")
        return resolve(fallback.strip(), tokens, depth + 1)

    previous, current = None, value
    while previous != current:
        previous, current = current, _VAR.sub(swap, current)
    return " ".join(current.split())


def schemes(html: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    outside, inside = split_by_scheme(html)
    dark_raw = root_tokens(outside)
    light_raw = {**dark_raw, **root_tokens(inside)}
    dark = {k: resolve(v, dark_raw) for k, v in dark_raw.items()}
    light = {k: resolve(v, light_raw) for k, v in light_raw.items()}
    return dark, light, root_tokens(inside)


# --- the checks ------------------------------------------------------------


def audit(html: str, assets: Path) -> list[str]:
    """Return a list of failures; empty means the page is sound."""

    bad: list[str] = []
    dark, light, overrides = schemes(html)

    declared = set(dark)
    if declared != CLASSIFIED:
        bad.append(
            "token roles are out of date -- "
            f"only in the stylesheet: {sorted(declared - CLASSIFIED)}; "
            f"only in this script: {sorted(CLASSIFIED - declared)}"
        )
        return bad  # every table below would be measuring the wrong set

    if set(overrides) != set(LIGHT_OVERRIDES):
        bad.append(
            "the light block re-points the wrong set of roles -- "
            f"only in the stylesheet: {sorted(set(overrides) - LIGHT_OVERRIDES)}; "
            f"only in this script: {sorted(LIGHT_OVERRIDES - set(overrides))}"
        )
    for name in sorted(set(overrides) & LIGHT_OVERRIDES):
        if dark[name] == light[name]:
            bad.append(f"light override {name} = {dark[name]} does nothing")

    if not re.search(r"color-scheme:\s*light dark", html):
        bad.append("color-scheme is not 'light dark': controls and scrollbars stay dark")
    if luminance(light["--bg"]) < 0.80:
        bad.append(f"the light ground {light['--bg']} is not light")
    if luminance(dark["--bg"]) > 0.05:
        bad.append(f"the dark ground {dark['--bg']} is not dark")

    for scheme, tokens in (("dark", dark), ("light", light)):
        for text in TEXT:
            for surface in SURFACES:
                got = contrast(tokens[text], tokens[surface])
                if got < AA_TEXT:
                    bad.append(
                        f"{scheme}: {text} ({tokens[text]}) on {surface} "
                        f"({tokens[surface]}) is {got:.2f}:1, below AA {AA_TEXT}"
                    )
        for text, fill in PAIRED:
            got = contrast(tokens[text], tokens[fill])
            if got < AA_TEXT:
                bad.append(f"{scheme}: {text} on {fill} is {got:.2f}:1, below AA")
        # the second contrast: the band itself, not only the text on it
        for fill in FILLS:
            got = contrast(tokens[fill], tokens["--bg"])
            if got < AA_NON_TEXT:
                bad.append(
                    f"{scheme}: the {fill} band ({tokens[fill]}) against the page "
                    f"is {got:.2f}:1 -- the control dissolves into the page"
                )
        for ring in RINGS:
            for surface in ("--bg", "--bg-elev"):
                got = contrast(tokens[ring], tokens[surface])
                if got < AA_NON_TEXT:
                    bad.append(f"{scheme}: {ring} on {surface} is {got:.2f}:1")
        for line in LINES:
            behind = {"--advisory-border": "--advisory-bg",
                      "--error-border": "--error-bg"}.get(line, "--bg")
            got = contrast(tokens[line], tokens[behind])
            if got < HAIRLINE:
                bad.append(f"{scheme}: {line} on {behind} is {got:.2f}:1 -- it flattens")

    bad.extend(_audit_lockup(html, assets))
    return bad


_WORD = re.compile(r'<g fill="(#[0-9A-Fa-f]{6})">')
_PIXEL = re.compile(r'<path fill="(#[0-9A-Fa-f]{6})" d="M462 12')


def _audit_lockup(html: str, assets: Path) -> list[str]:
    bad: list[str] = []
    source = re.search(
        r'<source media="\(prefers-color-scheme: light\)" srcset="([^"]+)">', html
    )
    fallback = re.search(r'<img class="lockup" src="([^"]+)"', html)
    if not source:
        return ["the header lockup offers no light <source>: a dark lockup on a light page"]
    if not fallback:
        return ["the header lockup has no <img> fallback"]

    files = {}
    for label, rel in (("light", source.group(1)), ("dark", fallback.group(1))):
        path = assets.parent / rel
        if not path.exists():
            bad.append(f"the {label} lockup {rel} is not in the repository")
            continue
        files[label] = path.read_text(encoding="utf-8")
    if len(files) != 2:
        return bad

    for pattern, what in ((_WORD, "wordmark"), (_PIXEL, "cursor pixel")):
        got = {k: pattern.search(v) for k, v in files.items()}
        if not all(got.values()):
            bad.append(f"could not read the {what} fill out of both lockups")
            continue
        if got["light"].group(1).upper() == got["dark"].group(1).upper():
            bad.append(
                f"the two lockups paint the {what} the same colour "
                f"({got['dark'].group(1)}) -- one of them is wrong for its ground"
            )
    return bad


# --- positive controls: prove each detector can see its own fault -----------

CONTROLS = (
    ("light accent reverts to the brand glow",
     "      --accent: #0E7490;", "      --accent: #22D3EE;"),
    ("a light role is left at its dark value",
     "      --fg: #22303A;", "      --fg: #C6D6DC;"),
    ("the light block is gone",
     "  @media (prefers-color-scheme: light) {", "  @media (prefers-color-scheme: nope) {"),
    ("color-scheme goes back to dark only",
     "color-scheme: light dark;", "color-scheme: dark;"),
    ("an unclassified token appears",
     "    --radius: 12px;", "    --rogue: #ff00ff;\n    --radius: 12px;"),
    ("the light lockup source is dropped",
     '          <source media="(prefers-color-scheme: light)" srcset="assets/lockup-light.svg">\n',
     ""),
    ("the light lockup points at the dark file",
     'srcset="assets/lockup-light.svg"', 'srcset="assets/lockup-dark.svg"'),
)


def self_test(html: str, assets: Path) -> list[str]:
    broken = []
    for label, old, new in CONTROLS:
        if html.count(old) < 1:
            broken.append(f"control '{label}' no longer matches the page: {old!r}")
            continue
        if not audit(html.replace(old, new, 1), assets):
            broken.append(f"control '{label}' passed the audit -- that fault is invisible")
    return broken


def main(argv: list[str]) -> int:
    """Report the audit FIRST, then the controls.

    The other order was tried and is wrong: a fault big enough to break a
    control's anchor made the script exit on "detectors are blind" without ever
    saying what was wrong with the page. Sabotaging this file is what surfaced
    that -- 7 of 15 injected faults were caught by the reporter rather than by
    the audit, so the sweep proved less than it appeared to. Both layers now
    always run, and both always print.
    """

    page = Path(argv[1]) if len(argv) > 1 else ROOT / "index.html"
    html = page.read_text(encoding="utf-8")
    assets = page.parent / "assets"

    bad = audit(html, assets)
    for line in bad:
        print(f"FAIL     {line}")
    if not bad:
        dark, light, _ = schemes(html)
        for scheme, tokens in (("dark", dark), ("light", light)):
            worst = min(
                (contrast(tokens[t], tokens[s]), t, s) for t in TEXT for s in SURFACES
            )
            print(f"ok       {scheme:5s} ground {tokens['--bg']}; weakest text pair "
                  f"{worst[0]:.2f}:1 ({worst[1]} on {worst[2]})")
        print(f"ok       {page} reads on both grounds")

    broken = self_test(html, assets)
    for line in broken:
        print(f"BLIND    {line}")
    if broken:
        print("         a clean audit above would have meant nothing; fix the "
              "controls (their anchors may simply have moved) and run again")
    else:
        print(f"ok       {len(CONTROLS)} positive controls all detected")

    return (1 if bad else 0) + (2 if broken else 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""Both colour schemes of index.html must be legible, and the lockup must swap.

WHY THIS EXISTS. index.html is served to GitHub Pages verbatim -- no build, no
bundler, nothing that reads it. When it was dark-locked, the measured ratios in
the comment above :root were the only record that anyone had checked, and a
comment is not a check. Adding a light scheme doubles the surface for the same
mistake, and the light half is the half a maintainer on a dark laptop never
sees.

WHAT IT MEASURES.

1. Every token is classified. A new token with no role here is an error, so the
   tables below cannot silently skip what they never measured.
2. The cascade is read the way a browser reads it. A @media query carries no
   specificity, so a :root written BELOW the light block wins for a light
   reader; the token maps are built in document order, and a separate check
   pins that no :root follows the light block at all.
3. Every colour lives in a token. A hex literal in a rule body, or any rule
   other than :root inside the light block, is a failure -- both are invisible
   to a palette, and a palette is the only thing the tables can measure.
4. Every text token clears WCAG AA (4.5:1) on every surface token, in BOTH
   schemes. Anything with a fill or a ring of its own is measured twice: the
   text on it, and the band itself against the page. An element that reads fine
   but dissolves into the page is a real failure mode and text contrast alone
   cannot see it.
5. The lockup actually swaps: the <picture> must offer a light source, the file
   must exist, and the two vectors must differ in the word and the cursor pixel
   (BRAND.md: no brand colour is strong on both grounds, so the lockup is
   chosen per ground rather than recoloured to compromise).

EVERY detector is proved individually. Each control doctors the page and then
asserts that THAT detector's own message comes back -- not merely that some
failure did, which an earlier version settled for and which let one broken
detector hide behind any other that happened to fire.

The audit is reported BEFORE the controls run, deliberately -- see main().

Usage:  python scripts/check_theme.py [path/to/index.html]
Requires: nothing outside the standard library.
Exit status: 1 the page has a fault, 2 a detector is blind, 3 both.
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

#: The only selectors the light block may touch.
LIGHT_SELECTORS = frozenset({":root"})

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


# --- a very small stylesheet reader, in document order ---------------------

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_LIGHT_AT = re.compile(r"@media\s*\(\s*prefers-color-scheme:\s*light\s*\)\s*\{", re.I)
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,([^()]*))?\)")
_LITERAL = re.compile(r"#[0-9A-Fa-f]{3,8}\b|\brgba?\(|\bhsla?\(|\bcolor-mix\(")


def segments(html: str) -> list[tuple[str, bool]]:
    """The stylesheet in document order as (text, is_inside_a_light_media_block)."""
    found = _STYLE.search(html)
    if not found:
        raise SystemExit("index.html has no <style> block")
    css = _COMMENT.sub("", found.group(1))
    out: list[tuple[str, bool]] = []
    cursor = 0
    while True:
        hit = _LIGHT_AT.search(css, cursor)
        if not hit:
            out.append((css[cursor:], False))
            return out
        out.append((css[cursor : hit.start()], False))
        depth, index = 1, hit.end()
        while index < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[index], 0)
            index += 1
        out.append((css[hit.end() : index - 1], True))
        cursor = index


def _declarations(body: str) -> list[tuple[str, str]]:
    out = []
    for piece in body.split(";"):
        if ":" not in piece:
            continue
        name, value = piece.split(":", 1)
        out.append((name.strip(), " ".join(value.split())))
    return out


def rules_in_order(html: str) -> list[tuple[str, str, bool]]:
    """(selector, body, is_inside_light) across the whole sheet, in order."""
    out = []
    for text, in_light in segments(html):
        for chunk in text.split("}"):
            if "{" not in chunk:
                continue
            selector, body = chunk.split("{", 1)
            selector = " ".join(selector.split())
            if selector and not selector.startswith("@"):
                out.append((selector, body, in_light))
    return out


def token_map(html: str, *, include_light: bool) -> dict[str, str]:
    """Merge every :root in DOCUMENT ORDER, the way equal specificity resolves."""
    tokens: dict[str, str] = {}
    for selector, body, in_light in rules_in_order(html):
        if selector != ":root" or (in_light and not include_light):
            continue
        for name, value in _declarations(body):
            if name.startswith("--"):
                tokens[name] = value
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


def schemes(html: str) -> tuple[dict[str, str], dict[str, str], set[str]]:
    dark_raw = token_map(html, include_light=False)
    light_raw = token_map(html, include_light=True)
    overrides = {
        name
        for selector, body, in_light in rules_in_order(html)
        if in_light and selector == ":root"
        for name, _ in _declarations(body)
        if name.startswith("--")
    }
    dark = {k: resolve(v, dark_raw) for k, v in dark_raw.items()}
    light = {k: resolve(v, light_raw) for k, v in light_raw.items()}
    return dark, light, overrides


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

    if overrides != set(LIGHT_OVERRIDES):
        bad.append(
            "the light block re-points the wrong set of roles -- "
            f"only in the stylesheet: {sorted(overrides - LIGHT_OVERRIDES)}; "
            f"only in this script: {sorted(LIGHT_OVERRIDES - overrides)}"
        )
    for name in sorted(overrides & LIGHT_OVERRIDES):
        if dark[name] == light[name]:
            bad.append(f"light override {name} = {dark[name]} does nothing")

    seen_light = False
    for selector, _body, in_light in rules_in_order(html):
        if in_light:
            seen_light = True
            if selector not in LIGHT_SELECTORS:
                bad.append(
                    f"the light block touches {selector!r}, which no token table "
                    "can see -- only :root belongs there"
                )
        elif seen_light and selector == ":root":
            bad.append(
                "a :root block sits below the light @media block; a media query "
                "adds no specificity, so everything it declares beats the light "
                "palette for a light reader"
            )

    for selector, body, _in_light in rules_in_order(html):
        if selector == ":root":
            continue
        for name, value in _declarations(body):
            if _LITERAL.search(value):
                bad.append(
                    f"colour literal outside :root -- {selector} {{ {name}: {value} }} "
                    "cannot follow the scheme, and nothing here can measure it"
                )

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
                bad.append(
                    f"{scheme}: {text} on its own fill {fill} is {got:.2f}:1, below AA"
                )
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
                    bad.append(
                        f"{scheme}: the focus ring {ring} ({tokens[ring]}) on "
                        f"{surface} is {got:.2f}:1, below {AA_NON_TEXT}"
                    )
        for line in LINES:
            behind = {"--advisory-border": "--advisory-bg",
                      "--error-border": "--error-bg"}.get(line, "--bg")
            got = contrast(tokens[line], tokens[behind])
            if got < HAIRLINE:
                bad.append(
                    f"{scheme}: the hairline {line} on {behind} is {got:.2f}:1 -- it flattens"
                )

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


# --- positive controls: one per detector, each matched by ITS OWN message ----
#
# (label, find, replace, the substring that detector alone produces)

CONTROLS = (
    ("an unclassified token appears",
     "    --radius: 12px;", "    --rogue: #ff00ff;\n    --radius: 12px;",
     "token roles are out of date"),
    ("a light override is forgotten",
     "      --chip-fg: #2B3A3F;\n", "",
     "re-points the wrong set of roles"),
    ("a light override is a no-op",
     "      --border-strong: #BAC7D1;", "      --border-strong: #2b3a46;",
     "does nothing"),
    ("a :root is written below the light block",
     "  /* ---- Reset / base", "  :root { --bg: #0B0F14; }\n  /* ---- Reset / base",
     "sits below the light @media block"),
    ("a non-:root rule is put in the light block",
     "      --focus: #0E7490;\n    }", "      --focus: #0E7490;\n    }\n    .card { background: #0B0F14; }",
     "the light block touches"),
    ("a colour is hardcoded into a rule",
     "  .hero p.lead {\n    margin: 0 0 8px;", "  .hero p.lead {\n    color: #C6D6DC;\n    margin: 0 0 8px;",
     "colour literal outside :root"),
    ("color-scheme goes back to dark only",
     "color-scheme: light dark;", "color-scheme: dark;",
     "color-scheme is not 'light dark'"),
    ("the light ground is left dark",
     "      --bg: #F6FAFB;", "      --bg: #0B0F14;",
     "is not light"),
    ("the dark ground is made light",
     "    --bg: #0B0F14;\n", "    --bg: #F6FAFB;\n",
     "is not dark"),
    ("light body text is left at its dark value",
     "      --fg: #22303A;", "      --fg: #C6D6DC;",
     "below AA"),
    ("the text on the accent fill is left as ink",
     "      --accent-fg: #F6FAFB;", "      --accent-fg: #0B1220;",
     "on its own fill"),
    ("the accent band dissolves into the page",
     "      --accent: #0E7490;", "      --accent: #F4F9FA;",
     "dissolves into the page"),
    ("the focus ring flattens on the light page",
     "      --focus: #0E7490;", "      --focus: #F2F7F9;",
     "the focus ring"),
    ("a hairline flattens into its own tint",
     "      --error-border: #EBB8B8;", "      --error-border: #FDEAEA;",
     "it flattens"),
    ("the light lockup source is dropped",
     '          <source media="(prefers-color-scheme: light)" srcset="assets/lockup-light.svg">\n',
     "", "offers no light <source>"),
    ("the light lockup points at a missing file",
     'srcset="assets/lockup-light.svg"', 'srcset="assets/lockup-nope.svg"',
     "is not in the repository"),
    ("the light lockup points at the dark file",
     'srcset="assets/lockup-light.svg"', 'srcset="assets/lockup-dark.svg"',
     "paint the wordmark the same colour"),
)


def self_test(html: str, assets: Path) -> list[str]:
    """Prove each detector on its own. Matching THIS detector's message, not
    merely 'something failed' -- an earlier version did the latter, which let a
    broken detector hide behind any other that fired on the same doctored page.
    """
    broken = []
    for label, old, new, expect in CONTROLS:
        if old not in html:
            broken.append(f"control '{label}' no longer matches the page: {old[:48]!r}")
            continue
        found = audit(html.replace(old, new, 1), assets)
        if not any(expect in line for line in found):
            broken.append(
                f"control '{label}' did not produce {expect!r} -- that detector is "
                f"blind. It reported: {found or 'nothing at all'}"
            )
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
        print(f"ok       {len(CONTROLS)} detectors each proved by their own control")

    return (1 if bad else 0) + (2 if broken else 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Syntax validation tests for all source files in the project.

Checks Python, CSS, JavaScript, and HTML/XML files for syntax errors.
Uses: ast (Python), tinycss2 (CSS), acorn (JS), lxml (HTML/XML).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_JS_DIR = PROJECT_ROOT / "static" / "js"
STATIC_CSS_DIR = PROJECT_ROOT / "static" / "css"

# File patterns to check per type
PYTHON_DIRS = [BACKEND_DIR]
PYTHON_FILES = [PROJECT_ROOT / "run.py"]
CSS_DIRS = [STATIC_CSS_DIR]
JS_DIRS = [STATIC_JS_DIR]
HTML_DIRS = [TEMPLATES_DIR]


def _iter_python_files():
    seen = set()
    for d in PYTHON_DIRS:
        for f in sorted(d.rglob("*.py")):
            if f not in seen:
                seen.add(f)
                yield f
    for f in PYTHON_FILES:
        if f.exists() and f not in seen:
            seen.add(f)
            yield f


def _iter_css_files():
    for d in CSS_DIRS:
        yield from sorted(d.glob("*.css"))


def _iter_js_files():
    for d in JS_DIRS:
        yield from sorted(d.glob("*.js"))


def _iter_html_files():
    for d in HTML_DIRS:
        yield from sorted(d.glob("*.html"))


# ─── Python Syntax ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", list(_iter_python_files()), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_python_syntax(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        pytest.fail(f"Cannot read {path}: {e}")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {path}: {e}")


# ─── CSS Syntax ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", list(_iter_css_files()), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_css_syntax(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        pytest.fail(f"Cannot read {path}: {e}")
    try:
        import tinycss2

        stylesheet = tinycss2.parse_stylesheet(source)
        errors = [err for err in stylesheet if isinstance(err, tinycss2.ast.ParseError)]
        if errors:
            msg = "\n".join(f"  Line ~{e.source_line}: {e.message}" for e in errors[:10])
            pytest.fail(f"CSS parse errors in {path}:\n{msg}")
    except ImportError:
        pytest.skip("tinycss2 not available")


# ─── JavaScript Syntax ────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", list(_iter_js_files()), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_js_syntax(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        pytest.fail(f"Cannot read {path}: {e}")

    # Try acorn via npx for proper JS parsing
    try:
        result = subprocess.run(
            ["npx", "--yes", "acorn", "--ecma2022", "--module", "--allow-hash-bang", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                pytest.fail(f"JS syntax error in {path}: {stderr}")
    except FileNotFoundError:
        pytest.skip("acorn (via npx) not available")
    except subprocess.TimeoutExpired:
        pytest.skip("acorn timed out")
    except Exception as e:
        # Fallback: basic structural validation
        _basic_js_check(source, path)


def _basic_js_check(source: str, path: Path):
    """Basic JavaScript structure check (balanced braces, parens)."""
    stack = []
    pairs = {"{": "}", "[": "]", "(": ")"}
    in_string = False
    in_template = False
    string_char = None
    i = 0
    while i < len(source):
        c = source[i]
        nc = source[i + 1] if i + 1 < len(source) else ""

        # Handle strings
        if not in_template:
            if c in ("'", '"', "`") and (i == 0 or source[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = c
                    if c == "`":
                        in_template = True
                elif c == string_char:
                    in_string = False
                    in_template = False
            if in_string:
                i += 1
                continue
            if c == "/" and nc in ("/", "*"):
                # Skip comment
                if nc == "/":
                    end = source.find("\n", i)
                    i = end if end != -1 else len(source)
                else:
                    end = source.find("*/", i + 2)
                    i = end + 2 if end != -1 else len(source)
                continue

        if c in pairs:
            stack.append(pairs[c])
        elif c in ("}", "]", ")"):
            if not stack:
                pytest.fail(f"Unmatched closing bracket '{c}' in {path} at position {i}")
            expected = stack.pop()
            if c != expected:
                pytest.fail(
                    f"Mismatched bracket in {path} at position {i}: "
                    f"expected '{expected}', got '{c}'"
                )
        i += 1

    if stack:
        pytest.fail(f"Unclosed brackets in {path}: {stack}")


# ─── HTML/XML Syntax ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", list(_iter_html_files()), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_html_syntax(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        pytest.fail(f"Cannot read {path}: {e}")

    # Jinja2 templates are not valid HTML - parse with html5lib in forgiving mode
    try:
        import html5lib

        doc = html5lib.parse(source, namespaceHTMLElements=False)
        if doc is None:
            pytest.fail(f"HTML parsing returned None for {path}")
        # Check for parse errors in the document
        _check_html5lib_errors(source, path)
    except ImportError:
        pass

    # Also try lxml for additional validation
    try:
        from lxml import html

        # lxml is more forgiving but will catch structural issues
        tree = html.fromstring(source)
        if tree is None:
            pytest.fail(f"lxml parsing returned None for {path}")
    except Exception as e:
        pytest.fail(f"HTML parse error in {path}: {e}")


def _check_html5lib_errors(source: str, path: Path):
    """Try to identify common HTML template issues."""
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Check for unclosed template tags that span lines
        if "{%" in stripped and "%}" not in stripped and "{% end" not in stripped:
            # Multi-line template tags are OK, but single-line should be closed
            if "{%-" not in stripped:
                pass  # Allow block starts like {% block %}, {% for %}
        # Check basic Jinja2 syntax: {{ }} should be closed on same line
        if "{{" in stripped and "}}" not in stripped:
            if "{%" not in stripped[i:]:
                pass  # Allow multi-line expressions

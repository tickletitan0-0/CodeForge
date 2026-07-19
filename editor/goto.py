"""goto.py - symbol extraction for CodeForge's "Go to Line / Symbol" popup.

extract_symbols(path, content) is the single entry point app.py calls to
build the list its Ctrl+P popup fuzzy-filters against (the popup itself
lives in app.py, reusing the same overrideredirect/fuzzy-score/positioning
plumbing as the Command Palette - this module only knows how to find
symbols in text, not how to draw anything). It dispatches by file
extension, mirroring linters.py's _EXT_LANGUAGE table, since the same
languages that get real diagnostics there are the ones worth a real
symbol list here:

  - Python uses the standard library's ast module, so function/class defs
    (including nested ones, indented in the popup to show their nesting)
    are always exact - no regex guessing.
  - JavaScript, Java, CSS, and HTML get a regex scan instead of a real
    parser, the same "good enough, no bespoke grammar per language"
    tradeoff linters.py makes for its generic bracket checker. It catches
    the common declaration shapes (function/class/const-arrow, CSS rule
    selectors, HTML ids), not every possible one.
  - Any other or unrecognized extension just gets no symbols - the popup
    still works fine as a plain "type a number, jump to that line" box in
    that case, it just has nothing to fuzzy-search.

Nothing here ever raises out to the caller: a symbol list is a nice-to-
have navigation aid, not something that should ever be able to break the
popup opening, so any parse/regex hiccup just means an empty list for
that pass - same "degrade quietly" convention as linters.py and
code_folding.py.
"""

import ast
import os
import re


# ---------------- Python: ast (exact) ----------------

def _extract_python(content):
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    symbols = []

    def walk(node, indent):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                symbols.append({"name": child.name, "kind": "class", "line": child.lineno, "indent": indent})
                walk(child, indent + 1)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                symbols.append({"name": child.name, "kind": kind, "line": child.lineno, "indent": indent})
                walk(child, indent + 1)
            else:
                # Don't recurse into an arbitrary statement's own body
                # generically (e.g. an `if` block) - just keep looking
                # for defs/classes at whatever indent we're already at,
                # so a function defined inside an `if TYPE_CHECKING:`
                # guard still shows up instead of being skipped.
                walk(child, indent)

    try:
        walk(tree, 0)
    except RecursionError:
        return symbols
    return symbols


# ---------------- JavaScript: regex (best-effort) ----------------

_JS_PATTERNS = (
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\("), "const"),
    (re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function"), "const"),
)


def _extract_js(content):
    symbols = []
    for i, line in enumerate(content.split("\n"), start=1):
        for pattern, kind in _JS_PATTERNS:
            m = pattern.match(line)
            if m:
                symbols.append({"name": m.group(1), "kind": kind, "line": i, "indent": 0})
                break
    return symbols


# ---------------- Java: regex (best-effort) ----------------

_JAVA_TYPE_PATTERN = re.compile(
    r"^\s*(?:public|private|protected|static|final|abstract|\s)*"
    r"(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
_JAVA_METHOD_PATTERN = re.compile(
    r"^\s*(?:public|private|protected|static|final|abstract|synchronized|native|\s)+"
    r"[\w<>\[\],\s]+?\s+([A-Za-z_$][\w$]*)\s*\([^;{]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{?\s*$"
)
_JAVA_CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "return"}


def _extract_java(content):
    symbols = []
    for i, line in enumerate(content.split("\n"), start=1):
        m = _JAVA_TYPE_PATTERN.match(line)
        if m:
            symbols.append({"name": m.group(1), "kind": "type", "line": i, "indent": 0})
            continue
        m = _JAVA_METHOD_PATTERN.match(line)
        if m and m.group(1) not in _JAVA_CONTROL_KEYWORDS:
            symbols.append({"name": m.group(1), "kind": "method", "line": i, "indent": 1})
    return symbols


# ---------------- CSS: rule selectors (best-effort) ----------------

_CSS_SELECTOR_PATTERN = re.compile(r"^\s*([^{}\n]+?)\s*\{")


def _extract_css(content):
    symbols = []
    for i, line in enumerate(content.split("\n"), start=1):
        m = _CSS_SELECTOR_PATTERN.match(line)
        if not m:
            continue
        selector = m.group(1).strip()
        if selector and not selector.startswith(("//", "/*", "@media", "@keyframes")):
            symbols.append({"name": selector, "kind": "rule", "line": i, "indent": 0})
    return symbols


# ---------------- HTML: element ids (best-effort) ----------------

_HTML_ID_PATTERN = re.compile(r'id=["\']([^"\']+)["\']')


def _extract_html(content):
    symbols = []
    for i, line in enumerate(content.split("\n"), start=1):
        for m in _HTML_ID_PATTERN.finditer(line):
            symbols.append({"name": "#" + m.group(1), "kind": "id", "line": i, "indent": 0})
    return symbols


# ---------------- Dispatch ----------------

_EXT_EXTRACTOR = {
    ".py": _extract_python, ".pyw": _extract_python,
    ".js": _extract_js,
    ".java": _extract_java,
    ".css": _extract_css,
    ".html": _extract_html, ".htm": _extract_html,
}


def extract_symbols(path, content):
    """Returns a list of {"name", "kind", "line", "indent"} dicts found in
    `content`, dispatched by the file extension in `path`, sorted top to
    bottom. Never raises - any parser/regex failure just means an empty
    symbol list (the popup still works as a bare line-number jump)
    rather than a crash."""
    if not content or not path:
        return []
    ext = os.path.splitext(path)[1].lower()
    extractor = _EXT_EXTRACTOR.get(ext)
    if extractor is None:
        return []
    try:
        symbols = extractor(content)
    except Exception:
        return []
    return sorted(symbols, key=lambda s: s["line"])
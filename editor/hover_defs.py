"""hover_defs.py - "definition on hover" support for CodeForge.

find_definition(path, content, name, hover_line) is the single entry
point app.py calls, from a debounced <Motion> hook that mirrors the one
linters.py's diagnostics already use (see bind_lint_hover in app.py) -
except the mouse position there resolves straight to a word via Tk's own
`wordstart`/`wordend` index modifiers on the Text widget, so this module
only ever has to answer one question: "where, if anywhere, is `name`
defined in this file?"

Same dispatch-by-extension shape as goto.py/linters.py, and the same
tradeoffs:

  - Python goes through ast (exact): function/class defs, imports, and
    a best-effort pass over every Name in Store context (plain
    assignments, augmented/annotated assignments, for-loop targets,
    comprehension targets, `with ... as`, except-clause names, match
    captures) - this is NOT real scope resolution, the same "collect
    every binding anywhere in the file" heuristic linters.py's
    undefined-name checker already uses. A name reused across two
    unrelated functions resolves to whichever binding this module
    happens to prefer (see _pick_best below), not necessarily the one
    actually in scope at the hover point. Good enough for a quick
    preview; not a substitute for real static analysis.
  - Every other supported language reuses goto.py's regex-based symbol
    extraction rather than duplicating it, so hover can only resolve
    the same functions/classes/consts/rules/ids goto.py's Ctrl+P popup
    can already jump to - nothing goto.py can't find, hover can't
    either. No separate variable tracking for these languages: the
    regex extractors were never scope-aware to begin with.
  - Unrecognized/unsupported extensions, or a name that matches
    nothing, return None - hover just shows nothing, same "degrade
    quietly" convention as every other optional feature in this app.

Nothing here ever raises out to the caller, matching goto.py/linters.py/
code_folding.py's own contract.
"""

import ast
import os

try:
    # goto.py is being imported as part of the "editor" package.
    from . import goto
except ImportError:
    # Standalone script - plain import, same fallback pattern app.py uses.
    import goto


_PREVIEW_MAX_LEN = 100


def _source_line(content, lineno):
    """1-based line `lineno` from `content`, stripped and truncated for
    display - or "" if out of range (shouldn't normally happen, but a
    stale/edited buffer could shift line counts between the AST pass and
    this lookup, so it's guarded rather than trusted)."""
    lines = content.split("\n")
    if lineno < 1 or lineno > len(lines):
        return ""
    line = lines[lineno - 1].strip()
    if len(line) > _PREVIEW_MAX_LEN:
        line = line[:_PREVIEW_MAX_LEN - 1] + "\u2026"
    return line


# ---------------- Python: ast (exact defs, heuristic variables) ----------------

def _function_signature(node):
    """A short `name(args)` preview built straight from the ast.arguments
    node - cheaper and more robust across Python versions than
    ast.unparse (which also would reformat the body, not just the
    signature, and isn't available before 3.9)."""
    args = node.args
    parts = [a.arg for a in args.posonlyargs] if hasattr(args, "posonlyargs") else []
    parts += [a.arg for a in args.args]
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    parts += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(parts)})"


def _docstring_summary(node):
    """First non-blank line of `node`'s docstring, if it has one - a
    one-line summary is plenty for a hover preview; the rest is a
    "go to definition" click away."""
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return None
    for line in doc.split("\n"):
        line = line.strip()
        if line:
            return line
    return None


def _collect_python_candidates(tree, name):
    """Every binding of `name` found anywhere in the tree, as a list of
    {"line", "kind", "detail"} dicts - deliberately unsorted-by-scope
    (see module docstring) since this app doesn't do real scope
    resolution anywhere else either."""
    candidates = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            candidates.append({
                "line": node.lineno,
                "kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "detail": _function_signature(node),
                "doc": _docstring_summary(node),
            })
        elif isinstance(node, ast.ClassDef) and node.name == name:
            candidates.append({
                "line": node.lineno,
                "kind": "class",
                "detail": f"class {node.name}",
                "doc": _docstring_summary(node),
            })
        elif isinstance(node, ast.arg) and node.arg == name:
            candidates.append({"line": node.lineno, "kind": "parameter", "detail": None, "doc": None})
        elif isinstance(node, ast.alias) and (node.asname or node.name).split(".")[0] == name:
            candidates.append({"line": node.lineno, "kind": "import", "detail": None, "doc": None})
        elif isinstance(node, ast.ExceptHandler) and node.name == name:
            candidates.append({"line": node.lineno, "kind": "exception", "detail": None, "doc": None})
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
            candidates.append({"line": node.lineno, "kind": "variable", "detail": None, "doc": None})
        else:
            # Match-statement capture patterns, guarded the same way
            # linters.py's _collect_bound_names guards them (these node
            # types don't exist before Python 3.10).
            bound_name = getattr(node, "name", None)
            if bound_name == name and node.__class__.__name__ in ("MatchAs", "MatchStar"):
                candidates.append({"line": node.lineno, "kind": "variable", "detail": None, "doc": None})

    return candidates


def _pick_best(candidates, hover_line):
    """Picks one candidate to show. Definitions (function/class/import)
    outrank plain variable bindings, since they're exact and usually
    what "go to definition" means anyway; among same-kind candidates,
    the nearest one at or before the hover line wins (falling back to
    the first one in the file if every binding happens to come after
    it) - a plain-text approximation of "closest enclosing scope" that's
    right far more often than it's wrong for typically-short functions."""
    if not candidates:
        return None

    def rank(c):
        kind_rank = 0 if c["kind"] in ("function", "async function", "class", "import") else 1
        return kind_rank

    best_rank = min(rank(c) for c in candidates)
    pool = [c for c in candidates if rank(c) == best_rank]

    before = [c for c in pool if c["line"] <= hover_line]
    if before:
        return max(before, key=lambda c: c["line"])
    return min(pool, key=lambda c: c["line"])


def _find_python_definition(content, name, hover_line):
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    try:
        candidates = _collect_python_candidates(tree, name)
    except RecursionError:
        return None
    return _pick_best(candidates, hover_line)


# ---------------- Everything else: reuse goto.py's symbol list ----------------

def _find_symbol_definition(path, content, name, hover_line):
    try:
        symbols = goto.extract_symbols(path, content)
    except Exception:
        return None
    matches = [s for s in symbols if s["name"] == name or s["name"].lstrip("#.") == name]
    if not matches:
        return None
    before = [s for s in matches if s["line"] <= hover_line]
    chosen = max(before, key=lambda s: s["line"]) if before else min(matches, key=lambda s: s["line"])
    return {"line": chosen["line"], "kind": chosen["kind"], "detail": None, "doc": None}


# ---------------- Dispatch ----------------

def find_definition(path, content, name, hover_line):
    """Returns {"name", "kind", "line", "preview", "doc"} for the nearest
    definition of `name` in `content`, or None if `name` is empty,
    `path`/`content` are missing, the extension isn't one CodeForge
    resolves definitions for, or nothing matches. Never raises - any
    parser hiccup just means no hover popup for this pass, the same
    "degrade quietly" convention as goto.py/linters.py."""
    if not name or not content or not path:
        return None

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".py", ".pyw"):
            result = _find_python_definition(content, name, hover_line)
        else:
            result = _find_symbol_definition(path, content, name, hover_line)
    except Exception:
        return None

    if result is None:
        return None

    return {
        "name": name,
        "kind": result["kind"],
        "line": result["line"],
        "preview": result.get("detail") or _source_line(content, result["line"]),
        "doc": result.get("doc"),
    }
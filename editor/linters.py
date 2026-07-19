"""
Lightweight diagnostics ("squiggly lines") for CodeForge.

lint(path, content) is the single entry point app.py calls (on a background
thread - see run_lint() there) and returns a list of diagnostic dicts:

    {"line": 1-based int, "col": 0-based int, "end_col": int or None,
     "severity": "error" | "warning", "message": str}

Every language gets *something*, but the depth varies with what's available
without asking the user to install anything:

  - Python, JSON, and XML are checked with the standard library's own
    parser (ast / json / xml.etree), so these are always exact and never
    need an external tool.
  - YAML is checked with PyYAML if it happens to be installed (optional
    dependency, same try/except pattern app.py already uses for
    tkinterdnd2/yt-dlp/python-vlc) - silently skipped otherwise.
  - JavaScript, C, C++, and Shell shell out to a real toolchain (node,
    gcc/g++, bash) *if* one is found on PATH, giving a real syntax check;
    if the tool isn't installed, they fall back to the generic checker
    below instead of giving up entirely.
  - Everything else (CSS, Java, JSX/TS/TSX, SQL) and any of the above
    without their external tool available uses a generic bracket/quote
    balance scanner - no real grammar, but it catches the single most
    common typo (a missing closing brace/paren/bracket or an unclosed
    string) in basically any C-like or bracket-using language.
  - HTML gets its own lightweight tag-balance scanner instead, since its
    "brackets" are angle-bracket tag pairs, not the same three characters
    the generic scanner looks for.
  - Markdown and plain text are prose, not syntax - there's nothing
    correct to flag them against, so they're always clean.

Nothing in here ever raises out to the caller: any unexpected failure
(a missing tool, a weird encoding, a checker choking on something odd)
just means no diagnostics for that pass, the same "degrade quietly"
philosophy as the rest of the app's optional integrations.
"""

import ast
import builtins
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:
    yaml = None


_SUBPROCESS_TIMEOUT = 5  # seconds - a hung compiler shouldn't hang typing
_MAX_DIAGNOSTICS = 200   # a pathological file shouldn't paint thousands of squiggles


def _diag(line, col, message, severity="error", end_col=None):
    return {
        "line": max(1, int(line)),
        "col": max(0, int(col)),
        "end_col": end_col,
        "severity": severity,
        "message": message,
    }


def _run(cmd):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT
        )
    except Exception:
        return None


def _first_available(names):
    """First of `names` that resolves to a real executable on PATH, or
    None if none of them do - callers treat None as "tool not installed,
    fall back to the generic checker" rather than an error."""
    for name in names:
        if shutil.which(name):
            return name
    return None


def _lint_via_temp_file(content, suffix, run_cmd, parse_fn):
    """Writes `content` to a throwaway file with the right extension (most
    external tools only work on real files), runs it through `run_cmd`,
    hands the result to `parse_fn`, and always cleans the temp file up
    afterwards regardless of how that goes."""
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        proc = run_cmd(temp_path)
        if proc is None:
            return None
        return parse_fn(proc, temp_path)
    except Exception:
        return None
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


# ---------------- Python (stdlib ast - always available) ----------------
def _lint_python(content):
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        line = exc.lineno or 1
        col = max((exc.offset or 1) - 1, 0)
        end_col = None
        if exc.end_lineno == line and exc.end_offset:
            end_col = exc.end_offset - 1
        return [_diag(line, col, exc.msg or "Syntax error", "error", end_col)]
    except (ValueError, RecursionError, UnicodeDecodeError):
        return []

    # No syntax error - also do a best-effort pass for names that are used
    # but never assigned anywhere in the file (calling an undefined
    # function, referencing a typo'd variable, etc). This is NOT real
    # scope resolution: it collects every name assigned *anywhere* in the
    # file regardless of which function/class it's in, so it can miss
    # things a real scope-aware checker (pyflakes) would catch, and won't
    # false-positive on legitimate forward references. Reported as a
    # warning rather than an error to reflect that it's a heuristic.
    try:
        return _lint_python_undefined_names(tree)
    except Exception:
        return []


def _collect_bound_names(tree):
    """Every name that's assigned, imported, defined, or bound as a
    parameter anywhere in the file, plus all builtins - the "known good"
    set that _lint_python_undefined_names checks reads against."""
    bound = set(dir(builtins))
    bound.update({"__name__", "__file__", "__doc__", "__package__", "self", "cls"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        else:
            # Match-statement capture patterns (MatchAs/MatchStar/
            # MatchMapping's **rest) - guarded with getattr since these
            # AST nodes don't exist before Python 3.10.
            name = getattr(node, "name", None)
            if name and node.__class__.__name__ in ("MatchAs", "MatchStar"):
                bound.add(name)
            rest = getattr(node, "rest", None)
            if rest and node.__class__.__name__ == "MatchMapping":
                bound.add(rest)
    return bound


def _lint_python_undefined_names(tree):
    # A `from x import *` makes it impossible to know what's actually in
    # scope, so bail out entirely rather than flag a wall of false
    # positives for perfectly legitimate names it brought in.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return []

    bound = _collect_bound_names(tree)
    diags = []
    seen = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
            continue
        if node.id in bound:
            continue
        key = (node.lineno, node.col_offset, node.id)
        if key in seen:
            continue
        seen.add(key)
        diags.append(_diag(
            node.lineno, node.col_offset, f"'{node.id}' is not defined", "warning",
            end_col=node.col_offset + len(node.id)
        ))
    return diags[:_MAX_DIAGNOSTICS]


# ---------------- JSON (stdlib json - always available) ----------------
def _lint_json(content):
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return [_diag(exc.lineno, max(exc.colno - 1, 0), exc.msg, "error")]
    except Exception:
        pass
    return []


# ---------------- XML (stdlib ElementTree - always available) ----------------
def _lint_xml(content):
    try:
        ET.fromstring(content)
    except ET.ParseError as exc:
        line, col = exc.position
        message = str(exc)
        # ElementTree's message is "<reason>: line N, column M" - the
        # position is already conveyed by line/col above, so trim the
        # redundant suffix rather than showing it twice in the tooltip.
        message = re.sub(r":\s*line\s+\d+,\s*column\s+\d+\s*$", "", message)
        return [_diag(line, col, message or "XML parse error", "error")]
    except Exception:
        pass
    return []


# ---------------- YAML (optional: pip install pyyaml) ----------------
def _lint_yaml(content):
    if yaml is None:
        return []
    try:
        for _ in yaml.safe_load_all(content):
            pass
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        message = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        if mark is not None:
            return [_diag(mark.line + 1, mark.column, message, "error")]
        return [_diag(1, 0, message, "error")]
    except Exception:
        pass
    return []


# ---------------- JavaScript (optional: node on PATH) ----------------
_NODE_SYNTAX_ERROR_RE = re.compile(r"SyntaxError:\s*(.+)")


def _parse_node_check(proc, temp_path):
    if proc.returncode == 0:
        return []
    line_no = 1
    message = "Syntax error"
    prefix = temp_path + ":"
    for line in proc.stderr.splitlines():
        if line.startswith(prefix):
            try:
                line_no = int(line[len(prefix):])
            except ValueError:
                pass
        m = _NODE_SYNTAX_ERROR_RE.search(line)
        if m:
            message = m.group(1).strip()
            break
    return [_diag(line_no, 0, message, "error")]


def _lint_javascript(content):
    node = _first_available(["node"])
    if not node:
        return None
    return _lint_via_temp_file(
        content, ".js",
        lambda path: _run([node, "--check", path]),
        _parse_node_check,
    )


# ---------------- C / C++ (optional: gcc/g++ on PATH) ----------------
_GCC_DIAG_RE = re.compile(r":(\d+):(\d+):\s*(error|warning):\s*(.+)")


def _parse_gcc_output(proc, temp_path):
    diags = []
    prefix = temp_path + ":"
    for line in proc.stderr.splitlines():
        if not line.startswith(prefix):
            continue
        m = _GCC_DIAG_RE.match(line[len(temp_path):])
        if not m:
            continue
        line_no, col_no, severity, message = m.groups()
        diags.append(_diag(line_no, max(int(col_no) - 1, 0), message.strip(), severity))
    return diags[:_MAX_DIAGNOSTICS]


def _lint_c_family(content, suffix, compiler_names):
    compiler = _first_available(compiler_names)
    if not compiler:
        return None
    return _lint_via_temp_file(
        content, suffix,
        lambda path: _run([compiler, "-fsyntax-only", "-w", path]),
        _parse_gcc_output,
    )


# ---------------- Shell (optional: bash on PATH) ----------------
_BASH_LINE_RE = re.compile(r":\s*line\s+(\d+):\s*(.+)")


def _parse_bash_check(proc, temp_path):
    if proc.returncode == 0:
        return []
    diags = []
    for line in proc.stderr.splitlines():
        m = _BASH_LINE_RE.search(line)
        if m:
            diags.append(_diag(m.group(1), 0, m.group(2).strip(), "error"))
    if not diags:
        last = proc.stderr.strip().splitlines()
        diags.append(_diag(1, 0, last[-1] if last else "Syntax error", "error"))
    return diags


def _lint_shell(content):
    bash = _first_available(["bash"])
    if not bash:
        return None
    return _lint_via_temp_file(
        content, ".sh",
        lambda path: _run([bash, "-n", path]),
        _parse_bash_check,
    )


# ---------------- Generic fallback: bracket/quote balance ----------------
# No real grammar - just tracks (), [], {} nesting and string literals while
# skipping over comments, so it works reasonably for any C-like or bracket-
# using language CodeForge doesn't have a dedicated checker for (or where
# the dedicated tool isn't installed). Good enough to catch a missing
# closing brace or an unterminated string; not a substitute for a real
# parser, and doesn't try to be one.
_BRACKET_OPENERS = {"(": ")", "[": "]", "{": "}"}
_BRACKET_CLOSERS = {v: k for k, v in _BRACKET_OPENERS.items()}


def _lint_brackets_and_quotes(content, line_comment=None, block_comment=None, quote_chars="\"'"):
    diags = []
    stack = []
    line = 1
    col = 0
    i = 0
    n = len(content)
    in_string = None
    string_start = None

    while i < n:
        ch = content[i]

        if ch == "\n":
            line += 1
            col = 0
            i += 1
            continue

        if in_string:
            if ch == "\\" and in_string != "`":
                i += 2
                col += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            col += 1
            continue

        if block_comment and content.startswith(block_comment[0], i):
            end = content.find(block_comment[1], i + len(block_comment[0]))
            if end == -1:
                break
            skipped = content[i:end + len(block_comment[1])]
            newlines = skipped.count("\n")
            if newlines:
                line += newlines
                col = len(skipped) - skipped.rfind("\n") - 1
            else:
                col += len(skipped)
            i = end + len(block_comment[1])
            continue

        if line_comment and content.startswith(line_comment, i):
            end = content.find("\n", i)
            if end == -1:
                break
            i = end
            continue

        if ch in quote_chars:
            in_string = ch
            string_start = (line, col)
            i += 1
            col += 1
            continue

        if ch in _BRACKET_OPENERS:
            stack.append((ch, line, col))
        elif ch in _BRACKET_CLOSERS:
            if stack and stack[-1][0] == _BRACKET_CLOSERS[ch]:
                stack.pop()
            else:
                diags.append(_diag(line, col, f"Unexpected '{ch}'", "error"))

        i += 1
        col += 1

    if in_string and string_start:
        diags.append(_diag(string_start[0], string_start[1], "Unterminated string literal", "error"))

    for ch, line_no, col_no in stack:
        diags.append(_diag(line_no, col_no, f"'{ch}' is never closed", "error"))

    return diags[:_MAX_DIAGNOSTICS]


# ---------------- HTML: tag-balance scanner ----------------
_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
_HTML_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9:-]*)([^>]*?)(/?)>")


def _lint_html(content):
    diags = []
    stack = []

    for m in _HTML_TAG_RE.finditer(content):
        closing, name, _attrs, self_close = m.groups()
        name = name.lower()
        line = content.count("\n", 0, m.start()) + 1
        col = m.start() - (content.rfind("\n", 0, m.start()) + 1)

        if closing:
            if stack and stack[-1][0] == name:
                stack.pop()
            elif any(entry[0] == name for entry in stack):
                # Closes an ancestor that skipped some tags in between -
                # pop back to it, flagging whatever got skipped as
                # (probably) unclosed rather than silently dropping them.
                while stack and stack[-1][0] != name:
                    unclosed = stack.pop()
                    diags.append(_diag(
                        unclosed[1], unclosed[2],
                        f"'<{unclosed[0]}>' is never closed", "warning"
                    ))
                if stack:
                    stack.pop()
            else:
                diags.append(_diag(line, col, f"'</{name}>' has no matching opening tag", "error"))
        elif self_close or name in _VOID_ELEMENTS:
            continue
        else:
            stack.append((name, line, col))

    for name, line, col in stack:
        diags.append(_diag(line, col, f"'<{name}>' is never closed", "warning"))

    return diags[:_MAX_DIAGNOSTICS]


# ---------------- Dispatch ----------------
_EXT_LANGUAGE = {
    ".py": "python", ".pyw": "python",
    ".json": "json",
    ".xml": "xml",
    ".yml": "yaml", ".yaml": "yaml",
    ".html": "html", ".htm": "html",
    ".css": "css",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript", ".tsx": "tsx",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp",
    ".java": "java",
    ".sh": "shell",
    ".sql": "sql",
}


def lint(path, content):
    """Return a list of diagnostics for `content`, dispatched by the file
    extension in `path`. Never raises - any unexpected failure just means
    no diagnostics for this pass rather than crashing the editor."""
    if not content or not content.strip():
        return []

    ext = os.path.splitext(path or "")[1].lower()
    language = _EXT_LANGUAGE.get(ext)
    if language is None:
        return []  # Markdown, plain text, or anything unrecognized: no syntax to violate

    try:
        if language == "python":
            return _lint_python(content)
        if language == "json":
            return _lint_json(content)
        if language == "xml":
            return _lint_xml(content)
        if language == "yaml":
            return _lint_yaml(content)
        if language == "html":
            return _lint_html(content)
        if language == "css":
            return _lint_brackets_and_quotes(content, block_comment=("/*", "*/"))
        if language == "javascript":
            diagnostics = _lint_javascript(content)
            if diagnostics is not None:
                return diagnostics
            return _lint_brackets_and_quotes(content, line_comment="//", block_comment=("/*", "*/"))
        if language in ("jsx", "typescript", "tsx"):
            # node --check chokes on valid JSX/TS syntax (it's not plain
            # JS), so this would flag correct code as broken - stick to
            # the generic bracket/quote scanner for these instead.
            return _lint_brackets_and_quotes(
                content, line_comment="//", block_comment=("/*", "*/"), quote_chars="\"'`"
            )
        if language == "c":
            diagnostics = _lint_c_family(content, ".c", ["gcc", "cc", "clang"])
            if diagnostics is not None:
                return diagnostics
            return _lint_brackets_and_quotes(content, line_comment="//", block_comment=("/*", "*/"))
        if language == "cpp":
            diagnostics = _lint_c_family(content, ".cpp", ["g++", "c++", "clang++"])
            if diagnostics is not None:
                return diagnostics
            return _lint_brackets_and_quotes(content, line_comment="//", block_comment=("/*", "*/"))
        if language == "java":
            # javac needs a real compile (public-class-name-must-match-
            # filename rules, a real output dir, classpath...) to get
            # anything beyond this, which is a lot of false-positive risk
            # for a background checker - the generic scanner is the safer
            # default here.
            return _lint_brackets_and_quotes(content, line_comment="//", block_comment=("/*", "*/"))
        if language == "shell":
            diagnostics = _lint_shell(content)
            return diagnostics if diagnostics is not None else []
        if language == "sql":
            return _lint_brackets_and_quotes(content, line_comment="--", block_comment=("/*", "*/"))
    except Exception:
        return []

    return []